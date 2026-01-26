"""LangGraph nodes for the MISRA C Refactoring Agent."""

from typing import Any
from .state import AgentState, Violation, RefactoringLog, save_state
from ..tools import (
    find_file_in_project,
    read_file,
    write_file,
    find_function,
    validate_c_syntax,
    check_semantic_preservation,
    OllamaClient,
    SecurityError
)
from ..config import settings


def load_violations_node(state: AgentState) -> AgentState:
    """
    Initial node: Load next violation from queue.
    
    Load next violation from queue and initialize state.
    """
    print("\n" + "="*60)
    
    # All tasks complete if queue is empty
    if not state["violations_queue"]:
        print("[COMPLETE] All violations processed")
        state["status"] = "completed"
        return state
    
    # Get next violation from queue
    current = state["violations_queue"][0]
    state["current_violation"] = current
    state["retry_count"] = 0
    state["error_message"] = None
    state["file_content"] = None
    state["function_code"] = None
    state["modified_code"] = None
    
    print(f"[PROCESSING] {current.file_path} :: {current.function_name}")
    print(f"[VIOLATION] {current.violation_description}")
    
    return state


def read_file_node(state: AgentState) -> AgentState:
    """
    Read the file containing the violation.
    
    Find and read the file where the violation occurred.
    """
    violation = state["current_violation"]
    if not violation:
        state["error_message"] = "No current violation"
        return state
    
    print(f"[ACTION] Reading file: {violation.file_path}")
    
    try:
        # Find file in project
        project_root = settings.get_project_root_path()
        file_path = find_file_in_project(violation.file_path, str(project_root))
        
        if not file_path:
            state["error_message"] = f"File not found: {violation.file_path}"
            print(f"[ERROR] {state['error_message']}")
            return state
        
        # Read file content
        content = read_file(file_path, str(project_root))
        state["file_content"] = content
        
        print(f"[OBSERVATION] File loaded: {len(content)} characters")
        
    except (SecurityError, FileNotFoundError) as e:
        state["error_message"] = str(e)
        print(f"[ERROR] {state['error_message']}")
    
    return state


def extract_function_node(state: AgentState) -> AgentState:
    """
    Extract the function code from the file.
    """
    violation = state["current_violation"]
    if not violation or not state["file_content"]:
        state["error_message"] = "Missing file content"
        return state
    
    print(f"[ACTION] Extracting function: {violation.function_name}")
    
    try:
        func_info = find_function(state["file_content"], violation.function_name)
        
        if not func_info:
            state["error_message"] = f"Function '{violation.function_name}' not found in file"
            print(f"[ERROR] {state['error_message']}")
            return state
        
        state["function_code"] = func_info.full_code
        print(f"[OBSERVATION] Function found at lines {func_info.start_line}-{func_info.end_line}")
        
    except Exception as e:
        state["error_message"] = f"Function extraction failed: {e}"
        print(f"[ERROR] {state['error_message']}")
    
    return state


def decide_action_node(state: AgentState) -> AgentState:
    """
    LLM decides on refactoring action.
    """
    violation = state["current_violation"]
    if not violation or not state["function_code"]:
        state["error_message"] = "Missing function code"
        return state
    
    print(f"[THINKING] Analyzing MISRA violation...")
    
    # Initialize Ollama client
    llm = OllamaClient(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        timeout=settings.ollama_timeout
    )
    
    # Get LLM decision - only wrap the actual LLM call in try-except
    try:
        response = llm.decide_action(
            violation=violation.violation_description,
            function_code=state["function_code"],
            error_feedback=state["error_message"],
            temperature=0.7
        )
    except ValueError as e:
        # JSON parsing or validation error - will trigger retry
        state["error_message"] = str(e)
        print(f"[ERROR] {state['error_message']}")
        return state
    except (ConnectionError, TimeoutError) as e:
        state["error_message"] = f"Ollama error: {e}"
        print(f"[ERROR] {state['error_message']}")
        return state
    
    # Process the response (outside of exception handling)
    print(f"[THINKING] {response.reasoning}")
    
    # Check safety assessment
    if not response.is_safe:
        safety_msg = f"Unsafe modification detected: {response.safety_concerns or 'requires global changes'}"
        state["error_message"] = safety_msg
        print(f"[SAFETY RISK] {safety_msg}")
        print(f"[SKIP] Will not apply risky changes")
        return state
    
    # Check if code is already compliant
    if response.action == "already_compliant":
        state["error_message"] = f"Already compliant: {response.reasoning}"
        print(f"[ALREADY COMPLIANT] {response.reasoning}")
        return state
    
    if response.action == "skip":
        state["error_message"] = f"LLM decided to skip: {response.reasoning}"
        print(f"[SKIP] {state['error_message']}")
        return state
    
    if response.action == "modify_code" and response.modified_code:
        state["modified_code"] = response.modified_code
        state["error_message"] = None  # Clear previous errors
        print(f"[ACTION] Generated fix: {response.reason or 'MISRA compliance'}")
    else:
        state["error_message"] = "LLM did not provide modified code"
        print(f"[ERROR] {state['error_message']}")
    
    return state


def validate_modification_node(state: AgentState) -> AgentState:
    """
    Validate the modified code using deterministic checks (no LLM).
    """
    if not state["modified_code"]:
        return state
    
    print(f"[OBSERVATION] Validating modified code...")
    
    # Syntax validation (fast, deterministic)
    is_valid, syntax_error = validate_c_syntax(state["modified_code"])
    if not is_valid:
        state["error_message"] = f"Syntax error: {syntax_error}"
        print(f"[ERROR] {state['error_message']}")
        return state
    
    print(f"[OBSERVATION] Syntax validation passed [OK]")
    
    # Semantic preservation check
    if state["function_code"]:
        is_preserved, warning = check_semantic_preservation(
            state["function_code"],
            state["modified_code"]
        )
        
        if warning:
            print(f"[WARNING] {warning}")
    
    return state


def _minimize_code_diff(original: str, modified: str) -> tuple[str, str]:
    """
    Helper to extract only changed lines for logging.
    Returns (minimized_original, minimized_modified).
    """
    import difflib
    
    orig_lines = original.splitlines()
    mod_lines = modified.splitlines()
    
    matcher = difflib.SequenceMatcher(None, orig_lines, mod_lines)
    
    min_orig = []
    min_mod = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
            
        if tag in ('replace', 'delete'):
            min_orig.extend(orig_lines[i1:i2])
        if tag in ('replace', 'insert'):
            min_mod.extend(mod_lines[j1:j2])
            
    # If no changes found (unlikely if we are here), return full or empty
    if not min_orig and not min_mod:
        return "(no changes identified)", "(no changes identified)"
        
    return "\n".join(min_orig), "\n".join(min_mod)


def apply_modification_node(state: AgentState) -> AgentState:
    """
    Apply the modification to the file.
    """
    violation = state["current_violation"]
    if not violation or not state["modified_code"] or not state["file_content"]:
        return state
    
    print(f"[ACTION] Applying modification with backup...")
    
    try:
        # Replace function in file content
        func_info = find_function(state["file_content"], violation.function_name)
        if not func_info:
            state["error_message"] = "Cannot locate function for replacement"
            return state
        
        # Replace the function code
        lines = state["file_content"].split('\n')
        new_lines = (
            lines[:func_info.start_line - 1] +
            state["modified_code"].split('\n') +
            lines[func_info.end_line:]
        )
        new_content = '\n'.join(new_lines)
        
        # Write to file (with backup)
        project_root = settings.get_project_root_path()
        file_path = find_file_in_project(violation.file_path, str(project_root))
        
        if file_path:
            write_file(file_path, new_content, str(project_root), create_backup=True)
            print(f"[SUCCESS] Fixed MISRA violation")
            
            # Minimize log content
            min_orig, min_mod = _minimize_code_diff(
                state["function_code"] or "", 
                state["modified_code"]
            )
            
            # Create log entry
            log = RefactoringLog.create(
                file_path=violation.file_path,
                function_name=violation.function_name,
                violation=violation.violation_description,
                original_code=min_orig,
                modified_code=min_mod,
                reason="MISRA C compliance fix",
                status="success",
                retry_count=state["retry_count"]
            )
            state["logs"].append(log)
        
    except Exception as e:
        state["error_message"] = f"Failed to apply modification: {e}"
        print(f"[ERROR] {state['error_message']}")
    
    return state


def log_failure_node(state: AgentState) -> AgentState:
    """
    Log a failed refactoring attempt.
    """
    violation = state["current_violation"]
    if not violation:
        return state
    
    # Determine if this is a safety skip, already compliant, or a failure
    error_msg = state["error_message"] or "Unknown error"
    is_safety_skip = "Unsafe modification detected" in error_msg or "safety" in error_msg.lower()
    is_already_compliant = "Already compliant" in error_msg
    
    if is_already_compliant:
        print(f"[ALREADY_COMPLIANT] {error_msg}")
        status = "already_compliant"
    elif is_safety_skip:
        print(f"[SKIPPED_UNSAFE] {error_msg}")
        status = "skipped_unsafe"
    else:
        print(f"[FAILED] Could not fix violation after {state['retry_count']} attempts")
        status = "failed"
    
    # For failures, still minimize if there was a modified_code (for retry cases)
    original_to_log = state["function_code"] or ""
    modified_to_log = ""
    
    if state.get("modified_code"):
        # If there was an attempted modification, show the diff
        original_to_log, modified_to_log = _minimize_code_diff(
            state["function_code"] or "",
            state["modified_code"]
        )
    elif original_to_log:
        # If no modification was attempted, just show first few lines of original
        lines = original_to_log.splitlines()
        if len(lines) > 3:
            original_to_log = "\n".join(lines[:3]) + "\n... (truncated)"
    
    log = RefactoringLog.create(
        file_path=violation.file_path,
        function_name=violation.function_name,
        violation=violation.violation_description,
        original_code=original_to_log,
        modified_code=modified_to_log,
        reason=error_msg,
        status=status,
        retry_count=state["retry_count"]
    )
    state["logs"].append(log)
    
    return state


def next_violation_node(state: AgentState) -> AgentState:
    """
    Move to next violation in queue.
    """
    if state["violations_queue"]:
        state["violations_queue"] = state["violations_queue"][1:]
    
    # Save state for persistence
    save_state(state, settings.state_file)
    
    # Save logs incrementally after each violation
    from .state import save_logs
    save_logs(state["logs"], settings.log_file)
    
    return state
