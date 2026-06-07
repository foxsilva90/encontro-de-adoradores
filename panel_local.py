#!/usr/bin/env python3
"""AGTv Web Panel — gerenciamento da grade e upload de vídeos."""
import glob
import json
import os
import subprocess
import threading
from datetime import datetime
from flask import (Flask, Response, redirect, render_template_string,
                   request, session, url_for)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("PANEL_SECRET_KEY", "agtv2026secretkey")

PANEL_PASSWORD = os.environ.get("PANEL_PASSWORD", "agtv2026")
VIDEOS_DIR = "/root/webtv/videos"
VIDEOS_RAW_DIR = "/root/webtv/videos_raw"
SCHEDULE_FILE = "/root/webtv/schedule.json"
ENCODE_LOG = "/root/webtv/encode.log"
STATE_FILE = "/root/webtv/now_playing.json"
SCHEDULER_LOG = "/root/webtv/scheduler.log"
ALLOWED_EXT = {".mp4", ".mov", ".avi", ".mkv"}

encode_status = {"running": False, "file": ""}
download_status = {"running": False, "title": ""}
YTDLP_COOKIES = "/root/webtv/cookies.txt"


def download_video_bg(url):
    download_status["running"] = True
    download_status["title"] = url[:50]
    cmd = [
        "nice", "-n", "19",
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-o", os.path.join(VIDEOS_DIR, "%(title)s.mp4"),
    ]
    if os.path.exists(YTDLP_COOKIES):
        cmd += ["--cookies", YTDLP_COOKIES]
    cmd.append(url)
    with open(ENCODE_LOG, "a") as log:
        log.write(f"\n[{datetime.now()}] Downloading: {url}\n")
        subprocess.run(cmd, stdout=log, stderr=log)
        log.write(f"[{datetime.now()}] Download done.\n")
    download_status["running"] = False
    download_status["title"] = ""


def load_config():
    with open(SCHEDULE_FILE) as f:
        return json.load(f)


def save_config(cfg):
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_videos():
    return sorted([os.path.basename(f) for f in glob.glob(f"{VIDEOS_DIR}/*.mp4")])


def stream_status():
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "webtv-scheduler"],
            capture_output=True, text=True)
        return r.stdout.strip()
    except Exception:
        return "unknown"


def encode_video_bg(raw_path, out_name):
    encode_status["running"] = True
    encode_status["file"] = out_name
    out_path = os.path.join(VIDEOS_DIR, out_name)
    cmd = [
        "nice", "-n", "19",
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-i", raw_path,
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "ultrafast", "-profile:v", "high", "-level", "4.0",
        "-b:v", "4500k", "-maxrate", "5000k", "-bufsize", "8000k",
        "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart",
        out_path,
    ]
    with open(ENCODE_LOG, "a") as log:
        log.write(f"\n[{datetime.now()}] Encoding: {out_name}\n")
        subprocess.run(cmd, stdout=log, stderr=log)
        log.write(f"[{datetime.now()}] Done: {out_name}\n")
    encode_status["running"] = False
    subprocess.run(["systemctl", "restart", "webtv-scheduler"], shell=False)


LOGO_PATH = "/root/webtv/logo.jpg"


@app.route("/logo")
def serve_logo():
    if not os.path.exists(LOGO_PATH):
        return Response(status=404)
    ext = os.path.splitext(LOGO_PATH)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    with open(LOGO_PATH, "rb") as f:
        return Response(f.read(), mimetype=mime)


HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AGTv — Painel</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet">
<style>
:root {
  --grad: linear-gradient(90deg, #f7971e, #f44369, #9b27af, #2196f3, #00bcd4);
  --bg: #0a0a0a;
  --sidebar: #111;
  --card: #161616;
  --border: #2a2a2a;
  --text: #e0e0e0;
  --muted: #666;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; display: flex; min-height: 100vh; }

/* SIDEBAR */
.sidebar {
  width: 220px; min-height: 100vh; background: var(--sidebar);
  border-right: 1px solid var(--border); display: flex; flex-direction: column;
  position: fixed; top: 0; left: 0; z-index: 100;
}
.sidebar-logo {
  padding: 24px 20px 16px;
  border-bottom: 1px solid var(--border);
}
.sidebar-logo .ag { font-size: 1.6rem; font-weight: 900; color: #ccc; letter-spacing: -1px; }
.sidebar-logo .tv {
  font-size: 1.6rem; font-weight: 900;
  background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.sidebar-logo .tagline { font-size: .6rem; color: var(--muted); letter-spacing: 3px; margin-top: 2px; }
.sidebar-nav { padding: 12px 0; flex: 1; }
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 20px; color: var(--muted); font-size: .85rem;
  cursor: default; border-left: 3px solid transparent;
}
.nav-item.active {
  color: #fff; border-left-color: #f7971e;
  background: linear-gradient(90deg, rgba(247,151,30,.08), transparent);
}
.nav-item i { font-size: 1rem; }
.sidebar-footer {
  padding: 16px 20px; border-top: 1px solid var(--border);
}
.sidebar-footer a {
  color: var(--muted); font-size: .8rem; text-decoration: none;
  display: flex; align-items: center; gap: 8px;
}
.sidebar-footer a:hover { color: #fff; }

/* MAIN */
.main { margin-left: 220px; flex: 1; display: flex; flex-direction: column; min-height: 100vh; }
.topbar {
  height: 56px; background: var(--sidebar); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; padding: 0 24px; gap: 12px;
  position: sticky; top: 0; z-index: 50;
}
.topbar-title { font-weight: 600; font-size: .95rem; }
.grad-bar { height: 3px; background: var(--grad); }
.content { padding: 24px; }

/* CARDS */
.ag-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden; margin-bottom: 20px;
}
.ag-card-header {
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px;
  font-size: .85rem; font-weight: 600; color: #bbb; text-transform: uppercase; letter-spacing: .5px;
}
.ag-card-header i { background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.ag-card-body { padding: 16px; }

/* STATUS BADGE */
.badge-live {
  display: inline-flex; align-items: center; gap: 6px;
  background: rgba(0,200,83,.12); color: #00c853;
  border: 1px solid rgba(0,200,83,.3); border-radius: 20px;
  padding: 4px 12px; font-size: .8rem; font-weight: 600;
}
.badge-live::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #00c853; animation: pulse 1.5s infinite; }
.badge-stopped {
  display: inline-flex; align-items: center; gap: 6px;
  background: rgba(244,67,54,.1); color: #f44336;
  border: 1px solid rgba(244,67,54,.3); border-radius: 20px;
  padding: 4px 12px; font-size: .8rem; font-weight: 600;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

/* BUTTONS */
.btn-ag {
  background: var(--grad); border: none; color: #fff;
  padding: 6px 16px; border-radius: 6px; font-size: .82rem; cursor: pointer;
}
.btn-ag:hover { opacity: .85; }
.btn-ag-outline {
  background: transparent; border: 1px solid #333; color: #bbb;
  padding: 5px 14px; border-radius: 6px; font-size: .82rem; cursor: pointer;
}
.btn-ag-outline:hover { border-color: #666; color: #fff; }
.btn-danger-xs {
  background: rgba(244,67,54,.15); border: 1px solid rgba(244,67,54,.3);
  color: #f44336; padding: 2px 8px; border-radius: 4px; font-size: .75rem; cursor: pointer;
}
.btn-danger-xs:hover { background: rgba(244,67,54,.3); }

/* TABLE */
.ag-table { width: 100%; border-collapse: collapse; font-size: .83rem; }
.ag-table th { color: var(--muted); font-weight: 600; text-transform: uppercase;
  font-size: .72rem; letter-spacing: .5px; padding: 8px 10px; border-bottom: 1px solid var(--border); }
.ag-table td { padding: 9px 10px; border-bottom: 1px solid #1e1e1e; color: var(--text); vertical-align: middle; }
.ag-table tr:hover td { background: rgba(255,255,255,.02); }
.ag-table .time-badge {
  background: rgba(247,151,30,.12); color: #f7971e;
  border: 1px solid rgba(247,151,30,.25); border-radius: 4px;
  padding: 2px 8px; font-size: .78rem; font-weight: 600; font-family: monospace;
}

/* FORM CONTROLS */
.ag-input, .ag-select {
  background: #1e1e1e; border: 1px solid var(--border); color: var(--text);
  border-radius: 6px; padding: 6px 10px; font-size: .83rem; width: 100%;
}
.ag-input:focus, .ag-select:focus { outline: none; border-color: #f7971e; }
.ag-select option { background: #1e1e1e; }

/* UPLOAD ZONE */
.upload-zone {
  border: 2px dashed var(--border); border-radius: 8px; padding: 20px;
  text-align: center; margin-bottom: 12px; transition: border-color .2s;
}
.upload-zone:hover { border-color: #f7971e; }
.upload-zone input[type=file] { display: none; }
.upload-zone label { cursor: pointer; color: var(--muted); font-size: .85rem; }
.upload-zone label:hover { color: #fff; }
.upload-filename { font-size: .8rem; color: #f7971e; margin-top: 6px; }

/* ENCODE NOTICE */
.encode-notice {
  background: rgba(247,151,30,.08); border: 1px solid rgba(247,151,30,.2);
  border-radius: 6px; padding: 8px 12px; font-size: .8rem; color: #f7971e;
  display: flex; align-items: center; gap: 8px; margin-top: 8px;
}
@keyframes spin { to { transform: rotate(360deg); } }
.spin { display:inline-block; animation: spin 1s linear infinite; }

/* VIDEO LIST */
.video-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: 4px; border-bottom: 1px solid #1a1a1a;
}
.video-item:hover { background: rgba(255,255,255,.03); }
.video-item:last-child { border-bottom: none; }
.video-item .v-num { font-size:.68rem; color:var(--muted); min-width:20px; text-align:right; flex-shrink:0; }
.video-item .v-name { flex:1; font-size:.78rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.video-item input[type=checkbox] { flex-shrink:0; accent-color:var(--orange); width:14px; height:14px; cursor:pointer; }
.video-item.selected { background: rgba(245,163,36,.07); }

/* STATS ROW */
.stat-box {
  background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 16px 20px; text-align: center;
}
.stat-box .stat-val { font-size: 1.8rem; font-weight: 700; background: var(--grad);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.stat-box .stat-label { font-size: .72rem; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; }

/* SIDEBAR COLLAPSE */
.sidebar { transition: width .25s ease; }
.sidebar.collapsed { width: 56px; overflow: hidden; }
.sidebar.collapsed .nav-text,
.sidebar.collapsed .sidebar-logo .tagline,
.sidebar.collapsed .sidebar-footer a span { display: none; }
.sidebar.collapsed .sidebar-logo { padding: 20px 8px; text-align: center; }
.sidebar.collapsed .sidebar-logo .ag,
.sidebar.collapsed .sidebar-logo .tv { font-size: 1.1rem; }
.sidebar.collapsed .nav-item { justify-content: center; padding: 12px 0; }
.sidebar.collapsed .sidebar-footer { padding: 12px 0; text-align: center; }
.sidebar.collapsed .sidebar-footer a { justify-content: center; }
.sidebar.collapsed .btn-collapse i::before { content: "\F284"; }
.main { transition: margin-left .25s ease; }
.btn-collapse {
  background: none; border: none; color: var(--muted); cursor: pointer;
  padding: 2px 6px; font-size: .9rem; margin-left: auto;
}
.btn-collapse:hover { color: #fff; }
.nav-item { cursor: pointer; user-select: none; }
.nav-item:hover { color: #ccc; background: rgba(255,255,255,.03); }

/* MOBILE */
.sidebar-overlay {
  display: none; position: fixed; inset: 0; background: rgba(0,0,0,.65); z-index: 99;
}
.sidebar-overlay.show { display: block; }
.btn-hamburger {
  display: none; background: none; border: none; color: var(--text);
  font-size: 1.3rem; padding: 2px 6px; cursor: pointer; flex-shrink: 0; margin-right: 4px;
}

@media (max-width: 768px) {
  .sidebar {
    transform: translateX(-220px);
    transition: transform .25s ease;
    z-index: 200;
  }
  .sidebar.open { transform: translateX(0); }
  .main { margin-left: 0 !important; }
  .btn-hamburger { display: block; }
  .content { padding: 12px; }
  .topbar { padding: 0 12px; gap: 8px; }
  .stat-box { padding: 12px 6px; }
  .stat-box .stat-val { font-size: 1.4rem; }
  .ag-card-body { padding: 12px; }
  .ag-card-header { padding: 10px 12px; font-size: .78rem; }
  .table-responsive-ag { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .ag-table { min-width: 420px; }
  body.sidebar-open { overflow: hidden; }
}
</style>
</head>
<body>

<div class="sidebar-overlay" id="sidebarOverlay" onclick="closeSidebar()"></div>

<!-- SIDEBAR -->
<div class="sidebar">
  <div class="sidebar-logo" style="display:flex;align-items:center;gap:6px">
    <div style="flex:1"><span class="ag">AG</span><span class="tv">TV</span>
    <div class="tagline">INFORMA &bull; INSPIRA &bull; CONECTA</div></div>
    <button class="btn-collapse" onclick="toggleSidebarCollapse()" id="collapseBtn" title="Recolher menu">
      <i class="bi bi-layout-sidebar-reverse" id="collapseIcon"></i>
    </button>
  </div>
  <nav class="sidebar-nav">
    <div class="nav-item active" id="nav-dashboard" onclick="scrollTo(0,0)"><i class="bi bi-grid-1x2"></i> <span class="nav-text">Dashboard</span></div>
    <div class="nav-item" id="nav-stream" onclick="navTo('section-stream','nav-stream')"><i class="bi bi-broadcast"></i> <span class="nav-text">Stream</span></div>
    <div class="nav-item" id="nav-playlists" onclick="navTo('section-playlists','nav-playlists')"><i class="bi bi-collection-play"></i> <span class="nav-text">Playlists</span></div>
    <div class="nav-item" id="nav-grade" onclick="navTo('section-grade','nav-grade')"><i class="bi bi-calendar3"></i> <span class="nav-text">Grade</span></div>
    <div class="nav-item" id="nav-videos" onclick="navTo('section-videos','nav-videos')"><i class="bi bi-film"></i> <span class="nav-text">Vídeos</span></div>
  </nav>
  <div class="sidebar-footer">
    <a href="/logout"><i class="bi bi-box-arrow-left"></i> <span>Sair</span></a>
  </div>
</div>

<!-- MAIN -->
<div class="main">
  <div class="topbar">
    <button class="btn-hamburger" onclick="toggleSidebar()" aria-label="Menu"><i class="bi bi-list"></i></button>
    <i class="bi bi-broadcast" style="background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-size:1.1rem"></i>
    <span class="topbar-title">AGTv — TV Web</span>
    <div class="ms-auto">
      {% if status == "active" %}
        <span class="badge-live">AO VIVO</span>
      {% else %}
        <span class="badge-stopped">PARADO</span>
      {% endif %}
    </div>
  </div>
  <div class="grad-bar"></div>

  <div class="content">

    <!-- STATS -->
    <div class="row g-3 mb-4">
      <div class="col-6 col-md-3">
        <div class="stat-box">
          <div class="stat-val">{{ videos|length }}</div>
          <div class="stat-label">Videos</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="stat-box">
          <div class="stat-val">{{ schedule|length }}</div>
          <div class="stat-label">Agendados</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="stat-box">
          <div class="stat-val" style="font-size:1.1rem;padding-top:6px">
            {% if status == "active" %}1080p{% else %}---{% endif %}
          </div>
          <div class="stat-label">Qualidade</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="stat-box">
          <div class="stat-val" style="font-size:1rem;padding-top:8px">YouTube</div>
          <div class="stat-label">Destino</div>
        </div>
      </div>
    </div>

    <!-- NOW PLAYING -->
    <div class="ag-card mb-4">
      <div class="ag-card-header"><i class="bi bi-play-circle"></i> Transmitindo Agora</div>
      <div class="ag-card-body d-flex align-items-center gap-3 flex-wrap">
        <div id="np-mode-badge" style="border-radius:20px;padding:4px 14px;font-size:.8rem;font-weight:600;background:rgba(102,102,102,.12);color:#666;border:1px solid rgba(102,102,102,.3)">---</div>
        <div>
          <div id="np-label" style="font-size:.9rem;font-weight:500;color:var(--text)">Carregando...</div>
          <div id="np-since" style="font-size:.72rem;color:var(--muted)"></div>
        </div>
      </div>
    </div>

    <!-- STREAM CONTROL -->
    <div class="ag-card mb-4" id="section-stream">
      <div class="ag-card-header"><i class="bi bi-broadcast"></i> Controle do Stream</div>
      <div class="ag-card-body d-flex align-items-center gap-3 flex-wrap">
        <form method="post" action="/stream/restart">
          <button class="btn-ag"><i class="bi bi-arrow-clockwise"></i> Reiniciar</button>
        </form>
        <form method="post" action="/stream/start">
          <button class="btn-ag-outline"><i class="bi bi-play-fill"></i> Iniciar</button>
        </form>
        <form method="post" action="/stream/stop">
          <button class="btn-ag-outline" style="border-color:#f44336;color:#f44336"><i class="bi bi-stop-fill"></i> Parar</button>
        </form>
        <div id="encodeNotice" class="encode-notice" style="display:none"><i class="bi bi-gear-fill spin"></i> <span id="encodeMsg"></span></div>
      </div>
    </div>

    <!-- PLAYLISTS -->
    <div class="ag-card mb-4" id="section-playlists">
      <div class="ag-card-header" style="justify-content:space-between">
        <span><i class="bi bi-collection-play"></i> Playlists</span>
        <button class="btn-ag" style="font-size:.75rem;padding:4px 12px"
                data-bs-toggle="collapse" data-bs-target="#newPlaylistForm">+ Nova</button>
      </div>
      <div class="collapse" id="newPlaylistForm">
        <div style="padding:12px 16px;border-bottom:1px solid var(--border);background:rgba(255,255,255,.015)">
          <form method="post" action="/playlist/create" class="d-flex gap-2 flex-wrap">
            <input type="text" name="name" class="ag-input" placeholder="Nome da playlist" required style="max-width:280px">
            <button class="btn-ag" style="padding:6px 16px">Criar</button>
          </form>
        </div>
      </div>
      {% if not playlists %}
      <div style="padding:20px;text-align:center;color:var(--muted);font-size:.85rem">
        Nenhuma playlist — crie uma e adicione vídeos para o loop
      </div>
      {% endif %}
      {% for pl in playlists %}
      <div style="border-bottom:1px solid #1a1a1a">
        <div style="padding:10px 16px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <button style="background:none;border:none;color:var(--muted);cursor:pointer;padding:2px 4px;font-size:.9rem"
                  data-bs-toggle="collapse" data-bs-target="#pl-{{ pl.id }}">
            <i class="bi bi-chevron-down"></i>
          </button>
          <span style="flex:1;font-size:.88rem;font-weight:500;min-width:100px">{{ pl.name }}</span>
          <span style="font-size:.75rem;color:var(--muted)">{{ pl.videos|length }} vídeo(s)</span>
          {% if pl.get('shuffle', False) %}
          <span style="font-size:.72rem;color:#9b27af;border:1px solid rgba(155,39,175,.3);border-radius:4px;padding:1px 6px">SHUFFLE</span>
          {% endif %}
          {% if pl.get('avoid_duplicates', False) %}
          <span style="font-size:.72rem;color:#2196f3;border:1px solid rgba(33,150,243,.3);border-radius:4px;padding:1px 6px">SEM REPET.</span>
          {% endif %}
          <span style="font-size:.7rem;color:#555;border:1px solid #2a2a2a;border-radius:4px;padding:1px 6px">W{{ pl.get('weight', 3) }}</span>
          {% if active_playlist == pl.id %}
          <span style="background:rgba(0,200,83,.12);color:#00c853;border:1px solid rgba(0,200,83,.3);border-radius:20px;padding:2px 10px;font-size:.72rem;font-weight:600">ATIVO</span>
          {% else %}
          <form method="post" action="/playlist/set-active">
            <input type="hidden" name="id" value="{{ pl.id }}">
            <button class="btn-ag-outline" style="font-size:.75rem;padding:3px 10px">Ativar</button>
          </form>
          {% endif %}
          <form method="post" action="/playlist/delete" onsubmit="return confirm('Remover playlist {{ pl.name }}?')">
            <input type="hidden" name="id" value="{{ pl.id }}">
            <button class="btn-danger-xs">remover</button>
          </form>
        </div>
        <div class="collapse" id="pl-{{ pl.id }}">
          <div style="padding:8px 16px 12px 16px;background:rgba(0,0,0,.2)">
            <div class="d-flex gap-2 mb-3 flex-wrap align-items-center">
              <form method="post" action="/playlist/add-video" class="d-flex gap-2 flex-wrap flex-grow-1">
                <input type="hidden" name="id" value="{{ pl.id }}">
                <select name="video" class="ag-select" style="max-width:320px" required>
                  <option value="">Selecionar vídeo para adicionar...</option>
                  {% for v in videos %}{% if v not in pl.videos %}
                  <option value="{{ v }}">{{ v }}</option>
                  {% endif %}{% endfor %}
                </select>
                <button class="btn-ag" style="font-size:.78rem;padding:5px 12px">Adicionar</button>
              </form>
              <form method="post" action="/playlist/toggle-shuffle">
                <input type="hidden" name="id" value="{{ pl.id }}">
                <button class="btn-ag-outline" style="font-size:.75rem;padding:4px 10px{% if pl.get('shuffle', False) %};border-color:#9b27af;color:#9b27af{% endif %}">
                  <i class="bi bi-shuffle"></i> Shuffle {% if pl.get('shuffle', False) %}ON{% else %}OFF{% endif %}
                </button>
              </form>
              <form method="post" action="/playlist/toggle-avoid-duplicates">
                <input type="hidden" name="id" value="{{ pl.id }}">
                <button class="btn-ag-outline" style="font-size:.75rem;padding:4px 10px{% if pl.get('avoid_duplicates', False) %};border-color:#2196f3;color:#2196f3{% endif %}" title="Evita repetir vídeos recentes ao reiniciar o loop">
                  <i class="bi bi-skip-forward"></i> Sem repet. {% if pl.get('avoid_duplicates', False) %}ON{% else %}OFF{% endif %}
                </button>
              </form>
              <form method="post" action="/playlist/set-weight" class="d-flex align-items-center gap-1">
                <input type="hidden" name="id" value="{{ pl.id }}">
                <label style="font-size:.75rem;color:var(--muted);white-space:nowrap">Peso</label>
                <input type="number" name="weight" min="1" max="10" value="{{ pl.get('weight', 3) }}"
                       class="ag-input" style="width:52px;padding:4px 6px;font-size:.8rem" title="1–10: playlists com maior peso tocam mais (futuro)">
                <button class="btn-ag-outline" style="font-size:.75rem;padding:4px 8px">OK</button>
              </form>
            </div>
            {% if pl.videos %}
            <div class="table-responsive-ag">
            <table class="ag-table" style="min-width:0">
              <tbody>
                {% for v in pl.videos %}
                <tr>
                  <td style="font-size:.78rem">{{ loop.index }}. {{ v }}</td>
                  <td style="width:52px;text-align:center">
                    <div style="display:flex;gap:2px;justify-content:center">
                      <form method="post" action="/playlist/move-video">
                        <input type="hidden" name="id" value="{{ pl.id }}">
                        <input type="hidden" name="video" value="{{ v }}">
                        <input type="hidden" name="direction" value="up">
                        <button class="btn-ag-outline" style="padding:1px 6px;font-size:.75rem;line-height:1.4">↑</button>
                      </form>
                      <form method="post" action="/playlist/move-video">
                        <input type="hidden" name="id" value="{{ pl.id }}">
                        <input type="hidden" name="video" value="{{ v }}">
                        <input type="hidden" name="direction" value="down">
                        <button class="btn-ag-outline" style="padding:1px 6px;font-size:.75rem;line-height:1.4">↓</button>
                      </form>
                    </div>
                  </td>
                  <td style="width:70px;text-align:right">
                    <form method="post" action="/playlist/remove-video">
                      <input type="hidden" name="id" value="{{ pl.id }}">
                      <input type="hidden" name="video" value="{{ v }}">
                      <button class="btn-danger-xs">remover</button>
                    </form>
                  </td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
            </div>
            {% else %}
            <div style="font-size:.78rem;color:var(--muted)">Nenhum vídeo nesta playlist</div>
            {% endif %}

            <!-- AGENDAMENTO DA PLAYLIST -->
            {% set ps = playlist_schedules.get(pl.id) %}
            <div style="border-top:1px solid #1e1e1e;margin-top:10px;padding-top:10px">
              <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                <button class="btn-ag-outline" style="font-size:.73rem;padding:3px 10px"
                        data-bs-toggle="collapse" data-bs-target="#plsched-{{ pl.id }}">
                  <i class="bi bi-calendar3"></i> Agendar
                </button>
                {% if ps %}
                <span style="font-size:.72rem;color:#f7971e">
                  {{ ps.time }} &bull; {{ ps.get('duration',60) }}min &bull;
                  {% if ps.get('recurrence','daily') == 'weekly' %}
                    {% set dnames = ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'] %}
                    {% for d in ps.get('days',[]) %}{{ dnames[d] }}{% if not loop.last %} {% endif %}{% endfor %}
                  {% elif ps.get('recurrence') == 'once' %}{{ ps.get('date','') }}
                  {% else %}Diário{% endif %}
                </span>
                {% endif %}
              </div>
              <div class="collapse{% if ps %} show{% endif %}" id="plsched-{{ pl.id }}" style="padding-top:10px">
                <form method="post" action="/playlist/set-schedule">
                  <input type="hidden" name="id" value="{{ pl.id }}">
                  <div class="d-flex gap-2 flex-wrap align-items-end">
                    <div>
                      <label style="font-size:.72rem;color:var(--muted);display:block;margin-bottom:2px">Horário</label>
                      <input type="time" name="time" class="ag-input" value="{{ ps.time if ps else '' }}" required style="width:110px">
                    </div>
                    <div>
                      <label style="font-size:.72rem;color:var(--muted);display:block;margin-bottom:2px">Duração</label>
                      <select name="duration" class="ag-select" style="width:90px">
                        {% for v,l in [('30','30min'),('60','1h'),('90','1h30'),('120','2h'),('180','3h'),('240','4h')] %}
                        <option value="{{ v }}"
                          {% if ps and ps.get('duration',60)|string == v %}selected
                          {% elif not ps and v == '60' %}selected{% endif %}>{{ l }}</option>
                        {% endfor %}
                      </select>
                    </div>
                    <div>
                      <label style="font-size:.72rem;color:var(--muted);display:block;margin-bottom:2px">Repetição</label>
                      <select name="recurrence" class="ag-select" style="width:110px"
                              onchange="togglePlSched(this,'{{ pl.id }}')">
                        <option value="daily" {% if not ps or ps.get('recurrence','daily')=='daily' %}selected{% endif %}>Diário</option>
                        <option value="weekly" {% if ps and ps.get('recurrence')=='weekly' %}selected{% endif %}>Semanal</option>
                        <option value="once" {% if ps and ps.get('recurrence')=='once' %}selected{% endif %}>Uma vez</option>
                      </select>
                    </div>
                  </div>
                  <div id="plsd-{{ pl.id }}" style="margin-top:8px;display:{% if ps and ps.get('recurrence')=='weekly' %}flex{% else %}none{% endif %};gap:10px;flex-wrap:wrap">
                    {% for dval,dlabel in [('0','Seg'),('1','Ter'),('2','Qua'),('3','Qui'),('4','Sex'),('5','Sáb'),('6','Dom')] %}
                    <label style="font-size:.75rem;cursor:pointer;color:var(--muted);display:flex;align-items:center;gap:3px">
                      <input type="checkbox" name="days" value="{{ dval }}"
                        {% if ps and ps.get('recurrence')=='weekly' and dval|int in ps.get('days',[]) %}checked{% endif %}>{{ dlabel }}
                    </label>
                    {% endfor %}
                  </div>
                  <div id="plsdate-{{ pl.id }}" style="margin-top:8px;display:{% if ps and ps.get('recurrence')=='once' %}block{% else %}none{% endif %}">
                    <input type="date" name="date" class="ag-input" style="width:auto;display:inline-block"
                           value="{{ ps.get('date','') if ps else '' }}">
                  </div>
                  <div class="d-flex gap-2 mt-2">
                    <button type="submit" class="btn-ag" style="font-size:.75rem;padding:4px 12px">Salvar</button>
                  </div>
                </form>
                {% if ps %}
                <form method="post" action="/playlist/remove-schedule" style="margin-top:6px">
                  <input type="hidden" name="id" value="{{ pl.id }}">
                  <button class="btn-danger-xs" style="font-size:.73rem;padding:3px 8px">Remover agendamento</button>
                </form>
                {% endif %}
              </div>
            </div>

          </div>
        </div>
      </div>
      {% endfor %}
    </div>

    <div class="row">
      <!-- GRADE -->
      <div class="col-lg-7 mb-4" id="section-grade">
        <div class="ag-card" style="overflow:visible">
          <div class="ag-card-header"><i class="bi bi-calendar3"></i> Grade de Programacao</div>
          <div class="ag-card-body">
            <div class="table-responsive-ag">
            <table class="ag-table">
              <thead><tr><th>Início</th><th>Fim</th><th>Repetição</th><th>Programa</th><th>Arquivo</th><th></th></tr></thead>
              <tbody>
                {% for i, item in schedule %}
                <tr>
                  <td><span class="time-badge">{{ item.time }}</span></td>
                  <td>
                    {% set h = item.time.split(':')[0]|int %}
                    {% set m = item.time.split(':')[1]|int %}
                    {% set dur = item.get('duration', 120) %}
                    {% set etotal = h*60 + m + dur %}
                    {% set eh = (etotal // 60) % 24 %}
                    {% set em = etotal % 60 %}
                    <span class="time-badge" style="opacity:.6">{{ '%02d'|format(eh) }}:{{ '%02d'|format(em) }}</span>
                  </td>
                  <td style="font-size:.72rem">
                    {% set rec = item.get('recurrence','daily') %}
                    {% if rec == 'once' %}
                      <span style="color:#f7971e">{{ item.get('date','?') }}</span>
                    {% elif rec == 'weekly' %}
                      {% set dnames = ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'] %}
                      <span style="color:#9b27af">{% for d in item.get('days',[]) %}{{ dnames[d] }}{% if not loop.last %} {% endif %}{% endfor %}</span>
                    {% else %}
                      <span style="color:var(--muted)">Diário</span>
                    {% endif %}
                  </td>
                  <td>{{ item.label }}</td>
                  <td style="color:var(--muted);font-size:.78rem">
                    {% if item.get('playlist_id') %}<span style="color:#9b27af">playlist</span>
                    {% else %}{{ item.get('file','').split("/")[-1] }}{% endif %}
                  </td>
                  <td>
                    <form method="post" action="/schedule/delete">
                      <input type="hidden" name="index" value="{{ i }}">
                      <button class="btn-danger-xs">remover</button>
                    </form>
                  </td>
                </tr>
                {% endfor %}
                {% if not schedule %}
                <tr><td colspan="4" style="color:var(--muted);text-align:center;padding:20px">
                  Nenhum programa agendado — loop continuo ativo
                </td></tr>
                {% endif %}
              </tbody>
            </table>
            </div>
            <div style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px">
              <div style="font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Timeline 24h</div>
              <div id="schedTimeline" style="position:relative;height:30px;background:#0d0d0d;border-radius:5px;border:1px solid var(--border);overflow:hidden"></div>
            </div>

            <div style="border-top:1px solid var(--border);margin-top:14px;padding-top:16px">
              <div style="font-size:.78rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">Adicionar programa</div>
              <form method="post" action="/schedule/add">
                <div class="row g-2 align-items-end">
                  <div class="col-4 col-md-2">
                    <input type="time" name="time" class="ag-input" required>
                  </div>
                  <div class="col-4 col-md-2">
                    <select name="duration" class="ag-select" title="Duração">
                      <option value="30">30 min</option>
                      <option value="60">1h</option>
                      <option value="90">1h30</option>
                      <option value="120" selected>2h</option>
                      <option value="180">3h</option>
                      <option value="240">4h</option>
                    </select>
                  </div>
                  <div class="col-4 col-md-3">
                    <input type="text" name="label" class="ag-input" placeholder="Nome do programa" required>
                  </div>
                  <div class="col-12 mt-1">
                    <div class="d-flex gap-3 align-items-center flex-wrap">
                      <select id="recurrenceType" name="recurrence" class="ag-select" style="width:auto;font-size:.78rem" onchange="toggleRecurrence(this.value)">
                        <option value="daily">🔁 Diário</option>
                        <option value="weekly">📅 Semanal</option>
                        <option value="once">1️⃣ Uma vez</option>
                      </select>
                      <div id="weekdayPicker" style="display:none" class="d-flex gap-2 flex-wrap">
                        {% for dval, dlabel in [('0','Seg'),('1','Ter'),('2','Qua'),('3','Qui'),('4','Sex'),('5','Sáb'),('6','Dom')] %}
                        <label style="font-size:.75rem;cursor:pointer;color:var(--muted);display:flex;align-items:center;gap:3px">
                          <input type="checkbox" name="days" value="{{ dval }}"> {{ dlabel }}
                        </label>
                        {% endfor %}
                      </div>
                      <input type="date" id="onceDatePicker" name="date" class="ag-input" style="display:none;width:auto;font-size:.8rem">
                    </div>
                  </div>
                  <div class="col-12 col-md-3" style="position:relative">
                    <input type="text" id="gradeSearch" class="ag-input" placeholder="Pesquisar vídeo..."
                           autocomplete="off" oninput="filterGradeVideos(this.value)"
                           onfocus="openGradeDD()" onblur="setTimeout(closeGradeDD,200)">
                    <input type="hidden" name="file" id="gradeVideoValue" required>
                    <div id="gradeDropdown" style="display:none;position:absolute;top:100%;left:0;right:0;z-index:9999;background:#1e1e1e;border:1px solid var(--border);border-radius:0 0 6px 6px;max-height:200px;overflow-y:auto;box-shadow:0 8px 24px rgba(0,0,0,.7)"></div>
                  </div>
                  <div class="col-12 col-md-2" style="flex-shrink:0">
                    <button class="btn-ag w-100" style="padding:8px">Adicionar</button>
                  </div>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>

      <!-- VIDEOS -->
      <div class="col-lg-5 mb-4" id="section-videos">
        <div class="ag-card">
          <div class="ag-card-header"><i class="bi bi-film"></i> Videos ({{ videos|length }})</div>
          <div class="ag-card-body">
            <form method="post" action="/upload" enctype="multipart/form-data" id="uploadForm">
              <div class="upload-zone" id="uploadZone">
                <input type="file" name="video" id="fileInput" accept="video/*" required onchange="showName(this)">
                <label for="fileInput">
                  <i class="bi bi-cloud-upload" style="font-size:1.5rem;display:block;margin-bottom:6px"></i>
                  Clique para selecionar video
                </label>
                <div class="upload-filename" id="uploadName"></div>
              </div>
              <button class="btn-ag w-100" style="width:100%;padding:8px">Fazer Upload</button>
              <div style="font-size:.75rem;color:var(--muted);margin-top:6px;text-align:center">
                Sera encodado em 1080p automaticamente (~10 min)
              </div>
            </form>
            <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">
              <form method="post" action="/video/download-url" class="d-flex gap-2 flex-wrap">
                <input type="url" name="url" class="ag-input" placeholder="URL do YouTube (https://youtu.be/...)" required
                       style="flex:1;min-width:180px" {% if download_running %}disabled{% endif %}>
                <button class="btn-ag" style="padding:8px 14px;white-space:nowrap" {% if download_running %}disabled{% endif %}>
                  <i class="bi bi-download"></i> Baixar
                </button>
              </form>
              <div style="font-size:.75rem;color:var(--muted);margin-top:4px">Baixa direto do YouTube sem re-encode</div>
              {% if download_running %}
              <div class="encode-notice"><i class="bi bi-arrow-repeat spin"></i> Baixando: {{ download_title }}</div>
              {% endif %}
            </div>
            <div style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px">
              <div class="d-flex align-items-center gap-2 mb-2">
                <input type="text" id="videoSearch" class="ag-input" placeholder="Pesquisar vídeo..."
                       style="flex:1;font-size:.8rem;padding:5px 10px" oninput="filterVideos(this.value)">
                <span id="videoCount" style="font-size:.72rem;color:var(--muted);white-space:nowrap">{{ videos|length }} vídeos</span>
              </div>
              <div class="d-flex align-items-center gap-2 mb-2" id="bulkBar">
                <label style="font-size:.75rem;color:var(--muted);display:flex;align-items:center;gap:5px;cursor:pointer">
                  <input type="checkbox" id="selectAllCb" onchange="toggleSelectAll(this)" style="accent-color:var(--orange);width:14px;height:14px">
                  Selecionar tudo
                </label>
                <form method="post" action="/videos/delete-bulk" id="bulkDeleteForm" style="margin:0" onsubmit="return confirmBulk()">
                  <input type="hidden" name="filenames" id="bulkFilenames">
                  <button type="submit" class="btn-danger-xs" id="bulkDeleteBtn" style="display:none;font-size:.72rem;padding:3px 10px">
                    Excluir selecionados (<span id="bulkCount">0</span>)
                  </button>
                </form>
              </div>
              <div style="max-height:320px;overflow-y:auto" id="videoList">
                {% for v in videos %}
                <div class="video-item" data-name="{{ v|lower }}">
                  <input type="checkbox" class="video-cb" value="{{ v }}" onchange="onCbChange()">
                  <span class="v-num">{{ loop.index }}</span>
                  <span class="v-name" title="{{ v }}" ondblclick="startRename(this,'{{ v }}')" style="cursor:pointer">{{ v }}</span>
                  <form method="post" action="/videos/rename" class="rename-form" style="display:none;flex:1">
                    <input type="hidden" name="old_name" value="{{ v }}">
                    <input type="text" name="new_name" class="ag-input" style="font-size:.75rem;padding:2px 6px;width:100%" value="{{ v|replace('.mp4','') }}">
                    <button type="submit" style="font-size:.7rem;padding:2px 8px;background:#F5A324;color:#000;font-weight:700;border:none;border-radius:3px;cursor:pointer;white-space:nowrap">OK</button>
                    <button type="button" onclick="cancelRename(this)" style="font-size:.7rem;padding:2px 8px;background:#555;color:#fff;border:none;border-radius:3px;cursor:pointer">✕</button>
                  </form>
                  <form method="post" action="/videos/delete" style="flex-shrink:0">
                    <input type="hidden" name="filename" value="{{ v }}">
                    <button class="btn-danger-xs" onclick="return confirm('Remover {{ v }}?')">✕</button>
                  </form>
                </div>
                {% endfor %}
              </div>
              <div id="videoNoResult" style="display:none;text-align:center;color:var(--muted);font-size:.82rem;padding:14px">Nenhum vídeo encontrado</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- LOG -->
    <div class="ag-card mb-4">
      <div class="ag-card-header" style="justify-content:space-between;cursor:pointer"
           data-bs-toggle="collapse" data-bs-target="#logSection">
        <span><i class="bi bi-terminal"></i> Log do Scheduler</span>
        <i class="bi bi-chevron-down" style="font-size:.8rem;color:var(--muted)"></i>
      </div>
      <div class="collapse" id="logSection">
        <pre id="logOutput" style="margin:0;background:#080808;padding:14px 16px;font-size:.7rem;color:#6a9955;max-height:260px;overflow-y:auto;font-family:monospace;line-height:1.5;border-top:1px solid var(--border)">Abrindo log...</pre>
      </div>
    </div>

  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
function toggleRecurrence(val) {
  document.getElementById('weekdayPicker').style.display = val === 'weekly' ? 'flex' : 'none';
  document.getElementById('onceDatePicker').style.display = val === 'once' ? 'inline-block' : 'none';
}
function togglePlSched(sel, pid) {
  var v = sel.value;
  document.getElementById('plsd-'+pid).style.display = v==='weekly'?'flex':'none';
  document.getElementById('plsdate-'+pid).style.display = v==='once'?'block':'none';
}

// Sidebar collapse
var _sidebarCollapsed = false;
function toggleSidebarCollapse() {
  _sidebarCollapsed = !_sidebarCollapsed;
  document.querySelector('.sidebar').classList.toggle('collapsed', _sidebarCollapsed);
  document.querySelector('.main').style.marginLeft = _sidebarCollapsed ? '56px' : '220px';
  document.getElementById('collapseIcon').className = _sidebarCollapsed ? 'bi bi-layout-sidebar' : 'bi bi-layout-sidebar-reverse';
}

// Sidebar navigation
function navTo(sectionId, navId) {
  document.querySelectorAll('.nav-item').forEach(function(el){ el.classList.remove('active'); });
  var navEl = document.getElementById(navId);
  if (navEl) navEl.classList.add('active');
  var section = document.getElementById(sectionId);
  if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  if (window.innerWidth <= 768) closeSidebar();
}

// Grade video searchable dropdown
var _allGradeVideos = [{% for v in videos %}{"v":"/root/webtv/videos/{{ v|replace('\\','\\\\') }}","t":"{{ v|replace('"','\\"') }}"},{% endfor %}];
function _buildGradeDD(items) {
  var dd = document.getElementById('gradeDropdown');
  dd.innerHTML = '';
  if (!items.length) {
    dd.innerHTML = '<div style="padding:8px 12px;color:var(--muted);font-size:.8rem">Nenhum vídeo encontrado</div>';
    return;
  }
  items.forEach(function(item) {
    var el = document.createElement('div');
    el.style.cssText = 'padding:7px 12px;font-size:.78rem;cursor:pointer;border-bottom:1px solid #1a1a1a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis';
    el.textContent = item.t;
    el.title = item.t;
    el.onmouseenter = function(){ this.style.background='rgba(255,255,255,.06)'; };
    el.onmouseleave = function(){ this.style.background=''; };
    el.onmousedown = function() {
      document.getElementById('gradeSearch').value = item.t;
      document.getElementById('gradeVideoValue').value = item.v;
      closeGradeDD();
    };
    dd.appendChild(el);
  });
}
function openGradeDD() {
  var q = document.getElementById('gradeSearch').value.toLowerCase().trim();
  var filtered = q ? _allGradeVideos.filter(function(v){ return v.t.toLowerCase().includes(q); }) : _allGradeVideos;
  _buildGradeDD(filtered);
  document.getElementById('gradeDropdown').style.display = 'block';
}
function closeGradeDD() { document.getElementById('gradeDropdown').style.display = 'none'; }
function filterGradeVideos(q) {
  q = q.toLowerCase().trim();
  var filtered = q ? _allGradeVideos.filter(function(v){ return v.t.toLowerCase().includes(q); }) : _allGradeVideos;
  _buildGradeDD(filtered);
  document.getElementById('gradeDropdown').style.display = 'block';
}

function filterVideos(q) {
  var items = document.querySelectorAll('.video-item');
  q = q.toLowerCase().trim();
  var visible = 0;
  items.forEach(function(el) {
    var match = !q || el.dataset.name.includes(q);
    el.style.display = match ? 'flex' : 'none';
    if (match) visible++;
  });
  document.getElementById('videoNoResult').style.display = visible ? 'none' : 'block';
  document.getElementById('videoCount').textContent = visible + ' vídeo' + (visible !== 1 ? 's' : '');
  onCbChange();
}
function toggleSelectAll(cb) {
  var cbs = document.querySelectorAll('.video-cb');
  cbs.forEach(function(c) {
    var item = c.closest('.video-item');
    if (item && item.style.display !== 'none') {
      c.checked = cb.checked;
      item.classList.toggle('selected', cb.checked);
    }
  });
  onCbChange();
}
function onCbChange() {
  var checked = document.querySelectorAll('.video-cb:checked');
  var btn = document.getElementById('bulkDeleteBtn');
  var countEl = document.getElementById('bulkCount');
  var n = checked.length;
  btn.style.display = n > 0 ? 'inline-block' : 'none';
  countEl.textContent = n;
  checked.forEach(function(c) { c.closest('.video-item').classList.add('selected'); });
  document.querySelectorAll('.video-cb:not(:checked)').forEach(function(c) {
    c.closest('.video-item').classList.remove('selected');
  });
  var allCb = document.getElementById('selectAllCb');
  var visible = document.querySelectorAll('.video-item:not([style*="none"]) .video-cb');
  allCb.indeterminate = n > 0 && n < visible.length;
  allCb.checked = visible.length > 0 && n === visible.length;
}
function startRename(nameEl, filename) {
  var item = nameEl.closest('.video-item');
  nameEl.style.display = 'none';
  var form = item.querySelector('.rename-form');
  form.style.display = 'flex';
  form.style.gap = '4px';
  form.style.alignItems = 'center';
  form.style.flex = '1';
  form.querySelector('input[name=new_name]').focus();
}
function cancelRename(btn) {
  var item = btn.closest('.video-item');
  item.querySelector('.rename-form').style.display = 'none';
  item.querySelector('.v-name').style.display = '';
}
function confirmBulk() {
  var checked = document.querySelectorAll('.video-cb:checked');
  if (!checked.length) return false;
  var names = Array.from(checked).map(function(c){ return c.value; });
  if (!confirm('Excluir ' + names.length + ' vídeo(s)? Essa ação não pode ser desfeita.')) return false;
  document.getElementById('bulkFilenames').value = JSON.stringify(names);
  return true;
}
function showName(input) {
  document.getElementById('uploadName').textContent = input.files[0] ? input.files[0].name : '';
}
function toggleSidebar() {
  var s = document.querySelector('.sidebar');
  var o = document.getElementById('sidebarOverlay');
  var open = s.classList.toggle('open');
  o.classList.toggle('show', open);
  document.body.classList.toggle('sidebar-open', open);
}
function closeSidebar() {
  document.querySelector('.sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('show');
  document.body.classList.remove('sidebar-open');
}

// Now Playing
var modeStyles = {
  live:      {bg:'rgba(0,200,83,.12)',   color:'#00c853', border:'rgba(0,200,83,.3)',   label:'AO VIVO'},
  scheduled: {bg:'rgba(33,150,243,.12)', color:'#2196f3', border:'rgba(33,150,243,.3)', label:'PROGRAMADO'},
  loop:      {bg:'rgba(155,39,175,.12)', color:'#9b27af', border:'rgba(155,39,175,.3)', label:'LOOP'},
  unknown:   {bg:'rgba(102,102,102,.12)',color:'#666',    border:'rgba(102,102,102,.3)',label:'---'}
};
function updateNowPlaying() {
  fetch('/api/now-playing').then(function(r){return r.json();}).then(function(d) {
    var s = modeStyles[d.mode] || modeStyles.unknown;
    var b = document.getElementById('np-mode-badge');
    b.style.background = s.bg; b.style.color = s.color;
    b.style.border = '1px solid '+s.border;
    b.textContent = s.label;
    document.getElementById('np-label').textContent = d.label || '---';
    document.getElementById('np-since').textContent = d.since ? 'desde ' + d.since.replace('T',' ') : '';
  }).catch(function(){});
}
setInterval(updateNowPlaying, 5000);
updateNowPlaying();

// Log viewer
var logOpen = false;
var logEl = document.getElementById('logSection');
if (logEl) {
  logEl.addEventListener('show.bs.collapse', function() { logOpen = true; updateLog(); });
  logEl.addEventListener('hide.bs.collapse', function() { logOpen = false; });
}
function updateLog() {
  if (!logOpen) return;
  fetch('/api/log').then(function(r){return r.json();}).then(function(d) {
    var pre = document.getElementById('logOutput');
    pre.textContent = d.lines.join('');
    pre.scrollTop = pre.scrollHeight;
  }).catch(function(){});
}
setInterval(function(){ if(logOpen) updateLog(); }, 3000);

// Timeline 24h
function drawTimeline() {
  var el = document.getElementById('schedTimeline');
  if (!el) return;
  var items = [{% for i, item in schedule %}{"t":"{{ item.time }}","l":"{{ item.label|replace('"','') }}"},{% endfor %}];
  var html = '';
  for (var h = 0; h < 24; h += 3) {
    var pct = (h / 24 * 100).toFixed(2);
    html += '<div style="position:absolute;left:'+pct+'%;top:0;bottom:0;border-left:1px solid #1a1a1a;padding-left:2px;font-size:.55rem;color:#333;padding-top:2px">'+('0'+h).slice(-2)+'h</div>';
  }
  items.forEach(function(item) {
    var p = item.t.split(':');
    var mins = parseInt(p[0])*60 + parseInt(p[1]);
    var pct = (mins / 1440 * 100).toFixed(2);
    html += '<div style="position:absolute;left:'+pct+'%;top:5px;bottom:5px;min-width:8px;width:2.5%;background:linear-gradient(90deg,#f7971e,#f44369);border-radius:3px" title="'+item.t+' — '+item.l+'"></div>';
  });
  el.innerHTML = html || '<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:.7rem;color:#333">Sem programas agendados</div>';
}
drawTimeline();
window.addEventListener('resize', drawTimeline);

// Encode/Download status polling
var _encWas = false;
var _dlWas = false;
function pollEncodeStatus() {
  fetch('/api/encode-status').then(function(r){return r.json();}).then(function(d) {
    var notice = document.getElementById('encodeNotice');
    var msg = document.getElementById('encodeMsg');
    if (d.running) {
      msg.textContent = 'Encodando: ' + d.file;
      notice.style.display = 'flex';
      notice.style.color = '#f7971e';
      _encWas = true;
    } else if (d.download_running) {
      msg.textContent = 'Baixando: ' + d.download_title;
      notice.style.display = 'flex';
      notice.style.color = '#f7971e';
      _dlWas = true;
    } else {
      if (_encWas) {
        msg.textContent = 'Encode concluido! Video disponivel.';
        notice.style.color = '#00c853';
        notice.style.display = 'flex';
        notice.querySelector('i').className = 'bi bi-check-circle-fill';
        setTimeout(function(){ notice.style.display='none'; _encWas=false; }, 6000);
      } else if (_dlWas) {
        msg.textContent = 'Download concluido! Video disponivel.';
        notice.style.color = '#00c853';
        notice.style.display = 'flex';
        notice.querySelector('i').className = 'bi bi-check-circle-fill';
        setTimeout(function(){ notice.style.display='none'; _dlWas=false; location.reload(); }, 4000);
      } else {
        notice.style.display = 'none';
      }
    }
  }).catch(function(){});
}
setInterval(pollEncodeStatus, 3000);
pollEncodeStatus();
</script>
</body>
</html>"""

LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>AGTv — Login</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
:root { --grad: linear-gradient(90deg,#f7971e,#f44369,#9b27af,#2196f3,#00bcd4); }
body { margin:0; background:#0a0a0a; display:flex; align-items:center; justify-content:center; min-height:100vh; }
.login-card {
  background:#111; border:1px solid #222; border-radius:12px;
  padding:40px 36px; width:340px;
}
.logo-wrap { text-align:center; margin-bottom:32px; }
.logo-wrap .ag { font-size:2.2rem; font-weight:900; color:#ccc; letter-spacing:-1px; }
.logo-wrap .tv {
  font-size:2.2rem; font-weight:900;
  background:var(--grad); -webkit-background-clip:text; -webkit-text-fill-color:transparent;
}
.logo-wrap .tagline { font-size:.6rem; color:#444; letter-spacing:3px; margin-top:4px; }
.ag-input {
  width:100%; background:#1a1a1a; border:1px solid #2a2a2a; color:#e0e0e0;
  border-radius:8px; padding:10px 14px; font-size:.9rem; margin-bottom:16px;
}
.ag-input:focus { outline:none; border-color:#f7971e; }
.btn-login {
  width:100%; padding:10px; border:none; border-radius:8px; font-size:.9rem;
  font-weight:600; cursor:pointer; background:var(--grad); color:#fff;
}
.btn-login:hover { opacity:.85; }
.err { background:rgba(244,67,54,.1); border:1px solid rgba(244,67,54,.3);
  color:#f44336; border-radius:6px; padding:8px 12px; font-size:.83rem; margin-bottom:14px; }
.grad-line { height:3px; background:var(--grad); border-radius:12px 12px 0 0; margin:-40px -36px 32px; }
</style>
</head>
<body>
<div class="login-card">
  <div class="grad-line"></div>
  <div class="logo-wrap">
    <div><span class="ag">AG</span><span class="tv">TV</span></div>
    <div class="tagline">INFORMA &bull; INSPIRA &bull; CONECTA</div>
  </div>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  <form method="post">
    <input type="password" name="password" class="ag-input" placeholder="Senha de acesso" autofocus required>
    <button class="btn-login">Entrar</button>
  </form>
</div>
</body>
</html>"""


def get_playlists():
    cfg = load_config()
    return cfg.get("playlists", [])


def get_active_playlist_id():
    cfg = load_config()
    return cfg.get("active_playlist")


@app.route("/playlist/create", methods=["POST"])
def playlist_create():
    if not session.get("auth"):
        return redirect(url_for("login"))
    name = request.form.get("name", "").strip()
    if name:
        cfg = load_config()
        playlists = cfg.setdefault("playlists", [])
        playlists.append({"id": os.urandom(4).hex(), "name": name, "videos": [], "shuffle": False})
        save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/playlist/delete", methods=["POST"])
def playlist_delete():
    if not session.get("auth"):
        return redirect(url_for("login"))
    pid = request.form.get("id", "")
    cfg = load_config()
    cfg["playlists"] = [p for p in cfg.get("playlists", []) if p["id"] != pid]
    if cfg.get("active_playlist") == pid:
        cfg["active_playlist"] = None
    save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/playlist/set-active", methods=["POST"])
def playlist_set_active():
    if not session.get("auth"):
        return redirect(url_for("login"))
    pid = request.form.get("id", "")
    cfg = load_config()
    cfg["active_playlist"] = pid if pid else None
    save_config(cfg)
    subprocess.run(["systemctl", "restart", "webtv-scheduler"], shell=False)
    return redirect(url_for("dashboard"))


@app.route("/playlist/add-video", methods=["POST"])
def playlist_add_video():
    if not session.get("auth"):
        return redirect(url_for("login"))
    pid = request.form.get("id", "")
    video = request.form.get("video", "")
    if pid and video:
        cfg = load_config()
        for pl in cfg.get("playlists", []):
            if pl["id"] == pid and video not in pl["videos"]:
                pl["videos"].append(video)
        save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/playlist/remove-video", methods=["POST"])
def playlist_remove_video():
    if not session.get("auth"):
        return redirect(url_for("login"))
    pid = request.form.get("id", "")
    video = request.form.get("video", "")
    if pid and video:
        cfg = load_config()
        for pl in cfg.get("playlists", []):
            if pl["id"] == pid:
                pl["videos"] = [v for v in pl["videos"] if v != video]
        save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/playlist/move-video", methods=["POST"])
def playlist_move_video():
    if not session.get("auth"):
        return redirect(url_for("login"))
    pid = request.form.get("id", "")
    video = request.form.get("video", "")
    direction = request.form.get("direction", "up")
    if pid and video:
        cfg = load_config()
        for pl in cfg.get("playlists", []):
            if pl["id"] == pid and video in pl["videos"]:
                idx = pl["videos"].index(video)
                if direction == "up" and idx > 0:
                    pl["videos"][idx], pl["videos"][idx - 1] = pl["videos"][idx - 1], pl["videos"][idx]
                elif direction == "down" and idx < len(pl["videos"]) - 1:
                    pl["videos"][idx], pl["videos"][idx + 1] = pl["videos"][idx + 1], pl["videos"][idx]
        save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/api/encode-status")
def api_encode_status():
    if not session.get("auth"):
        return Response('{"error":"unauthorized"}', status=401, mimetype="application/json")
    return Response(
        json.dumps({"running": encode_status["running"], "file": encode_status["file"],
                    "download_running": download_status["running"], "download_title": download_status["title"]}),
        mimetype="application/json"
    )


@app.route("/api/now-playing")
def api_now_playing():
    if not session.get("auth"):
        return Response('{"error":"unauthorized"}', status=401, mimetype="application/json")
    try:
        with open(STATE_FILE) as f:
            data = f.read()
    except FileNotFoundError:
        data = '{"mode":"unknown","label":"Aguardando scheduler...","file":"","since":""}'
    return Response(data, mimetype="application/json")


@app.route("/api/log")
def api_log():
    if not session.get("auth"):
        return Response('{"error":"unauthorized"}', status=401, mimetype="application/json")
    try:
        with open(SCHEDULER_LOG) as f:
            lines = f.readlines()[-60:]
    except FileNotFoundError:
        lines = []
    return Response(json.dumps({"lines": lines}), mimetype="application/json")


@app.route("/playlist/toggle-avoid-duplicates", methods=["POST"])
def playlist_toggle_avoid_duplicates():
    if not session.get("auth"):
        return redirect(url_for("login"))
    pid = request.form.get("id", "")
    cfg = load_config()
    for pl in cfg.get("playlists", []):
        if pl["id"] == pid:
            pl["avoid_duplicates"] = not pl.get("avoid_duplicates", False)
    save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/playlist/set-weight", methods=["POST"])
def playlist_set_weight():
    if not session.get("auth"):
        return redirect(url_for("login"))
    pid = request.form.get("id", "")
    try:
        weight = max(1, min(10, int(request.form.get("weight", 3))))
    except ValueError:
        weight = 3
    cfg = load_config()
    for pl in cfg.get("playlists", []):
        if pl["id"] == pid:
            pl["weight"] = weight
    save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/playlist/set-schedule", methods=["POST"])
def playlist_set_schedule():
    if not session.get("auth"):
        return redirect(url_for("login"))
    pid = request.form.get("id", "")
    time_val = request.form.get("time", "")
    if not pid or not time_val:
        return redirect(url_for("dashboard"))
    try:
        duration = max(5, min(480, int(request.form.get("duration", 60))))
    except ValueError:
        duration = 60
    recurrence = request.form.get("recurrence", "daily")
    cfg = load_config()
    pl = next((p for p in cfg.get("playlists", []) if p["id"] == pid), None)
    if not pl:
        return redirect(url_for("dashboard"))
    cfg["schedule"] = [s for s in cfg.get("schedule", []) if s.get("playlist_id") != pid]
    item = {"time": time_val, "duration": duration, "label": pl["name"],
            "playlist_id": pid, "recurrence": recurrence}
    if recurrence == "weekly":
        item["days"] = [int(d) for d in request.form.getlist("days")]
    elif recurrence == "once":
        item["date"] = request.form.get("date", "")
    cfg.setdefault("schedule", []).append(item)
    cfg["schedule"].sort(key=lambda x: x["time"])
    save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/playlist/remove-schedule", methods=["POST"])
def playlist_remove_schedule():
    if not session.get("auth"):
        return redirect(url_for("login"))
    pid = request.form.get("id", "")
    if pid:
        cfg = load_config()
        cfg["schedule"] = [s for s in cfg.get("schedule", []) if s.get("playlist_id") != pid]
        save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/playlist/toggle-shuffle", methods=["POST"])
def playlist_toggle_shuffle():
    if not session.get("auth"):
        return redirect(url_for("login"))
    pid = request.form.get("id", "")
    cfg = load_config()
    for pl in cfg.get("playlists", []):
        if pl["id"] == pid:
            pl["shuffle"] = not pl.get("shuffle", False)
    save_config(cfg)
    subprocess.run(["systemctl", "restart", "webtv-scheduler"], shell=False)
    return redirect(url_for("dashboard"))


@app.route("/video/download-url", methods=["POST"])
def video_download_url():
    if not session.get("auth"):
        return redirect(url_for("login"))
    url = request.form.get("url", "").strip()
    if url and not download_status["running"]:
        t = threading.Thread(target=download_video_bg, args=(url,), daemon=True)
        t.start()
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == PANEL_PASSWORD:
            session["auth"] = True
            return redirect(url_for("dashboard"))
        return render_template_string(LOGIN_HTML, error="Senha incorreta")
    return render_template_string(LOGIN_HTML, error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def dashboard():
    if not session.get("auth"):
        return redirect(url_for("login"))
    cfg = load_config()
    schedule = list(enumerate(cfg.get("schedule", [])))
    pl_schedules = {s["playlist_id"]: s for s in cfg.get("schedule", []) if s.get("playlist_id")}
    return render_template_string(
        HTML,
        status=stream_status(),
        schedule=schedule,
        videos=get_videos(),
        encode_running=encode_status["running"],
        encode_file=encode_status["file"],
        download_running=download_status["running"],
        download_title=download_status["title"],
        playlists=get_playlists(),
        active_playlist=get_active_playlist_id(),
        playlist_schedules=pl_schedules,
    )


@app.route("/stream/restart", methods=["POST"])
def stream_restart():
    if not session.get("auth"):
        return redirect(url_for("login"))
    subprocess.run(["systemctl", "restart", "webtv-scheduler"], shell=False)
    return redirect(url_for("dashboard"))


@app.route("/stream/stop", methods=["POST"])
def stream_stop():
    if not session.get("auth"):
        return redirect(url_for("login"))
    subprocess.run(["systemctl", "stop", "webtv-scheduler"], shell=False)
    return redirect(url_for("dashboard"))


@app.route("/stream/start", methods=["POST"])
def stream_start():
    if not session.get("auth"):
        return redirect(url_for("login"))
    subprocess.run(["systemctl", "start", "webtv-scheduler"], shell=False)
    return redirect(url_for("dashboard"))


@app.route("/upload", methods=["POST"])
def upload():
    if not session.get("auth"):
        return redirect(url_for("login"))
    f = request.files.get("video")
    if not f:
        return redirect(url_for("dashboard"))
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return redirect(url_for("dashboard"))
    filename = secure_filename(f.filename)
    raw_path = os.path.join(VIDEOS_RAW_DIR, filename)
    os.makedirs(VIDEOS_RAW_DIR, exist_ok=True)
    f.save(raw_path)
    out_name = os.path.splitext(filename)[0] + ".mp4"
    t = threading.Thread(target=encode_video_bg, args=(raw_path, out_name), daemon=True)
    t.start()
    return redirect(url_for("dashboard"))


@app.route("/videos/rename", methods=["POST"])
def video_rename():
    if not session.get("auth"):
        return redirect(url_for("login"))
    old_name = request.form.get("old_name", "")
    new_name = request.form.get("new_name", "").strip()
    if not new_name:
        return redirect(url_for("dashboard"))
    if not new_name.lower().endswith(".mp4"):
        new_name += ".mp4"
    if "/" in old_name or "\\" in old_name or "/" in new_name or "\\" in new_name:
        return redirect(url_for("dashboard"))
    old_path = os.path.join(VIDEOS_DIR, old_name)
    new_path = os.path.join(VIDEOS_DIR, new_name)
    if os.path.exists(old_path) and not os.path.exists(new_path):
        os.rename(old_path, new_path)
        subprocess.run(["systemctl", "restart", "webtv-scheduler"], shell=False)
    return redirect(url_for("dashboard"))


@app.route("/videos/delete-bulk", methods=["POST"])
def video_delete_bulk():
    if not session.get("auth"):
        return redirect(url_for("login"))
    raw = request.form.get("filenames", "[]")
    try:
        filenames = json.loads(raw)
    except Exception:
        filenames = []
    deleted = 0
    for filename in filenames:
        if filename and "/" not in filename and "\\" not in filename:
            path = os.path.join(VIDEOS_DIR, filename)
            if os.path.exists(path):
                os.remove(path)
                deleted += 1
    if deleted:
        subprocess.run(["systemctl", "restart", "webtv-scheduler"], shell=False)
    return redirect(url_for("dashboard"))


@app.route("/videos/delete", methods=["POST"])
def video_delete():
    if not session.get("auth"):
        return redirect(url_for("login"))
    filename = secure_filename(request.form.get("filename", ""))
    if filename:
        path = os.path.join(VIDEOS_DIR, filename)
        if os.path.exists(path):
            os.remove(path)
        subprocess.run(["systemctl", "restart", "webtv-scheduler"], shell=False)
    return redirect(url_for("dashboard"))


@app.route("/schedule/add", methods=["POST"])
def schedule_add():
    if not session.get("auth"):
        return redirect(url_for("login"))
    time_val = request.form.get("time", "")
    label = request.form.get("label", "")
    file_val = request.form.get("file", "")
    if time_val and label and file_val:
        try:
            duration = max(5, min(480, int(request.form.get("duration", 120))))
        except ValueError:
            duration = 120
        cfg = load_config()
        recurrence = request.form.get("recurrence", "daily")
        item = {"time": time_val, "label": label, "file": file_val, "duration": duration, "recurrence": recurrence}
        if recurrence == "weekly":
            item["days"] = [int(d) for d in request.form.getlist("days")]
        elif recurrence == "once":
            item["date"] = request.form.get("date", "")
        cfg.setdefault("schedule", []).append(item)
        cfg["schedule"].sort(key=lambda x: x["time"])
        save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/schedule/delete", methods=["POST"])
def schedule_delete():
    if not session.get("auth"):
        return redirect(url_for("login"))
    try:
        idx = int(request.form.get("index", -1))
        cfg = load_config()
        schedule = cfg.get("schedule", [])
        if 0 <= idx < len(schedule):
            schedule.pop(idx)
            cfg["schedule"] = schedule
            save_config(cfg)
    except (ValueError, IndexError):
        pass
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
