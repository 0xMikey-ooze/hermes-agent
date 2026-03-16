#!/usr/bin/env python3
"""
Hermes Tasks Tool — direct DB access for task queue management.

Gives the agent first-class tools to:
- list_tasks: See all tasks with status/description
- get_task: Read a single task in full
- update_task_status: Mark task in_progress / done / blocked
- create_task: Create a new task from chat
- query_db: Run a raw SELECT query against Neon for inspection
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

from tools.registry import registry

logger = logging.getLogger(__name__)

TOOLSET = "hermes-tasks"


# ── helpers ───────────────────────────────────────────────────────────────────

def _db_exec(sql: str, params: tuple = ()) -> Optional[List[Dict]]:
    """Run a query against Neon. Returns list of row dicts or None on error."""
    try:
        from gateway.db import _exec as _raw_exec
        result = _raw_exec(sql, params)
        if result is not None:
            return result
    except Exception as e:
        logger.debug("hermes_tasks_tool direct DB error: %s — trying env fallback", e)

    # Fallback: use psycopg2 directly with DATABASE_URL env var
    try:
        import psycopg2
        import psycopg2.extras
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            return None
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Convert $1/$2 style params to %s for psycopg2
        import re
        psql = re.sub(r'\$([0-9]+)', '%s', sql)
        cur.execute(psql, params or None)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        cur.close()
        conn.close()
        return rows
    except Exception as e2:
        logger.warning("hermes_tasks_tool fallback DB error: %s", e2)
        return None


def _db_available() -> bool:
    try:
        from gateway.db import is_available
        return is_available()
    except Exception:
        return bool(os.environ.get("DATABASE_URL"))


# ── tool handlers ─────────────────────────────────────────────────────────────

def list_tasks_handler(params: Dict[str, Any], **_) -> str:
    """Return all tasks as formatted text the agent can read."""
    status_filter = params.get("status")  # optional: "pending", "in_progress", "done"

    if not _db_available():
        return "⚠️ Database not available. Cannot read task queue."

    sql = "SELECT id, title, description, status, repo, created_at FROM tasks ORDER BY created_at DESC LIMIT 50"
    args: tuple = ()
    if status_filter:
        sql = "SELECT id, title, description, status, repo, created_at FROM tasks WHERE status=$1 ORDER BY created_at DESC LIMIT 50"
        args = (status_filter,)

    rows = _db_exec(sql, args)
    if rows is None:
        return "⚠️ Failed to query tasks table."
    if not rows:
        return "✅ Task queue is empty."

    lines = [f"📋 Task Queue ({len(rows)} tasks{' — ' + status_filter if status_filter else ''}):\n"]
    for r in rows:
        status_icon = {"pending": "⏳", "in_progress": "🔄", "done": "✅", "blocked": "🚫"}.get(r.get("status", ""), "•")
        created = str(r.get("created_at", ""))[:16]
        lines.append(
            f"{status_icon} [{r['status'].upper()}] {r['title']}\n"
            f"   ID: {r['id']} | Repo: {r.get('repo', 'n/a')} | Created: {created}\n"
            f"   {(r.get('description') or '')[:120]}"
        )
    return "\n\n".join(lines)


def get_task_handler(params: Dict[str, Any], **_) -> str:
    """Return a single task in full detail."""
    task_id = params.get("task_id", "")
    if not task_id:
        return "❌ task_id is required."
    if not _db_available():
        return "⚠️ Database not available."

    rows = _db_exec(
        "SELECT id, title, description, status, repo, created_at, updated_at FROM tasks WHERE id=$1 LIMIT 1",
        (task_id,),
    )
    if not rows:
        return f"❌ Task {task_id!r} not found."

    r = rows[0]
    return (
        f"📌 Task: {r['title']}\n"
        f"ID: {r['id']}\n"
        f"Status: {r['status']}\n"
        f"Repo: {r.get('repo', 'n/a')}\n"
        f"Created: {str(r.get('created_at',''))[:19]}\n"
        f"Updated: {str(r.get('updated_at',''))[:19]}\n\n"
        f"Description:\n{r.get('description','(none)')}"
    )


def update_task_status_handler(params: Dict[str, Any], **_) -> str:
    """Update a task's status and log to activity feed."""
    task_id = params.get("task_id", "")
    new_status = params.get("status", "")
    note = params.get("note", "")

    if not task_id or not new_status:
        return "❌ task_id and status are required."
    allowed = {"pending", "in_progress", "done", "blocked", "cancelled"}
    if new_status not in allowed:
        return f"❌ status must be one of: {', '.join(sorted(allowed))}"
    if not _db_available():
        return "⚠️ Database not available."

    sql = "UPDATE tasks SET status=$1, updated_at=NOW() WHERE id=$2 RETURNING id, title, status"
    rows = _db_exec(sql, (new_status, task_id))
    if not rows:
        return f"❌ Task {task_id!r} not found or update failed."

    r = rows[0]
    note_str = f" — {note}" if note else ""

    # Log to activity feed (events table)
    event_type = {
        "in_progress": "task_started",
        "done": "task_completed",
        "blocked": "task_blocked",
        "cancelled": "task_blocked",
    }.get(new_status, "task_status_changed")
    try:
        payload = {"id": r["id"], "title": r["title"], "status": new_status}
        if note:
            payload["note"] = note
        _db_exec(
            "INSERT INTO events (event_type, payload, created_at) VALUES ($1, $2::jsonb, NOW())",
            (event_type, __import__("json").dumps(payload)),
        )
    except Exception as e:
        logger.debug("Event log failed: %s", e)

    return f"✅ Task updated: [{r['status'].upper()}] {r['title']} (id: {r['id']}){note_str}"


def create_task_handler(params: Dict[str, Any], **_) -> str:
    """Create a new task in the queue from chat."""
    title = params.get("title", "").strip()
    description = params.get("description", "").strip()
    repo = params.get("repo", "").strip()

    if not title:
        return "❌ title is required."
    if not _db_available():
        return "⚠️ Database not available."

    import uuid
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    sql = """INSERT INTO tasks (id, title, description, status, repo, created_at, updated_at)
             VALUES ($1,$2,$3,'pending',$4,NOW(),NOW()) RETURNING id, title, status"""
    rows = _db_exec(sql, (task_id, title, description or title, repo or None))
    if not rows:
        return "❌ Failed to create task."

    r = rows[0]
    return f"✅ Task created: {r['title']} (id: {r['id']}, status: {r['status']})"


def query_db_handler(params: Dict[str, Any], **_) -> str:
    """Run a read-only SQL SELECT query against the Neon database."""
    sql = params.get("sql", "").strip()
    if not sql:
        return "❌ sql parameter is required."

    # Safety: only allow SELECT / WITH (no mutations)
    normalized = sql.upper().lstrip()
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        return "❌ Only SELECT and WITH queries are allowed for safety."

    if not _db_available():
        return "⚠️ Database not available."

    rows = _db_exec(sql)
    if rows is None:
        return "❌ Query failed. Check syntax or table names."
    if not rows:
        return "✅ Query returned 0 rows."

    # Format as table
    if len(rows) == 0:
        return "0 rows."
    cols = list(rows[0].keys())
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in rows[:50]:
        lines.append("| " + " | ".join(str(row.get(c, ""))[:60] for c in cols) + " |")
    suffix = f"\n\n(showing first 50 of {len(rows)} rows)" if len(rows) > 50 else f"\n\n({len(rows)} row{'s' if len(rows)!=1 else ''})"
    return "\n".join(lines) + suffix


# ── schema definitions ────────────────────────────────────────────────────────

_LIST_TASKS_SCHEMA = {
    "name": "list_tasks",
    "description": (
        "List all tasks in the Hermes task queue. "
        "Optionally filter by status (pending, in_progress, done, blocked). "
        "Use this to check what work is queued before starting new tasks."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "done", "blocked", "cancelled"],
                "description": "Filter tasks by status. Omit to return all tasks.",
            }
        },
        "required": [],
    },
}

_GET_TASK_SCHEMA = {
    "name": "get_task",
    "description": "Get the full details of a specific task by its ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The task ID (e.g. task-abc12345)"}
        },
        "required": ["task_id"],
    },
}

_UPDATE_TASK_STATUS_SCHEMA = {
    "name": "update_task_status",
    "description": (
        "Update the status of a task. "
        "Use in_progress when you start working on it, done when complete, "
        "blocked if you hit a blocker, cancelled to remove from queue."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The task ID"},
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "done", "blocked", "cancelled"],
                "description": "New status",
            },
            "note": {"type": "string", "description": "Optional note about why the status changed"},
        },
        "required": ["task_id", "status"],
    },
}

_CREATE_TASK_SCHEMA = {
    "name": "create_task",
    "description": "Create a new task in the queue from chat. Useful when the user asks you to track something for later.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short task title"},
            "description": {"type": "string", "description": "Full task description / instructions"},
            "repo": {"type": "string", "description": "GitHub repo this task relates to (e.g. 0xMikey-ooze/hermes-agent)"},
        },
        "required": ["title"],
    },
}

_QUERY_DB_SCHEMA = {
    "name": "query_db",
    "description": (
        "Run a read-only SQL SELECT query against the Neon PostgreSQL database. "
        "Tables available: tasks, events, agent_sessions, skills, watched_repos, simulations. "
        "Use for inspection, reporting, or debugging."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "A SELECT or WITH query to execute. No INSERT/UPDATE/DELETE allowed.",
            }
        },
        "required": ["sql"],
    },
}

# ── registration ──────────────────────────────────────────────────────────────

def _check_db_available():
    return _db_available()


registry.register(
    name="list_tasks",
    toolset=TOOLSET,
    schema=_LIST_TASKS_SCHEMA,
    handler=list_tasks_handler,
    check_fn=_check_db_available,
    requires_env=["DATABASE_URL"],
    is_async=False,
    description="List all tasks in the Hermes queue",
)

registry.register(
    name="get_task",
    toolset=TOOLSET,
    schema=_GET_TASK_SCHEMA,
    handler=get_task_handler,
    check_fn=_check_db_available,
    requires_env=["DATABASE_URL"],
    is_async=False,
    description="Get full details of a task by ID",
)

registry.register(
    name="update_task_status",
    toolset=TOOLSET,
    schema=_UPDATE_TASK_STATUS_SCHEMA,
    handler=update_task_status_handler,
    check_fn=_check_db_available,
    requires_env=["DATABASE_URL"],
    is_async=False,
    description="Update a task's status (pending/in_progress/done/blocked)",
)

registry.register(
    name="create_task",
    toolset=TOOLSET,
    schema=_CREATE_TASK_SCHEMA,
    handler=create_task_handler,
    check_fn=_check_db_available,
    requires_env=["DATABASE_URL"],
    is_async=False,
    description="Create a new task in the queue",
)

registry.register(
    name="query_db",
    toolset=TOOLSET,
    schema=_QUERY_DB_SCHEMA,
    handler=query_db_handler,
    check_fn=_check_db_available,
    requires_env=["DATABASE_URL"],
    is_async=False,
    description="Run a read-only SELECT query against the Neon DB",
)
