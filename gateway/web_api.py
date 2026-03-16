"""Hermes-native Web API for the dashboard.

Provides a REST + SSE API that the Hermes dashboard and external tools
use to inspect and control the gateway.

Usage:
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=agi_client, config=config)
    app = api.create_app()
    # Run standalone
    await api.start(port=3001)
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from aiohttp import web
except ImportError:  # pragma: no cover
    web = None  # type: ignore[assignment]

_START_TIME = time.time()
_DEFAULT_REPOS_FILE = Path.home() / ".hermes" / "watched_repos.json"
_DEFAULT_SKILLS_PATH = Path(__file__).parent.parent / "skills"


class HermesWebAPI:
    """Aiohttp-based Web API exposing Hermes gateway internals.

    Args:
        agi_client: An AgiClient instance (or compatible mock).
        config:     Gateway config dict (or GatewayConfig object).
        repos_file: Path to watched_repos.json (default: ~/.hermes/watched_repos.json).
        skills_path: Path to the skills directory.
        cors_origins: Comma-separated allowed origins (default: *).
    """

    def __init__(
        self,
        agi_client: Any,
        config: Any = None,
        repos_file: Optional[Path] = None,
        skills_path: Optional[Path] = None,
        cors_origins: str = "*",
    ):
        self.agi_client = agi_client
        self.config = config or {}
        self.repos_file = Path(repos_file) if repos_file else _DEFAULT_REPOS_FILE
        self.skills_path = Path(skills_path) if skills_path else _DEFAULT_SKILLS_PATH
        self.cors_origins = cors_origins
        self._runner: Optional[Any] = None

    # ── Helpers ───────────────────────────────────────────────────────────

    def _get_api_key(self) -> Optional[str]:
        """Return configured DASHBOARD_API_KEY or None if auth is disabled."""
        return os.environ.get("DASHBOARD_API_KEY") or None

    def _cors_headers(self) -> Dict[str, str]:
        return {
            "Access-Control-Allow-Origin": self.cors_origins,
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-API-Key",
        }

    def _json(self, data: Any, status: int = 200) -> "web.Response":
        headers = self._cors_headers()
        return web.Response(
            text=json.dumps(data),
            status=status,
            content_type="application/json",
            headers=headers,
        )

    def _error(self, message: str, status: int = 400) -> "web.Response":
        return self._json({"error": message}, status=status)

    def _read_repos(self) -> List[Dict]:
        try:
            if self.repos_file.exists():
                return json.loads(self.repos_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _write_repos(self, repos: List[Dict]) -> None:
        self.repos_file.parent.mkdir(parents=True, exist_ok=True)
        self.repos_file.write_text(json.dumps(repos, indent=2), encoding="utf-8")

    def _config_value(self, key: str, default: Any = None) -> Any:
        if isinstance(self.config, dict):
            return self.config.get(key, default)
        return getattr(self.config, key, default)

    # ── Middleware ────────────────────────────────────────────────────────

    @web.middleware
    async def _auth_middleware(self, request: "web.Request", handler):
        """Optional API key auth. Skipped when DASHBOARD_API_KEY is not set."""
        # OPTIONS preflight — always allow
        if request.method == "OPTIONS":
            return await handler(request)

        required_key = self._get_api_key()
        if required_key:
            sent_key = request.headers.get("X-API-Key", "")
            if sent_key != required_key:
                return web.Response(
                    text=json.dumps({"error": "Unauthorized"}),
                    status=401,
                    content_type="application/json",
                    headers=self._cors_headers(),
                )
        return await handler(request)

    @web.middleware
    async def _cors_middleware(self, request: "web.Request", handler):
        """Inject CORS headers on every response."""
        if request.method == "OPTIONS":
            return web.Response(
                status=204,
                headers=self._cors_headers(),
            )
        response = await handler(request)
        for k, v in self._cors_headers().items():
            response.headers[k] = v
        return response

    # ── Route handlers ────────────────────────────────────────────────────

    async def _handle_status(self, request: "web.Request") -> "web.Response":
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        gateway_state_path = hermes_home / "gateway_state.json"
        gateway_running = False
        try:
            if gateway_state_path.exists():
                state = json.loads(gateway_state_path.read_text())
                gateway_running = state.get("gateway_state") == "running"
        except Exception:
            pass

        return self._json({
            "version": self._config_value("version", "0.2.0"),
            "uptime_seconds": time.time() - _START_TIME,
            "model": self._config_value("model", os.environ.get("HERMES_MODEL", "unknown")),
            "platform": self._config_value("platform", "hermes-gateway"),
            "gateway_running": gateway_running,
        })

    async def _handle_get_goals(self, request: "web.Request") -> "web.Response":
        try:
            result = self.agi_client.goal_status()
            goals = result.get("goals", []) if isinstance(result, dict) else result
        except Exception as exc:
            logger.warning("goal_status failed: %s", exc)
            goals = []
        return self._json({"goals": goals})

    async def _handle_post_goals(self, request: "web.Request") -> "web.Response":
        try:
            body = await request.json()
        except Exception:
            return self._error("Invalid JSON body")

        repo = body.get("repo", "").strip()
        description = body.get("description", "").strip()
        if not repo:
            return self._error("Missing required field: repo")
        if not description:
            return self._error("Missing required field: description")

        priority = body.get("priority", "normal")
        goal_text = f"[{repo}] {description}"
        try:
            tasks = self.agi_client.goal_decompose(
                goal_text,
                context={"repo": repo, "priority": priority},
            )
        except Exception as exc:
            logger.warning("goal_decompose failed: %s", exc)
            tasks = []

        return self._json({"tasks": tasks}, status=201)

    async def _handle_delete_goal(self, request: "web.Request") -> "web.Response":
        task_id = request.match_info["id"]
        try:
            # Post a cancel signal to the blackboard
            self.agi_client.blackboard_put(  # type: ignore[attr-defined]
                key=f"cancel:{task_id}",
                value={"task_id": task_id, "signal": "cancel"},
            )
        except Exception as exc:
            # blackboard_put is optional; best-effort
            logger.debug("blackboard cancel for %s failed: %s", task_id, exc)
        return self._json({"cancelled": task_id})

    async def _handle_get_repos(self, request: "web.Request") -> "web.Response":
        return self._json({"repos": self._read_repos()})

    async def _handle_post_repos(self, request: "web.Request") -> "web.Response":
        try:
            body = await request.json()
        except Exception:
            return self._error("Invalid JSON body")

        owner = body.get("owner", "").strip()
        repo = body.get("repo", "").strip()
        if not owner:
            return self._error("Missing required field: owner")
        if not repo:
            return self._error("Missing required field: repo")

        repos = self._read_repos()
        # Avoid duplicates
        if not any(r.get("owner") == owner and r.get("repo") == repo for r in repos):
            repos.append({"owner": owner, "repo": repo})
            self._write_repos(repos)

        return self._json({"owner": owner, "repo": repo}, status=201)

    async def _handle_delete_repo(self, request: "web.Request") -> "web.Response":
        owner = request.match_info["owner"]
        repo = request.match_info["repo"]

        repos = self._read_repos()
        new_repos = [
            r for r in repos
            if not (r.get("owner") == owner and r.get("repo") == repo)
        ]

        if len(new_repos) == len(repos):
            return self._error(f"Repo {owner}/{repo} not found", status=404)

        self._write_repos(new_repos)
        return self._json({"deleted": f"{owner}/{repo}"})

    async def _handle_get_skills(self, request: "web.Request") -> "web.Response":
        skills = []

        # Try to load SkillEffectiveness for scores
        effectiveness = None
        try:
            from tools.skill_effectiveness import SkillEffectiveness
            effectiveness = SkillEffectiveness()
        except Exception:
            pass

        if self.skills_path.exists():
            for entry in sorted(self.skills_path.iterdir()):
                if not entry.is_dir():
                    continue
                skill_md = entry / "SKILL.md"
                description = ""
                if skill_md.exists():
                    try:
                        content = skill_md.read_text(encoding="utf-8")
                        # Extract first non-header line as description
                        for line in content.splitlines():
                            line = line.strip()
                            if line and not line.startswith("#"):
                                description = line
                                break
                    except OSError:
                        pass

                score = None
                if effectiveness:
                    try:
                        score = effectiveness.get_score(entry.name)
                    except Exception:
                        pass

                skills.append({
                    "name": entry.name,
                    "description": description,
                    "score": score,
                    "path": str(entry),
                })

        return self._json({"skills": skills})

    async def _handle_get_sessions(self, request: "web.Request") -> "web.Response":
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        gateway_state_path = hermes_home / "gateway_state.json"
        sessions: List[Dict] = []

        try:
            if gateway_state_path.exists():
                state = json.loads(gateway_state_path.read_text())
                sessions = state.get("sessions", [])
        except Exception as exc:
            logger.debug("Could not read gateway_state.json: %s", exc)

        return self._json({"sessions": sessions})

    async def _handle_memory_search(self, request: "web.Request") -> "web.Response":
        query = request.rel_url.query.get("q", "").strip()
        if not query:
            return self._error("Missing query parameter: q")

        try:
            result = self.agi_client.memory_search(query)
            results = result.get("results", []) if isinstance(result, dict) else result
        except Exception as exc:
            logger.warning("memory_search failed: %s", exc)
            results = []

        return self._json({"results": results, "query": query})

    async def _handle_events(self, request: "web.Request") -> "web.StreamResponse":
        """SSE endpoint — streams blackboard events every 2 seconds."""
        resp = web.StreamResponse()
        resp.content_type = "text/event-stream"
        for k, v in self._cors_headers().items():
            resp.headers[k] = v
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"

        await resp.prepare(request)

        try:
            while True:
                try:
                    events = self.agi_client.blackboard_get()
                    data = json.dumps(events) if events else "{}"
                except Exception:
                    data = "{}"

                await resp.write(f"data: {data}\n\n".encode())

                # Check if client disconnected
                if request.transport is None or request.transport.is_closing():
                    break

                await asyncio.sleep(2)
        except (ConnectionResetError, asyncio.CancelledError):
            pass

        return resp

    # ── App factory ───────────────────────────────────────────────────────

    def create_app(self) -> "web.Application":
        """Create and return the aiohttp Application."""
        if web is None:  # pragma: no cover
            raise ImportError("aiohttp is required for HermesWebAPI")

        app = web.Application(middlewares=[self._auth_middleware, self._cors_middleware])

        # Status
        app.router.add_get("/api/status", self._handle_status)
        app.router.add_options("/api/status", self._handle_options)

        # Goals
        app.router.add_get("/api/goals", self._handle_get_goals)
        app.router.add_post("/api/goals", self._handle_post_goals)
        app.router.add_delete("/api/goals/{id}", self._handle_delete_goal)
        app.router.add_options("/api/goals", self._handle_options)
        app.router.add_options("/api/goals/{id}", self._handle_options)

        # Repos
        app.router.add_get("/api/repos", self._handle_get_repos)
        app.router.add_post("/api/repos", self._handle_post_repos)
        app.router.add_delete("/api/repos/{owner}/{repo}", self._handle_delete_repo)
        app.router.add_options("/api/repos", self._handle_options)
        app.router.add_options("/api/repos/{owner}/{repo}", self._handle_options)

        # Skills
        app.router.add_get("/api/skills", self._handle_get_skills)
        app.router.add_options("/api/skills", self._handle_options)

        # Sessions
        app.router.add_get("/api/sessions", self._handle_get_sessions)
        app.router.add_options("/api/sessions", self._handle_options)

        # Memory
        app.router.add_get("/api/memory/search", self._handle_memory_search)
        app.router.add_options("/api/memory/search", self._handle_options)

        # Events (SSE)
        app.router.add_get("/api/events", self._handle_events)
        app.router.add_options("/api/events", self._handle_options)

        # Telegram webhook endpoint — receives POST updates from Telegram
        # when TELEGRAM_WEBHOOK_URL is configured.
        app.router.add_post("/telegram/webhook", self._handle_telegram_webhook)

        return app

    async def _handle_telegram_webhook(self, request: "web.Request") -> "web.Response":
        """Accept incoming Telegram updates and forward to the Telegram adapter."""
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400, text="bad json")

        # Locate the telegram adapter via the gateway runner if available
        try:
            from gateway.run import GatewayRunner  # noqa: F401
            runner = getattr(self, "_runner_ref", None)
            if runner is None:
                # Try to find it from the config stored on self
                from gateway import run as _run
                runner = getattr(_run, "_active_runner", None)

            if runner is not None:
                for adapter in getattr(runner, "_adapters", []):
                    if hasattr(adapter, "handle_webhook_update"):
                        await adapter.handle_webhook_update(data)
                        break
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning("Telegram webhook dispatch error: %s", exc)

        # Always return 200 to Telegram so it doesn't retry
        return web.Response(status=200, text="ok")

    async def _handle_options(self, request: "web.Request") -> "web.Response":
        """Handle CORS preflight OPTIONS requests."""
        return web.Response(status=204, headers=self._cors_headers())

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self, port: int = 3001, host: str = "0.0.0.0") -> None:
        """Start the web API server."""
        if web is None:  # pragma: no cover
            logger.warning("aiohttp not installed — dashboard API disabled")
            return

        app = self.create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host, port)
        await site.start()
        logger.info("Hermes Web API listening on %s:%d", host, port)

    async def stop(self) -> None:
        """Stop the web API server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
