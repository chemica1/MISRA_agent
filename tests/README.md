# Test files for MISRA C Refactoring Agent

This directory contains sample C code with intentional MISRA C violations for testing the agent.

## Files

- `sample_violations.csv` - Sample violations report
- `sample_code/uart.c` - UART driver with MISRA violations
- `sample_code/buffer.c` - Buffer utilities with MISRA violations

## Running Tests

To test the agent with these samples:

1. Copy `.env.example` to `.env`
2. Edit `.env` and set:
   ```
   PROJECT_ROOT=./tests/sample_code
   VIOLATIONS_CSV=./tests/sample_violations.csv
   ```
3. Run the agent:
   ```bash
   python -m src.main
   ```

## Expected Results

The agent should:
1. Fix `uart_init` by adding proper prototype
2. Fix `uart_send` by adding void cast or using return value
3. Fix `buffer_write` by replacing memcpy with manual loop

Check `refactoring_log.json` for detailed results.
