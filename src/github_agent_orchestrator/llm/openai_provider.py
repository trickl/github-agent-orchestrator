"""OpenAI LLM provider implementation."""

import logging
from typing import Any

from openai import OpenAI

from github_agent_orchestrator.core.config import LLMConfig
from github_agent_orchestrator.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI API provider implementation."""
    
    def __init__(self, config: LLMConfig) -> None:
        """Initialize the OpenAI provider.
        
        Args:
            config: LLM configuration.
            
        Raises:
            ValueError: If API key is not provided.
        """
        if not config.openai_api_key:
            raise ValueError("OpenAI API key is required")
        
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)
        self.model = config.openai_model
        self.temperature = config.openai_temperature
        
        logger.info(f"OpenAI provider initialized with model: {self.model}")
    
    def generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate text completion using OpenAI API.
        
        Args:
            prompt: The input prompt.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            **kwargs: Additional OpenAI-specific parameters.
            
        Returns:
            Generated text completion.
        """
        temp = temperature if temperature is not None else self.temperature
        
        logger.debug(f"Generating completion for prompt: {prompt[:100]}...")
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temp,
            **kwargs,
        )
        
        content = response.choices[0].message.content or ""
        logger.debug(f"Generated {len(content)} characters")
        
        return content
    
    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate chat completion using OpenAI API.
        
        Args:
            messages: List of message dicts with 'role' and 'content'.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            **kwargs: Additional OpenAI-specific parameters.
            
        Returns:
            Generated chat response.
        """
        temp = temperature if temperature is not None else self.temperature
        
        logger.debug(f"Generating chat completion with {len(messages)} messages")
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore
            max_tokens=max_tokens,
            temperature=temp,
            **kwargs,
        )
        
        content = response.choices[0].message.content or ""
        logger.debug(f"Generated {len(content)} characters")
        
        return content
    
    def count_tokens(self, text: str) -> int:
        """Count tokens using a simple approximation.
        
        Args:
            text: Text to count tokens for.
            
        Returns:
            Estimated number of tokens.
            
        Note:
            This is a rough approximation. For accurate counts,
            use tiktoken library with the specific model's encoding.
        """
        # Rough approximation: 1 token ≈ 4 characters
        return len(text) // 4
