"""Ollama LLM client with robust error handling."""

import requests
import json
import re
from typing import Optional, Dict, Any
from pydantic import BaseModel, ValidationError


class OllamaResponse(BaseModel):
    """Structured response from Ollama."""
    action: str  # "read_file" | "modify_code" | "next_violation" | "skip" | "already_compliant"
    reasoning: str
    is_safe: bool = True  # Whether fix can be safely applied in isolation
    safety_concerns: Optional[str] = None  # Description of risks if unsafe (<200 chars)
    modified_code: Optional[str] = None
    reason: Optional[str] = None  # Short reason for modification (<200 chars)


class FunctionLocationResponse(BaseModel):
    """Response for function location in C code."""
    found: bool
    start_line: int = 0  # 1-indexed, 0 if not found
    end_line: int = 0    # 1-indexed, 0 if not found
    signature: str = ""
    reasoning: str = ""


class OllamaClient:
    """Client for interacting with Ollama API."""
    
    def __init__(self, model: str, base_url: str, timeout: int):
        """
        Initialize Ollama client.
        
        Args:
            model: Model name (e.g., "deepseek-coder")
            base_url: Ollama API base URL
            timeout: Request timeout in seconds
        """
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """
        Generate response from Ollama.
        
        Args:
            prompt: User prompt
            system: System prompt
            
        Returns:
            Generated text
            
        Raises:
            ConnectionError: If cannot connect to Ollama
            TimeoutError: If request times out
        """
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }
        
        if system:
            payload["system"] = system
        
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            
            result = response.json()
            return result.get("response", "")
            
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Could not connect to Ollama at {self.base_url}. Is Ollama running?")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Ollama request timed out after {self.timeout} seconds")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama request failed: {e}")
    
    def parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response with error recovery.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            ValueError: If JSON cannot be parsed
        """
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError("No JSON found in response")
        
        # Parse JSON with strict=False to handle Korean text and backslash escapes
        # strict=False allows control characters and unescaped backslashes
        try:
            return json.loads(json_str, strict=False)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
    
    def validate_response(self, response: str) -> OllamaResponse:
        """
        Validate and parse Ollama response into structured format.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Validated OllamaResponse
            
        Raises:
            ValueError: If response is invalid
        """
        try:
            data = self.parse_json_response(response)
            return OllamaResponse(**data)
        except (ValueError, ValidationError) as e:
            raise ValueError(f"Invalid response format: {e}")
    
    def decide_action(
        self,
        violation: str,
        function_code: str,
        error_feedback: Optional[str] = None
    ) -> OllamaResponse:
        """
        Ask LLM to decide on refactoring action.
        
        Args:
            violation: MISRA C violation description
            function_code: Current function code
            error_feedback: Previous error message for self-correction
            
        Returns:
            Structured decision
        """
        system_prompt = """You are an expert embedded C developer specializing in MISRA C compliance.
Your task is to refactor C code to fix MISRA C violations while preserving the original logic.

CRITICAL RULES:
1. **FIRST STEP**: Analyze if the code ALREADY complies with the mentioned MISRA rule
   - Carefully check if the violation actually exists in the current code
   - If the code is already compliant, use action: "already_compliant"
   - This is important to avoid unnecessary modifications
2. Only fix the specific MISRA violation mentioned
3. Do NOT change business logic or behavior
4. Keep modifications minimal and conservative
5. Ensure code remains syntactically correct
6. Provide a brief reason (<200 chars) for your changes

SAFETY ANALYSIS - BEFORE proposing any fix, check if it requires:
- Changing function signature (parameters, return type)
- Modifying global variables or adding new ones
- Adding new external function calls or dependencies
- Changing function semantics or side effects

If ANY of these apply, set "is_safe": false and "action": "skip" with clear explanation.

Respond in JSON format:
{
    "action": "modify_code",  // or "skip" if unsafe, or "already_compliant" if no violation exists
    "reasoning": "Brief explanation of what you're doing or why it's already compliant",
    "is_safe": true,  // false if fix requires signature changes or global impacts
    "safety_concerns": null,  // describe risks if is_safe=false (<200 chars)
    "modified_code": "Complete modified function code",  // null if already_compliant or skip
    "reason": "Short reason for change (<200 chars)"
}

EXAMPLES:
- Already compliant: "Code already follows MISRA C:2012 Rule 8.4, function prototype exists in header"
- Safe: Adding const to local variable, fixing brace style, renaming local variable
- Unsafe: Changing return type, adding function parameter, modifying global state

If code is already compliant, use action: "already_compliant".
If you cannot fix the violation safely, use action: "skip" with is_safe: false."""

        user_prompt = f"""MISRA C Violation:
{violation}

Current Function Code:
```c
{function_code}
```
"""

        if error_feedback:
            user_prompt += f"""
PREVIOUS ERROR:
{error_feedback}

Please correct your previous response based on this error."""

        response = self.generate(user_prompt, system=system_prompt)
        
        try:
            return self.validate_response(response)
        except ValueError as e:
            # Return error for self-correction loop
            raise ValueError(f"LLM response validation failed: {e}\n\nRaw response:\n{response}")
    
    def find_function_in_code(
        self,
        file_content: str,
        function_name: str
    ) -> FunctionLocationResponse:
        """
        Ask LLM to locate a function in C source code.
        
        Args:
            file_content: Full C file content
            function_name: Name of function to find
            
        Returns:
            FunctionLocationResponse with location info
        """
        # Add line numbers to file content for LLM reference
        lines = file_content.split('\n')
        numbered_content = '\n'.join(f"{i+1:4d}: {line}" for i, line in enumerate(lines))
        
        system_prompt = """You are an expert C code analyzer. Your task is to locate a specific function in C source code.

CRITICAL RULES:
1. Identify the EXACT start and end line numbers (1-indexed)
2. Start line = first line of function declaration/definition
3. End line = line with closing brace of function body
4. Extract the complete function signature
5. VERIFY this is a function DEFINITION (has body with {}), not just:
   - A function declaration/prototype (ends with ;)
   - A function call
   - A comment mentioning the function
6. If function is not found or not a valid definition, set found=false

Respond in JSON format:
{
    "found": true,
    "start_line": 42,
    "end_line": 58,
    "signature": "static int my_function(int param)",
    "reasoning": "Found function definition with body at lines 42-58"
}

If function is not found or not a definition:
{
    "found": false,
    "start_line": 0,
    "end_line": 0,
    "signature": "",
    "reasoning": "Function 'xyz' not found in file"
}"""

        user_prompt = f"""Find the function named '{function_name}' in this C code.

The code is shown with line numbers (format: "LINE: code"):

```c
{numbered_content}
```

Locate the function '{function_name}' and return its exact line numbers and signature."""

        try:
            response = self.generate(user_prompt, system=system_prompt)
            data = self.parse_json_response(response)
            return FunctionLocationResponse(**data)
        except (ValueError, ValidationError) as e:
            # Return not found on parsing errors
            return FunctionLocationResponse(
                found=False,
                reasoning=f"LLM response parsing failed: {e}"
            )
        except (ConnectionError, TimeoutError) as e:
            # Return not found on connection errors
            return FunctionLocationResponse(
                found=False,
                reasoning=f"LLM connection error: {e}"
            )
