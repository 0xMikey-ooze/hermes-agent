# Architecture: Railway Deployment Fix

## System Overview

```
Railway Container Lifecycle:
┌─────────────────────────────────────────────────┐
│  Container Start                                 │
│  1. python gateway/run.py                        │
│  2. Early health server binds $PORT (immediate)  │
│  3. Railway health check passes ✓                │
│  4. Telegram polling starts                      │
│  5. Early health server CLEANED UP               │
│  6. Full HermesWebAPI binds $PORT                │
│  7. Gateway running                              │
└─────────────────────────────────────────────────┘

Rolling Deploy (overlap period):
┌──────────────┐     ┌──────────────┐
│ Old Container │     │ New Container │
│ polling TG    │────▶│ 409 conflict  │
│ stops ~10-30s │     │ retry loop    │
└──────────────┘     │ connects ✓    │
                     └──────────────┘
```

## Component Changes

### 1. Early Health Server → Web API Handoff (`gateway/run.py`)

**Current flow (broken):**
```python
# Line 4588-4590 — early health server starts
_early_runner = _aiohttp_web.AppRunner(_early_app)
await _early_runner.setup()
await _aiohttp_web.TCPSite(_early_runner, "0.0.0.0", _early_port).start()

# ... later in Gateway._start_gateway() at line 926-934 ...
# Full web API tries same port → OSError
asyncio.create_task(_web_api.start(port=_dashboard_port))
```

**Fixed flow:**
```python
# In main(): store runner reference in a module-level variable
_EARLY_HEALTH_RUNNER = None  # module-level

# In main() after starting early health server:
global _EARLY_HEALTH_RUNNER
_EARLY_HEALTH_RUNNER = _early_runner

# In Gateway._start_gateway() before starting full web API:
global _EARLY_HEALTH_RUNNER
if _EARLY_HEALTH_RUNNER is not None:
    await _EARLY_HEALTH_RUNNER.cleanup()
    _EARLY_HEALTH_RUNNER = None

# Then start full web API on the now-free port
asyncio.create_task(_web_api.start(port=_dashboard_port))
```

### 2. Telegram Polling Retry (`gateway/platforms/telegram.py`)

**Current flow (broken):**
```python
async def _handle_polling_conflict(self, error):
    self._set_fatal_error("telegram_polling_conflict", message, retryable=True)
    await self._app.updater.stop()  # stops polling forever
    await self._notify_fatal_error()  # that's it — no retry
```

**Fixed flow:**
```python
# New constants
_CONFLICT_RETRY_DELAYS = [5, 10, 20, 30]  # seconds, 4 attempts
_CONFLICT_MAX_TOTAL_WAIT = 60  # seconds

async def _handle_polling_conflict(self, error):
    # Stop current polling
    await self._app.updater.stop()

    # Retry loop with backoff
    for attempt, delay in enumerate(_CONFLICT_RETRY_DELAYS, 1):
        logger.info("[%s] Telegram conflict — retry %d/%d in %ds",
                    self.name, attempt, len(_CONFLICT_RETRY_DELAYS), delay)
        await asyncio.sleep(delay)

        try:
            await self._app.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                error_callback=self._make_polling_error_callback(),
            )
            # Clear fatal error on successful reconnect
            self._clear_fatal_error()
            logger.info("[%s] Telegram polling resumed after conflict", self.name)
            return
        except Exception as retry_err:
            if not self._looks_like_polling_conflict(retry_err):
                raise  # different error, propagate
            logger.warning("[%s] Retry %d failed: %s", self.name, attempt, retry_err)

    # All retries exhausted
    self._set_fatal_error("telegram_polling_conflict", message, retryable=False)
    await self._notify_fatal_error()
```

### 3. Tirith Graceful Skip (`tools/tirith_security.py` + `railway.toml`)

**Approach:** Two-layer fix:
1. **Configuration:** Add `TIRITH_ENABLED=false` to `railway.toml` service variables
2. **Code:** When `TIRITH_ENABLED=false`, skip all download/install logic entirely (zero network calls, zero warnings)

**railway.toml change:**
```toml
[services.variables]
HERMES_PLATFORM = "telegram"
TIRITH_ENABLED = "false"
```

**Code change in `check_command_security()`:** Early return before any path resolution when disabled.

## API Contracts

No API contract changes — all fixes are internal to the gateway startup sequence. The existing REST API (`/api/status`, `/api/goals`, etc.) and SSE endpoint (`/api/events`) remain unchanged.

### Health Endpoint Contract (unchanged)
```
GET /health → {"status": "starting"|"healthy", "service": "hermes-gateway"}
GET /       → same as /health
```

### Internal Interface: Early Health Runner Handoff
```python
# Module-level variable in gateway/run.py
_EARLY_HEALTH_RUNNER: Optional[aiohttp.web.AppRunner] = None

# Gateway._start_gateway() calls:
async def _cleanup_early_health_server() -> None
```

## Error Handling Strategy

| Error | Current Behavior | New Behavior |
|-------|-----------------|--------------|
| Port in use (OSError) | Gateway crashes | Clean up early server first, then bind |
| Telegram 409 Conflict | Stop polling permanently | Retry 4x with backoff over 65s |
| Tirith cosign missing | WARNING + download attempt | Skip entirely when TIRITH_ENABLED=false |
| Telegram retry exhausted | N/A (new) | Set non-retryable fatal error, notify |

## Data Flow

No data model changes. No database migrations. No new dependencies.

## Files Modified

| File | Change | Team |
|------|--------|------|
| `gateway/run.py` | Store early health runner, clean up before web API starts | Backend |
| `gateway/platforms/telegram.py` | Add retry loop to `_handle_polling_conflict()` | Backend |
| `tools/tirith_security.py` | Early return when `TIRITH_ENABLED=false` | Backend |
| `railway.toml` | Add `TIRITH_ENABLED = "false"` | Backend |
| `tests/gateway/test_health_handoff.py` | Test early→full server transition | QA |
| `tests/gateway/test_telegram_conflict_retry.py` | Test polling retry with backoff | QA |
| `tests/tools/test_tirith_disabled.py` | Test tirith skip when disabled | QA |

## Dependencies

No new dependencies required. All fixes use existing libraries (aiohttp, python-telegram-bot, stdlib).
