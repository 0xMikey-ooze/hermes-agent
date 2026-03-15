"""TDD tests for the extracted provider_router module.

These tests validate the provider routing and client initialization logic
that is being extracted from run_agent.py's AIAgent.__init__.
"""

import pytest


class TestProviderDetection:
    """Test API mode and provider detection from URLs and config."""

    def test_openrouter_detected_from_base_url(self):
        """OpenRouter should be detected from the default base URL."""
        from agent.provider_router import detect_provider
        result = detect_provider(
            base_url="https://openrouter.ai/api/v1",
            provider=None,
            model="anthropic/claude-sonnet-4",
        )
        assert result.provider == "openrouter"
        assert result.api_mode == "chat_completions"

    def test_anthropic_detected_from_base_url(self):
        """Anthropic should be detected from api.anthropic.com."""
        from agent.provider_router import detect_provider
        result = detect_provider(
            base_url="https://api.anthropic.com/v1",
            provider=None,
            model="claude-sonnet-4-20250514",
        )
        assert result.provider == "anthropic"
        assert result.api_mode == "anthropic_messages"

    def test_codex_detected_from_base_url(self):
        """Codex should be detected from chatgpt.com backend URL."""
        from agent.provider_router import detect_provider
        result = detect_provider(
            base_url="https://chatgpt.com/backend-api/codex",
            provider=None,
            model="gpt-4",
        )
        assert result.provider == "openai-codex"
        assert result.api_mode == "codex_responses"

    def test_explicit_provider_overrides_detection(self):
        """Explicit provider should take precedence over URL detection."""
        from agent.provider_router import detect_provider
        result = detect_provider(
            base_url="https://my-custom-endpoint.com/v1",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )
        assert result.provider == "anthropic"
        assert result.api_mode == "anthropic_messages"

    def test_explicit_api_mode_overrides_all(self):
        """Explicit api_mode should override everything."""
        from agent.provider_router import detect_provider
        result = detect_provider(
            base_url="https://api.anthropic.com/v1",
            provider=None,
            model="claude-sonnet-4-20250514",
            api_mode="chat_completions",
        )
        assert result.api_mode == "chat_completions"

    def test_unknown_url_defaults_to_chat_completions(self):
        """Unknown base URLs should default to chat_completions mode."""
        from agent.provider_router import detect_provider
        result = detect_provider(
            base_url="https://my-vllm-server.com/v1",
            provider=None,
            model="my-model",
        )
        assert result.api_mode == "chat_completions"

    def test_kimi_detected_from_base_url(self):
        """Kimi should be detected from api.kimi.com."""
        from agent.provider_router import detect_provider
        result = detect_provider(
            base_url="https://api.kimi.com/v1",
            provider=None,
            model="kimi-k2",
        )
        assert result.provider == "kimi"

    def test_none_base_url_defaults_to_openrouter(self):
        """No base URL should default to OpenRouter."""
        from agent.provider_router import detect_provider
        result = detect_provider(
            base_url=None,
            provider=None,
            model="anthropic/claude-sonnet-4",
        )
        assert result.provider == "openrouter"


class TestPromptCachingDecision:
    """Test prompt caching eligibility detection."""

    def test_claude_on_openrouter_enables_caching(self):
        """Claude models via OpenRouter should enable prompt caching."""
        from agent.provider_router import should_enable_prompt_caching
        assert should_enable_prompt_caching(
            base_url="https://openrouter.ai/api/v1",
            model="anthropic/claude-sonnet-4",
            api_mode="chat_completions",
        ) is True

    def test_non_claude_on_openrouter_disables_caching(self):
        """Non-Claude models via OpenRouter should not enable caching."""
        from agent.provider_router import should_enable_prompt_caching
        assert should_enable_prompt_caching(
            base_url="https://openrouter.ai/api/v1",
            model="google/gemini-2.5-pro",
            api_mode="chat_completions",
        ) is False

    def test_native_anthropic_enables_caching(self):
        """Native Anthropic API should always enable caching."""
        from agent.provider_router import should_enable_prompt_caching
        assert should_enable_prompt_caching(
            base_url="https://api.anthropic.com/v1",
            model="claude-sonnet-4-20250514",
            api_mode="anthropic_messages",
        ) is True


class TestToolDispatchDecision:
    """Tests for extracted tool dispatch logic."""

    def test_single_tool_uses_sequential(self):
        """A single tool call should use the sequential path."""
        from agent.tool_dispatch import choose_dispatch_mode
        mode = choose_dispatch_mode(
            tool_names=["web_search"],
            never_parallel=frozenset({"clarify"}),
        )
        assert mode == "sequential"

    def test_multiple_tools_uses_concurrent(self):
        """Multiple non-interactive tools should use concurrent."""
        from agent.tool_dispatch import choose_dispatch_mode
        mode = choose_dispatch_mode(
            tool_names=["web_search", "terminal", "read_file"],
            never_parallel=frozenset({"clarify"}),
        )
        assert mode == "concurrent"

    def test_interactive_tool_forces_sequential(self):
        """If any tool is in never_parallel, use sequential."""
        from agent.tool_dispatch import choose_dispatch_mode
        mode = choose_dispatch_mode(
            tool_names=["web_search", "clarify"],
            never_parallel=frozenset({"clarify"}),
        )
        assert mode == "sequential"

    def test_empty_tool_list_uses_sequential(self):
        """No tools should default to sequential (noop)."""
        from agent.tool_dispatch import choose_dispatch_mode
        mode = choose_dispatch_mode(
            tool_names=[],
            never_parallel=frozenset({"clarify"}),
        )
        assert mode == "sequential"
