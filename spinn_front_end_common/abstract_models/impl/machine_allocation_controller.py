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
import sys
from threading import Thread
from spinn_utilities.log import FormatAdapter
from spinn_utilities.overrides import overrides
from spinn_utilities.abstract_base import AbstractBase, abstractmethod
from spinnman.constants import SCP_SCAMP_PORT
from spinnman.connections.udp_packet_connections import SCAMPConnection
from spinnman.transceiver import create_transceiver_from_hostname
from spinn_front_end_common.abstract_models import (
    AbstractMachineAllocationController)
from spinnman.connections.udp_packet_connections import EIEIOConnection
logger = FormatAdapter(logging.getLogger(__name__))


class MachineAllocationController(
        AbstractMachineAllocationController, metaclass=AbstractBase):
    """ How to manage the allocation of a machine so that it gets cleaned up\
        neatly when the script dies.
    """
    __slots__ = [
        #: boolean flag for telling this thread when the system has ended
        "_exited",
        #: the address of the root board of the allocation
        "__hostname",
        "__connection_data"
    ]

    def __init__(self, thread_name, hostname=None, connection_data=None):
        """
        :param str thread_name:
        """
        thread = Thread(name=thread_name, target=self.__manage_allocation)
        thread.daemon = True
        self._exited = False
        self.__hostname = hostname
        self.__connection_data = connection_data
        thread.start()

    @overrides(AbstractMachineAllocationController.close)
    def close(self):
        self._exited = True

    @abstractmethod
    def _wait(self):
        """ Wait for some bounded amount of time for a change in the status\
            of the machine allocation.

        :return: Whether the machine is still (believed to be) allocated.
        :rtype: bool
        """

    def _teardown(self):
        """ Perform any extra teardown that the thread requires. Does not\
            need to be overridden if no action is desired."""

    def __manage_allocation(self):
        machine_still_allocated = True
        while machine_still_allocated and not self._exited:
            machine_still_allocated = self._wait()
        self._teardown()
        if not self._exited:
            logger.error(
                "The allocated machine has been released before the end of"
                " the script; this script will now exit")
            sys.exit(1)

    @overrides(AbstractMachineAllocationController.create_transceiver)
    def create_transceiver(self):
        if not self.__hostname:
            return None
        return create_transceiver_from_hostname(
            hostname=self.__hostname,
            bmp_connection_data=None,
            version=5, auto_detect_bmp=False)

    @overrides(AbstractMachineAllocationController.open_sdp_connection)
    def open_sdp_connection(self, chip_x, chip_y, udp_port=SCP_SCAMP_PORT):
        if not self.__connection_data:
            return None
        host = self.__connection_data[chip_x, chip_y]
        if not host:
            return None
        return SCAMPConnection(
            chip_x=chip_x, chip_y=chip_y,
            remote_host=host, remote_port=udp_port)

    @overrides(AbstractMachineAllocationController.open_eieio_connection)
    def open_eieio_connection(self, chip_x, chip_y):
        if not self.__connection_data:
            return None
        host = self.__connection_data[chip_x, chip_y]
        if not host:
            return None
        return EIEIOConnection(remote_host=host, remote_port=SCP_SCAMP_PORT)

    @overrides(AbstractMachineAllocationController.open_eieio_listener)
    def open_eieio_listener(self):
        return EIEIOConnection()
