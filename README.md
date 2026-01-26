# MISRA C Refactoring Agent

Autonomous Python agent that uses local LLM (Ollama) to refactor C code according to MISRA C standards.

## Features

- 🤖 **Autonomous Agent**: LangGraph-based agentic loop with self-correction
- 🔒 **Security First**: Path traversal prevention, automatic backups
- 📊 **CSV-Driven**: Processes violation reports systematically
- 🔄 **State Persistence**: Resume interrupted sessions
- 📝 **Comprehensive Logging**: Detailed audit trail of all changes

## Prerequisites

1. **Python 3.10+**
2. **Ollama** installed and running locally
   ```bash
   # Install Ollama from https://ollama.ai
   # Pull a code model:
   ollama pull deepseek-coder
   # or
   ollama pull codellama
   ```

## Installation

1. **Clone and navigate to project**:
   ```bash
   cd MISRA_agent
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   ```

3. **Activate virtual environment**:
   ```bash
   # Windows
   .\venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

## Usage

### Basic Usage

```bash
python -m src.main
```

This will:
1. Read violations from `violations.csv`
2. Process each violation autonomously
3. Create `.bak` backups before modifications
4. Log all changes to `refactoring_log.json`
5. Save state to `state.json` for resume capability

### Configuration

Edit `.env` file:

```env
# Ollama Configuration
OLLAMA_MODEL=deepseek-coder
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT=120

# Agent Configuration
MAX_RETRIES=3
PROJECT_ROOT=./target_project
VIOLATIONS_CSV=./violations.csv

# Logging
LOG_LEVEL=INFO
LOG_FILE=refactoring_log.json
STATE_FILE=state.json
```

### Input Format (violations.csv)

```csv
file_path,function_name,violation_description
src/driver/uart.c,uart_init,MISRA C:2012 Rule 8.4 - Missing function prototype
src/utils/buffer.c,buffer_write,MISRA C:2012 Rule 17.7 - Return value not checked
```

### Resume Interrupted Session

If the agent is interrupted (Ctrl+C), simply run it again:

```bash
python -m src.main
```

It will automatically resume from `state.json`.

## Architecture

```
┌─────────────────┐
│ Load Violations │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Decide Action   │◄──────┐
│ (LLM Reasoning) │       │
└────────┬────────┘       │
         │                │
         ▼                │
┌─────────────────┐       │
│ Execute Action  │       │
│ (Tools)         │       │
└────────┬────────┘       │
         │                │
         ▼                │
┌─────────────────┐       │
│ Observe Result  │       │
│ (Validation)    │       │
└────────┬────────┘       │
         │                │
         ▼                │
┌─────────────────┐       │
│ Route Next      │───────┘
│ (Success/Retry) │  retry < 3
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Next Violation  │
└─────────────────┘
```

## Output

### Console Output (Real-time)

```
[THINKING] Analyzing violation in uart.c::uart_init...
[ACTION] Reading file: src/driver/uart.c
[OBSERVATION] Function found at lines 45-67
[THINKING] Generating MISRA-compliant fix...
[ACTION] Applying modification with backup
[OBSERVATION] Syntax validation passed ✓
[SUCCESS] Fixed MISRA Rule 8.4 violation
```

### refactoring_log.json

```json
[
  {
    "timestamp": "2026-01-07T11:20:00+09:00",
    "file_path": "src/driver/uart.c",
    "function_name": "uart_init",
    "violation": "MISRA C:2012 Rule 8.4 - Missing function prototype",
    "original_code": "void uart_init() { ... }",
    "modified_code": "static void uart_init(void) { ... }",
    "reason": "Added 'static' keyword and explicit 'void' parameter",
    "status": "success",
    "retry_count": 0
  }
]
```

## Security Features

- ✅ **Path Traversal Prevention**: All file paths validated using `os.path.commonpath`
- ✅ **Automatic Backups**: `.bak` files created before any modification
- ✅ **Sandboxed Execution**: Agent restricted to `PROJECT_ROOT` directory


## Development

### Project Structure

```
MISRA_agent/
├── src/
│   ├── agent/          # LangGraph workflow
│   ├── tools/          # File ops, LLM client, validators
│   ├── config/         # Settings management
│   └── main.py         # Entry point
├── tests/              # Sample data and tests
├── venv/               # Virtual environment
└── requirements.txt
```

## Limitations

- **LLM Dependency**: Effectiveness depends on Ollama model capabilities
- **Syntax-Only Validation**: No actual compilation (to avoid toolchain dependencies)
- **Heuristic Checks**: Semantic preservation uses heuristics, not formal verification
- **Manual Review Required**: Always review changes before production deployment
