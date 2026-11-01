#!/usr/bin/env python3
"""
Publica na rádio um programa enviado por um locutor.

Origens possíveis (workflow_dispatch):
- AUDIO_URL : arquivo enviado pelo link de envio (projeto envio/ na Vercel):
              upload no Vercel Blob ou link de download de um arquivo do Google Drive
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
- PROGRAMA                      : título do episódio (e nome da pasta no AzuraCast)
- PLAYLISTS                     : JSON com as playlists que recebem o episódio
                                  (vazio = playlist com o mesmo nome de PROGRAMA)
                                  ou {"playlists": [...], "editar": false} pra programa
                                  já pronto (sobe sem vinheta, playback nem ajuste de volume)
- AUDIO_URL ou MEDIA_ID         : origem do áudio
- AZURACAST_API_KEY, AZURACAST_BASE_URL, AZURACAST_STATION
- Só pra origem WhatsApp: PROGRAMAS_WHATSAPP, WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID
"""
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from urllib.parse import parse_qs, urlparse

import requests

import audio_mix

GRAPH_API = "https://graph.facebook.com/v23.0"
MANAGED_ROOT = "programas"
MEDIA_ID_RE = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
BLOB_HOST_RE = re.compile(r"^[a-z0-9]+\.public\.blob\.vercel-storage\.com$")
DRIVE_HOST = "drive.usercontent.google.com"
DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,100}$")
MAX_WHATSAPP_BYTES = 100 * 1024 * 1024   # limite da própria WhatsApp pra documentos
MAX_UPLOAD_BYTES = 500 * 1024 * 1024     # mesmo limite do link de envio
# Upload pro AzuraCast em pedaços (protocolo Flow, igual ao painel web): cada
# requisição fica bem abaixo do limite de tamanho do servidor (erro 413).
UPLOAD_CHUNK_BYTES = 4 * 1024 * 1024
UPLOAD_LAST_CHUNK_RETRIES = 3
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


def is_drive_url(url):
    """Só o formato que api/publicar.js monta: drive.usercontent.google.com/download?id=..."""
    parsed = urlparse(url or "")
    if parsed.scheme != "https" or parsed.hostname != DRIVE_HOST or parsed.path != "/download":
        return False
    ids = parse_qs(parsed.query).get("id", [])
    return len(ids) == 1 and bool(DRIVE_ID_RE.match(ids[0]))


def resolve_source(audio_url, media_id, programa, mapping):
    """Valida os inputs e devolve ("url", valor) ou ("whatsapp", valor)."""
    if not programa:
        raise ValueError("PROGRAMA vazio")
    if bool(audio_url) == bool(media_id):
        raise ValueError("Informe AUDIO_URL ou MEDIA_ID (um dos dois)")
    if audio_url:
        if not (is_blob_url(audio_url) or is_drive_url(audio_url)):
            raise ValueError("AUDIO_URL não é do Vercel Blob nem do Google Drive")
        return "url", audio_url
    if not MEDIA_ID_RE.match(media_id):
        raise ValueError("MEDIA_ID inválido")
    if programa not in mapping.values():
        raise ValueError(f"Programa '{programa}' não está em PROGRAMAS_WHATSAPP")
    return "whatsapp", media_id


def _name_key(name):
    """Compara nomes ignorando maiúsculas, espaços e pontuação: "(11h" == "(11h)"."""
    return re.sub(r"[\W_]+", "", str(name).casefold())


def parse_destino(raw, programa):
    """PLAYLISTS do workflow. Formatos:
    - vazio                                   -> playlist com o nome do programa, com edição
    - ["P1", "P2"]                            -> essas playlists, com edição
    - {"playlists": ["P1"], "editar": false}  -> programa pronto, sobe sem edição
    @returns (lista de nomes, editar)
    """
    if not (raw or "").strip():
        return [programa], True
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("PLAYLISTS não é JSON válido") from exc
    editar = True
    if isinstance(parsed, dict):
        if "playlists" not in parsed:
            raise ValueError("PLAYLISTS precisa da lista 'playlists'")
        editar = parsed.get("editar") is not False
        parsed = parsed["playlists"]
    if not isinstance(parsed, list):
        raise ValueError("PLAYLISTS precisa ser uma lista")
    names = [str(n).strip() for n in parsed if str(n).strip()]
    if not names:
        raise ValueError("PLAYLISTS vazia")
    return names, editar


def parse_playlists(raw, programa):
    return parse_destino(raw, programa)[0]


TITLE_PREFIX = "PG "
HONORIFIC_RE = re.compile(r"^(bp|bispo|pr|pra|pastor|pastora|ap|apóstolo|apostolo|ev|miss|dc|dr|dra)\.?\s", re.I)
WEEKDAY_RE = re.compile(r"^(seg|ter|qua|qui|sex|s[áa]b|dom)", re.I)
PAREN_RE = re.compile(r"\(([^()]*)\)?")


def _person_in_playlist(name):
    """Acha o nome de quem apresenta no nome da playlist.

    Ex.: "PG Palavras de Fé (Pr. Anderson Barbosa) - 14h (QUI/TER)" -> "Pr. Anderson Barbosa".
    Prioriza quem tem título (Pr., Bp., ...); senão aceita um trecho depois de " - "
    sem número nem dia da semana ("... - Patricia Bambrila"). Nada achado: None.
    """
    parts = [p.strip() for p in name.split(" - ")]
    groups = [g.strip() for g in PAREN_RE.findall(name)]
    candidates = [PAREN_RE.sub("", p).strip() for p in parts[1:]] + groups
    for cand in candidates:
        if HONORIFIC_RE.match(cand):
            return cand
    for cand in (PAREN_RE.sub("", p).strip() for p in parts[1:]):
        if cand and not re.search(r"\d", cand) and not WEEKDAY_RE.match(cand):
            return cand
    return None


def media_tags(programa, playlist_names):
    """Título e artista que aparecem no AzuraCast: ("PG <programa>", apresentador)."""
    title = programa if programa.upper().startswith(TITLE_PREFIX) else TITLE_PREFIX + programa
    people = (_person_in_playlist(n) for n in playlist_names)
    return title, next((p for p in people if p), ARTIST)


def find_playlist_ids(playlists, names):
    by_key = {}
    for p in playlists:
        by_key.setdefault(_name_key(p.get("name", "")), []).append(p["id"])
    ids, missing = [], []
    for name in names:
        found = by_key.get(_name_key(name), [])
        if len(found) > 1:
            raise LookupError(f"Há mais de uma playlist parecida com '{name}' no AzuraCast")
        if not found:
            missing.append(name)
        else:
            ids.append(found[0])
    if missing:
        raise LookupError("Playlist não existe no AzuraCast: " + "; ".join(missing))
    return ids


def plan_replacement(files, playlist_ids, new_media_id, managed_prefix):
    """Decide o que fazer com os arquivos que já estão nas playlists do programa."""
    targets = set(playlist_ids)
    delete, unassign = [], []
    for f in files:
        ids = [p["id"] for p in f.get("playlists", [])]
        if f["id"] == new_media_id or not targets.intersection(ids):
            continue
        if f.get("path", "").startswith(managed_prefix):
            delete.append(f["id"])
        else:
            unassign.append((f["id"], [i for i in ids if i not in targets]))
    return {"delete": delete, "unassign": unassign}


def chunk_plan(total_size, chunk_size):
    """Pedaços do upload: lista de (número a partir de 1, posição inicial, tamanho)."""
    if total_size <= 0:
        raise ValueError("Arquivo vazio")
    return [
        (i + 1, offset, min(chunk_size, total_size - offset))
        for i, offset in enumerate(range(0, total_size, chunk_size))
    ]


def find_media_id_by_path(files, path):
    for f in files:
        if f.get("path") == path:
            return f["id"]
    raise LookupError(f"Arquivo enviado não apareceu no AzuraCast: {path}")


def build_passthrough_command(src_path, out_path, codec, title, artist, ffmpeg="ffmpeg"):
    """Programa pronto: MP3 é só copiado; outros formatos viram MP3 sem filtro nenhum."""
    audio = ["-c:a", "copy"] if codec == "mp3" else ["-c:a", "libmp3lame", "-b:a", audio_mix.MP3_BITRATE]
    return [
        ffmpeg, "-y", "-loglevel", "error", "-i", src_path, "-map", "0:a:0", "-vn",
        *audio, "-metadata", f"title={title}", "-metadata", f"artist={artist}", out_path,
    ]


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
        # Drive com arquivo privado devolve página de login (HTML) em vez do áudio.
        if (resp.headers.get("Content-Type") or "").startswith("text/html"):
            raise ValueError("o link devolveu uma página, não um áudio "
                             "(arquivo do Drive não está compartilhado com 'qualquer pessoa com o link'?)")
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


def build_program(voice_path, out_path, title, artist):
    intro, bed = trilha_paths()
    voice_seconds = get_duration(voice_path)
    if voice_seconds < 1:
        raise ValueError("Áudio vazio ou curto demais")
    audio_mix.mix_program(voice_path, bed, intro, out_path, voice_seconds, title, artist)
    return get_duration(out_path)


def get_audio_codec(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name",
         "-of", "csv=p=0", path],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


def prepare_as_is(src_path, out_path, title, artist):
    if get_duration(src_path) < 1:
        raise ValueError("Áudio vazio ou curto demais")
    cmd = build_passthrough_command(src_path, out_path, get_audio_codec(src_path), title, artist)
    subprocess.run(cmd, check=True)
    return get_duration(out_path)


# ---------------------------------------------------------------- AzuraCast

def api_request(method, base_url, api_key, path, timeout=30, **kwargs):
    resp = requests.request(
        method, f"{base_url}/api{path}", headers={"X-API-Key": api_key}, timeout=timeout, **kwargs
    )
    resp.raise_for_status()
    return resp.json() if resp.content else None


def _post_chunk(url, api_key, data, filename, payload):
    resp = requests.post(
        url, headers={"X-API-Key": api_key}, data=data,
        files={"file": (filename, payload, "application/octet-stream")}, timeout=300,
    )
    resp.raise_for_status()
    return resp


def upload_in_chunks(base_url, api_key, station, directory, filename, path, chunk_size=UPLOAD_CHUNK_BYTES):
    """Sobe o arquivo em pedaços pra pasta `directory` da biblioteca do AzuraCast."""
    url = f"{base_url}/api/station/{station}/files/upload"
    total = os.path.getsize(path)
    plan = chunk_plan(total, chunk_size)
    identifier = re.sub(r"[^0-9A-Za-z_-]", "-", f"{total}-{directory}-{filename}")
    with open(path, "rb") as fh:
        for number, offset, size in plan:
            fh.seek(offset)
            payload = fh.read(size)
            data = {
                "flowChunkNumber": number, "flowTotalChunks": len(plan),
                "flowChunkSize": chunk_size, "flowCurrentChunkSize": size,
                "flowTotalSize": total, "flowIdentifier": identifier,
                "flowFilename": filename, "flowRelativePath": filename,
                "currentDirectory": directory,
            }
            resp = _post_chunk(url, api_key, data, filename, payload)
            if number < len(plan):
                continue
            # Último pedaço: 204 = servidor ainda não juntou tudo, pede de novo.
            for _ in range(UPLOAD_LAST_CHUNK_RETRIES):
                if resp.status_code != 204:
                    break
                resp = _post_chunk(url, api_key, data, filename, payload)
            result = resp.json() if resp.content else None
            if not result or not result.get("success"):
                message = (result or {}).get("message") or f"resposta {resp.status_code}"
                raise RuntimeError(f"AzuraCast não aceitou o arquivo: {message}")


def publish(base_url, api_key, station, programa, playlist_names, mp3_path, tags):
    playlists = api_request("GET", base_url, api_key, f"/station/{station}/playlists")
    playlist_ids = find_playlist_ids(playlists, playlist_names)

    directory = f"{MANAGED_ROOT}/{slugify(programa)}"
    prefix = f"{directory}/"
    filename = datetime.datetime.now(BRT).strftime("%Y%m%d-%H%M%S") + ".mp3"
    upload_in_chunks(base_url, api_key, station, directory, filename, mp3_path)

    files = api_request("GET", base_url, api_key, f"/station/{station}/files", timeout=120)
    new_id = find_media_id_by_path(files, prefix + filename)
    api_request(
        "PUT", base_url, api_key, f"/station/{station}/file/{new_id}",
        json={"playlists": playlist_ids, "title": tags[0], "artist": tags[1]},
    )

    # O plano usa a lista de antes de vincular o novo: ele é ignorado pelo id.
    plan = plan_replacement(files, playlist_ids, new_id, prefix)
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
    playlist_names, editar = parse_destino(os.environ.get("PLAYLISTS"), programa)
    print("Modo: " + ("edição (vinheta + playback)" if editar else "sem edição (programa pronto)"))
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
            tags = media_tags(programa, playlist_names)
            print(f"Título: {tags[0]} | Artista: {tags[1]}")
            if editar:
                duration = build_program(voice, mp3, *tags)
            else:
                duration = prepare_as_is(voice, mp3, *tags)
            publish(base_url, api_key, station, programa, playlist_names, mp3, tags)
    except Exception as exc:
        print(f"ERRO: {type(exc).__name__}: {exc}")
        _notify(kind, programa, mapping, ok=False)
        return 1

    print(f"OK: \"{programa}\" publicado ({format_duration(duration)}).")
    _notify(kind, programa, mapping, ok=True, duration=duration)
    return 0


if __name__ == "__main__":
    sys.exit(main())
