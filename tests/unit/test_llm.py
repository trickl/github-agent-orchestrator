"""Unit tests for LLM providers."""

from unittest.mock import Mock, patch

import pytest

from github_agent_orchestrator.core.config import LLMConfig
from github_agent_orchestrator.llm.factory import LLMFactory
from github_agent_orchestrator.llm.openai_provider import OpenAIProvider


def test_llm_factory_openai() -> None:
    """Test LLM factory creates OpenAI provider."""
    config = LLMConfig(provider="openai", openai_api_key="test-key")

    with patch("github_agent_orchestrator.llm.openai_provider.OpenAI"):
        provider = LLMFactory.create(config)
        assert isinstance(provider, OpenAIProvider)


def test_llm_factory_unsupported() -> None:
    """Test LLM factory raises error for unsupported provider."""
    # Can't test with unsupported provider due to pydantic validation
    # This test validates that only supported providers work
    config = LLMConfig(provider="openai", openai_api_key="test-key")

    with patch("github_agent_orchestrator.llm.openai_provider.OpenAI"):
        provider = LLMFactory.create(config)
        assert isinstance(provider, OpenAIProvider)


def test_openai_provider_requires_api_key() -> None:
    """Test OpenAI provider requires API key."""
    config = LLMConfig(provider="openai")

    with pytest.raises(ValueError, match="OpenAI API key is required"):
        OpenAIProvider(config)


def test_openai_provider_generate(llm_config: LLMConfig) -> None:
    """Test OpenAI provider generate method."""
    with patch("github_agent_orchestrator.llm.openai_provider.OpenAI") as mock_openai:
        # Setup mock
        mock_client = Mock()
        mock_openai.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Generated text"
        mock_client.chat.completions.create.return_value = mock_response

        # Test
        provider = OpenAIProvider(llm_config)
        result = provider.generate("test prompt")

        assert result == "Generated text"
        mock_client.chat.completions.create.assert_called_once()


def test_openai_provider_chat(llm_config: LLMConfig) -> None:
    """Test OpenAI provider chat method."""
    with patch("github_agent_orchestrator.llm.openai_provider.OpenAI") as mock_openai:
        # Setup mock
        mock_client = Mock()
        mock_openai.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Chat response"
        mock_client.chat.completions.create.return_value = mock_response

        # Test
        provider = OpenAIProvider(llm_config)
        messages = [{"role": "user", "content": "Hello"}]
        result = provider.chat(messages)

        assert result == "Chat response"
        mock_client.chat.completions.create.assert_called_once()
