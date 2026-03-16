# Shared Context — Railway Deployment Fix

## What Changed

Three bugs fixed in Railway deployment:

### Bug 1: Port Conflict (OSError)
- **Root cause:** Early health server binds `$PORT` at startup but is never cleaned up before `HermesWebAPI` tries to bind the same port
- **Fix:** Store `_EARLY_HEALTH_RUNNER` at module level in `gateway/run.py`, clean it up in `Gateway._start_gateway()` before starting the full web API
- **Files:** `gateway/run.py`

### Bug 2: Telegram 409 Conflict
- **Root cause:** `_handle_polling_conflict()` stops polling but never retries, so the new container gives up even though the old container releases the token within 10-30s
- **Fix:** Add retry loop with backoff [5s, 10s, 20s, 30s] in `_handle_polling_conflict()`. Extract `_make_polling_error_callback()` method for reuse
- **Files:** `gateway/platforms/telegram.py`

### Bug 3: Tirith cosign not found
- **Root cause:** Railway containers don't have cosign installed, tirith download fails with warnings
- **Fix:** Set `TIRITH_ENABLED=false` in `railway.toml`. When disabled, `check_command_security()` returns allow immediately without any network calls
- **Files:** `tools/tirith_security.py`, `railway.toml`

## API Contracts

**No changes to any API endpoints.** The REST API and SSE stream behave identically.

## Cross-Team Dependencies

- **Team 1 → Team 3:** QA tests import from `gateway.run`, `gateway.platforms.telegram`, `tools.tirith_security`. Tests mock internal methods — function signatures must not change beyond what's specified.
- **Team 2:** No work required.

## Key Decisions

1. **No webhook switch:** Polling with retry is simpler and sufficient for Railway rolling deploys
2. **Retry delays [5, 10, 20, 30]:** Total 65s wait covers Railway's typical 10-30s container shutdown
3. **`TIRITH_ENABLED=false` in railway.toml:** Config-level disable rather than code-level container detection — simpler and more explicit
