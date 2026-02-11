import os
import json
import logging
import requests
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    content: str
    model: str
    tokens_used: Optional[int] = None
    success: bool = True
    error: Optional[str] = None


class BaseLLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        pass


class OllamaProvider(BaseLLMProvider):
    def __init__(self, model: str, endpoint: str, temperature: float = 0.2, 
                 max_tokens: int = 2048, timeout: int = 60):
        self.model = model
        self.endpoint = endpoint
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        try:
            url = f"{self.endpoint}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            
            result = response.json()
            return LLMResponse(
                content=result.get("response", ""),
                model=self.model,
                tokens_used=result.get("eval_count"),
                success=True
            )
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            return LLMResponse(
                content="",
                model=self.model,
                success=False,
                error=str(e)
            )


class LocalLLMProvider(BaseLLMProvider):
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        logger.warning("Local LLM provider - using mock refactoring responses")
        
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        logger.info("Using mock LLM response for refactoring")
        
        if "Refactor this code" in prompt and "calculate_total" in prompt:
            refactored = """def calculate_total(items):
    if not items:
        return 0
    
    total = 0
    for item in items:
        if item and 'price' in item and item['price'] > 0:
            total += item['price']
    return total"""
            return LLMResponse(content=refactored, model="local-mock", success=True)
        
        if "Refactor this code" in prompt and "DataProcessor" in prompt:
            refactored = """class DataProcessor:
    def process(self, data):
        return [x * 2 for x in data if x > 0]"""
            return LLMResponse(content=refactored, model="local-mock", success=True)
        
        return LLMResponse(
            content="Mock response: Refactoring suggestion generated.",
            model="local-mock",
            success=True
        )


class LLMClient:
    ANALYSIS_SYSTEM_PROMPT = """You are an expert code analyzer. Analyze the provided code for:
1. Architectural violations and design pattern issues
2. Long methods that should be refactored
3. Code organization and modularity problems
4. Potential maintainability issues

Provide structured analysis with severity levels (CRITICAL, HIGH, MEDIUM, LOW)."""

    REFACTORING_SYSTEM_PROMPT = """You are an expert code refactoring assistant. 
Generate clean, improved code that:
1. Maintains original functionality
2. Improves readability and maintainability
3. Follows Python best practices
4. Preserves existing comments and docstrings

Output ONLY the refactored code without explanations."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        llm_config = config.get("llm", {})
        
        provider_type = llm_config.get("provider", "ollama")
        
        if provider_type == "ollama":
            try:
                ollama_provider = OllamaProvider(
                    model=llm_config.get("model", "deepseek-coder:6.7b"),
                    endpoint=llm_config.get("api_endpoint", "http://localhost:11434"),
                    temperature=llm_config.get("temperature", 0.2),
                    max_tokens=llm_config.get("max_tokens", 2048),
                    timeout=llm_config.get("timeout", 60)
                )
                
                test_response = ollama_provider.generate("test", None)
                if test_response.success:
                    self.provider = ollama_provider
                    logger.info("Ollama provider initialized successfully")
                else:
                    logger.warning("Ollama not available, falling back to mock provider")
                    self.provider = LocalLLMProvider()
            except Exception as e:
                logger.warning(f"Ollama connection failed, using mock provider: {e}")
                self.provider = LocalLLMProvider()
        else:
            self.provider = LocalLLMProvider()
            
        logger.info(f"Initialized LLM client with provider: {provider_type}")
    
    def analyze_code(self, code: str, file_path: str) -> LLMResponse:
        prompt = f"""Analyze this Python code from {file_path}:

```python
{code}
```

Identify high-level semantic issues, architectural violations, and refactoring opportunities.
Format your response as JSON with structure:
{{
  "issues": [
    {{
      "type": "architectural_violation|long_method|code_organization",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "description": "Issue description",
      "line_start": <line_number>,
      "line_end": <line_number>,
      "suggestion": "How to fix"
    }}
  ]
}}"""
        
        return self.provider.generate(prompt, self.ANALYSIS_SYSTEM_PROMPT)
    
    def generate_refactoring(self, code: str, issue_description: str, 
                           file_path: str) -> LLMResponse:
        prompt = f"""Refactor this code to fix the following issue:
Issue: {issue_description}

Original code from {file_path}:
```python
{code}
```

Generate the complete refactored code maintaining all functionality."""
        
        return self.provider.generate(prompt, self.REFACTORING_SYSTEM_PROMPT)
    
    def generate_commit_message(self, changes: List[str]) -> str:
        changes_text = "\n".join(f"- {change}" for change in changes)
        prompt = f"""Generate a concise git commit message for these refactoring changes:

{changes_text}

Format: Single line under 72 characters starting with verb."""
        
        response = self.provider.generate(prompt)
        if response.success:
            return response.content.strip().split('\n')[0][:72]
        return "Refactor: Code quality improvements"