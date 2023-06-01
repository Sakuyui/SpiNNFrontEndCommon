# Copyright (c) 2015 The University of Manchester
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import numpy
from typing import Optional
from dataclasses import dataclass
from spinn_utilities.overrides import overrides
from spinn_machine.tags import IPTag
from spinnman.messages.eieio import EIEIOPrefix
from pacman.model.partitioner_interfaces import LegacyPartitionerAPI
from pacman.model.graphs.application import ApplicationVertex
from pacman.model.routing_info.base_key_and_mask import BaseKeyAndMask
from spinn_front_end_common.utilities.constants import SDP_PORTS
from .reverse_ip_tag_multicast_source_machine_vertex import (
    ReverseIPTagMulticastSourceMachineVertex)
from spinn_front_end_common.utilities.exceptions import ConfigurationException


@dataclass
class _EIEIOParameters:
    """
    :param str board_address:
        The IP address of the board on which to place this vertex if receiving
        data, either buffered or live (by default, any board is chosen)
    :param int receive_port:
        The port on the board that will listen for incoming event packets
        (default is to disable this feature; set a value to enable it, or set
        the `reserve_reverse_ip_tag parameter` to True if a random port is to
        be used)
    :param int receive_sdp_port:
        The SDP port to listen on for incoming event packets (defaults to 1)
    :param int receive_tag:
        The IP tag to use for receiving live events (uses any by default)
    :param float receive_rate:
    :param int virtual_key:
        The base multicast key to send received events with (assigned
        automatically by default)
    :param int prefix:
        The prefix to "or" with generated multicast keys (default is no prefix)
    :param ~spinnman.messages.eieio.EIEIOPrefix prefix_type:
        Whether the prefix should apply to the upper or lower half of the
        multicast keys (default is upper half)
    :param bool check_keys:
        True if the keys of received events should be verified before sending
        (default False)
    :param str send_buffer_partition_id:
        The ID of the partition containing the edges down which the events are
        to be sent
    :param bool reserve_reverse_ip_tag:
        True if the source should set up a tag through which it can receive
        packets; if port is set to `None` this can be used to enable the
        reception of packets on a randomly assigned port, which can be read
        from the database
    :param str injection_partition:
        If not `None`, will enable injection and specify the partition to send
        injected keys with
    """
    receive_port: Optional[int] = None
    receive_sdp_port: int = SDP_PORTS.INPUT_BUFFERING_SDP_PORT.value
    receive_tag: Optional[IPTag] = None
    receive_rate: float = 10.0
    virtual_key: Optional[int] = None
    prefix: Optional[int] = None
    prefix_type: Optional[EIEIOPrefix] = None
    check_keys: bool = False
    send_buffer_partition_id: Optional[str] = None
    reserve_reverse_ip_tag: bool = False
    injection_partition_id: Optional[str] = None


class ReverseIpTagMultiCastSource(ApplicationVertex, LegacyPartitionerAPI):
    """
    A model which will allow events to be injected into a SpiNNaker
    machine and converted into multicast packets.
    """
    __slots__ = (
        "__n_atoms", "_eieio_params", "_is_recording",
        "__send_buffer_times",)

    def __init__(
            self, n_keys, label=None, max_atoms_per_core=sys.maxsize,

            # Live input parameters
            receive_port=None,
            receive_sdp_port=SDP_PORTS.INPUT_BUFFERING_SDP_PORT.value,
            receive_tag=None,
            receive_rate=10,

            # Key parameters
            virtual_key=None, prefix=None,
            prefix_type=None, check_keys=False,

            # Send buffer parameters
            send_buffer_times=None,
            send_buffer_partition_id=None,

            # Extra flag for input without a reserved port
            reserve_reverse_ip_tag=False,

            # Name of partition to inject keys with
            injection_partition_id=None,

            # splitter object
            splitter=None):
        """
        :param int n_keys:
            The number of keys to be sent via this multicast source
        :param str label: The label of this vertex
        :param int max_atoms_per_core:
        :param board_address: The IP address of the board on which to place
            this vertex if receiving data, either buffered or live (by
            default, any board is chosen)
        :type board_address: str or None
        :param receive_port: The port on the board that will listen for
            incoming event packets (default is to disable this feature; set a
            value to enable it)
        :type receive_port: int or None
        :param int receive_sdp_port:
            The SDP port to listen on for incoming event packets
            (defaults to 1)
        :param ~spinn_machine.tags.IPTag receive_tag:
            The IP tag to use for receiving live events
            (uses any by default)
        :param float receive_rate:
            The estimated rate of packets that will be sent by this source
        :param int virtual_key:
            The base multicast key to send received events with
            (assigned automatically by default)
        :param int prefix:
            The prefix to "or" with generated multicast keys
            (default is no prefix)
        :param ~spinnman.messages.eieio.EIEIOPrefix prefix_type:
            Whether the prefix should apply to the upper or lower half of the
            multicast keys (default is upper half)
        :param bool check_keys:
            True if the keys of received events should be verified before
            sending (default False)
        :param send_buffer_times: An array of arrays of times at which keys
            should be sent (one array for each key, default disabled)
        :type send_buffer_times:
            ~numpy.ndarray(~numpy.ndarray(numpy.int32)) or
            list(~numpy.ndarray(~numpy.int32)) or None
        :param send_buffer_partition_id: The ID of the partition containing
            the edges down which the events are to be sent
        :type send_buffer_partition_id: str or None
        :param bool reserve_reverse_ip_tag:
            Extra flag for input without a reserved port
        :param str injection_partition:
            If not `None`, will enable injection and specify the partition to
            send injected keys with
        :param splitter: the splitter object needed for this vertex
        :type splitter:
            ~pacman.model.partitioner_splitters.AbstractSplitterCommon or None
        """
        # pylint: disable=too-many-arguments
        super().__init__(label, max_atoms_per_core, splitter=splitter)

        # basic items
        self.__n_atoms = self.round_n_atoms(n_keys, "n_keys")

        # Store the parameters for EIEIO
        self._eieio_params = _EIEIOParameters(
            receive_port, receive_sdp_port, receive_tag, receive_rate,
            virtual_key, prefix, prefix_type, check_keys,
            send_buffer_partition_id, reserve_reverse_ip_tag,
            injection_partition_id)

        # Store the send buffering details
        self.__send_buffer_times = self._validate_send_buffer_times(
            send_buffer_times)

        # Store recording parameters
        self._is_recording = False

    def _validate_send_buffer_times(self, send_buffer_times):
        if send_buffer_times is None:
            return None
        if len(send_buffer_times) and hasattr(send_buffer_times[0], "__len__"):
            if len(send_buffer_times) != self.__n_atoms:
                raise ConfigurationException(
                    f"The array or arrays of times {send_buffer_times} does "
                    f"not have the expected length of {self.__n_atoms}")
            return numpy.array(send_buffer_times, dtype="object")
        return numpy.array(send_buffer_times)

    @property
    @overrides(ApplicationVertex.n_atoms)
    def n_atoms(self):
        return self.__n_atoms

    @overrides(LegacyPartitionerAPI.get_sdram_used_by_atoms)
    def get_sdram_used_by_atoms(self, vertex_slice):
        return ReverseIPTagMulticastSourceMachineVertex.get_sdram_usage(
            self._filtered_send_buffer_times(vertex_slice),
            self._is_recording, self._eieio_params.receive_rate,
            vertex_slice.n_atoms)

    @property
    def send_buffer_times(self):
        """
        When messages will be sent.

        :rtype: ~numpy.ndarray(~numpy.ndarray(numpy.int32)) or
            list(~numpy.ndarray(~numpy.int32)) or None
        """
        return self.__send_buffer_times

    @send_buffer_times.setter
    def send_buffer_times(self, send_buffer_times):
        self.__send_buffer_times = send_buffer_times
        for vertex in self.machine_vertices:
            send_buffer_times_to_set = self.__send_buffer_times
            if len(self.__send_buffer_times) > 0:
                if hasattr(self.__send_buffer_times[0], "__len__"):
                    vertex_slice = vertex.vertex_slice
                    send_buffer_times_to_set = self.__send_buffer_times[
                        vertex_slice.lo_atom:vertex_slice.hi_atom + 1]
            vertex.send_buffer_times = send_buffer_times_to_set

    def enable_recording(self, new_state=True):
        self._is_recording = new_state

    @overrides(LegacyPartitionerAPI.create_machine_vertex)
    def create_machine_vertex(self, vertex_slice, sdram, label=None):
        send_buffer_times = self._filtered_send_buffer_times(vertex_slice)
        machine_vertex = ReverseIPTagMulticastSourceMachineVertex(
            label=label, app_vertex=self, vertex_slice=vertex_slice,
            eieio_params=self._eieio_params,
            send_buffer_times=send_buffer_times)
        machine_vertex.enable_recording(self._is_recording)
        # Known issue with ReverseIPTagMulticastSourceMachineVertex
        if sdram:
            assert (sdram == machine_vertex.sdram_required)
        return machine_vertex

    def _filtered_send_buffer_times(self, vertex_slice):
        ids = vertex_slice.get_raster_ids()
        send_buffer_times = self.__send_buffer_times
        n_buffer_times = 0
        if send_buffer_times is not None:
            # If there is at least one array element, and that element is
            # itself an array
            if (len(send_buffer_times) and
                    hasattr(send_buffer_times[0], "__len__")):
                send_buffer_times = send_buffer_times[ids]
            # Check the buffer times are not empty
            for i in send_buffer_times:
                if hasattr(i, "__len__"):
                    n_buffer_times += len(i)
                else:
                    # assuming this must be a single integer
                    n_buffer_times += 1
        if n_buffer_times == 0:
            return None
        return send_buffer_times

    def __repr__(self):
        return self._label

    @overrides(ApplicationVertex.get_fixed_key_and_mask)
    def get_fixed_key_and_mask(self, partition_id):
        if self._eieio_params.virtual_key is None:
            return None
        mask = ReverseIPTagMulticastSourceMachineVertex.calculate_mask(
            min(self.n_atoms, self.get_max_atoms_per_core()))
        return BaseKeyAndMask(self._eieio_params.virtual_key, mask)
