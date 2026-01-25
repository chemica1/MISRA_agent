"""Main entry point for MISRA C Refactoring Agent."""

import sys
import traceback
from pathlib import Path

# LangGraph의 GraphRecursionError를 상단에서 import
from langgraph.errors import GraphRecursionError

# 내부 모듈
from .config import settings
from .agent.state import (
    initialize_state,
    load_state,
    save_logs,
    save_state,
    RefactoringLog,
    AgentState
)
from .agent.graph import build_agent_graph
from .tools import parse_violations_csv

# Constants
RECURSION_LIMIT = 50  # Maximum recursion depth for retry loops


def print_banner():
    """Print startup banner."""
    print("""
============================================================
        MISRA C Refactoring Agent (Powered by Ollama)
============================================================
""")


def print_summary(state: AgentState):
    """Print execution summary.
    
    Args:
        state: Final agent state (includes logs)
    """
    total = len(state["logs"])
    success = sum(1 for log in state["logs"] if log.status == "success")
    skipped_unsafe = sum(1 for log in state["logs"] if log.status == "skipped_unsafe")
    already_compliant = sum(1 for log in state["logs"] if log.status == "already_compliant")
    failed = sum(1 for log in state["logs"] if log.status == "failed")
    
    print("\n" + "="*60)
    print("EXECUTION SUMMARY")
    print("="*60)
    print(f"Total violations processed: {total}")
    print(f"  [OK] Successfully fixed: {success}")
    print(f"  [COMPLIANT] Already compliant: {already_compliant}")
    print(f"  [SKIP] Skipped (unsafe): {skipped_unsafe}")
    print(f"  [FAIL] Failed: {failed}")
    print(f"\nLogs saved to: {settings.log_file}")
    print(f"State saved to: {settings.state_file}")
    print("="*60)


def _handle_recursion_error(state: AgentState) -> AgentState:
    """Handle GraphRecursionError when it occurs.
    
    When recursion limit is exceeded due to infinite retry loop:
    1. Log current violation as failed
    2. Move to next violation
    3. Return updated state (loop will continue automatically)
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state
    """
    print("\n[ERROR] GraphRecursionError: Infinite retry loop detected")
    print("[SKIP] Skipping problematic violation and continuing...")
    
    # Log current violation as failed
    if state.get("current_violation"):
        log = RefactoringLog.create(
            file_path=state["current_violation"].file_path,
            function_name=state["current_violation"].function_name,
            violation=state["current_violation"].violation_description,
            original_code="",
            modified_code="",
            reason="GraphRecursionError: Exceeded retry limit",
            status="failed",
            retry_count=state.get("retry_count", 0)
        )
        state["logs"].append(log)
        
        # Move to next violation
        if state["violations_queue"]:
            state["violations_queue"] = state["violations_queue"][1:]
    
    # Reset state for next violation
    state["current_violation"] = None
    state["retry_count"] = 0
    state["error_message"] = None
    state["file_content"] = None
    state["function_code"] = None
    state["modified_code"] = None
    
    print(f"[INFO] {len(state['violations_queue'])} violations remaining. Continuing...\n")
    
    return state


def _load_or_initialize_state():
    """Load from previous session or initialize new state.
    
    Returns:
        AgentState or None (on error)
    """
    state_file = Path(settings.state_file)
    
    # Check if previous state file exists
    if state_file.exists():
        print(f"[INFO] Found existing state file: {settings.state_file}")
        response = input("Resume from previous session? (y/n): ").strip().lower()
        
        if response == 'y':
            print("[INFO] Resuming from previous state...")
            try:
                state = load_state(settings.state_file)
                print(f"[INFO] Loaded {len(state['violations_queue'])} remaining violations")
                return state
            except Exception as e:
                print(f"[ERROR] Failed to load state: {e}")
                print("[INFO] Starting fresh session...")
    
    # Start new session
    print(f"[INFO] Loading violations from: {settings.violations_csv}")
    
    try:
        violations = parse_violations_csv(settings.violations_csv)
        print(f"[INFO] Loaded {len(violations)} violations")
        
        if not violations:
            print("[ERROR] No violations found in CSV")
            return None
        
        return initialize_state(violations)
        
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        print("\nPlease create a violations.csv file with the following format:")
        print("file_path,function_name,violation_description")
        print("src/driver/uart.c,uart_init,MISRA C:2012 Rule 8.4 - Missing function prototype")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to parse violations CSV: {e}")
        return None


def main():
    """Main execution function."""
    print_banner()
    
    # Load or initialize state
    state = _load_or_initialize_state()
    if state is None:
        return
    
    # Verify project root path
    project_root = settings.get_project_root_path()
    if not project_root.exists():
        print(f"[ERROR] Project root not found: {project_root}")
        print("\nPlease set PROJECT_ROOT in .env to point to your C project directory")
        return
    
    print(f"[INFO] Project root: {project_root}")
    print(f"[INFO] Using Ollama model: {settings.ollama_model}")
    print(f"[INFO] Max retries per violation: {settings.max_retries}")
    
    # Build and run agent workflow
    print("\n[INFO] Building agent workflow...")
    
    try:
        graph = build_agent_graph()
        
        print("[INFO] Starting agent execution...\n")
        
        # Process violations with error recovery
        # Continue even if GraphRecursionError occurs for a specific violation
        current_state = state
        while current_state["violations_queue"]:
            try:
                # Run graph with recursion limit for current violation
                current_state = graph.invoke(current_state, {"recursion_limit": RECURSION_LIMIT})
                
                # Check if all violations are processed
                if current_state["status"] == "completed":
                    break
                    
            except GraphRecursionError as e:
                # Skip current violation and continue with next
                print(f"\n[ERROR] GraphRecursionError: {e}")
                current_state = _handle_recursion_error(current_state)
                
                # If queue is empty after handling error, we're done
                if not current_state["violations_queue"]:
                    break
                
                print(f"[INFO] Continuing with {len(current_state['violations_queue'])} remaining violations...\n")
        
        final_state = current_state
        
        # Save final logs
        print(f"\n[INFO] Saving logs to: {settings.log_file}")
        save_logs(final_state["logs"], settings.log_file)
        
        # Print summary
        print_summary(final_state)
        
    except KeyboardInterrupt:
        # User interrupted with Ctrl+C
        print("\n\n[INTERRUPTED] Execution interrupted by user")
        print(f"[INFO] State saved to: {settings.state_file}")
        print("[INFO] Run again to resume from this point")
        sys.exit(0)
    except Exception as e:
        # Unexpected error occurred
        print(f"\n[ERROR] Agent execution failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
