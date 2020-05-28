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

#include <spin1_api.h>
#include <debug.h>
#include <bit_field.h>
#include <circular_buffer.h>
#include <data_specification.h>
#include <malloc_extras.h>
#include "common-typedefs.h"
#include "common/routing_table.h"
#include "common/constants.h"
#include "common/compressor_sorter_structs.h"
#include "common/bit_field_table_generator.h"
#include "sorter_includes/bit_field_reader.h"
/*****************************************************************************/
/* SpiNNaker routing table minimisation with bitfield integration control
 * processor.
 *
 * controls the attempt to minimise the router entries with bitfield
 * components.
 */

//============================================================================
//! #defines and enums

//! \brief time step for safety timer tick interrupt
#define TIME_STEP 1000

//! \brief used for debug. kills after how many time steps to kill the process
#define KILL_TIME 20000

//! \brief the magic +1 for inclusive coverage that 0 index is no bitfields
#define ADD_INCLUSIVE_BIT 1

//! \brief flag for if a rtr_mc failure.
#define RTR_MC_FAILED 0

//! \brief number of bitfields that no bitfields run needs
#define NO_BIT_FIELDS 0

//! \brief bit shift for the app id for the route
#define ROUTE_APP_ID_BIT_SHIFT 24

//! \brief flag for detecting that the last message back is not a malloc fail.
#define LAST_RESULT_NOT_MALLOC_FAIL -1

//! \brief callback priorities
typedef enum priorities{
    COMPRESSION_START_PRIORITY = 3, TIMER_TICK_PRIORITY = 0
}priorities;

//============================================================================
//! global params

//! \brief DEBUG variable: counter of how many time steps have passed
uint32_t time_steps = 0;

//! \brief bool flag for saying found the best stopping position
volatile bool found_best = false;

//! \brief easier programming tracking of the user registers
uncompressed_table_region_data_t *restrict uncompressed_router_table; // user1

//! \brief stores the locations of bitfields from app processors
region_addresses_t *restrict region_addresses; // user2

//! \brief stores of sdram blocks the fake heap can use
available_sdram_blocks *restrict usable_sdram_regions; // user3

// Best midpoint that record a success
int best_success = FAILED_TO_FIND;

// Lowest midpoint that record failure
int lowest_failure;

//! \brief the store for the last routing table that was compressed
table_t *restrict last_compressed_table = NULL;

//! \brief the compressor app id
uint32_t app_id = 0;

//! \brief the list of bitfields in sorted order based off best effect, and
//! processor ids.
sorted_bit_fields_t *restrict sorted_bit_fields;

//! \brief stores which values have been tested
bit_field_t tested_mid_points;

//! \brief SDRAM used to communicate with the compressors
comms_sdram_t *restrict comms_sdram;

//! \brief record of the last mid_point to return a malloc failed
int last_malloc_failed = LAST_RESULT_NOT_MALLOC_FAIL;

//============================================================================

//! \brief Load the best routing table to the router.
//! \return bool saying if the table was loaded into the router or not
static inline bool load_routing_table_into_router(void) {

    // Try to allocate sufficient room for the routing table.
    int start_entry = rtr_alloc_id(last_compressed_table->size, app_id);
    if (start_entry == RTR_MC_FAILED) {
        log_error(
            "Unable to allocate routing table of size %d\n",
            last_compressed_table->size);
        return false;
    }

    // Load entries into the table (provided the allocation succeeded).
    // Note that although the allocation included the specified
    // application ID we also need to include it as the most significant
    // byte in the route (see `sark_hw.c`).
    log_debug("loading %d entries into router", last_compressed_table->size);
    for (uint32_t entry_id = 0; entry_id < last_compressed_table->size;
            entry_id++) {
        entry_t entry = last_compressed_table->entries[entry_id];
        uint32_t route = entry.route | (app_id << ROUTE_APP_ID_BIT_SHIFT);
        uint success = rtr_mc_set(
            start_entry + entry_id, entry.key_mask.key, entry.key_mask.mask,
            route);

        // chekc that the entry was set
        if (success == RTR_MC_FAILED) {
            log_error(
                "failed to set a router table entry at index %d",
                start_entry + entry_id);
            return false;
        }
    }

    // Indicate we were able to allocate routing table entries.
    return true;
}

//! \brief sends a message forcing the processor to stop its compression
//! attempt
//! \param[in] processor_id: the processor id to send a force stop
//! compression attempt
void send_force_stop_message(int processor_id) {
    if (comms_sdram[processor_id].sorter_instruction == RUN) {
        log_debug("sending stop to processor %d", processor_id);
        comms_sdram[processor_id].sorter_instruction = FORCE_TO_STOP;
    }
}

//! \brief sends a message telling the processor to prepare for the next run
//! This is critical as it tells the processor to clear the result field
//! \param[in] processor_id: the processor id to send a prepare to
//! compression attempt
void send_prepare_message(int processor_id) {
    // set message params
    log_debug("sending prepare to processor %d", processor_id);
    comms_sdram[processor_id].sorter_instruction = PREPARE;
    comms_sdram[processor_id].mid_point = -1;
}

//! \brief sets up the search bitfields.
//! \return bool saying success or failure of the setup
static inline bool set_up_tested_mid_points(void) {
    log_info(
        "set_up_tested_mid_point n bf addresses is %d",
        sorted_bit_fields->n_bit_fields);

    uint32_t words = get_bit_field_size(
        sorted_bit_fields->n_bit_fields + ADD_INCLUSIVE_BIT);
    tested_mid_points = (bit_field_t) MALLOC(words * sizeof(bit_field_t));

    // check the malloc worked
    if (tested_mid_points == NULL) {
        return false;
    }

    // clear the bitfields
    clear_bit_field(tested_mid_points, words);

    // return if successful
    return true;
}

//! \brief stores the addresses for freeing when response code is sent
//! \param[in] processor_id: the compressor processor id
//! \param[in] mid_point: the point in the bitfields to work from
//! \param[in] table_size: Number of entries that the uncompressed routing
//!    tables need to hold.
//! \return bool stating if stored or not
static inline bool pass_instructions_to_compressor(
    uint32_t processor_id, uint32_t mid_point, uint32_t table_size) {

    bool success = routing_table_utils_malloc(
        comms_sdram[processor_id].routing_tables, table_size);
    if (!success) {
        log_info(
            "failed to create bitfield tables for midpoint %d", mid_point);
        return false;
    }

    // set compressor states for the given processor.
    comms_sdram[processor_id].mid_point = mid_point;
    comms_sdram[processor_id].sorted_bit_fields = sorted_bit_fields;

    // Info stuff
    log_info(
        "using processor %d with %d entries for %d bitfields out of %d",
        processor_id, table_size,
        comms_sdram[processor_id].mid_point,
        comms_sdram[processor_id].sorted_bit_fields->n_bit_fields);

    comms_sdram[processor_id].sorter_instruction = RUN;
    return true;
}

//! builds tables and tries to set off a compressor processor based off
//! midpoint
//! If there is a problem will set reset the mid_point as untested and
//! set this and all unused compressors to do not use
//! \param[in] mid_point: the mid point to start at
//! \param[in] processor_id: the processor to run the compression on
static inline void malloc_tables_and_set_off_bit_compressor(
        int mid_point, int processor_id) {

    // free any previous routing tables
    routing_table_utils_free_all(comms_sdram[processor_id].routing_tables);

    // malloc space for the routing tables
    uint32_t table_size = bit_field_table_generator_max_size(
        mid_point, &uncompressed_router_table->uncompressed_table,
        sorted_bit_fields);

    malloc_extras_check_all_marked(1005);
    // if successful, try setting off the bitfield compression
    bool success = pass_instructions_to_compressor(
        processor_id, mid_point, table_size);

    if (!success) {
        // Ok lets turn this and all ready processors off to save space.
        // At least default no bitfield handled elsewhere so of to reduce.
        comms_sdram[processor_id].sorter_instruction = DO_NOT_USE;
        for (int processor_id = 0; processor_id < MAX_PROCESSORS;
                processor_id++) {
            if ((comms_sdram[processor_id].sorter_instruction == PREPARE) ||
                    (comms_sdram[processor_id].sorter_instruction == TO_BE_PREPARED)) {
                comms_sdram[processor_id].sorter_instruction = DO_NOT_USE;
            }
        }
        // Ok that midpoint did not work so need to try it again
        bit_field_clear(tested_mid_points, mid_point);
    }
}

//! \brief finds the region id in the region addresses for this processor id
//! \param[in] processor_id: the processor id to find the region id in the
//! addresses
//! \return the address in the addresses region for the processor id
static inline filter_region_t * find_processor_bit_field_region(
        int processor_id) {

    // find the right bitfield region
    for (int r_id = 0; r_id < region_addresses->n_triples; r_id++) {
        int region_proc_id = region_addresses->triples[r_id].processor;
        log_debug(
            "is looking for %d and found %d", processor_id, region_proc_id);
        if (region_proc_id == processor_id) {
            return region_addresses->triples[r_id].filter;
        }
    }

    // if not found
    log_error("failed to find the right region. WTF");
    malloc_extras_terminate(EXIT_SWERR);
    return NULL;
}

//! \brief set_n_merged_filters for every core with bitfields
//! bitfield regions
static inline void set_n_merged_filters(void) {
    uint32_t highest_key[MAX_PROCESSORS];
    int highest_order[MAX_PROCESSORS];
    log_info("best_success %d", best_success);

    // Initialize highest order to -1 ie None merged in
    for (int index = 0; index < MAX_PROCESSORS; index++) {
        highest_order[index] = -1;
    }

    // Find the first key above the best midpoint for each processor
    for (int sorted_index = 0; sorted_index < sorted_bit_fields->n_bit_fields;
            sorted_index++) {
        int test = sorted_bit_fields->sort_order[sorted_index];
        if (test <= best_success) {
            int processor_id = sorted_bit_fields->processor_ids[sorted_index];
            if (test > highest_order[processor_id]) {
                highest_order[processor_id] = test;
                highest_key[processor_id] =
                    sorted_bit_fields->bit_fields[sorted_index]->key;
            }
        }
    }

    // debug
    for (int processor_id = 0; processor_id < MAX_PROCESSORS; processor_id++) {
        log_debug("processor %d, first_key %d first_order %d", processor_id,
            highest_key[processor_id], highest_order[processor_id]);
    }

    // Set n_redundancy_filters
    for (int r_id = 0; r_id < region_addresses->n_triples; r_id++) {
        int processor_id = region_addresses->triples[r_id].processor;
        filter_region_t *filter = region_addresses->triples[r_id].filter;
        int index = filter->n_redundancy_filters - 1;

        // Find the index of highest one merged in
        while ((index >= 0) &&
                (filter->filters[index].key != highest_key[processor_id])) {
            index--;
        }
        filter->n_merged_filters = index + 1;
        log_info("core %d has %d bitfields of which %d have redundancy "
            "of which %d merged in", processor_id, filter->n_filters,
            filter->n_redundancy_filters, filter->n_merged_filters);
    }
}

//! \brief locates the next valid midpoint to test
//! \return int which is the midpoint or -1 if no midpoints left
static inline int locate_next_mid_point(void) {
    int new_mid_point;

    // If not tested yet / reset test 0
    if (!bit_field_test(tested_mid_points, 0)) {
        log_info("Retrying no bit fields");
        return 0;
    } else {
        if (sorted_bit_fields->n_bit_fields == 0) {
            return FAILED_TO_FIND;
        }
    }

    // if not tested yet / reset test all
    if (!bit_field_test(tested_mid_points, sorted_bit_fields->n_bit_fields)){
        log_info("Retrying all which is mid_point %d",
            sorted_bit_fields->n_bit_fields);
        return sorted_bit_fields->n_bit_fields;
    }

    // need to find a midpoint
    log_debug(
        "n_bf_addresses %d tested_mid_points %d",
        sorted_bit_fields->n_bit_fields,
        bit_field_test(tested_mid_points, sorted_bit_fields->n_bit_fields));

    // the last point of the longest space
    int best_end = FAILED_TO_FIND;

    // the length of the longest space to test
    int best_length = 0;

    // the current length of the currently detected space
    int current_length = 0;

    log_debug(
        "best_success %d lowest_failure %d", best_success, lowest_failure);

    // iterate over the range to binary search, looking for biggest block to
    // explore, then take the middle of that block

    // NOTE: if there are no available bitfields, this will result in best end
    // being still set to -1, as every bit is set, so there is no blocks with
    // any best length, and so best end is never set and lengths will still be
    // 0 at the end of the for loop. -1 is a special midpoint which higher
    // code knows to recognise as no more exploration needed.
    for (int index = best_success + 1; index <= lowest_failure; index++) {
        log_debug(
            "index: %d, value: %u current_length: %d",
            index, bit_field_test(tested_mid_points, index),
            current_length);

        // verify that the index has been used before
        if (bit_field_test(tested_mid_points, index)) {

           // if used before and is the end of the biggest block seen so far.
           // Record and repeat.
           if (current_length > best_length) {
                best_length = current_length;
                best_end = index - 1;
                log_debug(
                    "found best_length: %d best_end %d",
                    best_length, best_end);
           // if not the end of the biggest block, ignore (log for debugging)
           } else {
                log_debug(
                    "not best: %d best_end %d", best_length, best_end);
           }
           // if its seen a set we're at the end of a block. so reset the
           // current block len, as we're about to start another block.
           current_length = 0;
        // not set, so still within a block, increase len.
        } else {
           current_length += 1;
        }
    }

    // use the best less half (shifted) of the best length
    new_mid_point = best_end - (best_length >> 1);
    log_debug("returning mid point %d", new_mid_point);

    // set the mid point to be tested. (safe as we de-set if we fail later on)
    if (new_mid_point >= 0) {
        log_debug("setting new mid point %d", new_mid_point);

        // just a safety check, as this has caught us before.
        if (bit_field_test(tested_mid_points, new_mid_point)) {
            log_info("HOW THE HELL DID YOU GET HERE!");
            malloc_extras_terminate(EXIT_SWERR);
        }
    }

    return new_mid_point;
}

//! \brief handles the freeing of memory from compressor processors, waiting
//! for compressor processors to finish and removing merged bitfields from
//! the bitfield regions.
static inline void handle_best_cleanup(void) {
    if (best_success == FAILED_TO_FIND) {
        log_error("No usable result found!");
        malloc_extras_terminate(RTE_SWERR);
    }

    // load routing table into router
    load_routing_table_into_router();
    log_debug("finished loading table");

    log_info("setting set_n_merged_filters");
    set_n_merged_filters();

    // This is to allow the host report to know how many bitfields on the chip
    // merged without reading every cores bit-field region.
    vcpu_t *sark_virtual_processor_info = (vcpu_t *) SV_VCPU;
    uint processor_id = spin1_get_core_id();
    sark_virtual_processor_info[processor_id].user2 = best_success;

    // Safety to break out of loop in check_buffer_queue as terminate wont
    // stop this interrupt
    found_best = true;

    // set up user registers etc to finish cleanly
    malloc_extras_terminate(EXITED_CLEANLY);
}

//! \brief Prepares a processor for the first time.
//!
//! This includes mallocing the comp_instruction_t user
//! \param[in] mid_point: the mid point this processor will use
//! \return the processor id of the next available processor or -1 if none
bool prepare_processor_first_time(int processor_id) {
    comms_sdram[processor_id].sorter_instruction = PREPARE;

    //! Create the space for the routing table meta data
    comms_sdram[processor_id].routing_tables =
        MALLOC_SDRAM(sizeof(multi_table_t));
    if (comms_sdram[processor_id].routing_tables == NULL) {
        comms_sdram[processor_id].sorter_instruction = DO_NOT_USE;
        log_error("Error mallocing routing bake pointer on  %d", processor_id);
            return false;
    }
    comms_sdram[processor_id].routing_tables->sub_tables = NULL;
    comms_sdram[processor_id].routing_tables->n_sub_tables = 0;
    comms_sdram[processor_id].routing_tables->n_entries = 0;

    //! Pass the fake heap stuff
    comms_sdram[processor_id].fake_heap_data = malloc_extras_get_stolen_heap();
    log_debug("fake_heap_data %u", comms_sdram[processor_id].fake_heap_data);

    //! Check the processor is live
    int count = 0;
    while (!(comms_sdram[processor_id].compressor_state == PREPARED)) {
        // give chance for compressor to read
        spin1_delay_us(50);
        count++;
        if (count > 20) {
            comms_sdram[processor_id].sorter_instruction = DO_NOT_USE;
            log_error("compressor failed to reply %d",
                processor_id);
            return false;
        }
    }
    return true;
}

//! \brief Returns the next processor id which is ready to run a compression.
//! may result in preparing a processor in the process.
//! \param[in] mid_point: the mid point this processor will use
//! \return the processor id of the next available processor or -1 if none
int find_prepared_processor(void) {
    // Look for a prepared one
    for (int processor_id = 0; processor_id < MAX_PROCESSORS; processor_id++) {
        if (comms_sdram[processor_id].sorter_instruction == PREPARE) {
            if (comms_sdram[processor_id].compressor_state == PREPARED) {
                log_debug("found prepared %d", processor_id);
                return processor_id;
            }
        }
    }

    // NOTE: This initialization component exists here due to a race condition
    // with the compressors, where we dont know if they are reacting to
    // "messages" before sync signal has been sent. We also have this here to
    // save the 16 bytes per compressor core we dont end up using.

    // Look for a processor never used and  prepare it
    for (int processor_id = 0; processor_id < MAX_PROCESSORS; processor_id++) {
        log_debug(
            "processor_id %d status %d",
            processor_id, comms_sdram[processor_id].sorter_instruction);
        if (comms_sdram[processor_id].sorter_instruction == TO_BE_PREPARED) {
            if (prepare_processor_first_time(processor_id)) {
                log_debug("found to be prepared %d", processor_id);
                return processor_id;
            } else {
                log_debug("first failed %d", processor_id);
            }
        }
    }
    log_debug("FAILED %d", FAILED_TO_FIND);
    return FAILED_TO_FIND;
}

//! \brief Returns the next processor id which is ready to run a compression
//! \param[in] mid_point: the mid point this processor will use
//! \return the processor id of the next available processor or -1 if none
int find_compressor_processor_and_set_tracker(int midpoint) {
    int processor_id = find_prepared_processor();
    if (processor_id > FAILED_TO_FIND) {
        // allocate this core to do this midpoint.
        comms_sdram[processor_id].mid_point = midpoint;
        // set the tracker to use this midpoint
        bit_field_set(tested_mid_points, midpoint);
        // return processor id
    }
    log_debug("returning %d", processor_id);
    return processor_id;
}

//! \brief sets up the compression attempt for the no bitfield version.
//! \return bool which says if setting off the compression attempt was
//! successful or not.
bool setup_no_bitfields_attempt(void) {
    int processor_id = find_compressor_processor_and_set_tracker(NO_BIT_FIELDS);
    if (processor_id == FAILED_TO_FIND) {
        log_error("No processor available for no bitfield attempt");
        malloc_extras_terminate(RTE_SWERR);
    }
    // set off a none bitfield compression attempt, to pipe line work
    log_info("sets off the no bitfield version of the search on %u", processor_id);

    pass_instructions_to_compressor(
        processor_id, NO_BIT_FIELDS,
        uncompressed_router_table->uncompressed_table.size);
    malloc_extras_check_all_marked(1001);
    return true;
}

//! \brief Check if a compressor processor is available
//! \return true if at least one processor is ready to compress
bool all_compressor_processors_busy(void) {
    for (int processor_id = 0; processor_id < MAX_PROCESSORS; processor_id++) {
        log_debug("processor_id %d status %d", processor_id,
            comms_sdram[processor_id].sorter_instruction);
        if (comms_sdram[processor_id].sorter_instruction == PREPARE) {
            if (comms_sdram[processor_id].compressor_state == PREPARED) {
                return false;
            }
        }
        else if (comms_sdram[processor_id].sorter_instruction == TO_BE_PREPARED) {
            return false;
        }
    }
    return true;
}

//! \brief Check to see if all compressor processor are done and not ready
//! \return true if all processors are done and not set ready
bool all_compressor_processors_done(void) {
    for (int processor_id = 0; processor_id < MAX_PROCESSORS; processor_id++) {
        if (comms_sdram[processor_id].sorter_instruction >= PREPARE) {
            return false;
        }
    }
    return true;
}

//! \brief Start the binary search on another compressor if one available
void carry_on_binary_search(void) {
     if (all_compressor_processors_done()) {
        log_info("carry_on_binary_search detected done");
        handle_best_cleanup();
        // Above method has a terminate so no worry about carry on here
    }
    if (all_compressor_processors_busy()) {
        log_debug("all_compressor_processors_busy");
        return;  //Pass back to check_buffer_queue
    }
    log_debug("start carry_on_binary_search");

    int mid_point = locate_next_mid_point();
    log_debug("available with midpoint %d", mid_point);

    if (mid_point == FAILED_TO_FIND) {
        // Ok lets turn all ready processors off as done.
        for (int processor_id = 0; processor_id < MAX_PROCESSORS; processor_id++) {
            if (comms_sdram[processor_id].sorter_instruction == PREPARE) {
                comms_sdram[processor_id].sorter_instruction = DO_NOT_USE;
            } else if (comms_sdram[processor_id].sorter_instruction > PREPARE) {
                log_debug(
                    "waiting for processor %d status %d doing midpoint %u",
                    processor_id,
                    comms_sdram[processor_id].sorter_instruction,
                    comms_sdram[processor_id].mid_point);
            }
        }
        return;
    }

    int processor_id = find_compressor_processor_and_set_tracker(mid_point);
    log_debug("start create at time step: %u", time_steps);
    malloc_tables_and_set_off_bit_compressor(mid_point, processor_id);
    log_debug("end create at time step: %u", time_steps);
    malloc_extras_check_all_marked(1002);
}

//! \brief timer interrupt for controlling time taken to try to compress table
//! \param[in] unused0: not used
//! \param[in] unused1: not used
void timer_callback(uint unused0, uint unused1) {
    use(unused0);
    use(unused1);
    time_steps+=1;
    // Debug stuff please keep
    //if ((time_steps & 1023) == 0){
    //    log_info("time_steps: %u", time_steps);
    //}
    //if (time_steps > KILL_TIME){
    //    log_error("timer overran %u", time_steps);
    //    malloc_extras_terminate(RTE_SWERR);
    //}
}

//! brief handle the fact that a midpoint was successfull.
//! \param[in] mid_point: the mid point that failed
//! \param[in] processor_id: the compressor processor id
void process_success(int mid_point, int processor_id) {
    comms_sdram[processor_id].mid_point = -1;
    if (best_success <= mid_point) {
        best_success = mid_point;
        malloc_extras_check_all_marked(1003);
        // If we have a previous table free it as no longer needed
        if (last_compressed_table != NULL) {
            FREE_MARKED(last_compressed_table, 1100);
        }
        // Get last table and free the rest
        last_compressed_table = routing_table_utils_convert(
            comms_sdram[processor_id].routing_tables);
        log_debug("n entries is %d", last_compressed_table->size);
        malloc_extras_check_all_marked(1004);
    } else {
        routing_table_utils_free_all(comms_sdram[processor_id].routing_tables);
    }

    // kill any search below this point, as they all redundant as
    // this is a better search.
    for (int processor_id = 0; processor_id < MAX_PROCESSORS; processor_id++) {
        if (comms_sdram[processor_id].mid_point < mid_point) {
            send_force_stop_message(processor_id);
        }
    }

    last_malloc_failed = LAST_RESULT_NOT_MALLOC_FAIL;
    log_debug("finished process of successful compression");
}

//! brief handle the fact that a midpoint failed due to a malloc
//! \param[in] mid_point: the mid point that failed
//! \param[in] processor_id: the compressor processor id
void process_failed_malloc(int mid_point, int processor_id) {
    routing_table_utils_free_all(comms_sdram[processor_id].routing_tables);
    // Remove the flag that say this midpoint has been checked
    bit_field_clear(tested_mid_points, mid_point);
    if (last_malloc_failed == LAST_RESULT_NOT_MALLOC_FAIL) {
        // Remove the flag that say this midpoint has been checked
        bit_field_clear(tested_mid_points, mid_point);
        // this will threshold the number of compressor processors that
        // can be ran at any given time.
        comms_sdram[processor_id].sorter_instruction = DO_NOT_USE;
        last_malloc_failed = mid_point;
    } else if (last_malloc_failed == mid_point) {
        if (mid_point == 0) {
            // Dont give up on mid point zero
            bit_field_clear(tested_mid_points, mid_point);
        }
        log_info("Repeated malloc fail detected at %d", mid_point);
        comms_sdram[processor_id].sorter_instruction = DO_NOT_USE;
        // Not resetting tested_mid_points as failed twice
    } else {
        log_info("Multiple malloc detected on %d keeping processor %d",
            mid_point, processor_id);
        bit_field_clear(tested_mid_points, mid_point);
        // Not thresholding as just did a threshold
        // Every other malloc should result in a thresholded
        // This ensures we do not end in a endless loop of malloc fails
        last_malloc_failed = LAST_RESULT_NOT_MALLOC_FAIL;
    }
}

//! brief handle the fact that a midpoint failed.
//! \param[in] mid_point: the mid point that failed
//! \param[in] processor_id: the compressor processor id
void process_failed(int mid_point, int processor_id) {
    // safety check to ensure we dont go on if the uncompressed failed
    if (mid_point == 0)  {
        log_error("The no bitfields attempted failed! Giving up");
        malloc_extras_terminate(EXIT_FAIL);
    }
    if (lowest_failure > mid_point) {
        log_info(
            "Changing lowest_failure from: %d to mid_point:%d",
            lowest_failure, mid_point);
        lowest_failure = mid_point;
    } else {
        log_info(
            "lowest_failure: %d already lower than mid_point:%d",
            lowest_failure, mid_point);
    }
    routing_table_utils_free_all(comms_sdram[processor_id].routing_tables);

    // tell all compression processors trying midpoints above this one
    // to stop, as its highly likely a waste of time.
    for (int processor_id = 0; processor_id < MAX_PROCESSORS; processor_id++) {
        if (comms_sdram[processor_id].mid_point > mid_point) {
            send_force_stop_message(processor_id);
        }
    }

    last_malloc_failed = LAST_RESULT_NOT_MALLOC_FAIL;
}

//! \brief processes the response from the compressor attempt
//! \param[in] processor_id: the compressor processor id
//! \param[in] finished_state: the response code
void process_compressor_response(
        int processor_id, compressor_states finished_state) {
    int mid_point = comms_sdram[processor_id].mid_point;
    log_debug("received response %d from processor %d doing %d midpoint",
        finished_state, processor_id, mid_point);

    // free the processor for future processing
    send_prepare_message(processor_id);

    switch (finished_state) {

        // compressor was successful at compressing the tables.
        case SUCCESSFUL_COMPRESSION:
            log_info(
                "successful from processor %d doing mid point %d "
                "best so far was %d",
                processor_id, mid_point, best_success);
            process_success(mid_point, processor_id);
            break;

        // compressor failed as a malloc request failed.
        case FAILED_MALLOC:
            log_info(
                "failed by malloc from processor %d doing mid point %d",
                processor_id, mid_point);
            process_failed_malloc(mid_point, processor_id);
            break;

        // compressor failed to compress the tables as no more merge options.
        case FAILED_TO_COMPRESS:
            log_info(
                "failed to compress from processor %d doing mid point %d",
                processor_id, mid_point);
            process_failed(mid_point, processor_id);
            break;

        // compressor failed to compress as it ran out of time.
        case RAN_OUT_OF_TIME:
            log_info(
                "failed by time from processor %d doing mid point %d",
                processor_id, mid_point);
            process_failed(mid_point, processor_id);
            break;

        // compressor stopped at the request of the sorter.
        case FORCED_BY_COMPRESSOR_CONTROL:
            log_info(
                "ack from forced from processor %d doing mid point %d",
                processor_id, mid_point);
            routing_table_utils_free_all(
                comms_sdram[processor_id].routing_tables);
            break;
        case UNUSED:
        case PREPARED:
        case COMPRESSING:
            log_error(
                "no idea what to do with finished state %d, from processor %d ",
                finished_state, processor_id);
            malloc_extras_terminate(RTE_SWERR);
    }
}

//! \brief check compressors till its finished
//! \param[in] unused0: api
//! \param[in] unused1: api
void check_compressors(uint unused0, uint unused1) {
    use(unused0);
    use(unused1);

    log_info("Entering the check_compressors loop");
    // iterate over the compressors buffer until we have the finished state
    while (!found_best) {
        bool no_new_result = true;

        // iterate over processors looking for a new result
        for (int processor_id = 0; processor_id < MAX_PROCESSORS; processor_id++) {
            // Check each compressor asked to run or forced
            compressor_states finished_state =
                comms_sdram[processor_id].compressor_state;
            if (finished_state > COMPRESSING) {
                no_new_result = false;
                process_compressor_response(processor_id, finished_state);
            }
        }
        if (no_new_result) {
            log_debug("no_new_result");
            // Check if another processor could be started or even done
            carry_on_binary_search();
        } else {
            log_debug("result");
        }
    }
    // Safety code in case exit after setting best_found fails
    log_info("exiting the interrupt, to allow the binary to finish");
}

//! \brief Starts binary search on all compressor diving the bitfields as even
//! as possible
void start_binary_search(void) {
    // Find the number of available processors
    uint32_t available = 0;
    for (int processor_id = 0; processor_id < MAX_PROCESSORS; processor_id++) {
        if (comms_sdram[processor_id].sorter_instruction == TO_BE_PREPARED) {
            available += 1;
        }
    }

    uint32_t mid_point = sorted_bit_fields->n_bit_fields;
    while ((available > 0) && (mid_point > 0)) {
        int processor_id = find_compressor_processor_and_set_tracker(mid_point);
        // Check the processor replied and has not been turned of by previous
        if (processor_id == FAILED_TO_FIND) {
            log_error("No processor available in start_binary_search");
            return;
        }
        malloc_tables_and_set_off_bit_compressor(mid_point, processor_id);

        // Find the next step which may change due to rounding
        int step = (mid_point / available);
        if (step < 1) {
            step = 1;
        }
        mid_point -= step;
        available -= 1;
    }
}

//! \brief starts the work for the compression search
//! \param[in] unused0: api
//! \param[in] unused1: api
void start_compression_process(uint unused0, uint unused1) {
    //api requirements
    use(unused0);
    use(unused1);

    // malloc the struct and populate n bit-fields. DOES NOT populate the rest.
    sorted_bit_fields = bit_field_reader_initialise(region_addresses);

    // check state to fail if not read in
    // TODO this may not be valid action when trying to allow uncompressed
    // best chance to pass.
    if (sorted_bit_fields == NULL) {
        log_error("failed to read in bitfields, quitting");
        malloc_extras_terminate(EXIT_MALLOC);
    }

    // set up mid point trackers. NEEDED here as setup no bitfields attempt
    // will use it during processor allocation.
    set_up_tested_mid_points();

    // set off the first compression attempt (aka no bitfields).
    bool success = setup_no_bitfields_attempt();
    if (!success){
        log_error("failed to set up uncompressed attempt");
        malloc_extras_terminate(EXIT_MALLOC);
    }

    log_debug("populating sorted bitfields at time step: %d", time_steps);
    bit_field_reader_read_in_bit_fields(region_addresses, sorted_bit_fields);

    // the first possible failure is all bitfields so set there.
    lowest_failure = sorted_bit_fields->n_bit_fields;
    log_debug("finished reading bitfields at time step: %d", time_steps);

    //TODO: safety code to be removed
    for (int bit_field_index = 0;
            bit_field_index < sorted_bit_fields->n_bit_fields;
            bit_field_index++) {
        // get key
        filter_info_t* bf_pointer =
            sorted_bit_fields->bit_fields[bit_field_index];
        if (bf_pointer == NULL) {
            log_info("failed at index %d", bit_field_index);
            malloc_extras_terminate(RTE_SWERR);
            return;
        }
    }

    start_binary_search();

    // set off checker which in turn sets of the other compressor processors
    spin1_schedule_callback(
        check_compressors, 0, 0, COMPRESSION_START_PRIORITY);
}

//! \brief sets up a tracker for the user registers so that its easier to use
//!  during coding.
static void initialise_user_register_tracker(void) {
    log_debug("set up user register tracker (easier reading)");
    vcpu_t *restrict sark_virtual_processor_info = (vcpu_t *) SV_VCPU;
    vcpu_t *restrict this_vcpu_info =
        &sark_virtual_processor_info[spin1_get_core_id()];

    // convert user registers to struct pointers
    data_specification_metadata_t *restrict app_ptr_table =
        (data_specification_metadata_t *) this_vcpu_info->user0;
    uncompressed_router_table =
        (uncompressed_table_region_data_t *) this_vcpu_info->user1;
    region_addresses = (region_addresses_t *) this_vcpu_info->user2;

    comms_sdram = (comms_sdram_t*)region_addresses->comms_sdram;
    for (int processor_id = 0; processor_id < MAX_PROCESSORS; processor_id++) {
        comms_sdram[processor_id].compressor_state = UNUSED;
        comms_sdram[processor_id].sorter_instruction = NOT_COMPRESSOR;
        comms_sdram[processor_id].mid_point = FAILED_TO_FIND;
        comms_sdram[processor_id].routing_tables = NULL;
        comms_sdram[processor_id].uncompressed_router_table =
            &uncompressed_router_table->uncompressed_table;
        comms_sdram[processor_id].sorted_bit_fields = NULL;
        comms_sdram[processor_id].fake_heap_data = NULL;
    }
    usable_sdram_regions = (available_sdram_blocks *) this_vcpu_info->user3;

    log_debug(
        "finished setting up register tracker: \n\n"
        "user0 = %d\n user1 = %d\n user2 = %d\n user3 = %d\n",
        app_ptr_table, uncompressed_router_table,
        region_addresses, usable_sdram_regions);
}

//! \brief reads in router table setup params
static void initialise_routing_control_flags(void) {
    app_id = uncompressed_router_table->app_id;
    log_debug(
        "app id %d, uncompress total entries %d",
        app_id, uncompressed_router_table->uncompressed_table.size);
}

//! \brief get compressor processors
//! \return bool saying if the init compressor succeeded or not.
bool initialise_compressor_processors(void) {
    // allocate DTCM memory for the processor status trackers
    log_info("allocate and step compressor processor status");
    compressor_processors_top_t *compressor_processors_top =
        (void *) &region_addresses->triples[region_addresses->n_triples];

    // Switch compressor processors to TO_BE_PREPARED
    for (uint32_t processor_index = 0;
            processor_index < compressor_processors_top->n_processors;
            processor_index++) {
        int processor_id =
            compressor_processors_top->processor_id[processor_index];
        comms_sdram[processor_id].sorter_instruction = TO_BE_PREPARED;
    }
    return true;
}

//! \brief the callback for setting off the router compressor
//! \return bool which says if the initialisation was successful or not.
static bool initialise(void) {
    log_debug(
        "Setting up stuff to allow bitfield comp control class to occur.");

    // Get pointer to 1st virtual processor info struct in SRAM
    initialise_user_register_tracker();

    // ensure the original table is sorted by key
    // (done here instead of by host for performance)
    sort_table_by_key(&uncompressed_router_table->uncompressed_table);

    // get the compressor data flags (app id, compress only when needed,
    //compress as much as possible, x_entries
    initialise_routing_control_flags();

    // build the fake heap for allocating memory
    log_info("setting up fake heap for sdram usage");
    bool heap_creation = malloc_extras_initialise_and_build_fake_heap(
            usable_sdram_regions);
    if (!heap_creation) {
        log_error("failed to setup stolen heap");
        return false;
    }
    log_info("finished setting up fake heap for sdram usage");

    // get the compressor processors stored in an array
    log_debug("start init of compressor processors");
    bool success_compressor_processors = initialise_compressor_processors();
    if (!success_compressor_processors) {
        log_error("failed to init the compressor processors.");
        return false;
    }

    // finished init
    return true;
}

//! \brief the main entrance.
void c_main(void) {
    bool success_init = initialise();
    if (!success_init) {
        log_error("failed to init");
        malloc_extras_terminate(EXIT_FAIL);
    }

    // set up interrupts
    spin1_set_timer_tick(TIME_STEP);
    spin1_callback_on(TIMER_TICK, timer_callback, TIMER_TICK_PRIORITY);

    // kick-start the process
    spin1_schedule_callback(
      start_compression_process, 0, 0, COMPRESSION_START_PRIORITY);

    // go
    log_debug("waiting for sycn");
    spin1_start(SYNC_WAIT);
}
