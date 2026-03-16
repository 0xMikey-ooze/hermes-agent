# Team 1: Backend — Fix Railway Deployment Bugs

**Branch:** `fix/railway-deploy`
**Scope:** `gateway/run.py`, `gateway/platforms/telegram.py`, `tools/tirith_security.py`, `railway.toml`

---

## Task 1: Fix Port Conflict — Early Health Server Handoff

**File:** `gateway/run.py`
**Problem:** Early health server (line 4588-4590) binds `$PORT` but is never cleaned up before `HermesWebAPI` (line 926-934) tries to bind the same port → `OSError: address already in use`.

### Steps

1. Add a module-level variable to store the early health runner reference:

```python
# Add near the top of the file, after imports (around line 30-50)
_EARLY_HEALTH_RUNNER: "web.AppRunner | None" = None
```

2. In the `main()` function (around line 4588-4594), store the runner reference:

```python
# Replace the current early health server block (lines 4569-4594)
global _EARLY_HEALTH_RUNNER
_early_port = int(os.getenv("PORT") or os.getenv("DASHBOARD_PORT", "3001"))
try:
    from aiohttp import web as _aiohttp_web
    import logging as _logging
    _early_log = _logging.getLogger("hermes.health")

    async def _health(request):
        return _aiohttp_web.Response(
            text='{"status":"starting","service":"hermes-gateway"}',
            content_type="application/json",
        )

    _early_app = _aiohttp_web.Application()
    _early_app.router.add_get("/", _health)
    _early_app.router.add_get("/health", _health)
    _early_runner = _aiohttp_web.AppRunner(_early_app)
    await _early_runner.setup()
    await _aiohttp_web.TCPSite(_early_runner, "0.0.0.0", _early_port).start()
    _EARLY_HEALTH_RUNNER = _early_runner  # <-- NEW: store for later cleanup
    _early_log.info("Early health server listening on port %d", _early_port)
    print(f"[hermes] Health server listening on port {_early_port}", flush=True)
except Exception as _early_err:
    print(f"[hermes] Early health server failed: {_early_err}", flush=True)
```

3. In `Gateway._start_gateway()` (around line 919-937), clean up the early server before starting the full API:

```python
# INSERT before the "Start Hermes Web API" block at line 919:
# Clean up early health server so the full web API can bind the port
global _EARLY_HEALTH_RUNNER
if _EARLY_HEALTH_RUNNER is not None:
    try:
        await _EARLY_HEALTH_RUNNER.cleanup()
        logger.info("Early health server stopped — handing off to full Web API")
    except Exception as _cleanup_err:
        logger.warning("Early health server cleanup failed: %s", _cleanup_err)
    _EARLY_HEALTH_RUNNER = None

# Start Hermes Web API / Dashboard backend
try:
    from gateway.web_api import HermesWebAPI
    # ... (existing code unchanged)
```

### Verification
- `python -c "import gateway.run"` — module imports without error
- Deploy to Railway: early health server responds on `$PORT` within 2s, full API takes over cleanly

---

## Task 2: Fix Telegram 409 Polling Conflict with Retry Loop

**File:** `gateway/platforms/telegram.py`
**Problem:** `_handle_polling_conflict()` (line 133-152) stops polling but never retries. During Railway rolling deploys, the old container releases the token within 10-30s, but the new container has already given up.

### Steps

1. Add retry constants near the top of the class (after line 108):

```python
# Retry delays for polling conflicts during rolling deploys
_CONFLICT_RETRY_DELAYS = [5, 10, 20, 30]  # seconds between retries
```

2. Extract the error callback factory into a method so the retry loop can create fresh callbacks:

```python
def _make_polling_error_callback(self) -> callable:
    """Create a polling error callback bound to the current event loop."""
    loop = asyncio.get_running_loop()

    def _callback(error: Exception) -> None:
        if not self._looks_like_polling_conflict(error):
            logger.error("[%s] Telegram polling error: %s", self.name, error, exc_info=True)
            return
        if self._polling_error_task and not self._polling_error_task.done():
            return
        self._polling_error_task = loop.create_task(self._handle_polling_conflict(error))

    return _callback
```

3. Update `connect()` (line 214-226) to use the new factory:

```python
# Replace the inline _polling_error_callback definition and start_polling call:
await self._app.updater.start_polling(
    allowed_updates=Update.ALL_TYPES,
    drop_pending_updates=True,
    error_callback=self._make_polling_error_callback(),
)
```

4. Rewrite `_handle_polling_conflict()` with retry logic:

```python
async def _handle_polling_conflict(self, error: Exception) -> None:
    """Handle Telegram 409 conflict with retry for rolling deploys."""
    if self.has_fatal_error and self.fatal_error_code == "telegram_polling_conflict":
        return

    logger.warning("[%s] Telegram polling conflict detected: %s", self.name, error)

    # Stop current polling
    try:
        if self._app and self._app.updater and self._app.updater.running:
            await self._app.updater.stop()
    except Exception as stop_err:
        logger.warning("[%s] Error stopping Telegram polling: %s", self.name, stop_err)

    # Retry with backoff — during rolling deploys the old container
    # typically releases the bot token within 10-30 seconds
    for attempt, delay in enumerate(self._CONFLICT_RETRY_DELAYS, 1):
        logger.info(
            "[%s] Telegram conflict — retry %d/%d in %ds",
            self.name, attempt, len(self._CONFLICT_RETRY_DELAYS), delay,
        )
        await asyncio.sleep(delay)

        try:
            await self._app.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                error_callback=self._make_polling_error_callback(),
            )
            # Success — clear any fatal error state
            if self.has_fatal_error and self.fatal_error_code == "telegram_polling_conflict":
                self._clear_fatal_error()
            logger.info("[%s] Telegram polling resumed after conflict (attempt %d)", self.name, attempt)
            return
        except Exception as retry_err:
            if self._looks_like_polling_conflict(retry_err):
                logger.warning("[%s] Retry %d still conflicted: %s", self.name, attempt, retry_err)
                continue
            # Different error — stop retrying
            logger.error("[%s] Unexpected error during polling retry: %s", self.name, retry_err, exc_info=True)
            break

    # All retries exhausted — give up permanently
    message = (
        "Another Telegram bot poller is already using this token. "
        "Hermes retried polling 4 times over 65 seconds but the conflict persists. "
        "Make sure only one gateway instance is running for this bot token."
    )
    logger.error("[%s] %s", self.name, message)
    self._set_fatal_error("telegram_polling_conflict", message, retryable=False)
    await self._notify_fatal_error()
```

5. Check if `_clear_fatal_error` exists on `BasePlatformAdapter`. If not, add it:

```python
# In gateway/platforms/base.py, verify this method exists:
def _clear_fatal_error(self):
    """Clear a previously set fatal error (e.g., after successful reconnect)."""
    self._fatal_error = None
    self._fatal_error_code = None
    self._fatal_error_retryable = False
```

### Verification
- Unit test: mock the updater, simulate 409 then success on retry 2
- Integration: deploy two Railway instances simultaneously, verify new one connects

---

## Task 3: Disable Tirith on Railway

**File:** `tools/tirith_security.py`, `railway.toml`
**Problem:** Tirith auto-install tries to download the binary and verify with cosign, which isn't available in Railway containers. Generates noisy warnings.

### Steps

1. **Update `railway.toml`** — add `TIRITH_ENABLED = "false"`:

```toml
[build]
builder = "nixpacks"

[[services]]
name = "hermes"
source = "."
startCommand = "python gateway/run.py"

[services.variables]
HERMES_PLATFORM = "telegram"
TIRITH_ENABLED = "false"
```

2. **Update `check_command_security()` in `tirith_security.py`** — ensure early return when disabled produces zero log noise. Find the main `check_command_security()` function and verify the disabled check is the very first thing:

```python
def check_command_security(command: str, cwd: str | None = None) -> dict:
    """Check a command for security threats using tirith.

    Returns dict with 'verdict' ('allow'|'block'|'warn'), 'findings', 'summary'.
    """
    cfg = _load_security_config()
    if not cfg["tirith_enabled"]:
        return {"verdict": "allow", "findings": [], "summary": "tirith disabled"}
    # ... rest of function
```

This should already exist — verify it's the first check before any path resolution or download attempts.

3. **Verify `_resolve_tirith_path` is not called when disabled** — trace the call path from `check_command_security()` to ensure `_resolve_tirith_path()` (which triggers the download) is only called after the enabled check.

### Verification
- Set `TIRITH_ENABLED=false`, start gateway — zero tirith-related log lines
- `grep -n "tirith" gateway.log` returns nothing when disabled

---

## Task 4: Verify and Commit

1. Run `python -c "import gateway.run; import gateway.platforms.telegram; import tools.tirith_security"` to verify imports
2. Run existing tests: `python -m pytest tests/gateway/ tests/tools/test_tirith*.py -x -q`
3. Commit each fix separately:
   - `git add gateway/run.py && git commit -m "fix(gateway): clean up early health server before starting full web API"`
   - `git add gateway/platforms/telegram.py && git commit -m "fix(telegram): retry polling on 409 conflict during rolling deploys"`
   - `git add tools/tirith_security.py railway.toml && git commit -m "fix(tirith): disable tirith on Railway to avoid cosign download failures"`
4. Push: `git push origin fix/railway-deploy`

---

## Important Notes

- **Do NOT change the port logic** — `$PORT` reading is already correct. The bug is the missing cleanup of the early health server, not port configuration.
- **Do NOT switch to webhooks** — polling with retry is sufficient and much simpler.
- **Check `BasePlatformAdapter`** for `_clear_fatal_error` — if it doesn't exist, add it to `gateway/platforms/base.py`.
- **Follow existing patterns** — the codebase uses `logger.info/warning/error` consistently, no print statements except in `main()`.
