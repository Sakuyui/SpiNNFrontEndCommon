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

from spinn_utilities.progress_bar import ProgressBar
from spinn_front_end_common.utility_models import (
    ExtraMonitorSupportMachineVertex)
from spinn_front_end_common.utility_models import (
    DataSpeedUpPacketGatherMachineVertex)


class PreAllocateResourcesForExtraMonitorSupport(object):
    """ Allocates resources for the extra monitors.
    """
    def __call__(
            self, machine, pre_allocated_resources,
            n_cores_to_allocate=1):
        """
        :param ~spinn_machine.Machine machine: SpiNNaker machine object
        :param pre_allocated_resources: resources already preallocated
        :type pre_allocated_resources:
            ~pacman.model.resources.ResourceReservations
        :param int n_cores_to_allocate: how many gatherers to use per chip
        :rtype: ~pacman.model.resources.PreAllocatedResourceContainer
        """

        progress_bar = ProgressBar(
            1, "Preallocating resources for Extra Monitor support vertices")

        resources = DataSpeedUpPacketGatherMachineVertex.\
            static_resources_required()
        pre_allocated_resources.add_sdram_ethernet(resources.sdram)
        pre_allocated_resources.add_cores_ethernet(n_cores_to_allocate)
        pre_allocated_resources.add_iptag_resource(resources.iptags[0])

        extra_usage = \
            ExtraMonitorSupportMachineVertex.static_resources_required()
        pre_allocated_resources.add_sdram_all(extra_usage.sdram)
        pre_allocated_resources.add_cores_all(1)

        progress_bar.end()
        return pre_allocated_resources
