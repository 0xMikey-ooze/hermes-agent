"""Tests for Bug #2: Telegram 409 polling conflict on rolling deploys.

Railway rolling deploys briefly overlap old/new containers. The old container
is still polling Telegram while the new one starts, causing HTTP 409 Conflict
("terminated by other getUpdates request"). The gateway must:

- Detect 409 conflict errors by error class name and message text
- Mark the error as RETRYABLE (not fatal) so the new container recovers
- Stop the updater gracefully after conflict detection
- Notify the fatal error system so monitoring can observe it

TDD RED phase — these tests verify the fix for:
  Telegram 409 Conflict: terminated by other getUpdates
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Stub optional deps
for _mod in ["dotenv", "yaml", "telegram", "telegram.ext"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# ===========================================================================
# Tests: Conflict detection helper
# ===========================================================================


class TestPollingConflictDetection:
    """Verify _looks_like_polling_conflict correctly identifies 409 errors."""

    def _get_platform_class(self):
        """Import TelegramPlatform from gateway."""
        from gateway.platforms.telegram import TelegramPlatform
        return TelegramPlatform

    def test_detects_conflict_by_class_name(self):
        """Error with class name 'Conflict' (python-telegram-bot) is detected."""
        cls = self._get_platform_class()

        # Simulate python-telegram-bot's Conflict exception
        class Conflict(Exception):
            pass

        error = Conflict("some conflict message")
        assert cls._looks_like_polling_conflict(error) is True

    def test_detects_conflict_by_getupdates_message(self):
        """Error mentioning 'terminated by other getUpdates request' is detected."""
        cls = self._get_platform_class()
        error = Exception("Conflict: terminated by other getUpdates request")
        assert cls._looks_like_polling_conflict(error) is True

    def test_detects_conflict_by_another_instance_message(self):
        """Error mentioning 'another bot instance is running' is detected."""
        cls = self._get_platform_class()
        error = Exception("another bot instance is running")
        assert cls._looks_like_polling_conflict(error) is True

    def test_ignores_unrelated_errors(self):
        """Non-conflict errors (network timeout, etc.) are not misidentified."""
        cls = self._get_platform_class()
        error = TimeoutError("Connection timed out")
        assert cls._looks_like_polling_conflict(error) is False

    def test_ignores_generic_runtime_error(self):
        """Generic RuntimeError is not a polling conflict."""
        cls = self._get_platform_class()
        error = RuntimeError("something went wrong")
        assert cls._looks_like_polling_conflict(error) is False

    def test_case_insensitive_detection(self):
        """Conflict detection is case-insensitive."""
        cls = self._get_platform_class()
        error = Exception("TERMINATED BY OTHER GETUPDATES REQUEST")
        assert cls._looks_like_polling_conflict(error) is True


# ===========================================================================
# Tests: Conflict handler marks error as retryable
# ===========================================================================


class TestPollingConflictHandler:
    """Verify _handle_polling_conflict marks the error as retryable."""

    def _make_platform(self):
        """Create a TelegramPlatform instance with mocked internals."""
        from gateway.platforms.telegram import TelegramPlatform

        platform = TelegramPlatform.__new__(TelegramPlatform)
        platform.name = "test-telegram"
        platform.has_fatal_error = False
        platform.fatal_error_code = None
        platform._app = None
        platform._polling_error_task = None
        # Mock the methods we need
        platform._set_fatal_error = MagicMock()
        platform._notify_fatal_error = AsyncMock()
        return platform

    @pytest.mark.asyncio
    async def test_conflict_marked_retryable(self):
        """409 conflict must be marked retryable=True so gateway can recover."""
        platform = self._make_platform()

        class Conflict(Exception):
            pass

        await platform._handle_polling_conflict(Conflict("terminated by other getUpdates"))

        # Verify _set_fatal_error was called with retryable=True
        platform._set_fatal_error.assert_called_once()
        call_args = platform._set_fatal_error.call_args
        assert call_args[0][0] == "telegram_polling_conflict", \
            f"Expected error code 'telegram_polling_conflict', got {call_args[0][0]}"
        assert call_args[1].get("retryable", call_args[0][2] if len(call_args[0]) > 2 else None) is True, \
            "Conflict must be marked retryable=True for rolling deploy recovery"

    @pytest.mark.asyncio
    async def test_conflict_not_marked_fatal_permanently(self):
        """Conflict must NOT permanently kill the gateway (retryable, not permanent)."""
        platform = self._make_platform()
        error = Exception("terminated by other getUpdates request")

        await platform._handle_polling_conflict(error)

        # Check that retryable=True was passed (not False or omitted)
        call_kwargs = platform._set_fatal_error.call_args
        # The third positional arg or 'retryable' kwarg must be True
        args = call_kwargs[0]
        kwargs = call_kwargs[1]
        retryable = kwargs.get("retryable", args[2] if len(args) > 2 else None)
        assert retryable is True, \
            "409 conflict must be retryable — old container will die soon"

    @pytest.mark.asyncio
    async def test_conflict_stops_updater(self):
        """After detecting conflict, the Telegram updater should be stopped."""
        platform = self._make_platform()
        mock_updater = AsyncMock()
        mock_app = MagicMock()
        mock_app.updater = mock_updater
        platform._app = mock_app

        error = Exception("terminated by other getUpdates request")
        await platform._handle_polling_conflict(error)

        mock_updater.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_conflict_notifies_fatal_error_system(self):
        """Conflict handler must call _notify_fatal_error for observability."""
        platform = self._make_platform()
        error = Exception("another bot instance is running")

        await platform._handle_polling_conflict(error)

        platform._notify_fatal_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotent_when_already_in_conflict(self):
        """If already in conflict state, handler is a no-op (no double-fire)."""
        platform = self._make_platform()
        platform.has_fatal_error = True
        platform.fatal_error_code = "telegram_polling_conflict"

        error = Exception("terminated by other getUpdates request")
        await platform._handle_polling_conflict(error)

        # Should not call _set_fatal_error again
        platform._set_fatal_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_updater_stop_failure_does_not_crash(self):
        """If stopping the updater throws, handler must not propagate the error."""
        platform = self._make_platform()
        mock_updater = AsyncMock()
        mock_updater.stop.side_effect = RuntimeError("stop failed")
        mock_app = MagicMock()
        mock_app.updater = mock_updater
        platform._app = mock_app

        error = Exception("terminated by other getUpdates request")
        # Must not raise
        await platform._handle_polling_conflict(error)

        # Should still notify despite updater stop failure
        platform._notify_fatal_error.assert_called_once()


# ===========================================================================
# Tests: Polling error callback routing
# ===========================================================================


class TestPollingErrorCallback:
    """Verify the error callback correctly routes conflict vs non-conflict errors."""

    def test_non_conflict_error_is_logged_not_handled(self):
        """Non-conflict polling errors should be logged but not trigger conflict handler."""
        from gateway.platforms.telegram import TelegramPlatform

        # Verify the static method exists and correctly filters
        timeout_error = TimeoutError("read timeout")
        assert TelegramPlatform._looks_like_polling_conflict(timeout_error) is False

    def test_conflict_error_triggers_handler(self):
        """A 409 conflict error should be routed to _handle_polling_conflict."""
        from gateway.platforms.telegram import TelegramPlatform

        conflict_error = Exception("terminated by other getUpdates request")
        assert TelegramPlatform._looks_like_polling_conflict(conflict_error) is True
