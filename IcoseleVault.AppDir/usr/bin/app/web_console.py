"""Task 1 — Local web management console using stdlib http.server only."""
from __future__ import annotations

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

log = logging.getLogger(__name__)

_PORT = 47821
_server: HTTPServer | None = None
_thread: threading.Thread | None = None
_data_fn = None  # callable returning API data


def set_data_provider(fn):
    global _data_fn
    _data_fn = fn


def _get_data() -> dict:
    if _data_fn:
        try:
            return _data_fn()
        except Exception:
            pass
    return {"vms": [], "audit": [], "stats": {}}


_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Icosele Vault Console</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1e1e2e;color:#cdd6f4;font-family:'Inter','Segoe UI',sans-serif;font-size:14px}
a{color:#f47b1f;text-decoration:none}
a:hover{text-decoration:underline}
.top{background:#181825;padding:12px 24px;display:flex;align-items:center;gap:16px;border-bottom:1px solid #313244}
.top h1{font-size:18px;font-weight:800;color:#f47b1f;letter-spacing:2px}
.nav{display:flex;gap:8px}
.nav a{padding:6px 14px;border-radius:6px;color:#a6adc8;font-size:12px;font-weight:600}
.nav a.active,.nav a:hover{background:#313244;color:#cdd6f4}
.main{padding:24px;max-width:960px;margin:0 auto}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-bottom:20px}
.card{background:#313244;border-radius:8px;padding:14px;text-align:center}
.card .val{font-size:24px;font-weight:900;color:#cdd6f4}
.card .lbl{font-size:9px;color:#6c7086;text-transform:uppercase;letter-spacing:1px;margin-top:4px}
table{width:100%;border-collapse:collapse;margin-top:12px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #313244;font-size:12px}
th{color:#6c7086;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:1px}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700}
.badge-running{background:#1a3328;color:#a6e3a1;border:1px solid #a6e3a1}
.badge-stopped{background:#2a2a2a;color:#6c7086;border:1px solid #45475a}
.btn{padding:4px 10px;border:1px solid #45475a;border-radius:4px;background:transparent;color:#cdd6f4;cursor:pointer;font-size:11px}
.btn:hover{border-color:#f47b1f;color:#f47b1f}
.btn-accent{background:#f47b1f;color:#1e1e2e;border-color:#f47b1f}
select{background:#313244;color:#cdd6f4;border:1px solid #45475a;padding:6px 10px;border-radius:4px;font-size:12px}
#feed{margin-top:12px}
.feed-item{padding:6px 0;border-bottom:1px solid #313244;font-size:11px;color:#a6adc8}
</style>
</head>
<body>
<div class="top">
<h1>ICOSELE VAULT</h1>
<div class="nav">
<a href="#dashboard" onclick="go('dashboard')">Dashboard</a>
<a href="#vms" onclick="go('vms')">VMs</a>
<a href="#audit" onclick="go('audit')">Audit</a>
<a href="#settings" onclick="go('settings')">Settings</a>
</div>
</div>
<div class="main" id="content"></div>
<script>
let DATA={vms:[],audit:[],stats:{}};
async function load(){try{const r=await fetch('/api/data');DATA=await r.json()}catch(e){}}
function go(p){location.hash=p;render()}
function render(){
const h=location.hash.slice(1)||'dashboard';
document.querySelectorAll('.nav a').forEach(a=>{a.classList.toggle('active',a.hash==='#'+h)});
const c=document.getElementById('content');
if(h==='dashboard')renderDash(c);
else if(h==='vms')renderVMs(c);
else if(h==='audit')renderAudit(c);
else if(h==='settings')renderSettings(c);
}
function renderDash(c){
const s=DATA.stats||{};
c.innerHTML=`<h2>Dashboard</h2>
<div class="cards">
<div class="card"><div class="val">${s.total_vms||0}</div><div class="lbl">Total VMs</div></div>
<div class="card"><div class="val">${s.running||0}</div><div class="lbl">Running</div></div>
<div class="card"><div class="val">${s.stopped||0}</div><div class="lbl">Stopped</div></div>
<div class="card"><div class="val">${s.snapshots||0}</div><div class="lbl">Snapshots</div></div>
<div class="card"><div class="val">${s.disk_gb||'0'}</div><div class="lbl">Disk GB</div></div>
</div>
<h3 style="font-size:12px;color:#6c7086;margin-bottom:8px">RECENT ACTIVITY</h3>
<div id="feed">${(DATA.audit||[]).slice(-20).reverse().map(e=>
`<div class="feed-item">${(e.timestamp||'').slice(0,19).replace('T',' ')} &mdash; <b>${e.action||''}</b> ${e.vm_name||''}</div>`
).join('')}</div>`;
}
function renderVMs(c){
const rows=(DATA.vms||[]).map(v=>{
const badge=v.status==='running'?'badge-running':'badge-stopped';
return`<tr><td>${v.name}</td><td><span class="badge ${badge}">${v.status}</span></td>
<td>${v.ram_mb} MB</td><td>${v.cpu_cores}</td><td>${v.disk_mb||0} MB</td></tr>`;
}).join('');
c.innerHTML=`<h2>Virtual Machines</h2><table><thead><tr><th>Name</th><th>Status</th><th>RAM</th><th>CPU</th><th>Disk</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderAudit(c){
const entries=DATA.audit||[];
const actions=[...new Set(entries.map(e=>e.action))];
const opts=actions.map(a=>`<option value="${a}">${a}</option>`).join('');
c.innerHTML=`<h2>Audit Log</h2>
<select id="af" onchange="filterAudit()"><option value="">All</option>${opts}</select>
<button class="btn" onclick="exportCSV()" style="margin-left:8px">Export CSV</button>
<table><thead><tr><th>Time</th><th>Action</th><th>VM</th><th>Details</th></tr></thead><tbody id="at"></tbody></table>`;
filterAudit();
}
function filterAudit(){
const f=document.getElementById('af').value;
const rows=(DATA.audit||[]).filter(e=>!f||e.action===f).reverse().map(e=>
`<tr><td>${(e.timestamp||'').slice(0,19).replace('T',' ')}</td><td>${e.action||''}</td><td>${e.vm_name||''}</td><td style="font-size:10px;color:#6c7086">${JSON.stringify(e.details||{}).slice(0,80)}</td></tr>`
).join('');
document.getElementById('at').innerHTML=rows;
}
function exportCSV(){
let csv='Timestamp,Action,VM,Details\n';
(DATA.audit||[]).forEach(e=>{csv+=`"${e.timestamp}","${e.action}","${e.vm_name}","${JSON.stringify(e.details)}"\n`});
const a=document.createElement('a');a.href='data:text/csv,'+encodeURIComponent(csv);a.download='audit.csv';a.click();
}
function renderSettings(c){
c.innerHTML=`<h2>Settings</h2>
<div class="card" style="text-align:left;padding:16px"><p>Version: 0.1.0</p><p>API: localhost:47821</p>
<p>Webhooks: check data/webhooks.json</p><p>Plugins: check plugins/ directory</p></div>`;
}
async function init(){await load();render();setInterval(async()=>{await load();render()},10000)}
window.onhashchange=render;
init();
</script>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/data":
            data = _get_data()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_HTML.encode())

    def log_message(self, fmt, *args):
        pass


def start():
    global _server, _thread
    if _server:
        return
    _server = HTTPServer(("127.0.0.1", _PORT), _Handler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    log.info("Web console started on http://localhost:%d", _PORT)


def stop():
    global _server, _thread
    if _server:
        _server.shutdown()
        _server = None
        _thread = None


def is_running() -> bool:
    return _server is not None
