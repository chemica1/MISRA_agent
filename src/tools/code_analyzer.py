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
    Find function in C source code using tree-sitter parser.
    
    Args:
        file_content: Full file content
        function_name: Name of function to find
        
    Returns:
        FunctionInfo if found, None otherwise
    """
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_c
    except ImportError as e:
        print(f"[ERROR] tree-sitter not installed: {e}")
        print("[ERROR] Run: pip install tree-sitter tree-sitter-c")
        return None
    
    # Initialize parser
    C_LANGUAGE = Language(tree_sitter_c.language())
    parser = Parser(C_LANGUAGE)
    
    # Parse the source code
    tree = parser.parse(bytes(file_content, "utf8"))
    root_node = tree.root_node
    
    # Find function definition
    def find_function_node(node, target_name):
        """Recursively search for function definition with matching name."""
        if node.type == 'function_definition':
            # Get the declarator node which contains the function name
            declarator = None
            for child in node.children:
                if child.type == 'function_declarator':
                    declarator = child
                    break
                elif child.type in ['pointer_declarator', 'attributed_declarator']:
                    # Handle pointer return types or attributed functions
                    for subchild in child.children:
                        if subchild.type == 'function_declarator':
                            declarator = subchild
                            break
            
            if declarator:
                # Find the identifier (function name)
                identifier = None
                for child in declarator.children:
                    if child.type == 'identifier':
                        identifier = child
                        break
                    elif child.type in ['pointer_declarator', 'field_identifier']:
                        # Handle nested declarators
                        for subchild in child.children:
                            if subchild.type == 'identifier':
                                identifier = subchild
                                break
                
                if identifier:
                    func_name = file_content[identifier.start_byte:identifier.end_byte]
                    if func_name == target_name:
                        return node
        
        # Recursively search children
        for child in node.children:
            result = find_function_node(child, target_name)
            if result:
                return result
        
        return None
    
    # Search for the function
    func_node = find_function_node(root_node, function_name)
    
    if not func_node:
        print(f"[TREE-SITTER] Function '{function_name}' not found in file")
        return None
    
    # Extract function information
    start_line = func_node.start_point[0] + 1  # tree-sitter uses 0-indexed lines
    end_line = func_node.end_point[0] + 1
    
    # Extract full function code
    lines = file_content.split('\n')
    full_code = '\n'.join(lines[start_line - 1:end_line])
    
    # Extract function signature (everything before the opening brace)
    signature = extract_function_signature(full_code)
    
    print(f"[TREE-SITTER] Found '{function_name}' at lines {start_line}-{end_line}")
    
    return FunctionInfo(
        name=function_name,
        start_line=start_line,
        end_line=end_line,
        full_code=full_code,
        signature=signature
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
