# Dependencies

## No New Dependencies Required

All three fixes use existing libraries already in `requirements.txt`:

| Library | Version | Used For |
|---------|---------|----------|
| `aiohttp` | `>=3.9.0` | Early health server, Web API (already installed) |
| `python-telegram-bot` | `>=20.0` | Telegram polling with retry (already installed) |
| Python stdlib | 3.11+ | `asyncio.sleep`, `os.getenv`, `logging` |

## Existing Install Command

```bash
pip install -r requirements.txt
```

## No New Environment Variables

Existing variables used:
- `PORT` — Railway-injected HTTP port (already read)
- `DASHBOARD_PORT` — Fallback port for local dev (already read)
- `TIRITH_ENABLED` — Already supported by `tirith_security.py`, now set to `false` in `railway.toml`

## Test Dependencies

Tests use existing test infrastructure:
- `pytest` + `pytest-asyncio` (already in dev deps)
- `unittest.mock` (stdlib)
- `tomllib` (stdlib, Python 3.11+)
