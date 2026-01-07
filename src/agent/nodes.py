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
    """
    print("\n" + "="*60)
    
    if not state["violations_queue"]:
        print("[COMPLETE] All violations processed")
        state["status"] = "completed"
        return state
    
    # Get next violation
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
    
    try:
        # Initialize Ollama client
        llm = OllamaClient(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            timeout=settings.ollama_timeout
        )
        
        # Get LLM decision
        response = llm.decide_action(
            violation=violation.violation_description,
            function_code=state["function_code"],
            error_feedback=state["error_message"]
        )
        
        print(f"[THINKING] {response.reasoning}")
        
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
        
    except ValueError as e:
        # JSON parsing or validation error - will trigger retry
        state["error_message"] = str(e)
        print(f"[ERROR] {state['error_message']}")
    except (ConnectionError, TimeoutError) as e:
        state["error_message"] = f"Ollama error: {e}"
        print(f"[ERROR] {state['error_message']}")
    
    return state


def validate_modification_node(state: AgentState) -> AgentState:
    """
    Validate the modified code.
    """
    if not state["modified_code"]:
        return state
    
    print(f"[OBSERVATION] Validating modified code...")
    
    # Syntax validation
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
            
            # Create log entry
            log = RefactoringLog.create(
                file_path=violation.file_path,
                function_name=violation.function_name,
                violation=violation.violation_description,
                original_code=state["function_code"] or "",
                modified_code=state["modified_code"],
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
    
    print(f"[FAILED] Could not fix violation after {state['retry_count']} attempts")
    
    log = RefactoringLog.create(
        file_path=violation.file_path,
        function_name=violation.function_name,
        violation=violation.violation_description,
        original_code=state["function_code"] or "",
        modified_code="",
        reason=state["error_message"] or "Unknown error",
        status="failed",
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
    
    return state
