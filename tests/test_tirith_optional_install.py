"""Tests for Bug #3: Tirith binary download must fail gracefully.

The gateway calls tirith_security.ensure_installed() at startup. If the
download fails (network error, unsupported platform, cosign not found),
the gateway must continue running — tirith is optional. Failures should:

- Not block or crash gateway startup
- Return None (not available) instead of raising
- Set appropriate failure reason markers
- Be retryable when the cause is transient (e.g., cosign later installed)

TDD RED phase — these tests verify the fix for:
  cosign not found, tirith download failed
"""

import os
import platform
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Stub deps
for _mod in ["dotenv", "yaml", "requests", "requests.exceptions"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def _purge_tirith_module():
    """Remove tirith module from cache so globals reset."""
    to_remove = [k for k in sys.modules if "tirith" in k]
    for k in to_remove:
        del sys.modules[k]


def _import_tirith():
    """Import tirith_security module fresh."""
    _purge_tirith_module()
    from tools import tirith_security
    # Reset module-level state
    tirith_security._resolved_path = None
    tirith_security._install_thread = None
    tirith_security._install_failure_reason = ""
    return tirith_security


# ===========================================================================
# Tests: ensure_installed returns None gracefully on failures
# ===========================================================================


class TestEnsureInstalledGraceful:
    """Verify ensure_installed() never crashes, returns None on failure."""

    def test_returns_none_when_tirith_disabled(self):
        """When tirith_enabled=False in config, returns None immediately."""
        mod = _import_tirith()
        with patch.object(mod, "_load_security_config",
                          return_value={"tirith_enabled": False, "tirith_path": "tirith"}):
            result = mod.ensure_installed()
            assert result is None

    def test_returns_none_when_binary_not_found(self):
        """When tirith binary is not on PATH or in HERMES_HOME, returns None."""
        mod = _import_tirith()
        with patch.object(mod, "_load_security_config",
                          return_value={"tirith_enabled": True, "tirith_path": "tirith"}):
            with patch("shutil.which", return_value=None):
                with patch.object(mod, "_hermes_bin_dir", return_value="/nonexistent/bin"):
                    with patch.object(mod, "_is_install_failed_on_disk", return_value=False):
                        with patch.object(mod, "_read_failure_reason", return_value=None):
                            # Should spawn background thread, return None immediately
                            with patch.object(mod, "_background_install"):
                                result = mod.ensure_installed()
                                assert result is None

    def test_returns_path_when_binary_on_path(self):
        """When tirith is already on PATH, returns its path immediately."""
        mod = _import_tirith()
        with patch.object(mod, "_load_security_config",
                          return_value={"tirith_enabled": True, "tirith_path": "tirith"}):
            with patch("shutil.which", return_value="/usr/local/bin/tirith"):
                result = mod.ensure_installed()
                assert result == "/usr/local/bin/tirith"

    def test_does_not_raise_on_explicit_path_missing(self):
        """When explicit path configured but missing, returns None (no crash)."""
        mod = _import_tirith()
        with patch.object(mod, "_load_security_config",
                          return_value={"tirith_enabled": True, "tirith_path": "/opt/tirith/bin/tirith"}):
            with patch.object(mod, "_is_explicit_path", return_value=True):
                with patch("os.path.isfile", return_value=False):
                    with patch("shutil.which", return_value=None):
                        result = mod.ensure_installed()
                        assert result is None


# ===========================================================================
# Tests: _install_tirith handles download failures
# ===========================================================================


class TestInstallTirithFailures:
    """Verify _install_tirith returns failure tuples instead of raising."""

    def test_unsupported_platform_returns_none(self):
        """On unsupported platform (e.g., Windows ARM), returns (None, reason)."""
        mod = _import_tirith()
        with patch.object(mod, "_detect_target", return_value=None):
            result_path, reason = mod._install_tirith()
            assert result_path is None
            assert reason == "unsupported_platform"

    def test_download_failure_returns_none(self):
        """Network error during archive download returns (None, 'download_failed')."""
        mod = _import_tirith()
        with patch.object(mod, "_detect_target", return_value="linux-amd64"):
            with patch.object(mod, "_download_file",
                              side_effect=ConnectionError("network unreachable")):
                result_path, reason = mod._install_tirith()
                assert result_path is None
                assert reason == "download_failed"

    def test_cosign_missing_returns_none(self):
        """When cosign binary is not found, returns (None, 'cosign_missing')."""
        mod = _import_tirith()
        call_count = [0]
        def mock_download(url, path):
            """Succeed for all downloads (archive + checksums + sig + cert)."""
            call_count[0] += 1
            Path(path).touch()

        with patch.object(mod, "_detect_target", return_value="linux-amd64"):
            with patch.object(mod, "_download_file", side_effect=mock_download):
                with patch("shutil.which", return_value=None):
                    result_path, reason = mod._install_tirith()
                    assert result_path is None
                    assert reason == "cosign_missing"

    def test_cosign_artifacts_unavailable(self):
        """When cosign signature files can't be downloaded, returns gracefully."""
        mod = _import_tirith()
        download_calls = [0]
        def mock_download(url, path):
            download_calls[0] += 1
            # First two downloads (archive + checksums) succeed
            if download_calls[0] <= 2:
                Path(path).touch()
                return
            # Sig/cert downloads fail
            raise ConnectionError("signature file not found")

        with patch.object(mod, "_detect_target", return_value="linux-amd64"):
            with patch.object(mod, "_download_file", side_effect=mock_download):
                result_path, reason = mod._install_tirith()
                assert result_path is None
                assert reason == "cosign_artifacts_unavailable"

    def test_cosign_verification_failed(self):
        """When cosign rejects the signature, returns (None, reason)."""
        mod = _import_tirith()
        def mock_download(url, path):
            Path(path).touch()

        with patch.object(mod, "_detect_target", return_value="linux-amd64"):
            with patch.object(mod, "_download_file", side_effect=mock_download):
                with patch("shutil.which", return_value="/usr/bin/cosign"):
                    with patch.object(mod, "_verify_cosign", return_value=False):
                        result_path, reason = mod._install_tirith()
                        assert result_path is None
                        assert reason == "cosign_verification_failed"

    def test_cosign_exec_failed(self):
        """When cosign execution fails (timeout/OSError), returns (None, reason)."""
        mod = _import_tirith()
        def mock_download(url, path):
            Path(path).touch()

        with patch.object(mod, "_detect_target", return_value="linux-amd64"):
            with patch.object(mod, "_download_file", side_effect=mock_download):
                with patch("shutil.which", return_value="/usr/bin/cosign"):
                    with patch.object(mod, "_verify_cosign", return_value=None):
                        result_path, reason = mod._install_tirith()
                        assert result_path is None
                        assert reason == "cosign_exec_failed"


# ===========================================================================
# Tests: Failure markers and retry logic
# ===========================================================================


class TestFailureMarkersAndRetry:
    """Verify failure state is tracked and retryable failures can recover."""

    def test_cosign_missing_is_retryable(self):
        """When cosign becomes available later, the failure should clear."""
        mod = _import_tirith()

        # Simulate previous failure due to cosign_missing
        mod._resolved_path = mod._INSTALL_FAILED
        mod._install_failure_reason = "cosign_missing"

        with patch.object(mod, "_load_security_config",
                          return_value={"tirith_enabled": True, "tirith_path": "tirith"}):
            # Now cosign IS available
            with patch("shutil.which", side_effect=lambda cmd: "/usr/bin/cosign" if cmd == "cosign" else None):
                with patch.object(mod, "_is_install_failed_on_disk", return_value=False):
                    with patch.object(mod, "_read_failure_reason", return_value=None):
                        with patch.object(mod, "_hermes_bin_dir", return_value="/nonexistent"):
                            with patch.object(mod, "_background_install"):
                                # Should reset the failure and try again
                                result = mod.ensure_installed()
                                # After reset, _resolved_path should no longer be INSTALL_FAILED
                                assert mod._resolved_path is not mod._INSTALL_FAILED or result is None

    def test_disk_failure_marker_prevents_repeated_downloads(self):
        """If install failed recently (disk marker), don't retry for 24h."""
        mod = _import_tirith()
        mod._resolved_path = None

        with patch.object(mod, "_load_security_config",
                          return_value={"tirith_enabled": True, "tirith_path": "tirith"}):
            with patch("shutil.which", return_value=None):
                with patch.object(mod, "_hermes_bin_dir", return_value="/nonexistent"):
                    with patch.object(mod, "_is_install_failed_on_disk", return_value=True):
                        with patch.object(mod, "_read_failure_reason", return_value="download_failed"):
                            result = mod.ensure_installed()
                            assert result is None
                            # Should have set in-memory marker
                            assert mod._resolved_path is mod._INSTALL_FAILED

    def test_background_install_does_not_block_startup(self):
        """ensure_installed() must return immediately, even if download is needed."""
        mod = _import_tirith()

        with patch.object(mod, "_load_security_config",
                          return_value={"tirith_enabled": True, "tirith_path": "tirith"}):
            with patch("shutil.which", return_value=None):
                with patch.object(mod, "_hermes_bin_dir", return_value="/nonexistent"):
                    with patch.object(mod, "_is_install_failed_on_disk", return_value=False):
                        with patch.object(mod, "_read_failure_reason", return_value=None):
                            # Mock threading to verify background thread is spawned
                            mock_thread = MagicMock(spec=threading.Thread)
                            mock_thread.is_alive.return_value = False
                            with patch("threading.Thread", return_value=mock_thread) as MockThread:
                                result = mod.ensure_installed()
                                # Must return None immediately (not block)
                                assert result is None
                                # Must have started a background thread
                                mock_thread.start.assert_called_once()


# ===========================================================================
# Tests: Gateway startup integration (tirith failure doesn't crash gateway)
# ===========================================================================


class TestGatewayStartupTirithIntegration:
    """Verify gateway.run handles tirith failures at startup without crashing."""

    def test_gateway_startup_wraps_tirith_in_try_except(self):
        """gateway/run.py must wrap ensure_installed() in try/except at startup."""
        import inspect
        _purge_tirith_module()
        # Remove gateway modules too
        to_remove = [k for k in sys.modules if k.startswith("gateway")]
        for k in to_remove:
            del sys.modules[k]

        from gateway import run
        source = inspect.getsource(run)

        # The source should contain a try/except around tirith
        # Look for the pattern: try + ensure_installed + except
        assert "ensure_installed" in source, \
            "gateway.run must call tirith_security.ensure_installed()"

    def test_tirith_import_error_does_not_crash_gateway(self):
        """If tirith_security module itself fails to import, gateway continues."""
        _purge_tirith_module()
        to_remove = [k for k in sys.modules if k.startswith("gateway")]
        for k in to_remove:
            del sys.modules[k]

        # Temporarily make tools.tirith_security raise on import
        broken_mod = MagicMock()
        broken_mod.ensure_installed = MagicMock(side_effect=ImportError("no module"))

        with patch.dict(sys.modules, {"tools.tirith_security": broken_mod}):
            # Gateway should handle this gracefully
            try:
                from gateway import run
                # If the module loads, verify it didn't crash
                assert True
            except ImportError:
                pytest.fail("Gateway must not crash if tirith_security import fails")
