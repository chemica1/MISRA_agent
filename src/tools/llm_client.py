"""Ollama LLM client with robust error handling."""

import requests
import json
import re
from typing import Optional, Dict, Any
from pydantic import BaseModel, ValidationError
from json_repair import repair_json


from .prompts import (
    DECIDE_ACTION_SYSTEM_PROMPT,
    DECIDE_ACTION_USER_TEMPLATE
)


class OllamaResponse(BaseModel):
    """Structured response from Ollama."""
    action: str  # "read_file" | "modify_code" | "next_violation" | "skip" | "already_compliant"
    reasoning: str
    is_safe: bool = True  # Whether fix can be safely applied in isolation
    safety_concerns: Optional[str] = None  # Description of risks if unsafe (<200 chars)
    modified_code: Optional[str] = None
    reason: Optional[str] = None  # Short reason for modification (<200 chars)


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
            "stream": False,
            "options": {}
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
        Parse JSON from LLM response using json-repair for robust handling.
        
        Handles C code in fields like 'modified_code' which may contain
        unescaped quotes from string literals (e.g., printf("hello")).
        
        Args:
            response: Raw LLM response
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            ValueError: If JSON cannot be parsed
        """
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly (greedy match)
            json_match = re.search(r'{.*}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError(f"No JSON found in response. Response starts with: {response[:200]}...")
        
        # Use json-repair to fix common LLM errors:
        # - Unescaped quotes in string values (e.g., C code with printf("..."))
        # - Trailing commas
        # - Comments
        # - Missing quotes on keys
        try:
            repaired_json = repair_json(json_str)
            parsed = json.loads(repaired_json, strict=False)
            
            # Ensure the result is a dictionary, not a list
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected JSON object (dict), but got {type(parsed).__name__}. Parsed value: {str(parsed)[:200]}")
            
            return parsed
        except Exception as e:
            raise ValueError(f"Failed to parse JSON even after repair: {e}. JSON excerpt: {json_str[:200]}...")
    
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
            violation: MISRA violation description
            function_code: Code of the function to fix
            error_feedback: Previous error message if retrying
        """
        system_prompt = DECIDE_ACTION_SYSTEM_PROMPT

        user_prompt = DECIDE_ACTION_USER_TEMPLATE.format(
            violation=violation,
            function_code=function_code
        )

        if error_feedback:
            user_prompt += f"\nPREVIOUS ERROR: {error_feedback}\nFix the error in your previous response."

        user_prompt += "\nRespond with valid JSON object only:"

        response = self.generate(user_prompt, system=system_prompt)
        
        try:
            return self.validate_response(response)
        except ValueError as e:
            raise ValueError(f"LLM response validation failed: {e}\n\nRaw response:\n{response}")
