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
<title>Hermes</title>
<style>
:root{--bg:#0d0f14;--surface:#161a23;--border:#252b38;--accent:#6c63ff;--accent2:#00d2ff;--green:#22d3a0;--red:#ff4d6d;--yellow:#fbbf24;--text:#e2e8f0;--muted:#64748b;--card:#1a1f2e}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;height:100vh;overflow:hidden}
.shell{display:grid;grid-template-columns:200px 1fr;height:100vh}
.sidebar{background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.logo{padding:20px;border-bottom:1px solid var(--border)}
.logo h1{font-size:16px;font-weight:700;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.logo .sub{font-size:11px;color:var(--muted);margin-top:3px}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--green);margin-right:5px;box-shadow:0 0 5px var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
nav{padding:8px 0;flex:1}
nav a{display:flex;align-items:center;gap:10px;padding:10px 16px;color:var(--muted);text-decoration:none;font-size:13px;font-weight:500;transition:all .12s;border-left:2px solid transparent;cursor:pointer}
nav a:hover{color:var(--text);background:rgba(255,255,255,.03)}
nav a.active{color:var(--text);border-left-color:var(--accent);background:rgba(108,99,255,.1)}
.sidebar-foot{padding:14px 16px;border-top:1px solid var(--border);font-size:11px;color:var(--muted);line-height:1.8}
.main{overflow:hidden;display:flex;flex-direction:column}
.page{display:none;flex:1;overflow:hidden;flex-direction:column}
.page.active{display:flex}
.page-inner{flex:1;overflow-y:auto;padding:28px}
/* KPI */
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px}
.kpi .lbl{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px}
.kpi .val{font-size:26px;font-weight:700}
.kpi .sub{font-size:11px;color:var(--muted);margin-top:5px}
.kpi.g .val{color:var(--green)}.kpi.a .val{color:var(--accent)}.kpi.b .val{color:var(--accent2)}
.upbar{height:3px;background:var(--border);border-radius:99px;margin-top:8px;overflow:hidden}
.upfill{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:99px;transition:width 1s}
/* Card */
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;margin-bottom:16px;overflow:hidden}
.card-head{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--border)}
.card-head h2{font-size:13px;font-weight:600}
.card-body{padding:18px}
/* Table */
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;padding-bottom:10px;font-weight:500}
td{padding:9px 0;border-top:1px solid var(--border);vertical-align:middle}
tr:first-child td{border-top:none}
.badge{display:inline-block;padding:2px 7px;border-radius:99px;font-size:10px;font-weight:600}
.badge.g{background:rgba(34,211,160,.15);color:var(--green)}
.badge.a{background:rgba(108,99,255,.15);color:var(--accent)}
.badge.y{background:rgba(251,191,36,.15);color:var(--yellow)}
/* Events */
.ev-feed{max-height:240px;overflow-y:auto;font-size:11px;font-family:'JetBrains Mono',monospace}
.ev-line{padding:5px 0;border-bottom:1px solid rgba(255,255,255,.04);display:flex;gap:8px}
.ev-ts{color:var(--accent);flex-shrink:0}
.ev-msg{color:var(--muted)}
/* CHAT */
#page-chat{height:100vh}
.chat-wrap{display:flex;flex-direction:column;height:100%}
.chat-msgs{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:12px}
.msg-row{display:flex;flex-direction:column}
.msg-row.user{align-items:flex-end}
.msg-row.agent{align-items:flex-start}
.msg-bubble{padding:10px 14px;border-radius:18px;max-width:72%;line-height:1.5;font-size:14px;word-break:break-word}
.msg-row.user .msg-bubble{background:var(--accent);color:#fff;border-radius:18px 18px 4px 18px}
.msg-row.agent .msg-bubble{background:var(--card);border:1px solid var(--border);border-radius:18px 18px 18px 4px;color:var(--text)}
.msg-meta{font-size:10px;color:var(--muted);margin-top:4px;padding:0 4px}
.typing{display:flex;gap:4px;padding:10px 14px;background:var(--card);border:1px solid var(--border);border-radius:18px 18px 18px 4px;align-self:flex-start;width:fit-content}
.typing span{width:6px;height:6px;border-radius:50%;background:var(--muted);animation:bounce .9s infinite}
.typing span:nth-child(2){animation-delay:.15s}
.typing span:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-6px)}}
.chat-input-row{padding:16px;border-top:1px solid var(--border);display:flex;gap:10px;background:var(--surface)}
.chat-input{flex:1;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:24px;padding:11px 18px;font-size:14px;outline:none;resize:none;transition:border .15s;font-family:inherit}
.chat-input:focus{border-color:var(--accent)}
.send-btn{background:var(--accent);color:#fff;border:none;border-radius:50%;width:42px;height:42px;font-size:18px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:opacity .15s}
.send-btn:hover{opacity:.85}
.send-btn:disabled{opacity:.4;cursor:not-allowed}
/* Repos */
.add-row{display:flex;gap:8px;margin-top:16px}
.add-row input{flex:1;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:8px 12px;font-size:13px;outline:none}
.add-row input:focus{border-color:var(--accent)}
.add-row button{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:8px 14px;font-size:13px;font-weight:600;cursor:pointer}
.del-btn{background:none;border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:3px 9px;font-size:11px;cursor:pointer;transition:all .12s}
.del-btn:hover{border-color:var(--red);color:var(--red)}
/* Activity */
.act-feed{font-size:12px;font-family:'JetBrains Mono',monospace;max-height:420px;overflow-y:auto}
.act-line{padding:6px 0;border-bottom:1px solid rgba(255,255,255,.04);display:flex;gap:10px;align-items:flex-start}
.act-ts{color:var(--accent);flex-shrink:0;font-size:11px}
.act-msg{color:var(--text);word-break:break-all}
.empty{color:var(--muted);text-align:center;padding:32px 0;font-size:13px}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--border);border-radius:99px}
</style>
</head>
<body>
<div class="shell">
<aside class="sidebar">
  <div class="logo">
    <h1>⚡ Hermes</h1>
    <div class="sub"><span class="dot" id="dot"></span><span id="status-txt">connecting...</span></div>
  </div>
  <nav>
    <a class="active" data-page="overview" onclick="nav(this,event)"><span>📊</span>Overview</a>
    <a data-page="chat" onclick="nav(this,event)"><span>💬</span>Chat</a>
    <a data-page="repos" onclick="nav(this,event)"><span>📁</span>Repos</a>
    <a data-page="activity" onclick="nav(this,event)"><span>⚡</span>Activity</a>
  </nav>
  <div class="sidebar-foot">
    <div id="foot-model">model: —</div>
    <div id="foot-platform">platform: —</div>
    <div id="foot-uptime">uptime: —</div>
  </div>
</aside>
<main class="main">

  <!-- OVERVIEW -->
  <div class="page active" id="page-overview">
    <div class="page-inner">
      <div class="kpi-grid">
        <div class="kpi g"><div class="lbl">Gateway</div><div class="val" id="kpi-gw">—</div><div class="sub">core process</div></div>
        <div class="kpi a"><div class="lbl">Uptime</div><div class="val" id="kpi-up">—</div><div class="upbar"><div class="upfill" id="upfill" style="width:0%"></div></div></div>
        <div class="kpi b"><div class="lbl">Skills</div><div class="val" id="kpi-sk">—</div><div class="sub">loaded</div></div>
        <div class="kpi"><div class="lbl">Sessions</div><div class="val" id="kpi-ss">—</div><div class="sub">active</div></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Active Sessions</h2></div>
        <div class="card-body" id="ov-sessions"><div class="empty">No active sessions</div></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Recent Activity</h2><span style="font-size:11px;color:var(--muted)" id="ev-count">live</span></div>
        <div class="card-body"><div class="ev-feed" id="ev-mini"><div class="empty">Waiting for events...</div></div></div>
      </div>
    </div>
  </div>

  <!-- CHAT -->
  <div class="page" id="page-chat">
    <div class="chat-wrap">
      <div class="chat-msgs" id="chat-msgs">
        <div class="msg-row agent"><div class="msg-bubble">👋 Hey! I'm Hermes. Ask me anything or give me a task.</div></div>
      </div>
      <div class="chat-input-row">
        <textarea class="chat-input" id="chat-in" placeholder="Message Hermes..." rows="1" onkeydown="chatKey(event)"></textarea>
        <button class="send-btn" id="send-btn" onclick="sendMsg()">↑</button>
      </div>
    </div>
  </div>

  <!-- REPOS -->
  <div class="page" id="page-repos">
    <div class="page-inner">
      <div class="card">
        <div class="card-head"><h2>Watched Repos</h2><button onclick="loadRepos()" style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:12px">↻ refresh</button></div>
        <div class="card-body">
          <div id="repos-list"><div class="empty">Loading...</div></div>
          <div class="add-row">
            <input id="r-owner" placeholder="owner" />
            <input id="r-repo" placeholder="repo" />
            <button onclick="addRepo()">+ Add</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ACTIVITY -->
  <div class="page" id="page-activity">
    <div class="page-inner">
      <div class="kpi-grid" style="grid-template-columns:repeat(3,1fr)">
        <div class="kpi g"><div class="lbl">Status</div><div class="val" id="act-gw">—</div></div>
        <div class="kpi a"><div class="lbl">Uptime</div><div class="val" id="act-up">—</div></div>
        <div class="kpi b"><div class="lbl">Model</div><div class="val" id="act-model" style="font-size:14px;margin-top:4px">—</div></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Live Event Stream</h2><span class="badge g" id="sse-badge">connecting</span></div>
        <div class="card-body"><div class="act-feed" id="act-feed"><div class="empty">Waiting for events...</div></div></div>
      </div>
    </div>
  </div>

</main>
</div>
<script>
const BASE='';
let evLog=[];
let sse=null;
let chatHistory=[];

function nav(el,e){
  if(e)e.preventDefault();
  document.querySelectorAll('nav a').forEach(a=>a.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('page-'+el.dataset.page).classList.add('active');
  if(el.dataset.page==='repos')loadRepos();
}

function fmt(s){if(s<60)return s.toFixed(0)+'s';if(s<3600)return(s/60).toFixed(0)+'m';if(s<86400)return(s/3600).toFixed(1)+'h';return(s/86400).toFixed(1)+'d';}

async function loadStatus(){
  try{
    const d=await fetch(BASE+'/api/status').then(r=>r.json());
    document.getElementById('kpi-gw').textContent=d.gateway_running?'● ON':'○ OFF';
    document.getElementById('kpi-up').textContent=fmt(d.uptime_seconds);
    document.getElementById('upfill').style.width=Math.min(100,(d.uptime_seconds/86400)*100)+'%';
    document.getElementById('foot-model').textContent='model: '+(d.model||'—');
    document.getElementById('foot-platform').textContent='platform: '+(d.platform||'—');
    document.getElementById('foot-uptime').textContent='uptime: '+fmt(d.uptime_seconds);
    document.getElementById('act-gw').textContent=d.gateway_running?'Online':'Offline';
    document.getElementById('act-up').textContent=fmt(d.uptime_seconds);
    document.getElementById('act-model').textContent=d.model||'—';
    document.getElementById('dot').style.background='var(--green)';
    document.getElementById('status-txt').textContent='online';
  }catch(e){
    document.getElementById('dot').style.background='var(--red)';
    document.getElementById('status-txt').textContent='offline';
  }
}

async function loadSessions(){
  try{
    const d=await fetch(BASE+'/api/sessions').then(r=>r.json());
    const ss=d.sessions||[];
    document.getElementById('kpi-ss').textContent=ss.length;
    const el=document.getElementById('ov-sessions');
    if(!ss.length){el.innerHTML='<div class="empty">No active sessions</div>';return;}
    el.innerHTML='<table><thead><tr><th>ID</th><th>Platform</th><th>Status</th></tr></thead><tbody>'+
      ss.map(s=>`<tr><td style="font-family:monospace;font-size:11px">${s.id||s.session_id||'—'}</td><td>${s.platform||'—'}</td><td><span class="badge g">active</span></td></tr>`).join('')+
      '</tbody></table>';
  }catch(e){}
}

async function loadSkills(){
  try{
    const d=await fetch(BASE+'/api/skills').then(r=>r.json());
    document.getElementById('kpi-sk').textContent=(d.skills||[]).length;
  }catch(e){}
}

async function loadRepos(){
  document.getElementById('repos-list').innerHTML='<div class="empty">Loading...</div>';
  try{
    const d=await fetch(BASE+'/api/repos').then(r=>r.json());
    const repos=d.repos||[];
    const el=document.getElementById('repos-list');
    if(!repos.length){el.innerHTML='<div class="empty">No repos configured</div>';return;}
    el.innerHTML='<table><thead><tr><th>Repository</th><th></th></tr></thead><tbody>'+
      repos.map(r=>`<tr>
        <td><a href="https://github.com/${r.owner}/${r.repo}" target="_blank" style="color:var(--accent2);text-decoration:none;font-size:13px">⎇ ${r.owner}/<strong>${r.repo}</strong></a></td>
        <td style="text-align:right"><button class="del-btn" onclick="delRepo('${r.owner}','${r.repo}')">remove</button></td>
      </tr>`).join('')+'</tbody></table>';
  }catch(e){document.getElementById('repos-list').innerHTML='<div class="empty">Failed to load repos</div>';}
}

async function addRepo(){
  const owner=document.getElementById('r-owner').value.trim();
  const repo=document.getElementById('r-repo').value.trim();
  if(!owner||!repo)return;
  await fetch(BASE+'/api/repos',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({owner,repo})});
  document.getElementById('r-owner').value='';
  document.getElementById('r-repo').value='';
  loadRepos();
}

async function delRepo(owner,repo){
  await fetch(BASE+`/api/repos/${owner}/${repo}`,{method:'DELETE'});
  loadRepos();
}

// Chat
function chatKey(e){
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();}
}

function appendMsg(role,text){
  const msgs=document.getElementById('chat-msgs');
  const ts=new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
  const div=document.createElement('div');
  div.className='msg-row '+role;
  div.innerHTML=`<div class="msg-bubble">${text.replace(/\n/g,'<br>')}</div><div class="msg-meta">${ts}</div>`;
  msgs.appendChild(div);
  msgs.scrollTop=msgs.scrollHeight;
  return div;
}

function showTyping(){
  const msgs=document.getElementById('chat-msgs');
  const div=document.createElement('div');
  div.className='msg-row agent';
  div.id='typing-ind';
  div.innerHTML='<div class="typing"><span></span><span></span><span></span></div>';
  msgs.appendChild(div);
  msgs.scrollTop=msgs.scrollHeight;
}

function hideTyping(){
  const el=document.getElementById('typing-ind');
  if(el)el.remove();
}

async function sendMsg(){
  const inp=document.getElementById('chat-in');
  const btn=document.getElementById('send-btn');
  const text=inp.value.trim();
  if(!text)return;
  inp.value='';
  inp.style.height='auto';
  appendMsg('user',text);
  btn.disabled=true;
  showTyping();
  try{
    const r=await fetch(BASE+'/api/chat',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:text})
    });
    const d=await r.json();
    hideTyping();
    appendMsg('agent',d.response||'(no response)');
  }catch(e){
    hideTyping();
    appendMsg('agent','⚠️ Connection error. Is the gateway running?');
  }
  btn.disabled=false;
  inp.focus();
}

// SSE
function connectSSE(){
  if(sse)sse.close();
  sse=new EventSource(BASE+'/api/events');
  sse.onopen=()=>{
    const b=document.getElementById('sse-badge');
    if(b){b.textContent='live';b.className='badge g';}
  };
  sse.onmessage=(e)=>{
    try{
      const data=JSON.parse(e.data);
      if(!Object.keys(data).length)return;
      const ts=new Date().toLocaleTimeString();
      const msg=JSON.stringify(data).slice(0,140);
      evLog.unshift({ts,msg});
      if(evLog.length>150)evLog.pop();
      renderEvents();
    }catch(err){}
  };
  sse.onerror=()=>{
    const b=document.getElementById('sse-badge');
    if(b){b.textContent='reconnecting';b.className='badge y';}
  };
}

function renderEvents(){
  const html=evLog.length
    ?evLog.map(e=>`<div class="ev-line"><span class="ev-ts">${e.ts}</span><span class="ev-msg">${e.msg}</span></div>`).join('')
    :'<div class="empty">Waiting for events...</div>';
  ['ev-mini','act-feed'].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML=html;});
  const c=document.getElementById('ev-count');
  if(c)c.textContent=evLog.length+' events';
}

// Auto-resize textarea
document.getElementById('chat-in').addEventListener('input',function(){
  this.style.height='auto';
  this.style.height=Math.min(this.scrollHeight,120)+'px';
});

async function init(){
  await loadStatus();
  await Promise.all([loadSessions(),loadSkills()]);
  connectSSE();
  setInterval(loadStatus,15000);
  setInterval(loadSessions,10000);
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
        app.router.add_post("/api/chat", self._handle_chat)
        app.router.add_options("/api/chat", self._handle_options)
        app.router.add_post("/api/chat", self._handle_chat)
        app.router.add_options("/api/chat", self._handle_options)
        app.router.add_get("/api/activity", self._handle_activity)

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



    async def _handle_chat(self, request: "web.Request") -> "web.Response":
        """Web chat endpoint — injects a message into the gateway runner."""
        try:
            body = await request.json()
        except Exception:
            return self._error("Invalid JSON body")

        message = (body.get("message") or "").strip()
        if not message:
            return self._error("Missing field: message")

        try:
            from gateway import run as _run
            runner = getattr(_run, "_active_runner", None)
            if runner is None:
                return self._json({"response": "Agent not ready — runner not initialized."})

            from gateway.session import SessionSource
            from gateway.config import Platform
            from gateway.platforms.base import MessageEvent

            source = SessionSource(
                platform=Platform.TELEGRAM,
                chat_id="web-dashboard",
                user_id="dashboard",
                user_name="Dashboard",
                chat_type="dm",
            )
            event = MessageEvent(text=message, source=source)
            response = await runner._handle_message(event)
            return self._json({"response": response or "(no response)"})
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning("Chat handler error: %s", exc)
            return self._json({"response": f"Error: {exc}"})


    async def _handle_chat(self, request: "web.Request") -> "web.Response":
        """Web chat endpoint — inject a message into the gateway and return the response."""
        try:
            body = await request.json()
        except Exception:
            return self._error("Invalid JSON body")

        message = (body.get("message") or "").strip()
        if not message:
            return self._error("Missing required field: message")

        try:
            from gateway import run as _run
            from gateway.session import SessionSource
            from gateway.config import Platform
            from gateway.platforms.base import MessageEvent

            runner = getattr(_run, "_active_runner", None)
            if runner is None:
                return self._json({"response": "Agent not ready — gateway not started yet."})

            source = SessionSource(
                platform=Platform.TELEGRAM,
                chat_id="web-dashboard",
                user_id="dashboard",
                user_name="Dashboard",
                chat_type="dm",
            )
            event = MessageEvent(text=message, source=source)
            response = await runner._handle_message(event)
            return self._json({"response": response or ""})
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning("Chat handler error: %s", exc)
            return self._json({"response": f"Error: {exc}"})

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
