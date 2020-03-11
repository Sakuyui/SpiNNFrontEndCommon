/*
 * Copyright (c) 2019-2020 The University of Manchester
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#ifndef __MESSAGE_SENDING_H__
#define __MESSAGE_SENDING_H__

#include "constants.h"
#include "../common/sdp_formats.h"

//! how many tables the uncompressed router table entries is
#define N_UNCOMPRESSED_TABLE 1

//! \brief sends the sdp message. assumes all params have already been set
//! \param[in] my_msg: sdp message to send
void message_sending_send_sdp_message(sdp_msg_pure_data* my_msg){
    uint32_t attempt = 0;
    log_debug("sending message");
    while (!spin1_send_sdp_msg((sdp_msg_t *) my_msg, _SDP_TIMEOUT)) {
        attempt += 1;
        log_debug("failed to send. trying again");
        if (attempt >= 30) {
            rt_error(RTE_SWERR);
            terminate(EXIT_FAIL);
        }
    }
    log_debug("sent message");
}

//! \brief stores the addresses for freeing when response code is sent
//! \param[in] n_rt_addresses: how many bit field addresses there are
//! \param[in] comp_core_index: the compressor core
//! \param[in] compressed_address: the addresses for the compressed routing
//! table
//! \param[in] mid_point: the point in the bitfields to work from
//! \param[in] comp_cores_bf_tables: the map of compressor core and the sdram
//!  addresses for its routing tables to compress.
//! \param[in] bit_field_routing_tables:  the tables generated by the bitfields
//! \return bool stating if stored or not
static inline bool store_sdram_addresses_for_compression(
        int n_rt_addresses, uint32_t comp_core_index,
        table_t *compressed_address, uint32_t mid_point,
        comp_core_store_t* comp_cores_bf_tables,
        table_t** bit_field_routing_tables){

    //free previous if there is any
    if (comp_cores_bf_tables[comp_core_index].elements != NULL) {
        bool success = helpful_functions_free_sdram_from_compression_attempt(
            comp_core_index, comp_cores_bf_tables);
        if (!success) {
            log_error("failed to free compressor core elements.");
            return false;
        }
        FREE(comp_cores_bf_tables[comp_core_index].elements);
    }

    // allocate memory for the elements
    comp_cores_bf_tables[comp_core_index].elements =
        MALLOC(n_rt_addresses * sizeof(table_t**));
    if (comp_cores_bf_tables[comp_core_index].elements == NULL) {
        log_error("cannot allocate memory for sdram tracker of addresses");
        return false;
    }

    // store the elements. note need to copy over, as this is a central malloc
    // space for the routing tables.
    comp_cores_bf_tables[comp_core_index].n_elements = n_rt_addresses;
    comp_cores_bf_tables[comp_core_index].n_bit_fields = mid_point;
    comp_cores_bf_tables[comp_core_index].compressed_table = compressed_address;
    for (int rt_index = 0; rt_index < n_rt_addresses; rt_index++) {
        comp_cores_bf_tables[comp_core_index].elements[rt_index] =
            bit_field_routing_tables[rt_index];
    }
    return true;
}


//! \brief update the mc message to point at right direction
//! \param[in] comp_core_index: the compressor core id.
//! \param[in] my_msg: sdp message
//! \param[in] compressor_cores: list of compressor core ids.
static inline void update_mc_message(
        int comp_core_index, sdp_msg_pure_data* my_msg, int* compressor_cores) {
    log_debug("chip id = %d", spin1_get_chip_id());
    my_msg->srce_addr = spin1_get_chip_id();
    my_msg->dest_addr = spin1_get_chip_id();
    my_msg->flags = REPLY_NOT_EXPECTED;
    log_debug("core id =  %d", spin1_get_id() & 0x1F);
    my_msg->srce_port = (RANDOM_PORT << PORT_SHIFT) | spin1_get_core_id();
    log_debug("compressor core = %d", compressor_cores[comp_core_index]);
    my_msg->dest_port =
        (RANDOM_PORT << PORT_SHIFT) | compressor_cores[comp_core_index];
}

//! \brief sets up the packet to fly to the compressor core
//! \param[in]
//! \param[in] my_msg: sdp message to send
//! \param[in] usable_sdram_regions: sdram for fake heap for compressor
static void set_up_packet(
        comp_core_store_t* data_store, sdp_msg_pure_data* my_msg) {

    // create cast
    start_sdp_packet_t *data = (start_sdp_packet_t*) &my_msg->data;

    // fill in
    data->command_code = START_DATA_STREAM;
    data->fake_heap_data = stolen_sdram_heap;
    data->table_data = data_store;

    my_msg->length = (LENGTH_OF_SDP_HEADER + sizeof(start_sdp_packet_t));

    log_debug(
        "message contains command code %d, fake heap data address %x "
        "table data address %x",
        data->command_code, data->fake_heap_data, data->table_data);
    log_debug("message length = %d", my_msg->length);
}

//! \brief selects a compression core's index that's not doing anything yet
//! \param[in] midpoint: the midpoint this compressor is going to explore
//! \param[in] n_compression_cores: the number of compression cores
//! \param[in] comp_core_mid_point: the mid point for this attempt
//! \param[in/out] n_available_compression_cores: the number of available
//! compressor cores to attempt attempts with.
//! \return the compressor core index for this attempt.
static int select_compressor_core_index(
        int midpoint, int n_compression_cores, int* comp_core_mid_point,
        int *n_available_compression_cores){

    for (int comp_core_index = 0; comp_core_index < n_compression_cores;
            comp_core_index++) {
        if (comp_core_mid_point[comp_core_index] == DOING_NOWT) {
            comp_core_mid_point[comp_core_index] = midpoint;
            *n_available_compression_cores -= 1;
            return comp_core_index;
        }
    }

    log_error("cant find a core to allocate to you");
    terminate(EXIT_FAIL);
    return 0;
}


//! \brief sends a SDP message to a compressor core to do compression with
//!  a number of bitfields
//! \param[in] n_rt_addresses: how many addresses the bitfields merged into
//! \param[in] mid_point: the mid point in the binary search
//! \param[in] comp_cores_bf_tables: struct that holds meta data like the
//! routing table addresses for each compressor core attempt.
//! \param[in] bit_field_routing_tables: the list of routing tables which
//! were generated by the set of bitfields.
//! \param[in] my_msg: sdp message to send
//! \param[in] compressor_cores: the list of compressor core ids
//! \param[in] n_compressor_cores: the number of compressor cores total
//! \param[in] comp_core_mid_point: the mid points being tested
//! \param[in] n_available_compression_cores: the number of compressor cores
//! available right now.
//! \return bool saying if we succeeded or not.
static bool message_sending_set_off_bit_field_compression(
        int n_rt_addresses, uint32_t mid_point,
        comp_core_store_t* comp_cores_bf_tables,
        table_t **bit_field_routing_tables, sdp_msg_pure_data* my_msg,
        int* compressor_cores, int n_compressor_cores, int* comp_core_mid_point,
        int* n_available_compression_cores){

    // select compressor core to execute this
    int comp_core_index = select_compressor_core_index(
        mid_point, n_compressor_cores, comp_core_mid_point,
        n_available_compression_cores);

    int n_entries = 0;
    for (int rt_index = 0; rt_index < n_rt_addresses; rt_index++){
        n_entries += bit_field_routing_tables[rt_index]->size;
    }
    log_info(
        "using core %d for %d rts with %d entries",
        compressor_cores[comp_core_index], n_rt_addresses, n_entries);

    // allocate space for the compressed routing entries if required
    table_t *compressed_address =
        comp_cores_bf_tables[comp_core_index].compressed_table;
    if (comp_cores_bf_tables[comp_core_index].compressed_table == NULL){
        compressed_address = MALLOC_SDRAM(
            routing_table_sdram_size_of_table(TARGET_LENGTH));
        comp_cores_bf_tables[comp_core_index].compressed_table =
            compressed_address;
        if (compressed_address == NULL) {
            log_error(
                "failed to allocate sdram for compressed routing entries");
            return false;
        }
    }

    // record addresses for response processing code
    bool success = store_sdram_addresses_for_compression(
        n_rt_addresses, comp_core_index, compressed_address, mid_point,
        comp_cores_bf_tables, bit_field_routing_tables);
    if (!success) {
        log_error("failed to store the addresses for response functionality");
        return false;
    }

    // update sdp to right destination
    update_mc_message(comp_core_index, my_msg, compressor_cores);

    // generate the message to send to the compressor core
    set_up_packet(&comp_cores_bf_tables[comp_core_index], my_msg);
    log_debug("finished setting up compressor packet");

    // send sdp packet
    message_sending_send_sdp_message(my_msg);
    return true;
}

//! \brief sets off the basic compression without any bitfields
//! \param[in] comp_cores_bf_tables: metadata holder of compressor cores such
//!  as the routing tables used in its attempt.
//! \param[in] compressor_cores: the compressor core ids.
//! \param[in] my_msg: sdp message to send
//! \param[in] usable_sdram_regions: the data for fake heap to send to the
//! compressor.
//! \param[in] uncompressed_router_table: uncompressed router table in sdram.
//! \param[in] n_compressor_cores: number of compressor cores total
//! \param[in] comp_core_mid_point: the mid points being tested
//! \param[in] n_available_compression_cores: the number of available
//! compressor cores to use for attempts.
//! \return bool saying if the memory allocations were successful and packet
//! sent. false otherwise.
bool message_sending_set_off_no_bit_field_compression(
        comp_core_store_t* comp_cores_bf_tables, int* compressor_cores,
        sdp_msg_pure_data* my_msg,
        uncompressed_table_region_data_t *uncompressed_router_table,
        int n_compressor_cores, int* comp_core_mid_point,
        int* n_available_compression_cores){

    // allocate and clone uncompressed entry
    log_debug("start cloning of uncompressed table");
    table_t *sdram_clone_of_routing_table =
        helpful_functions_clone_un_compressed_routing_table(
            uncompressed_router_table);
    if (sdram_clone_of_routing_table == NULL){
        log_error("could not allocate memory for uncompressed table for no "
                  "bit field compression attempt.");
        return false;
    }
    log_debug("finished cloning of uncompressed table");

    // set up the bitfield routing tables so that it'll map down below
    log_debug("allocating bf routing tables");
    table_t **bit_field_routing_tables = MALLOC(sizeof(table_t**));
    log_debug("malloc finished");
    if (bit_field_routing_tables == NULL){
        log_error(
            "failed to allocate memory for the bit_field_routing tables");
        return false;
    }
    log_debug("allocate to array");
    bit_field_routing_tables[0] = sdram_clone_of_routing_table;
    log_debug("allocated bf routing tables");

    // run the allocation and set off of a compressor core
    return message_sending_set_off_bit_field_compression(
        N_UNCOMPRESSED_TABLE, 0, comp_cores_bf_tables,
        bit_field_routing_tables, my_msg, compressor_cores,
        n_compressor_cores, comp_core_mid_point, n_available_compression_cores);
}

#endif  // __MESSAGE_SENDING_H__
