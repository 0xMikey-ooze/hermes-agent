# Specification: Fix Railway Deployment — 3 Bugs

## Problem Statement

The Hermes gateway fails on Railway deployment with three distinct errors:

1. **OSError: port already in use** — The early health server (run.py:4588-4590) binds to `$PORT` immediately on startup, but is never cleaned up before the full `HermesWebAPI` (run.py:926-934) tries to bind the same port. Both use `int(os.getenv("PORT") or os.getenv("DASHBOARD_PORT", "3001"))`.

2. **Telegram 409 Conflict** — `"terminated by other getUpdates request"`. During Railway rolling deploys, the old container is still polling when the new container starts. The existing retry logic (`_handle_polling_conflict` in telegram.py:133-152) marks the error as retryable but doesn't implement an actual retry loop — it stops polling and never restarts.

3. **Tirith binary download fails** — `cosign not found`. The `_install_tirith()` function (tirith_security.py:282-369) requires cosign for provenance verification. Railway containers don't have cosign installed. While `tirith_fail_open=True` is the default, the download attempt still logs noisy warnings and wastes startup time.

## Root Cause Analysis

### Bug 1: Port Conflict
- **File:** `gateway/run.py` lines 4569-4595 (early health server) and lines 919-937 (full web API)
- **Cause:** `_early_runner` is a local variable in the module-level `main()` function. It's never passed to the `Gateway` class, so `_start_gateway()` can't clean it up before starting `HermesWebAPI` on the same port.
- **Fix:** Store `_early_runner` so the Gateway can call `await _early_runner.cleanup()` before starting the full web API. Alternatively, have the full web API reuse the early runner's socket.

### Bug 2: Telegram 409 Polling Conflict
- **File:** `gateway/platforms/telegram.py` lines 124-152
- **Cause:** `_handle_polling_conflict()` sets a retryable fatal error and stops the updater, but nothing ever retries. The `retryable=True` flag is informational only — no code reads it to schedule a reconnect.
- **Fix:** Add a retry loop in the conflict handler: after stopping polling, wait with exponential backoff (5s, 10s, 20s) and attempt `start_polling()` again. The old container typically stops within 10-30 seconds during Railway rolling deploys.

### Bug 3: Tirith Download Failure
- **File:** `tools/tirith_security.py` lines 282-369
- **Cause:** Cosign is not available in Railway containers. The install function correctly fails and marks the failure, but the process generates multiple warning-level log lines during every startup.
- **Fix:** (a) Detect containerized/CI environments and skip the download attempt entirely. (b) Reduce log level from WARNING to DEBUG when cosign is missing in non-interactive environments. (c) Ensure `TIRITH_ENABLED=false` in railway.toml so tirith scanning is disabled on Railway.

## Success Criteria

1. Gateway starts cleanly on Railway: early health server responds within 2s of container start, full web API takes over the port without OSError.
2. During rolling deploys, the new container's Telegram adapter retries polling until the old container releases the bot token (up to 60s), then connects successfully.
3. No tirith-related errors or warnings in Railway deploy logs.

## Out of Scope

- Switching Telegram from polling to webhooks (larger architectural change, not needed for this fix)
- Modifying the tirith binary or cosign verification logic
- Dashboard/frontend changes (no frontend team work needed for these backend bugs)
