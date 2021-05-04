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

from enum import Enum
from spinn_utilities.abstract_base import abstractproperty
from spinn_utilities.overrides import overrides
from data_specification.utility_calls import get_region_base_address_offset
from .abstract_provides_provenance_data_from_machine import (
    AbstractProvidesProvenanceDataFromMachine)
from spinn_front_end_common.utilities.constants import BYTES_PER_WORD
from spinn_front_end_common.utilities.helpful_functions import n_word_struct
from spinn_front_end_common.utilities.utility_objs import ProvenanceDataItem


def add_name(names, name):
    """
    :param iterable(str) names:
    :param str name:
    :rtype: list(str)
    """
    new_names = list(names)
    new_names.append(name)
    return new_names


class ProvidesProvenanceDataFromMachineImpl(
        AbstractProvidesProvenanceDataFromMachine, allow_derivation=True):
    """ An implementation that gets provenance data from a region of ints on\
        the machine.
    """

    __slots__ = ()

    class PROVENANCE_DATA_ENTRIES(Enum):
        """ Entries for the provenance data generated by models using provides\
            provenance vertex.
        """
        #: The counter of transmission overflows
        TRANSMISSION_EVENT_OVERFLOW = 0
        #: The counter of the number of times the callback queue was overloaded
        CALLBACK_QUEUE_OVERLOADED = 1
        #: The counter of the number of times the DMA queue was overloaded
        DMA_QUEUE_OVERLOADED = 2
        #: Whether the timer tick has overrun at all at any point
        TIMER_TIC_HAS_OVERRUN = 3
        #: The counter of the number of times the timer tick overran
        MAX_NUMBER_OF_TIMER_TIC_OVERRUN = 4

    N_SYSTEM_PROVENANCE_WORDS = len(PROVENANCE_DATA_ENTRIES)

    _TIMER_TICK_OVERRUN = "Times_the_timer_tic_over_ran"
    _MAX_TIMER_TICK_OVERRUN = "max_number_of_times_timer_tic_over_ran"
    _TIMES_DMA_QUEUE_OVERLOADED = "Times_the_dma_queue_was_overloaded"
    _TIMES_TRANSMISSION_SPIKES_OVERRAN = \
        "Times_the_transmission_of_spikes_overran"
    _TIMES_CALLBACK_QUEUE_OVERLOADED = \
        "Times_the_callback_queue_was_overloaded"

    @abstractproperty
    def _provenance_region_id(self):
        """ The index of the provenance region.

        :rtype: int
        """

    @abstractproperty
    def _n_additional_data_items(self):
        """ The number of extra machine words of provenance that the model \
            reports.

        :rtype: int
        """

    def reserve_provenance_data_region(self, spec):
        """
        :param ~data_specification.DataSpecificationGenerator spec:
            The data specification being written.
        """
        spec.reserve_memory_region(
            self._provenance_region_id,
            self.get_provenance_data_size(self._n_additional_data_items),
            label="Provenance", empty=True)

    @classmethod
    def get_provenance_data_size(cls, n_additional_data_items):
        """
        :param int n_additional_data_items:
        :rtype: int
        """
        return (
            (cls.N_SYSTEM_PROVENANCE_WORDS + n_additional_data_items)
            * BYTES_PER_WORD)

    def _get_provenance_region_address(self, transceiver, placement):
        """
        :param ~spinnman.transceiver.Transceiver transceiver:
        :param ~pacman.model.placements.Placement placement:
        :rtype: int
        """
        # Get the App Data for the core
        region_table_address = transceiver.get_cpu_information_from_core(
            placement.x, placement.y, placement.p).user[0]

        # Get the provenance region base address
        prov_region_entry_address = get_region_base_address_offset(
            region_table_address, self._provenance_region_id)
        return transceiver.read_word(
            placement.x, placement.y, prov_region_entry_address)

    def _read_provenance_data(self, transceiver, placement):
        """
        :param ~spinnman.transceiver.Transceiver transceiver:
        :param ~pacman.model.placements.Placement placement:
        :rtype: iterable(int)
        """
        provenance_address = self._get_provenance_region_address(
            transceiver, placement)
        data = transceiver.read_memory(
            placement.x, placement.y, provenance_address,
            self.get_provenance_data_size(self._n_additional_data_items))
        return n_word_struct(
            self.N_SYSTEM_PROVENANCE_WORDS +
            self._n_additional_data_items).unpack_from(data)

    @staticmethod
    def _get_provenance_placement_description(placement):
        """
        :param ~pacman.model.placements.Placement placement:
        :returns:
            A descriptive (human-readable) label and a mechanical label
            (or prefix of one) for provenance items from the given placement.
        :rtype: tuple(str,list(str))
        """
        label = placement.vertex.label
        x = placement.x
        y = placement.y
        p = placement.p
        names = [f"vertex_{x}_{y}_{p}_{label}"]
        desc_label = f"{label} on {x},{y},{p}"
        return desc_label, names

    def parse_system_provenance_items(self, label, names, provenance_data):
        """
        Given some words of provenance data, convert the portion of them that
        describes the system provenance into proper provenance items.

        Called by
        :py:meth:`~spinn_front_end_common.interface.provenance.ProvidesProvenanceDataFromMachineImpl.parse_extra_provenance_items.get_provenance_data_from_machine`

        :param str label:
            A descriptive label for the vertex (derived from label and placed
            position) to be used for provenance error reporting to the user.
        :param list(str) names:
            The base names describing the location of the machine vertex
            producing the provenance.
        :param list(int) provenance_data:
        :rtype: ~collections.abc.Iterable(ProvenanceDataItem)
        """
        (tx_overflow, cb_overload, dma_overload, tic_overruns,
         tic_overrun_max) = provenance_data[:self.N_SYSTEM_PROVENANCE_WORDS]

        # create provenance data items for returning
        yield ProvenanceDataItem(
            names + [self._TIMES_TRANSMISSION_SPIKES_OVERRAN], tx_overflow,
            (tx_overflow != 0),
            f"The transmission buffer for {label} was blocked on "
            f"{tx_overflow} occasions.  This is often a sign that the system "
            "is experiencing back pressure from the communication fabric. "
            "Please either: "
            "1. spread the load over more cores, "
            "2. reduce your peak transmission load, or "
            "3. adjust your mapping algorithm.")
        yield ProvenanceDataItem(
            names + [self._TIMES_CALLBACK_QUEUE_OVERLOADED],
            cb_overload, (cb_overload != 0),
            f"The callback queue for {label} overloaded on {cb_overload} "
            "occasions.  This is often a sign that the system is running too "
            "quickly for the number of neurons per core.  Please increase the "
            "machine time step or time_scale_factor or decrease the number of "
            "neurons per core.")
        yield ProvenanceDataItem(
            names + [self._TIMES_DMA_QUEUE_OVERLOADED], dma_overload,
            (dma_overload != 0),
            f"The DMA queue for {label} overloaded on {dma_overload} "
            "occasions.  This is often a sign that the system is running too "
            "quickly for the number of neurons per core.  Please increase the "
            "machine time step or time_scale_factor or decrease the number of "
            "neurons per core.")
        yield ProvenanceDataItem(
            names + [self._TIMER_TICK_OVERRUN], tic_overruns,
            (tic_overruns != 0),
            f"A Timer tick callback in {label} was still executing when the "
            f"next timer tick callback was fired off {tic_overruns} times.  "
            "This is a sign of the system being overloaded and therefore the "
            "results are likely incorrect.  Please increase the machine time "
            "step or time_scale_factor or decrease the number of neurons per "
            "core")
        yield ProvenanceDataItem(
            names + [self._MAX_TIMER_TICK_OVERRUN], tic_overrun_max,
            (tic_overrun_max > 0),
            f"The timer for {label} fell behind by up to {tic_overrun_max} "
            "ticks.  This is a sign of the system being overloaded and "
            "therefore the results are likely incorrect. Please increase the "
            "machine time step or time_scale_factor or decrease the number "
            "of neurons per core")

    def _get_extra_provenance_words(self, provenance_data):
        """
        Gets the words of provenance data not used for system provenance.

        :param list(int) provenance_data:
        :rtype: list(int)
        """
        return provenance_data[self.N_SYSTEM_PROVENANCE_WORDS:]

    def parse_extra_provenance_items(self, label, names, provenance_data):
        # pylint: disable=unused-argument
        """
        Convert the remaining provenance words (those not in the standard set)
        into provenance items.

        Called by
        :py:meth:`~spinn_front_end_common.interface.provenance.ProvidesProvenanceDataFromMachineImpl.parse_extra_provenance_items.get_provenance_data_from_machine`

        :param str label:
            A descriptive label for the vertex (derived from label and placed
            position) to be used for provenance error reporting to the user.
        :param list(str) names:
            The base names describing the location of the machine vertex
            producing the provenance.
        :param list(int) provenance_data:
            The list of words of raw provenance data.
        :return: The interpreted provenance items.
        :rtype:
            iterable(~spinn_front_end_common.utilities.utility_objs.ProvenanceDataItem)
        """
        return []

    @overrides(
        AbstractProvidesProvenanceDataFromMachine.
        get_provenance_data_from_machine,
        extend_doc=False)
    def get_provenance_data_from_machine(self, transceiver, placement):
        """ Retrieve the provenance data.

        :param ~spinnman.transceiver.Transceiver transceiver:
            How to talk to the machine
        :param ~pacman.model.placements.Placement placement:
            Which vertex are we retrieving from, and where was it
        :rtype:
            ~collections.abc.Iterable(~spinn_front_end_common.utilities.utility_objs.ProvenanceDataItem)
        """
        provenance_data = self._read_provenance_data(transceiver, placement)
        label, names = self._get_provenance_placement_description(placement)
        yield from self.parse_system_provenance_items(
            label, names, provenance_data)
        yield from self.parse_extra_provenance_items(
            label, names, self._get_extra_provenance_words(provenance_data))
