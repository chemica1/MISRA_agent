"""File operations with security measures."""

import os
import shutil
from pathlib import Path
from typing import Optional


class SecurityError(Exception):
    """Raised when a security violation is detected."""
    pass


def validate_path(file_path: str, project_root: str) -> Path:
    """
    Validate file path to prevent path traversal attacks.
    
    Args:
        file_path: File path to validate
        project_root: Project root directory
        
    Returns:
        Resolved Path object
        
    Raises:
        SecurityError: If path traversal is detected
    """
    # Resolve to absolute paths
    root = Path(project_root).resolve()
    target = Path(file_path).resolve()
    
    # Check if target is within project root using commonpath
    try:
        common = Path(os.path.commonpath([root, target]))
        if common != root:
            raise SecurityError(f"Path traversal detected: {file_path} is outside project root")
    except ValueError:
        # Different drives on Windows
        raise SecurityError(f"Path traversal detected: {file_path} is on different drive")
    
    return target


def backup_file(file_path: Path) -> Path:
    """
    Create backup of file with .bak extension.
    Only creates backup if one doesn't already exist to preserve original content.
    
    Args:
        file_path: Path to file to backup
        
    Returns:
        Path to backup file
    """
    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
    
    # Only create backup if it doesn't already exist
    # This preserves the original file content across multiple modifications
    if file_path.exists() and not backup_path.exists():
        shutil.copy2(file_path, backup_path)
        print(f"[BACKUP] Created: {backup_path}")
    elif backup_path.exists():
        print(f"[BACKUP] Already exists (preserving original): {backup_path}")
    
    return backup_path


def read_file(file_path: Path, project_root: str) -> str:
    """
    Read file content with security validation.
    
    Args:
        file_path: Path to file
        project_root: Project root directory
        
    Returns:
        File content as string
        
    Raises:
        SecurityError: If path validation fails
        FileNotFoundError: If file doesn't exist
    """
    validated_path = validate_path(str(file_path), project_root)
    
    if not validated_path.exists():
        raise FileNotFoundError(f"File not found: {validated_path}")
    
    with open(validated_path, "r", encoding="utf-8", errors='replace') as f:
        return f.read()


def write_file(file_path: Path, content: str, project_root: str, create_backup: bool = True) -> None:
    """
    Write content to file with security validation and optional backup.
    
    Args:
        file_path: Path to file
        content: Content to write
        project_root: Project root directory
        create_backup: Whether to create backup before writing
        
    Raises:
        SecurityError: If path validation fails
    """
    validated_path = validate_path(str(file_path), project_root)
    
    # Create backup if file exists and backup is requested
    if create_backup and validated_path.exists():
        backup_file(validated_path)
    
    # Ensure parent directory exists
    validated_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write content
    with open(validated_path, "w", encoding="utf-8", errors='replace') as f:
        f.write(content)
    
    print(f"[WRITE] Updated: {validated_path}")


def find_file_in_project(relative_path: str, project_root: str) -> Optional[Path]:
    """
    Find file in project by relative path.
    
    Args:
        relative_path: Relative path from CSV
        project_root: Project root directory
        
    Returns:
        Absolute Path if found, None otherwise
    """
    # Try direct path
    direct_path = Path(project_root) / relative_path
    if direct_path.exists():
        return validate_path(str(direct_path), project_root)
    
    # Try searching in project root
    root = Path(project_root)
    filename = Path(relative_path).name
    
    for file in root.rglob(filename):
        try:
            validated = validate_path(str(file), project_root)
            return validated
        except SecurityError:
            continue
    
    return None
