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

import logging
import os
import time
from spinn_utilities.progress_bar import ProgressBar
from spinn_utilities.log import FormatAdapter
from spinn_machine import Router
from pacman import exceptions
from pacman.model.graphs import AbstractSpiNNakerLink, AbstractFPGA
from pacman.utilities.algorithm_utilities.routing_algorithm_utilities import (
    get_app_partitions)
from pacman.utilities.algorithm_utilities.routes_format import format_route
from spinn_front_end_common.utilities.globals_variables import (
    report_default_directory)
from .router_summary import RouterSummary

logger = FormatAdapter(logging.getLogger(__name__))

_LINK_LABELS = {0: 'E', 1: 'NE', 2: 'N', 3: 'W', 4: 'SW', 5: 'S'}

_C_ROUTING_TABLE_DIR = "compressed_routing_tables_generated"
_COMPARED_FILENAME = "comparison_of_compressed_uncompressed_routing_tables.rpt"
_COMPRESSED_ROUTING_SUMMARY_FILENAME = "compressed_routing_summary.rpt"
_PARTITIONING_FILENAME = "partitioned_by_vertex.rpt"
_PLACEMENT_VTX_GRAPH_FILENAME = "placement_by_vertex_using_graph.rpt"
_PLACEMENT_VTX_SIMPLE_FILENAME = "placement_by_vertex_without_graph.rpt"
_PLACEMENT_CORE_GRAPH_FILENAME = "placement_by_core_using_graph.rpt"
_PLACEMENT_CORE_SIMPLE_FILENAME = "placement_by_core_without_graph.rpt"
_ROUTING_FILENAME = "edge_routing_info.rpt"
_ROUTING_SUMMARY_FILENAME = "routing_summary.rpt"
_ROUTING_TABLE_DIR = "routing_tables_generated"
_SDRAM_FILENAME = "chip_sdram_usage_by_core.rpt"
_TAGS_FILENAME = "tags.rpt"
_VIRTKEY_FILENAME = "virtual_key_space_information_report.rpt"

_LOWER_16_BITS = 0xFFFF


def tag_allocator_report(tag_infos):
    """ Reports the tags that are being used by the tool chain for this\
        simulation

    :param Tags tag_infos: the tags container generated by the tools.
    :rtype: None
    """

    file_name = os.path.join(report_default_directory(), _TAGS_FILENAME)
    try:
        with open(file_name, "w") as f:
            progress = ProgressBar(
                len(list(tag_infos.ip_tags)) +
                len(list(tag_infos.reverse_ip_tags)),
                "Reporting Tags")
            for ip_tag in progress.over(tag_infos.ip_tags, False):
                f.write(str(ip_tag) + "\n")
            for reverse_ip_tag in progress.over(tag_infos.reverse_ip_tags):
                f.write(str(reverse_ip_tag) + "\n")
    except IOError:
        logger.error("Generate_tag_report: Can't open file {} for "
                     "writing.", file_name)


def placer_reports_with_application_graph(
        hostname, graph, placements, machine):
    """ Reports that can be produced from placement given a application\
        graph's existence

    :param str hostname: The machine's hostname to which the placer worked on.
    :param ApplicationGraph graph:
        The application graph to which placements were built.
    :param Placements placements: the placements objects built by the placer.
    :param ~spinn_machine.Machine machine: the python machine object.
    :rtype: None
    """
    placement_report_with_application_graph_by_vertex(
        hostname, graph, placements)
    placement_report_with_application_graph_by_core(
        hostname, placements, machine)


def router_summary_report(routing_tables,  hostname, machine):
    """ Generates a text file of routing summaries

    :param MulticastRoutingTables routing_tables:
        The original routing tables.
    :param str hostname: The machine's hostname to which the placer worked on.
    :param ~spinn_machine.Machine machine: The python machine object.
    :rtype: RouterSummary
    """
    file_name = os.path.join(
        report_default_directory(), _ROUTING_SUMMARY_FILENAME)
    progress = ProgressBar(machine.n_chips,
                           "Generating Routing summary report")
    return _do_router_summary_report(
        file_name, progress, routing_tables,  hostname, machine)


def router_compressed_summary_report(routing_tables, hostname, machine):
    """ Generates a text file of routing summaries

    :param MulticastRoutingTables routing_tables:
        The in-operation routing tables.
    :param str hostname: The machine's hostname to which the placer worked on.
    :param ~spinn_machine.Machine machine: The python machine object.
    :rtype: RouterSummary
    """
    file_name = os.path.join(
        report_default_directory(), _COMPRESSED_ROUTING_SUMMARY_FILENAME)
    progress = ProgressBar(machine.n_chips,
                           "Generating Routing summary report")
    return _do_router_summary_report(
        file_name, progress, routing_tables, hostname, machine)


def _do_router_summary_report(
        file_name, progress, routing_tables, hostname, machine):
    """
    :param str file_name:
    :param ~spinn_utilities.progress_bar.Progress progress:
    :param MulticastRoutingTables routing_tables:
    :param str hostname:
    :param ~spinn_machine.Machine machine:
    :return: RouterSummary
    """
    time_date_string = time.strftime("%c")
    convert = Router.convert_routing_table_entry_to_spinnaker_route
    try:
        with open(file_name, "w") as f:
            f.write("        Routing Summary Report\n")
            f.write("        ======================\n\n")
            f.write("Generated: {} for target machine '{}'\n\n".format(
                time_date_string, hostname))

            total_entries = 0
            max_entries = 0
            max_none_defaultable = 0
            max_link_only = 0
            max_spinnaker_routes = 0
            for (x, y) in progress.over(machine.chip_coordinates):
                table = routing_tables.get_routing_table_for_chip(x, y)
                if table is not None:
                    entries = table.number_of_entries
                    defaultable = table.number_of_defaultable_entries
                    link_only = 0
                    spinnaker_routes = set()
                    for entry in table.multicast_routing_entries:
                        if not entry.processor_ids:
                            link_only += 1
                        spinnaker_routes.add(convert(entry))
                    f.write("Chip {}:{} has {} entries of which {} are "
                            "defaultable and {} link only with {} unique "
                            "spinnaker routes\n"
                            "".format(x, y, entries, defaultable, link_only,
                                      len(spinnaker_routes)))
                    total_entries += entries
                    max_entries = max(max_entries, entries)
                    max_none_defaultable = max(
                        max_none_defaultable, entries - defaultable)
                    max_link_only = max(max_link_only, link_only)
                    max_spinnaker_routes = max(
                        max_spinnaker_routes, len(spinnaker_routes))

            f.write("\n Total entries {}, max per chip {} max none "
                    "defaultable {} max link only {} "
                    "max unique spinnaker routes {}\n\n".format(
                        total_entries, max_entries, max_none_defaultable,
                        max_link_only, max_spinnaker_routes))
            return RouterSummary(
                total_entries, max_entries, max_none_defaultable,
                max_link_only, max_spinnaker_routes)

    except IOError:
        logger.exception("Generate_routing summary reports: "
                         "Can't open file {} for writing.", file_name)


def router_report_from_paths(
        routing_tables, routing_infos, hostname,
        graph, placements, machine):
    """ Generates a text file of routing paths

    :param MulticastRoutingTables routing_tables: The original routing tables.
    :param str hostname: The machine's hostname to which the placer worked on.
    :param RoutingInfo routing_infos:
    :param ApplicationGraph graph:
    :param Placements placements:
    :param ~spinn_machine.Machine machine: The python machine object.
    :rtype: None
    """
    file_name = os.path.join(report_default_directory(), _ROUTING_FILENAME)
    time_date_string = time.strftime("%c")
    partitions = get_app_partitions(graph)
    try:
        with open(file_name, "w") as f:
            progress = ProgressBar(len(partitions),
                                   "Generating Routing path report")

            f.write("        Edge Routing Report\n")
            f.write("        ===================\n\n")
            f.write("Generated: {} for target machine '{}'\n\n".format(
                time_date_string, hostname))

            for partition in progress.over(partitions):
                _write_one_router_partition_report(
                    f, partition, machine, placements, routing_infos,
                    routing_tables)
    except IOError:
        logger.exception("Generate_routing_reports: Can't open file {} for "
                         "writing.", file_name)


def _write_one_router_partition_report(f, partition, machine, placements,
                                       routing_infos, routing_tables):
    """
    :param ~io.FileIO f:
    :param AApplicationEdgePartition partition:
    :param ~spinn_machine.Machine machine:
    :param Placements placements:
    :param RoutingInfo routing_infos:
    :param MulticastRoutingTables routing_tables:
    """
    source = partition.pre_vertex
    outgoing = source.splitter.get_out_going_vertices(partition.identifier)
    f.write(f"Source Application vertex {source}, partition"
            f" {partition.identifier}\n")

    for edge in partition.edges:
        for m_vertex in outgoing:
            source_placement = placements.get_placement_of_vertex(m_vertex)
            key_and_mask = routing_infos.get_routing_info_from_pre_vertex(
                m_vertex, partition.identifier)
            path, number_of_entries = _search_route(
                source_placement, key_and_mask, routing_tables, machine)
            f.write("    Edge '{}', from vertex: '{}' to vertex: '{}'".format(
                edge.label, edge.pre_vertex.label, edge.post_vertex.label))
            f.write("{}\n".format(path))
            f.write("        Route length: {}\n".format(number_of_entries))

            # End one entry:
            f.write("\n")


def partitioner_report(hostname, graph):
    """ Generate report on the placement of vertices onto cores.

    :param str hostname: the machine's hostname to which the placer worked on
    :param ApplicationGraph graph: the app graph

    """

    # Cycle through all vertices, and for each cycle through its vertices.
    # For each vertex, describe its core mapping.
    file_name = os.path.join(
        report_default_directory(), _PARTITIONING_FILENAME)
    time_date_string = time.strftime("%c")
    try:
        with open(file_name, "w") as f:
            progress = ProgressBar(graph.n_vertices,
                                   "Generating partitioner report")

            f.write("        Partitioning Information by Vertex\n")
            f.write("        ===============================\n\n")
            f.write("Generated: {} for target machine '{}'\n\n".format(
                time_date_string, hostname))

            for vertex in progress.over(graph.vertices):
                _write_one_vertex_partition(f, vertex)
    except IOError:
        logger.exception("Generate_placement_reports: Can't open file {} for"
                         " writing.", file_name)


def _write_one_vertex_partition(f, vertex):
    """
    :param ~io.FileIO f:
    :param ApplicationVertex vertex:
    """
    vertex_name = vertex.label
    vertex_model = vertex.__class__.__name__
    num_atoms = vertex.n_atoms
    f.write("**** Vertex: '{}'\n".format(vertex_name))
    f.write("Model: {}\n".format(vertex_model))
    f.write("Pop size: {}\n".format(num_atoms))
    f.write("Machine Vertices: \n")

    # Sort by slice and then by label
    machine_vertices = sorted(vertex.machine_vertices,
                              key=lambda x: x.label)
    machine_vertices = sorted(machine_vertices,
                              key=lambda x: x.vertex_slice.lo_atom)
    for sv in machine_vertices:
        f.write("  Slice {}:{} ({} atoms) \n".format(
            sv.vertex_slice.lo_atom, sv.vertex_slice.hi_atom,
            sv.vertex_slice.n_atoms))
    f.write("\n")


def placement_report_with_application_graph_by_vertex(
        hostname, graph, placements):
    """ Generate report on the placement of vertices onto cores by vertex.

    :param str hostname: the machine's hostname to which the placer worked on
    :param ApplicationGraph graph: the graph to which placements were built
    :param Placements placements: the placements objects built by the placer.
    """

    # Cycle through all vertices, and for each cycle through its vertices.
    # For each vertex, describe its core mapping.
    file_name = os.path.join(
        report_default_directory(), _PLACEMENT_VTX_GRAPH_FILENAME)
    time_date_string = time.strftime("%c")
    try:
        with open(file_name, "w") as f:
            progress = ProgressBar(graph.n_vertices,
                                   "Generating placement report")

            f.write("        Placement Information by Vertex\n")
            f.write("        ===============================\n\n")
            f.write("Generated: {} for target machine '{}'\n\n".format(
                time_date_string, hostname))

            for vertex in progress.over(graph.vertices):
                _write_one_vertex_application_placement(f, vertex, placements)
    except IOError:
        logger.exception("Generate_placement_reports: Can't open file {} for"
                         " writing.", file_name)


def _write_one_vertex_application_placement(f, vertex, placements):
    """
    :param ~io.FileIO f:
    :param ApplicationVertex vertex:
    :param Placements placements:
    """
    vertex_name = vertex.label
    vertex_model = vertex.__class__.__name__
    num_atoms = vertex.n_atoms
    f.write("**** Vertex: '{}'\n".format(vertex_name))
    f.write("Model: {}\n".format(vertex_model))
    f.write("Pop size: {}\n".format(num_atoms))
    f.write("Machine Vertices: \n")

    # Sort by slice and then by label
    machine_vertices = sorted(vertex.machine_vertices,
                              key=lambda vert: vert.label)
    machine_vertices = sorted(machine_vertices,
                              key=lambda vert: vert.vertex_slice.lo_atom)
    for sv in machine_vertices:
        lo_atom = sv.vertex_slice.lo_atom
        hi_atom = sv.vertex_slice.hi_atom
        num_atoms = sv.vertex_slice.n_atoms
        cur_placement = placements.get_placement_of_vertex(sv)
        x, y, p = cur_placement.x, cur_placement.y, cur_placement.p
        f.write("  Slice {}:{} ({} atoms) on core ({}, {}, {}) \n"
                .format(lo_atom, hi_atom, num_atoms, x, y, p))
    f.write("\n")


def placement_report_with_application_graph_by_core(
        hostname, placements, machine):
    """ Generate report on the placement of vertices onto cores by core.

    :param str hostname: the machine's hostname to which the placer worked on
    :param ~spinn_machine.Machine machine: the SpiNNaker machine object
    :param Placements placements: the placements objects built by the placer.
    """

    # File 2: Placement by core.
    # Cycle through all chips and by all cores within each chip.
    # For each core, display what is held on it.
    file_name = os.path.join(
        report_default_directory(), _PLACEMENT_CORE_GRAPH_FILENAME)
    time_date_string = time.strftime("%c")
    try:
        with open(file_name, "w") as f:
            progress = ProgressBar(machine.n_chips,
                                   "Generating placement by core report")

            f.write("        Placement Information by Core\n")
            f.write("        =============================\n\n")
            f.write("Generated: {} for target machine '{}'\n\n".format(
                time_date_string, hostname))

            for chip in progress.over(machine.chips):
                _write_one_chip_application_placement(f, chip, placements)
    except IOError:
        logger.exception("Generate_placement_reports: Can't open file {} for "
                         "writing.", file_name)


def _write_one_chip_application_placement(f, chip, placements):
    """
    :param ~io.FileIO f:
    :param ~spinn_machine.Chip chip:
    :param Placements placements:
    """
    written_header = False
    total_sdram = None
    for processor in chip.processors:
        if placements.is_processor_occupied(
                chip.x, chip.y, processor.processor_id):
            if not written_header:
                f.write("**** Chip: ({}, {})\n".format(chip.x, chip.y))
                f.write("Application cores: {}\n".format(
                    len(list(chip.processors))))
                written_header = True
            pro_id = processor.processor_id
            vertex = placements.get_vertex_on_processor(
                chip.x, chip.y, processor.processor_id)
            app_vertex = vertex.app_vertex
            if app_vertex is not None:
                vertex_label = app_vertex.label
                vertex_model = app_vertex.__class__.__name__
                vertex_atoms = app_vertex.n_atoms
                lo_atom = vertex.vertex_slice.lo_atom
                hi_atom = vertex.vertex_slice.hi_atom
                num_atoms = vertex.vertex_slice.n_atoms
                f.write("  Processor {}: Vertex: '{}', pop size: {}\n".format(
                    pro_id, vertex_label, vertex_atoms))
                f.write("              Slice on this core: {}:{} ({} atoms)\n"
                        .format(lo_atom, hi_atom, num_atoms))
                f.write("              Model: {}\n".format(vertex_model))
            else:
                f.write("  Processor {}: System Vertex: '{}'\n".format(
                    pro_id, vertex.label))
                f.write("              Model: {}\n".format(
                    vertex.__class__.__name__))

            sdram = vertex.resources_required.sdram
            f.write("              SDRAM required: {}; {} per timestep\n\n"
                    .format(sdram.fixed, sdram.per_timestep))
            if total_sdram is None:
                total_sdram = sdram
            else:
                total_sdram += sdram

    if total_sdram is not None:
        f.write("Total SDRAM on chip ({} available): {}; {} per-timestep\n\n"
                .format(chip.sdram.size, total_sdram.fixed,
                        total_sdram.per_timestep))


def placement_report_without_application_graph_by_core(
        hostname, placements, machine):
    """ Generate report on the placement of vertices onto cores by core.

    :param str hostname: the machine's hostname to which the placer worked on
    :param ~spinn_machine.Machine machine: the SpiNNaker machine object
    :param Placements placements: the placements objects built by the placer.
    """

    # File 2: Placement by core.
    # Cycle through all chips and by all cores within each chip.
    # For each core, display what is held on it.
    file_name = os.path.join(
        report_default_directory(), _PLACEMENT_CORE_SIMPLE_FILENAME)
    time_date_string = time.strftime("%c")
    try:
        with open(file_name, "w") as f:
            progress = ProgressBar(machine.chips,
                                   "Generating placement by core report")

            f.write("        Placement Information by Core\n")
            f.write("        =============================\n\n")
            f.write("Generated: {}".format(time_date_string))
            f.write(" for target machine '{}'".format(hostname))
            f.write("\n\n")

            for chip in progress.over(machine.chips):
                _write_one_chip_machine_placement(f, chip, placements)
    except IOError:
        logger.exception("Generate_placement_reports: Can't open file {} for "
                         "writing.", file_name)


def _write_one_chip_machine_placement(f, c, placements):
    """
    :param ~io.FileIO f:
    :param ~spinn_machine.Chip c:
    :param Placements placements:
    """
    written_header = False
    for pr in c.processors:
        if placements.is_processor_occupied(c.x, c.y, pr.processor_id):
            if not written_header:
                f.write("**** Chip: ({}, {})\n".format(c.x, c.y))
                f.write("Application cores: {}\n".format(
                    len(list(c.processors))))
                written_header = True
            vertex = placements.get_vertex_on_processor(
                c.x, c.y, pr.processor_id)
            f.write("  Processor {}: Vertex: '{}' \n".format(
                pr.processor_id, vertex.label))
            f.write("              Model: {}\n\n".format(
                vertex.__class__.__name__))
            f.write("\n")


def sdram_usage_report_per_chip(
        hostname, placements, machine, plan_n_timesteps, data_n_timesteps):
    """ Reports the SDRAM used per chip

    :param str hostname: the machine's hostname to which the placer worked on
    :param Placements placements: the placements objects built by the placer.
    :param ~spinn_machine.Machine machine: the python machine object
    :param int plan_n_timesteps:
        The number of timesteps for which placer reserved space.
    :param int data_n_timesteps:
        The number of timesteps for which data can be saved on the machine.
    :rtype: None
    """

    file_name = os.path.join(report_default_directory(), _SDRAM_FILENAME)
    time_date_string = time.strftime("%c")
    progress = ProgressBar((len(placements) * 2 + machine.n_chips * 2),
                           "Generating SDRAM usage report")
    try:
        with open(file_name, "w") as f:
            f.write("        Memory Usage by Core\n")
            f.write("        ====================\n\n")
            f.write("Generated: {} for target machine '{}'\n\n".format(
                time_date_string, hostname))
            f.write("Planned by partitioner\n")
            f.write("----------------------\n")
            _sdram_usage_report_per_chip_with_timesteps(
                f, placements, machine, plan_n_timesteps, progress, False,
                False)
            f.write("\nActual space reserved on the machine\n")
            f.write("----------------------\n")
            _sdram_usage_report_per_chip_with_timesteps(
                f, placements, machine, data_n_timesteps, progress, True, True)
    except IOError:
        logger.exception("Generate_placement_reports: Can't open file {} for "
                         "writing.", file_name)


def _sdram_usage_report_per_chip_with_timesteps(
        f, placements, machine, timesteps, progress, end_progress, details):
    """
    :param ~io.FileIO f:
    :param Placements placements:
    :param ~spinn_machine.Machine machine:
    :param int timesteps:
    :param ~spinn_utilities.progress_bar.ProgressBar progress:
    :param bool end_progress:
    :param bool details: If True will get costs printed by regions
    """
    f.write("Based on {} timesteps\n\n".format(timesteps))
    used_sdram_by_chip = dict()
    placements = sorted(placements.placements,
                        key=lambda x: x.vertex.label)
    for placement in progress.over(placements, False):
        vertex_sdram = placement.vertex.resources_required.sdram
        core_sdram = vertex_sdram.get_total_sdram(timesteps)
        x, y, p = placement.x, placement.y, placement.p
        if details:
            vertex_sdram.report(
                timesteps=timesteps,
                preamble="core ({},{},{})".format(x, y, p), target=f)
        else:
            f.write(
                "SDRAM reqs for core ({},{},{}) is {} KB ({} bytes) for {}\n"
                "".format(x, y, p, int(core_sdram / 1024.0), core_sdram,
                          placement))
        key = (x, y)
        if key not in used_sdram_by_chip:
            used_sdram_by_chip[key] = core_sdram
        else:
            used_sdram_by_chip[key] += core_sdram
    for chip in progress.over(machine.chips, end_progress):
        try:
            used_sdram = used_sdram_by_chip[chip.x, chip.y]
            if used_sdram:
                f.write(
                    "**** Chip: ({}, {}) has total memory usage of"
                    " {} KB ({} bytes) out of a max of "
                    "{} KB ({} bytes)\n\n".format(
                        chip.x, chip.y,
                        int(used_sdram / 1024.0), used_sdram,
                        int(chip.sdram.size / 1024.0), chip.sdram.size))
        except KeyError:
            # Do Nothing
            pass


def routing_info_report(app_graph, routing_infos):
    """ Generates a report which says which keys is being allocated to each\
        vertex

    :param ApplicationGraph app_graph:
    :param RoutingInfo routing_infos:
    """
    file_name = os.path.join(report_default_directory(), _VIRTKEY_FILENAME)
    try:
        with open(file_name, "w") as f:
            progress = ProgressBar(app_graph.n_outgoing_edge_partitions,
                                   "Generating Routing info report")
            for part in progress.over(app_graph.outgoing_edge_partitions):
                _write_vertex_virtual_keys(f, part, routing_infos)
            progress.end()
    except IOError:
        logger.exception("generate virtual key space information report: "
                         "Can't open file {} for writing.", file_name)


def _write_vertex_virtual_keys(f, part, routing_infos):
    """
    :param ~io.FileIO f:
    :param MachineVertex vertex:
    :param RoutingInfo routing_infos:
    :param ~spinn_utilities.progress_bar.ProgressBar progress:
    """
    rinfo = routing_infos.get_routing_info_from_pre_vertex(
        part.pre_vertex, part.identifier)
    # Might be None if the partition has no outgoing vertices e.g. a Poisson
    # source replaced by SDRAM comms
    if rinfo is not None:
        f.write("Vertex: {}\n".format(part.pre_vertex))
        f.write("    Partition: {}, Routing Info: {}\n".format(
            part.identifier, rinfo.keys_and_masks))
        for m_vertex in part.pre_vertex.splitter.get_out_going_vertices(
                part.identifier):
            r_info = routing_infos.get_routing_info_from_pre_vertex(
                m_vertex, part.identifier)
            if r_info is not None:
                f.write("    Machine Vertex: {}, Routing Info: {}\n".format(
                    m_vertex, r_info.keys_and_masks))


def router_report_from_router_tables(routing_tables):
    """
    :param MulticastRoutingTables routing_tables:
        the original routing tables
    :rtype: None
    """

    top_level_folder = os.path.join(
        report_default_directory(), _ROUTING_TABLE_DIR)
    if not os.path.exists(top_level_folder):
        os.mkdir(top_level_folder)
    progress = ProgressBar(routing_tables.routing_tables,
                           "Generating Router table report")
    for routing_table in progress.over(routing_tables.routing_tables):
        if routing_table.number_of_entries:
            generate_routing_table(routing_table, top_level_folder)


def router_report_from_compressed_router_tables(routing_tables):
    """
    :param MulticastRoutingTables routing_tables:
        the compressed routing tables
    :rtype: None
    """

    top_level_folder = os.path.join(
        report_default_directory(), _C_ROUTING_TABLE_DIR)
    if not os.path.exists(top_level_folder):
        os.mkdir(top_level_folder)
    progress = ProgressBar(routing_tables.routing_tables,
                           "Generating compressed router table report")
    for routing_table in progress.over(routing_tables.routing_tables):
        if routing_table.number_of_entries:
            generate_routing_table(routing_table, top_level_folder)


def generate_routing_table(routing_table, top_level_folder):
    """
    :param AbstractMulticastRoutingTable routing_table:
    :param str top_level_folder:
    """
    file_name = "routing_table_{}_{}.rpt".format(
        routing_table.x, routing_table.y)
    file_path = os.path.join(top_level_folder, file_name)
    try:
        with open(file_path, "w") as f:
            f.write("Router contains {} entries\n".format(
                routing_table.number_of_entries))

            f.write("{: <5s} {: <10s} {: <10s} {: <10s} {: <7s} {}\n".format(
                "Index", "Key", "Mask", "Route", "Default", "[Cores][Links]"))
            f.write(
                "{:-<5s} {:-<10s} {:-<10s} {:-<10s} {:-<7s} {:-<14s}\n".format(
                    "", "", "", "", "", ""))
            line_format = "{: >5d} {}\n"

            entry_count = 0
            n_defaultable = 0
            for entry in routing_table.multicast_routing_entries:
                index = entry_count & _LOWER_16_BITS
                entry_str = line_format.format(index, format_route(entry))
                entry_count += 1
                if entry.defaultable:
                    n_defaultable += 1
                f.write(entry_str)
            f.write("{} Defaultable entries\n".format(n_defaultable))
    except IOError:
        logger.exception("Generate_placement_reports: Can't open file"
                         " {} for writing.", file_path)


def _compression_ratio(uncompressed, compressed):
    """ Get the compression ratio, as a percentage.

    :param int uncompressed:
    :param int compressed:
    :rtype: float
    """
    if uncompressed == 0:
        return 0
    return (uncompressed - compressed) / float(uncompressed) * 100


def generate_comparison_router_report(
        routing_tables, compressed_routing_tables):
    """ Make a report on comparison of the compressed and uncompressed \
        routing tables

    :param MulticastRoutingTables routing_tables:
        the original routing tables
    :param MulticastRoutingTables compressed_routing_tables:
        the compressed routing tables
    :rtype: None
    """
    file_name = os.path.join(report_default_directory(), _COMPARED_FILENAME)
    try:
        with open(file_name, "w") as f:
            progress = ProgressBar(
                routing_tables.routing_tables,
                "Generating comparison of router table report")
            total_uncompressed = 0
            total_compressed = 0
            max_compressed = 0
            uncompressed_for_max = 0
            for table in progress.over(routing_tables.routing_tables):
                x = table.x
                y = table.y
                compressed_table = compressed_routing_tables.\
                    get_routing_table_for_chip(x, y)
                n_entries_uncompressed = table.number_of_entries
                total_uncompressed += n_entries_uncompressed
                n_entries_compressed = compressed_table.number_of_entries
                total_compressed += n_entries_compressed
                f.write(
                    "Uncompressed table at {}:{} has {} entries "
                    "whereas compressed table has {} entries. "
                    "This is a decrease of {}%\n".format(
                        x, y, n_entries_uncompressed, n_entries_compressed,
                        _compression_ratio(
                            n_entries_uncompressed, n_entries_compressed)))
                if max_compressed < n_entries_compressed:
                    max_compressed = n_entries_compressed
                    uncompressed_for_max = n_entries_uncompressed
            if total_uncompressed > 0:
                f.write(
                    "\nTotal has {} entries whereas compressed tables "
                    "have {} entries. This is an average decrease of {}%\n"
                    "".format(
                        total_uncompressed, total_compressed,
                        _compression_ratio(
                            total_uncompressed, total_compressed)))
                f.write(
                    "Worst case has {} entries whereas compressed tables "
                    "have {} entries. This is a decrease of {}%\n".format(
                        uncompressed_for_max, max_compressed,
                        _compression_ratio(
                            uncompressed_for_max, max_compressed)))
    except IOError:
        logger.exception("Generate_router_comparison_reports: Can't open file"
                         " {} for writing.", file_name)


def _search_route(source_placement, key_and_mask, routing_tables, machine):
    """
    :param Placement source_placement:
    :param Placement dest_placement:
    :param BaseKeyAndMask key_and_mask:
    :param ~spinn_machine.MulticastRoutingTables routing_tables:
    :param ~spinn_machine.Machine machine:
    :rtype: tuple(str, int)
    """
    # Create text for starting point
    source_vertex = source_placement.vertex
    text = ""
    if isinstance(source_vertex, AbstractSpiNNakerLink):
        text = "        Virtual SpiNNaker Link on {}:{}:{} -> ".format(
            source_placement.x, source_placement.y, source_placement.p)
        slink = machine.get_spinnaker_link_with_id(
            source_vertex.spinnaker_link_id)
        x = slink.connected_chip_x
        y = slink.connected_chip_y
    elif isinstance(source_vertex, AbstractFPGA):
        text = "        Virtual FPGA Link on {}:{}:{} -> ".format(
            source_placement.x, source_placement.y, source_placement.p)
        flink = machine.get_fpga_link_with_id(
            source_vertex.fpga_id, source_vertex.fpga_link_id)
        x = flink.connected_chip_x
        y = flink.connected_chip_y
    else:
        x = source_placement.x
        y = source_placement.y
        text = "        {}:{}:{} -> ".format(
            source_placement.x, source_placement.y, source_placement.p)

    # Start the search
    number_of_entries = 0

    # If the destination is virtual, replace with the real destination chip
    text += _recursive_trace_to_destinations(
        x, y, key_and_mask, machine, routing_tables, number_of_entries,
        pre_space="        ")
    return text


# Locates the destinations of a route
def _recursive_trace_to_destinations(
        chip_x, chip_y, key_and_mask, machine, routing_tables, pre_space):
    """ Recursively search though routing tables till no more entries are\
        registered with this key

    :param int chip_x:
    :param int chip_y
    :param BaseKeyAndMask key_and_mask:
    :param ~spinn_machine.Machine machine:
    :param ~spinn_machine.MulticastRoutingTables routing_tables:
    :rtype: str
    """

    chip = machine.get_chip_at(chip_x, chip_y)

    if chip.virtual:
        return "-> Virtual Chip {}, {}".format(chip_x, chip_y)

    text = "-> Chip {}:{}".format(chip_x, chip_y)
    table = routing_tables.get_routing_table_for_chip(chip_x, chip_y)
    entry = _locate_routing_entry(table, key_and_mask.key)
    new_pre_space = pre_space + (" " * len(text))
    first = True
    for link_id in entry.link_ids:
        if not first:
            text += "\n{}".format(pre_space)
        link = chip.router.get_link(link_id)
        text += "-> {}".format(link)
        text += _recursive_trace_to_destinations(
            link.destination_x, link.destination_y, key_and_mask, machine,
            routing_tables, new_pre_space)
        first = False

    return text


def _locate_routing_entry(current_router, key):
    """ Locate the entry from the router based off the edge

    :param ~spinn_machine.MulticastRoutingTable current_router:
        the current router being used in the trace
    :param int key: the key being used by the source placement
    :return: the routing table entry
    :rtype: ~spinn_machine.MulticastRoutingEntry
    :raise PacmanRoutingException:
        when there is no entry located on this router.
    """
    for entry in current_router.multicast_routing_entries:
        if entry.mask & key == entry.routing_entry_key:
            return entry
    raise exceptions.PacmanRoutingException("no entry located")
