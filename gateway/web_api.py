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

# DB layer — gracefully disabled if psycopg2/DATABASE_URL not available
try:
    from gateway.db import (
        tasks_list as db_tasks_list,
        task_get as db_task_get,
        task_upsert as db_task_upsert,
        task_update_status as db_task_update_status,
        task_delete as db_task_delete,
        event_log as db_event_log,
        events_list as db_events_list,
        skill_upsert as db_skill_upsert,
        repos_list as db_repos_list,
        repo_upsert as db_repo_upsert,
        repo_delete as db_repo_delete,
        is_available as db_available,
    )
except Exception:
    db_tasks_list = db_task_get = db_task_upsert = db_task_update_status = None
    db_task_delete = db_event_log = db_events_list = db_skill_upsert = db_available = None
    db_repos_list = db_repo_upsert = db_repo_delete = None

_START_TIME = time.time()
_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Hermes</title>
<style>
:root{--bg:#121212;--text:#F4F4F4;--muted:#888;--accent:#EFA024;--divider:#2A2A2A;--hover:#171717;--font:'Helvetica Neue',Helvetica,Arial,sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--font);-webkit-font-smoothing:antialiased;height:100vh;display:flex;flex-direction:column;overflow:hidden}
.top-bar{padding:1.1rem 2rem;border-bottom:1px solid var(--divider);display:flex;justify-content:space-between;align-items:center;flex-shrink:0}
.sys-label{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.top-nav{display:flex}
.top-nav a{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);text-decoration:none;padding:4px 14px;border-left:1px solid var(--divider);cursor:pointer;transition:color .15s}
.top-nav a:first-child{border-left:none}
.top-nav a:hover,.top-nav a.active{color:var(--accent)}
.status-ind{display:flex;align-items:center;gap:8px;font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.dot{width:6px;height:6px;border-radius:50%;background:var(--muted)}
.dot.online{background:var(--accent);box-shadow:0 0 8px rgba(239,160,36,.45);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.page{display:none;flex:1;overflow:hidden}
.page.active{display:flex}
/* WORKSPACE */
.workspace{display:grid;grid-template-columns:1fr 380px;flex:1;overflow:hidden}
/* PANELS */
.panel{display:flex;flex-direction:column;overflow:hidden;border-right:1px solid var(--divider)}
.panel:last-child{border-right:none}
.panel-head{padding:1.75rem 2rem 1.25rem;border-bottom:1px solid var(--divider);flex-shrink:0}
.eyebrow{font-size:.65rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:.6rem}
.big-title{font-size:1.6rem;font-weight:400;text-transform:uppercase;letter-spacing:-.02em;line-height:1.1;margin-bottom:.6rem}
.panel-desc{font-size:.78rem;line-height:1.6;color:var(--muted)}
/* KPI strip */
.kpi-strip{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--divider);flex-shrink:0}
.kpi-cell{padding:1rem 2rem;border-right:1px solid var(--divider)}
.kpi-cell:last-child{border-right:none}
.kpi-lbl{font-size:.6rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:5px}
.kpi-val{font-size:1.3rem;font-weight:400}
.kpi-val.on{color:var(--accent)}
/* Task list */
.scroll{flex:1;overflow-y:auto}
.task-item{padding:1.5rem 2rem;border-bottom:1px solid var(--divider);display:grid;grid-template-columns:120px 1fr;gap:1.25rem;align-items:start;transition:background .15s}
.task-item:hover{background:var(--hover)}
.t-meta{font-size:.65rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);display:flex;align-items:center;gap:5px;padding-top:3px}
.sdot{width:5px;height:5px;border-radius:50%;background:var(--muted);flex-shrink:0}
.task-item.active .sdot{background:var(--accent);box-shadow:0 0 5px rgba(239,160,36,.5);animation:pulse 2s infinite}
.task-item.active .t-meta{color:var(--accent)}
.task-item.pending{opacity:.45}
.t-name{font-size:.95rem;font-weight:400;text-transform:uppercase;letter-spacing:-.01em;margin-bottom:.4rem}
.t-info{font-size:.72rem;line-height:1.5;color:var(--muted)}
.t-actions{display:flex;gap:10px;margin-top:.6rem}
.lnk{font-size:.65rem;text-transform:uppercase;letter-spacing:.06em;background:none;border:none;border-bottom:1px solid var(--divider);color:var(--muted);cursor:pointer;padding-bottom:2px;font-family:var(--font);transition:color .12s,border-color .12s}
.lnk:hover{color:var(--text);border-bottom-color:var(--text)}
.lnk.accent{color:var(--accent);border-bottom-color:var(--accent)}
.lnk.danger:hover{color:#ff4d6d;border-bottom-color:#ff4d6d}
.lnk.main{color:var(--accent);border-bottom-color:var(--accent)}
.col-empty{padding:2.5rem 2rem;font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:#333}
/* Task add bar */
.add-bar{border-top:1px solid var(--divider);padding:1rem 2rem;display:flex;gap:.75rem;align-items:center;flex-shrink:0}
.add-bar select,.add-bar input{background:transparent;border:none;border-bottom:1px solid var(--divider);color:var(--text);font-family:var(--font);font-size:.78rem;padding:4px 0;outline:none;transition:border-color .15s}
.add-bar select{color:var(--muted);width:150px;cursor:pointer}
.add-bar select option{background:#1a1a1a}
.add-bar input{flex:1}
.add-bar input::placeholder{color:#333;text-transform:uppercase;font-size:.7rem;letter-spacing:.05em}
.add-bar input:focus,.add-bar select:focus{border-bottom-color:var(--text)}
/* Chat */
.chat-wrap{display:flex;flex-direction:column;height:100%}
.chat-msgs{flex:1;overflow-y:auto;padding:1.5rem 2rem;display:flex;flex-direction:column;gap:1.75rem}
.msg{display:flex;flex-direction:column;gap:3px;max-width:92%}
.msg.user{align-self:flex-end;text-align:right}
.msg-sender{font-size:.65rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.msg.agent .msg-sender{color:var(--accent)}
.msg-content{font-size:.88rem;line-height:1.65}
.msg.user .msg-content{color:var(--muted)}
.typing-row{display:flex;gap:4px;align-items:center;padding:3px 0}
.tdot{width:5px;height:5px;border-radius:50%;background:var(--muted);animation:bounce .9s infinite}
.tdot:nth-child(2){animation-delay:.15s}.tdot:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-5px)}}
.chat-foot{padding:1.25rem 2rem;border-top:1px solid var(--divider);flex-shrink:0}
.chat-foot textarea{width:100%;background:transparent;border:none;border-bottom:1px solid var(--divider);color:var(--text);font-family:var(--font);font-size:.88rem;padding:4px 0 8px;resize:none;outline:none;min-height:34px;line-height:1.5;transition:border-color .2s}
.chat-foot textarea:focus{border-bottom-color:var(--text)}
.chat-foot textarea::placeholder{color:#333;text-transform:uppercase;font-size:.7rem;letter-spacing:.05em}
.chat-foot-row{display:flex;justify-content:space-between;align-items:center;margin-top:.6rem}
.hint{font-size:.6rem;text-transform:uppercase;letter-spacing:.07em;color:#333}
/* Repos page */
.full-panel{flex:1;display:flex;flex-direction:column;overflow:hidden}
.repo-item{padding:1.25rem 2rem;border-bottom:1px solid var(--divider);display:flex;align-items:center;justify-content:space-between;transition:background .15s}
.repo-item:hover{background:var(--hover)}
.r-name{font-size:.9rem;text-transform:uppercase;letter-spacing:-.01em}
.r-sub{font-size:.7rem;color:var(--muted);margin-top:2px}
.repo-actions{display:flex;gap:10px}
/* Skills/Soul editor */
.editor-grid{display:grid;grid-template-columns:220px 1fr;flex:1;overflow:hidden}
.skill-list{border-right:1px solid var(--divider);overflow-y:auto}
.skill-row{padding:.9rem 1.5rem;border-bottom:1px solid var(--divider);cursor:pointer;transition:background .15s}
.skill-row:hover{background:var(--hover)}
.skill-row.active{background:var(--hover);border-left:2px solid var(--accent)}
.skill-row.active .sk-name{color:var(--accent)}
.sk-name{font-size:.8rem;text-transform:uppercase;letter-spacing:-.01em}
.sk-desc{font-size:.65rem;color:var(--muted);margin-top:2px;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.editor-pane{display:flex;flex-direction:column;overflow:hidden}
.editor-head{padding:1rem 1.5rem;border-bottom:1px solid var(--divider);display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.editor-title{font-size:.8rem;text-transform:uppercase;letter-spacing:-.01em}
textarea.code-editor{flex:1;background:var(--bg);border:none;color:var(--text);font-family:'Menlo','Courier New',monospace;font-size:.78rem;line-height:1.6;padding:1.25rem 1.5rem;resize:none;outline:none;overflow-y:auto}
/* Activity */
.ev-item{padding:.9rem 2rem;border-bottom:1px solid var(--divider);display:grid;grid-template-columns:75px 1fr;gap:1.25rem;font-size:.72rem;font-family:'Menlo','Courier New',monospace}
.ev-ts{color:var(--accent)}.ev-msg{color:var(--muted);word-break:break-all}
.ev-empty{padding:2.5rem 2rem;font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:#333}
/* Inline input rows */
.input-row{display:flex;gap:.75rem;padding:1.25rem 2rem;border-bottom:1px solid var(--divider);flex-shrink:0}
.input-row input{background:transparent;border:none;border-bottom:1px solid var(--divider);color:var(--text);font-family:var(--font);font-size:.78rem;padding:4px 0;outline:none;flex:1;transition:border-color .15s}
.input-row input:focus{border-bottom-color:var(--text)}
/* Scrollbar */
::-webkit-scrollbar{width:3px}::-webkit-scrollbar-track{background:var(--bg)}::-webkit-scrollbar-thumb{background:var(--divider)}
</style>
</head>
<body>
<header class="top-bar">
  <div class="sys-label">Hermes // System Ops Terminal</div>
  <nav class="top-nav">
    <a class="active" data-page="main" onclick="nav(this,event)">Operations</a>
    <a data-page="repos" onclick="nav(this,event)">Repos</a>
    <a data-page="skills" onclick="nav(this,event)">Skills</a>
    <a data-page="activity" onclick="nav(this,event)">Activity</a>
  </nav>
  <div class="status-ind">
    <div class="dot" id="dot"></div>
    <span id="status-txt">connecting</span>
    <span style="margin-left:6px;color:var(--divider)">|</span>
    <span id="uptime-txt">—</span>
  </div>
</header>

<!-- MAIN -->
<div class="page active" id="page-main" style="flex-direction:column">
  <div class="kpi-strip">
    <div class="kpi-cell"><div class="kpi-lbl">Gateway</div><div class="kpi-val" id="kpi-gw">—</div></div>
    <div class="kpi-cell"><div class="kpi-lbl">In Progress</div><div class="kpi-val" id="kpi-active">0</div></div>
    <div class="kpi-cell"><div class="kpi-lbl">Backlog</div><div class="kpi-val" id="kpi-backlog">0</div></div>
    <div class="kpi-cell"><div class="kpi-lbl">Done</div><div class="kpi-val" id="kpi-done">0</div></div>
  </div>
  <div class="workspace">
    <section class="panel">
      <div class="panel-head">
        <div class="eyebrow">Task Queue</div>
        <h1 class="big-title" id="op-title">Standby</h1>
        <p class="panel-desc" id="op-desc">No active operations.</p>
      </div>
      <div class="scroll" id="task-list"><div class="col-empty">No tasks assigned</div></div>
      <div class="add-bar">
        <select id="nt-repo"><option value="">— Repo —</option></select>
        <input id="nt-title" placeholder="Task description..." onkeydown="if(event.key==='Enter')addTask()"/>
        <button class="lnk main" onclick="addTask()">Assign →</button>
      </div>
    </section>
    <section class="panel" style="border-right:none">
      <div class="panel-head"><div class="eyebrow">Agent Comm Link</div></div>
      <div class="chat-wrap">
        <div class="chat-msgs" id="chat-msgs">
          <div class="msg agent"><span class="msg-sender">Hermes Core</span><p class="msg-content">System online. Awaiting instructions.</p></div>
        </div>
        <div class="chat-foot">
          <textarea id="chat-in" placeholder="Transmit instruction..." rows="1" onkeydown="chatKey(event)"></textarea>
          <div class="chat-foot-row">
            <span class="hint">Enter to send · Shift+Enter new line</span>
            <button class="lnk main" onclick="sendMsg()">Transmit</button>
          </div>
        </div>
      </div>
    </section>
  </div>
</div>

<!-- REPOS -->
<div class="page" id="page-repos" style="flex-direction:column">
  <div class="full-panel">
    <div class="panel-head" style="display:flex;align-items:flex-start;justify-content:space-between">
      <div>
        <div class="eyebrow">Repository Registry</div>
        <h1 class="big-title" style="font-size:1.2rem">Watched Repos</h1>
      </div>
      <div style="display:flex;gap:1rem;align-items:center;padding-top:.5rem">
        <button class="lnk main" onclick="syncGitHub()">↓ Pull from GitHub</button>
        <button class="lnk" onclick="loadRepos()">↻ Refresh</button>
      </div>
    </div>
    <!-- Skill import bar -->
    <div style="display:flex;gap:8px;padding:12px 0 4px 0;border-top:1px solid #222;margin-top:12px">
      <div style="font-size:10px;color:#888;letter-spacing:.08em;text-transform:uppercase;padding-top:8px;white-space:nowrap">Import Skill:</div>
      <input id="skill-import-url" type="text" placeholder="GitHub URL or clawhub slug..."
        style="flex:1;background:#1a1a1a;border:1px solid #333;color:#e0e0e0;padding:6px 10px;font-size:11px;font-family:inherit;">
      <button class="lnk main" onclick="importSkill()">↓ IMPORT</button>
    </div>
    <div id="import-status" style="font-size:11px;min-height:14px;padding-bottom:8px;"></div>
    <div class="input-row">
      <input id="r-owner" placeholder="Owner" style="max-width:140px"/>
      <input id="r-repo" placeholder="Repo name"/>
      <button class="lnk main" onclick="addRepo()">+ Register</button>
    </div>
    <div class="scroll" id="repos-list"><div class="ev-empty">Loading...</div></div>
  </div>
</div>

<!-- SKILLS / SOUL EDITOR -->
<div class="page" id="page-skills" style="flex-direction:column">
  <div style="flex:1;display:flex;flex-direction:column;overflow:hidden">
    <div class="panel-head" style="display:flex;align-items:center;justify-content:space-between;flex-shrink:0">
      <div><div class="eyebrow">Agent Configuration</div><h1 class="big-title" style="font-size:1.2rem">Skills & Soul</h1></div>
      <div style="display:flex;gap:1rem">
        <button class="lnk" onclick="loadSkillList()">↻ Refresh</button>
      </div>
    </div>
    <div class="editor-grid">
      <div class="skill-list" id="skill-list"><div class="ev-empty">Loading...</div></div>
      <div class="editor-pane">
        <div class="editor-head">
          <span class="editor-title" id="editor-title">Select a skill or Soul.md</span>
          <div style="display:flex;gap:1rem">
            <button class="lnk main" id="save-btn" onclick="saveCurrentFile()" style="display:none">Save ↗</button>
          </div>
        </div>
        <textarea class="code-editor" id="code-editor" placeholder="Select a file from the list to edit..." spellcheck="false"></textarea>
      </div>
    </div>
  </div>
</div>

<!-- ACTIVITY -->
<div class="page" id="page-activity" style="flex-direction:column">
  <div class="panel-head" style="flex-shrink:0;display:flex;align-items:center;justify-content:space-between">
    <div><div class="eyebrow">Live Event Stream</div><h1 class="big-title" style="font-size:1.2rem">System Activity</h1></div>
    <span class="sys-label" id="ev-status">Connecting...</span>
  </div>
  <div class="scroll" id="act-feed"><div class="ev-empty">Waiting for events...</div></div>
</div>

<script>
const BASE='';
let evLog=[],sse=null,allTasks=[],allRepos=[],curFile=null;

function nav(el,e){
  if(e)e.preventDefault();
  document.querySelectorAll('.top-nav a').forEach(a=>a.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  const pg=el.dataset.page;
  document.getElementById('page-'+pg).classList.add('active');
  if(pg==='repos')loadRepos();
  if(pg==='skills')loadSkillList();
  if(pg==='activity')document.getElementById('ev-status').textContent=evLog.length+' events';
}

function fmt(s){if(!s)return '--';if(s<60)return s.toFixed(0)+'s';if(s<3600)return(s/60).toFixed(0)+'m';if(s<86400)return(s/3600).toFixed(1)+'h';return(s/86400).toFixed(1)+'d';}
function timeAgo(iso){if(!iso)return '';const clean=iso.endsWith('Z')?iso:iso.replace(/\+00:00$/,'Z');const d=new Date(clean),s=Math.floor((Date.now()-d)/1000);if(isNaN(s))return '';if(s<60)return s+'s ago';if(s<3600)return Math.floor(s/60)+'m ago';if(s<86400)return Math.floor(s/3600)+'h ago';return Math.floor(s/86400)+'d ago';}
function ts(){return new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});}

async function loadStatus(){
  try{
    const d=await fetch(BASE+'/api/status').then(r=>r.json());
    document.getElementById('kpi-gw').textContent=d.gateway_running?'ONLINE':'OFFLINE';
    document.getElementById('kpi-gw').className='kpi-val'+(d.gateway_running?' on':'');
    document.getElementById('uptime-txt').textContent=fmt(d.uptime_seconds);
    document.getElementById('dot').className='dot'+(d.gateway_running?' online':'');
    document.getElementById('status-txt').textContent=d.gateway_running?'online':'offline';
  }catch(e){
    document.getElementById('dot').className='dot';
    document.getElementById('status-txt').textContent='offline';
  }
}

async function loadTasks(){
  try{
    const d=await fetch(BASE+'/api/tasks').then(r=>r.json());
    allTasks=d.tasks||[];
    renderTasks();
    document.getElementById('kpi-active').textContent=allTasks.filter(t=>t.status==='in_progress').length;
    document.getElementById('kpi-backlog').textContent=allTasks.filter(t=>t.status==='backlog').length;
    document.getElementById('kpi-done').textContent=allTasks.filter(t=>t.status==='done').length;
    const active=allTasks.filter(t=>t.status==='in_progress');
    const queued=allTasks.filter(t=>t.status==='backlog');
    const featured=active[0]||queued[0]||null;
    if(featured){
      const prefix=featured.status==='in_progress'?'Processing: ':'Queued: ';
      document.getElementById('op-title').textContent=featured.title.toUpperCase();
      document.getElementById('op-desc').textContent=prefix+(featured.description||featured.repo);
    }else{document.getElementById('op-title').textContent='STANDBY';document.getElementById('op-desc').textContent='No active operations.';}
  }catch(e){}
}

function renderTasks(){
  const el=document.getElementById('task-list');
  if(!allTasks.length){el.innerHTML='<div class="col-empty">No tasks assigned</div>';return;}
  const sorted=[...allTasks].sort((a,b)=>{const o={in_progress:0,pending:1,backlog:1,done:2};return(o[a.status]||1)-(o[b.status]||1);});
  el.innerHTML=sorted.map(t=>{
    const isA=t.status==='in_progress',isDone=t.status==='done';
    const isPending=t.status==='pending';const lbl=isA?'Processing':isDone?'Completed':isPending?'Pending':'Queued';
    return `<div class="task-item${isA?' active':''}${t.status==='pending'||t.status==='backlog'?' pending':''}">
      <div class="t-meta"><span class="sdot"></span>${lbl} <span style="opacity:.45;font-size:.65rem;margin-left:6px">#${(t.id||'').slice(-6)}</span></div>
      <div>
        <div class="t-name">${t.title}</div>
        ${t.description?`<div class="t-info">${t.description}</div>`:''}
        <div class="t-info" style="margin-top:3px">${t.repo||''} ${t.repo?'&middot;':''} ${timeAgo(t.created_at||t.updated_at)}</div>
        <div class="t-actions">
          ${isA?`<button class="lnk accent" onclick="moveTask('${t.id}','done')">Mark Done</button>`:''}
          ${t.status==='backlog'?`<button class="lnk accent" onclick="moveTask('${t.id}','in_progress')">Start</button>`:''}
          ${isDone?`<button class="lnk" onclick="moveTask('${t.id}','backlog')">Reopen</button>`:''}
          <button class="lnk danger" onclick="deleteTask('${t.id}')">Remove</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

async function addTask(){
  const repo=document.getElementById('nt-repo').value;
  const title=document.getElementById('nt-title').value.trim();
  if(!repo||!title)return;
  document.getElementById('nt-title').value='';
  await fetch(BASE+'/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({repo,title,description:'',priority:'normal'})});
  loadTasks();
}
async function moveTask(id,status){await fetch(BASE+`/api/tasks/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});loadTasks();}
async function deleteTask(id){await fetch(BASE+`/api/tasks/${id}`,{method:'DELETE'});loadTasks();}

// REPOS
async function loadRepos(){
  document.getElementById('repos-list').innerHTML='<div class="ev-empty">Loading...</div>';
  try{
    const d=await fetch(BASE+'/api/repos').then(r=>r.json());
    allRepos=d.repos||[];
    populateRepoDropdown();
    if(!allRepos.length){document.getElementById('repos-list').innerHTML='<div class="ev-empty">No repos registered. Pull from GitHub or add manually.</div>';return;}
    document.getElementById('repos-list').innerHTML=allRepos.map(r=>`
      <div class="repo-item">
        <div><div class="r-name">${r.owner} / ${r.repo}</div><div class="r-sub">github.com/${r.owner}/${r.repo}${r.private?' &middot; private':''}</div></div>
        <div class="repo-actions"><button class="lnk danger" onclick="delRepo('${r.owner}','${r.repo}')">Deregister</button></div>
      </div>`).join('');
  }catch(e){document.getElementById('repos-list').innerHTML='<div class="ev-empty">Connection error</div>';}
}

function populateRepoDropdown(){
  const sel=document.getElementById('nt-repo');
  const cur=sel.value;
  sel.innerHTML='<option value="">— Repo —</option>';
  allRepos.forEach(r=>{const o=document.createElement('option');o.value=`${r.owner}/${r.repo}`;o.textContent=`${r.owner}/${r.repo}`;sel.appendChild(o);});
  sel.value=cur;
}

async function importSkill() {
  const src = document.getElementById('skill-import-url').value.trim();
  const el = document.getElementById('import-status');
  if (!src) { el.textContent = 'Enter a GitHub URL or clawhub slug first.'; el.style.color='#f88'; return; }
  el.style.color = '#888';
  el.textContent = 'Importing...';
  try {
    const r = await fetch('/api/skills/import', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:src})});
    const d = await r.json();
    if (d.ok) {
      el.style.color = '#4caf50';
      el.textContent = '\u2713 Skill "' + d.skill + '" installed — ' + d.bytes + ' bytes.';
      document.getElementById('skill-import-url').value = '';
    } else {
      el.style.color = '#f44336';
      el.textContent = '\u2717 ' + (d.error || 'Import failed');
    }
  } catch(e) { el.style.color='#f44'; el.textContent='Network error: ' + e.message; }
}
async function syncGitHub(){
  const btn=document.querySelector('[onclick="syncGitHub()"]');
  btn.textContent='Fetching...';
  try{
    const d=await fetch(BASE+'/api/github/repos').then(r=>r.json());
    if(d.error){alert('GitHub error: '+d.error);btn.textContent='↓ Pull from GitHub';return;}
    const ghRepos=d.repos||[];
    // Bulk register all repos
    let added=0;
    for(const r of ghRepos){
      const exists=allRepos.some(x=>x.owner===r.owner&&x.repo===r.repo);
      if(!exists){
        await fetch(BASE+'/api/repos',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({owner:r.owner,repo:r.repo})});
        added++;
      }
    }
    btn.textContent='↓ Pull from GitHub';
    await loadRepos();
    if(added>0)alert(`Registered ${added} new repos from GitHub.`);
    else alert('All repos already registered.');
  }catch(e){btn.textContent='↓ Pull from GitHub';alert('Error: '+e.message);}
}

async function addRepo(){
  const owner=document.getElementById('r-owner').value.trim();
  const repo=document.getElementById('r-repo').value.trim();
  if(!owner||!repo)return;
  await fetch(BASE+'/api/repos',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({owner,repo})});
  document.getElementById('r-owner').value='';document.getElementById('r-repo').value='';
  loadRepos();
}
async function delRepo(owner,repo){await fetch(BASE+`/api/repos/${owner}/${repo}`,{method:'DELETE'});loadRepos();}

// SKILLS / SOUL EDITOR
let allSkills=[];

async function loadSkillList(){
  try{
    const [skRes,soulRes]=await Promise.all([
      fetch(BASE+'/api/skills').then(r=>r.json()),
      fetch(BASE+'/api/soul').then(r=>r.json()),
    ]);
    allSkills=skRes.skills||[];
    const el=document.getElementById('skill-list');
    let html='<div class="skill-row" onclick="loadFile(\\'soul\\',\\'SOUL.md\\')" id="row-soul"><div class="sk-name">Soul.md</div><div class="sk-desc">Agent personality &amp; behavior</div></div>';
    html+=allSkills.map(s=>`<div class="skill-row" onclick="loadFile('skill','${s.name}')" id="row-${s.name}"><div class="sk-name">${s.name}</div><div class="sk-desc">${s.description||''}</div></div>`).join('');
    el.innerHTML=html;
  }catch(e){document.getElementById('skill-list').innerHTML='<div class="ev-empty">Error loading</div>';}
}

async function loadFile(type,name){
  document.querySelectorAll('.skill-row').forEach(r=>r.classList.remove('active'));
  const row=document.getElementById('row-'+name);
  if(row)row.classList.add('active');
  document.getElementById('editor-title').textContent=type==='soul'?'SOUL.MD':name.toUpperCase()+' — SKILL.MD';
  document.getElementById('save-btn').style.display='inline';
  curFile={type,name};
  try{
    const url=type==='soul'?'/api/soul':`/api/skills/${encodeURIComponent(name)}`;
    const d=await fetch(BASE+url).then(r=>r.json());
    document.getElementById('code-editor').value=d.content||'';
  }catch(e){document.getElementById('code-editor').value='// Error loading file';}
}

async function saveCurrentFile(){
  if(!curFile)return;
  const content=document.getElementById('code-editor').value;
  const url=curFile.type==='soul'?'/api/soul':`/api/skills/${encodeURIComponent(curFile.name)}`;
  const btn=document.getElementById('save-btn');
  btn.textContent='Saving...';
  try{
    await fetch(BASE+url,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({content})});
    btn.textContent='Saved ✓';
    setTimeout(()=>btn.textContent='Save ↗',1500);
  }catch(e){btn.textContent='Error';setTimeout(()=>btn.textContent='Save ↗',1500);}
}

// CHAT
function chatKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();}}
function appendMsg(role,text){
  const msgs=document.getElementById('chat-msgs');
  const d=document.createElement('div');d.className='msg '+role;
  const sender=role==='user'?'You':'Hermes Core';
  d.innerHTML=`<span class="msg-sender">${sender} &bull; ${ts()}</span><p class="msg-content">${text.replace(/\\n/g,'<br>')}</p>`;
  msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;
}
function showTyping(){const msgs=document.getElementById('chat-msgs');const d=document.createElement('div');d.className='msg agent';d.id='typ';d.innerHTML='<span class="msg-sender">Hermes Core</span><div class="typing-row"><div class="tdot"></div><div class="tdot"></div><div class="tdot"></div></div>';msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;}
function hideTyping(){const el=document.getElementById('typ');if(el)el.remove();}
async function sendMsg(){
  const inp=document.getElementById('chat-in');const text=inp.value.trim();if(!text)return;
  inp.value='';inp.style.height='auto';
  appendMsg('user',text);showTyping();
  try{
    const r=await fetch(BASE+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
    const d=await r.json();hideTyping();appendMsg('agent',d.response||'--');
  }catch(e){hideTyping();appendMsg('agent','Connection error.');}
}
document.getElementById('chat-in').addEventListener('input',function(){this.style.height='auto';this.style.height=Math.min(this.scrollHeight,100)+'px';});

// SSE
function connectSSE(){
  if(sse)sse.close();
  sse=new EventSource(BASE+'/api/events');
  sse.onopen=()=>document.getElementById('ev-status').textContent='Stream active';
  sse.onmessage=(e)=>{
    try{const data=JSON.parse(e.data);if(!Object.keys(data).length)return;
    evLog.unshift({ts:new Date().toLocaleTimeString(),msg:JSON.stringify(data).slice(0,200)});
    if(evLog.length>200)evLog.pop();renderEvents();}catch(err){}
  };
  sse.onerror=()=>document.getElementById('ev-status').textContent='Reconnecting...';
}
function renderEvents(){
  const el=document.getElementById('act-feed');
  el.innerHTML=evLog.length?evLog.map(e=>`<div class="ev-item"><span class="ev-ts">${e.ts}</span><span class="ev-msg">${e.msg}</span></div>`).join(''):'<div class="ev-empty">Waiting for events...</div>';
  document.getElementById('ev-status').textContent='Stream active -- '+evLog.length+' events';
}

async function init(){
  await loadStatus();
  await Promise.all([loadTasks(),loadRepos()]);
  connectSSE();
  setInterval(loadStatus,15000);
  setInterval(loadTasks,8000);
}
init();
</script>
</body>
</html>
"""

_DEFAULT_REPOS_FILE = Path.home() / ".hermes" / "watched_repos.json"
_DEFAULT_TASKS_FILE = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "tasks.json"
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
        self.tasks_file = _DEFAULT_TASKS_FILE
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
        """Read repos — DB first (persistent), then local JSON."""
        if db_repos_list and db_available and db_available():
            rows = db_repos_list()
            if rows is not None:
                return rows
        try:
            if self.repos_file.exists():
                return json.loads(self.repos_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _write_repos(self, repos: List[Dict]) -> None:
        """Write repos — DB primary, local JSON backup."""
        if db_repo_upsert and db_available and db_available():
            for r in repos:
                db_repo_upsert(r)
        try:
            self.repos_file.parent.mkdir(parents=True, exist_ok=True)
            self.repos_file.write_text(json.dumps(repos, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _read_tasks(self) -> List[Dict]:
        """Read tasks — DB first, fall back to local JSON file."""
        if db_tasks_list and db_available and db_available():
            return db_tasks_list()
        try:
            if self.tasks_file.exists():
                return json.loads(self.tasks_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _write_tasks(self, tasks: List[Dict]) -> None:
        """Write tasks — always write to both DB and local JSON."""
        if db_task_upsert and db_available and db_available():
            for t in tasks:
                db_task_upsert(t)
        # Also keep local copy as backup
        try:
            self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
            self.tasks_file.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
        except OSError:
            pass

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
        full_name = f"{owner}/{repo}"
        if db_repo_delete and db_available and db_available():
            db_repo_delete(full_name)
        repos = self._read_repos()
        new_repos = [r for r in repos if not (r.get("owner") == owner and r.get("repo") == repo)]
        self._write_repos(new_repos)
        return self._json({"deleted": full_name})

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



    async def _handle_github_sync(self, request: "web.Request") -> "web.Response":
        """Pull latest hermes-agent repo and restart. Called after a git push."""
        import subprocess, asyncio
        repo_dir = Path(__file__).parent.parent
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "-C", str(repo_dir), "pull", "--rebase", "--autostash"],
                    capture_output=True, text=True, timeout=30
                )
            )
            out = result.stdout + result.stderr
            return self._json({"ok": result.returncode == 0, "output": out.strip()})
        except Exception as exc:
            return self._error(str(exc), status=500)

    async def _handle_skill_import(self, request: "web.Request") -> "web.Response":
        """Import a skill from a GitHub URL, raw URL, or skills.sh slug.

        Body: { "source": "<url-or-slug>" }
        Examples:
          - "https://github.com/owner/repo/tree/main/skills/my-skill"
          - "https://raw.githubusercontent.com/.../SKILL.md"
          - "my-skill-name"  (looks up clawhub.com)
        """
        import urllib.request as _ureq
        try:
            body = await request.json()
        except Exception:
            return self._error("Invalid JSON")
        source = (body.get("source") or "").strip()
        if not source:
            return self._error("source is required")

        # Normalize to a raw SKILL.md URL
        raw_url = None
        skill_name = None

        if source.startswith("https://raw.githubusercontent.com"):
            raw_url = source
            skill_name = source.rstrip("/").split("/")[-2]
        elif source.startswith("https://github.com"):
            # Convert github.com tree URL → raw.githubusercontent.com
            raw_url = source.replace("https://github.com", "https://raw.githubusercontent.com")
            raw_url = raw_url.replace("/tree/", "/")
            if not raw_url.endswith("SKILL.md"):
                raw_url = raw_url.rstrip("/") + "/SKILL.md"
            skill_name = source.rstrip("/").split("/")[-1]
        else:
            # Treat as slug — try clawhub.com skills API
            skill_name = source
            raw_url = f"https://clawhub.com/api/skills/{source}/SKILL.md"

        # Fetch the SKILL.md
        try:
            req = _ureq.Request(raw_url, headers={"User-Agent": "hermes-agent"})
            token = os.environ.get("GITHUB_TOKEN", "")
            if token and "github" in raw_url:
                req.add_header("Authorization", f"token {token}")
            with _ureq.urlopen(req, timeout=10) as resp:
                skill_content = resp.read().decode("utf-8")
        except Exception as exc:
            return self._error(f"Could not fetch skill from {raw_url}: {exc}", status=502)

        if not skill_content.strip():
            return self._error("Fetched empty SKILL.md", status=502)

        # Write to HERMES_HOME/skills/<name>/SKILL.md
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        skill_dir = hermes_home / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        if db_skill_upsert and db_available and db_available():
            db_skill_upsert(skill_name, skill_content, source_url=raw_url)
        return self._json({"ok": True, "skill": skill_name, "path": str(skill_dir / "SKILL.md"),
                           "bytes": len(skill_content)})

    async def _handle_db_status(self, request: "web.Request") -> "web.Response":
        """Return DB connectivity + stats."""
        if not db_available or not db_available():
            return self._json({"connected": False, "reason": "DATABASE_URL not set or psycopg2 not installed"})
        from gateway.db import events_list as _el, tasks_list as _tl, skills_list as _sl
        try:
            task_count = len(_tl() or [])
            event_count = len(_el(limit=1000) or [])
            skill_count = len(_sl() or [])
            return self._json({
                "connected": True,
                "tables": {"tasks": task_count, "events": event_count, "skills": skill_count},
            })
        except Exception as exc:
            return self._json({"connected": True, "error": str(exc)})

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

        # Tasks / Kanban
        app.router.add_get("/api/tasks", self._handle_get_tasks)
        app.router.add_post("/api/tasks", self._handle_post_tasks)
        app.router.add_patch("/api/tasks/{id}", self._handle_patch_task)
        app.router.add_delete("/api/tasks/{id}", self._handle_delete_task)
        app.router.add_options("/api/tasks", self._handle_options)
        app.router.add_options("/api/tasks/{id}", self._handle_options)

        # Activity
        app.router.add_get("/api/activity", self._handle_activity)
        app.router.add_options("/api/activity", self._handle_options)

        # Soul.md editor
        app.router.add_get("/api/soul", self._handle_get_soul)
        app.router.add_put("/api/soul", self._handle_put_soul)
        app.router.add_options("/api/soul", self._handle_options)

        # Skill file editor
        app.router.add_get("/api/skills/{name}", self._handle_get_skill_file)
        app.router.add_put("/api/skills/{name}", self._handle_put_skill_file)
        app.router.add_options("/api/skills/{name}", self._handle_options)

        # GitHub repo discovery
        app.router.add_get("/api/github/repos", self._handle_github_repos)
        app.router.add_post("/api/github/sync", self._handle_github_sync)
        app.router.add_post("/api/skills/import", self._handle_skill_import)
        app.router.add_get("/api/db/status", self._handle_db_status)
        app.router.add_options("/api/github/repos", self._handle_options)

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





    async def _handle_activity(self, request: "web.Request") -> "web.Response":
        """Return recent event log for activity feed — DB first, in-memory fallback."""
        if db_events_list and db_available and db_available():
            events = db_events_list(limit=100)
        else:
            events = list(getattr(self, "_event_log", []))[-100:]
        return self._json({"events": events})


    def _soul_path(self) -> "Path":
        """Canonical writable path for SOUL.md — always HERMES_HOME."""
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        hermes_home.mkdir(parents=True, exist_ok=True)
        return hermes_home / "SOUL.md"

    def _github_soul_path(self):
        """Return (owner, repo, branch, path) for SOUL.md in GitHub, or None."""
        token = os.environ.get("GITHUB_TOKEN", "")
        repo = os.environ.get("HERMES_GITHUB_REPO", "")  # e.g. "0xMikey-ooze/hermes-agent"
        if not token or not repo:
            return None
        branch = os.environ.get("HERMES_GITHUB_BRANCH", "main")
        return token, repo, branch, "SOUL.md"

    def _github_get_file(self, token, repo, path, branch="main"):
        """Fetch a file from GitHub. Returns (content_str, sha) or (None, None)."""
        import urllib.request, base64
        url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        })
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
                return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]
        except Exception:
            return None, None

    def _github_put_file(self, token, repo, path, content, sha, branch="main", message=None):
        """Commit a file to GitHub. Returns True on success."""
        import urllib.request, base64
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        body = {
            "message": message or f"chore: update {path} via dashboard",
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="PUT", headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status in (200, 201)
        except Exception:
            return False

    async def _handle_get_soul(self, request: "web.Request") -> "web.Response":
        """Return SOUL.md — try GitHub first (persistent), then HERMES_HOME, then /app."""
        gh = self._github_soul_path()
        if gh:
            token, repo, branch, path = gh
            gh_content, sha = self._github_get_file(token, repo, path, branch)
            if gh_content is not None:
                # Cache locally so it survives a GitHub hiccup
                self._soul_path().write_text(gh_content, encoding="utf-8")
                return self._json({"path": f"github:{repo}/{path}", "content": gh_content, "sha": sha})
        # Fall through to local
        target = self._soul_path()
        if target.exists():
            return self._json({"path": str(target), "content": target.read_text(encoding="utf-8")})
        fallback = Path(__file__).parent.parent / "SOUL.md"
        if fallback.exists():
            return self._json({"path": str(target), "content": fallback.read_text(encoding="utf-8")})
        return self._json({"path": str(target), "content": ""})

    async def _handle_put_soul(self, request: "web.Request") -> "web.Response":
        """Write SOUL.md — save locally AND commit to GitHub for persistence."""
        try:
            body = await request.json()
        except Exception:
            return self._error("Invalid JSON")
        content_text = body.get("content", "")
        sha = body.get("sha")  # sha from last GET — required for GitHub update
        # Always write locally first (fast path)
        target = self._soul_path()
        try:
            target.write_text(content_text, encoding="utf-8")
        except OSError as exc:
            return self._error(f"Local write failed: {exc}", status=500)
        # Commit to GitHub for true persistence
        gh = self._github_soul_path()
        if gh:
            token, repo, branch, path = gh
            if not sha:
                _, sha = self._github_get_file(token, repo, path, branch)
            ok = self._github_put_file(token, repo, path, content_text, sha, branch,
                                       message="chore: update SOUL.md via dashboard")
            return self._json({"saved": f"github:{repo}/{path}", "ok": True, "github": ok})
        return self._json({"saved": str(target), "ok": True, "github": False,
                           "note": "Set HERMES_GITHUB_REPO env var to persist across deploys"})

    def _skill_overlay_path(self, name: str) -> "Path":
        """Writable overlay path for skill files in HERMES_HOME."""
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        p = hermes_home / "skills" / name
        p.mkdir(parents=True, exist_ok=True)
        return p / "SKILL.md"

    async def _handle_get_skill_file(self, request: "web.Request") -> "web.Response":
        """Return SKILL.md — DB first (persistent), then local overlay, then image."""
        name = request.match_info["name"]
        # Try DB first (survives redeployments)
        if db_available and db_available():
            try:
                from gateway.db import _exec as _db_exec
                rows = _db_exec("SELECT content FROM skills WHERE name=$1", (name,))
                if rows and rows[0].get("content"):
                    return self._json({"name": name, "content": rows[0]["content"], "source": "db"})
            except Exception:
                pass
        # Local overlay
        overlay = self._skill_overlay_path(name)
        if overlay.exists():
            return self._json({"name": name, "content": overlay.read_text(encoding="utf-8"), "source": "local"})
        # Fallback to image copy
        skill_md = self.skills_path / name / "SKILL.md"
        if not skill_md.exists():
            return self._error(f"Skill '{name}' not found", status=404)
        return self._json({"name": name, "content": skill_md.read_text(encoding="utf-8"), "source": "image"})

    async def _handle_put_skill_file(self, request: "web.Request") -> "web.Response":
        """Write SKILL.md to HERMES_HOME overlay AND Neon DB for persistence."""
        name = request.match_info["name"]
        try:
            body = await request.json()
        except Exception:
            return self._error("Invalid JSON")
        content_text = body.get("content", "")
        target = self._skill_overlay_path(name)
        saved_local = False
        try:
            target.write_text(content_text, encoding="utf-8")
            saved_local = True
        except OSError:
            pass
        # Persist to DB so it survives redeployments
        db_ok = False
        if db_skill_upsert and db_available and db_available():
            db_ok = db_skill_upsert(name, content_text)
        if not saved_local and not db_ok:
            return self._error("Write failed: filesystem read-only and DB unavailable", status=500)
        return self._json({"saved": str(target), "ok": True, "db": db_ok})

    async def _handle_github_repos(self, request: "web.Request") -> "web.Response":
        """Fetch all repos accessible via GITHUB_TOKEN."""
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            return self._json({"repos": [], "error": "GITHUB_TOKEN not set"})
        try:
            import urllib.request as _urllib
            import ssl as _ssl
            ctx = _ssl.create_default_context()
            all_repos = []
            page = 1
            while True:
                url = f"https://api.github.com/user/repos?per_page=100&page={page}&sort=updated&affiliation=owner"
                req = _urllib.Request(url, headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "hermes-agent",
                })
                with _urllib.urlopen(req, context=ctx, timeout=10) as r:
                    data = __import__("json").loads(r.read())
                if not data:
                    break
                all_repos.extend([{
                    "owner": repo["owner"]["login"],
                    "repo": repo["name"],
                    "full_name": repo["full_name"],
                    "private": repo["private"],
                    "updated_at": repo.get("updated_at", ""),
                    "description": repo.get("description") or "",
                } for repo in data])
                if len(data) < 100:
                    break
                page += 1
            return self._json({"repos": all_repos})
        except Exception as exc:
            return self._error(f"GitHub API error: {exc}")

    async def _handle_get_tasks(self, request: "web.Request") -> "web.Response":
        return self._json({"tasks": self._read_tasks()})

    async def _handle_post_tasks(self, request: "web.Request") -> "web.Response":
        import uuid as _uuid
        try:
            body = await request.json()
        except Exception:
            return self._error("Invalid JSON body")

        repo = body.get("repo", "").strip()
        title = body.get("title", "").strip()
        description = body.get("description", "").strip()
        priority = body.get("priority", "normal")
        if not repo or not title:
            return self._error("Missing required fields: repo, title")

        task = {
            "id": _uuid.uuid4().hex[:10],
            "repo": repo,
            "title": title,
            "description": description,
            "priority": priority,
            "status": "in_progress",
            "created_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        tasks = self._read_tasks()
        tasks.append(task)
        self._write_tasks(tasks)
        if db_event_log and db_available and db_available():
            db_event_log("task_created", payload={"id": task.get("id"), "title": title, "repo": repo})

        # Auto-dispatch to agent
        try:
            from gateway import run as _run
            from gateway.session import SessionSource
            from gateway.config import Platform
            from gateway.platforms.base import MessageEvent

            runner = getattr(_run, "_active_runner", None)
            if runner is not None:
                desc_part = f"\n\nDescription: {description}" if description and description != title else ""
                repo_part = f"\n\nRepo: {repo}" if repo else ""
                prompt = (
                    f"TASK ASSIGNED [#{task['id']}]: {title}"
                    f"{repo_part}{desc_part}\n\n"
                    f"Instructions:\n"
                    f"1. Call update_task_status('{task['id']}', 'in_progress') immediately\n"
                    f"2. Execute the task using available tools (query_db, exec, web tools, etc.)\n"
                    f"3. Call update_task_status('{task['id']}', 'done') when complete\n"
                    f"4. Send a Telegram message to chat_id={MIKEY_TG} summarizing what you did\n"
                    f"5. Call write_reflection() with what you learned\n"
                    f"If blocked, call update_task_status('{task['id']}', 'blocked') and notify Mikey."
                )
                source = SessionSource(
                    platform=Platform.LOCAL,
                    chat_id="dashboard",
                    user_id="dashboard",
                    user_name="Dashboard",
                    chat_type="dm",
                )
                event = MessageEvent(text=prompt, source=source)
                __import__("asyncio").create_task(runner._handle_message(event))
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning("Task dispatch error: %s", exc)

        return self._json({"task": task}, status=201)

    async def _handle_patch_task(self, request: "web.Request") -> "web.Response":
        task_id = request.match_info["id"]
        try:
            body = await request.json()
        except Exception:
            return self._error("Invalid JSON body")

        tasks = self._read_tasks()
        for t in tasks:
            if t.get("id") == task_id:
                if "status" in body:
                    t["status"] = body["status"]
                self._write_tasks(tasks)
                return self._json({"task": t})
        return self._error(f"Task {task_id} not found", status=404)

    async def _handle_delete_task(self, request: "web.Request") -> "web.Response":
        task_id = request.match_info["id"]
        tasks = self._read_tasks()
        new_tasks = [t for t in tasks if t.get("id") != task_id]
        if len(new_tasks) == len(tasks):
            return self._error(f"Task {task_id} not found", status=404)
        self._write_tasks(new_tasks)
        return self._json({"deleted": task_id})

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
                platform=Platform.LOCAL,
                chat_id="dashboard",
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




    async def _handle_activity(self, request: "web.Request") -> "web.Response":
        """Return recent event log for activity feed — DB first, in-memory fallback."""
        if db_events_list and db_available and db_available():
            events = db_events_list(limit=100)
        else:
            events = list(getattr(self, "_event_log", []))[-100:]
        return self._json({"events": events})


    def _soul_path(self) -> "Path":
        """Canonical writable path for SOUL.md — always HERMES_HOME."""
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        hermes_home.mkdir(parents=True, exist_ok=True)
        return hermes_home / "SOUL.md"

    def _github_soul_path(self):
        """Return (owner, repo, branch, path) for SOUL.md in GitHub, or None."""
        token = os.environ.get("GITHUB_TOKEN", "")
        repo = os.environ.get("HERMES_GITHUB_REPO", "")  # e.g. "0xMikey-ooze/hermes-agent"
        if not token or not repo:
            return None
        branch = os.environ.get("HERMES_GITHUB_BRANCH", "main")
        return token, repo, branch, "SOUL.md"

    def _github_get_file(self, token, repo, path, branch="main"):
        """Fetch a file from GitHub. Returns (content_str, sha) or (None, None)."""
        import urllib.request, base64
        url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        })
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
                return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]
        except Exception:
            return None, None

    def _github_put_file(self, token, repo, path, content, sha, branch="main", message=None):
        """Commit a file to GitHub. Returns True on success."""
        import urllib.request, base64
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        body = {
            "message": message or f"chore: update {path} via dashboard",
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="PUT", headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status in (200, 201)
        except Exception:
            return False

    async def _handle_get_soul(self, request: "web.Request") -> "web.Response":
        """Return SOUL.md — try GitHub first (persistent), then HERMES_HOME, then /app."""
        gh = self._github_soul_path()
        if gh:
            token, repo, branch, path = gh
            gh_content, sha = self._github_get_file(token, repo, path, branch)
            if gh_content is not None:
                # Cache locally so it survives a GitHub hiccup
                self._soul_path().write_text(gh_content, encoding="utf-8")
                return self._json({"path": f"github:{repo}/{path}", "content": gh_content, "sha": sha})
        # Fall through to local
        target = self._soul_path()
        if target.exists():
            return self._json({"path": str(target), "content": target.read_text(encoding="utf-8")})
        fallback = Path(__file__).parent.parent / "SOUL.md"
        if fallback.exists():
            return self._json({"path": str(target), "content": fallback.read_text(encoding="utf-8")})
        return self._json({"path": str(target), "content": ""})

    async def _handle_put_soul(self, request: "web.Request") -> "web.Response":
        """Write SOUL.md — save locally AND commit to GitHub for persistence."""
        try:
            body = await request.json()
        except Exception:
            return self._error("Invalid JSON")
        content_text = body.get("content", "")
        sha = body.get("sha")  # sha from last GET — required for GitHub update
        # Always write locally first (fast path)
        target = self._soul_path()
        try:
            target.write_text(content_text, encoding="utf-8")
        except OSError as exc:
            return self._error(f"Local write failed: {exc}", status=500)
        # Commit to GitHub for true persistence
        gh = self._github_soul_path()
        if gh:
            token, repo, branch, path = gh
            if not sha:
                _, sha = self._github_get_file(token, repo, path, branch)
            ok = self._github_put_file(token, repo, path, content_text, sha, branch,
                                       message="chore: update SOUL.md via dashboard")
            return self._json({"saved": f"github:{repo}/{path}", "ok": True, "github": ok})
        return self._json({"saved": str(target), "ok": True, "github": False,
                           "note": "Set HERMES_GITHUB_REPO env var to persist across deploys"})

    def _skill_overlay_path(self, name: str) -> "Path":
        """Writable overlay path for skill files in HERMES_HOME."""
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        p = hermes_home / "skills" / name
        p.mkdir(parents=True, exist_ok=True)
        return p / "SKILL.md"

    async def _handle_get_skill_file(self, request: "web.Request") -> "web.Response":
        """Return SKILL.md — DB first (persistent), then local overlay, then image."""
        name = request.match_info["name"]
        # Try DB first (survives redeployments)
        if db_available and db_available():
            try:
                from gateway.db import _exec as _db_exec
                rows = _db_exec("SELECT content FROM skills WHERE name=$1", (name,))
                if rows and rows[0].get("content"):
                    return self._json({"name": name, "content": rows[0]["content"], "source": "db"})
            except Exception:
                pass
        # Local overlay
        overlay = self._skill_overlay_path(name)
        if overlay.exists():
            return self._json({"name": name, "content": overlay.read_text(encoding="utf-8"), "source": "local"})
        # Fallback to image copy
        skill_md = self.skills_path / name / "SKILL.md"
        if not skill_md.exists():
            return self._error(f"Skill '{name}' not found", status=404)
        return self._json({"name": name, "content": skill_md.read_text(encoding="utf-8"), "source": "image"})

    async def _handle_put_skill_file(self, request: "web.Request") -> "web.Response":
        """Write SKILL.md to HERMES_HOME overlay AND Neon DB for persistence."""
        name = request.match_info["name"]
        try:
            body = await request.json()
        except Exception:
            return self._error("Invalid JSON")
        content_text = body.get("content", "")
        target = self._skill_overlay_path(name)
        saved_local = False
        try:
            target.write_text(content_text, encoding="utf-8")
            saved_local = True
        except OSError:
            pass
        # Persist to DB so it survives redeployments
        db_ok = False
        if db_skill_upsert and db_available and db_available():
            db_ok = db_skill_upsert(name, content_text)
        if not saved_local and not db_ok:
            return self._error("Write failed: filesystem read-only and DB unavailable", status=500)
        return self._json({"saved": str(target), "ok": True, "db": db_ok})

    async def _handle_github_repos(self, request: "web.Request") -> "web.Response":
        """Fetch all repos accessible via GITHUB_TOKEN."""
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            return self._json({"repos": [], "error": "GITHUB_TOKEN not set"})
        try:
            import urllib.request as _urllib
            import ssl as _ssl
            ctx = _ssl.create_default_context()
            all_repos = []
            page = 1
            while True:
                url = f"https://api.github.com/user/repos?per_page=100&page={page}&sort=updated&affiliation=owner"
                req = _urllib.Request(url, headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "hermes-agent",
                })
                with _urllib.urlopen(req, context=ctx, timeout=10) as r:
                    data = __import__("json").loads(r.read())
                if not data:
                    break
                all_repos.extend([{
                    "owner": repo["owner"]["login"],
                    "repo": repo["name"],
                    "full_name": repo["full_name"],
                    "private": repo["private"],
                    "updated_at": repo.get("updated_at", ""),
                    "description": repo.get("description") or "",
                } for repo in data])
                if len(data) < 100:
                    break
                page += 1
            return self._json({"repos": all_repos})
        except Exception as exc:
            return self._error(f"GitHub API error: {exc}")

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
                platform=Platform.LOCAL,
                chat_id="dashboard",
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
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
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
