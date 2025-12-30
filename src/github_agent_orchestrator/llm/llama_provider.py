"""Local LLaMA LLM provider implementation."""

import logging
from typing import Any

from github_agent_orchestrator.core.config import LLMConfig
from github_agent_orchestrator.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class LLaMAProvider(LLMProvider):
    """Local LLaMA model provider implementation.
    
    Requires llama-cpp-python to be installed:
        pip install llama-cpp-python
    """
    
    def __init__(self, config: LLMConfig) -> None:
        """Initialize the LLaMA provider.
        
        Args:
            config: LLM configuration.
            
        Raises:
            ValueError: If model path is not provided.
            ImportError: If llama-cpp-python is not installed.
        """
        if not config.llama_model_path:
            raise ValueError("LLaMA model path is required")
        
        try:
            from llama_cpp import Llama
        except ImportError as e:
            raise ImportError(
                "llama-cpp-python is required for LLaMA provider. "
                "Install it with: pip install llama-cpp-python"
            ) from e
        
        self.config = config
        
        logger.info(f"Loading LLaMA model from: {config.llama_model_path}")
        
        self.llm = Llama(
            model_path=str(config.llama_model_path),
            n_ctx=config.llama_n_ctx,
            n_threads=config.llama_n_threads,
            verbose=False,
        )
        
        logger.info("LLaMA model loaded successfully")
    
    def generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate text completion using local LLaMA model.
        
        Args:
            prompt: The input prompt.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            **kwargs: Additional llama-cpp-specific parameters.
            
        Returns:
            Generated text completion.
        """
        logger.debug(f"Generating completion for prompt: {prompt[:100]}...")
        
        result = self.llm(
            prompt,
            max_tokens=max_tokens or 512,
            temperature=temperature or 0.7,
            **kwargs,
        )
        
        content = result["choices"][0]["text"]
        logger.debug(f"Generated {len(content)} characters")
        
        return content
    
    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate chat completion using local LLaMA model.
        
        Args:
            messages: List of message dicts with 'role' and 'content'.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            **kwargs: Additional llama-cpp-specific parameters.
            
        Returns:
            Generated chat response.
        """
        logger.debug(f"Generating chat completion with {len(messages)} messages")
        
        result = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens or 512,
            temperature=temperature or 0.7,
            **kwargs,
        )
        
        content = result["choices"][0]["message"]["content"]
        logger.debug(f"Generated {len(content)} characters")
        
        return content
    
    def count_tokens(self, text: str) -> int:
        """Count tokens using LLaMA tokenizer.
        
        Args:
            text: Text to count tokens for.
            
        Returns:
            Number of tokens.
        """
        tokens = self.llm.tokenize(text.encode("utf-8"))
        return len(tokens)
