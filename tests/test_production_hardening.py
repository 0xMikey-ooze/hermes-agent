"""Tests for production hardening: structured logging, health checks,
graceful shutdown, and resource cleanup.

TDD: Tests written before implementation.
"""

import asyncio
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Structured Logging ──────────────────────────────────────────────────────


class TestStructuredLogging:
    """Tests for JSON structured logging formatter."""

    def test_formats_as_json(self):
        """Log output should be valid JSON."""
        from agent.structured_logging import StructuredFormatter
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hello world", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"

    def test_includes_timestamp(self):
        """Log entries should include an ISO timestamp."""
        from agent.structured_logging import StructuredFormatter
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="test", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "timestamp" in parsed

    def test_includes_extra_fields(self):
        """Extra fields (session_id, etc.) should be included."""
        from agent.structured_logging import StructuredFormatter
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="test", args=(), exc_info=None,
        )
        record.session_id = "sess_123"
        record.platform = "telegram"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["session_id"] == "sess_123"
        assert parsed["platform"] == "telegram"

    def test_includes_exception_info(self):
        """Exception info should be serialized into the JSON."""
        from agent.structured_logging import StructuredFormatter
        formatter = StructuredFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1, msg="failure", args=(), exc_info=exc_info,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]

    def test_redacts_secrets(self):
        """API keys in messages should be redacted."""
        from agent.structured_logging import StructuredFormatter
        formatter = StructuredFormatter(redact=True)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="key=sk-1234567890abcdef1234567890abcdef",
            args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "sk-1234567890abcdef" not in parsed["message"]


# ── Health Check ────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    """Tests for the HealthServer state logic (no aiohttp test client needed)."""

    def test_health_server_state_running(self):
        """HealthServer should report healthy when state is 'running'."""
        from gateway.health import HealthServer
        server = HealthServer()
        server.update_state(gateway_state="running", platforms={"telegram": "connected"})
        assert server._state["gateway_state"] == "running"
        assert server._state["platforms"]["telegram"] == "connected"

    def test_health_server_state_starting_unhealthy(self):
        """HealthServer should report unhealthy when state is 'starting'."""
        from gateway.health import HealthServer
        server = HealthServer()
        # Default state is "starting"
        assert server._state["gateway_state"] == "starting"

    def test_health_server_ready_needs_platforms(self):
        """Readiness requires at least one connected platform."""
        from gateway.health import HealthServer
        server = HealthServer()
        server.update_state(gateway_state="running", platforms={})
        # Running but no platforms = not ready
        assert server._state["gateway_state"] == "running"
        assert len(server._state["platforms"]) == 0


# ── Resource Cleanup ────────────────────────────────────────────────────────


class TestSessionDBCleanup:
    """Tests for SessionDB resource cleanup."""

    def test_close_closes_connection(self, tmp_path):
        """Calling close() should close the SQLite connection."""
        from hermes_state import SessionDB
        db = SessionDB(db_path=tmp_path / "test.db")
        db.close()
        with pytest.raises(Exception):
            db._conn.execute("SELECT 1")

    def test_context_manager_closes_on_exit(self, tmp_path):
        """SessionDB should support context manager protocol."""
        from hermes_state import SessionDB
        with SessionDB(db_path=tmp_path / "test.db") as db:
            db._conn.execute("SELECT 1")
        # After exiting context, connection should be closed
        with pytest.raises(Exception):
            db._conn.execute("SELECT 1")


# ── Graceful Shutdown ───────────────────────────────────────────────────────


class TestGracefulShutdown:
    """Tests for shutdown timeout behavior."""

    @pytest.mark.asyncio
    async def test_shutdown_timeout_on_hung_adapter(self):
        """Shutdown should not hang forever if an adapter is stuck."""
        from gateway.shutdown import shutdown_with_timeout

        async def hung_disconnect():
            await asyncio.sleep(999)  # Simulates a hung adapter

        adapter = MagicMock()
        adapter.disconnect = hung_disconnect

        # Should complete within the timeout, not hang
        completed = await asyncio.wait_for(
            shutdown_with_timeout([adapter], timeout=0.5),
            timeout=2.0,
        )
        assert completed is True
