"""
AGI Tool — Hermes tool wrappers for the AGI HTTP server.

Registers these tools with Hermes' tool registry:
  agi_health            — check AGI server connectivity
  agi_goal_status       — get GoalPlanner queue status
  agi_goal_decompose    — decompose a goal into subtasks
  agi_goal_complete     — mark a task complete
  agi_memory_search     — search MemoryStore
  agi_blackboard_post   — post to shared blackboard
  agi_worktree_create   — provision isolated git worktree
  agi_worktree_remove   — clean up a worktree
  agi_worktree_list     — list active worktrees for a run

All tools fail gracefully when AGI_SERVER_URL is not set (dev mode without server).
"""
import json
import logging
import os
from typing import Any, Dict, Optional

from tools.registry import registry

logger = logging.getLogger(__name__)


def _get_client():
    """Get AgiClient or return None if env not configured."""
    try:
        from src.agi_client import AgiClient
        return AgiClient.from_env()
    except (ValueError, ImportError):
        return None


def agi_health() -> Dict:
    client = _get_client()
    if not client:
        return {"ok": False, "error": "AGI_SERVER_URL not set"}
    ok = client.health()
    if ok:
        return {"ok": True}
    return {"ok": False, "error": "AGI server not reachable"}


def agi_goal_status() -> Dict:
    client = _get_client()
    if not client:
        return {"error": "AGI_SERVER_URL not set"}
    return client.goal_status()


def agi_goal_decompose(goal: str, context: Dict = None) -> Any:
    client = _get_client()
    if not client:
        return {"error": "AGI_SERVER_URL not set"}
    return client.goal_decompose(goal, context or {})


def agi_goal_complete(task_id: str, result: Dict) -> Dict:
    client = _get_client()
    if not client:
        return {"error": "AGI_SERVER_URL not set"}
    return client.goal_complete(task_id, result)


def agi_memory_search(query: str, limit: int = 5) -> Any:
    client = _get_client()
    if not client:
        return {"error": "AGI_SERVER_URL not set"}
    return client.memory_search(query, limit)


def agi_blackboard_post(topic: str, message: Any) -> Dict:
    client = _get_client()
    if not client:
        return {"error": "AGI_SERVER_URL not set"}
    return client.blackboard_post(topic, message)


def agi_worktree_create(run_id: str, team_id: str, branch: str = "main") -> Dict:
    client = _get_client()
    if not client:
        return {"error": "AGI_SERVER_URL not set"}
    return client.worktree_create(run_id, team_id, branch)


def agi_worktree_remove(run_id: str, team_id: str) -> Dict:
    client = _get_client()
    if not client:
        return {"error": "AGI_SERVER_URL not set"}
    removed = client.worktree_remove(run_id, team_id)
    return {"removed": removed}


def agi_worktree_list(run_id: str) -> Any:
    client = _get_client()
    if not client:
        return {"error": "AGI_SERVER_URL not set"}
    return client.worktree_list(run_id)


# ── Tool registration ──────────────────────────────────────────────────────────

def _check_agi():
    return bool(os.environ.get("AGI_SERVER_URL"))


registry.register(
    name="agi_health",
    toolset="agi",
    schema={
        "name": "agi_health",
        "description": "Check AGI server connectivity and health.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: json.dumps(agi_health()),
    check_fn=_check_agi,
    requires_env=["AGI_SERVER_URL"],
)

registry.register(
    name="agi_goal_status",
    toolset="agi",
    schema={
        "name": "agi_goal_status",
        "description": "Get GoalPlanner queue status (pending, inProgress, completed counts).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: json.dumps(agi_goal_status()),
    check_fn=_check_agi,
    requires_env=["AGI_SERVER_URL"],
)

registry.register(
    name="agi_goal_decompose",
    toolset="agi",
    schema={
        "name": "agi_goal_decompose",
        "description": "Decompose a high-level goal into ordered subtasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The goal to decompose"},
                "context": {"type": "object", "description": "Optional context"},
            },
            "required": ["goal"],
        },
    },
    handler=lambda args, **kw: json.dumps(
        agi_goal_decompose(args["goal"], args.get("context"))
    ),
    check_fn=_check_agi,
    requires_env=["AGI_SERVER_URL"],
)

registry.register(
    name="agi_goal_complete",
    toolset="agi",
    schema={
        "name": "agi_goal_complete",
        "description": "Mark a task complete with its result.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "result": {"type": "object"},
            },
            "required": ["task_id", "result"],
        },
    },
    handler=lambda args, **kw: json.dumps(
        agi_goal_complete(args["task_id"], args["result"])
    ),
    check_fn=_check_agi,
    requires_env=["AGI_SERVER_URL"],
)

registry.register(
    name="agi_memory_search",
    toolset="agi",
    schema={
        "name": "agi_memory_search",
        "description": "Search the AGI MemoryStore for entries matching a query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: json.dumps(
        agi_memory_search(args["query"], args.get("limit", 5))
    ),
    check_fn=_check_agi,
    requires_env=["AGI_SERVER_URL"],
)

registry.register(
    name="agi_blackboard_post",
    toolset="agi",
    schema={
        "name": "agi_blackboard_post",
        "description": "Post a message to the shared AGI blackboard.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "message": {"type": "object"},
            },
            "required": ["topic", "message"],
        },
    },
    handler=lambda args, **kw: json.dumps(
        agi_blackboard_post(args["topic"], args["message"])
    ),
    check_fn=_check_agi,
    requires_env=["AGI_SERVER_URL"],
)

registry.register(
    name="agi_worktree_create",
    toolset="agi",
    schema={
        "name": "agi_worktree_create",
        "description": "Provision an isolated git worktree for a worker.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "team_id": {"type": "string"},
                "branch": {"type": "string", "default": "main"},
            },
            "required": ["run_id", "team_id"],
        },
    },
    handler=lambda args, **kw: json.dumps(
        agi_worktree_create(args["run_id"], args["team_id"], args.get("branch", "main"))
    ),
    check_fn=_check_agi,
    requires_env=["AGI_SERVER_URL"],
)

registry.register(
    name="agi_worktree_remove",
    toolset="agi",
    schema={
        "name": "agi_worktree_remove",
        "description": "Remove a git worktree after worker completes.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "team_id": {"type": "string"},
            },
            "required": ["run_id", "team_id"],
        },
    },
    handler=lambda args, **kw: json.dumps(
        agi_worktree_remove(args["run_id"], args["team_id"])
    ),
    check_fn=_check_agi,
    requires_env=["AGI_SERVER_URL"],
)

registry.register(
    name="agi_worktree_list",
    toolset="agi",
    schema={
        "name": "agi_worktree_list",
        "description": "List all active worktrees for a run.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
            },
            "required": ["run_id"],
        },
    },
    handler=lambda args, **kw: json.dumps(
        agi_worktree_list(args["run_id"])
    ),
    check_fn=_check_agi,
    requires_env=["AGI_SERVER_URL"],
)
