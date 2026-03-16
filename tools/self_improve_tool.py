#!/usr/bin/env python3
"""
Self-Improvement Tool — Hermes Agent

Gives the agent first-class tools to learn from experience and improve itself:

- write_reflection  : Record what worked/failed after a task. Stored in Neon.
- read_reflections  : Recall past lessons by category or keyword.
- update_soul       : Edit the agent's own Soul.md (via GitHub-backed API).
- commit_skill      : Push a HERMES_HOME skill to GitHub so it persists across deploys.
- self_diagnose     : Identify gaps in current skills vs. recent task failures.
"""

import json
import logging
import os
import urllib.request
import urllib.parse
from typing import Any, Dict, List, Optional

from tools.registry import registry

logger = logging.getLogger(__name__)

TOOLSET = "hermes-self-improve"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("HERMES_GITHUB_REPO", "0xMikey-ooze/hermes-agent")
HERMES_URL = os.environ.get("HERMES_SELF_URL", "http://localhost:8080")


# ── DB helpers ────────────────────────────────────────────────────────────────

def _db_exec(sql: str, params=None):
    try:
        from gateway.db import _exec as _raw
        result = _raw(sql, params)
        if result is not None:
            return result
    except Exception:
        pass
    try:
        import psycopg2, psycopg2.extras, re as _re
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        psql = _re.sub(r'\$([0-9]+)', '%s', sql)
        cur.execute(psql, params or None)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        cur.close(); conn.close()
        return rows
    except Exception as e:
        logger.warning("self_improve DB error: %s", e)
        return None


def _db_ok():
    return bool(os.environ.get("DATABASE_URL"))


# ── GitHub helpers ────────────────────────────────────────────────────────────

def _github_put_file(path: str, content: str, message: str) -> bool:
    """Commit a file to the hermes-agent GitHub repo."""
    token = GITHUB_TOKEN or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return False
    import base64

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    # Get current SHA if file exists
    sha = None
    try:
        req = urllib.request.Request(api_url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "hermes-self-improve",
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            sha = json.loads(r.read()).get("sha")
    except Exception:
        pass

    payload: Dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
    }
    if sha:
        payload["sha"] = sha

    body = json.dumps(payload).encode()
    req2 = urllib.request.Request(api_url, data=body, method="PUT", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "hermes-self-improve",
    })
    try:
        with urllib.request.urlopen(req2, timeout=10) as r:
            resp = json.loads(r.read())
            return "content" in resp
    except Exception as e:
        logger.warning("GitHub put failed: %s", e)
        return False


# ── Tool handlers ─────────────────────────────────────────────────────────────

def write_reflection_handler(params: Dict[str, Any], **_) -> str:
    """Record a lesson from a completed task."""
    lesson = params.get("lesson", "").strip()
    if not lesson:
        return "❌ lesson is required."

    task_id = params.get("task_id", "")
    category = params.get("category", "general")
    what_worked = params.get("what_worked", "")
    what_failed = params.get("what_failed", "")
    applied_to = params.get("applied_to", "")

    if not _db_ok():
        return "⚠️ DATABASE_URL not set — reflection not stored."

    sql = """INSERT INTO reflections (task_id, category, what_worked, what_failed, lesson, applied_to)
             VALUES ($1,$2,$3,$4,$5,$6) RETURNING id"""
    rows = _db_exec(sql, (task_id or None, category, what_worked, what_failed, lesson, applied_to or None))
    if not rows:
        return "❌ Failed to write reflection."

    rid = rows[0].get("id", "?")
    return f"✅ Reflection #{rid} stored [{category}]: {lesson[:80]}"


def read_reflections_handler(params: Dict[str, Any], **_) -> str:
    """Recall past lessons — searchable by category or keyword."""
    category = params.get("category", "")
    keyword = params.get("keyword", "")
    limit = min(int(params.get("limit", 10)), 50)

    if not _db_ok():
        return "⚠️ DATABASE_URL not set."

    if category and keyword:
        sql = "SELECT * FROM reflections WHERE category=$1 AND lesson ILIKE $2 ORDER BY created_at DESC LIMIT $3"
        rows = _db_exec(sql, (category, f"%{keyword}%", limit))
    elif category:
        sql = "SELECT * FROM reflections WHERE category=$1 ORDER BY created_at DESC LIMIT $2"
        rows = _db_exec(sql, (category, limit))
    elif keyword:
        sql = "SELECT * FROM reflections WHERE lesson ILIKE $1 OR what_worked ILIKE $1 ORDER BY created_at DESC LIMIT $2"
        rows = _db_exec(sql, (f"%{keyword}%", limit))
    else:
        sql = "SELECT * FROM reflections ORDER BY created_at DESC LIMIT $1"
        rows = _db_exec(sql, (limit,))

    if rows is None:
        return "❌ Query failed."
    if not rows:
        return "📭 No reflections found."

    lines = [f"📚 {len(rows)} reflection(s):\n"]
    for r in rows:
        ts = str(r.get("created_at", ""))[:10]
        lines.append(
            f"[{r.get('category','?')}] {ts} — {r.get('lesson','')[:120]}\n"
            + (f"  ✓ {r.get('what_worked','')[:80]}\n" if r.get("what_worked") else "")
            + (f"  ✗ {r.get('what_failed','')[:80]}\n" if r.get("what_failed") else "")
        )
    return "\n".join(lines)


def update_soul_handler(params: Dict[str, Any], **_) -> str:
    """Edit the agent's Soul.md — the document that defines its personality, values, and behavior.
    
    IMPORTANT: Only update Soul.md for fundamental shifts in how you should operate.
    Do not make trivial changes. Think carefully before calling this.
    """
    content = params.get("content", "").strip()
    reason = params.get("reason", "").strip()

    if not content:
        return "❌ content is required (full Soul.md text)."
    if not reason:
        return "❌ reason is required — why are you updating Soul.md?"
    if len(content) < 100:
        return "❌ Soul.md content too short — provide the full document."

    # Write via internal API (already GitHub-backed)
    try:
        hermes_url = os.environ.get("HERMES_SELF_URL", "http://localhost:8080")
        body = json.dumps({"content": content}).encode()
        req = urllib.request.Request(
            f"{hermes_url}/api/soul",
            data=body,
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
            if resp.get("ok"):
                # Log the soul update as a reflection
                write_reflection_handler({
                    "category": "soul-update",
                    "lesson": f"Updated Soul.md: {reason}",
                    "what_worked": "Identified need for behavioral change",
                })
                return f"✅ Soul.md updated and committed to GitHub. Reason: {reason}"
            return f"❌ Soul update failed: {resp}"
    except Exception as e:
        return f"❌ Soul update error: {e}"


def commit_skill_handler(params: Dict[str, Any], **_) -> str:
    """Push a skill from HERMES_HOME to GitHub so it persists across redeployments.
    
    Use this after creating or significantly updating a skill via skill_manage.
    """
    skill_name = params.get("skill_name", "").strip()
    commit_message = params.get("commit_message", "").strip()

    if not skill_name:
        return "❌ skill_name is required."

    from pathlib import Path
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    skill_path = hermes_home / "skills" / skill_name / "SKILL.md"

    if not skill_path.exists():
        return f"❌ Skill '{skill_name}' not found at {skill_path}. Create it first with skill_manage."

    content = skill_path.read_text(encoding="utf-8")
    github_path = f"skills/{skill_name}/SKILL.md"
    msg = commit_message or f"feat: add/update skill {skill_name} (agent self-improvement)"

    ok = _github_put_file(github_path, content, msg)
    if ok:
        # Also write to Neon
        try:
            from gateway.db import skill_upsert
            skill_upsert(skill_name, content)
        except Exception:
            pass
        write_reflection_handler({
            "category": "skill-created",
            "lesson": f"Created/updated skill '{skill_name}' and pushed to GitHub",
        })
        return f"✅ Skill '{skill_name}' committed to GitHub at {github_path}"
    else:
        return f"⚠️ Skill saved locally but GitHub push failed (check GITHUB_TOKEN). Skill is in Neon DB."


def self_diagnose_handler(params: Dict[str, Any], **_) -> str:
    """Identify what skills or capabilities are missing based on recent failures and tasks.
    
    Returns a diagnosis: what went wrong, what skill gaps exist, what to create next.
    """
    if not _db_ok():
        return "⚠️ Database not available for diagnosis."

    # Get recent failed/blocked tasks
    tasks = _db_exec(
        "SELECT id, title, status, description FROM tasks WHERE status IN ('blocked','cancelled') ORDER BY updated_at DESC LIMIT 10"
    ) or []

    # Get recent reflections
    reflections = _db_exec(
        "SELECT category, lesson, what_failed FROM reflections WHERE what_failed != '' ORDER BY created_at DESC LIMIT 10"
    ) or []

    # Get existing skills
    existing = _db_exec("SELECT name FROM skills ORDER BY name") or []
    skill_names = [r.get("name", "") for r in existing]

    lines = ["🔍 SELF-DIAGNOSIS\n"]

    if tasks:
        lines.append(f"Recent blocked/cancelled tasks ({len(tasks)}):")
        for t in tasks:
            lines.append(f"  [{t.get('status')}] {t.get('title','')[:80]}")

    if reflections:
        lines.append(f"\nRecent failures ({len(reflections)}):")
        for r in reflections:
            lines.append(f"  [{r.get('category','?')}] {r.get('what_failed','')[:80]}")

    lines.append(f"\nExisting skills: {', '.join(skill_names[:20]) or 'none'}")
    lines.append("\n→ Use skill_manage(action='create') to fill gaps.")
    lines.append("→ Use write_reflection to document what you learn.")
    lines.append("→ Use commit_skill to persist new skills to GitHub.")

    return "\n".join(lines)


# ── Schemas ────────────────────────────────────────────────────────────────────

registry.register(
    name="write_reflection",
    toolset=TOOLSET,
    schema={
        "name": "write_reflection",
        "description": (
            "Record a lesson learned from completing (or failing) a task. "
            "Call this after every significant task — what worked, what failed, what to remember next time. "
            "This is how you improve over time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lesson": {"type": "string", "description": "The core lesson in 1-2 sentences"},
                "task_id": {"type": "string", "description": "Optional task ID this relates to"},
                "category": {
                    "type": "string",
                    "enum": ["coding", "db", "api", "deployment", "communication", "research", "skill-created", "soul-update", "general"],
                    "description": "Category for retrieval",
                },
                "what_worked": {"type": "string", "description": "What approach succeeded"},
                "what_failed": {"type": "string", "description": "What approach failed and why"},
                "applied_to": {"type": "string", "description": "Project/context this applies to"},
            },
            "required": ["lesson"],
        },
    },
    handler=write_reflection_handler,
    check_fn=_db_ok,
    requires_env=["DATABASE_URL"],
    is_async=False,
    description="Record a lesson from a task (self-improvement memory)",
)

registry.register(
    name="read_reflections",
    toolset=TOOLSET,
    schema={
        "name": "read_reflections",
        "description": "Recall past lessons. Search by category or keyword to find relevant experience before starting a task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["coding", "db", "api", "deployment", "communication", "research", "skill-created", "soul-update", "general"],
                },
                "keyword": {"type": "string", "description": "Search term to filter lessons"},
                "limit": {"type": "integer", "description": "Max lessons to return (default 10)"},
            },
            "required": [],
        },
    },
    handler=read_reflections_handler,
    check_fn=_db_ok,
    requires_env=["DATABASE_URL"],
    is_async=False,
    description="Recall past lessons by category/keyword",
)

registry.register(
    name="update_soul",
    toolset=TOOLSET,
    schema={
        "name": "update_soul",
        "description": (
            "Edit Soul.md — the document defining your personality, values, and behavioral rules. "
            "ONLY use for fundamental changes to how you should operate. "
            "Requires: full replacement content + a reason explaining the change."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Full Soul.md content (complete replacement)"},
                "reason": {"type": "string", "description": "Why you're updating Soul.md — what experience triggered this"},
            },
            "required": ["content", "reason"],
        },
    },
    handler=update_soul_handler,
    check_fn=lambda: True,
    requires_env=[],
    is_async=False,
    description="Edit the agent's Soul.md (GitHub-backed)",
)

registry.register(
    name="commit_skill",
    toolset=TOOLSET,
    schema={
        "name": "commit_skill",
        "description": (
            "Push a skill created with skill_manage to GitHub so it persists across redeployments. "
            "Call this after creating or significantly improving a skill."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "Skill directory name (e.g. 'my-new-skill')"},
                "commit_message": {"type": "string", "description": "Optional git commit message"},
            },
            "required": ["skill_name"],
        },
    },
    handler=commit_skill_handler,
    check_fn=lambda: bool(os.environ.get("GITHUB_TOKEN")),
    requires_env=["GITHUB_TOKEN"],
    is_async=False,
    description="Commit a skill to GitHub for persistence",
)

registry.register(
    name="self_diagnose",
    toolset=TOOLSET,
    schema={
        "name": "self_diagnose",
        "description": (
            "Analyze recent blocked tasks and failures to identify skill gaps. "
            "Use when you notice repeated failures or when starting a new work session."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    handler=self_diagnose_handler,
    check_fn=_db_ok,
    requires_env=["DATABASE_URL"],
    is_async=False,
    description="Identify skill gaps from recent failures",
)
