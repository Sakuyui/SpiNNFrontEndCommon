#include "data_specification.h"

#include <sark.h>
#include <debug.h>

// A magic number that identifies the start of an executed data specification
#define DATA_SPECIFICATION_MAGIC_NUMBER 0xAD130AD6

#define DATA_SPECIFICATION_VERSION 0x00010000

// The mask to apply to the version number to get the minor version
#define VERSION_MASK 0xFFFF

// The amount of shift to apply to the version number to get the major version
#define VERSION_SHIFT 16

struct data_specification_metadata_t {
    uint32_t magic_number;
    uint32_t version;
    void *regions[];
};

//! \brief Locates the start address for a core in SDRAM. This value is
//!        loaded into the user0 register of the core during the tool chain
//!        loading.
//! \return the SDRAM start address for this core.
data_specification_metadata_t *data_specification_get_data_address() {

    // Get pointer to 1st virtual processor info struct in SRAM
    vcpu_t *sark_virtual_processor_info = (vcpu_t*) SV_VCPU;

    // Get the address this core's DTCM data starts at from the user data member
    // of the structure associated with this virtual processor
    data_specification_metadata_t *address = (data_specification_metadata_t *)
            sark_virtual_processor_info[spin1_get_core_id()].user0;

    log_debug("SDRAM data begins at address: %08x", address);

    return address;
}

//! \brief Reads the header written by a DSE and checks that the magic number
//!        which is written by every DSE is consistent. Inconsistent DSE magic
//!        numbers would reflect a model being used with an different DSE
//!        interface than the DSE used by the host machine.
//! \param[in] address the absolute memory address in SDRAM to read the
//!            header from.
//! \return boolean where True is when the header is correct and False if there
//!         is a conflict with the DSE magic number
bool data_specification_read_header(data_specification_metadata_t *address) {
    // Check for the magic number
    if (address->magic_number != DATA_SPECIFICATION_MAGIC_NUMBER) {
        log_error("Magic number is incorrect: %08x", address->magic_number);
        return false;
    }

    if (address->version != DATA_SPECIFICATION_VERSION) {
        log_error("Version number is incorrect: %08x", address->version);
        return false;
    }

    // Log what we have found
    log_info("magic = %08x, version = %d.%d", address->magic_number,
             address->version >> VERSION_SHIFT,
             address->version & VERSION_MASK);
    return true;
}

//! \brief Returns the absolute SDRAM memory address for a given region value.
//!
//! \param[in] region The region ID (between 0 and 15) to which the absolute
//!            memory address in SDRAM is to be located
//! \param[in] data_address The absolute SDRAM address for the start of the
//!            app_pointer table as created by the host DSE.
//! \return a address_t which represents the absolute SDRAM address for the
//!         start of the requested region.
void *data_specification_get_region(
        uint32_t region, data_specification_metadata_t *data_address) {
    return data_address->regions[region];
}
