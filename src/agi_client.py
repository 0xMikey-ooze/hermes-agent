"""
AgiClient — thin wrapper around the AGI HTTP server REST API.
Uses only urllib (stdlib) so no extra dependencies.
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorktreeConflictError(Exception):
    """Raised when a worktree already exists (HTTP 409)."""


class AgiAuthError(Exception):
    """Raised when the server returns HTTP 401."""


class AgiClient:
    def __init__(self, url: str, api_key: Optional[str] = None):
        self.url = url.rstrip("/")
        self.api_key = api_key

    # ── Internal helpers ──────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{self.url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, headers=self._headers(), method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise AgiAuthError("Unauthorized")
            if e.code == 409:
                raise WorktreeConflictError(e.read().decode())
            raise

    # ── Public API ────────────────────────────────────────────────────────

    def health(self) -> bool:
        """Return True if the server is reachable and healthy."""
        try:
            self._request("GET", "/health")
            return True
        except Exception:
            return False

    def goal_status(self) -> Dict:
        """Return GoalPlanner queue status."""
        return self._request("GET", "/api/goals/status")

    def goal_decompose(self, goal: str, context: Dict = None) -> List[Dict]:
        """Decompose a high-level goal into ordered subtasks."""
        return self._request(
            "POST",
            "/api/goals/decompose",
            {"goal": goal, "context": context or {}},
        )

    def goal_complete(self, task_id: str, result: Dict) -> Dict:
        """Mark a task complete with the given result payload."""
        return self._request(
            "POST",
            "/api/goals/complete",
            {"taskId": task_id, "result": result},
        )

    def memory_search(self, query: str, limit: int = 5) -> List[Dict]:
        """Search the MemoryStore for entries matching *query*."""
        q = urllib.parse.quote(query)
        return self._request("GET", f"/api/memory/search?q={q}&limit={limit}")

    def blackboard_post(self, topic: str, message: Any) -> Dict:
        """Post *message* to the shared blackboard under *topic*."""
        t = urllib.parse.quote(topic)
        return self._request("POST", f"/api/blackboard/{t}", {"message": message})

    def worktree_create(self, run_id: str, team_id: str, branch: str = "main") -> Dict:
        """Provision an isolated git worktree for a worker."""
        return self._request(
            "POST",
            "/api/worktree/create",
            {"runId": run_id, "teamId": team_id, "branch": branch},
        )

    def worktree_remove(self, run_id: str, team_id: str) -> bool:
        """Remove a worktree; returns False if it was already gone (404)."""
        try:
            result = self._request("DELETE", f"/api/worktree/{run_id}/{team_id}")
            return result.get("removed", False)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            raise

    def worktree_list(self, run_id: str) -> List[Dict]:
        """List all worktrees for a given run."""
        return self._request("GET", f"/api/worktree/{run_id}")

    # ── Class methods ─────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "AgiClient":
        """Construct an AgiClient from environment variables.

        Required:
            AGI_SERVER_URL  — base URL of the AGI HTTP server.

        Optional:
            AGI_SERVER_API_KEY — API key sent as X-API-Key header.
        """
        url = os.environ.get("AGI_SERVER_URL")
        if not url:
            raise ValueError(
                "AGI_SERVER_URL environment variable is required. "
                "Set it to the base URL of the AGI HTTP server, e.g. "
                "http://localhost:8080 or https://agi-server.railway.app"
            )
        api_key = os.environ.get("AGI_SERVER_API_KEY")
        return cls(url, api_key)


# ── Startup helper ────────────────────────────────────────────────────────────


def check_agi_server(client: AgiClient) -> bool:
    """Validate AGI server connectivity; raise RuntimeError if unreachable.

    Intended to be called during Hermes startup so problems surface
    immediately rather than at first tool call.
    """
    logger.info("Checking AGI server at %s...", client.url)
    if not client.health():
        raise RuntimeError(
            f"AGI server at {client.url} is not reachable. "
            "Start it with: node src/mcp/agi-server-http.js\n"
            "Or set AGI_SERVER_URL to a running instance."
        )
    logger.info("AGI server OK")
    return True
