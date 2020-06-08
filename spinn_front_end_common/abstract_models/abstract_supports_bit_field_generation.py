# Copyright (c) 2019-2020 The University of Manchester
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

from spinn_utilities.abstract_base import AbstractBase, abstractmethod
from six import add_metaclass


@add_metaclass(AbstractBase)
class AbstractSupportsBitFieldGeneration(object):

    @abstractmethod
    def bit_field_base_address(self, transceiver, placement):
        """ returns the sdram address for the bit field table data

        :param transceiver: txrx
        :param placement: placement
        :return: the sdram address for the bitfield address
        """

    @abstractmethod
    def bit_field_builder_region(self, transceiver, placement):
        """ returns the sdram address for the bit field builder data

        :param transceiver: txrx
        :param placement: placement
        :return: the sdram address for the bitfield builder data
        """
