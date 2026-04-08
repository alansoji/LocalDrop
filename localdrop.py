#!/usr/bin/env python3
"""
LocalDrop — Multi-device wireless file & notes bridge
Features: text notes, multi-device support, per-device activity
Requirements: pip install pyqt6 qrcode[pil]
Falls back to PyQt5 if PyQt6 not available.
Runs on Windows, macOS, and Linux.
"""
import sys
import os
import socket
import io
import json
import mimetypes
import urllib.parse
import http.server
import threading
import traceback
from datetime import datetime
from pathlib import Path

# ── PyQt6 / PyQt5 ─────────────────────────────────────────────
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QTextEdit, QFrame, QSizePolicy,
        QSystemTrayIcon, QMenu, QMessageBox, QTabWidget
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
    from PyQt6.QtGui import QPixmap, QImage, QFont, QIcon, QColor, QPalette, QAction
    PYQT = 6
except ImportError:
    try:
        from PyQt5.QtWidgets import (
            QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
            QLabel, QPushButton, QTextEdit, QFrame, QSizePolicy,
            QSystemTrayIcon, QMenu, QMessageBox, QTabWidget
        )
        from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
        from PyQt5.QtGui import QPixmap, QImage, QFont, QIcon, QColor, QPalette
        from PyQt5.QtWidgets import QAction
        PYQT = 5
    except ImportError:
        print("ERROR: PyQt6 or PyQt5 is required.")
        print("Install: pip install pyqt6 qrcode[pil]")
        sys.exit(1)

# ── Config ──────────────────────────────────────────────────────
PREFERRED_PORT = 5005
SAVE_DIR = Path.home() / "LocalDrop_Received"

# Shared state between HTTP handler and GUI
_shared_state = {
    "notes":        [],   # list of {text, time, device}
    "devices":      {},   # ip -> {name, last_seen, files_sent}
    "log_callback": None,
    "server_url":   "",
}
_state_lock = threading.Lock()

# ── Helpers ─────────────────────────────────────────────────────
def get_local_ip():
    """Return (ip, warning_or_None). Tries multiple methods."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            return ip, None
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith(("192.", "10.", "172.")):
                return ip, None
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import subprocess
            out = subprocess.check_output(["ipconfig"], text=True, errors="ignore")
            for line in out.splitlines():
                if "IPv4" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        ip = parts[-1].strip()
                        if ip.startswith(("192.", "10.", "172.")):
                            return ip, None
        except Exception:
            pass
    else:
        try:
            import subprocess
            out = subprocess.check_output(["hostname", "-I"], text=True)
            for part in out.split():
                if part.startswith(("192.", "10.", "172.")):
                    return part, None
        except Exception:
            pass
    return "127.0.0.1", "⚠️ No LAN IP found — is Wi-Fi on?"


def find_free_port(preferred: int, search_range: int = 20) -> int:
    for port in range(preferred, preferred + search_range):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise OSError(f"No free port in {preferred}–{preferred + search_range - 1}")


def make_qr_pixmap(url: str, size: int = 200):
    try:
        import qrcode
        qr = qrcode.QRCode(border=2, box_size=6,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#7c6dfa", back_color="#13131a")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        qimg = QImage()
        qimg.loadFromData(buf.read())
        px = QPixmap.fromImage(qimg)
        mode_ar = Qt.AspectRatioMode.KeepAspectRatio if PYQT == 6 else Qt.KeepAspectRatio
        mode_tr = Qt.TransformationMode.SmoothTransformation if PYQT == 6 else Qt.SmoothTransformation
        return px.scaled(size, size, mode_ar, mode_tr)
    except Exception:
        return None


def _log(msg):
    cb = _shared_state.get("log_callback")
    if cb:
        cb(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def _register_device(client_ip, name=None):
    with _state_lock:
        entry = _shared_state["devices"].get(
            client_ip,
            {"name": name or client_ip, "last_seen": "", "files_sent": 0}
        )
        if name:
            entry["name"] = name
        entry["last_seen"] = datetime.now().strftime("%H:%M:%S")
        _shared_state["devices"][client_ip] = entry
    return entry


# ── HTML page (clipboard removed) ───────────────────────────────
def build_html(server_url):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LocalDrop</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0a0f;--surface:#13131a;--card:#1a1a24;--border:#2a2a3a;
--accent:#7c6dfa;--accent2:#fa6d9a;--accent3:#6dfac8;--text:#e8e8f0;--muted:#6b6b80;
--success:#4ade80;--r:16px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);
min-height:100vh;padding:24px 16px 80px;
background-image:radial-gradient(ellipse at 15% 0%,rgba(124,109,250,.18) 0%,transparent 55%),
radial-gradient(ellipse at 85% 100%,rgba(250,109,154,.12) 0%,transparent 55%)}}
.center{{display:flex;flex-direction:column;align-items:center}}
.logo{{font-family:'Syne',sans-serif;font-weight:800;font-size:2rem;
background:linear-gradient(135deg,var(--accent),var(--accent2));
-webkit-background-clip:text;-webkit-text-fill-color:transparent;
letter-spacing:-1px;margin-bottom:2px}}
.tagline{{color:var(--muted);font-size:.82rem;margin-bottom:28px}}
.tabs{{display:flex;gap:6px;margin-bottom:20px;width:100%;max-width:500px;flex-wrap:wrap}}
.tab{{flex:1;min-width:80px;padding:9px 6px;border:1px solid var(--border);
border-radius:10px;background:var(--surface);color:var(--muted);
font-family:'Syne',sans-serif;font-weight:700;font-size:.78rem;cursor:pointer;
transition:all .2s;text-align:center}}
.tab.active{{background:var(--accent);border-color:var(--accent);color:#fff}}
.panel{{display:none;width:100%;max-width:500px}}
.panel.active{{display:block}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:var(--r);
padding:20px;margin-bottom:14px}}
.card-title{{font-family:'Syne',sans-serif;font-weight:700;font-size:.75rem;
color:var(--muted);letter-spacing:1px;text-transform:uppercase;margin-bottom:14px}}
.drop-zone{{border:2px dashed var(--border);border-radius:12px;padding:32px 16px;
text-align:center;cursor:pointer;transition:all .2s;
background:rgba(124,109,250,.03);position:relative}}
.drop-zone:hover,.drop-zone.over{{border-color:var(--accent);background:rgba(124,109,250,.08)}}
.drop-zone input[type=file]{{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}}
.di{{font-size:2rem;display:block;margin-bottom:8px}}
.dl{{font-family:'Syne',sans-serif;font-weight:700;font-size:1rem;margin-bottom:4px}}
.ds{{font-size:.75rem;color:var(--muted)}}
.file-list{{margin-top:10px;display:flex;flex-direction:column;gap:6px}}
.file-item{{display:flex;align-items:center;gap:8px;background:var(--surface);
border:1px solid var(--border);border-radius:10px;padding:8px 11px;font-size:.82rem}}
.fi{{font-size:1.1rem;flex-shrink:0}}.fn{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.fs{{color:var(--muted);font-size:.7rem;flex-shrink:0}}
.frm{{background:none;border:none;color:var(--muted);cursor:pointer;font-size:.9rem;
padding:0 2px;transition:color .15s}}.frm:hover{{color:var(--accent2)}}
.prog-wrap{{margin-top:12px;display:none}}.prog-wrap.show{{display:block}}
.prog-bg{{height:4px;background:var(--border);border-radius:99px;overflow:hidden;margin-bottom:6px}}
.prog-bar{{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));
border-radius:99px;width:0;transition:width .25s}}
.prog-txt{{font-size:.75rem;color:var(--muted);text-align:center}}
.btn{{width:100%;padding:12px;border:none;border-radius:12px;color:#fff;
font-family:'Syne',sans-serif;font-weight:700;font-size:.92rem;cursor:pointer;
margin-top:12px;transition:all .2s;letter-spacing:.4px}}
.btn-primary{{background:linear-gradient(135deg,var(--accent),#9b6dfa)}}
.btn-primary:hover{{opacity:.9;transform:translateY(-1px)}}
.btn-primary:disabled{{opacity:.35;cursor:not-allowed;transform:none}}
.btn-green{{background:linear-gradient(135deg,#22c55e,#16a34a)}}
.btn-green:hover{{opacity:.9}}
.laptop-files{{display:flex;flex-direction:column;gap:8px}}
.lf-item{{display:flex;align-items:center;gap:10px;background:var(--surface);
border:1px solid var(--border);border-radius:10px;padding:10px 13px}}
.lf-info{{flex:1;overflow:hidden}}
.lf-name{{font-size:.83rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.lf-meta{{font-size:.7rem;color:var(--muted);margin-top:2px}}
.dl-btn{{background:rgba(124,109,250,.15);border:1px solid rgba(124,109,250,.3);
color:var(--accent);font-size:.75rem;font-weight:600;padding:5px 11px;
border-radius:8px;cursor:pointer;white-space:nowrap;transition:all .15s;flex-shrink:0}}
.dl-btn:hover{{background:rgba(124,109,250,.28)}}
.empty{{color:var(--muted);font-size:.83rem;text-align:center;padding:18px 0}}
.refresh-row{{display:flex;justify-content:flex-end;margin-bottom:10px}}
.refresh-btn{{background:none;border:1px solid var(--border);color:var(--muted);
font-size:.75rem;padding:4px 11px;border-radius:8px;cursor:pointer;transition:all .15s}}
.refresh-btn:hover{{border-color:var(--accent);color:var(--accent)}}
.h-item{{display:flex;align-items:center;gap:8px;padding:8px 0;
border-bottom:1px solid var(--border);font-size:.82rem}}
.h-item:last-child{{border-bottom:none}}
.h-name{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.h-time{{color:var(--muted);font-size:.7rem;flex-shrink:0}}
.badge{{font-size:.65rem;padding:2px 7px;border-radius:99px;font-weight:600;flex-shrink:0}}
.badge-ok{{background:rgba(74,222,128,.14);color:var(--success)}}
.badge-dl{{background:rgba(124,109,250,.14);color:var(--accent)}}
textarea{{width:100%;background:var(--surface);border:1px solid var(--border);
border-radius:10px;color:var(--text);font-family:'DM Sans',sans-serif;font-size:.88rem;
padding:12px;resize:vertical;min-height:100px;outline:none;transition:border-color .2s}}
textarea:focus{{border-color:var(--accent)}}
.note-item{{background:var(--surface);border:1px solid var(--border);
border-radius:10px;padding:11px 13px;margin-bottom:8px}}
.note-text{{font-size:.85rem;line-height:1.5;white-space:pre-wrap;word-break:break-word}}
.note-meta{{font-size:.68rem;color:var(--muted);margin-top:5px}}
.dev-item{{display:flex;align-items:center;gap:10px;background:var(--surface);
border:1px solid var(--border);border-radius:10px;padding:11px 14px;margin-bottom:8px}}
.dev-dot{{width:8px;height:8px;border-radius:50%;background:var(--success);flex-shrink:0}}
.dev-info{{flex:1}}.dev-name{{font-size:.85rem;font-weight:600}}
.dev-meta{{font-size:.7rem;color:var(--muted);margin-top:2px}}
.toast{{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(120px);
background:var(--success);color:#0a0a0f;font-weight:600;padding:10px 20px;
border-radius:99px;font-size:.86rem;transition:transform .3s cubic-bezier(.34,1.56,.64,1);
white-space:nowrap;z-index:999}}
.toast.err{{background:var(--accent2)}}.toast.show{{transform:translateX(-50%) translateY(0)}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.spin{{display:inline-block;animation:spin .7s linear infinite}}
.row{{display:flex;gap:8px;align-items:center}}
</style>
</head>
<body class="center">
<div class="logo">LocalDrop</div>
<p class="tagline">Multi-device wireless bridge — files &amp; notes</p>
<div class="tabs">
  <div class="tab active" onclick="switchTab('send')">Send</div>
  <div class="tab" onclick="switchTab('receive')">Receive</div>
  <div class="tab" onclick="switchTab('notes')">Notes</div>
  <div class="tab" onclick="switchTab('devices')">Devices</div>
</div>

<!-- SEND -->
<div class="panel active" id="panel-send">
  <div class="card">
    <div class="card-title">Choose files to send</div>
    <div class="drop-zone" id="dropZone">
      <input type="file" id="fileInput" multiple>
      <span class="di">📁</span>
      <div class="dl">Tap or drop files here</div>
      <div class="ds">Images · PDFs · Videos · Any type</div>
    </div>
    <div class="file-list" id="fileList"></div>
    <div class="prog-wrap" id="progWrap">
      <div class="prog-bg"><div class="prog-bar" id="progBar"></div></div>
      <div class="prog-txt" id="progTxt">Sending…</div>
    </div>
    <button class="btn btn-primary" id="sendBtn" disabled onclick="uploadFiles()">Send to Laptop</button>
  </div>
  <div class="card">
    <div class="card-title">Send history</div>
    <div id="sendHistory"><div class="empty">Nothing sent yet</div></div>
  </div>
</div>

<!-- RECEIVE -->
<div class="panel" id="panel-receive">
  <div class="card">
    <div class="card-title">Files on laptop</div>
    <div class="refresh-row"><button class="refresh-btn" onclick="loadLaptopFiles()">Refresh</button></div>
    <div class="laptop-files" id="laptopFiles"><div class="empty"><span class="spin">⟳</span> Loading</div></div>
  </div>
  <div class="card">
    <div class="card-title">Download history</div>
    <div id="dlHistory"><div class="empty">Nothing downloaded yet</div></div>
  </div>
</div>

<!-- NOTES -->
<div class="panel" id="panel-notes">
  <div class="card">
    <div class="card-title">Send a note to laptop</div>
    <textarea id="noteInput" placeholder="Quick message, URL, anything…"></textarea>
    <button class="btn btn-primary" onclick="sendNote()">Send Note</button>
  </div>
  <div class="card">
    <div class="card-title">Notes log</div>
    <div class="refresh-row"><button class="refresh-btn" onclick="loadNotes()">Refresh</button></div>
    <div id="notesList"><div class="empty">No notes yet</div></div>
  </div>
</div>

<!-- DEVICES -->
<div class="panel" id="panel-devices">
  <div class="card">
    <div class="card-title">Connected devices</div>
    <div class="refresh-row"><button class="refresh-btn" onclick="loadDevices()">Refresh</button></div>
    <div id="devicesList"><div class="empty"><span class="spin">⟳</span> Loading</div></div>
  </div>
  <div class="card">
    <div class="card-title">Your device name</div>
    <div class="row">
      <input id="devNameInput" type="text" placeholder="My Phone"
        style="flex:1;background:var(--surface);border:1px solid var(--border);border-radius:9px;
        color:var(--text);font-family:'DM Sans',sans-serif;font-size:.88rem;padding:9px 12px;outline:none">
      <button class="refresh-btn" onclick="registerName()">Save</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>
<script>
let selectedFiles=[], sendHistory=[], dlHistory=[];

function switchTab(n) {{
  ['send','receive','notes','devices'].forEach((id,i)=>{{
    document.querySelectorAll('.tab')[i].classList.toggle('active',id===n);
    document.getElementById('panel-'+id).classList.toggle('active',id===n);
  }});
  if(n==='receive') loadLaptopFiles();
  if(n==='notes') loadNotes();
  if(n==='devices') loadDevices();
}}

function icon(name){{
  const e=name.split('.').pop().toLowerCase();
  if(['jpg','jpeg','png','gif','webp','heic','avif','svg'].includes(e)) return '🖼️';
  if(e==='pdf') return '📄';
  if(['mp4','mov','avi','mkv','webm'].includes(e)) return '🎬';
  if(['mp3','wav','aac','flac','m4a'].includes(e)) return '🎵';
  if(['zip','rar','7z','tar','gz'].includes(e)) return '🗜️';
  if(['doc','docx'].includes(e)) return '📝';
  if(['xls','xlsx','csv'].includes(e)) return '📊';
  return '📎';
}}
function fmtSize(b){{if(b<1024)return b+' B';if(b<1048576)return(b/1024).toFixed(1)+' KB';return(b/1048576).toFixed(1)+' MB'}}
function fmtTime(){{return new Date().toLocaleTimeString([],{{hour:'2-digit',minute:'2-digit'}})}}
function toast(msg,err=false){{const t=document.getElementById('toast');t.textContent=msg;t.className='toast'+(err?' err':'')+' show';setTimeout(()=>t.className='toast'+(err?' err':''),3200)}}

function renderFileList(){{
  const el=document.getElementById('fileList');
  el.innerHTML=selectedFiles.map((f,i)=>
    `<div class="file-item"><span class="fi">${{icon(f.name)}}</span><span class="fn">${{f.name}}</span><span class="fs">${{fmtSize(f.size)}}</span><button class="frm" onclick="removeFile(${{i}})">✕</button></div>`
  ).join('');
  document.getElementById('sendBtn').disabled=selectedFiles.length===0;
}}
function removeFile(i){{selectedFiles.splice(i,1);renderFileList()}}
document.getElementById('fileInput').addEventListener('change',function(){{selectedFiles=Array.from(this.files);renderFileList()}});
const dz=document.getElementById('dropZone');
dz.addEventListener('dragover',e=>{{e.preventDefault();dz.classList.add('over')}});
dz.addEventListener('dragleave',()=>dz.classList.remove('over'));
dz.addEventListener('drop',e=>{{e.preventDefault();dz.classList.remove('over');selectedFiles=Array.from(e.dataTransfer.files);renderFileList()}});

async function uploadFiles(){{
  if(!selectedFiles.length) return;
  const fd=new FormData();
  selectedFiles.forEach(f=>fd.append('files',f));
  const pw=document.getElementById('progWrap'),pb=document.getElementById('progBar'),pt=document.getElementById('progTxt');
  pw.classList.add('show');document.getElementById('sendBtn').disabled=true;
  try{{
    await new Promise((res,rej)=>{{
      const xhr=new XMLHttpRequest();xhr.open('POST','/upload');
      xhr.upload.onprogress=e=>{{if(e.lengthComputable){{const p=Math.round(e.loaded/e.total*100);pb.style.width=p+'%';pt.textContent='Uploading '+p+'%';}}}};
      xhr.onload=()=>xhr.status===200?res():rej(new Error('Server error '+xhr.status));
      xhr.onerror=()=>rej(new Error('Network error'));xhr.send(fd);
    }});
    const t=fmtTime();selectedFiles.forEach(f=>sendHistory.unshift({{name:f.name,time:t,icon:icon(f.name)}}));
    renderSendHistory();toast(selectedFiles.length+' file(s) sent!');
    selectedFiles=[];document.getElementById('fileInput').value='';renderFileList();pb.style.width='0';
  }}catch(e){{toast(e.message,true)}}
  finally{{pw.classList.remove('show');document.getElementById('sendBtn').disabled=selectedFiles.length===0}}
}}
function renderSendHistory(){{
  const el=document.getElementById('sendHistory');
  if(!sendHistory.length){{el.innerHTML='<div class="empty">Nothing sent yet</div>';return;}}
  el.innerHTML=sendHistory.map(h=>`<div class="h-item"><span>${{h.icon}}</span><span class="h-name">${{h.name}}</span><span class="badge badge-ok">Sent</span><span class="h-time">${{h.time}}</span></div>`).join('');
}}

async function loadLaptopFiles(){{
  document.getElementById('laptopFiles').innerHTML='<div class="empty"><span class="spin">⟳</span> Loading</div>';
  try{{const r=await fetch('/files');const data=await r.json();renderLaptopFiles(data.files);}}
  catch(e){{document.getElementById('laptopFiles').innerHTML='<div class="empty">⚠️ Could not load files</div>';}}
}}
function renderLaptopFiles(files){{
  const el=document.getElementById('laptopFiles');
  if(!files||!files.length){{el.innerHTML='<div class="empty">No files yet. Send some!</div>';return;}}
  el.innerHTML=files.map(f=>`<div class="lf-item"><span style="font-size:1.3rem">${{icon(f.name)}}</span><div class="lf-info"><div class="lf-name">${{f.name}}</div><div class="lf-meta">${{fmtSize(f.size)}} · ${{f.modified}}</div></div><button class="dl-btn" onclick="downloadFile('${{encodeURIComponent(f.name)}}','${{f.name}}')">Get</button></div>`).join('');
}}
async function downloadFile(encoded,name){{
  toast('Downloading '+name);
  const a=document.createElement('a');a.href='/download/'+encoded;a.download=name;
  document.body.appendChild(a);a.click();document.body.removeChild(a);
  dlHistory.unshift({{name,time:fmtTime(),icon:icon(name)}});renderDlHistory();
}}
function renderDlHistory(){{
  const el=document.getElementById('dlHistory');
  if(!dlHistory.length){{el.innerHTML='<div class="empty">Nothing downloaded yet</div>';return;}}
  el.innerHTML=dlHistory.map(h=>`<div class="h-item"><span>${{h.icon}}</span><span class="h-name">${{h.name}}</span><span class="badge badge-dl">Got</span><span class="h-time">${{h.time}}</span></div>`).join('');
}}

async function sendNote(){{
  const text=document.getElementById('noteInput').value.trim();
  if(!text){{toast('Write something first',true);return;}}
  try{{
    await fetch('/notes',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{text}})}});
    document.getElementById('noteInput').value='';toast('Note sent!');loadNotes();
  }}catch(e){{toast(e.message,true)}}
}}
async function loadNotes(){{
  try{{
    const r=await fetch('/notes');const d=await r.json();
    const el=document.getElementById('notesList');
    if(!d.notes||!d.notes.length){{el.innerHTML='<div class="empty">No notes yet</div>';return;}}
    el.innerHTML=d.notes.map(n=>`<div class="note-item"><div class="note-text">${{escHtml(n.text)}}</div><div class="note-meta">${{n.time}} · ${{n.device}}</div></div>`).join('');
  }}catch(e){{}}
}}

async function loadDevices(){{
  try{{
    const r=await fetch('/devices');const d=await r.json();
    const el=document.getElementById('devicesList');
    if(!d.devices||!d.devices.length){{el.innerHTML='<div class="empty">No devices seen yet</div>';return;}}
    el.innerHTML=d.devices.map(dv=>`<div class="dev-item"><div class="dev-dot"></div><div class="dev-info"><div class="dev-name">${{escHtml(dv.name)}}</div><div class="dev-meta">Last seen ${{dv.last_seen}} · ${{dv.files_sent}} files sent</div></div></div>`).join('');
  }}catch(e){{}}
}}
async function registerName(){{
  const name=document.getElementById('devNameInput').value.trim();
  if(!name){{toast('Enter a name first',true);return;}}
  try{{await fetch('/register',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{name}})}});toast('Name saved!');}}
  catch(e){{toast(e.message,true)}}
}}

function escHtml(s){{return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}
</script>
</body>
</html>"""


# ── HTTP Handler ─────────────────────────────────────────────────
class HTTPHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def client_ip(self):
        return self.client_address[0]

    def do_GET(self):
        path = urllib.parse.unquote(self.path.split("?")[0])
        ip = self.client_ip()
        _register_device(ip)
        try:
            if path in ("/", "/index.html"):
                body = build_html(_shared_state["server_url"]).encode()
                self.respond(200, "text/html; charset=utf-8", body)
            elif path == "/files":
                self.handle_list_files()
            elif path.startswith("/download/"):
                filename = urllib.parse.unquote(path[len("/download/"):])
                self.handle_download(filename)
            elif path == "/notes":
                with _state_lock:
                    notes = list(_shared_state["notes"])
                self.respond(200, "application/json", json.dumps({"notes": notes}).encode())
            elif path == "/devices":
                with _state_lock:
                    devs = [{"name": v["name"], "last_seen": v["last_seen"], "files_sent": v["files_sent"]}
                            for v in _shared_state["devices"].values()]
                self.respond(200, "application/json", json.dumps({"devices": devs}).encode())
            else:
                self.respond(404, "text/plain", b"Not found")
        except Exception as e:
            _log(f"GET error {path}: {e}")
            self.respond(500, "text/plain", str(e).encode())

    def do_POST(self):
        path = self.path
        ip = self.client_ip()
        _register_device(ip)
        try:
            if path == "/upload":
                self.handle_upload(ip)
            elif path == "/notes":
                data = self.read_json()
                text = data.get("text", "").strip()
                if text:
                    entry = {
                        "text": text,
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "device": _shared_state["devices"].get(ip, {}).get("name", ip)
                    }
                    with _state_lock:
                        _shared_state["notes"].insert(0, entry)
                        _shared_state["notes"] = _shared_state["notes"][:50]
                    _log(f"Note from {ip}: {text[:60]!r}")
                    cb = _shared_state.get("log_callback")
                    if cb:
                        cb(f"{entry['time']} ✉ Note: {text[:80]}")
                self.respond(200, "application/json", b'{"ok":true}')
            elif path == "/register":
                data = self.read_json()
                name = data.get("name", "").strip()
                if name:
                    _register_device(ip, name)
                    _log(f"Device {ip} named {name!r}")
                self.respond(200, "application/json", b'{"ok":true}')
            else:
                self.respond(404, "text/plain", b"Not found")
        except Exception as e:
            _log(f"POST error {path}: {e}\n{traceback.format_exc()}")
            self.respond(500, "text/plain", str(e).encode())

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw)

    def handle_list_files(self):
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        files = []
        for p in sorted(SAVE_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.is_file():
                st = p.stat()
                files.append({
                    "name": p.name,
                    "size": st.st_size,
                    "modified": datetime.fromtimestamp(st.st_mtime).strftime("%b %d, %H:%M")
                })
        self.respond(200, "application/json", json.dumps({"files": files}).encode())

    def handle_download(self, filename):
        target = SAVE_DIR / filename
        try:
            target.resolve().relative_to(SAVE_DIR.resolve())
        except ValueError:
            self.respond(403, "text/plain", b"Forbidden")
            return
        if not target.exists() or not target.is_file():
            self.respond(404, "text/plain", b"File not found")
            return
        mime, _ = mimetypes.guess_type(target.name)
        mime = mime or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
        self.end_headers()
        self.wfile.write(data)

    def handle_upload(self, client_ip):
        import cgi
        ct = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ct:
            self.respond(400, "text/plain", b"Bad request: not multipart")
            return
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        fs = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                              environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": ct})
        items = fs["files"] if "files" in fs else []
        if not isinstance(items, list):
            items = [items]
        saved = []
        for f in items:
            if not f.filename:
                continue
            dest = SAVE_DIR / f.filename
            stem, ext, n = dest.stem, dest.suffix, 1
            while dest.exists():
                dest = SAVE_DIR / f"{stem}_{n}{ext}"
                n += 1
            dest.write_bytes(f.file.read())
            saved.append(dest.name)
            _log(f"Saved from {client_ip}: {dest.name}")
            with _state_lock:
                if client_ip in _shared_state["devices"]:
                    _shared_state["devices"][client_ip]["files_sent"] += 1
            cb = _shared_state.get("log_callback")
            if cb:
                cb(f"{datetime.now().strftime('%H:%M:%S')} 📥 {dest.name} ← {client_ip}")
        self.respond(200, "application/json", json.dumps({"saved": saved}).encode())

    def respond(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


# ── Server thread ────────────────────────────────────────────────
class ServerThread(QThread):
    log_signal   = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    ready_signal = pyqtSignal()

    def __init__(self, port):
        super().__init__()
        self.port = port
        self.server = None

    def run(self):
        def log_cb(msg):
            self.log_signal.emit(msg)
        try:
            _shared_state["log_callback"] = log_cb
            http.server.HTTPServer.allow_reuse_address = True
            self.server = http.server.HTTPServer(("0.0.0.0", self.port), HTTPHandler)
            self.ready_signal.emit()
            self.server.serve_forever()
        except OSError as e:
            self.error_signal.emit(f"Cannot bind port {self.port}: {e}")
        except Exception as e:
            self.error_signal.emit(f"Server crashed: {e}\n{traceback.format_exc()}")

# FIXED
    def stop(self):
        if self.server:
            srv = self.server
            self.server = None  # guard against double-stop
            def _do_shutdown():
                try:
                    srv.shutdown()
                except Exception:
                    pass
            threading.Thread(target=_do_shutdown, daemon=True).start()
    

# ── Main Window ──────────────────────────────────────────────────
class LocalDropWindow(QMainWindow):
    def __init__(self, ip, port, url, ip_warn=None):
        super().__init__()
        self.ip = ip
        self.port = port
        self.url = url
        self.ip_warn = ip_warn
        self.server_thread = None
        self._setup_ui()
        if ip_warn:
            self.append_log(ip_warn)
        self.start_server()

    def _setup_ui(self):
        self.setWindowTitle("LocalDrop")
        self.setMinimumSize(420, 600)
        self.resize(440, 660)

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window,     QColor("#0a0a0f"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#e8e8f0"))
        palette.setColor(QPalette.ColorRole.Base,       QColor("#13131a"))
        palette.setColor(QPalette.ColorRole.Text,       QColor("#e8e8f0"))
        palette.setColor(QPalette.ColorRole.Button,     QColor("#1a1a24"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e8e8f0"))
        self.setPalette(palette)

        self.setStyleSheet("""
            QMainWindow, QWidget { background:#0a0a0f; color:#e8e8f0; font-family:'DM Sans',sans-serif; }
            QLabel { background:transparent; }
            QPushButton {
                background:#1a1a24; border:1px solid #2a2a3a; border-radius:9px;
                color:#e8e8f0; padding:7px 14px; font-size:12px; font-weight:600;
            }
            QPushButton:hover { border-color:#7c6dfa; color:#7c6dfa; }
            QPushButton#stopBtn {
                background:rgba(250,109,154,0.12); border-color:rgba(250,109,154,0.4); color:#fa6d9a;
            }
            QPushButton#stopBtn:hover { background:rgba(250,109,154,0.22); }
            QPushButton#restartBtn {
                background:rgba(74,222,128,0.12); border-color:rgba(74,222,128,0.4); color:#4ade80;
            }
            QPushButton#restartBtn:hover { background:rgba(74,222,128,0.22); }
            QPushButton#openBtn {
                background:rgba(124,109,250,0.15); border-color:rgba(124,109,250,0.4); color:#7c6dfa;
            }
            QPushButton#openBtn:hover { background:rgba(124,109,250,0.25); }
            QTextEdit {
                background:#13131a; border:1px solid #2a2a3a; border-radius:9px;
                color:#e8e8f0; font-family:'Courier New',monospace; font-size:11px; padding:7px;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        logo = QLabel("LocalDrop")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("font-size:24px;font-weight:800;color:#7c6dfa;letter-spacing:-1px")
        layout.addWidget(logo)

        tagline = QLabel("Multi-device Files & Notes")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet("color:#6b6b80;font-size:11px;margin-bottom:2px")
        layout.addWidget(tagline)

        self.status_label = QLabel("Starting…")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            background:rgba(124,109,250,0.12); border:1px solid rgba(124,109,250,0.3);
            border-radius:99px; color:#7c6dfa; font-size:12px; font-weight:600; padding:5px 14px;
        """)
        layout.addWidget(self.status_label)

        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setMinimumHeight(190)
        self.qr_label.setStyleSheet("background:#13131a;border:1px solid #2a2a3a;border-radius:14px;padding:10px")
        px = make_qr_pixmap(self.url, 190)
        if px:
            self.qr_label.setPixmap(px)
        else:
            self.qr_label.setText("QR unavailable — install qrcode[pil]")
            self.qr_label.setStyleSheet(self.qr_label.styleSheet() + "color:#6b6b80;font-size:11px")
        layout.addWidget(self.qr_label)

        self.url_label = QLabel(self.url)
        self.url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.url_label.setStyleSheet("""
            background:#1a1a24; border:1px solid #2a2a3a; border-radius:9px;
            color:#e8e8f0; font-family:'Courier New',monospace;
            font-size:14px; font-weight:700; padding:9px;
        """)
        flag = Qt.TextInteractionFlag.TextSelectableByMouse if PYQT == 6 else Qt.TextSelectableByMouse
        self.url_label.setTextInteractionFlags(flag)
        layout.addWidget(self.url_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.open_btn = QPushButton("Open in Browser")
        self.open_btn.setObjectName("openBtn")
        self.open_btn.clicked.connect(self.open_browser)
        btn_row.addWidget(self.open_btn)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.clicked.connect(self.toggle_server)
        btn_row.addWidget(self.stop_btn)
        layout.addLayout(btn_row)

        log_lbl = QLabel("Activity Log")
        log_lbl.setStyleSheet("color:#6b6b80;font-size:10px;font-weight:600;letter-spacing:1px")
        layout.addWidget(log_lbl)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(110)
        layout.addWidget(self.log_view)

        footer = QLabel(f"Saved → ~/LocalDrop_Received   ·   Port {self.port}")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color:#3a3a4a;font-size:10px")
        layout.addWidget(footer)

    def start_server(self):
        _shared_state["server_url"] = self.url
        self.server_thread = ServerThread(self.port)
        self.server_thread.log_signal.connect(self.append_log)
        self.server_thread.ready_signal.connect(self.on_server_ready)
        self.server_thread.error_signal.connect(self.on_server_error)
        self.append_log(f"Binding to 0.0.0.0:{self.port}…")
        self.server_thread.start()

    def on_server_ready(self):
        self.status_label.setText(f"🟢  Live on port {self.port}")
        self.status_label.setStyleSheet("""
            background:rgba(74,222,128,0.12); border:1px solid rgba(74,222,128,0.3);
            border-radius:99px; color:#4ade80; font-size:12px; font-weight:600; padding:5px 14px;
        """)
        self.stop_btn.setText("Stop")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setStyleSheet("")
        self.open_btn.setEnabled(True)
        self.append_log(f"Server live → {self.url}")
        self.append_log(f"Saving to {SAVE_DIR}")

    def on_server_error(self, msg):
        self.status_label.setText("⚠️  Failed")
        self.status_label.setStyleSheet("""
            background:rgba(250,109,154,0.12); border:1px solid rgba(250,109,154,0.3);
            border-radius:99px; color:#fa6d9a; font-size:12px; font-weight:600; padding:5px 14px;
        """)
        self.append_log(f"ERROR: {msg}")
        if sys.platform == "win32":
            self.append_log("Windows: Allow Python in Firewall → Windows Defender Firewall → Allow an app")
        else:
            self.append_log("Run: sudo ufw allow 5005  OR check: lsof -i :5005")
        self._set_restart_mode()

    def toggle_server(self):
        if self.stop_btn.text() == "Stop":
            self._stop_server_async()
        else:
            self._restart_server()

    def _stop_server_async(self):
        self.stop_btn.setEnabled(False)
        self.append_log("Stopping server…")
        if self.server_thread:
            self.server_thread.stop()
        self._poll_stop()

    def _poll_stop(self):
        if self.server_thread and self.server_thread.isRunning():
            QTimer.singleShot(200, self._poll_stop)
        else:
            self.status_label.setText("⏹  Stopped")
            self.status_label.setStyleSheet("""
                background:rgba(250,109,154,0.12); border:1px solid rgba(250,109,154,0.3);
                border-radius:99px; color:#fa6d9a; font-size:12px; font-weight:600; padding:5px 14px;
            """)
            self.open_btn.setEnabled(False)
            self.append_log("Server stopped.")
            self._set_restart_mode()

    def _set_restart_mode(self):
        self.stop_btn.setText("Restart")
        self.stop_btn.setObjectName("restartBtn")
        self.stop_btn.setStyleSheet(
            "background:rgba(74,222,128,0.12);border:1px solid rgba(74,222,128,0.4);"
            "color:#4ade80;border-radius:9px;padding:7px 14px;font-size:12px;font-weight:600;"
        )
        self.stop_btn.setEnabled(True)

    def _restart_server(self):
        self.stop_btn.setEnabled(False)
        self.append_log("Restarting server…")
        self.status_label.setText("⟳  Restarting…")
        self.status_label.setStyleSheet("""
            background:rgba(124,109,250,0.12); border:1px solid rgba(124,109,250,0.3);
            border-radius:99px; color:#7c6dfa; font-size:12px; font-weight:600; padding:5px 14px;
        """)
        if self.server_thread:
            self.server_thread.stop()
        self._poll_restart()
        
    def _poll_restart(self):
        if self.server_thread and self.server_thread.isRunning():
            QTimer.singleShot(200, self._poll_restart)
            return
        new_ip, ip_warn = get_local_ip()
        try:
            new_port = find_free_port(PREFERRED_PORT)
        except OSError:
            new_port = self.port
        self.ip = new_ip
        self.port = new_port
        self.url = f"http://{new_ip}:{new_port}"
        self.url_label.setText(self.url)
        px = make_qr_pixmap(self.url, 190)
        if px:
            self.qr_label.setPixmap(px)
        else:
            self.qr_label.setText("QR unavailable — install qrcode[pil]")
        if ip_warn:
            self.append_log(ip_warn)
        self.append_log(f"New IP detected: {self.url}")
        self.stop_btn.setText("Stop")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setStyleSheet("")
        self.open_btn.setEnabled(True)
        self.server_thread = None
        self.start_server()

    def append_log(self, msg):
        self.log_view.append(msg)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def open_browser(self):
        import webbrowser
        webbrowser.open(self.url)

    def closeEvent(self, event):
        if self.server_thread:
            self.server_thread.stop()
        event.accept()


# ── Entry point ──────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LocalDrop")
    app.setOrganizationName("LocalDrop")
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    ip, ip_warn = get_local_ip()
    try:
        port = find_free_port(PREFERRED_PORT)
    except OSError as e:
        try:
            from PyQt6.QtWidgets import QMessageBox as MB
        except ImportError:
            from PyQt5.QtWidgets import QMessageBox as MB
        MB.critical(None, "LocalDrop Error", str(e))
        sys.exit(1)

    url = f"http://{ip}:{port}"
    window = LocalDropWindow(ip, port, url, ip_warn)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
