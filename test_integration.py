"""Integration test: Verify llm_client can parse problematic JSON using json-repair."""

import sys
sys.path.insert(0, r'c:\Users\dh\Desktop\agent\MISRA_agent\src')

from tools.llm_client import OllamaClient

# Initialize client (we won't actually call the LLM, just test parsing)
client = OllamaClient(
    model="qwen2.5-coder:32b",
    base_url="http://localhost:11434",
    timeout=120
)

# Test: Simulated LLM response with unescaped quotes in C code
llm_response_with_unescaped_quotes = '''```json
{
    "action": "modify_code",
    "reasoning": "Fixed MISRA Rule 10.3 violation by adding explicit cast",
    "is_safe": true,
    "safety_concerns": null,
    "modified_code": "void process_data(void) {
    uint16_t value = 100U;
    uint8_t result = (uint8_t)value;
    printf("Result: %u", result);
    logMessage("Processing complete");
    return;
}",
    "reason": "Added explicit type cast for MISRA compliance"
}
```'''

print("=" * 70)
print("Integration Test: llm_client with json-repair")
print("=" * 70)

print("\nSimulated LLM Response (has unescaped quotes in C code):")
print("  Lines with printf:")
for line in llm_response_with_unescaped_quotes.split('\n'):
    if 'printf' in line or 'logMessage' in line:
        print(f"    {line}")

print("\nParsing with llm_client.parse_json_response():")
try:
    result = client.parse_json_response(llm_response_with_unescaped_quotes)
    
    print("  >> SUCCESS!")
    print(f"  - Action: {result.get('action')}")
    print(f"  - Reasoning: {result.get('reasoning')[:50]}...")
    print(f"  - Is Safe: {result.get('is_safe')}")
    print(f"  - Has modified_code: {bool(result.get('modified_code'))}")
    
    if result.get('modified_code'):
        code = result['modified_code']
        lines = code.split('\n')
        print(f"  - Code lines: {len(lines)}")
        # Find the printf line
        for i, line in enumerate(lines):
            if 'printf' in line:
                print(f"  - Line {i+1}: {line.strip()}")
                
    print("\n" + "=" * 70)
    print("RESULT: json-repair successfully handles our use case!")
    print("=" * 70)
    
except Exception as e:
    print(f"  >> FAILED: {e}")
    import traceback
    traceback.print_exc()
    print("\n" + "=" * 70)
    print("RESULT: Integration test failed - needs investigation")
    print("=" * 70)
