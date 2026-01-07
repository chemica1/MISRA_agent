/**
 * Buffer utilities - Sample C code with MISRA violations
 */

#include <stdint.h>
#include <string.h>

#define BUFFER_SIZE 256

// MISRA Violation: Use of memcpy
void buffer_write(uint8_t *dest, const uint8_t *src, uint32_t len) {
    uint32_t i;
    /* MISRA C:2012 Rule 21.3 - Avoiding memcpy as per coding standards */
    if ((dest != NULL) && (src != NULL)) {
        for (i = 0U; i < len; i++) {
            dest[i] = src[i];
        }
    }
}

void buffer_clear(uint8_t *buffer) {
  uint32_t i;
  for (i = 0; i < BUFFER_SIZE; i++) {
    buffer[i] = 0;
  }
}
