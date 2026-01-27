"""LangGraph workflow definition for MISRA C Refactoring Agent."""

from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import (
    load_violations_node,
    read_file_node,
    extract_function_node,
    decide_action_node,
    validate_modification_node,
    apply_modification_node,
    log_failure_node,
    next_violation_node
)
from ..config import settings


def should_retry(state: AgentState) -> str:
    """
    Routing function: decide whether to retry, skip, or proceed.
    
    Returns:
        "retry" - if error and retry_count < max_retries
        "skip" - if error and retry_count >= max_retries
        "apply" - if no error and modification is ready
        "next" - if completed
    """
    if state["status"] == "completed":
        return "end"
    
    # Check if we have an error
    if state["error_message"]:
        # Max retries reached - log and skip
        if state["retry_count"] >= settings.max_retries:
            print(f"[MAX_RETRIES] Reached max retries ({settings.max_retries}), skipping violation")
            return "skip"
        # Still have retries left
        return "retry"
    
    # Check if modification is ready
    if state["modified_code"]:
        return "apply"
    
    # Default: continue to next step
    return "next"


def should_continue(state: AgentState) -> str:
    """
    Routing after applying modification or moving to next violation.
    
    Returns:
        "next" - move to next violation
        "end" - all done
    """
    if state["status"] == "completed":
        return "end"
    
    # Check if there are more violations to process
    if not state["violations_queue"]:
        return "end"
    
    return "next"


def increment_retry(state: AgentState) -> AgentState:
    """Increment retry counter."""
    state["retry_count"] += 1
    print(f"[RETRY] Attempt {state['retry_count']}/{settings.max_retries}")
    return state


def build_agent_graph() -> StateGraph:
    """
    Build the LangGraph workflow.
    
    Graph structure:
    
    START
      ↓
    load_violations
      ↓
    read_file
      ↓
    extract_function
      ↓
    decide_action ←──────┐ (retry loop)
      ↓                  │
    validate_modification│
      ↓                  │
    [routing]            │
      ├─ error? ─────────┘ (if retry_count < max)
      ├─ max retries? → log_failure → next_violation
      └─ success? → apply_modification → next_violation
                                           ↓
                                      load_violations (loop)
                                           ↓
                                          END
    """
    
    # Create graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("load_violations", load_violations_node)
    workflow.add_node("read_file", read_file_node)
    workflow.add_node("extract_function", extract_function_node)
    workflow.add_node("decide_action", decide_action_node)
    workflow.add_node("validate_modification", validate_modification_node)
    workflow.add_node("apply_modification", apply_modification_node)
    workflow.add_node("log_failure", log_failure_node)
    workflow.add_node("next_violation", next_violation_node)
    workflow.add_node("increment_retry", increment_retry)
    
    # Set entry point
    workflow.set_entry_point("load_violations")
    
    # Add edges
    workflow.add_edge("load_violations", "read_file")
    workflow.add_edge("read_file", "extract_function")
    workflow.add_edge("extract_function", "decide_action")
    workflow.add_edge("decide_action", "validate_modification")
    
    # Conditional routing after validation
    workflow.add_conditional_edges(
        "validate_modification",
        should_retry,
        {
            "retry": "increment_retry",
            "skip": "log_failure",
            "apply": "apply_modification",
            "next": "next_violation",
            "end": END
        }
    )
    
    # Retry loop
    workflow.add_edge("increment_retry", "decide_action")
    
    # After failure logging
    workflow.add_edge("log_failure", "next_violation")
    
    # After successful application
    workflow.add_edge("apply_modification", "next_violation")
    
    # Loop back or end
    workflow.add_conditional_edges(
        "next_violation",
        should_continue,
        {
            "next": "load_violations",
            "end": END
        }
    )
    
    return workflow.compile()
