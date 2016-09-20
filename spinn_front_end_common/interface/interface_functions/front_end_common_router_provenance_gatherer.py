
# pacman imports
from spinn_machine.utilities.progress_bar import ProgressBar

# front end common imports
from spinn_front_end_common.utilities.utility_objs.provenance_data_item \
    import ProvenanceDataItem
from spinn_front_end_common.utilities import exceptions


class FrontEndCommonRouterProvenanceGatherer(object):
    """
    FrontEndCommonRouterProvenanceGatherer: gathers diagnostics from the
    routers.
    """

    __slots__ = [
        # int for how many packets were sent
        '_total_sent_packets',

        # how many new packets were received
        '_total_new_packets',

        # how many dropped packets
        '_total_dropped_packets',

        # total missed dropped packets
        '_total_missed_dropped_packets',

        # total lost dropped packets
        '_total_lost_dropped_packets'

        # total
    ]

    def __call__(
            self, transceiver, machine, router_tables, has_ran,
            provenance_data_objects=None):
        """
        :param transceiver: the SpiNNMan interface object
        :param machine: the python representation of the spinnaker machine
        :param router_tables: the router tables that have been generated
        :param has_ran: token that states that the simulation has ran
        """

        if not has_ran:
            raise exceptions.ConfigurationException(
                "This function has been called before the simulation has ran."
                " This is deemed an error, please rectify and try again")

        self._total_sent_packets = 0
        self._total_new_packets = 0
        self._total_dropped_packets = 0
        self._total_missed_dropped_packets = 0
        self._total_lost_dropped_packets = 0

        if provenance_data_objects is not None:
            prov_items = provenance_data_objects
        else:
            prov_items = list()

        prov_items.extend(self._write_router_provenance_data(
            router_tables, machine, transceiver))

        prov_items.append(ProvenanceDataItem(
            ["router_provenance", "total_sent_packets"],
            self._total_sent_packets))
        prov_items.append(ProvenanceDataItem(
            ["router_provenance", "total_created_packets"],
            self._total_new_packets))
        prov_items.append(ProvenanceDataItem(
            ["router_provenance", "total_dropped_packets"],
            self._total_dropped_packets))
        prov_items.append(ProvenanceDataItem(
            ["router_provenance", "total_missed_dropped_packets"],
            self._total_missed_dropped_packets))
        prov_items.append(ProvenanceDataItem(
            ["router_provenance", "total_lost_dropped_packets"],
            self._total_lost_dropped_packets))

        return prov_items

    def _write_router_provenance_data(self, router_tables, machine, txrx):
        """ Writes the provenance data of the router diagnostics

        :param router_tables: the routing tables generated by pacman
        :param machine: the spinnMachine object
        :param txrx: the transceiver object
        :return: None
        """
        progress = ProgressBar(machine.n_chips, "Getting Router Provenance")

        # acquire diagnostic data
        items = list()
        seen_chips = set()

        for router_table in sorted(
                router_tables.routing_tables,
                key=lambda table: (table.x, table.y)):
            x = router_table.x
            y = router_table.y
            if not machine.get_chip_at(x, y).virtual:
                router_diagnostic = txrx.get_router_diagnostics(x, y)
                seen_chips.add((x, y))
                reinjector_status = txrx.get_reinjection_status(x, y)
                items.extend(self._write_router_diagnostics(
                    x, y, router_diagnostic, reinjector_status, True))
                self._add_totals(router_diagnostic, reinjector_status)
            progress.update()

        for chip in sorted(machine.chips, key=lambda c: (c.x, c.y)):
            if not chip.virtual and (chip.x, chip.y) not in seen_chips:
                try:
                    diagnostic = txrx.get_router_diagnostics(chip.x, chip.y)

                    if (diagnostic.n_dropped_multicast_packets != 0 or
                            diagnostic.n_local_multicast_packets != 0 or
                            diagnostic.n_external_multicast_packets != 0):

                        reinjector_status = txrx.get_reinjection_status(
                            chip.x, chip.y)
                        items.extend(self._write_router_diagnostics(
                            chip.x, chip.y, diagnostic, reinjector_status,
                            False))
                        self._add_totals(diagnostic, reinjector_status)
                        progress.update()
                except Exception:
                    # There could be issues with unused chips - don't worry!
                    pass
        progress.end()
        return items

    def _add_totals(self, router_diagnostic, reinjector_status):
        self._total_sent_packets += (
            router_diagnostic.n_local_multicast_packets +
            router_diagnostic.n_external_multicast_packets)
        self._total_new_packets += router_diagnostic.n_local_multicast_packets
        self._total_dropped_packets += (
            router_diagnostic.n_dropped_multicast_packets)
        if reinjector_status is not None:
            self._total_missed_dropped_packets += (
                reinjector_status.n_missed_dropped_packets)
            self._total_lost_dropped_packets += (
                reinjector_status.n_dropped_packet_overflows)
        else:
            self._total_lost_dropped_packets += (
                router_diagnostic.n_dropped_multicast_packets)

    @staticmethod
    def _add_name(names, name):
        new_names = list(names)
        new_names.append(name)
        return new_names

    def _write_router_diagnostics(
            self, x, y, router_diagnostic, reinjector_status, expected):
        """ Stores router diagnostics as a set of provenance data items

        :param x: x coord of the router in question
        :param y: y coord of the router in question
        :param router_diagnostic: the router diagnostic object
        :param reinjector_status: the data gained from the reinjector
        :return: None
        """
        names = list()
        names.append("router_provenance")
        if expected:
            names.append("expected_routers")
        else:
            names.append("unexpected_routers")
        names.append("router_at_chip_{}_{}".format(x, y))

        items = list()

        items.append(ProvenanceDataItem(
            self._add_name(names, "Local_Multicast_Packets"),
            str(router_diagnostic.n_local_multicast_packets)))
        items.append(ProvenanceDataItem(
            self._add_name(names, "External_Multicast_Packets"),
            str(router_diagnostic.n_external_multicast_packets)))
        items.append(ProvenanceDataItem(
            self._add_name(names, "Dropped_Multicast_Packets"),
            str(router_diagnostic.n_dropped_multicast_packets),
            report=(
                router_diagnostic.n_dropped_multicast_packets > 0 and
                reinjector_status is None),
            message=(
                "The router on {}, {} has dropped {} multicast route packets. "
                "Try increasing the machine_time_step and/or the time scale "
                "factor or reducing the number of atoms per core."
                .format(x, y, router_diagnostic.n_dropped_multicast_packets))))
        items.append(ProvenanceDataItem(
            self._add_name(
                names, "Dropped_Multicast_Packets_via_local_transmission"),
            str(router_diagnostic.user_3),
            report=(router_diagnostic.user_3 > 0),
            message=(
                "The router on {}, {} has dropped {} multicast packets that had"
                " been transmitted by local cores. This occurs where the "
                "router has no entry associated with the multi-cast key. "
                "Try investigating the keys allocated to the vertices and "
                "whats placed in the router table entries.".format(
                    x, y, router_diagnostic.user_3))))
        items.append(ProvenanceDataItem(
            self._add_name(names, "Local_P2P_Packets"),
            str(router_diagnostic.n_local_peer_to_peer_packets)))
        items.append(ProvenanceDataItem(
            self._add_name(names, "External_P2P_Packets"),
            str(router_diagnostic.n_external_peer_to_peer_packets)))
        items.append(ProvenanceDataItem(
            self._add_name(names, "Dropped_P2P_Packets"),
            str(router_diagnostic.n_dropped_peer_to_peer_packets)))
        items.append(ProvenanceDataItem(
            self._add_name(names, "Local_NN_Packets"),
            str(router_diagnostic.n_local_nearest_neighbour_packets)))
        items.append(ProvenanceDataItem(
            self._add_name(names, "External_NN_Packets"),
            str(router_diagnostic.n_external_nearest_neighbour_packets)))
        items.append(ProvenanceDataItem(
            self._add_name(names, "Dropped_NN_Packets"),
            str(router_diagnostic.n_dropped_nearest_neighbour_packets)))
        items.append(ProvenanceDataItem(
            self._add_name(names, "Local_FR_Packets"),
            str(router_diagnostic.n_local_fixed_route_packets)))
        items.append(ProvenanceDataItem(
            self._add_name(names, "External_FR_Packets"),
            str(router_diagnostic.n_external_fixed_route_packets)))
        items.append(ProvenanceDataItem(
            self._add_name(names, "Dropped_FR_Packets"),
            str(router_diagnostic.n_dropped_fixed_route_packets)))
        if reinjector_status is not None:
            items.append(ProvenanceDataItem(
                self._add_name(names, "Received_For_Reinjection"),
                reinjector_status.n_dropped_packets))
            items.append(ProvenanceDataItem(
                self._add_name(names, "Missed_For_Reinjection"),
                reinjector_status.n_missed_dropped_packets,
                report=reinjector_status.n_missed_dropped_packets > 0,
                message=(
                    "The reinjector on {}, {} has missed {} packets.".format(
                        x, y, reinjector_status.n_missed_dropped_packets))))
            items.append(ProvenanceDataItem(
                self._add_name(names, "Reinjection_Overflows"),
                reinjector_status.n_dropped_packet_overflows,
                report=reinjector_status.n_dropped_packet_overflows > 0,
                message=(
                    "The reinjector on {}, {} has dropped {} packets.".format(
                        x, y, reinjector_status.n_dropped_packet_overflows))))
            items.append(ProvenanceDataItem(
                self._add_name(names, "Reinjected"),
                reinjector_status.n_reinjected_packets))

        return items
