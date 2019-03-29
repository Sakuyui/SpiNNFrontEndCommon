import struct
from enum import Enum
from six import add_metaclass
from spinn_utilities.abstract_base import AbstractBase, abstractproperty
from data_specification.utility_calls import get_region_base_address_offset
from .abstract_provides_provenance_data_from_machine import (
    AbstractProvidesProvenanceDataFromMachine)
from spinn_front_end_common.utilities.utility_objs import ProvenanceDataItem

_ONE_WORD = struct.Struct("<I")


@add_metaclass(AbstractBase)
class ProvidesProvenanceDataFromMachineImpl(
        AbstractProvidesProvenanceDataFromMachine):
    """ An implementation that gets provenance data from a region of ints on\
        the machine.
    """

    __slots__ = ()

    # entries for the provenance data generated by models using provides
    # provenance vertex
    PROVENANCE_DATA_ENTRIES = Enum(
        value="PROVENANCE_DATA_ENTRIES",
        names=[("TRANSMISSION_EVENT_OVERFLOW", 0),
               ("CALLBACK_QUEUE_OVERLOADED", 1),
               ("DMA_QUEUE_OVERLOADED", 2),
               ("TIMER_TIC_HAS_OVERRUN", 3),
               ("MAX_NUMBER_OF_TIMER_TIC_OVERRUN", 4)]
    )
    NUM_PROVENANCE_DATA_ENTRIES = len(PROVENANCE_DATA_ENTRIES)

    _TIMER_TICK_OVERRUN = "Times_the_timer_tic_over_ran"
    _MAX_TIMER_TICK_OVERRUN = "max_number_of_times_timer_tic_over_ran"
    _TIMES_DMA_QUEUE_OVERLOADED = "Times_the_dma_queue_was_overloaded"
    _TIMES_TRANSMISSION_SPIKES_OVERRAN = \
        "Times_the_transmission_of_spikes_overran"
    _TIMES_CALLBACK_QUEUE_OVERLOADED = \
        "Times_the_callback_queue_was_overloaded"

    @abstractproperty
    def _provenance_region_id(self):
        """
        :return: provenance_region_id
        """

    @abstractproperty
    def _n_additional_data_items(self):
        """
        :return: n_additional_data_items
        """

    def reserve_provenance_data_region(self, spec):
        spec.reserve_memory_region(
            self._provenance_region_id,
            self.get_provenance_data_size(self._n_additional_data_items),
            label="Provenance", empty=True)

    @staticmethod
    def get_provenance_data_size(n_additional_data_items):
        return (
            (ProvidesProvenanceDataFromMachineImpl.NUM_PROVENANCE_DATA_ENTRIES
             + n_additional_data_items) * 4)

    def _get_provenance_region_address(self, transceiver, placement):

        # Get the App Data for the core
        app_data_base_address = transceiver.get_cpu_information_from_core(
            placement.x, placement.y, placement.p).user[0]

        # Get the provenance region base address
        base_address_offset = get_region_base_address_offset(
            app_data_base_address, self._provenance_region_id)
        base_address = transceiver.read_memory(
            placement.x, placement.y, base_address_offset, 4)
        return _ONE_WORD.unpack(base_address)[0]

    def _read_provenance_data(self, transceiver, placement):
        provenance_address = self._get_provenance_region_address(
            transceiver, placement)
        data = transceiver.read_memory(
            placement.x, placement.y, provenance_address,
            self.get_provenance_data_size(self._n_additional_data_items))
        return struct.unpack_from("<{}I".format(
            self.NUM_PROVENANCE_DATA_ENTRIES + self._n_additional_data_items),
            data)

    @staticmethod
    def _get_placement_details(placement):
        label = placement.vertex.label
        x = placement.x
        y = placement.y
        p = placement.p
        names = ["{}_{}_{}_{}".format(x, y, p, label)]
        return label, x, y, p, names

    @staticmethod
    def _add_name(names, name):
        new_names = list(names)
        new_names.append(name)
        return new_names

    @staticmethod
    def _add_names(names, extra_names):
        new_names = list(names)
        new_names.extend(extra_names)
        return new_names

    def _read_basic_provenance_items(self, provenance_data, placement):
        transmission_event_overflow = provenance_data[
            self.PROVENANCE_DATA_ENTRIES.TRANSMISSION_EVENT_OVERFLOW.value]
        callback_queue_overloaded = provenance_data[
            self.PROVENANCE_DATA_ENTRIES.CALLBACK_QUEUE_OVERLOADED.value]
        dma_queue_overloaded = provenance_data[
            self.PROVENANCE_DATA_ENTRIES.DMA_QUEUE_OVERLOADED.value]
        number_of_times_timer_tic_over_ran = provenance_data[
            self.PROVENANCE_DATA_ENTRIES.TIMER_TIC_HAS_OVERRUN.value]
        max_number_of_times_timer_tic_over_ran = provenance_data[
            self.PROVENANCE_DATA_ENTRIES.MAX_NUMBER_OF_TIMER_TIC_OVERRUN.value]

        # create provenance data items for returning
        label, x, y, p, names = self._get_placement_details(placement)
        data_items = list()
        data_items.append(ProvenanceDataItem(
            self._add_name(names, self._TIMES_TRANSMISSION_SPIKES_OVERRAN),
            transmission_event_overflow,
            report=transmission_event_overflow != 0,
            message=(
                "The transmission buffer for {} on {}, {}, {} was blocked "
                "on {} occasions. This is often a sign that the system is "
                "experiencing back pressure from the communication fabric. "
                "Please either: "
                "1. spread the load over more cores, "
                "2. reduce your peak transmission load,"
                "3. adjust your mapping algorithm.".format(
                    label, x, y, p, transmission_event_overflow))))

        data_items.append(ProvenanceDataItem(
            self._add_name(names, self._TIMES_CALLBACK_QUEUE_OVERLOADED),
            callback_queue_overloaded,
            report=callback_queue_overloaded != 0,
            message=(
                "The callback queue for {} on {}, {}, {} overloaded on {} "
                "occasions. This is often a sign that the system is running "
                "too quickly for the number of neurons per core.  Please "
                "increase the machine time step or time_scale_factor or "
                "decrease the number of neurons per core.".format(
                    label, x, y, p, callback_queue_overloaded))))

        data_items.append(ProvenanceDataItem(
            self._add_name(names, self._TIMES_DMA_QUEUE_OVERLOADED),
            dma_queue_overloaded,
            report=dma_queue_overloaded != 0,
            message=(
                "The DMA queue for {} on {}, {}, {} overloaded on {} "
                "occasions. This is often a sign that the system is running "
                "too quickly for the number of neurons per core.  Please "
                "increase the machine time step or time_scale_factor or "
                "decrease the number of neurons per core.".format(
                    label, x, y, p, dma_queue_overloaded))))

        data_items.append(ProvenanceDataItem(
            self._add_name(names, self._TIMER_TICK_OVERRUN),
            number_of_times_timer_tic_over_ran,
            report=number_of_times_timer_tic_over_ran != 0,
            message=(
                "A Timer tick callback was still executing when the next "
                "timer tick callback was fired off for {} on {}, {}, {}, {} "
                "times. This is a sign of the system being overloaded and "
                "therefore the results are likely incorrect.  Please increase "
                "the machine time step or time_scale_factor or decrease the "
                "number of neurons per core".format(
                    label, x, y, p, number_of_times_timer_tic_over_ran))))

        data_items.append(ProvenanceDataItem(
            self._add_name(names, self._MAX_TIMER_TICK_OVERRUN),
            max_number_of_times_timer_tic_over_ran,
            report=max_number_of_times_timer_tic_over_ran > 4,
            message=(
                "The timer for {} on {}, {}, {} fell behind by up to {} "
                "ticks. This is a sign of the system being overloaded and "
                "therefore the results are likely incorrect. Please increase "
                "the machine time step or time_scale_factor or decrease the "
                "number of neurons per core".format(
                    label, x, y, p, max_number_of_times_timer_tic_over_ran))))

        return data_items

    def _get_remaining_provenance_data_items(self, provenance_data):
        return provenance_data[self.NUM_PROVENANCE_DATA_ENTRIES:]

    def get_provenance_data_from_machine(self, transceiver, placement):
        provenance_data = self._read_provenance_data(
            transceiver, placement)
        return self._read_basic_provenance_items(provenance_data, placement)
