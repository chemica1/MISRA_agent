"""Ollama LLM client with robust error handling."""

import requests
import json
import re
from typing import Optional, Dict, Any
from pydantic import BaseModel, ValidationError


class OllamaResponse(BaseModel):
    """Structured response from Ollama."""
    action: str  # "read_file" | "modify_code" | "next_violation" | "skip"
    reasoning: str
    is_safe: bool = True  # Whether fix can be safely applied in isolation
    safety_concerns: Optional[str] = None  # Description of risks if unsafe
    modified_code: Optional[str] = None
    reason: Optional[str] = None  # Short reason for modification (<100 chars)


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
        
        # Parse JSON
        try:
            return json.loads(json_str)
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
1. Only fix the specific MISRA violation mentioned
2. Do NOT change business logic or behavior
3. Keep modifications minimal and conservative
4. Ensure code remains syntactically correct
5. Provide a brief reason (<100 chars) for your changes

SAFETY ANALYSIS - BEFORE proposing any fix, check if it requires:
- Changing function signature (parameters, return type)
- Modifying global variables or adding new ones
- Adding new external function calls or dependencies
- Changing function semantics or side effects

If ANY of these apply, set "is_safe": false and "action": "skip" with clear explanation.

Respond in JSON format:
{
    "action": "modify_code",  // or "skip" if unsafe
    "reasoning": "Brief explanation of what you're doing",
    "is_safe": true,  // false if fix requires signature changes or global impacts
    "safety_concerns": null,  // describe risks if is_safe=false
    "modified_code": "Complete modified function code",
    "reason": "Short reason for change (<100 chars)"
}

EXAMPLES:
- Safe: Adding const to local variable, fixing brace style, renaming local variable
- Unsafe: Changing return type, adding function parameter, modifying global state

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
