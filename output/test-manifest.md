# Test Manifest — Railway Deployment Bug Fixes

## Overview
37 tests across 3 files covering the 3 Railway deployment bugs.
Framework: pytest (with pytest-asyncio for async tests).

---

## Bug #1: PORT env var (tests/test_port_env_var.py) — 8 tests

| Test | Purpose |
|------|---------|
| `test_uses_port_env_var_when_set` | $PORT env var is read and used as bind port |
| `test_falls_back_to_dashboard_port` | Falls back to $DASHBOARD_PORT when $PORT unset |
| `test_defaults_to_3001_when_no_env` | Defaults to 3001 when no env vars set |
| `test_port_is_not_hardcoded_8080` | Regression: never hardcodes port 8080 |
| `test_port_env_var_takes_precedence_over_dashboard_port` | $PORT wins over $DASHBOARD_PORT |
| `test_port_env_var_is_integer` | Port cast to int, not left as string |
| `test_early_port_matches_dashboard_port` | Health server and web API use same port (no conflict) |
| `test_web_api_host_port_from_env` | HermesWebAPI source has no hardcoded 8080 |

## Bug #2: Telegram 409 Conflict (tests/test_telegram_polling_conflict.py) — 14 tests

| Test | Purpose |
|------|---------|
| `test_detects_conflict_by_class_name` | Detects Conflict exception class |
| `test_detects_conflict_by_getupdates_message` | Detects "terminated by other getUpdates" text |
| `test_detects_conflict_by_another_instance_message` | Detects "another bot instance" text |
| `test_ignores_unrelated_errors` | TimeoutError not misidentified as conflict |
| `test_ignores_generic_runtime_error` | Generic errors not misidentified |
| `test_case_insensitive_detection` | Detection works regardless of case |
| `test_conflict_marked_retryable` | 409 sets retryable=True for rolling deploy recovery |
| `test_conflict_not_marked_fatal_permanently` | Conflict doesn't permanently kill gateway |
| `test_conflict_stops_updater` | Updater.stop() called after conflict |
| `test_conflict_notifies_fatal_error_system` | _notify_fatal_error called for observability |
| `test_idempotent_when_already_in_conflict` | No double-fire if already in conflict state |
| `test_updater_stop_failure_does_not_crash` | Updater stop error is swallowed |
| `test_non_conflict_error_is_logged_not_handled` | Non-conflict errors don't trigger handler |
| `test_conflict_error_triggers_handler` | Conflict errors route to handler |

## Bug #3: Tirith Optional Install (tests/test_tirith_optional_install.py) — 15 tests

| Test | Purpose |
|------|---------|
| `test_returns_none_when_tirith_disabled` | Disabled config → None immediately |
| `test_returns_none_when_binary_not_found` | Binary missing → None (spawns background thread) |
| `test_returns_path_when_binary_on_path` | Binary found → returns path |
| `test_does_not_raise_on_explicit_path_missing` | Explicit path missing → None (no crash) |
| `test_unsupported_platform_returns_none` | Unsupported OS → (None, "unsupported_platform") |
| `test_download_failure_returns_none` | Network error → (None, "download_failed") |
| `test_cosign_missing_returns_none` | No cosign binary → (None, "cosign_missing") |
| `test_cosign_artifacts_unavailable` | Sig files missing → (None, "cosign_artifacts_unavailable") |
| `test_cosign_verification_failed` | Cosign rejects signature → (None, reason) |
| `test_cosign_exec_failed` | Cosign execution error → (None, reason) |
| `test_cosign_missing_is_retryable` | Failure clears when cosign later appears |
| `test_disk_failure_marker_prevents_repeated_downloads` | 24h disk marker prevents download spam |
| `test_background_install_does_not_block_startup` | ensure_installed() returns immediately |
| `test_gateway_startup_wraps_tirith_in_try_except` | gateway.run has try/except around tirith |
| `test_tirith_import_error_does_not_crash_gateway` | Import failure doesn't crash gateway |
