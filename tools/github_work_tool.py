#!/usr/bin/env python3
"""
GitHub Work Tool — Clone, inspect, and run code from any GitHub repo.

Gives the agent the ability to:
- github_clone  : Clone a repo into a temp workspace using GITHUB_TOKEN
- github_ls     : List files/dirs in the cloned workspace
- github_read   : Read a file from the workspace
- github_exec   : Run a shell command inside the workspace
- github_push   : Commit + push changes back to the repo
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from tools.registry import registry

logger = logging.getLogger(__name__)
TOOLSET = "hermes-github"

# Shared workspace map: repo_full_name -> local_path
_WORKSPACES: Dict[str, str] = {}


def _get_token() -> str:
    return os.environ.get("GITHUB_TOKEN", "")


def _workspace(repo: str) -> Optional[str]:
    return _WORKSPACES.get(repo)


def _run(cmd: str, cwd: str, timeout: int = 60) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return {
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:2000],
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Command timed out", "exit_code": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}


# ── Handlers ──────────────────────────────────────────────────────────────────

def github_clone_handler(params: Dict[str, Any] = None, repo: str = "", branch: str = "main", **_) -> str:
    """Clone a GitHub repo into a temp workspace."""
    import shutil as _shutil
    if params is None: params = {}
    repo = repo or params.get("repo", "")
    branch = branch or params.get("branch", "main")
    repo = repo.strip().lstrip("https://github.com/").lstrip("/")

    if not repo:
        return "❌ repo is required (e.g. '0xMikey-ooze/believers-bookshelf-portal-dashboard')"

    token = _get_token()
    if not token:
        return "❌ GITHUB_TOKEN not set — cannot clone private repos."

    # Verify git is available
    if not _shutil.which("git"):
        return "❌ git is not installed in this environment. Container needs rebuild with git."

    # Reuse existing workspace if already cloned
    if repo in _WORKSPACES and Path(_WORKSPACES[repo]).exists():
        ws = _WORKSPACES[repo]
        # Pull latest
        _run(f"git pull origin {branch} --rebase 2>&1 | tail -3", cwd=ws)
        return f"✓ Already cloned at {ws} (pulled latest)"

    # Clone into /tmp/hermes-work/<repo-name>
    work_dir = Path("/tmp/hermes-work")
    work_dir.mkdir(parents=True, exist_ok=True)
    repo_name = repo.split("/")[-1]
    dest = str(work_dir / repo_name)

    if Path(dest).exists():
        import shutil
        shutil.rmtree(dest)

    clone_url = f"https://x-access-token:{token}@github.com/{repo}.git"
    result = _run(f"git clone --depth=20 -b {branch} {clone_url} {dest} 2>&1", cwd="/tmp")

    if result["exit_code"] != 0:
        return f"❌ Clone failed:\n{result['stderr'][:500]}"

    _WORKSPACES[repo] = dest
    # Get a quick overview
    ls = _run("ls -la", cwd=dest)
    pkg = ""
    if Path(dest + "/package.json").exists():
        pj = json.loads(Path(dest + "/package.json").read_text())
        pkg = f"\npackage.json: {pj.get('name','')} v{pj.get('version','')} — scripts: {list(pj.get('scripts',{}).keys())}"
    return f"✅ Cloned {repo} → {dest}\n{ls['stdout'][:600]}{pkg}"


def github_ls_handler(params: Dict[str, Any] = None, repo: str = "", path: str = "", **_) -> str:
    """List files in the cloned workspace."""
    if params is None: params = {}
    repo = (repo or params.get("repo", "")).strip().lstrip("https://github.com/").lstrip("/")
    subpath = (path or params.get("path", "")).strip("/")

    ws = _workspace(repo)
    if not ws:
        return f"❌ Repo '{repo}' not cloned yet. Call github_clone first."

    target = str(Path(ws) / subpath) if subpath else ws
    result = _run(f"find . -maxdepth 3 -not -path './.git/*' -not -path './node_modules/*' -not -path './.next/*' | sort | head -80", cwd=target)
    return result["stdout"] or result["stderr"]


def github_read_handler(params: Dict[str, Any] = None, repo: str = "", file_path: str = "", **_) -> str:
    """Read a file from the workspace."""
    if params is None: params = {}
    repo = (repo or params.get("repo", "")).strip().lstrip("https://github.com/").lstrip("/")
    file_path = (file_path or params.get("file_path", "")).strip("/")

    if not file_path:
        return "❌ file_path is required"

    ws = _workspace(repo)
    if not ws:
        return f"❌ Repo '{repo}' not cloned yet. Call github_clone first."

    full_path = Path(ws) / file_path
    if not full_path.exists():
        return f"❌ File not found: {file_path}"

    content = full_path.read_text(encoding="utf-8", errors="replace")
    if len(content) > 8000:
        return content[:8000] + f"\n\n... (truncated, file is {len(content)} chars)"
    return content


def github_exec_handler(params: Dict[str, Any] = None, repo: str = "", command: str = "", timeout: int = 60, **_) -> str:
    """Run a shell command in the workspace."""
    if params is None: params = {}
    repo = (repo or params.get("repo", "")).strip().lstrip("https://github.com/").lstrip("/")
    cmd = command or params.get("command", "")
    cmd = cmd.strip()
    timeout = int(timeout or params.get("timeout", 60))

    if not cmd:
        return "❌ command is required"

    ws = _workspace(repo)
    if not ws:
        return f"❌ Repo '{repo}' not cloned yet. Call github_clone first."

    result = _run(cmd, cwd=ws, timeout=min(timeout, 300))
    out = result["stdout"]
    err = result["stderr"]
    code = result["exit_code"]
    parts = []
    if out: parts.append(out)
    if err: parts.append(f"[stderr] {err}")
    parts.append(f"[exit {code}]")
    return "\n".join(parts)


def github_push_handler(params: Dict[str, Any] = None, repo: str = "", message: str = "", branch: str = "main", **_) -> str:
    """Commit and push changes in the workspace back to GitHub."""
    if params is None: params = {}
    repo = (repo or params.get("repo", "")).strip().lstrip("https://github.com/").lstrip("/")
    message = (message or params.get("message", "chore: agent update")).strip()
    branch = branch or params.get("branch", "main")

    ws = _workspace(repo)
    if not ws:
        return f"❌ Repo '{repo}' not cloned yet."

    token = _get_token()
    if not token:
        return "❌ GITHUB_TOKEN not set."

    # Set git identity
    _run('git config user.email "hermes@agent.local"', cwd=ws)
    _run('git config user.name "Hermes Agent"', cwd=ws)

    # Stage, commit, push
    r1 = _run("git add -A", cwd=ws)
    r2 = _run(f'git commit -m "{message}"', cwd=ws)
    if "nothing to commit" in r2["stdout"]:
        return "ℹ️ Nothing to commit — workspace is clean."

    r3 = _run(f"git push origin {branch}", cwd=ws, timeout=30)
    if r3["exit_code"] != 0:
        return f"❌ Push failed:\n{r3['stderr'][:500]}"

    # Get commit hash
    r4 = _run("git rev-parse --short HEAD", cwd=ws)
    sha = r4["stdout"].strip()
    return f"✅ Pushed to {repo}@{branch} — commit {sha}: {message}"


# ── Schemas ────────────────────────────────────────────────────────────────────

registry.register(
    name="github_clone",
    toolset=TOOLSET,
    schema={
        "name": "github_clone",
        "description": (
            "Clone a GitHub repo into a local workspace using GITHUB_TOKEN. "
            "Always do this first before reading files or running code. "
            "The token handles auth — you don't need credentials."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo in owner/name format, e.g. '0xMikey-ooze/believers-bookshelf-portal-dashboard'"},
                "branch": {"type": "string", "description": "Branch to clone (default: main)"},
            },
            "required": ["repo"],
        },
    },
    handler=github_clone_handler,
    check_fn=lambda: bool(_get_token()),
    requires_env=["GITHUB_TOKEN"],
    is_async=False,
    description="Clone a GitHub repo into a local workspace",
)

registry.register(
    name="github_ls",
    toolset=TOOLSET,
    schema={
        "name": "github_ls",
        "description": "List files in a cloned repo workspace. Must call github_clone first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo in owner/name format"},
                "path": {"type": "string", "description": "Subdirectory to list (optional)"},
            },
            "required": ["repo"],
        },
    },
    handler=github_ls_handler,
    check_fn=lambda: bool(_get_token()),
    requires_env=["GITHUB_TOKEN"],
    is_async=False,
    description="List files in a cloned repo workspace",
)

registry.register(
    name="github_read",
    toolset=TOOLSET,
    schema={
        "name": "github_read",
        "description": "Read a file from a cloned repo workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo in owner/name format"},
                "file_path": {"type": "string", "description": "File path relative to repo root"},
            },
            "required": ["repo", "file_path"],
        },
    },
    handler=github_read_handler,
    check_fn=lambda: bool(_get_token()),
    requires_env=["GITHUB_TOKEN"],
    is_async=False,
    description="Read a file from a cloned repo",
)

registry.register(
    name="github_exec",
    toolset=TOOLSET,
    schema={
        "name": "github_exec",
        "description": (
            "Run a shell command inside the cloned repo workspace. "
            "Use for: npm install, npm test, npm run build, git status, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo in owner/name format"},
                "command": {"type": "string", "description": "Shell command to run"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 60, max 300)"},
            },
            "required": ["repo", "command"],
        },
    },
    handler=github_exec_handler,
    check_fn=lambda: bool(_get_token()),
    requires_env=["GITHUB_TOKEN"],
    is_async=False,
    description="Run shell commands in a cloned repo workspace",
)

registry.register(
    name="github_push",
    toolset=TOOLSET,
    schema={
        "name": "github_push",
        "description": "Commit all changes in the workspace and push to GitHub.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo in owner/name format"},
                "message": {"type": "string", "description": "Commit message"},
                "branch": {"type": "string", "description": "Branch to push to (default: main)"},
            },
            "required": ["repo", "message"],
        },
    },
    handler=github_push_handler,
    check_fn=lambda: bool(_get_token()),
    requires_env=["GITHUB_TOKEN"],
    is_async=False,
    description="Commit and push changes to GitHub",
)
