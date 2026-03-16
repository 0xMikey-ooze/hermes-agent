# Team 3: QA — Test Specifications for Railway Deployment Fixes

**Branch:** `fix/railway-deploy-tests`
**Scope:** `tests/gateway/`, `tests/tools/`

---

## Test 1: Early Health Server → Web API Handoff

**File:** `tests/gateway/test_health_handoff.py`
**Tests the fix for:** Port conflict (Bug 1)

### Test Cases

#### `test_early_health_server_cleanup_before_web_api`
- **Setup:** Create an early health server runner on a random free port, store it in `gateway.run._EARLY_HEALTH_RUNNER`
- **Action:** Call the cleanup logic that runs before `HermesWebAPI.start()`
- **Assert:**
  - `_EARLY_HEALTH_RUNNER` is `None` after cleanup
  - A new `aiohttp.web.TCPSite` can bind the same port without `OSError`
- **Code pattern:**

```python
import asyncio
import pytest
from aiohttp import web
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_early_health_server_cleanup_before_web_api():
    """Early health server must be cleaned up before full web API binds the port."""
    import gateway.run as run_module

    # Create a minimal aiohttp app on a free port
    app = web.Application()
    app.router.add_get("/health", lambda r: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)  # port 0 = OS picks free port
    await site.start()
    actual_port = site._server.sockets[0].getsockname()[1]

    # Store as "early health runner"
    run_module._EARLY_HEALTH_RUNNER = runner

    # Simulate the cleanup that _start_gateway should perform
    await runner.cleanup()
    run_module._EARLY_HEALTH_RUNNER = None

    # Now bind the same port — should NOT raise OSError
    app2 = web.Application()
    app2.router.add_get("/health", lambda r: web.Response(text="ok"))
    runner2 = web.AppRunner(app2)
    await runner2.setup()
    site2 = web.TCPSite(runner2, "127.0.0.1", actual_port)
    await site2.start()  # Would raise OSError if port still held
    await runner2.cleanup()
```

#### `test_early_health_server_none_is_noop`
- **Setup:** Set `_EARLY_HEALTH_RUNNER = None`
- **Action:** Run the cleanup logic
- **Assert:** No exception raised, graceful no-op

#### `test_early_health_server_cleanup_failure_doesnt_crash`
- **Setup:** Create a mock runner whose `cleanup()` raises `RuntimeError`
- **Action:** Run the cleanup logic
- **Assert:** Exception is caught and logged, `_EARLY_HEALTH_RUNNER` is set to `None`, gateway continues

---

## Test 2: Telegram Polling Conflict Retry

**File:** `tests/gateway/test_telegram_conflict_retry.py`
**Tests the fix for:** Telegram 409 (Bug 2)

### Test Cases

#### `test_conflict_retries_and_succeeds`
- **Setup:** Mock `Application.updater.start_polling` to raise `Conflict("terminated by other getUpdates")` on first call, succeed on second
- **Action:** Trigger `_handle_polling_conflict()`
- **Assert:**
  - `updater.stop()` called once
  - `asyncio.sleep` called with first delay value (5s)
  - `updater.start_polling()` called twice (initial fail + successful retry)
  - Fatal error state is cleared after success
  - Adapter is NOT in fatal error state

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from gateway.platforms.telegram import TelegramAdapter
from gateway.config import PlatformConfig, Platform

class FakeConflict(Exception):
    """Mimics telegram.error.Conflict."""
    pass
FakeConflict.__name__ = "Conflict"

@pytest.mark.asyncio
async def test_conflict_retries_and_succeeds():
    """Polling retry succeeds on second attempt after 409 conflict."""
    config = PlatformConfig(platform=Platform.TELEGRAM, token="fake-token")
    adapter = TelegramAdapter(config)

    # Mock the app and updater
    mock_updater = AsyncMock()
    mock_updater.running = True
    mock_updater.stop = AsyncMock()

    # First start_polling raises conflict, second succeeds
    conflict = FakeConflict("terminated by other getUpdates request")
    mock_updater.start_polling = AsyncMock(side_effect=[conflict, None])

    mock_app = MagicMock()
    mock_app.updater = mock_updater
    adapter._app = mock_app

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await adapter._handle_polling_conflict(conflict)

    assert mock_updater.stop.call_count == 1
    assert mock_updater.start_polling.call_count == 1  # successful retry
    assert not adapter.has_fatal_error
```

#### `test_conflict_exhausts_retries`
- **Setup:** Mock `start_polling` to always raise `Conflict`
- **Action:** Trigger `_handle_polling_conflict()`
- **Assert:**
  - `start_polling` called `len(_CONFLICT_RETRY_DELAYS)` times
  - `asyncio.sleep` called with each delay value
  - Fatal error is set with `retryable=False`
  - `_notify_fatal_error()` was called

```python
@pytest.mark.asyncio
async def test_conflict_exhausts_retries():
    """All retries fail — fatal error is set as non-retryable."""
    config = PlatformConfig(platform=Platform.TELEGRAM, token="fake-token")
    adapter = TelegramAdapter(config)

    mock_updater = AsyncMock()
    mock_updater.running = True
    conflict = FakeConflict("terminated by other getUpdates request")
    mock_updater.start_polling = AsyncMock(side_effect=conflict)

    mock_app = MagicMock()
    mock_app.updater = mock_updater
    adapter._app = mock_app
    adapter._notify_fatal_error = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await adapter._handle_polling_conflict(conflict)

    assert adapter.has_fatal_error
    assert adapter.fatal_error_code == "telegram_polling_conflict"
    assert not adapter.fatal_error_retryable
    adapter._notify_fatal_error.assert_called_once()
```

#### `test_conflict_handler_idempotent`
- **Setup:** Set adapter to already have `telegram_polling_conflict` fatal error
- **Action:** Call `_handle_polling_conflict()` again
- **Assert:** Returns immediately without retrying (no `updater.stop()` call)

#### `test_looks_like_polling_conflict_detection`
- **Input/Output test cases:**

```python
def test_looks_like_polling_conflict_detection():
    """Static method correctly identifies 409 conflict errors."""
    # Positive cases
    conflict_err = FakeConflict("terminated by other getUpdates request")
    assert TelegramAdapter._looks_like_polling_conflict(conflict_err) is True

    another_err = Exception("another bot instance is running")
    assert TelegramAdapter._looks_like_polling_conflict(another_err) is True

    # Negative cases
    timeout_err = Exception("Connection timed out")
    assert TelegramAdapter._looks_like_polling_conflict(timeout_err) is False

    network_err = Exception("Network unreachable")
    assert TelegramAdapter._looks_like_polling_conflict(network_err) is False
```

#### `test_non_conflict_error_during_retry_propagates`
- **Setup:** Mock `start_polling` to raise `ConnectionError` (not a conflict)
- **Action:** Trigger retry after initial conflict
- **Assert:** Non-conflict error breaks the retry loop, fatal error is set

---

## Test 3: Tirith Disabled Skip

**File:** `tests/tools/test_tirith_disabled.py`
**Tests the fix for:** Tirith download failure (Bug 3)

### Test Cases

#### `test_tirith_disabled_returns_allow`
- **Setup:** Set `TIRITH_ENABLED=false` env var
- **Action:** Call `check_command_security("rm -rf /", cwd="/tmp")`
- **Assert:**
  - Returns `{"verdict": "allow", ...}`
  - No network calls made (mock `urllib.request.urlopen` and assert not called)
  - No log warnings emitted

```python
import os
import pytest
from unittest.mock import patch

def test_tirith_disabled_returns_allow(monkeypatch):
    """When TIRITH_ENABLED=false, all commands are allowed without network calls."""
    monkeypatch.setenv("TIRITH_ENABLED", "false")

    # Reset module-level caches
    import tools.tirith_security as ts
    ts._resolved_path = None

    with patch("urllib.request.urlopen") as mock_urlopen:
        result = ts.check_command_security("echo hello")

    assert result["verdict"] == "allow"
    mock_urlopen.assert_not_called()
```

#### `test_tirith_disabled_no_path_resolution`
- **Setup:** Set `TIRITH_ENABLED=false`
- **Action:** Call `check_command_security()`
- **Assert:** `_resolve_tirith_path` was never called

```python
def test_tirith_disabled_no_path_resolution(monkeypatch):
    """Disabled tirith skips path resolution entirely."""
    monkeypatch.setenv("TIRITH_ENABLED", "false")

    import tools.tirith_security as ts

    with patch.object(ts, "_resolve_tirith_path") as mock_resolve:
        ts.check_command_security("ls -la")

    mock_resolve.assert_not_called()
```

#### `test_tirith_enabled_default_true`
- **Setup:** No env vars set
- **Action:** Load config
- **Assert:** `tirith_enabled` is `True` by default

#### `test_tirith_env_bool_parsing`
- **Input/Output:**

```python
@pytest.mark.parametrize("val,expected", [
    ("false", False),
    ("False", False),
    ("FALSE", False),
    ("0", False),
    ("no", False),
    ("true", True),
    ("True", True),
    ("1", True),
    ("yes", True),
])
def test_tirith_env_bool_parsing(monkeypatch, val, expected):
    monkeypatch.setenv("TIRITH_ENABLED", val)
    from tools.tirith_security import _env_bool
    assert _env_bool("TIRITH_ENABLED", True) == expected
```

---

## Test 4: Railway.toml Configuration

**File:** `tests/test_railway_config.py`

#### `test_railway_toml_has_tirith_disabled`
- **Action:** Read and parse `railway.toml`
- **Assert:** `services.variables.TIRITH_ENABLED` is `"false"`

```python
import tomllib
from pathlib import Path

def test_railway_toml_has_tirith_disabled():
    """railway.toml must disable tirith for Railway deployments."""
    toml_path = Path(__file__).parent.parent / "railway.toml"
    with open(toml_path, "rb") as f:
        config = tomllib.load(f)

    # railway.toml uses [[services]] array
    services = config.get("services", [])
    if isinstance(services, list):
        hermes = next((s for s in services if s.get("name") == "hermes"), None)
        variables = hermes.get("variables", {}) if hermes else {}
    else:
        variables = services.get("variables", {})

    assert variables.get("TIRITH_ENABLED") == "false"
```

---

## Test 5: Integration — Full Gateway Startup Sequence

**File:** `tests/gateway/test_railway_startup_integration.py`

#### `test_full_startup_no_port_conflict`
- **Setup:** Mock Telegram, set `PORT=<free-port>`, `TIRITH_ENABLED=false`
- **Action:** Run the startup sequence: early health server → gateway init → web API
- **Assert:**
  - Early health server responds to `GET /health`
  - After gateway starts, full API responds to `GET /api/status`
  - No `OSError` during transition

#### `test_startup_with_telegram_conflict_recovery`
- **Setup:** Mock Telegram to return 409 on first poll, succeed on second
- **Action:** Run startup
- **Assert:** Gateway reaches `running` state after retry

---

## Edge Cases to Cover

1. **Race condition:** What if the early health server receives a request during cleanup? → Should return gracefully (aiohttp handles this)
2. **Telegram conflict on first connect (not just retry):** The initial `connect()` already handles this via `_polling_error_callback` → verify the callback routes to the new retry-enabled handler
3. **Multiple concurrent conflicts:** `_polling_error_task` guard prevents duplicate handlers → verify with test
4. **Tirith module-level state:** `_resolved_path` is module-level → `monkeypatch` must reset it between tests

---

## Test Execution Commands

```bash
# Run all new tests
python -m pytest tests/gateway/test_health_handoff.py tests/gateway/test_telegram_conflict_retry.py tests/tools/test_tirith_disabled.py tests/test_railway_config.py -v

# Run with coverage for changed files
python -m pytest tests/gateway/test_health_handoff.py tests/gateway/test_telegram_conflict_retry.py tests/tools/test_tirith_disabled.py --cov=gateway.run --cov=gateway.platforms.telegram --cov=tools.tirith_security --cov-report=term-missing

# Run existing tests to ensure no regressions
python -m pytest tests/gateway/ tests/tools/test_tirith*.py -x -q
```

---

## Important Notes

- **Use `monkeypatch.setenv`** for environment variables, not `os.environ` directly
- **Reset module-level caches** (`_resolved_path`, `_EARLY_HEALTH_RUNNER`) in test setup/teardown
- **Mock `asyncio.sleep`** in retry tests to avoid 65s test runtime
- **Use `pytest.mark.asyncio`** for all async test functions
- **Follow existing test patterns** in `tests/gateway/` — check imports and fixtures used there
