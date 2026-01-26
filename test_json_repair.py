"""
Test json-repair package with our EXACT problem:
C code in modified_code field with unescaped quotes
"""

import json
from json_repair import repair_json

print("=" * 70)
print("Testing json-repair with C code containing unescaped quotes")
print("=" * 70)

# Test Case 1: Simple printf with unescaped quotes (REAL PROBLEM)
test_case_1 = '''{
    "action": "modify_code",
    "reasoning": "Fixed MISRA violation",
    "is_safe": true,
    "modified_code": "void foo(void) {
    printf("Error: %s", "message");
    return;
}",
    "reason": "MISRA compliance"
}'''

# Test Case 2: More complex C code with multiple string literals
test_case_2 = '''{
    "action": "modify_code",
    "reasoning": "Added error handling",
    "is_safe": true,
    "modified_code": "int bar(void) {
    const char *str1 = "First string";
    const char *str2 = "Second string";
    printf("%s and %s", str1, str2);
    return 0;
}",
    "reason": "Fixed"
}'''

test_cases = [
    ("Simple printf with unescaped quotes", test_case_1),
    ("Multiple string literals", test_case_2),
]

for i, (desc, test_json) in enumerate(test_cases, 1):
    print(f"\n{'='*70}")
    print(f"Test Case {i}: {desc}")
    print(f"{'='*70}")
    
    # Try standard json.loads
    print(f"\n[1] Standard json.loads():")
    try:
        result = json.loads(test_json)
        print(f"    OK SUCCESS (unexpected!)")
    except json.JSONDecodeError as e:
        print(f"    X FAILED: {str(e)[:80]}")
    
    # Try json-repair
    print(f"\n[2] Using json-repair:")
    try:
        # Repair the JSON
        repaired = repair_json(test_json)
        
        # Parse the repaired JSON
        result = json.loads(repaired)
        
        print(f"    >> REPAIR SUCCESS!")
        print(f"       Action: {result.get('action')}")
        print(f"       Has modified_code: {bool(result.get('modified_code'))}")
        
        if result.get('modified_code'):
            code = result['modified_code']
            # Check if quotes are preserved
            has_printf = 'printf' in code
            has_quotes = '"' in code or '\\"' in code
            print(f"       Code has printf: {has_printf}")
            print(f"       Code has quotes: {has_quotes}")
            lines = code.split('\n')
            if len(lines) > 1:
                print(f"       Line 2: {lines[1][:60]}")
            
    except Exception as e:
        print(f"    X FAILED: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*70}")
print("CONCLUSION:")
print("If all tests show 'REPAIR SUCCESS', json-repair solves our problem!")
print(f"{'='*70}")
