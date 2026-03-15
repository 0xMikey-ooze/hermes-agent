"""
Tests for AgiClient — thin urllib-based wrapper around the AGI HTTP server.
All HTTP is mocked with unittest.mock.patch; no real network calls.
"""

import json
import sys
import urllib.error
import urllib.request
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is importable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agi_client import AgiClient, AgiAuthError, WorktreeConflictError


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_response(body: dict, status: int = 200):
    """Build a fake urllib response context manager."""
    raw = json.dumps(body).encode()
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read = MagicMock(return_value=raw)
    mock.status = status
    return mock


def _http_error(code: int, body: str = "error"):
    """Build a urllib.error.HTTPError."""
    return urllib.error.HTTPError(
        url="http://test", code=code, msg="err",
        hdrs=None, fp=BytesIO(body.encode()),
    )


# ── Block 1 Tests ────────────────────────────────────────────────────────────

class TestAgiClientInit:
    def test_agi_client_init(self):
        """AgiClient(url, api_key) stores url and api_key."""
        client = AgiClient("http://localhost:8080", "secret-key")
        assert client.url == "http://localhost:8080"
        assert client.api_key == "secret-key"

    def test_agi_client_init_strips_trailing_slash(self):
        client = AgiClient("http://localhost:8080/")
        assert client.url == "http://localhost:8080"

    def test_agi_client_init_no_api_key(self):
        client = AgiClient("http://localhost:8080")
        assert client.api_key is None


class TestHealthCheck:
    def test_health_check_success(self):
        """health() returns True when server returns 200."""
        client = AgiClient("http://localhost:8080", "key")
        mock_resp = _mock_response({"status": "ok"})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert client.health() is True

    def test_health_check_failure(self):
        """health() returns False on ConnectionError."""
        client = AgiClient("http://localhost:8080")
        with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")):
            assert client.health() is False

    def test_health_check_failure_non200(self):
        """health() returns False when server returns 500."""
        client = AgiClient("http://localhost:8080")
        with patch("urllib.request.urlopen", side_effect=_http_error(500)):
            assert client.health() is False


class TestGoalStatus:
    def test_goal_status(self):
        """goal_status() returns dict with pending/inProgress/completed keys."""
        client = AgiClient("http://localhost:8080", "key")
        payload = {"pending": [], "inProgress": [], "completed": [], "blocked": []}
        mock_resp = _mock_response(payload)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.goal_status()
        assert "pending" in result
        assert "inProgress" in result
        assert "completed" in result

    def test_goal_status_auth(self):
        """goal_status() sends X-API-Key header."""
        client = AgiClient("http://localhost:8080", "my-secret")
        payload = {"pending": [], "inProgress": [], "completed": [], "blocked": []}
        mock_resp = _mock_response(payload)

        captured_req = []

        def fake_urlopen(req, timeout=None):
            captured_req.append(req)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.goal_status()

        assert len(captured_req) == 1
        req = captured_req[0]
        assert req.get_header("X-api-key") == "my-secret"


class TestWorktreeCreate:
    def test_worktree_create(self):
        """worktree_create(runId, teamId, branch) returns dict with path key."""
        client = AgiClient("http://localhost:8080", "key")
        payload = {"path": "/tmp/worktrees/run-abc/team-1", "runId": "abc", "teamId": "team-1"}
        mock_resp = _mock_response(payload)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.worktree_create("abc", "team-1", "main")
        assert "path" in result
        assert result["path"] == "/tmp/worktrees/run-abc/team-1"

    def test_worktree_create_conflict(self):
        """worktree_create() raises WorktreeConflictError on 409."""
        client = AgiClient("http://localhost:8080", "key")
        with patch("urllib.request.urlopen", side_effect=_http_error(409, "already exists")):
            with pytest.raises(WorktreeConflictError):
                client.worktree_create("abc", "team-1", "main")


class TestWorktreeRemove:
    def test_worktree_remove(self):
        """worktree_remove(runId, teamId) returns True on success."""
        client = AgiClient("http://localhost:8080", "key")
        mock_resp = _mock_response({"removed": True})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.worktree_remove("abc", "team-1")
        assert result is True

    def test_worktree_remove_not_found(self):
        """worktree_remove() returns False on 404."""
        client = AgiClient("http://localhost:8080", "key")
        with patch("urllib.request.urlopen", side_effect=_http_error(404)):
            result = client.worktree_remove("abc", "team-1")
        assert result is False


class TestMemorySearch:
    def test_memory_search(self):
        """memory_search(query) returns list."""
        client = AgiClient("http://localhost:8080", "key")
        payload = [{"key": "pattern/1", "value": "use pytest"}]
        mock_resp = _mock_response(payload)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.memory_search("pytest patterns")
        assert isinstance(result, list)
        assert len(result) == 1


class TestBlackboardPost:
    def test_blackboard_post(self):
        """blackboard_post(topic, message) sends POST without error."""
        client = AgiClient("http://localhost:8080", "key")
        mock_resp = _mock_response({"ok": True})

        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(req)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.blackboard_post("swarm/status", {"status": "idle"})

        assert len(captured) == 1
        req = captured[0]
        assert req.get_method() == "POST"
        body = json.loads(req.data)
        assert body["message"] == {"status": "idle"}


class TestGoalDecompose:
    def test_goal_decompose(self):
        """goal_decompose(goal, context) returns list of tasks."""
        client = AgiClient("http://localhost:8080", "key")
        payload = [
            {"id": "t1", "description": "Write tests", "priority": 1},
            {"id": "t2", "description": "Implement feature", "priority": 2},
        ]
        mock_resp = _mock_response(payload)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.goal_decompose("Add login feature", {"repo": "myapp"})
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "t1"
