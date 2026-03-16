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
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Hermes</title>
<style>
:root{--bg:#0d0f14;--surface:#161a23;--border:#252b38;--accent:#6c63ff;--accent2:#00d2ff;--green:#22d3a0;--red:#ff4d6d;--yellow:#fbbf24;--text:#e2e8f0;--muted:#64748b;--card:#1a1f2e}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;height:100vh;overflow:hidden}
.shell{display:grid;grid-template-columns:200px 1fr;height:100vh}
.sidebar{background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column}
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
.main{overflow:hidden;display:flex;flex-direction:column;height:100vh}
.page{display:none;flex:1;overflow:hidden;flex-direction:column}
.page.active{display:flex}
.page-inner{flex:1;overflow-y:auto;padding:24px}
/* KPI */
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px}
.kpi .lbl{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px}
.kpi .val{font-size:24px;font-weight:700}
.kpi .sub{font-size:11px;color:var(--muted);margin-top:4px}
.kpi.g .val{color:var(--green)}.kpi.a .val{color:var(--accent)}.kpi.b .val{color:var(--accent2)}.kpi.y .val{color:var(--yellow)}
/* Card */
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;margin-bottom:14px;overflow:hidden}
.card-head{display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-bottom:1px solid var(--border)}
.card-head h2{font-size:13px;font-weight:600}
.card-body{padding:16px}
/* Badge */
.badge{display:inline-block;padding:2px 7px;border-radius:99px;font-size:10px;font-weight:600}
.badge.g{background:rgba(34,211,160,.15);color:var(--green)}
.badge.a{background:rgba(108,99,255,.15);color:var(--accent)}
.badge.y{background:rgba(251,191,36,.15);color:var(--yellow)}
.badge.r{background:rgba(255,77,109,.15);color:var(--red)}
.badge.b{background:rgba(0,210,255,.15);color:var(--accent2)}
/* KANBAN */
#page-kanban .page-inner{display:flex;flex-direction:column}
.kanban-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;flex-shrink:0}
.kanban-header h1{font-size:18px;font-weight:700}
.add-task-btn{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer;transition:opacity .15s}
.add-task-btn:hover{opacity:.85}
.kanban-board{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;flex:1;overflow:hidden}
.kanban-col{background:var(--surface);border:1px solid var(--border);border-radius:10px;display:flex;flex-direction:column;overflow:hidden}
.col-head{padding:13px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-shrink:0}
.col-head h3{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.col-count{font-size:11px;color:var(--muted);margin-left:auto}
.col-stripe{width:3px;height:14px;border-radius:2px;flex-shrink:0}
.col-body{flex:1;overflow-y:auto;padding:10px;display:flex;flex-direction:column;gap:8px}
/* Task card */
.task-card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px;cursor:pointer;transition:border-color .12s,transform .1s}
.task-card:hover{border-color:var(--accent);transform:translateY(-1px)}
.task-card .t-repo{font-size:10px;color:var(--muted);margin-bottom:5px;display:flex;align-items:center;gap:4px}
.task-card .t-title{font-size:13px;font-weight:600;line-height:1.4;margin-bottom:6px}
.task-card .t-desc{font-size:11px;color:var(--muted);line-height:1.5;margin-bottom:8px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.task-card .t-footer{display:flex;align-items:center;justify-content:space-between}
.task-card .t-time{font-size:10px;color:var(--muted)}
.task-actions{display:flex;gap:5px;margin-top:8px}
.t-btn{border:none;border-radius:5px;padding:3px 8px;font-size:10px;font-weight:600;cursor:pointer;transition:opacity .12s}
.t-btn:hover{opacity:.8}
.t-btn.move{background:rgba(108,99,255,.2);color:var(--accent)}
.t-btn.done{background:rgba(34,211,160,.2);color:var(--green)}
.t-btn.del{background:rgba(255,77,109,.15);color:var(--red)}
.col-empty{text-align:center;padding:32px 12px;color:var(--muted);font-size:12px}
/* Modal */
.modal-bg{position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:100;display:flex;align-items:center;justify-content:center;display:none}
.modal-bg.open{display:flex}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:24px;width:480px;max-width:95vw}
.modal h2{font-size:16px;font-weight:700;margin-bottom:18px}
.field{margin-bottom:14px}
.field label{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px;font-weight:500}
.field input,.field textarea,.field select{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;transition:border .15s;font-family:inherit}
.field input:focus,.field textarea:focus,.field select:focus{border-color:var(--accent)}
.field textarea{resize:vertical;min-height:72px}
.field select option{background:var(--bg)}
.modal-btns{display:flex;gap:10px;justify-content:flex-end;margin-top:20px}
.modal-btns button{border:none;border-radius:8px;padding:9px 18px;font-size:13px;font-weight:600;cursor:pointer}
.btn-cancel{background:var(--border);color:var(--muted)}
.btn-submit{background:var(--accent);color:#fff}
.btn-submit:hover{opacity:.85}
/* Chat */
#page-chat{height:100vh}
.chat-wrap{display:flex;flex-direction:column;height:100%}
.chat-msgs{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:12px}
.msg-row.user{align-items:flex-end;display:flex;flex-direction:column}
.msg-row.agent{align-items:flex-start;display:flex;flex-direction:column}
.msg-bubble{padding:10px 14px;border-radius:18px;max-width:72%;line-height:1.5;font-size:14px;word-break:break-word}
.msg-row.user .msg-bubble{background:var(--accent);color:#fff;border-radius:18px 18px 4px 18px}
.msg-row.agent .msg-bubble{background:var(--card);border:1px solid var(--border);border-radius:18px 18px 18px 4px}
.msg-meta{font-size:10px;color:var(--muted);margin-top:3px;padding:0 4px}
.typing{display:flex;gap:4px;padding:10px 14px;background:var(--card);border:1px solid var(--border);border-radius:18px 18px 18px 4px}
.typing span{width:6px;height:6px;border-radius:50%;background:var(--muted);animation:bounce .9s infinite}
.typing span:nth-child(2){animation-delay:.15s}.typing span:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-6px)}}
.chat-input-row{padding:14px 16px;border-top:1px solid var(--border);display:flex;gap:10px;background:var(--surface);flex-shrink:0}
.chat-input{flex:1;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:22px;padding:10px 16px;font-size:14px;outline:none;resize:none;transition:border .15s;font-family:inherit;max-height:100px}
.chat-input:focus{border-color:var(--accent)}
.send-btn{background:var(--accent);color:#fff;border:none;border-radius:50%;width:40px;height:40px;font-size:17px;cursor:pointer;flex-shrink:0;transition:opacity .15s}
.send-btn:hover{opacity:.85}.send-btn:disabled{opacity:.4;cursor:not-allowed}
/* Repos */
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;padding-bottom:10px;font-weight:500}
td{padding:9px 0;border-top:1px solid var(--border);vertical-align:middle}
tr:first-child td{border-top:none}
.add-row{display:flex;gap:8px;margin-top:14px}
.add-row input{flex:1;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:8px 11px;font-size:13px;outline:none}
.add-row input:focus{border-color:var(--accent)}
.add-row button{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:8px 13px;font-size:13px;font-weight:600;cursor:pointer}
.del-btn{background:none;border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:3px 9px;font-size:11px;cursor:pointer;transition:all .12s}
.del-btn:hover{border-color:var(--red);color:var(--red)}
/* Ev feed */
.ev-feed{max-height:220px;overflow-y:auto;font-size:11px;font-family:'JetBrains Mono',monospace}
.ev-line{padding:5px 0;border-bottom:1px solid rgba(255,255,255,.04);display:flex;gap:8px}
.ev-ts{color:var(--accent);flex-shrink:0}.ev-msg{color:var(--muted)}
.empty{color:var(--muted);text-align:center;padding:28px 0;font-size:13px}
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
    <a data-page="kanban" onclick="nav(this,event)"><span>📋</span>Tasks</a>
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
        <div class="kpi g"><div class="lbl">Gateway</div><div class="val" id="kpi-gw">—</div></div>
        <div class="kpi a"><div class="lbl">Uptime</div><div class="val" id="kpi-up">—</div></div>
        <div class="kpi b"><div class="lbl">Skills</div><div class="val" id="kpi-sk">—</div></div>
        <div class="kpi y"><div class="lbl">Tasks Active</div><div class="val" id="kpi-tk">—</div></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Active Tasks</h2><a href="#" onclick="goKanban()" style="font-size:12px;color:var(--accent);text-decoration:none">View all →</a></div>
        <div class="card-body" id="ov-tasks"><div class="empty">No active tasks</div></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Recent Activity</h2><span style="font-size:11px;color:var(--muted)" id="ev-count">live</span></div>
        <div class="card-body"><div class="ev-feed" id="ev-mini"></div></div>
      </div>
    </div>
  </div>

  <!-- KANBAN -->
  <div class="page" id="page-kanban">
    <div class="page-inner">
      <div class="kanban-header">
        <h1>Task Board</h1>
        <button class="add-task-btn" onclick="openModal()">+ New Task</button>
      </div>
      <div class="kanban-board">
        <div class="kanban-col">
          <div class="col-head"><div class="col-stripe" style="background:var(--muted)"></div><h3>Backlog</h3><span class="col-count" id="cnt-backlog">0</span></div>
          <div class="col-body" id="col-backlog"></div>
        </div>
        <div class="kanban-col">
          <div class="col-head"><div class="col-stripe" style="background:var(--yellow)"></div><h3>In Progress</h3><span class="col-count" id="cnt-inprog">0</span></div>
          <div class="col-body" id="col-inprog"></div>
        </div>
        <div class="kanban-col">
          <div class="col-head"><div class="col-stripe" style="background:var(--green)"></div><h3>Done</h3><span class="col-count" id="cnt-done">0</span></div>
          <div class="col-body" id="col-done"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- CHAT -->
  <div class="page" id="page-chat">
    <div class="chat-wrap">
      <div class="chat-msgs" id="chat-msgs">
        <div class="msg-row agent"><div class="msg-bubble">👋 Hey! I'm Hermes. Ask me anything or assign me a task.</div></div>
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
        <div class="card-head"><h2>Watched Repos</h2><button onclick="loadRepos()" style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:12px">↻</button></div>
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
        <div class="kpi b"><div class="lbl">Model</div><div class="val" id="act-model" style="font-size:13px;margin-top:6px">—</div></div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Live Event Stream</h2><span class="badge g" id="sse-badge">connecting</span></div>
        <div class="card-body"><div class="ev-feed" style="max-height:460px" id="act-feed"></div></div>
      </div>
    </div>
  </div>

</main>
</div>

<!-- NEW TASK MODAL -->
<div class="modal-bg" id="modal">
  <div class="modal">
    <h2>✦ New Task</h2>
    <div class="field">
      <label>Repo</label>
      <select id="m-repo"><option value="">Select a repo...</option></select>
    </div>
    <div class="field">
      <label>Task Title</label>
      <input id="m-title" placeholder="e.g. Fix Railway deployment bug" />
    </div>
    <div class="field">
      <label>Description (what exactly to do)</label>
      <textarea id="m-desc" placeholder="Describe the task in detail. The agent will read this and work autonomously."></textarea>
    </div>
    <div class="field">
      <label>Priority</label>
      <select id="m-priority">
        <option value="low">Low</option>
        <option value="normal" selected>Normal</option>
        <option value="high">High</option>
        <option value="urgent">Urgent 🔥</option>
      </select>
    </div>
    <div class="modal-btns">
      <button class="btn-cancel" onclick="closeModal()">Cancel</button>
      <button class="btn-submit" onclick="submitTask()">Assign to Agent ↗</button>
    </div>
  </div>
</div>

<script>
const BASE='';
let evLog=[];
let sse=null;
let allTasks=[];
let allRepos=[];

function nav(el,e){
  if(e)e.preventDefault();
  document.querySelectorAll('nav a').forEach(a=>a.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  const pg=el.dataset.page;
  document.getElementById('page-'+pg).classList.add('active');
  if(pg==='repos')loadRepos();
  if(pg==='kanban')loadTasks();
}

function goKanban(){
  const a=document.querySelector('[data-page="kanban"]');
  nav(a,null);
}

function fmt(s){if(s<60)return s.toFixed(0)+'s';if(s<3600)return(s/60).toFixed(0)+'m';if(s<86400)return(s/3600).toFixed(1)+'h';return(s/86400).toFixed(1)+'d';}

function timeAgo(iso){
  const d=new Date(iso+'Z');const s=Math.floor((Date.now()-d)/1000);
  if(s<60)return s+'s ago';if(s<3600)return Math.floor(s/60)+'m ago';
  if(s<86400)return Math.floor(s/3600)+'h ago';return Math.floor(s/86400)+'d ago';
}

function priorityBadge(p){
  const map={low:'<span class="badge b">low</span>',normal:'<span class="badge a">normal</span>',high:'<span class="badge y">high</span>',urgent:'<span class="badge r">🔥 urgent</span>'};
  return map[p]||'<span class="badge a">'+p+'</span>';
}

// Status
async function loadStatus(){
  try{
    const d=await fetch(BASE+'/api/status').then(r=>r.json());
    const up=fmt(d.uptime_seconds);
    document.getElementById('kpi-gw').textContent=d.gateway_running?'● ON':'○ OFF';
    document.getElementById('kpi-up').textContent=up;
    document.getElementById('foot-model').textContent='model: '+(d.model||'—');
    document.getElementById('foot-platform').textContent='platform: '+(d.platform||'—');
    document.getElementById('foot-uptime').textContent='uptime: '+up;
    document.getElementById('act-gw').textContent=d.gateway_running?'Online':'Offline';
    document.getElementById('act-up').textContent=up;
    document.getElementById('act-model').textContent=d.model||'—';
    document.getElementById('dot').style.background='var(--green)';
    document.getElementById('status-txt').textContent='online';
  }catch(e){
    document.getElementById('dot').style.background='var(--red)';
    document.getElementById('status-txt').textContent='offline';
  }
}

// Skills
async function loadSkills(){
  try{const d=await fetch(BASE+'/api/skills').then(r=>r.json());document.getElementById('kpi-sk').textContent=(d.skills||[]).length;}catch(e){}
}

// Tasks / Kanban
async function loadTasks(){
  try{
    const d=await fetch(BASE+'/api/tasks').then(r=>r.json());
    allTasks=d.tasks||[];
    renderKanban();
    renderOvTasks();
    const active=allTasks.filter(t=>t.status==='in_progress').length;
    document.getElementById('kpi-tk').textContent=active;
  }catch(e){}
}

function renderKanban(){
  const cols={backlog:[],in_progress:[],done:[]};
  allTasks.forEach(t=>{const k=t.status||'backlog';if(cols[k])cols[k].push(t);else cols.backlog.push(t);});
  document.getElementById('cnt-backlog').textContent=cols.backlog.length;
  document.getElementById('cnt-inprog').textContent=cols.in_progress.length;
  document.getElementById('cnt-done').textContent=cols.done.length;
  renderCol('col-backlog',cols.backlog,'backlog');
  renderCol('col-inprog',cols.in_progress,'in_progress');
  renderCol('col-done',cols.done,'done');
}

function renderCol(elId,tasks,col){
  const el=document.getElementById(elId);
  if(!tasks.length){el.innerHTML='<div class="col-empty">Drop tasks here</div>';return;}
  el.innerHTML=tasks.map(t=>`
    <div class="task-card" id="tc-${t.id}">
      <div class="t-repo">⎇ ${t.repo}</div>
      <div class="t-title">${t.title}</div>
      ${t.description?`<div class="t-desc">${t.description}</div>`:''}
      <div class="t-footer">${priorityBadge(t.priority)}<span class="t-time">${timeAgo(t.created_at)}</span></div>
      <div class="task-actions">
        ${col==='backlog'?`<button class="t-btn move" onclick="moveTask('${t.id}','in_progress')">▶ Start</button>`:''}
        ${col==='in_progress'?`<button class="t-btn done" onclick="moveTask('${t.id}','done')">✓ Done</button>`:''}
        ${col==='done'?`<button class="t-btn move" onclick="moveTask('${t.id}','backlog')">↩ Reopen</button>`:''}
        <button class="t-btn del" onclick="deleteTask('${t.id}')">✕</button>
      </div>
    </div>`).join('');
}

function renderOvTasks(){
  const active=allTasks.filter(t=>t.status==='in_progress');
  const el=document.getElementById('ov-tasks');
  if(!active.length){el.innerHTML='<div class="empty">No tasks in progress</div>';return;}
  el.innerHTML='<div style="display:flex;flex-direction:column;gap:8px">'+
    active.map(t=>`<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
      <div><div style="font-size:12px;color:var(--muted)">⎇ ${t.repo}</div><div style="font-size:13px;font-weight:600;margin-top:2px">${t.title}</div></div>
      <span class="badge y">in progress</span>
    </div>`).join('')+'</div>';
}

async function moveTask(id,status){
  try{
    await fetch(BASE+`/api/tasks/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});
    await loadTasks();
  }catch(e){}
}

async function deleteTask(id){
  try{await fetch(BASE+`/api/tasks/${id}`,{method:'DELETE'});await loadTasks();}catch(e){}
}

// Modal
async function openModal(){
  // Populate repo dropdown
  const sel=document.getElementById('m-repo');
  sel.innerHTML='<option value="">Select a repo...</option>';
  try{
    const d=await fetch(BASE+'/api/repos').then(r=>r.json());
    allRepos=d.repos||[];
    allRepos.forEach(r=>{
      const o=document.createElement('option');
      o.value=r.owner+'/'+r.repo;
      o.textContent=r.owner+'/'+r.repo;
      sel.appendChild(o);
    });
  }catch(e){}
  document.getElementById('modal').classList.add('open');
  document.getElementById('m-title').focus();
}

function closeModal(){
  document.getElementById('modal').classList.remove('open');
  document.getElementById('m-title').value='';
  document.getElementById('m-desc').value='';
  document.getElementById('m-priority').value='normal';
}

async function submitTask(){
  const repo=document.getElementById('m-repo').value.trim();
  const title=document.getElementById('m-title').value.trim();
  const description=document.getElementById('m-desc').value.trim();
  const priority=document.getElementById('m-priority').value;
  if(!repo||!title){alert('Repo and title are required');return;}
  const btn=document.querySelector('.btn-submit');
  btn.textContent='Dispatching...';btn.disabled=true;
  try{
    await fetch(BASE+'/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({repo,title,description,priority})});
    closeModal();
    await loadTasks();
    // Switch to kanban view
    goKanban();
  }catch(e){alert('Failed to create task');}
  btn.textContent='Assign to Agent ↗';btn.disabled=false;
}

// Close modal on bg click
document.getElementById('modal').addEventListener('click',function(e){if(e.target===this)closeModal();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});

// Repos
async function loadRepos(){
  document.getElementById('repos-list').innerHTML='<div class="empty">Loading...</div>';
  try{
    const d=await fetch(BASE+'/api/repos').then(r=>r.json());
    const repos=d.repos||[];
    if(!repos.length){document.getElementById('repos-list').innerHTML='<div class="empty">No repos configured</div>';return;}
    document.getElementById('repos-list').innerHTML='<table><thead><tr><th>Repository</th><th></th></tr></thead><tbody>'+
      repos.map(r=>`<tr><td><a href="https://github.com/${r.owner}/${r.repo}" target="_blank" style="color:var(--accent2);text-decoration:none">⎇ ${r.owner}/<strong>${r.repo}</strong></a></td>
        <td style="text-align:right"><button class="del-btn" onclick="delRepo('${r.owner}','${r.repo}')">remove</button></td></tr>`).join('')+'</tbody></table>';
  }catch(e){document.getElementById('repos-list').innerHTML='<div class="empty">Failed to load</div>';}
}
async function addRepo(){
  const owner=document.getElementById('r-owner').value.trim();
  const repo=document.getElementById('r-repo').value.trim();
  if(!owner||!repo)return;
  await fetch(BASE+'/api/repos',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({owner,repo})});
  document.getElementById('r-owner').value='';document.getElementById('r-repo').value='';
  loadRepos();
}
async function delRepo(owner,repo){
  await fetch(BASE+`/api/repos/${owner}/${repo}`,{method:'DELETE'});loadRepos();
}

// Chat
function chatKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();}}
function appendMsg(role,text){
  const msgs=document.getElementById('chat-msgs');
  const ts=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
  const d=document.createElement('div');d.className='msg-row '+role;
  d.innerHTML=`<div class="msg-bubble">${text.replace(/\n/g,'<br>')}</div><div class="msg-meta">${ts}</div>`;
  msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;
}
function showTyping(){const msgs=document.getElementById('chat-msgs');const d=document.createElement('div');d.className='msg-row agent';d.id='typing-ind';d.innerHTML='<div class="typing"><span></span><span></span><span></span></div>';msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;}
function hideTyping(){const el=document.getElementById('typing-ind');if(el)el.remove();}
async function sendMsg(){
  const inp=document.getElementById('chat-in');const btn=document.getElementById('send-btn');
  const text=inp.value.trim();if(!text)return;
  inp.value='';inp.style.height='auto';
  appendMsg('user',text);btn.disabled=true;showTyping();
  try{
    const r=await fetch(BASE+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
    const d=await r.json();hideTyping();appendMsg('agent',d.response||'(no response)');
  }catch(e){hideTyping();appendMsg('agent','⚠️ Connection error');}
  btn.disabled=false;inp.focus();
}
document.getElementById('chat-in').addEventListener('input',function(){this.style.height='auto';this.style.height=Math.min(this.scrollHeight,100)+'px';});

// SSE
function connectSSE(){
  if(sse)sse.close();
  sse=new EventSource(BASE+'/api/events');
  sse.onopen=()=>{const b=document.getElementById('sse-badge');if(b){b.textContent='live';b.className='badge g';}};
  sse.onmessage=(e)=>{
    try{const data=JSON.parse(e.data);if(!Object.keys(data).length)return;
    const ts=new Date().toLocaleTimeString();const msg=JSON.stringify(data).slice(0,150);
    evLog.unshift({ts,msg});if(evLog.length>200)evLog.pop();renderEvents();}catch(err){}
  };
  sse.onerror=()=>{const b=document.getElementById('sse-badge');if(b){b.textContent='reconnecting';b.className='badge y';}};
}
function renderEvents(){
  const html=evLog.length?evLog.map(e=>`<div class="ev-line"><span class="ev-ts">${e.ts}</span><span class="ev-msg">${e.msg}</span></div>`).join(''):'<div class="empty">Waiting for events...</div>';
  ['ev-mini','act-feed'].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML=html;});
  const c=document.getElementById('ev-count');if(c)c.textContent=evLog.length+' events';
}

async function init(){
  await loadStatus();
  await Promise.all([loadSkills(),loadTasks()]);
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
        try:
            if self.repos_file.exists():
                return json.loads(self.repos_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _write_repos(self, repos: List[Dict]) -> None:
        self.repos_file.parent.mkdir(parents=True, exist_ok=True)
        self.repos_file.write_text(json.dumps(repos, indent=2), encoding="utf-8")

    def _read_tasks(self) -> List[Dict]:
        try:
            if self.tasks_file.exists():
                return json.loads(self.tasks_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _write_tasks(self, tasks: List[Dict]) -> None:
        self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
        self.tasks_file.write_text(json.dumps(tasks, indent=2), encoding="utf-8")

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

        # Tasks / Kanban
        app.router.add_get("/api/tasks", self._handle_get_tasks)
        app.router.add_post("/api/tasks", self._handle_post_tasks)
        app.router.add_patch("/api/tasks/{id}", self._handle_patch_task)
        app.router.add_delete("/api/tasks/{id}", self._handle_delete_task)
        app.router.add_options("/api/tasks", self._handle_options)
        app.router.add_options("/api/tasks/{id}", self._handle_options)
        app.router.add_post("/api/chat", self._handle_chat)
        app.router.add_options("/api/chat", self._handle_options)

        # Tasks / Kanban
        app.router.add_get("/api/tasks", self._handle_get_tasks)
        app.router.add_post("/api/tasks", self._handle_post_tasks)
        app.router.add_patch("/api/tasks/{id}", self._handle_patch_task)
        app.router.add_delete("/api/tasks/{id}", self._handle_delete_task)
        app.router.add_options("/api/tasks", self._handle_options)
        app.router.add_options("/api/tasks/{id}", self._handle_options)
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





    async def _handle_activity(self, request: "web.Request") -> "web.Response":
        """Return recent event log for activity feed."""
        events = list(getattr(self, "_event_log", []))[-100:]
        return self._json({"events": events})

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
            "status": "backlog",
            "created_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        tasks = self._read_tasks()
        tasks.append(task)
        self._write_tasks(tasks)

        # Auto-dispatch to agent
        try:
            from gateway import run as _run
            from gateway.session import SessionSource
            from gateway.config import Platform
            from gateway.platforms.base import MessageEvent

            runner = getattr(_run, "_active_runner", None)
            if runner is not None:
                prompt = f"[TASK #{task['id']}] Repo: {repo}\n\n{title}\n\n{description}\n\nStart working on this task autonomously. When done, mark it complete."
                source = SessionSource(
                    platform=Platform.TELEGRAM,
                    chat_id=f"task-{task['id']}",
                    user_id="dashboard",
                    user_name="Dashboard",
                    chat_type="dm",
                )
                event = MessageEvent(text=prompt, source=source)
                task["status"] = "in_progress"
                self._write_tasks(tasks)
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




    async def _handle_activity(self, request: "web.Request") -> "web.Response":
        """Return recent event log for activity feed."""
        events = list(getattr(self, "_event_log", []))[-100:]
        return self._json({"events": events})

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
            "status": "backlog",
            "created_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        tasks = self._read_tasks()
        tasks.append(task)
        self._write_tasks(tasks)

        # Auto-dispatch to agent
        try:
            from gateway import run as _run
            from gateway.session import SessionSource
            from gateway.config import Platform
            from gateway.platforms.base import MessageEvent

            runner = getattr(_run, "_active_runner", None)
            if runner is not None:
                prompt = f"[TASK #{task['id']}] Repo: {repo}\n\n{title}\n\n{description}\n\nStart working on this task autonomously. When done, mark it complete."
                source = SessionSource(
                    platform=Platform.TELEGRAM,
                    chat_id=f"task-{task['id']}",
                    user_id="dashboard",
                    user_name="Dashboard",
                    chat_type="dm",
                )
                event = MessageEvent(text=prompt, source=source)
                task["status"] = "in_progress"
                self._write_tasks(tasks)
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
