"""Test the tree-sitter based find_function implementation."""

import re
from typing import Optional
from pydantic import BaseModel


class FunctionInfo(BaseModel):
    """Information about a C function."""
    name: str
    start_line: int
    end_line: int
    full_code: str
    signature: str


def extract_function_signature(function_code: str) -> str:
    """Extract function signature from function code."""
    match = re.search(r'^(.+?)\s*\{', function_code, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def find_function(file_content: str, function_name: str) -> Optional[FunctionInfo]:
    """Find function in C source code using tree-sitter parser."""
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


# Test C code with multiple functions
test_code = """
#include <stdio.h>

int helper_function(int x) {
    return x * 2;
}

void process_data(int *data, int size) {
    for (int i = 0; i < size; i++) {
        data[i] = helper_function(data[i]);
    }
}

int main(void) {
    int numbers[] = {1, 2, 3, 4, 5};
    int size = sizeof(numbers) / sizeof(numbers[0]);
    
    process_data(numbers, size);
    
    for (int i = 0; i < size; i++) {
        printf("%d ", numbers[i]);
    }
    printf("\\n");
    
    return 0;
}
"""

def test_find_function():
    """Test finding various functions."""
    print("Testing tree-sitter based find_function...\n")
    
    # Test 1: Find helper_function
    print("Test 1: Finding 'helper_function'")
    result = find_function(test_code, "helper_function")
    if result:
        print(f"[OK] Found: {result.name} at lines {result.start_line}-{result.end_line}")
        print(f"  Signature: {result.signature}")
    else:
        print("[FAIL] Failed to find helper_function")
        return False
    
    print()
    
    # Test 2: Find process_data
    print("Test 2: Finding 'process_data'")
    result = find_function(test_code, "process_data")
    if result:
        print(f"[OK] Found: {result.name} at lines {result.start_line}-{result.end_line}")
        print(f"  Signature: {result.signature}")
    else:
        print("[FAIL] Failed to find process_data")
        return False
    
    print()
    
    # Test 3: Find main
    print("Test 3: Finding 'main'")
    result = find_function(test_code, "main")
    if result:
        print(f"[OK] Found: {result.name} at lines {result.start_line}-{result.end_line}")
        print(f"  Signature: {result.signature}")
    else:
        print("[FAIL] Failed to find main")
        return False
    
    print()
    
    # Test 4: Try to find non-existent function
    print("Test 4: Finding non-existent 'foo_bar'")
    result = find_function(test_code, "foo_bar")
    if result is None:
        print("[OK] Correctly returned None for non-existent function")
    else:
        print("[FAIL] Should have returned None")
        return False
    
    print()
    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    import sys
    success = test_find_function()
    sys.exit(0 if success else 1)

