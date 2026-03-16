"""
gateway/db.py — Neon PostgreSQL persistence layer for Hermes.

Tables: tasks, events, agent_sessions, skills
Uses psycopg2 with a simple connection pool pattern.
Falls back to no-op if DATABASE_URL is not set.
"""
from __future__ import annotations
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn = None
_last_ping = 0.0
_PING_INTERVAL = 60.0  # re-check connection health every 60s


def _get_conn():
    """Return a live psycopg2 connection, (re)connecting as needed."""
    global _conn, _last_ping
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return None
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        logger.debug("psycopg2 not installed — DB disabled")
        return None

    with _lock:
        now = time.time()
        if _conn is None or (now - _last_ping > _PING_INTERVAL):
            try:
                if _conn is not None:
                    try:
                        _conn.cursor().execute("SELECT 1")
                        _last_ping = now
                        return _conn
                    except Exception:
                        try:
                            _conn.close()
                        except Exception:
                            pass
                _conn = psycopg2.connect(url)
                _conn.autocommit = True
                _last_ping = now
                logger.info("DB connected: %s", url[:40] + "...")
            except Exception as exc:
                logger.warning("DB connection failed: %s", exc)
                _conn = None
        return _conn


def _exec(sql: str, params=None) -> Optional[List[Dict]]:
    """Run a query, return rows as list-of-dicts or None on error."""
    conn = _get_conn()
    if conn is None:
        return None
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        if cur.description:
            return [dict(r) for r in cur.fetchall()]
        return []
    except Exception as exc:
        logger.warning("DB query error: %s | SQL: %s", exc, sql[:80])
        return None


# ── Tasks ─────────────────────────────────────────────────────────────────────

def tasks_list(status: str = None) -> List[Dict]:
    if status:
        rows = _exec("SELECT * FROM tasks WHERE status=$1 ORDER BY created_at DESC", (status,))
    else:
        rows = _exec("SELECT * FROM tasks ORDER BY created_at DESC")
    if rows is None:
        return []
    # Serialize timestamps
    for r in rows:
        for k in ("created_at", "updated_at"):
            if r.get(k):
                r[k] = r[k].isoformat()
    return rows


def task_get(task_id: str) -> Optional[Dict]:
    rows = _exec("SELECT * FROM tasks WHERE id=$1", (task_id,))
    if not rows:
        return None
    r = rows[0]
    for k in ("created_at", "updated_at"):
        if r.get(k):
            r[k] = r[k].isoformat()
    return r


def task_upsert(task: Dict) -> bool:
    sql = """
        INSERT INTO tasks (id, title, description, status, priority, agent, result, created_at, updated_at)
        VALUES (%(id)s, %(title)s, %(description)s, %(status)s, %(priority)s, %(agent)s, %(result)s, NOW(), NOW())
        ON CONFLICT (id) DO UPDATE SET
            title=EXCLUDED.title, description=EXCLUDED.description,
            status=EXCLUDED.status, priority=EXCLUDED.priority,
            agent=EXCLUDED.agent, result=EXCLUDED.result,
            updated_at=NOW()
    """
    result = _exec(sql, {
        "id": task.get("id"),
        "title": task.get("title", ""),
        "description": task.get("description"),
        "status": task.get("status", "backlog"),
        "priority": task.get("priority", "normal"),
        "agent": task.get("agent"),
        "result": task.get("result"),
    })
    return result is not None


def task_update_status(task_id: str, status: str, result: str = None) -> bool:
    if result is not None:
        r = _exec(
            "UPDATE tasks SET status=$1, result=$2, updated_at=NOW() WHERE id=$3",
            (status, result, task_id)
        )
    else:
        r = _exec(
            "UPDATE tasks SET status=$1, updated_at=NOW() WHERE id=$2",
            (status, task_id)
        )
    return r is not None


def task_delete(task_id: str) -> bool:
    return _exec("DELETE FROM tasks WHERE id=$1", (task_id,)) is not None


# ── Events ────────────────────────────────────────────────────────────────────

def event_log(event_type: str, agent: str = None, session_id: str = None,
              payload: Any = None) -> bool:
    sql = """INSERT INTO events (event_type, agent, session_id, payload)
             VALUES ($1, $2, $3, $4)"""
    payload_json = json.dumps(payload) if payload is not None else None
    return _exec(sql, (event_type, agent, session_id, payload_json)) is not None


def events_list(limit: int = 100, session_id: str = None) -> List[Dict]:
    if session_id:
        rows = _exec(
            "SELECT * FROM events WHERE session_id=$1 ORDER BY created_at DESC LIMIT $2",
            (session_id, limit)
        )
    else:
        rows = _exec(
            "SELECT * FROM events ORDER BY created_at DESC LIMIT $1", (limit,)
        )
    if rows is None:
        return []
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
        if r.get("payload") and isinstance(r["payload"], str):
            try:
                r["payload"] = json.loads(r["payload"])
            except Exception:
                pass
    return rows


# ── Skills ────────────────────────────────────────────────────────────────────

def skill_upsert(name: str, content: str, source_url: str = None,
                 tags: List[str] = None) -> bool:
    sql = """
        INSERT INTO skills (name, source_url, content, tags, installed_at, updated_at)
        VALUES ($1, $2, $3, $4, NOW(), NOW())
        ON CONFLICT (name) DO UPDATE SET
            source_url=EXCLUDED.source_url, content=EXCLUDED.content,
            tags=EXCLUDED.tags, updated_at=NOW()
    """
    return _exec(sql, (name, source_url, content, tags or [])) is not None


def skills_list() -> List[Dict]:
    rows = _exec("SELECT name, source_url, tags, installed_at, updated_at FROM skills ORDER BY name")
    if rows is None:
        return []
    for r in rows:
        for k in ("installed_at", "updated_at"):
            if r.get(k):
                r[k] = r[k].isoformat()
    return rows


def is_available() -> bool:
    """True if DATABASE_URL is set and connection works."""
    conn = _get_conn()
    return conn is not None
