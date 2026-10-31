#!/usr/bin/env python3
"""
Publica na rádio um programa enviado por um locutor.

Origens possíveis (workflow_dispatch):
- AUDIO_URL : arquivo enviado pelo link de envio (projeto envio/ na Vercel)
- MEDIA_ID  : áudio recebido pelo WhatsApp (api/whatsapp-webhook.js)

Fluxo: baixa a voz -> monta o programa (vinheta de responsabilidade + voz com
playback, ver audio_mix.py) -> sobe pro AzuraCast na pasta programas/<slug>/
-> coloca na playlist do programa -> tira o episódio anterior dessa playlist
-> (WhatsApp) responde ao locutor.

Episódio anterior:
- se foi enviado por este sistema (pasta programas/<slug>/), é apagado;
- se foi subido à mão no AzuraCast, só sai da playlist (o arquivo fica).
O novo entra na playlist ANTES de o antigo sair: a playlist nunca fica vazia.

Variáveis de ambiente:
- PROGRAMA                      : nome exato da playlist no AzuraCast
- AUDIO_URL ou MEDIA_ID         : origem do áudio
- AZURACAST_API_KEY, AZURACAST_BASE_URL, AZURACAST_STATION
- Só pra origem WhatsApp: PROGRAMAS_WHATSAPP, WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID
"""
import base64
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from urllib.parse import urlparse

import requests

import audio_mix

GRAPH_API = "https://graph.facebook.com/v23.0"
MANAGED_ROOT = "programas"
MEDIA_ID_RE = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
BLOB_HOST_RE = re.compile(r"^[a-z0-9]+\.public\.blob\.vercel-storage\.com$")
MAX_WHATSAPP_BYTES = 100 * 1024 * 1024   # limite da própria WhatsApp pra documentos
MAX_UPLOAD_BYTES = 500 * 1024 * 1024     # mesmo limite do link de envio
ARTIST = "Rádio Encontro de Adoradores"
BRT = datetime.timezone(datetime.timedelta(hours=-3))

TRILHAS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trilhas")
INTRO_FILE = "responsabilidade.mp3"
BED_FILE = "playback.m4a"


# ---------------------------------------------------------------- funções puras

def slugify(text):
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug or "programa"


def parse_program_map(raw):
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result = {}
    for phone, program in parsed.items():
        digits = re.sub(r"\D", "", str(phone))
        if len(digits) >= 10 and isinstance(program, str) and program.strip():
            result[digits] = program.strip()
    return result


def phones_for_program(mapping, programa):
    return [phone for phone, prog in mapping.items() if prog == programa]


def is_blob_url(url):
    parsed = urlparse(url or "")
    return parsed.scheme == "https" and bool(BLOB_HOST_RE.match(parsed.hostname or ""))


def resolve_source(audio_url, media_id, programa, mapping):
    """Valida os inputs e devolve ("url", valor) ou ("whatsapp", valor)."""
    if not programa:
        raise ValueError("PROGRAMA vazio")
    if bool(audio_url) == bool(media_id):
        raise ValueError("Informe AUDIO_URL ou MEDIA_ID (um dos dois)")
    if audio_url:
        if not is_blob_url(audio_url):
            raise ValueError("AUDIO_URL não é do Vercel Blob")
        return "url", audio_url
    if not MEDIA_ID_RE.match(media_id):
        raise ValueError("MEDIA_ID inválido")
    if programa not in mapping.values():
        raise ValueError(f"Programa '{programa}' não está em PROGRAMAS_WHATSAPP")
    return "whatsapp", media_id


def find_playlist_id(playlists, name):
    wanted = name.strip().casefold()
    for p in playlists:
        if str(p.get("name", "")).strip().casefold() == wanted:
            return p["id"]
    raise LookupError(f"Playlist '{name}' não existe no AzuraCast")


def plan_replacement(files, playlist_id, new_media_id, managed_prefix):
    """Decide o que fazer com os arquivos que já estão na playlist."""
    delete, unassign = [], []
    for f in files:
        ids = [p["id"] for p in f.get("playlists", [])]
        if f["id"] == new_media_id or playlist_id not in ids:
            continue
        if f.get("path", "").startswith(managed_prefix):
            delete.append(f["id"])
        else:
            unassign.append((f["id"], [i for i in ids if i != playlist_id]))
    return {"delete": delete, "unassign": unassign}


def format_duration(seconds):
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}min" if h else f"{m}min{s:02d}s"


# ---------------------------------------------------------------- download

def _stream_to_file(resp, dest_path, max_bytes):
    resp.raise_for_status()
    written = 0
    with open(dest_path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                raise ValueError(f"Arquivo maior que {max_bytes // (1024 * 1024)} MB")
            fh.write(chunk)


def download_url(url, dest_path):
    with requests.get(url, timeout=600, stream=True) as resp:
        _stream_to_file(resp, dest_path, MAX_UPLOAD_BYTES)


def _wa_headers(token):
    return {"Authorization": f"Bearer {token}"}


def download_whatsapp_media(media_id, token, dest_path):
    meta = requests.get(f"{GRAPH_API}/{media_id}", headers=_wa_headers(token), timeout=30)
    meta.raise_for_status()
    with requests.get(meta.json()["url"], headers=_wa_headers(token), timeout=300, stream=True) as resp:
        _stream_to_file(resp, dest_path, MAX_WHATSAPP_BYTES)


def send_text(token, phone_number_id, to, body):
    resp = requests.post(
        f"{GRAPH_API}/{phone_number_id}/messages",
        headers=_wa_headers(token),
        json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}},
        timeout=30,
    )
    if not resp.ok:
        # Não derruba a publicação por causa da resposta; só registra.
        print(f"Aviso: não consegui responder no WhatsApp ({resp.status_code}).")


# ---------------------------------------------------------------- áudio

def get_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def trilha_paths():
    intro = os.path.join(TRILHAS_DIR, INTRO_FILE)
    bed = os.path.join(TRILHAS_DIR, BED_FILE)
    for path in (intro, bed):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Trilha não encontrada: trilhas/{os.path.basename(path)}")
    return intro, bed


def build_program(voice_path, out_path, programa):
    intro, bed = trilha_paths()
    voice_seconds = get_duration(voice_path)
    if voice_seconds < 1:
        raise ValueError("Áudio vazio ou curto demais")
    audio_mix.mix_program(voice_path, bed, intro, out_path, voice_seconds, programa, ARTIST)
    return get_duration(out_path)


# ---------------------------------------------------------------- AzuraCast

def api_request(method, base_url, api_key, path, timeout=30, **kwargs):
    resp = requests.request(
        method, f"{base_url}/api{path}", headers={"X-API-Key": api_key}, timeout=timeout, **kwargs
    )
    resp.raise_for_status()
    return resp.json() if resp.content else None


def publish(base_url, api_key, station, programa, mp3_path):
    playlists = api_request("GET", base_url, api_key, f"/station/{station}/playlists")
    playlist_id = find_playlist_id(playlists, programa)

    prefix = f"{MANAGED_ROOT}/{slugify(programa)}/"
    stamp = datetime.datetime.now(BRT).strftime("%Y%m%d-%H%M%S")
    with open(mp3_path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode("ascii")
    media = api_request(
        "POST", base_url, api_key, f"/station/{station}/files", timeout=600,
        json={"path": f"{prefix}{stamp}.mp3", "file": encoded},
    )
    new_id = media["id"]
    api_request(
        "PUT", base_url, api_key, f"/station/{station}/file/{new_id}",
        json={"playlists": [playlist_id]},
    )

    files = api_request("GET", base_url, api_key, f"/station/{station}/files", timeout=120)
    plan = plan_replacement(files, playlist_id, new_id, prefix)
    for fid, remaining in plan["unassign"]:
        api_request("PUT", base_url, api_key, f"/station/{station}/file/{fid}", json={"playlists": remaining})
    for fid in plan["delete"]:
        api_request("DELETE", base_url, api_key, f"/station/{station}/file/{fid}")
    print(f"Publicado media_id={new_id}; removidos={plan['delete']}; desvinculados={[u[0] for u in plan['unassign']]}")


# ---------------------------------------------------------------- main

def _env(name):
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Variável {name} não configurada")
    return value


def _notify(kind, programa, mapping, ok, duration=0.0):
    if kind != "whatsapp":
        return  # o link de envio mostra o status na própria página
    token = _env("WHATSAPP_TOKEN")
    phone_number_id = _env("WHATSAPP_PHONE_NUMBER_ID")
    if ok:
        body = (f"✅ Programa \"{programa}\" atualizado na rádio! "
                f"Duração: {format_duration(duration)}. Deus abençoe!")
    else:
        body = (f"❌ Não consegui colocar o programa \"{programa}\" no ar. "
                "A equipe da rádio vai verificar. Se puder, envie o áudio de novo.")
    for to in phones_for_program(mapping, programa):
        send_text(token, phone_number_id, to, body)


def main():
    mapping = parse_program_map(os.environ.get("PROGRAMAS_WHATSAPP"))
    # Repositório público: esconde os números dos locutores nos logs.
    if os.environ.get("GITHUB_ACTIONS"):
        for phone in mapping:
            print(f"::add-mask::{phone}")

    programa = (os.environ.get("PROGRAMA") or "").strip()
    kind, source = resolve_source(
        (os.environ.get("AUDIO_URL") or "").strip(),
        (os.environ.get("MEDIA_ID") or "").strip(),
        programa, mapping,
    )
    base_url = _env("AZURACAST_BASE_URL").rstrip("/")
    api_key = _env("AZURACAST_API_KEY")
    station = _env("AZURACAST_STATION")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            voice = os.path.join(tmp, "voz")
            mp3 = os.path.join(tmp, "programa.mp3")
            if kind == "url":
                download_url(source, voice)
            else:
                download_whatsapp_media(source, _env("WHATSAPP_TOKEN"), voice)
            duration = build_program(voice, mp3, programa)
            publish(base_url, api_key, station, programa, mp3)
    except Exception as exc:
        print(f"ERRO: {type(exc).__name__}: {exc}")
        _notify(kind, programa, mapping, ok=False)
        return 1

    print(f"OK: \"{programa}\" publicado ({format_duration(duration)}).")
    _notify(kind, programa, mapping, ok=True, duration=duration)
    return 0


if __name__ == "__main__":
    sys.exit(main())
