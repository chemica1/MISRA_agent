"""C code analysis and function extraction using tree-sitter."""

import re
from typing import Optional, Tuple

from pydantic import BaseModel

from tree_sitter import Language, Parser
import tree_sitter_c


# ============================================================================
# Data Models
# ============================================================================

class FunctionInfo(BaseModel):
    """Information about a C function."""
    name: str
    start_line: int
    end_line: int
    full_code: str
    signature: str


# ============================================================================
# Function Finding (Tree-sitter)
# ============================================================================

def find_function(file_content: str, function_name: str) -> Optional[FunctionInfo]:
    """
    Find function in C source code using tree-sitter parser.
    
    Args:
        file_content: Full file content
        function_name: Name of function to find
        
    Returns:
        FunctionInfo if found, None otherwise
    """

    # Initialize parser
    c_language = Language(tree_sitter_c.language())
    parser = Parser(c_language)
    
    # Parse the source code
    tree = parser.parse(bytes(file_content, "utf8"))
    
    # Search for the function
    func_node = _find_function_node(tree.root_node, function_name, file_content)
    
    if not func_node:
        print(f"[TREE-SITTER] Function '{function_name}' not found in file")
        return None
    
    # Extract function information
    start_line = func_node.start_point[0] + 1  # tree-sitter uses 0-indexed lines
    end_line = func_node.end_point[0] + 1
    
    # Extract full function code
    lines = file_content.split('\n')
    full_code = '\n'.join(lines[start_line - 1:end_line])
    
    # Extract function signature
    signature = extract_function_signature(full_code)
    
    print(f"[TREE-SITTER] Found '{function_name}' at lines {start_line}-{end_line}")
    
    return FunctionInfo(
        name=function_name,
        start_line=start_line,
        end_line=end_line,
        full_code=full_code,
        signature=signature
    )


def _find_function_node(node, target_name: str, file_content: str):
    """
    Recursively search for function definition with matching name.
    
    Args:
        node: Tree-sitter AST node
        target_name: Function name to find
        file_content: Source code content
        
    Returns:
        Function definition node if found, None otherwise
    """
    if node.type == 'function_definition':
        func_name = _extract_function_name(node, file_content)
        if func_name == target_name:
            return node
    
    # Recursively search children
    for child in node.children:
        result = _find_function_node(child, target_name, file_content)
        if result:
            return result
    
    return None


def _extract_function_name(func_def_node, file_content: str) -> str:
    """
    Extract function name from function_definition node.
    
    Uses field-based declarator traversal to safely extract the function name.
    Follows only the 'declarator' field chain, ignoring parameters/attributes.
    
    Args:
        func_def_node: function_definition AST node
        file_content: Source code content
        
    Returns:
        Function name as string, or empty string if not found
    """
    # Get the declarator field from function_definition
    decl = func_def_node.child_by_field_name('declarator')
    if decl is None:
        return ""
    
    # Follow the declarator chain until we find an identifier
    cur = decl
    while cur is not None and cur.type != 'identifier':
        next_decl = cur.child_by_field_name('declarator')
        if next_decl is None:
            # Last resort: check direct children for identifier
            for ch in cur.children:
                if ch.type == 'identifier':
                    return file_content[ch.start_byte:ch.end_byte]
            break
        cur = next_decl
    
    # If we found an identifier, extract its text
    if cur is not None and cur.type == 'identifier':
        return file_content[cur.start_byte:cur.end_byte]
    
    return ""


# ============================================================================
# Code Analysis Utilities
# ============================================================================

def extract_function_signature(function_code: str) -> str:
    """
    Extract function signature from function code.
    
    Args:
        function_code: Full function code
        
    Returns:
        Function signature (everything before opening brace)
    """
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
        msg = f"{brace_count} extra opening" if brace_count > 0 else f"{abs(brace_count)} extra closing"
        errors.append(f"Unbalanced braces: {msg}")
    
    # Check balanced parentheses
    paren_count = code.count('(') - code.count(')')
    if paren_count != 0:
        msg = f"{paren_count} extra opening" if paren_count > 0 else f"{abs(paren_count)} extra closing"
        errors.append(f"Unbalanced parentheses: {msg}")
    
    # Check balanced brackets
    bracket_count = code.count('[') - code.count(']')
    if bracket_count != 0:
        msg = f"{bracket_count} extra opening" if bracket_count > 0 else f"{abs(bracket_count)} extra closing"
        errors.append(f"Unbalanced brackets: {msg}")
    
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
    
    # Extract and compare function signatures
    orig_sig = extract_function_signature(original)
    mod_sig = extract_function_signature(modified)
    
    orig_name = re.search(r'\b(\w+)\s*\(', orig_sig)
    mod_name = re.search(r'\b(\w+)\s*\(', mod_sig)
    
    if orig_name and mod_name:
        if orig_name.group(1) != mod_name.group(1):
            warnings.append(f"Function name changed: {orig_name.group(1)} -> {mod_name.group(1)}")
    
    # Check for significant code length changes (>50% might indicate logic change)
    orig_lines = len([l for l in original.split('\n') if l.strip()])
    mod_lines = len([l for l in modified.split('\n') if l.strip()])
    
    if orig_lines > 0:
        change_ratio = abs(mod_lines - orig_lines) / orig_lines
        if change_ratio > 0.5:
            warnings.append(
                f"Significant code length change: {orig_lines} -> {mod_lines} lines ({change_ratio:.1%})"
            )
    
    if warnings:
        return True, "; ".join(warnings)  # Still valid, but with warnings
    
    return True, None
