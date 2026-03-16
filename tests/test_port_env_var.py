"""Tests for Bug #1: PORT env var must be read dynamically, not hardcoded.

Railway assigns dynamic ports via $PORT. The gateway must:
- Use $PORT when set (PaaS deployment)
- Fall back to $DASHBOARD_PORT when $PORT is unset (local dev)
- Default to 3001 when neither is set
- Never bind two servers to the same port (early health + web API)

TDD RED phase — these tests verify the fix for:
  OSError: port 8080 already in use
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Stub dependencies that gateway.run imports at module level
_STUBS = ["dotenv", "yaml"]
for _mod in _STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def _purge_gateway_modules():
    """Remove gateway modules so env vars are re-evaluated on import."""
    to_remove = [k for k in sys.modules if k.startswith("gateway")]
    for k in to_remove:
        del sys.modules[k]


# ===========================================================================
# Tests: $PORT env var resolution
# ===========================================================================


class TestPortEnvVarResolution:
    """Verify gateway reads PORT from environment, not hardcoded 8080."""

    def test_uses_port_env_var_when_set(self):
        """When $PORT is set (Railway), gateway binds to that port."""
        _purge_gateway_modules()
        with patch.dict(os.environ, {"PORT": "5555"}, clear=False):
            # Remove DASHBOARD_PORT to isolate
            env = dict(os.environ)
            env.pop("DASHBOARD_PORT", None)
            with patch.dict(os.environ, env, clear=True):
                os.environ["PORT"] = "5555"
                from gateway import run
                # The module-level _dashboard_port should reflect $PORT
                assert hasattr(run, "_dashboard_port"), \
                    "gateway.run must define _dashboard_port at module level"
                assert run._dashboard_port == 5555, \
                    f"Expected port 5555 from $PORT, got {run._dashboard_port}"

    def test_falls_back_to_dashboard_port(self):
        """When $PORT is unset but $DASHBOARD_PORT is set, use DASHBOARD_PORT."""
        _purge_gateway_modules()
        env = dict(os.environ)
        env.pop("PORT", None)
        env["DASHBOARD_PORT"] = "4200"
        with patch.dict(os.environ, env, clear=True):
            from gateway import run
            assert run._dashboard_port == 4200, \
                f"Expected port 4200 from $DASHBOARD_PORT, got {run._dashboard_port}"

    def test_defaults_to_3001_when_no_env(self):
        """When neither $PORT nor $DASHBOARD_PORT is set, default to 3001."""
        _purge_gateway_modules()
        env = dict(os.environ)
        env.pop("PORT", None)
        env.pop("DASHBOARD_PORT", None)
        with patch.dict(os.environ, env, clear=True):
            from gateway import run
            assert run._dashboard_port == 3001, \
                f"Expected default port 3001, got {run._dashboard_port}"

    def test_port_is_not_hardcoded_8080(self):
        """Regression: port must never be hardcoded to 8080."""
        _purge_gateway_modules()
        env = dict(os.environ)
        env.pop("PORT", None)
        env.pop("DASHBOARD_PORT", None)
        with patch.dict(os.environ, env, clear=True):
            from gateway import run
            assert run._dashboard_port != 8080, \
                "Port must not be hardcoded to 8080 — use $PORT env var"

    def test_port_env_var_takes_precedence_over_dashboard_port(self):
        """$PORT (PaaS) takes priority over $DASHBOARD_PORT (dev convenience)."""
        _purge_gateway_modules()
        with patch.dict(os.environ, {"PORT": "9999", "DASHBOARD_PORT": "4200"}, clear=False):
            from gateway import run
            assert run._dashboard_port == 9999, \
                f"$PORT should take precedence, got {run._dashboard_port}"

    def test_port_env_var_is_integer(self):
        """Port value must be cast to int, not left as string."""
        _purge_gateway_modules()
        with patch.dict(os.environ, {"PORT": "7777"}, clear=False):
            from gateway import run
            assert isinstance(run._dashboard_port, int), \
                f"Port must be int, got {type(run._dashboard_port)}"


# ===========================================================================
# Tests: No port conflict between early health server and web API
# ===========================================================================


class TestNoPortConflict:
    """Verify the early health server and web API don't fight over the same port."""

    def test_early_port_matches_dashboard_port(self):
        """The early health server port must equal the dashboard port (single bind)."""
        _purge_gateway_modules()
        with patch.dict(os.environ, {"PORT": "6000"}, clear=False):
            from gateway import run
            # Both should resolve to the same value
            assert hasattr(run, "_early_port"), \
                "gateway.run must define _early_port for the health endpoint"
            assert run._early_port == run._dashboard_port, \
                f"Early port ({run._early_port}) != dashboard port ({run._dashboard_port}) — risk of conflict"

    def test_web_api_host_port_from_env(self):
        """HermesWebAPI.start() must use the env-derived port, not a hardcoded one."""
        _purge_gateway_modules()
        with patch.dict(os.environ, {"PORT": "8888"}, clear=False):
            from gateway.web_api import HermesWebAPI
            import inspect
            source = inspect.getsource(HermesWebAPI)
            # The source should NOT contain hardcoded "8080"
            assert "8080" not in source, \
                "HermesWebAPI source must not contain hardcoded port 8080"
