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
    Find function in C source code using LLM.
    
    Args:
        file_content: Full file content
        function_name: Name of function to find
        
    Returns:
        FunctionInfo if found, None otherwise
    """
    from .llm_client import OllamaClient
    from ..config import settings
    
    # Initialize LLM client
    llm = OllamaClient(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        timeout=settings.ollama_timeout
    )
    
    # Ask LLM to find function
    response = llm.find_function_in_code(file_content, function_name)
    
    if not response.found:
        print(f"[LLM] {response.reasoning}")
        return None
    
    # Extract function code using line numbers
    lines = file_content.split('\n')
    
    # Validate line numbers
    if response.start_line < 1 or response.end_line > len(lines):
        print(f"[ERROR] Invalid line numbers from LLM: {response.start_line}-{response.end_line}")
        return None
    
    if response.start_line > response.end_line:
        print(f"[ERROR] Start line > end line: {response.start_line} > {response.end_line}")
        return None
    
    # Extract function code (convert to 0-indexed)
    full_code = '\n'.join(lines[response.start_line - 1:response.end_line])
    
    print(f"[LLM] Found '{function_name}' at lines {response.start_line}-{response.end_line}")
    
    return FunctionInfo(
        name=function_name,
        start_line=response.start_line,
        end_line=response.end_line,
        full_code=full_code,
        signature=response.signature
    )


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
