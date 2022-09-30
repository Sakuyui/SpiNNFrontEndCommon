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
import numpy
from spinn_utilities.progress_bar import ProgressBar
from spinn_machine import SDRAM
from data_specification import DataSpecificationExecutor
from data_specification.constants import MAX_MEM_REGIONS
from spinn_front_end_common.utilities.helpful_functions import (
    get_region_base_address_offset)
from spinn_front_end_common.utilities.utility_calls import (
    get_data_spec_and_file_writer_filename)
from spinn_front_end_common.abstract_models import (
    AbstractRewritesDataSpecification)
from spinn_front_end_common.data import FecDataView
from spinn_front_end_common.utilities.helpful_functions import (
    generate_unique_folder_name)
from spinn_front_end_common.utilities.constants import BYTES_PER_WORD


def reload_dsg_regions():
    """ Reloads DSG regions where needed
    """
    # build file paths for reloaded stuff
    data_dir = get_reload_data_dir()

    progress = ProgressBar(
        FecDataView.get_n_placements(), "Reloading data")
    for placement in progress.over(FecDataView.iterate_placemements()):
        # Generate the data spec for the placement if needed
        regenerate_data_spec(placement, data_dir)

    # App data directory can be removed as should be empty
    os.rmdir(data_dir)


def get_reload_data_dir():
    """ Get a path in which reloaded data files can be written

    :rtype: str
    """
    run_dir_path = FecDataView.get_run_dir_path()
    data_dir = generate_unique_folder_name(
        run_dir_path, "reloaded_data_regions", "")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    return data_dir


def regenerate_data_spec(placement, data_dir):
    """ Regenerate a data specification for a placement

    :param ~.Placement placement: The placement to regenerate
    :param str data_dir: A place to use to write data to
    :return: Whether the data was regenerated or not
    :rtype: bool
    """
    vertex = placement.vertex

    # If the vertex doesn't regenerate, skip
    if not isinstance(vertex, AbstractRewritesDataSpecification):
        return False

    # If the vertex doesn't require regeneration, skip
    if not vertex.reload_required():
        return False

    txrx = FecDataView.get_transceiver()

    # build the writers for the reports and data
    spec_file, spec = get_data_spec_and_file_writer_filename(
        placement.x, placement.y, placement.p, data_dir)

    # Execute the regeneration
    vertex.regenerate_data_specification(spec, placement)

    # execute the spec
    with open(spec_file, "rb") as spec_reader:
        data_spec_executor = DataSpecificationExecutor(
            spec_reader, SDRAM.max_sdram_found)
        data_spec_executor.execute()
    try:
        os.remove(spec_file)
    except Exception:  # pylint: disable=broad-except
        # Ignore the deletion of files as non-critical
        pass

    # Read the region table for the placement
    regions_base_address = txrx.get_cpu_information_from_core(
        placement.x, placement.y, placement.p).user[0]
    start_region = get_region_base_address_offset(regions_base_address, 0)
    table_size = get_region_base_address_offset(
        regions_base_address, MAX_MEM_REGIONS) - start_region
    ptr_table = numpy.frombuffer(txrx.read_memory(
            placement.x, placement.y, start_region, table_size),
        dtype=DataSpecificationExecutor.TABLE_TYPE)
    ptr_table = _fix_ptr_table_sizes(ptr_table)

    # Get the data spec executor pointer table; note that this will not
    # have the right pointers since not all regions will be regenerated
    # but the checksum and size will be updated there
    ds_ptr_table = data_spec_executor.get_pointer_table(0)
    ds_ptr_table_bytes = ds_ptr_table.view("uint8")

    # Get the offset of the checksum and the checksum + size to write
    chk_off = DataSpecificationExecutor.TABLE_TYPE.fields['checksum'][1]
    chk_size = DataSpecificationExecutor.TABLE_TYPE.itemsize - chk_off

    # Write the regions to the machine
    for i, region in enumerate(data_spec_executor.dsef.mem_regions):
        if region is not None and not region.unfilled:
            # Verify that the region hasn't grown bigger than it was
            new_size = ds_ptr_table[i]["n_words"]
            old_size = ptr_table[i]["n_words"]
            if old_size != -1 and new_size > old_size:
                raise Exception(
                    f"Region {i} of {vertex} has grown from {old_size} bytes "
                    f"to {new_size} bytes and will overwrite the next region!")
            txrx.write_memory(
                placement.x, placement.y, ptr_table[i]["pointer"],
                region.region_data[:region.max_write_pointer])
            # Update the checksum and size of the region
            reg = get_region_base_address_offset(regions_base_address, i)
            byte_offset = (reg - start_region) + chk_off
            addr = reg + chk_off
            txrx.write_memory(
                placement.x, placement.y, addr,
                ds_ptr_table_bytes[byte_offset:], chk_size)
    vertex.set_reload_required(False)
    return True


def _fix_ptr_table_sizes(ptr_table):
    """ Go through the pointer table and fix sizes where they have been set to
        0 to avoid checksum checks
    """
    # Fill in the size of regions which have no size
    fixed_ptr_table = numpy.zeros(
        MAX_MEM_REGIONS, dtype=DataSpecificationExecutor.TABLE_TYPE)
    fixed_ptr_table[:] = ptr_table[:]
    last_no_size_region = None
    for i in range(0, MAX_MEM_REGIONS):

        # If this region is a valid region
        if ptr_table[i]["pointer"] != 0:

            # If there is a previous region with no size, use this region
            # pointer to find the size of the last one
            if last_no_size_region is not None:
                fixed_ptr_table[last_no_size_region]["n_words"] = (
                    ptr_table[i]["pointer"] -
                    ptr_table[last_no_size_region]["pointer"]) / BYTES_PER_WORD
                last_no_size_region = None

            # If this region has no size, make it the next to find the size of
            if ptr_table[i]["n_words"] == 0:
                last_no_size_region = i

    # We can get here and have the last region have no size; this is hard
    # to fix since we don't know where the data for the next region is!
    if last_no_size_region is not None:
        fixed_ptr_table[last_no_size_region]["n_words"] = -1
    return fixed_ptr_table
