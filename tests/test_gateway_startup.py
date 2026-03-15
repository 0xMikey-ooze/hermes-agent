"""
Tests for AGI server connectivity check during gateway startup.
TDD: these tests are written BEFORE the implementation.
"""
import os
import sys
import asyncio
import logging
import unittest
from unittest.mock import patch, MagicMock, call

# ---------------------------------------------------------------------------
# Patch all gateway.run dependencies that aren't available in test env before
# any test imports so the module can be loaded cleanly.
# ---------------------------------------------------------------------------
def _patch_gateway_deps():
    """Install stub modules for gateway/run.py's hard imports."""
    stubs = {
        "dotenv": MagicMock(load_dotenv=MagicMock()),
        "yaml": MagicMock(),
    }
    for name, stub in stubs.items():
        if name not in sys.modules:
            sys.modules[name] = stub

    # Also stub out submodules that gateway.run imports
    for mod in list(sys.modules):
        pass  # intentionally empty — just ensure dotenv is present

_patch_gateway_deps()


def _purge_gateway_run():
    """Remove gateway.run and related modules from sys.modules for a fresh import."""
    to_remove = [k for k in sys.modules if k in ("gateway.run", "gateway")]
    for k in to_remove:
        del sys.modules[k]


class TestGatewayStartupAgiCheck(unittest.TestCase):
    """Tests for _check_agi_integration() in gateway/run.py"""

    def _import_check_fn(self):
        """Import _check_agi_integration from gateway.run."""
        _purge_gateway_run()
        # Ensure dotenv stub is present for the import
        _patch_gateway_deps()
        from gateway.run import _check_agi_integration
        return _check_agi_integration

    def test_startup_calls_agi_check_when_url_set(self):
        """When AGI_SERVER_URL is set, _check_agi_integration calls check_agi_server."""
        _check_agi_integration = self._import_check_fn()

        mock_client = MagicMock()
        mock_check = MagicMock(return_value=True)

        with patch.dict(os.environ, {"AGI_SERVER_URL": "http://localhost:8080"}, clear=False):
            with patch("src.agi_client.AgiClient", return_value=mock_client) as MockClient:
                with patch("src.agi_client.check_agi_server", mock_check):
                    _check_agi_integration()

        mock_check.assert_called_once_with(mock_client)

    def test_startup_skips_agi_check_when_url_missing(self):
        """When AGI_SERVER_URL not set, startup proceeds without calling check_agi_server."""
        _check_agi_integration = self._import_check_fn()

        mock_check = MagicMock()

        env = {k: v for k, v in os.environ.items() if k != "AGI_SERVER_URL"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.agi_client.check_agi_server", mock_check):
                # Should not raise
                _check_agi_integration()

        mock_check.assert_not_called()

    def test_startup_logs_skip_message(self):
        """When AGI_SERVER_URL missing, logs 'AGI server integration disabled'."""
        _check_agi_integration = self._import_check_fn()

        env = {k: v for k, v in os.environ.items() if k != "AGI_SERVER_URL"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertLogs("gateway.run", level="INFO") as log_ctx:
                _check_agi_integration()

        self.assertTrue(
            any("AGI server integration disabled" in msg for msg in log_ctx.output),
            f"Expected 'AGI server integration disabled' in logs, got: {log_ctx.output}",
        )

    def test_startup_raises_on_unreachable(self):
        """When AGI_SERVER_URL is set but server unreachable, raises RuntimeError."""
        _check_agi_integration = self._import_check_fn()

        mock_client = MagicMock()
        mock_check = MagicMock(side_effect=RuntimeError("AGI server unreachable"))

        with patch.dict(os.environ, {"AGI_SERVER_URL": "http://localhost:9999"}, clear=False):
            with patch("src.agi_client.AgiClient", return_value=mock_client):
                with patch("src.agi_client.check_agi_server", mock_check):
                    with self.assertRaises(RuntimeError):
                        _check_agi_integration()

    def test_startup_ok_when_reachable(self):
        """When server returns health OK, startup proceeds normally (no exception)."""
        _check_agi_integration = self._import_check_fn()

        mock_client = MagicMock()
        mock_check = MagicMock(return_value=True)

        with patch.dict(os.environ, {"AGI_SERVER_URL": "http://localhost:8080"}, clear=False):
            with patch("src.agi_client.AgiClient", return_value=mock_client):
                with patch("src.agi_client.check_agi_server", mock_check):
                    # Should not raise
                    result = _check_agi_integration()

        # No exception means success; function may return None
        mock_check.assert_called_once()

    def test_startup_timeout(self):
        """If AGI health check hangs >5s, times out and logs warning (does NOT block startup)."""
        _check_agi_integration = self._import_check_fn()

        import time

        def slow_check(client):
            time.sleep(10)  # Much longer than 5s timeout

        mock_client = MagicMock()

        with patch.dict(os.environ, {"AGI_SERVER_URL": "http://localhost:8080"}, clear=False):
            with patch("src.agi_client.AgiClient", return_value=mock_client):
                with patch("src.agi_client.check_agi_server", slow_check):
                    with self.assertLogs("gateway.run", level="WARNING") as log_ctx:
                        # Must complete (not hang), return within reasonable time
                        start = time.time()
                        _check_agi_integration()
                        elapsed = time.time() - start

        self.assertLess(elapsed, 8.0, "AGI check should time out and not block for >8s")
        self.assertTrue(
            any("timed out" in msg.lower() or "timeout" in msg.lower() for msg in log_ctx.output),
            f"Expected timeout warning in logs, got: {log_ctx.output}",
        )


class TestStartGatewayCallsAgiCheck(unittest.TestCase):
    """Verify that start_gateway() calls _check_agi_integration() on startup."""

    def test_start_gateway_calls_check_agi_integration(self):
        """start_gateway() must call _check_agi_integration() during startup."""
        _purge_gateway_run()
        _patch_gateway_deps()

        with patch("gateway.run._check_agi_integration") as mock_check:
            # We only need to verify the call happens, not that the full gateway starts
            mock_check.return_value = None

            # Mock everything that start_gateway needs so it doesn't actually start
            with patch("gateway.run.GatewayRunner") as MockRunner:
                mock_runner = MagicMock()

                async def _fake_start():
                    return False

                mock_runner.start = _fake_start
                MockRunner.return_value = mock_runner

                try:
                    from gateway.run import start_gateway
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(
                            asyncio.wait_for(start_gateway(), timeout=3.0)
                        )
                    except (asyncio.TimeoutError, Exception):
                        pass
                    finally:
                        loop.close()
                except Exception:
                    pass

            mock_check.assert_called()


if __name__ == "__main__":
    unittest.main()
