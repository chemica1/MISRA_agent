"""LLM Prompts for MISRA C Agent."""

# Decide Action Prompts
DECIDE_ACTION_SYSTEM_PROMPT = """Refactor C code to fix the MISRA C violation.
STRICT JSON OUTPUT ONLY. No markdown, no "Here is the code", no conversational text.

RULES:
1. Fix ONLY the specified violation. Do not change other logic.
2. If code ALREADY complies, return action="already_compliant".
3. If fix requires unsafe changes (signature change, global vars, external dependencies), return action="skip" and is_safe=false.

RESPONSE SCHEMA:
{
    "action": "modify_code" | "skip" | "already_compliant",
    "reasoning": "Brief technical explanation",
    "is_safe": boolean,
    "safety_concerns": "string or null",
    "modified_code": "string (FULL function code) or null",
    "reason": "Brief commit message style reason"
}"""

DECIDE_ACTION_USER_TEMPLATE = """VIOLATION: {violation}

CODE:
```c
{function_code}
```
"""

# Find Function Prompts
FIND_FUNCTION_SYSTEM_PROMPT = """Locate the definition of the specified function in the C code.
STRICT JSON OUTPUT ONLY.

RULES:
1. Find EXACT start_line (first line of signature) and end_line (closing brace).
2. Must be a FUNCTION DEFINITION (with body), not a declaration/prototype.
3. If not found or only a prototype exists, set found=false.

RESPONSE SCHEMA:
{
    "found": boolean,
    "start_line": integer,
    "end_line": integer,
    "signature": "string",
    "reasoning": "string"
}"""

FIND_FUNCTION_USER_TEMPLATE = """FIND FUNCTION: {function_name}

SOURCE CODE:
```c
{numbered_content}
```

Respond with valid JSON object only:"""

# Retry-specific instruction templates
# Optimized for smaller local LLMs (e.g., Qwen Coder 32B)
# Use concrete, specific instructions instead of abstract concepts
RETRY_INSTRUCTIONS = {
    1: """⚠️ RETRY ATTEMPT #1
Previous solution failed. Try these specific changes:
- Change variable names (e.g., 'i' → 'index')
- Split complex expressions into multiple lines
- Use explicit type casts if needed
- Check for off-by-one errors in loops""",
    
    2: """⚠️⚠️ RETRY ATTEMPT #2
Still failing. Apply these fixes:
- Break down the function into smaller steps
- Add intermediate variables with clear names
- Ensure all return paths are covered
- Double-check MISRA rule specifics"""
}


def get_retry_instruction(retry_count: int) -> str:
    """Get progressive instruction based on retry count."""
    if retry_count == 0:
        return ""
    return RETRY_INSTRUCTIONS.get(retry_count, RETRY_INSTRUCTIONS[2])

