# Copyright (c) 2017-2023 The University of Manchester
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from spinn_utilities.config_holder import (
    add_default_cfg, clear_cfg_files)
from spinnman.config_setup import add_spinnman_cfg
from pacman.config_setup import add_pacman_cfg
from data_specification.config_setup import add_data_specification_cfg
from spinn_front_end_common.data.fec_data_writer import FecDataWriter

BASE_CONFIG_FILE = "spinnaker.cfg"


def unittest_setup():
    """
    Does all the steps that may be required before a unittest

    Resets the configs so only the local default configs are included.

    Unsets any previous simulators and tempdirs

    .. note::
        This file should only be called from spinn_front_end_common tests

    """
    clear_cfg_files(True)
    add_spinnaker_cfg()
    FecDataWriter.mock()


def add_spinnaker_cfg():
    """
    Add the local cfg and all dependent cfg files.
    """
    add_pacman_cfg()  # This add its dependencies too
    add_spinnman_cfg()  # double adds of dependencies ignored
    add_data_specification_cfg()  # double adds of dependencies ignored
    add_default_cfg(os.path.join(os.path.dirname(__file__), BASE_CONFIG_FILE))
