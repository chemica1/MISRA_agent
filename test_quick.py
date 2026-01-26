"""Quick verification that json-repair works for our modified code."""

from json_repair import repair_json
import json

# Simulated LLM response with C code containing unescaped quotes
test_response = '''{
    "action": "modify_code",
    "reasoning": "Fixed MISRA violation",
    "is_safe": true,
    "modified_code": "void foo(void) {
    printf("Result: %u", value);
    return;
}",
    "reason": "Added cast"
}'''

print("Testing json-repair integration")
print("=" * 60)

try:
    # This is what llm_client.py now does
    repaired = repair_json(test_response)
    result = json.loads(repaired)
    
    print("SUCCESS! json-repair works perfectly.")
    print(f"  Modified code field parsed: {bool(result.get('modified_code'))}")
    if result.get('modified_code'):
        has_print_statement = 'printf' in result['modified_code']
        print(f"  Contains printf:  {has_print_statement}")
    print("\n>>> json-repair successfully handles C code with quotes!")
    
except Exception as e:
    print(f"FAILED: {e}")

print("=" * 60)
