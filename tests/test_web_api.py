"""Tests for gateway/web_api.py — TDD-first.

Run with:
    .venv/bin/pytest tests/test_web_api.py -v

All tests use aiohttp test client and mock agi_client so no live server needed.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make project root importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Pytest + aiohttp test client setup
# ---------------------------------------------------------------------------
pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def mock_agi_client():
    """Return a mock agi_client with all methods used by web_api."""
    client = MagicMock()
    client.goal_status = MagicMock(return_value={"goals": []})
    client.goal_decompose = MagicMock(return_value=[{"id": "t1", "description": "do thing"}])
    client.blackboard_get = MagicMock(return_value={"events": []})
    client.memory_search = MagicMock(return_value={"results": []})
    return client


@pytest.fixture
def mock_config():
    """Return a minimal config dict."""
    return {
        "version": "0.2.0",
        "model": "anthropic/claude-opus-4-6",
        "platform": "hermes-gateway",
    }


@pytest.fixture
def tmp_hermes_home(tmp_path, monkeypatch):
    """Override HERMES_HOME so tests don't touch ~/.hermes."""
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    return hermes_home


@pytest.fixture
def tmp_skills_dir(tmp_path):
    """Create a temporary skills directory with fake skill entries."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    for skill_name in ("web-research", "code-review", "data-analysis"):
        skill_dir = skills_dir / skill_name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"# {skill_name}\n\nDescription of {skill_name} skill."
        )
    return skills_dir


@pytest.fixture
def tmp_repos_file(tmp_path):
    """Create a temporary watched_repos.json."""
    repos = [
        {"owner": "nousresearch", "repo": "hermes-agent"},
        {"owner": "acme", "repo": "myapp"},
    ]
    repos_file = tmp_path / "watched_repos.json"
    repos_file.write_text(json.dumps(repos))
    return repos_file


@pytest.fixture
def tmp_gateway_state(tmp_hermes_home):
    """Write a fake gateway_state.json for session tests."""
    state = {
        "gateway_state": "running",
        "sessions": [
            {"session_id": "s1", "platform": "telegram", "user_id": "123"},
        ],
    }
    (tmp_hermes_home / "gateway_state.json").write_text(json.dumps(state))
    return tmp_hermes_home / "gateway_state.json"


# ---------------------------------------------------------------------------
# Helper: build a test app
# ---------------------------------------------------------------------------

def make_app(
    agi_client,
    config=None,
    repos_file: Path = None,
    skills_path: Path = None,
    api_key: str = None,
    tmp_hermes_home: Path = None,
):
    """Import HermesWebAPI and create an aiohttp.Application for testing."""
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(
        agi_client=agi_client,
        config=config or {},
        repos_file=repos_file,
        skills_path=skills_path,
    )
    app = api.create_app()
    # Inject API key override without touching os.environ globally
    if api_key is not None:
        app["_test_api_key"] = api_key
    return app


# ===========================================================================
# Tests: /api/status
# ===========================================================================


@pytest.mark.asyncio
async def test_status_returns_200(mock_agi_client, mock_config, tmp_hermes_home, aiohttp_client):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/status")
    assert resp.status == 200
    data = await resp.json()
    assert "version" in data
    assert "uptime_seconds" in data
    assert "model" in data
    assert "platform" in data
    assert "gateway_running" in data


@pytest.mark.asyncio
async def test_status_cors_header(mock_agi_client, mock_config, aiohttp_client):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/status")
    assert resp.headers.get("Access-Control-Allow-Origin") is not None


# ===========================================================================
# Tests: /api/goals
# ===========================================================================


@pytest.mark.asyncio
async def test_get_goals_returns_200(mock_agi_client, mock_config, aiohttp_client):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/goals")
    assert resp.status == 200
    data = await resp.json()
    assert "goals" in data


@pytest.mark.asyncio
async def test_post_goals_returns_201_with_valid_body(mock_agi_client, mock_config, aiohttp_client):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.post(
        "/api/goals",
        json={"repo": "acme/myapp", "description": "Fix the login bug"},
    )
    assert resp.status == 201


@pytest.mark.asyncio
async def test_post_goals_missing_repo_returns_400(mock_agi_client, mock_config, aiohttp_client):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.post("/api/goals", json={"description": "Fix bug"})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_post_goals_missing_description_returns_400(mock_agi_client, mock_config, aiohttp_client):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.post("/api/goals", json={"repo": "acme/myapp"})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_delete_goal_returns_200(mock_agi_client, mock_config, aiohttp_client):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.delete("/api/goals/task-123")
    assert resp.status == 200


# ===========================================================================
# Tests: /api/repos
# ===========================================================================


@pytest.mark.asyncio
async def test_get_repos_returns_200_with_list(
    mock_agi_client, mock_config, tmp_repos_file, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(
        agi_client=mock_agi_client, config=mock_config, repos_file=tmp_repos_file
    )
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/repos")
    assert resp.status == 200
    data = await resp.json()
    assert "repos" in data
    assert len(data["repos"]) == 2


@pytest.mark.asyncio
async def test_post_repos_adds_entry(
    mock_agi_client, mock_config, tmp_path, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    repos_file = tmp_path / "repos.json"
    repos_file.write_text("[]")

    api = HermesWebAPI(
        agi_client=mock_agi_client, config=mock_config, repos_file=repos_file
    )
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.post(
        "/api/repos", json={"owner": "nousresearch", "repo": "new-repo"}
    )
    assert resp.status == 201

    saved = json.loads(repos_file.read_text())
    assert any(r["repo"] == "new-repo" for r in saved)


@pytest.mark.asyncio
async def test_post_repos_missing_owner_returns_400(
    mock_agi_client, mock_config, tmp_path, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    repos_file = tmp_path / "repos.json"
    repos_file.write_text("[]")

    api = HermesWebAPI(
        agi_client=mock_agi_client, config=mock_config, repos_file=repos_file
    )
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.post("/api/repos", json={"repo": "new-repo"})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_post_repos_missing_repo_returns_400(
    mock_agi_client, mock_config, tmp_path, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    repos_file = tmp_path / "repos.json"
    repos_file.write_text("[]")

    api = HermesWebAPI(
        agi_client=mock_agi_client, config=mock_config, repos_file=repos_file
    )
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.post("/api/repos", json={"owner": "acme"})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_delete_repo_removes_entry(
    mock_agi_client, mock_config, tmp_path, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    repos = [{"owner": "acme", "repo": "myapp"}, {"owner": "nousresearch", "repo": "hermes"}]
    repos_file = tmp_path / "repos.json"
    repos_file.write_text(json.dumps(repos))

    api = HermesWebAPI(
        agi_client=mock_agi_client, config=mock_config, repos_file=repos_file
    )
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.delete("/api/repos/acme/myapp")
    assert resp.status == 200

    saved = json.loads(repos_file.read_text())
    assert not any(r["owner"] == "acme" and r["repo"] == "myapp" for r in saved)


@pytest.mark.asyncio
async def test_delete_repo_not_found_returns_404(
    mock_agi_client, mock_config, tmp_path, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    repos_file = tmp_path / "repos.json"
    repos_file.write_text("[]")

    api = HermesWebAPI(
        agi_client=mock_agi_client, config=mock_config, repos_file=repos_file
    )
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.delete("/api/repos/nobody/nothing")
    assert resp.status == 404


# ===========================================================================
# Tests: /api/skills
# ===========================================================================


@pytest.mark.asyncio
async def test_get_skills_returns_200(
    mock_agi_client, mock_config, tmp_skills_dir, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(
        agi_client=mock_agi_client, config=mock_config, skills_path=tmp_skills_dir
    )
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/skills")
    assert resp.status == 200
    data = await resp.json()
    assert "skills" in data
    assert len(data["skills"]) == 3


@pytest.mark.asyncio
async def test_get_skills_includes_effectiveness_score(
    mock_agi_client, mock_config, tmp_skills_dir, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(
        agi_client=mock_agi_client, config=mock_config, skills_path=tmp_skills_dir
    )
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/skills")
    data = await resp.json()
    # Each skill entry should have a score field (float or None)
    for skill in data["skills"]:
        assert "name" in skill
        assert "score" in skill


# ===========================================================================
# Tests: /api/sessions
# ===========================================================================


@pytest.mark.asyncio
async def test_get_sessions_returns_200(
    mock_agi_client, mock_config, tmp_gateway_state, tmp_hermes_home, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/sessions")
    assert resp.status == 200
    data = await resp.json()
    assert "sessions" in data


# ===========================================================================
# Tests: /api/memory/search
# ===========================================================================


@pytest.mark.asyncio
async def test_memory_search_returns_200(mock_agi_client, mock_config, aiohttp_client):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/memory/search?q=login+bug")
    assert resp.status == 200
    data = await resp.json()
    assert "results" in data


@pytest.mark.asyncio
async def test_memory_search_missing_query_returns_400(
    mock_agi_client, mock_config, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/memory/search")
    assert resp.status == 400


# ===========================================================================
# Tests: /api/events (SSE)
# ===========================================================================


@pytest.mark.asyncio
async def test_events_returns_event_stream_content_type(
    mock_agi_client, mock_config, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    async with client.get("/api/events") as resp:
        assert resp.status == 200
        assert "text/event-stream" in resp.content_type


# ===========================================================================
# Tests: Authentication middleware
# ===========================================================================


@pytest.mark.asyncio
async def test_no_api_key_configured_allows_all(
    mock_agi_client, mock_config, aiohttp_client, monkeypatch
):
    """When DASHBOARD_API_KEY env var is not set, all requests pass through."""
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/status")
    assert resp.status == 200


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401(
    mock_agi_client, mock_config, aiohttp_client, monkeypatch
):
    """When DASHBOARD_API_KEY is set and wrong key sent → 401."""
    monkeypatch.setenv("DASHBOARD_API_KEY", "secret-key-abc")
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/status", headers={"X-API-Key": "wrong-key"})
    assert resp.status == 401


@pytest.mark.asyncio
async def test_correct_api_key_returns_200(
    mock_agi_client, mock_config, aiohttp_client, monkeypatch
):
    """When DASHBOARD_API_KEY is set and correct key sent → 200."""
    monkeypatch.setenv("DASHBOARD_API_KEY", "secret-key-abc")
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/status", headers={"X-API-Key": "secret-key-abc"})
    assert resp.status == 200


@pytest.mark.asyncio
async def test_missing_api_key_header_returns_401(
    mock_agi_client, mock_config, aiohttp_client, monkeypatch
):
    """When DASHBOARD_API_KEY is set and no header sent → 401."""
    monkeypatch.setenv("DASHBOARD_API_KEY", "secret-key-abc")
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/status")
    assert resp.status == 401


# ===========================================================================
# Tests: CORS headers on all routes
# ===========================================================================


@pytest.mark.asyncio
async def test_cors_on_goals_endpoint(mock_agi_client, mock_config, aiohttp_client):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/goals")
    assert resp.headers.get("Access-Control-Allow-Origin") is not None


@pytest.mark.asyncio
async def test_cors_on_repos_endpoint(
    mock_agi_client, mock_config, tmp_repos_file, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(
        agi_client=mock_agi_client, config=mock_config, repos_file=tmp_repos_file
    )
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/repos")
    assert resp.headers.get("Access-Control-Allow-Origin") is not None


@pytest.mark.asyncio
async def test_options_preflight_returns_200(mock_agi_client, mock_config, aiohttp_client):
    """OPTIONS preflight requests should succeed."""
    from gateway.web_api import HermesWebAPI

    api = HermesWebAPI(agi_client=mock_agi_client, config=mock_config)
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.options(
        "/api/status",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Should not 405 Method Not Allowed
    assert resp.status in (200, 204)


# ===========================================================================
# Tests: Repos file read/write isolation
# ===========================================================================


@pytest.mark.asyncio
async def test_repos_file_created_if_missing(
    mock_agi_client, mock_config, tmp_path, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    repos_file = tmp_path / "nonexistent_repos.json"
    assert not repos_file.exists()

    api = HermesWebAPI(
        agi_client=mock_agi_client, config=mock_config, repos_file=repos_file
    )
    app = api.create_app()
    client = await aiohttp_client(app)

    resp = await client.get("/api/repos")
    assert resp.status == 200
    data = await resp.json()
    assert data["repos"] == []


@pytest.mark.asyncio
async def test_repos_persisted_after_post(
    mock_agi_client, mock_config, tmp_path, aiohttp_client
):
    from gateway.web_api import HermesWebAPI

    repos_file = tmp_path / "repos.json"
    repos_file.write_text("[]")

    api = HermesWebAPI(
        agi_client=mock_agi_client, config=mock_config, repos_file=repos_file
    )
    app = api.create_app()
    client = await aiohttp_client(app)

    await client.post("/api/repos", json={"owner": "foo", "repo": "bar"})
    await client.post("/api/repos", json={"owner": "baz", "repo": "qux"})

    saved = json.loads(repos_file.read_text())
    assert len(saved) == 2
    names = {r["repo"] for r in saved}
    assert names == {"bar", "qux"}
