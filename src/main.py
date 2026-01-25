"""Main entry point for MISRA C Refactoring Agent."""

import sys
from pathlib import Path
from .config import settings
from .agent.state import initialize_state, load_state, save_logs, save_state
from .agent.graph import build_agent_graph
from .tools import parse_violations_csv


def print_banner():
    """Print startup banner."""
    print("""
============================================================
        MISRA C Refactoring Agent (Powered by Ollama)
============================================================
""")


def print_summary(state):
    """Print execution summary."""
    total = len(state["logs"])
    success = sum(1 for log in state["logs"] if log.status == "success")
    skipped_unsafe = sum(1 for log in state["logs"] if log.status == "skipped_unsafe")
    failed = sum(1 for log in state["logs"] if log.status == "failed")
    
    print("\n" + "="*60)
    print("EXECUTION SUMMARY")
    print("="*60)
    print(f"Total violations processed: {total}")
    print(f"  [OK] Successfully fixed: {success}")
    print(f"  [SKIP] Skipped (unsafe): {skipped_unsafe}")
    print(f"  [FAIL] Failed: {failed}")
    print(f"\nLogs saved to: {settings.log_file}")
    print(f"State saved to: {settings.state_file}")
    print("="*60)


def main():
    """Main execution function."""
    print_banner()
    
    # Check if resuming from previous state
    state_file = Path(settings.state_file)
    
    if state_file.exists():
        print(f"[INFO] Found existing state file: {settings.state_file}")
        response = input("Resume from previous session? (y/n): ").strip().lower()
        
        if response == 'y':
            print("[INFO] Resuming from previous state...")
            try:
                state = load_state(settings.state_file)
                print(f"[INFO] Loaded {len(state['violations_queue'])} remaining violations")
            except Exception as e:
                print(f"[ERROR] Failed to load state: {e}")
                print("[INFO] Starting fresh session...")
                state = None
        else:
            print("[INFO] Starting fresh session...")
            state = None
    else:
        state = None
    
    # Initialize new state if not resuming
    if state is None:
        print(f"[INFO] Loading violations from: {settings.violations_csv}")
        
        try:
            violations = parse_violations_csv(settings.violations_csv)
            print(f"[INFO] Loaded {len(violations)} violations")
            
            if not violations:
                print("[ERROR] No violations found in CSV")
                return
            
            state = initialize_state(violations)
            
        except FileNotFoundError as e:
            print(f"[ERROR] {e}")
            print(f"\nPlease create a violations.csv file with the following format:")
            print("file_path,function_name,violation_description")
            print("src/driver/uart.c,uart_init,MISRA C:2012 Rule 8.4 - Missing function prototype")
            return
        except Exception as e:
            print(f"[ERROR] Failed to parse violations CSV: {e}")
            return
    
    # Verify project root exists
    project_root = settings.get_project_root_path()
    if not project_root.exists():
        print(f"[ERROR] Project root not found: {project_root}")
        print(f"\nPlease set PROJECT_ROOT in .env to point to your C project directory")
        return
    
    print(f"[INFO] Project root: {project_root}")
    print(f"[INFO] Using Ollama model: {settings.ollama_model}")
    print(f"[INFO] Max retries per violation: {settings.max_retries}")
    
    # Build and run agent
    print("\n[INFO] Building agent workflow...")
    
    try:
        graph = build_agent_graph()
        
        print("[INFO] Starting agent execution...\n")
        
        # Run the graph with recursion limit
        try:
            final_state = graph.invoke(state, {"recursion_limit": 50})
        except Exception as e:
            # Check for GraphRecursionError
            from langgraph.errors import GraphRecursionError
            
            if isinstance(e, GraphRecursionError):
                print(f"\n[ERROR] GraphRecursionError: {e}")
                print("[SKIP] Infinite retry loop detected - skipping problematic violation")
                
                # Log the failure for current violation
                if state.get("current_violation"):
                    from .agent.state import RefactoringLog
                    log = RefactoringLog.create(
                        file_path=state["current_violation"].file_path,
                        function_name=state["current_violation"].function_name,
                        violation=state["current_violation"].violation_description,
                        original_code="",
                        modified_code="",
                        reason=f"GraphRecursionError: Exceeded retry limit",
                        status="failed",
                        retry_count=state.get("retry_count", 0)
                    )
                    state["logs"].append(log)
                    
                    # Move to next violation
                    if state["violations_queue"]:
                        state["violations_queue"] = state["violations_queue"][1:]
                
                # Save current progress
                save_logs(state["logs"], settings.log_file)
                save_state(state, settings.state_file)
                
                print(f"[INFO] Progress saved. {len(state['violations_queue'])} violations remaining.")
                print("[INFO] Please restart to continue with remaining violations.\n")
                
                final_state = state
            else:
                # Re-raise other exceptions
                raise
        
        # Save final logs
        print(f"\n[INFO] Saving logs to: {settings.log_file}")
        save_logs(final_state["logs"], settings.log_file)
        
        # Print summary
        print_summary(final_state)
        
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Execution interrupted by user")
        print(f"[INFO] State saved to: {settings.state_file}")
        print("[INFO] Run again to resume from this point")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Agent execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
