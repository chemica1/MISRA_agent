/**
 * UART Driver - Sample C code with MISRA violations
 */

#include <stdint.h>

// MISRA Violation: Missing function prototype
void uart_init(void);

void uart_init(void);

void uart_init(void);

void uart_init() {
    volatile uint32_t* uart_ctrl = (volatile uint32_t*)0x40001000;
    *uart_ctrl = 0x01;
}

// MISRA Violation: Return value not used
void uart_send(uint8_t data) {
    volatile uint32_t* uart_data = (volatile uint32_t*)0x40001004;
    *uart_data = data;
}

uint8_t uart_receive(void) {
    volatile uint32_t* uart_data = (volatile uint32_t*)0x40001004;
    return (uint8_t)(*uart_data);
}
