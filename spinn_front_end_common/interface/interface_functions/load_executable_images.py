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
from spinnman.messages.scp.enums import Signal
from spinnman.model import ExecutableTargets
from spinnman.model.enums import CPUState
from spinn_front_end_common.utilities.helpful_functions import (
    flood_fill_binary_to_spinnaker)
from spinn_front_end_common.utilities.utility_objs import ExecutableType
from spinnman.exceptions import SpiNNManCoresNotInStateException
from spinn_front_end_common.utilities.emergency_recovery import emergency_recover_states_from_failure


def load_app_images(executable_targets, app_id, transceiver):
    """ Go through the executable targets and load each binary to everywhere\
         and then send a start request to the cores that actually use it.

    :param ~spinnman.model.ExecutableTargets executable_targets:
    :param int app_id:
    :param ~spinnman.transceiver.Transceiver transceiver:
    """
    __load_images(executable_targets, app_id, transceiver,
                  lambda ty: ty is not ExecutableType.SYSTEM,
                  "Loading executables onto the machine")


def load_sys_images(executable_targets, app_id, transceiver):
    """ Go through the executable targets and load each binary to everywhere\
         and then send a start request to the cores that actually use it.

    :param ~spinnman.model.ExecutableTargets executable_targets:
    :param int app_id:
    :param ~spinnman.transceiver.Transceiver transceiver:
    """
    __load_images(executable_targets, app_id, transceiver,
                  lambda ty: ty is ExecutableType.SYSTEM,
                  "Loading system executables onto the machine")
    try:
        transceiver.wait_for_cores_to_be_in_state(
            executable_targets.all_core_subsets, app_id, [CPUState.RUNNING],
            timeout=10)
    except SpiNNManCoresNotInStateException as e:
        emergency_recover_states_from_failure(
            transceiver, app_id, executable_targets)
        raise e


def __load_images(executable_targets, app_id, txrx, filt, label):
    """
    :param ~.ExecutableTargets executable_targets:
    :param int app_id:
    :param ~.Transceiver txrx:
    :param callable(ExecutableType,bool) filt:
    :param str label
    """
    # Compute what work is to be done here
    binaries, cores = filter_targets(executable_targets, filt)

    # ISSUE: Loading order may be non-constant on older Python
    progress = ProgressBar(cores.total_processors + 1, label)
    for binary in binaries:
        progress.update(flood_fill_binary_to_spinnaker(
            executable_targets, binary, txrx, app_id))

    __start_simulation(cores, txrx, app_id)
    progress.update()
    progress.end()


def filter_targets(targets, filt):
    """
    :param ~spinnman.model.ExecutableTargets executable_targets:
    :param callable(ExecutableType,bool) filt:
    :rtype: tuple(list(str), ExecutableTargets)
    """
    binaries = []
    cores = ExecutableTargets()
    for exe_type in targets.executable_types_in_binary_set():
        if filt(exe_type):
            for aplx in targets.get_binaries_of_executable_type(exe_type):
                binaries.append(aplx)
                cores.add_subsets(
                    aplx, targets.get_cores_for_binary(aplx), exe_type)
    return binaries, cores


def __start_simulation(executable_targets, txrx, app_id):
    """
    :param ~.ExecutableTargets executable_targets:
    :param ~.Transceiver txrx:
    :param int app_id:
    """
    txrx.wait_for_cores_to_be_in_state(
        executable_targets.all_core_subsets, app_id, [CPUState.READY])
    txrx.send_signal(app_id, Signal.START)
