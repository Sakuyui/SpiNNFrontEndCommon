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

import os
from spinn_utilities.progress_bar import ProgressBar
from spinn_front_end_common.data import FecDataView


class BoardChipReport(object):
    """ Report on memory usage
    """

    AREA_CODE_REPORT_NAME = "board_chip_report.txt"

    def __call__(self, machine):
        """ Creates a report that states where in SDRAM each region is.

        :param ~spinn_machine.Machine machine:
            python representation of the machine
        :rtype: None
        """

        # create file path
        directory_name = os.path.join(
            FecDataView().run_dir_path, self.AREA_CODE_REPORT_NAME)

        # create the progress bar for end users
        progress_bar = ProgressBar(
            len(machine.ethernet_connected_chips),
            "Writing the board chip report")

        # iterate over ethernet chips and then the chips on that board
        with open(directory_name, "w") as writer:
            self._write_report(writer, machine, progress_bar)

    @staticmethod
    def _write_report(writer, machine, progress_bar):
        """
        :param ~io.FileIO writer:
        :param ~spinn_machine.Machine machine:
        :param ~spinn_utilities.progress_bar.ProgressBar progress_bar:
        """
        for chip in progress_bar.over(machine.ethernet_connected_chips):
            xys = machine.get_existing_xys_on_board(chip)
            writer.write(
                "board with IP address : {} : has chips {}\n".format(
                    chip.ip_address, list(xys)))
