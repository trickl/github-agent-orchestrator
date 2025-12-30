"""Factory for creating LLM providers."""

import logging

from github_agent_orchestrator.core.config import LLMConfig
from github_agent_orchestrator.llm.llama_provider import LLaMAProvider
from github_agent_orchestrator.llm.openai_provider import OpenAIProvider
from github_agent_orchestrator.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class LLMFactory:
    """Factory for creating LLM provider instances."""

    @staticmethod
    def create(config: LLMConfig) -> LLMProvider:
        """Create an LLM provider based on configuration.

        Args:
            config: LLM configuration specifying the provider.

        Returns:
            Configured LLM provider instance.

        Raises:
            ValueError: If provider type is not supported.
        """
        logger.info(f"Creating LLM provider: {config.provider}")

        if config.provider == "openai":
            return OpenAIProvider(config)
        elif config.provider == "llama":
            return LLaMAProvider(config)
        else:
            raise ValueError(f"Unsupported LLM provider: {config.provider}")
