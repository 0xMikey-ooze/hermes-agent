"""Provider detection and routing logic extracted from run_agent.py.

Determines the API mode, provider identity, and feature flags (like prompt
caching) based on the base URL, explicit provider, and model name.

This module is pure logic with no side effects — safe to import and test.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ProviderInfo:
    """Result of provider detection."""
    provider: str          # e.g., "openrouter", "anthropic", "openai-codex", "kimi"
    api_mode: str          # "chat_completions", "anthropic_messages", "codex_responses"


# Default OpenRouter URL used when no base_url is provided
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def detect_provider(
    base_url: Optional[str],
    provider: Optional[str],
    model: str,
    api_mode: Optional[str] = None,
) -> ProviderInfo:
    """Detect the provider and API mode from configuration.

    Priority:
    1. Explicit api_mode overrides everything
    2. Explicit provider name maps to known API modes
    3. Base URL pattern matching
    4. Default: openrouter + chat_completions

    Args:
        base_url: The API endpoint URL (may be None → defaults to OpenRouter).
        provider: Explicit provider name from config (may be None).
        model: The model identifier.
        api_mode: Explicit API mode override (may be None).

    Returns:
        ProviderInfo with resolved provider and api_mode.
    """
    effective_url = (base_url or _OPENROUTER_BASE).lower()
    provider_name = provider.strip().lower() if isinstance(provider, str) and provider.strip() else None

    # 1. Explicit api_mode — trust it
    if api_mode in ("chat_completions", "codex_responses", "anthropic_messages"):
        resolved_provider = provider_name or _guess_provider_from_url(effective_url)
        return ProviderInfo(provider=resolved_provider, api_mode=api_mode)

    # 2. Explicit provider name
    if provider_name == "openai-codex":
        return ProviderInfo(provider="openai-codex", api_mode="codex_responses")
    if provider_name == "anthropic":
        return ProviderInfo(provider="anthropic", api_mode="anthropic_messages")

    # 3. URL-based detection
    if "chatgpt.com/backend-api/codex" in effective_url:
        return ProviderInfo(provider="openai-codex", api_mode="codex_responses")
    if "api.anthropic.com" in effective_url:
        return ProviderInfo(provider="anthropic", api_mode="anthropic_messages")
    if "api.kimi.com" in effective_url:
        return ProviderInfo(provider=provider_name or "kimi", api_mode="chat_completions")

    # 4. Default
    return ProviderInfo(
        provider=provider_name or _guess_provider_from_url(effective_url),
        api_mode="chat_completions",
    )


def _guess_provider_from_url(url: str) -> str:
    """Best-effort provider name from URL patterns."""
    if "openrouter" in url:
        return "openrouter"
    if "api.openai.com" in url:
        return "openai"
    if "api.anthropic.com" in url:
        return "anthropic"
    if "api.kimi.com" in url:
        return "kimi"
    if "z.ai" in url or "open.bigmodel.cn" in url:
        return "glm"
    if "api.minimax.chat" in url:
        return "minimax"
    return "openrouter"


def should_enable_prompt_caching(
    base_url: Optional[str],
    model: str,
    api_mode: str,
) -> bool:
    """Determine whether to enable Anthropic prompt caching.

    Prompt caching is enabled when:
    - Using Claude models via OpenRouter, OR
    - Using the native Anthropic API (anthropic_messages mode)
    """
    effective_url = (base_url or _OPENROUTER_BASE).lower()
    is_openrouter = "openrouter" in effective_url
    is_claude = "claude" in model.lower()
    is_native_anthropic = api_mode == "anthropic_messages"
    return (is_openrouter and is_claude) or is_native_anthropic
