#ifndef __BIT_SET_H__
#define __BIT_SET_H__

#include <stdint.h>
#include "../common/platform.h"
#include "../common/common_helpful_functions.h"

typedef struct _bit_set_t {
    unsigned int count;       // Keep track of members
    unsigned int n_words;     // Number of words in _data
    unsigned int n_elements;  // Number of elements which may be in the set
    uint32_t *_data;          // Pointer to data
} bit_set_t;

// Empty a bitset entirely
static inline bool bit_set_clear(bit_set_t *b) {
    // Clear the data
    for (unsigned int i = 0; i < b->n_words; i++) {
        b->_data[i] = 0x0;
    }

    // Reset the count
    b->count = 0;

    return true;
}

// Create a new bitset
static inline bool bit_set_init(bit_set_t *b, unsigned int length) {
    // Malloc space for the data
    unsigned int n_words = length / 32;
    if (length % 32) {
        n_words++;
    }

    uint32_t *data = (uint32_t *) MALLOC(n_words * sizeof(uint32_t));

    if (data == NULL) {
        b->_data = NULL;
        b->n_elements = 0;
        b->n_words = 0;
        return false;
    } else {
        b->_data = data;
        b->n_words = n_words;
        b->n_elements = length;
        bit_set_clear(b);
        return true;
    }
}

// Destruct a bitset
static inline void bit_set_delete(bit_set_t *b) {
    FREE(b->_data);  // Free the storage
    b->_data = NULL;
    b->n_elements = 0;
}

// Add an element to a bitset
static inline bool bit_set_add(bit_set_t* b, unsigned int i) {
    if (b->n_elements <= i) {
        return false;
    }

    // Determine the word and bit
    unsigned int word = i / 32;
    unsigned int bit  = 1 << (i & 31);

    b->_data[word] |= bit;  // Set the word and bit
    b->count++;             // Increment the count of set elements
    return true;
}

// Test if an element is in a bitset
static inline bool bit_set_contains(bit_set_t *b, unsigned int i) {
    if (b->n_elements <= i) {
        return false;
    }

    // Determine the word and bit
    unsigned int word = i / 32;
    uint32_t bit  = 1 << (i & 31);
    return (bool) (b->_data[word] & bit);
}

// Remove an element from a bitset
static inline bool bit_set_remove(bit_set_t *b, unsigned int i) {
    if (!bit_set_contains(b, i)) {
        return false;
    }
    // Determine the word and bit
    unsigned int word = i >> 5;
    unsigned int bit  = 1 << (i & 0x1f);

    b->count--;              // Decrement the count of set elements
    b->_data[word] &= ~bit;  // Unset the bit of the appropriate word
    return true;
}

//! \brief This function prints out an entire bit_field,
// as a sequence of ones and zeros.
//! \param[in] b The sequence of words representing a bit_field.
//! \param[in] s The size of the bit_field.
void print_bit_set_bits(bit_field_t b, int s) {
    use(b);
    use(s);
    int i; //!< For indexing through the bit field
    for (i = s; i > 0; i--) {
	    print_bit_field_entry_v2(b[i], ((i - 1) * 32));
    }
}

void print_bit_set(bit_set_t b){
    print_bit_set_bits(b._data, b.n_words);
}

#endif  // __BIT_SET_H__
