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
<title>Hermes // System Ops</title>
<style>
:root {
  --bg: #121212;
  --text: #F4F4F4;
  --muted: #888888;
  --accent: #EFA024;
  --divider: #2A2A2A;
  --hover: #171717;
  --font: 'Helvetica Neue', Helvetica, Arial, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  -webkit-font-smoothing: antialiased;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* TOP BAR */
.top-bar {
  padding: 1.25rem 2rem;
  border-bottom: 1px solid var(--divider);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}
.sys-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}
.top-nav {
  display: flex;
  gap: 0;
}
.top-nav a {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  text-decoration: none;
  padding: 4px 14px;
  border-left: 1px solid var(--divider);
  cursor: pointer;
  transition: color .15s;
}
.top-nav a:first-child { border-left: none; }
.top-nav a:hover, .top-nav a.active { color: var(--accent); }
.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--muted);
}
.dot.online { background: var(--accent); box-shadow: 0 0 8px rgba(239,160,36,.45); animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.35} }

/* PAGES */
.page { display: none; flex: 1; overflow: hidden; }
.page.active { display: flex; }

/* MAIN: task panel + chat panel */
.workspace {
  display: grid;
  grid-template-columns: 1fr 400px;
  flex: 1;
  overflow: hidden;
}

/* TASK PANEL */
.task-panel {
  border-right: 1px solid var(--divider);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-head {
  padding: 2rem 2rem 1.5rem;
  border-bottom: 1px solid var(--divider);
  flex-shrink: 0;
}
.panel-eyebrow {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--muted);
  margin-bottom: 0.75rem;
}
.panel-title {
  font-size: 1.75rem;
  font-weight: 400;
  text-transform: uppercase;
  letter-spacing: -0.02em;
  line-height: 1.1;
  margin-bottom: 0.75rem;
}
.panel-desc { font-size: 0.8rem; line-height: 1.6; color: var(--muted); max-width: 420px; }
.panel-actions { margin-top: 1.25rem; display: flex; gap: 1.5rem; align-items: center; }
.action-link {
  color: var(--accent);
  text-decoration: none;
  text-transform: uppercase;
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  border-bottom: 1px solid var(--accent);
  padding-bottom: 2px;
  cursor: pointer;
  background: none;
  border-top: none; border-left: none; border-right: none;
  font-family: var(--font);
  transition: opacity .15s;
}
.action-link:hover { opacity: .7; }
.action-link.muted { color: var(--muted); border-bottom-color: var(--divider); }
.task-scroll { flex: 1; overflow-y: auto; }
.task-item {
  padding: 1.75rem 2rem;
  border-bottom: 1px solid var(--divider);
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 1.5rem;
  align-items: start;
  transition: background .15s;
}
.task-item:hover { background: var(--hover); }
.task-meta {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 4px;
}
.status-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--muted); flex-shrink: 0; }
.task-item.active .status-dot { background: var(--accent); box-shadow: 0 0 6px rgba(239,160,36,.5); animation: pulse 2s infinite; }
.task-item.active .task-meta { color: var(--accent); }
.task-item.pending { opacity: .45; }
.task-name {
  font-size: 1rem;
  font-weight: 400;
  text-transform: uppercase;
  letter-spacing: -0.01em;
  margin-bottom: 0.5rem;
}
.task-desc { font-size: 0.78rem; line-height: 1.55; color: var(--muted); }
.task-priority {
  font-size: 0.6rem;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--muted);
  margin-top: 0.6rem;
}
.task-priority.high { color: var(--accent); }
.task-btns { display: flex; gap: 10px; margin-top: 0.75rem; }
.t-btn {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: .06em;
  background: none;
  border: none;
  border-bottom: 1px solid var(--divider);
  color: var(--muted);
  cursor: pointer;
  padding-bottom: 2px;
  font-family: var(--font);
  transition: color .15s, border-color .15s;
}
.t-btn:hover { color: var(--text); border-bottom-color: var(--text); }
.t-btn.accent { color: var(--accent); border-bottom-color: var(--accent); }
.t-btn.danger:hover { color: #ff4d6d; border-bottom-color: #ff4d6d; }
.col-empty { padding: 3rem 2rem; font-size: 0.75rem; text-transform: uppercase; letter-spacing: .06em; color: var(--divider); }

/* New task bar */
.new-task-bar {
  border-top: 1px solid var(--divider);
  padding: 1.25rem 2rem;
  display: flex;
  gap: 1rem;
  align-items: center;
  flex-shrink: 0;
}
.new-task-bar select, .new-task-bar input {
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--divider);
  color: var(--text);
  font-family: var(--font);
  font-size: 0.78rem;
  padding: 4px 0;
  outline: none;
  transition: border-color .15s;
}
.new-task-bar select { color: var(--muted); width: 160px; cursor: pointer; }
.new-task-bar select option { background: #1a1a1a; }
.new-task-bar input { flex: 1; }
.new-task-bar input::placeholder { color: #3a3a3a; text-transform: uppercase; font-size: 0.7rem; letter-spacing: .05em; }
.new-task-bar input:focus, .new-task-bar select:focus { border-bottom-color: var(--text); }

/* CHAT PANEL */
.chat-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.chat-head {
  padding: 1.5rem 2rem;
  border-bottom: 1px solid var(--divider);
  flex-shrink: 0;
}
.chat-msgs {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 2rem;
}
.msg { display: flex; flex-direction: column; gap: 4px; max-width: 92%; }
.msg.user { align-self: flex-end; text-align: right; }
.msg.agent { align-self: flex-start; }
.msg-sender {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: .1em;
  color: var(--muted);
}
.msg.agent .msg-sender { color: var(--accent); }
.msg-content { font-size: 0.9rem; line-height: 1.65; color: var(--text); }
.msg.user .msg-content { color: var(--muted); }
.typing-row { display: flex; gap: 5px; align-items: center; padding: 4px 0; }
.typing-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--muted); animation: bounce .9s infinite; }
.typing-dot:nth-child(2){animation-delay:.15s} .typing-dot:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-5px)}}
.chat-input-area {
  padding: 1.5rem 2rem;
  border-top: 1px solid var(--divider);
  flex-shrink: 0;
}
.chat-input-area textarea {
  width: 100%;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--divider);
  color: var(--text);
  font-family: var(--font);
  font-size: 0.9rem;
  padding: 4px 0 10px;
  resize: none;
  outline: none;
  min-height: 36px;
  line-height: 1.5;
  transition: border-color .2s;
}
.chat-input-area textarea:focus { border-bottom-color: var(--text); }
.chat-input-area textarea::placeholder { color: #333; text-transform: uppercase; font-size: 0.7rem; letter-spacing: .05em; }
.chat-input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.75rem;
}
.input-hint { font-size: 0.6rem; text-transform: uppercase; letter-spacing: .07em; color: #333; }

/* REPOS PAGE */
.repos-wrap { flex: 1; overflow-y: auto; }
.repo-item {
  padding: 1.5rem 2rem;
  border-bottom: 1px solid var(--divider);
  display: flex;
  align-items: center;
  justify-content: space-between;
  transition: background .15s;
}
.repo-item:hover { background: var(--hover); }
.repo-name { font-size: 0.9rem; text-transform: uppercase; letter-spacing: -.01em; }
.repo-url { font-size: 0.7rem; color: var(--muted); margin-top: 3px; }

/* ACTIVITY PAGE */
.activity-wrap { flex: 1; overflow-y: auto; }
.ev-item {
  padding: 1rem 2rem;
  border-bottom: 1px solid var(--divider);
  display: grid;
  grid-template-columns: 80px 1fr;
  gap: 1.5rem;
  font-size: 0.75rem;
  font-family: 'Menlo','Courier New',monospace;
}
.ev-ts { color: var(--accent); }
.ev-msg { color: var(--muted); word-break: break-all; }
.ev-empty { padding: 3rem 2rem; font-size: 0.7rem; text-transform: uppercase; letter-spacing: .08em; color: var(--divider); }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--divider); }

/* KPI strip */
.kpi-strip {
  display: grid;
  grid-template-columns: repeat(4,1fr);
  border-bottom: 1px solid var(--divider);
  flex-shrink: 0;
}
.kpi-cell {
  padding: 1.25rem 2rem;
  border-right: 1px solid var(--divider);
}
.kpi-cell:last-child { border-right: none; }
.kpi-label { font-size: 0.6rem; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); margin-bottom: 6px; }
.kpi-val { font-size: 1.4rem; font-weight: 400; }
.kpi-val.online { color: var(--accent); }
.kpi-sub { font-size: 0.65rem; color: var(--muted); margin-top: 3px; }
</style>
</head>
<body>
<header class="top-bar">
  <div class="sys-label">Hermes // System Ops Terminal</div>
  <nav class="top-nav">
    <a class="active" data-page="main" onclick="nav(this,event)">Operations</a>
    <a data-page="repos" onclick="nav(this,event)">Repos</a>
    <a data-page="activity" onclick="nav(this,event)">Activity</a>
  </nav>
  <div class="status-indicator">
    <div class="dot" id="dot"></div>
    <span id="status-txt">connecting</span>
    <span style="margin-left:8px" id="uptime-txt">—</span>
  </div>
</header>

<!-- MAIN OPS PAGE -->
<div class="page active" id="page-main" style="flex-direction:column">
  <div class="kpi-strip">
    <div class="kpi-cell"><div class="kpi-label">Gateway</div><div class="kpi-val" id="kpi-gw">—</div></div>
    <div class="kpi-cell"><div class="kpi-label">In Progress</div><div class="kpi-val" id="kpi-active">—</div></div>
    <div class="kpi-cell"><div class="kpi-label">Backlog</div><div class="kpi-val" id="kpi-backlog">—</div></div>
    <div class="kpi-cell"><div class="kpi-label">Completed</div><div class="kpi-val" id="kpi-done">—</div></div>
  </div>
  <div class="workspace">
    <!-- TASK PANEL -->
    <section class="task-panel">
      <div class="panel-head">
        <div class="panel-eyebrow">Task Queue</div>
        <h1 class="panel-title" id="op-title">Standby</h1>
        <p class="panel-desc" id="op-desc">No active operations. Assign a task below.</p>
      </div>
      <div class="task-scroll" id="task-list">
        <div class="col-empty">No tasks assigned</div>
      </div>
      <div class="new-task-bar">
        <select id="nt-repo"><option value="">— Select repo —</option></select>
        <input id="nt-title" placeholder="Describe the task..." onkeydown="if(event.key==='Enter')addTask()"/>
        <button class="action-link" onclick="addTask()">Assign →</button>
      </div>
    </section>
    <!-- CHAT PANEL -->
    <section class="chat-panel">
      <div class="chat-head">
        <div class="panel-eyebrow">Agent Comm Link</div>
      </div>
      <div class="chat-msgs" id="chat-msgs">
        <div class="msg agent">
          <span class="msg-sender">Hermes Core • now</span>
          <p class="msg-content">System online. Awaiting instructions.</p>
        </div>
      </div>
      <div class="chat-input-area">
        <textarea id="chat-in" placeholder="Transmit instruction..." rows="1" onkeydown="chatKey(event)"></textarea>
        <div class="chat-input-footer">
          <span class="input-hint">Enter to send / Shift+Enter for new line</span>
          <button class="action-link" onclick="sendMsg()">Transmit</button>
        </div>
      </div>
    </section>
  </div>
</div>

<!-- REPOS PAGE -->
<div class="page" id="page-repos" style="flex-direction:column">
  <div class="panel-head" style="flex-shrink:0">
    <div class="panel-eyebrow">Watched Repositories</div>
    <h1 class="panel-title">Repo Registry</h1>
    <div class="panel-actions">
      <input id="r-owner" placeholder="owner" style="background:transparent;border:none;border-bottom:1px solid var(--divider);color:var(--text);font-family:var(--font);font-size:.8rem;padding:4px 0;outline:none;width:120px" />
      <input id="r-repo" placeholder="repo" style="background:transparent;border:none;border-bottom:1px solid var(--divider);color:var(--text);font-family:var(--font);font-size:.8rem;padding:4px 0;outline:none;width:160px" />
      <button class="action-link" onclick="addRepo()">Register →</button>
      <button class="action-link muted" onclick="loadRepos()">↻ Refresh</button>
    </div>
  </div>
  <div class="repos-wrap" id="repos-list">
    <div class="ev-empty">Loading...</div>
  </div>
</div>

<!-- ACTIVITY PAGE -->
<div class="page" id="page-activity" style="flex-direction:column">
  <div class="panel-head" style="flex-shrink:0">
    <div class="panel-eyebrow">Live Event Stream</div>
    <h1 class="panel-title">System Activity</h1>
    <div style="margin-top:.75rem">
      <span class="sys-label" id="ev-status">Connecting to stream...</span>
    </div>
  </div>
  <div class="activity-wrap" id="act-feed">
    <div class="ev-empty">Waiting for events...</div>
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
  document.querySelectorAll('.top-nav a').forEach(a=>a.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  const pg=el.dataset.page;
  document.getElementById('page-'+pg).classList.add('active');
  if(pg==='repos')loadRepos();
  if(pg==='activity')document.getElementById('ev-status').textContent=evLog.length+' events captured';
}

function fmt(s){if(!s)return '—';if(s<60)return s.toFixed(0)+'s';if(s<3600)return(s/60).toFixed(0)+'m';if(s<86400)return(s/3600).toFixed(1)+'h';return(s/86400).toFixed(1)+'d';}
function timeAgo(iso){const d=new Date(iso+'Z');const s=Math.floor((Date.now()-d)/1000);if(s<60)return s+'s ago';if(s<3600)return Math.floor(s/60)+'m ago';if(s<86400)return Math.floor(s/3600)+'h ago';return Math.floor(s/86400)+'d ago';}

async function loadStatus(){
  try{
    const d=await fetch(BASE+'/api/status').then(r=>r.json());
    document.getElementById('kpi-gw').textContent=d.gateway_running?'ONLINE':'OFFLINE';
    document.getElementById('kpi-gw').className='kpi-val'+(d.gateway_running?' online':'');
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
    const active=allTasks.filter(t=>t.status==='in_progress');
    const backlog=allTasks.filter(t=>t.status==='backlog');
    const done=allTasks.filter(t=>t.status==='done');
    document.getElementById('kpi-active').textContent=active.length;
    document.getElementById('kpi-backlog').textContent=backlog.length;
    document.getElementById('kpi-done').textContent=done.length;
    // Update panel header with most recent active task
    if(active.length){
      document.getElementById('op-title').textContent=active[0].title.toUpperCase();
      document.getElementById('op-desc').textContent=active[0].description||active[0].repo;
    } else if(allTasks.length){
      document.getElementById('op-title').textContent='STANDBY';
      document.getElementById('op-desc').textContent='All tasks complete. Assign a new operation.';
    }
  }catch(e){}
}

function renderTasks(){
  const el=document.getElementById('task-list');
  if(!allTasks.length){el.innerHTML='<div class="col-empty">No tasks assigned</div>';return;}
  // Order: in_progress first, then backlog, then done
  const sorted=[...allTasks].sort((a,b)=>{
    const o={in_progress:0,backlog:1,done:2};
    return (o[a.status]||1)-(o[b.status]||1);
  });
  el.innerHTML=sorted.map(t=>{
    const isActive=t.status==='in_progress';
    const isDone=t.status==='done';
    const statusLabel=isActive?'Processing':isDone?'Completed':'Pending';
    return `<div class="task-item${isActive?' active':''}${t.status==='backlog'?' pending':''}">
      <div class="task-meta"><span class="status-dot"></span>${statusLabel}</div>
      <div>
        <div class="task-name">${t.title}</div>
        ${t.description?`<div class="task-desc">${t.description}</div>`:''}
        <div class="task-priority${t.priority==='high'||t.priority==='urgent'?' high':''}">${t.repo} · ${t.priority} · ${timeAgo(t.created_at)}</div>
        <div class="task-btns">
          ${isActive?`<button class="t-btn accent" onclick="moveTask('${t.id}','done')">Mark Done</button>`:''}
          ${t.status==='backlog'?`<button class="t-btn accent" onclick="moveTask('${t.id}','in_progress')">Start</button>`:''}
          ${isDone?`<button class="t-btn" onclick="moveTask('${t.id}','backlog')">Reopen</button>`:''}
          <button class="t-btn danger" onclick="deleteTask('${t.id}')">Remove</button>
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

async function moveTask(id,status){
  await fetch(BASE+`/api/tasks/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});
  loadTasks();
}
async function deleteTask(id){
  await fetch(BASE+`/api/tasks/${id}`,{method:'DELETE'});
  loadTasks();
}

async function loadRepos(){
  document.getElementById('repos-list').innerHTML='<div class="ev-empty">Loading...</div>';
  try{
    const d=await fetch(BASE+'/api/repos').then(r=>r.json());
    allRepos=d.repos||[];
    // Populate repo dropdown
    const sel=document.getElementById('nt-repo');
    const cur=sel.value;
    sel.innerHTML='<option value="">— Select repo —</option>';
    allRepos.forEach(r=>{const o=document.createElement('option');o.value=r.owner+'/'+r.repo;o.textContent=r.owner+'/'+r.repo;sel.appendChild(o);});
    sel.value=cur;
    if(!allRepos.length){document.getElementById('repos-list').innerHTML='<div class="ev-empty">No repos registered</div>';return;}
    document.getElementById('repos-list').innerHTML=allRepos.map(r=>`
      <div class="repo-item">
        <div>
          <div class="repo-name">${r.owner} / ${r.repo}</div>
          <div class="repo-url">github.com/${r.owner}/${r.repo}</div>
        </div>
        <button class="t-btn danger" onclick="delRepo('${r.owner}','${r.repo}')">Deregister</button>
      </div>`).join('');
  }catch(e){document.getElementById('repos-list').innerHTML='<div class="ev-empty">Connection failed</div>';}
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
  await fetch(BASE+`/api/repos/${owner}/${repo}`,{method:'DELETE'});
  loadRepos();
}

// CHAT
function ts(){return new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});}
function chatKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();}}
function appendMsg(role,text){
  const msgs=document.getElementById('chat-msgs');
  const d=document.createElement('div');d.className='msg '+role;
  const sender=role==='user'?'You':'Hermes Core';
  d.innerHTML=`<span class="msg-sender">${sender} • ${ts()}</span><p class="msg-content">${text.replace(/\\n/g,'<br>')}</p>`;
  msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;
}
function showTyping(){
  const msgs=document.getElementById('chat-msgs');
  const d=document.createElement('div');d.className='msg agent';d.id='typing-ind';
  d.innerHTML=`<span class="msg-sender">Hermes Core</span><div class="typing-row"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>`;
  msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;
}
function hideTyping(){const el=document.getElementById('typing-ind');if(el)el.remove();}
async function sendMsg(){
  const inp=document.getElementById('chat-in');const text=inp.value.trim();if(!text)return;
  inp.value='';inp.style.height='auto';
  appendMsg('user',text);showTyping();
  try{
    const r=await fetch(BASE+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
    const d=await r.json();hideTyping();appendMsg('agent',d.response||'—');
  }catch(e){hideTyping();appendMsg('agent','Connection error. Gateway may be offline.');}
}
document.getElementById('chat-in').addEventListener('input',function(){this.style.height='auto';this.style.height=Math.min(this.scrollHeight,120)+'px';});

// SSE
function connectSSE(){
  if(sse)sse.close();
  sse=new EventSource(BASE+'/api/events');
  sse.onopen=()=>document.getElementById('ev-status').textContent='Stream active — '+evLog.length+' events';
  sse.onmessage=(e)=>{
    try{const data=JSON.parse(e.data);if(!Object.keys(data).length)return;
    evLog.unshift({ts:new Date().toLocaleTimeString(),msg:JSON.stringify(data).slice(0,200)});
    if(evLog.length>200)evLog.pop();renderEvents();}catch(err){}
  };
  sse.onerror=()=>document.getElementById('ev-status').textContent='Stream reconnecting...';
}
function renderEvents(){
  const el=document.getElementById('act-feed');
  el.innerHTML=evLog.length?evLog.map(e=>`<div class="ev-item"><span class="ev-ts">${e.ts}</span><span class="ev-msg">${e.msg}</span></div>`).join(''):'<div class="ev-empty">Waiting for events...</div>';
  document.getElementById('ev-status').textContent='Stream active — '+evLog.length+' events';
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

        # Activity
        app.router.add_get("/api/activity", self._handle_activity)
        app.router.add_options("/api/activity", self._handle_options)

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
