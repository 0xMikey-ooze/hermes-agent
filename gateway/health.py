"""Lightweight HTTP health check endpoint for the gateway.

Provides /health and /ready endpoints for container orchestrators
(Docker, Kubernetes, systemd) to probe gateway liveness and readiness.

Usage:
    from gateway.health import HealthServer

    server = HealthServer(port=8471)
    await server.start(gateway_state_fn, platforms_fn)
    # ... later ...
    await server.stop()
"""

import json
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from aiohttp import web
except ImportError:
    web = None  # type: ignore[assignment]


def create_health_app(
    gateway_state: str = "starting",
    platforms: Optional[Dict[str, str]] = None,
) -> Any:
    """Create an aiohttp app with /health and /ready endpoints.

    This is the simple factory used by tests. For production, use HealthServer.
    """
    if web is None:
        raise ImportError("aiohttp is required for health endpoints")

    _state = {"gateway_state": gateway_state, "platforms": platforms or {}}

    async def health_handler(request: web.Request) -> web.Response:
        is_healthy = _state["gateway_state"] == "running"
        body = {
            "status": "healthy" if is_healthy else "unhealthy",
            "gateway_state": _state["gateway_state"],
            "platforms": _state["platforms"],
        }
        return web.json_response(
            body,
            status=200 if is_healthy else 503,
        )

    async def ready_handler(request: web.Request) -> web.Response:
        is_running = _state["gateway_state"] == "running"
        has_platforms = bool(_state["platforms"])
        is_ready = is_running and has_platforms
        body = {
            "status": "ready" if is_ready else "not_ready",
            "gateway_state": _state["gateway_state"],
            "platforms": _state["platforms"],
        }
        return web.json_response(
            body,
            status=200 if is_ready else 503,
        )

    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/ready", ready_handler)
    return app


class HealthServer:
    """Async HTTP server that exposes /health and /ready.

    Args:
        port: Port to listen on (default: 8471).
        host: Host to bind to (default: 127.0.0.1).
    """

    def __init__(self, port: int = 8471, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self._runner: Optional[Any] = None
        self._state: Dict[str, Any] = {
            "gateway_state": "starting",
            "platforms": {},
        }

    def update_state(
        self,
        gateway_state: Optional[str] = None,
        platforms: Optional[Dict[str, str]] = None,
    ) -> None:
        """Update the reported health state."""
        if gateway_state is not None:
            self._state["gateway_state"] = gateway_state
        if platforms is not None:
            self._state["platforms"] = platforms

    async def start(self) -> None:
        """Start the health check HTTP server."""
        if web is None:
            logger.warning("aiohttp not installed — health endpoint disabled")
            return

        app = create_health_app()
        # Share state reference so updates propagate
        for route in app.router.routes():
            pass  # Routes close over _state in create_health_app

        # Build a fresh app that shares our mutable _state
        health_app = web.Application()

        async def health_handler(request: web.Request) -> web.Response:
            is_healthy = self._state["gateway_state"] == "running"
            body = {
                "status": "healthy" if is_healthy else "unhealthy",
                "gateway_state": self._state["gateway_state"],
                "platforms": self._state["platforms"],
            }
            return web.json_response(body, status=200 if is_healthy else 503)

        async def ready_handler(request: web.Request) -> web.Response:
            is_running = self._state["gateway_state"] == "running"
            has_platforms = bool(self._state["platforms"])
            is_ready = is_running and has_platforms
            body = {
                "status": "ready" if is_ready else "not_ready",
                "gateway_state": self._state["gateway_state"],
                "platforms": self._state["platforms"],
            }
            return web.json_response(body, status=200 if is_ready else 503)

        health_app.router.add_get("/health", health_handler)
        health_app.router.add_get("/ready", ready_handler)

        self._runner = web.AppRunner(health_app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info("Health endpoint listening on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop the health check HTTP server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
