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
_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Dashboard</title>
<style>
  :root {
    --bg: #0d0f14;
    --surface: #161a23;
    --border: #252b38;
    --accent: #6c63ff;
    --accent2: #00d2ff;
    --green: #22d3a0;
    --red: #ff4d6d;
    --yellow: #fbbf24;
    --text: #e2e8f0;
    --muted: #64748b;
    --card: #1a1f2e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-height: 100vh; }

  /* Layout */
  .shell { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh; }
  .sidebar { background: var(--surface); border-right: 1px solid var(--border); padding: 24px 0; position: sticky; top: 0; height: 100vh; display: flex; flex-direction: column; }
  .main { padding: 32px; overflow-y: auto; }

  /* Sidebar */
  .logo { padding: 0 20px 24px; border-bottom: 1px solid var(--border); margin-bottom: 16px; }
  .logo h1 { font-size: 18px; font-weight: 700; background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: -0.3px; }
  .logo .sub { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--green); margin-right: 6px; box-shadow: 0 0 6px var(--green); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }

  nav a { display: flex; align-items: center; gap: 10px; padding: 10px 20px; color: var(--muted); text-decoration: none; font-size: 13px; font-weight: 500; transition: all .15s; border-left: 2px solid transparent; }
  nav a:hover { color: var(--text); background: rgba(255,255,255,.03); }
  nav a.active { color: var(--text); border-left-color: var(--accent); background: rgba(108,99,255,.08); }
  nav a .icon { font-size: 15px; width: 18px; text-align: center; }

  .sidebar-footer { margin-top: auto; padding: 16px 20px; border-top: 1px solid var(--border); font-size: 11px; color: var(--muted); }

  /* Cards */
  .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 28px; }
  .kpi { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
  .kpi .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .8px; margin-bottom: 10px; }
  .kpi .value { font-size: 28px; font-weight: 700; line-height: 1; }
  .kpi .sub { font-size: 12px; color: var(--muted); margin-top: 6px; }
  .kpi.green .value { color: var(--green); }
  .kpi.accent .value { color: var(--accent); }
  .kpi.blue .value { color: var(--accent2); }

  /* Section */
  .section { background: var(--card); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 20px; overflow: hidden; }
  .section-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border); }
  .section-header h2 { font-size: 14px; font-weight: 600; }
  .section-body { padding: 20px; }

  /* Table */
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .6px; padding: 0 0 12px; font-weight: 500; }
  td { padding: 10px 0; border-top: 1px solid var(--border); vertical-align: middle; }
  tr:first-child td { border-top: none; }

  /* Badges */
  .badge { display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 11px; font-weight: 600; }
  .badge.green { background: rgba(34,211,160,.15); color: var(--green); }
  .badge.red { background: rgba(255,77,109,.15); color: var(--red); }
  .badge.yellow { background: rgba(251,191,36,.15); color: var(--yellow); }
  .badge.accent { background: rgba(108,99,255,.15); color: var(--accent); }

  /* Events feed */
  .events-feed { max-height: 280px; overflow-y: auto; font-size: 12px; font-family: 'JetBrains Mono', 'Fira Code', monospace; }
  .event-line { padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,.04); color: var(--muted); }
  .event-line .ts { color: var(--accent); margin-right: 8px; }
  .event-line .msg { color: var(--text); }

  /* Memory search */
  .search-row { display: flex; gap: 10px; margin-bottom: 16px; }
  .search-row input { flex: 1; background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 8px; padding: 9px 14px; font-size: 13px; outline: none; transition: border .15s; }
  .search-row input:focus { border-color: var(--accent); }
  .search-row button { background: var(--accent); color: #fff; border: none; border-radius: 8px; padding: 9px 18px; font-size: 13px; font-weight: 600; cursor: pointer; transition: opacity .15s; }
  .search-row button:hover { opacity: .85; }
  .search-results { font-size: 13px; }
  .search-result { padding: 10px 0; border-bottom: 1px solid var(--border); }
  .search-result .score { color: var(--accent); font-size: 11px; margin-bottom: 4px; }

  /* Skills grid */
  .skills-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
  .skill-card { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 14px; transition: border-color .15s; }
  .skill-card:hover { border-color: var(--accent); }
  .skill-card .name { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
  .skill-card .desc { font-size: 11px; color: var(--muted); line-height: 1.5; }

  /* Uptime bar */
  .uptime-bar { height: 4px; background: var(--border); border-radius: 99px; margin-top: 10px; overflow: hidden; }
  .uptime-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent2)); border-radius: 99px; transition: width 1s; }

  /* Tabs */
  .tabs { display: flex; gap: 4px; margin-bottom: 20px; }
  .tab { padding: 7px 16px; border-radius: 8px; font-size: 13px; font-weight: 500; cursor: pointer; color: var(--muted); transition: all .15s; }
  .tab.active { background: rgba(108,99,255,.15); color: var(--accent); }
  .tab:hover:not(.active) { color: var(--text); }

  /* Pages */
  .page { display: none; }
  .page.active { display: block; }

  /* Repo add form */
  .add-row { display: flex; gap: 10px; margin-top: 16px; }
  .add-row input { flex: 1; background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 8px; padding: 8px 12px; font-size: 13px; outline: none; }
  .add-row input:focus { border-color: var(--accent); }
  .add-row button { background: var(--accent); color: #fff; border: none; border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .del-btn { background: none; border: 1px solid var(--border); color: var(--muted); border-radius: 6px; padding: 4px 10px; font-size: 11px; cursor: pointer; transition: all .15s; }
  .del-btn:hover { border-color: var(--red); color: var(--red); }

  .empty { color: var(--muted); font-size: 13px; text-align: center; padding: 32px 0; }
  .page-title { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
  .page-sub { font-size: 13px; color: var(--muted); margin-bottom: 24px; }

  ::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 99px; }
</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="logo">
      <h1>⚡ Hermes</h1>
      <div class="sub"><span class="status-dot" id="dot"></span><span id="status-text">connecting...</span></div>
    </div>
    <nav>
      <a href="#" class="active" data-page="overview" onclick="nav(this)"><span class="icon">📊</span>Overview</a>
      <a href="#" data-page="sessions" onclick="nav(this)"><span class="icon">💬</span>Sessions</a>
      <a href="#" data-page="skills" onclick="nav(this)"><span class="icon">🧠</span>Skills</a>
      <a href="#" data-page="repos" onclick="nav(this)"><span class="icon">📁</span>Repos</a>
      <a href="#" data-page="memory" onclick="nav(this)"><span class="icon">🔍</span>Memory</a>
      <a href="#" data-page="events" onclick="nav(this)"><span class="icon">⚡</span>Live Events</a>
    </nav>
    <div class="sidebar-footer">
      <div id="model-label">model: —</div>
      <div id="platform-label">platform: —</div>
    </div>
  </aside>

  <main class="main">

    <!-- OVERVIEW -->
    <div class="page active" id="page-overview">
      <div class="page-title">Overview</div>
      <div class="page-sub" id="overview-sub">Loading status...</div>

      <div class="kpi-grid">
        <div class="kpi green">
          <div class="label">Gateway</div>
          <div class="value" id="kpi-gateway">—</div>
          <div class="sub">core process</div>
        </div>
        <div class="kpi accent">
          <div class="label">Uptime</div>
          <div class="value" id="kpi-uptime">—</div>
          <div class="sub">since last deploy</div>
          <div class="uptime-bar"><div class="uptime-fill" id="uptime-fill" style="width:0%"></div></div>
        </div>
        <div class="kpi blue">
          <div class="label">Skills</div>
          <div class="value" id="kpi-skills">—</div>
          <div class="sub">loaded</div>
        </div>
        <div class="kpi">
          <div class="label">Sessions</div>
          <div class="value" id="kpi-sessions">—</div>
          <div class="sub">active</div>
        </div>
      </div>

      <div class="section">
        <div class="section-header"><h2>Active Sessions</h2></div>
        <div class="section-body">
          <div id="sessions-preview"><div class="empty">No active sessions</div></div>
        </div>
      </div>

      <div class="section">
        <div class="section-header"><h2>Recent Events</h2><span style="font-size:11px;color:var(--muted)" id="event-count">live</span></div>
        <div class="section-body">
          <div class="events-feed" id="events-mini"><div class="empty">Waiting for events...</div></div>
        </div>
      </div>
    </div>

    <!-- SESSIONS -->
    <div class="page" id="page-sessions">
      <div class="page-title">Sessions</div>
      <div class="page-sub">Active conversations and agent threads</div>
      <div class="section">
        <div class="section-body">
          <div id="sessions-full"><div class="empty">No sessions found</div></div>
        </div>
      </div>
    </div>

    <!-- SKILLS -->
    <div class="page" id="page-skills">
      <div class="page-title">Skills</div>
      <div class="page-sub" id="skills-sub">Loading skills...</div>
      <div class="skills-grid" id="skills-grid"></div>
    </div>

    <!-- REPOS -->
    <div class="page" id="page-repos">
      <div class="page-title">Repos</div>
      <div class="page-sub">GitHub repositories being watched</div>
      <div class="section">
        <div class="section-body">
          <div id="repos-list"></div>
          <div class="add-row">
            <input id="repo-owner" placeholder="owner" />
            <input id="repo-name" placeholder="repo" />
            <button onclick="addRepo()">+ Add</button>
          </div>
        </div>
      </div>
    </div>

    <!-- MEMORY -->
    <div class="page" id="page-memory">
      <div class="page-title">Memory Search</div>
      <div class="page-sub">Semantic search across agent memory</div>
      <div class="section">
        <div class="section-body">
          <div class="search-row">
            <input id="mem-query" placeholder="Search memory..." onkeydown="if(event.key==='Enter')searchMem()" />
            <button onclick="searchMem()">Search</button>
          </div>
          <div class="search-results" id="mem-results"></div>
        </div>
      </div>
    </div>

    <!-- EVENTS -->
    <div class="page" id="page-events">
      <div class="page-title">Live Events</div>
      <div class="page-sub">Real-time blackboard event stream (SSE)</div>
      <div class="section">
        <div class="section-header"><h2>Event Feed</h2><span class="badge green" id="sse-badge">connecting</span></div>
        <div class="section-body">
          <div class="events-feed" id="events-full" style="max-height:520px"></div>
        </div>
      </div>
    </div>

  </main>
</div>

<script>
const BASE = '';
let eventLog = [];
let sseConn = null;

// Nav
function nav(el) {
  event.preventDefault();
  document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('page-' + el.dataset.page).classList.add('active');
  if (el.dataset.page === 'skills') loadSkills();
  if (el.dataset.page === 'repos') loadRepos();
  if (el.dataset.page === 'sessions') loadSessionsFull();
}

// Format uptime
function fmtUptime(s) {
  if (s < 60) return s.toFixed(0) + 's';
  if (s < 3600) return (s/60).toFixed(0) + 'm';
  if (s < 86400) return (s/3600).toFixed(1) + 'h';
  return (s/86400).toFixed(1) + 'd';
}

// Load status
async function loadStatus() {
  try {
    const r = await fetch(BASE + '/api/status');
    const d = await r.json();
    document.getElementById('kpi-gateway').textContent = d.gateway_running ? '✓ ON' : '✗ OFF';
    document.getElementById('kpi-uptime').textContent = fmtUptime(d.uptime_seconds);
    document.getElementById('uptime-fill').style.width = Math.min(100, (d.uptime_seconds / 86400) * 100) + '%';
    document.getElementById('model-label').textContent = 'model: ' + (d.model || '—');
    document.getElementById('platform-label').textContent = 'platform: ' + (d.platform || '—');
    document.getElementById('overview-sub').textContent = 'v' + d.version + ' · ' + d.platform;
    document.getElementById('dot').style.background = '#22d3a0';
    document.getElementById('status-text').textContent = 'online';
  } catch(e) {
    document.getElementById('dot').style.background = '#ff4d6d';
    document.getElementById('status-text').textContent = 'offline';
  }
}

// Load sessions
async function loadSessions() {
  try {
    const r = await fetch(BASE + '/api/sessions');
    const d = await r.json();
    const sessions = d.sessions || [];
    document.getElementById('kpi-sessions').textContent = sessions.length;
    const el = document.getElementById('sessions-preview');
    if (!sessions.length) { el.innerHTML = '<div class="empty">No active sessions</div>'; return; }
    el.innerHTML = '<table><thead><tr><th>ID</th><th>Platform</th><th>Status</th></tr></thead><tbody>' +
      sessions.map(s => `<tr><td>${s.id||s.session_id||'—'}</td><td>${s.platform||'—'}</td><td><span class="badge green">active</span></td></tr>`).join('') +
      '</tbody></table>';
  } catch(e) {}
}

async function loadSessionsFull() {
  try {
    const r = await fetch(BASE + '/api/sessions');
    const d = await r.json();
    const sessions = d.sessions || [];
    const el = document.getElementById('sessions-full');
    if (!sessions.length) { el.innerHTML = '<div class="empty">No sessions found</div>'; return; }
    el.innerHTML = '<table><thead><tr><th>Session ID</th><th>Platform</th><th>Model</th><th>Status</th></tr></thead><tbody>' +
      sessions.map(s => `<tr>
        <td style="font-family:monospace;font-size:12px">${s.id||s.session_id||'—'}</td>
        <td>${s.platform||'—'}</td>
        <td><span class="badge accent">${s.model||'—'}</span></td>
        <td><span class="badge green">active</span></td>
      </tr>`).join('') + '</tbody></table>';
  } catch(e) {}
}

// Load skills
async function loadSkills() {
  try {
    const r = await fetch(BASE + '/api/skills');
    const d = await r.json();
    const skills = d.skills || [];
    document.getElementById('kpi-skills').textContent = skills.length;
    document.getElementById('skills-sub').textContent = skills.length + ' skills loaded';
    document.getElementById('skills-grid').innerHTML = skills.map(s =>
      `<div class="skill-card">
        <div class="name">${s.name}</div>
        <div class="desc">${s.description || 'No description'}</div>
        ${s.score !== null && s.score !== undefined ? `<div style="margin-top:6px"><span class="badge accent">score: ${s.score}</span></div>` : ''}
      </div>`
    ).join('');
  } catch(e) {}
}

// Load repos
async function loadRepos() {
  try {
    const r = await fetch(BASE + '/api/repos');
    const d = await r.json();
    const repos = d.repos || [];
    const el = document.getElementById('repos-list');
    if (!repos.length) { el.innerHTML = '<div class="empty">No repos configured</div>'; return; }
    el.innerHTML = '<table><thead><tr><th>Repo</th><th></th></tr></thead><tbody>' +
      repos.map(r => `<tr>
        <td><a href="https://github.com/${r.owner}/${r.repo}" target="_blank" style="color:var(--accent2);text-decoration:none">${r.owner}/${r.repo}</a></td>
        <td style="text-align:right"><button class="del-btn" onclick="delRepo('${r.owner}','${r.repo}')">remove</button></td>
      </tr>`).join('') + '</tbody></table>';
  } catch(e) {}
}

async function addRepo() {
  const owner = document.getElementById('repo-owner').value.trim();
  const repo = document.getElementById('repo-name').value.trim();
  if (!owner || !repo) return;
  await fetch(BASE + '/api/repos', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({owner, repo}) });
  document.getElementById('repo-owner').value = '';
  document.getElementById('repo-name').value = '';
  loadRepos();
}

async function delRepo(owner, repo) {
  await fetch(BASE + `/api/repos/${owner}/${repo}`, { method: 'DELETE' });
  loadRepos();
}

// Memory search
async function searchMem() {
  const q = document.getElementById('mem-query').value.trim();
  if (!q) return;
  document.getElementById('mem-results').innerHTML = '<div class="empty">Searching...</div>';
  try {
    const r = await fetch(BASE + '/api/memory/search?q=' + encodeURIComponent(q));
    const d = await r.json();
    const results = d.results || [];
    if (!results.length) { document.getElementById('mem-results').innerHTML = '<div class="empty">No results found</div>'; return; }
    document.getElementById('mem-results').innerHTML = results.map(r =>
      `<div class="search-result">
        ${r.score !== undefined ? `<div class="score">relevance: ${(r.score*100).toFixed(0)}%</div>` : ''}
        <div>${r.text || r.content || JSON.stringify(r)}</div>
      </div>`
    ).join('');
  } catch(e) { document.getElementById('mem-results').innerHTML = '<div class="empty">Search failed</div>'; }
}

// SSE events
function connectSSE() {
  if (sseConn) sseConn.close();
  sseConn = new EventSource(BASE + '/api/events');
  sseConn.onopen = () => { document.getElementById('sse-badge').textContent = 'live'; document.getElementById('sse-badge').className = 'badge green'; };
  sseConn.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (Object.keys(data).length === 0) return;
      const ts = new Date().toLocaleTimeString();
      const msg = JSON.stringify(data).slice(0, 120);
      eventLog.unshift({ts, msg});
      if (eventLog.length > 100) eventLog.pop();
      renderEvents();
    } catch(err) {}
  };
  sseConn.onerror = () => { document.getElementById('sse-badge').textContent = 'reconnecting'; document.getElementById('sse-badge').className = 'badge yellow'; };
}

function renderEvents() {
  const html = eventLog.length
    ? eventLog.map(e => `<div class="event-line"><span class="ts">${e.ts}</span><span class="msg">${e.msg}</span></div>`).join('')
    : '<div class="empty">Waiting for events...</div>';
  ['events-mini', 'events-full'].forEach(id => { const el = document.getElementById(id); if(el) el.innerHTML = html; });
  document.getElementById('event-count').textContent = eventLog.length + ' events';
}

// Init
async function init() {
  await loadStatus();
  await loadSessions();
  await loadSkills();
  connectSSE();
  setInterval(loadStatus, 15000);
  setInterval(loadSessions, 10000);
}

init();
</script>
</body>
</html>
"""

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
        # Health / liveness routes for Railway and other PaaS health checks
        app.router.add_get("/", self._handle_health)
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/dashboard", self._handle_dashboard)

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


    async def _handle_dashboard(self, request: "web.Request") -> "web.Response":
        return web.Response(
            text=_DASHBOARD_HTML,
            content_type="text/html",
            charset="utf-8",
        )

    async def _handle_health(self, request: "web.Request") -> "web.Response":
        """Health check endpoint for Railway / PaaS liveness probes."""
        return web.Response(
            text='{"status":"ok","service":"hermes-gateway"}',
            content_type="application/json",
            headers=self._cors_headers(),
        )

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
