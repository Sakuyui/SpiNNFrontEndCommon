# Copyright (c) 2017-2019 The University of Manchester
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import math
import os
import tempfile
from spinn_utilities.config_holder import get_config_int
from spinn_utilities.log import FormatAdapter
from spinn_front_end_common.utilities.constants import (
    MICRO_TO_MILLISECOND_CONVERSION, MICRO_TO_SECOND_CONVERSION)
from spinn_front_end_common.utilities.exceptions import ConfigurationException
from .data_status import Data_Status
from .fec_data_view import FecDataView, _FecDataModel

logger = FormatAdapter(logging.getLogger(__name__))
__temp_dir = None


class FecDataWriter(FecDataView):
    """
    Writer class for the Fec Data

    """
    __fec_data = _FecDataModel()
    __slots__ = []

    def mock(self):
        """
        Clears out all data and adds mock values where needed.

        This should set the most likely defaults values.
        But be aware that what is considered the most likely default could
        change over time.

        Unittests that depend on any valid value being set should be able to
        depend on Mock.

        Unittest that depend on a specific value should call mock and then
        set that value.
        """
        self.__fec_data._clear()
        self.__fec_data._n_calls_to_run = 0
        self.__fec_data._status = Data_Status.MOCKED
        self.__set_up_report_mocked()
        self.set_app_id(6)
        self.set_up_timings(1000, 1)

    def setup(self):
        """
        Puts all data back into the state expected at sim.setup time

        """
        self.__fec_data._clear()
        self.__fec_data._n_calls_to_run = 0
        self.__fec_data._status = Data_Status.SETUP
        self.__set_up_report_specifics()

    def start_run(self):
        self.__fec_data._n_calls_to_run += 1
        self.__fec_data._status = Data_Status.IN_RUN

    def finish_run(self):
        self.__fec_data._status = Data_Status.FINISHED

    def __set_up_report_mocked(self):
        """
        Sets all the directories used to a Temporary Directory
        """
        temp_dir = tempfile.TemporaryDirectory()

        self.__fec_data._report_default_directory = temp_dir
        self.__fec_data._provenance_file_path = temp_dir

    def __set_up_report_specifics(self):
        # This is a highly simplified example
        report_simulation_top_directory = os.getcwd()
        self.__fec_data._report_default_directory = os.path.join(
            report_simulation_top_directory, f"run_{self.n_calls_to_run}")
        logger.info(self.report_default_directory)
        self.__fec_data._provenance_file_path = os.path.join(
            self.__fec_data._report_default_directory,
            "provenance_data")

    def set_app_id(self, app_id):
        """
        Sets the app_id value

        :param int app_id: new value
        """
        if not isinstance(app_id, int):
            raise TypeError("app_id should be an int")
        self.__fec_data._app_id = app_id

    def set_up_timings(
            self, simulation_time_step_us, time_scale_factor,
            default_time_scale_factor=None):
        """ Set up timings for the simulation

        :param simulation_time_step_us:
            An explicitly specified time step for the simulation in .
            If None, the value is read from the config
        :type simulation_time_step_us: int or None
        :param time_scale_factor:
            An explicitly specified time scale factor for the simulation.
            If None, the value is read from the config
        :type time_scale_factor: float or None
        :param default_time_scale_factor:
            A back up time scale factor for the simulation.
            Only used if time_scale_factor param and cfg are both None
            If None, the value is based on simulation_time_step
        :type default_time_scale_factor: float or None
        """
        try:
            self._set_simulation_time_step(simulation_time_step_us)
            self._set_time_scale_factor(
                time_scale_factor, default_time_scale_factor)
            self._set_hardware_timestep()
        except ConfigurationException:
            self.__fec_data._simulation_time_step_us = None
            self.__fec_data._simulation_time_step_ms = None
            self.__fec_data._simulation_time_step_per_ms = None
            self.__fec_data._simulation_time_step_per_s = None
            self.__fec_data._simulation_time_step_s = None
            self.__fec_data._time_scale_factor = None
            self.__fec_data._hardware_time_step_us = None
            self.__fec_data._hardware_time_step_ms = None
            raise

    def _set_simulation_time_step(self, simulation_time_step_us):
        """

        :param simulation_time_step_us:
            An explicitly specified time step for the simulation.  If None,
            the value is read from the config
        :type simulation_time_step: int or None
        """
        if simulation_time_step_us is None:
            simulation_time_step_us = get_config_int(
                "Machine", "simulation_time_step")

        if not isinstance(simulation_time_step_us, int):
            raise TypeError("simulation_time_step_us should be an int")

        if simulation_time_step_us <= 0:
            raise ConfigurationException(
                f'invalid simulation_time_step {simulation_time_step_us}'
                f': must greater than zero')

        self.__fec_data._simulation_time_step_us = simulation_time_step_us
        self.__fec_data._simulation_time_step_ms = (
                simulation_time_step_us / MICRO_TO_MILLISECOND_CONVERSION)
        self.__fec_data._simulation_time_step_per_ms = (
                MICRO_TO_MILLISECOND_CONVERSION / simulation_time_step_us)
        self.__fec_data._simulation_time_step_per_s = (
                MICRO_TO_SECOND_CONVERSION / simulation_time_step_us)
        self.__fec_data._simulation_time_step_s = (
                simulation_time_step_us / MICRO_TO_SECOND_CONVERSION)

    def _set_time_scale_factor(
            self, time_scale_factor, default_time_scale_factor):
        """ Set up time_scale_factor

        If time_scale_factor is provide that is used

        Then if cfg is not None that is used

        Then if default is provided that is used

        Lastly it is set based on the simulation_time_step

        :param time_scale_factor:
            An explicitly specified time scale factor for the simulation.
            If None, the value is read from the config
        :type time_scale_factor: float or None
        """
        if time_scale_factor is None:
            # Note while this reads from the cfg the cfg default is None
            time_scale_factor = get_config_int(
                "Machine", "time_scale_factor")

        if time_scale_factor is None:
            if default_time_scale_factor is not None:
                time_scale_factor = default_time_scale_factor

        if time_scale_factor is None:
            time_scale_factor = max(
                1.0, math.ceil(self.get_simulation_time_step_per_ms()))
            if time_scale_factor > 1.0:
                logger.warning(
                    "A timestep was entered that has forced spinnaker to "
                     f"automatically slow the simulation down from real time "
                    "by a factor of {time_scale_factor}.")

        if not isinstance(time_scale_factor, (int, float)):
            raise TypeError("app_id should be an int (or float)")

        if time_scale_factor <= 0:
            raise ConfigurationException(
                f'invalid time_scale_factor {time_scale_factor}'
                f': must greater than zero')

        self.__fec_data._time_scale_factor = time_scale_factor

    def _set_hardware_timestep(self):
        raw = (self.get_simulation_time_step_us() *
               self.get_time_scale_factor())
        rounded = round(raw)
        if abs(rounded - raw) > 0.0001:
            raise ConfigurationException(
                f"The multiplication of simulation time step in microseconds: "
                f"{self.get_simulation_time_step_us()} and times scale factor"
                f": {self.get_time_scale_factor()} produced a non integer "
                f"hardware time step of {raw}")

        logger.info(f"Setting hardware timestep as {rounded} microseconds "
                    f"based on simulation time step of "
                    f"{self.get_simulation_time_step_us()} and "
                    f"timescale factor of {self.get_time_scale_factor()}")
        self.__fec_data._hardware_time_step_us = rounded
        self.__fec_data._hardware_time_step_ms = (
                rounded / MICRO_TO_MILLISECOND_CONVERSION)
