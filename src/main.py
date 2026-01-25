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

# 상수 정의
RECURSION_LIMIT = 50  # 재시도 루프의 최대 깊이


def print_banner():
    """시작 배너 출력."""
    print("""
============================================================
        MISRA C Refactoring Agent (Powered by Ollama)
============================================================
""")


def print_summary(state: AgentState):
    """실행 요약 출력.
    
    Args:
        state: 최종 agent state (logs 포함)
    """
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


def _handle_recursion_error(state: AgentState) -> AgentState:
    """GraphRecursionError 발생 시 처리.
    
    무한 재시도 루프로 인해 recursion limit을 초과한 경우:
    1. 현재 violation을 failed로 로그
    2. 다음 violation으로 이동
    3. 진행 상황 저장
    
    Args:
        state: 현재 agent state
        
    Returns:
        업데이트된 state
    """
    print("\n[ERROR] GraphRecursionError: Infinite retry loop detected")
    print("[SKIP] Skipping problematic violation and continuing...")
    
    # 현재 violation을 실패로 기록
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
        
        # 다음 violation으로 이동
        if state["violations_queue"]:
            state["violations_queue"] = state["violations_queue"][1:]
    
    # 진행 상황 저장
    save_logs(state["logs"], settings.log_file)
    save_state(state, settings.state_file)
    
    print(f"[INFO] Progress saved. {len(state['violations_queue'])} violations remaining.")
    print("[INFO] Please restart to continue with remaining violations.\n")
    
    return state


def _load_or_initialize_state():
    """이전 세션에서 복원하거나 새로운 state 초기화.
    
    Returns:
        AgentState 또는 None (에러 발생 시)
    """
    state_file = Path(settings.state_file)
    
    # 이전 state 파일이 있는지 확인
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
    
    # 새로운 세션 시작
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
    """메인 실행 함수."""
    print_banner()
    
    # State 로드 또는 초기화
    state = _load_or_initialize_state()
    if state is None:
        return
    
    # 프로젝트 루트 경로 검증
    project_root = settings.get_project_root_path()
    if not project_root.exists():
        print(f"[ERROR] Project root not found: {project_root}")
        print("\nPlease set PROJECT_ROOT in .env to point to your C project directory")
        return
    
    print(f"[INFO] Project root: {project_root}")
    print(f"[INFO] Using Ollama model: {settings.ollama_model}")
    print(f"[INFO] Max retries per violation: {settings.max_retries}")
    
    # Agent 워크플로우 빌드 및 실행
    print("\n[INFO] Building agent workflow...")
    
    try:
        graph = build_agent_graph()
        
        print("[INFO] Starting agent execution...\n")
        
        # Graph 실행 (recursion limit 설정)
        try:
            final_state = graph.invoke(state, {"recursion_limit": RECURSION_LIMIT})
        except GraphRecursionError as e:
            # 재시도 루프 초과 시 현재 violation을 스킵하고 진행 상황 저장
            final_state = _handle_recursion_error(state)
        
        # 최종 로그 저장
        print(f"\n[INFO] Saving logs to: {settings.log_file}")
        save_logs(final_state["logs"], settings.log_file)
        
        # 실행 요약 출력
        print_summary(final_state)
        
    except KeyboardInterrupt:
        # 사용자가 Ctrl+C로 중단한 경우
        print("\n\n[INTERRUPTED] Execution interrupted by user")
        print(f"[INFO] State saved to: {settings.state_file}")
        print("[INFO] Run again to resume from this point")
        sys.exit(0)
    except Exception as e:
        # 예상치 못한 에러 발생
        print(f"\n[ERROR] Agent execution failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
