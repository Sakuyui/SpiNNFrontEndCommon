from pacman.model.graphs.machine import MachineGraph, MachineEdge
from pacman.model.placements import Placements, Placement
from pacman.model.routing_tables import (
    MulticastRoutingTables, MulticastRoutingTable)
from pacman.operations.fixed_route_router.fixed_route_router import (
    RoutingMachineVertex)
from pacman.operations.router_algorithms import BasicDijkstraRouting
from spinn_machine import (Router, VirtualMachine, MulticastRoutingEntry)
from spinn_utilities.progress_bar import ProgressBar
from spinn_front_end_common.utilities.helpful_functions import (
    calculate_board_level_chip_id, calculate_machine_level_chip_id)


class DataInMulticastRoutingGenerator(object):
    """ Generates routing table entries used by the data in processes with the\
    extra monitor cores.
    """

    N_KEYS_PER_PARTITION_ID = 4
    KEY_START_VALUE = 4
    FAKE_ETHERNET_CHIP_X = 0
    FAKE_ETHERNET_CHIP_Y = 0
    ROUTING_MASK = 0xFFFFFFFC

    def __call__(self, machine, extra_monitor_cores, placements,
                 board_version):
        # create progress bar
        progress = ProgressBar(
            machine.ethernet_connected_chips,
            "Generating routing tables for data in system processes")

        # create routing table holder
        routing_tables = MulticastRoutingTables()
        key_to_destination_map = dict()

        for ethernet_chip in progress.over(
                machine.ethernet_connected_chips):
            fake_graph, fake_placements, fake_machine, key_to_dest_map = \
                self._create_fake_network(
                    ethernet_chip, machine, extra_monitor_cores,
                    placements, board_version)

            # update dict for key mapping
            key_to_destination_map.update(key_to_dest_map)

            # do routing
            routing_tables_by_partition = self.do_routing(
                fake_graph=fake_graph, fake_placements=fake_placements,
                fake_machine=fake_machine)
            self._generate_routing_tables(
                routing_tables, routing_tables_by_partition, ethernet_chip,
                machine)
        return routing_tables, key_to_destination_map

    def _generate_routing_tables(
            self, routing_tables, routing_tables_by_partition, ethernet_chip,
            machine):
        """ from the routing. use the partition id as key, and build mc\
        routing tables.

        :param routing_tables: the routing tables to store routing tables in
        :param routing_tables_by_partition: the routing output
        :param ethernet_chip: the ethernet chip being used
        :param machine: the SpiNNMachine instance
        :return: dict of chip x and chip yto key to get there
        :rtype: dict
        """
        for fake_chip_x, fake_chip_y in \
                routing_tables_by_partition.get_routers():
            partitions_in_table = routing_tables_by_partition.\
                get_entries_for_router(fake_chip_x, fake_chip_y)

            real_chip_x, real_chip_y = calculate_machine_level_chip_id(
                fake_chip_x, fake_chip_y, ethernet_chip.x, ethernet_chip.y,
                machine)

            multicast_routing_table = MulticastRoutingTable(
                real_chip_x, real_chip_y)

            # build routing table entries
            for partition in partitions_in_table:
                entry = partitions_in_table[partition]
                multicast_routing_table.add_multicast_routing_entry(
                    MulticastRoutingEntry(
                        routing_entry_key=partition.identifier,
                        mask=DataInMulticastRoutingGenerator.ROUTING_MASK,
                        processor_ids=entry.out_going_processors,
                        link_ids=entry.out_going_links,
                        defaultable=entry.defaultable))

            # add routing table to pile
            routing_tables.add_routing_table(multicast_routing_table)

    def _create_fake_network(
            self, ethernet_connected_chip, machine, extra_monitor_cores,
            placements, board_version):
        """ generate the fake network for each board
        :param ethernet_connected_chip: the ethernet chip to fire from
        :param machine: the real SpiNNMachine instance
        :param extra_monitor_cores: the extra monitor cores
        :param placements: the real placements instance
        :param board_version: the board version
        :return: fake graph, fake placements, fake machine.
        """

        fake_graph = MachineGraph(label="routing fake_graph")
        fake_placements = Placements()
        destination_to_partition_identifier_map = dict()

        # build fake setup for the routing
        eth_x = ethernet_connected_chip.x
        eth_y = ethernet_connected_chip.y
        down_links = set()
        fake_machine = machine

        for (chip_x, chip_y) in machine.get_chips_on_board(
                ethernet_connected_chip):

            # add destination vertex
            vertex = RoutingMachineVertex()
            fake_graph.add_vertex(vertex)

            # adjust for wrap around's
            fake_x, fake_y = calculate_board_level_chip_id(
                chip_x, chip_y, eth_x, eth_y, machine)

            # locate correct chips extra monitor placement
            placement = placements.get_placement_of_vertex(
                extra_monitor_cores[chip_x, chip_y])

            # build fake placement
            fake_placements.add_placement(Placement(
                x=fake_x, y=fake_y, p=placement.p, vertex=vertex))

            # remove links to ensure it maps on just chips of this board.
            down_links.update({
                (fake_x, fake_y, link)
                for link in range(Router.MAX_LINKS_PER_ROUTER)
                if not machine.is_link_at(chip_x, chip_y, link)})

            # Create a fake machine consisting of only the one board that
            # the routes should go over
            valid_48_boards = list()
            valid_48_boards.extend(machine.BOARD_VERSION_FOR_48_CHIPS)
            valid_48_boards.append(None)

            if (board_version in valid_48_boards and
                    (machine.max_chip_x > machine.MAX_CHIP_X_ID_ON_ONE_BOARD or
                     machine.max_chip_y > machine.MAX_CHIP_Y_ID_ON_ONE_BOARD)):
                down_chips = {
                    (x, y) for x, y in zip(
                        range(machine.SIZE_X_OF_ONE_BOARD),
                        range(machine.SIZE_Y_OF_ONE_BOARD))
                    if not machine.is_chip_at(
                        (x + eth_x) % (machine.max_chip_x + 1),
                        (y + eth_y) % (machine.max_chip_y + 1))}

                # build a fake machine which is just one board but with the
                # missing bits of the real board
                fake_machine = VirtualMachine(
                    machine.SIZE_X_OF_ONE_BOARD, machine.SIZE_Y_OF_ONE_BOARD,
                    False, down_chips=down_chips, down_links=down_links)

        # build source
        destination_vertices = fake_graph.vertices
        vertex_source = RoutingMachineVertex()
        fake_graph.add_vertex(vertex_source)

        free_processor = 0
        while ((free_processor < machine.MAX_CORES_PER_CHIP) and
                fake_placements.is_processor_occupied(
                self.FAKE_ETHERNET_CHIP_X, y=self.FAKE_ETHERNET_CHIP_Y,
                p=free_processor)):
            free_processor += 1

        fake_placements.add_placement(Placement(
            x=self.FAKE_ETHERNET_CHIP_X, y=self.FAKE_ETHERNET_CHIP_Y,
            p=free_processor, vertex=vertex_source))

        # deal with edges, each one being in a unique partition id, to
        # allow unique routing to each chip.
        counter = self.KEY_START_VALUE
        for vertex in destination_vertices:
            if vertex != vertex_source:
                fake_graph.add_edge(
                    MachineEdge(pre_vertex=vertex_source, post_vertex=vertex),
                    counter)
                fake_placement = fake_placements.get_placement_of_vertex(
                    vertex)

                # adjust to real chip ids
                real_x, real_y = calculate_machine_level_chip_id(
                    fake_placement.x, fake_placement.y,
                    ethernet_connected_chip.x, ethernet_connected_chip.y,
                    machine)
                destination_to_partition_identifier_map[real_x, real_y] = \
                    counter
                counter += self.N_KEYS_PER_PARTITION_ID

        return (fake_graph, fake_placements, fake_machine,
                destination_to_partition_identifier_map)

    @staticmethod
    def do_routing(fake_placements, fake_graph, fake_machine):
        """ executes the routing

        :param fake_placements: the fake placements
        :param fake_graph: the fake graph
        :param fake_machine: the fake machine
        :return: the routes
        """
        # route as if using multicast
        router = BasicDijkstraRouting()
        return router(
            placements=fake_placements, machine=fake_machine,
            machine_graph=fake_graph, use_progress_bar=False)
