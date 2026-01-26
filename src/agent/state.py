"""State management for the MISRA C Refactoring Agent."""

from typing import TypedDict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import json
from pathlib import Path


class Violation(BaseModel):
    """Represents a single MISRA C violation from CSV."""
    file_path: str
    function_name: str
    violation_description: str
    
    class Config:
        frozen = True  # Immutable


class RefactoringLog(BaseModel):
    """Log entry for a refactoring action."""
    timestamp: str
    file_path: str
    function_name: str
    violation: str
    original_code: str
    modified_code: str
    reason: str
    status: str  # "success" | "failed" | "skipped_unsafe" | "already_compliant"
    retry_count: int
    
    @classmethod
    def create(
        cls,
        file_path: str,
        function_name: str,
        violation: str,
        original_code: str,
        modified_code: str,
        reason: str,
        status: str,
        retry_count: int
    ):
        """Create a new log entry with current timestamp."""
        return cls(
            timestamp=datetime.now().isoformat(),
            file_path=file_path,
            function_name=function_name,
            violation=violation,
            original_code=original_code,
            modified_code=modified_code,
            reason=reason,
            status=status,
            retry_count=retry_count
        )


class AgentState(TypedDict):
    """State for the LangGraph agent."""
    violations_queue: List[Violation]
    current_violation: Optional[Violation]
    file_content: Optional[str]
    function_code: Optional[str]  # Extracted function code
    modified_code: Optional[str]
    retry_count: int
    error_message: Optional[str]
    logs: List[RefactoringLog]
    status: str  # "processing" | "success" | "failed" | "completed"


def save_state(state: AgentState, file_path: str) -> None:
    """Save agent state to JSON file for persistence."""
    # Convert to serializable format
    serializable_state = {
        "violations_queue": [v.model_dump() for v in state["violations_queue"]],
        "current_violation": state["current_violation"].model_dump() if state["current_violation"] else None,
        "file_content": state["file_content"],
        "function_code": state["function_code"],
        "modified_code": state["modified_code"],
        "retry_count": state["retry_count"],
        "error_message": state["error_message"],
        "logs": [log.model_dump() for log in state["logs"]],
        "status": state["status"]
    }
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(serializable_state, f, indent=2, ensure_ascii=False)


def load_state(file_path: str) -> AgentState:
    """Load agent state from JSON file."""
    with open(file_path, "r", encoding="utf-8", errors='replace') as f:
        data = json.load(f)
    
    return AgentState(
        violations_queue=[Violation(**v) for v in data["violations_queue"]],
        current_violation=Violation(**data["current_violation"]) if data["current_violation"] else None,
        file_content=data["file_content"],
        function_code=data["function_code"],
        modified_code=data["modified_code"],
        retry_count=data["retry_count"],
        error_message=data["error_message"],
        logs=[RefactoringLog(**log) for log in data["logs"]],
        status=data["status"]
    )


def initialize_state(violations: List[Violation]) -> AgentState:
    """Initialize a new agent state."""
    return AgentState(
        violations_queue=violations,
        current_violation=None,
        file_content=None,
        function_code=None,
        modified_code=None,
        retry_count=0,
        error_message=None,
        logs=[],
        status="processing"
    )


def append_logs(new_logs: List[RefactoringLog], file_path: str) -> None:
    """
    Append new logs to the existing JSON log file.
    
    Reads existing logs from the file (if it exists), appends the new logs,
    and writes the combined list back to the file.
    """
    if not new_logs:
        return
        
    existing_logs = []
    path = Path(file_path)
    
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    existing_logs = json.loads(content)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[WARNING] Could not read existing logs from {file_path}: {e}")
            # If file is corrupted, we'll overwrite (or could backup, but for now we follow simple logic)
    
    # Combine and save
    all_logs = existing_logs + [log.model_dump() for log in new_logs]
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(all_logs, f, indent=2, ensure_ascii=False)
