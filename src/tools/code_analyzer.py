"""C code analysis and function extraction."""

import re
from typing import Optional, Tuple
from pydantic import BaseModel


class FunctionInfo(BaseModel):
    """Information about a C function."""
    name: str
    start_line: int
    end_line: int
    full_code: str
    signature: str


def find_function(file_content: str, function_name: str) -> Optional[FunctionInfo]:
    """
    Find function in C source code using smart chunking.
    Uses regex pre-filter + LLM verification on small chunks for large files.
    
    Args:
        file_content: Full file content
        function_name: Name of function to find
        
    Returns:
        FunctionInfo if found, None otherwise
    """
    from .llm_client import OllamaClient
    from ..config import settings
    
    lines = file_content.split('\n')
    
    # Step 1: Quick regex scan to find approximate location(s)
    pattern = rf'\b{re.escape(function_name)}\s*\('
    candidate_lines = []
    
    for i, line in enumerate(lines):
        if re.search(pattern, line):
            candidate_lines.append(i)
    
    if not candidate_lines:
        print(f"[REGEX] Function '{function_name}' not found in file")
        return None
    
    print(f"[REGEX] Found {len(candidate_lines)} potential location(s) for '{function_name}'")
    
    # Initialize LLM client
    llm = OllamaClient(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        timeout=settings.ollama_timeout
    )
    
    # Step 2: For each candidate, extract context and verify with LLM
    for idx, candidate_line in enumerate(candidate_lines):
        # Extract ±100 lines context around candidate
        context_size = 100
        start_line = max(0, candidate_line - context_size)
        end_line = min(len(lines), candidate_line + context_size)
        
        chunk = '\n'.join(lines[start_line:end_line])
        chunk_line_count = end_line - start_line
        
        print(f"[CHUNK {idx+1}/{len(candidate_lines)}] Checking lines {start_line+1}-{end_line} ({chunk_line_count} lines)")
        
        # Ask LLM to verify and find exact boundaries in this chunk
        response = llm.find_function_in_code(chunk, function_name)
        
        if response.found:
            # Adjust line numbers from chunk to full file (chunk is 1-indexed)
            actual_start = start_line + response.start_line
            actual_end = start_line + response.end_line
            
            # Validate adjusted line numbers
            if actual_start < 1 or actual_end > len(lines):
                print(f"[ERROR] Invalid adjusted line numbers: {actual_start}-{actual_end}")
                continue
            
            # Extract function code from full file
            full_code = '\n'.join(lines[actual_start - 1:actual_end])
            
            print(f"[LLM] Found '{function_name}' at lines {actual_start}-{actual_end}")
            
            return FunctionInfo(
                name=function_name,
                start_line=actual_start,
                end_line=actual_end,
                full_code=full_code,
                signature=response.signature
            )
        else:
            print(f"[LLM] Chunk {idx+1}: {response.reasoning}")
    
    # No valid function found in any chunk
    print(f"[ERROR] Function '{function_name}' not found after checking all candidates")
    return None


def extract_function_signature(function_code: str) -> str:
    """
    Extract function signature from function code.
    
    Args:
        function_code: Full function code
        
    Returns:
        Function signature
    """
    # Get first line up to opening brace
    match = re.search(r'^(.+?)\s*\{', function_code, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def validate_c_syntax(code: str) -> Tuple[bool, Optional[str]]:
    """
    Perform basic C syntax validation without compilation.
    
    Args:
        code: C code to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    errors = []
    
    # Check balanced braces
    brace_count = code.count('{') - code.count('}')
    if brace_count != 0:
        errors.append(f"Unbalanced braces: {brace_count} extra opening braces" if brace_count > 0 
                     else f"Unbalanced braces: {abs(brace_count)} extra closing braces")
    
    # Check balanced parentheses
    paren_count = code.count('(') - code.count(')')
    if paren_count != 0:
        errors.append(f"Unbalanced parentheses: {paren_count} extra opening" if paren_count > 0 
                     else f"Unbalanced parentheses: {abs(paren_count)} extra closing")
    
    # Check balanced brackets
    bracket_count = code.count('[') - code.count(']')
    if bracket_count != 0:
        errors.append(f"Unbalanced brackets: {bracket_count} extra opening" if bracket_count > 0 
                     else f"Unbalanced brackets: {abs(bracket_count)} extra closing")
    
    # Check for common syntax errors
    lines = code.split('\n')
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Skip empty lines and comments
        if not stripped or stripped.startswith('//') or stripped.startswith('/*'):
            continue
        
        # Check for statements that should end with semicolon
        if stripped and not stripped.endswith((';', '{', '}', ':')):
            # Check if it's a preprocessor directive
            if not stripped.startswith('#'):
                # Check if it's a control structure
                if not any(stripped.startswith(kw) for kw in ['if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default']):
                    # This might be missing a semicolon (heuristic)
                    pass  # Too many false positives, skip this check
    
    if errors:
        return False, "; ".join(errors)
    
    return True, None


def check_semantic_preservation(original: str, modified: str) -> Tuple[bool, Optional[str]]:
    """
    Heuristic check for semantic preservation.
    
    Args:
        original: Original function code
        modified: Modified function code
        
    Returns:
        Tuple of (is_preserved, warning_message)
    """
    warnings = []
    
    # Extract signatures
    orig_sig = extract_function_signature(original)
    mod_sig = extract_function_signature(modified)
    
    # Check if function signature changed significantly
    orig_name = re.search(r'\b(\w+)\s*\(', orig_sig)
    mod_name = re.search(r'\b(\w+)\s*\(', mod_sig)
    
    if orig_name and mod_name:
        if orig_name.group(1) != mod_name.group(1):
            warnings.append(f"Function name changed: {orig_name.group(1)} -> {mod_name.group(1)}")
    
    # Check if code length changed drastically (>50% change might indicate logic change)
    orig_lines = len([l for l in original.split('\n') if l.strip()])
    mod_lines = len([l for l in modified.split('\n') if l.strip()])
    
    if orig_lines > 0:
        change_ratio = abs(mod_lines - orig_lines) / orig_lines
        if change_ratio > 0.5:
            warnings.append(f"Significant code length change: {orig_lines} -> {mod_lines} lines ({change_ratio:.1%})")
    
    if warnings:
        return True, "; ".join(warnings)  # Still valid, but with warnings
    
    return True, None
