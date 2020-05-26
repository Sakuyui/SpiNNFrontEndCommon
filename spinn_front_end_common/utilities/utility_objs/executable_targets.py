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

from collections import defaultdict
from spinn_utilities.overrides import overrides
from spinn_utilities.ordered_set import OrderedSet
from spinnman.model import ExecutableTargets as SuperExecTargets


class ExecutableTargets(SuperExecTargets):
    __slots__ = ["_binary_type_map"]
    # pylint: disable=arguments-differ

    def __init__(self):
        super(ExecutableTargets, self).__init__()
        self._binary_type_map = defaultdict(OrderedSet)

    @overrides(SuperExecTargets.add_subsets)
    def add_subsets(self, binary, subsets, executable_type=None):
        """
        :type binary: str
        :type subsets: ~spinn_machine.CoreSubsets
        :param ExecutableType executable_type:
        """
        SuperExecTargets.add_subsets(self, binary, subsets)
        if executable_type is not None:
            self._binary_type_map[executable_type].add(binary)

    def place_binary(self, binary, placement, executable_type=None):
        """
        :param str binary:
        :param ~pacman.model.placements.Placement placement:
        :param ExecutableType executable_type:
        """
        self.add_processor(binary, placement.x, placement.y, placement.p)
        if executable_type is not None:
            self._binary_type_map[executable_type].add(binary)

    def get_n_cores_for_executable_type(self, executable_type):
        """ get the number of cores that the executable type is using

        :param ExecutableType executable_type:
            the executable type for locating n cores of
        :return: the number of cores using this executable type
        :rtype: int
        """
        return sum(
            len(self.get_cores_for_binary(aplx))
            for aplx in self._binary_type_map[executable_type])

    def get_binaries_of_executable_type(self, executable_type):
        """ get the binaries of a given a executable type

        :param ExecutableType executable_type: the executable type enum value
        :return: iterable of binaries with that executable type
        :rtype: iterable(str)
        """
        return self._binary_type_map[executable_type]

    def executable_types_in_binary_set(self):
        """ get the executable types in the set of binaries

        :return: iterable of the executable types in this binary set.
        :rtype: iterable(ExecutableType)
        """
        return self._binary_type_map.keys()
