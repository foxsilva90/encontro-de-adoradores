#!/usr/bin/env python3
"""
Gera e publica o boletim de notícias horário na rádio via API do AzuraCast.

Fluxo: busca manchetes no RSS do G1 -> monta um texto de locução ->
gera áudio com a voz clonada do Anderson Gustavo (XTTS-v2 via Replicate)
-> sobe pro AzuraCast, substituindo o boletim da hora anterior -> garante
que está atribuído à playlist "Boletim de Notícias" (criada
automaticamente na primeira execução, tipo once_per_hour, sem interromper
a faixa atual, agendada só entre 6h e 22h).

Credenciais vêm de variáveis de ambiente (secrets do GitHub Actions):
- AZURACAST_API_KEY   : chave de API com permissão de estação
- AZURACAST_BASE_URL  : ex. https://radio.encontrodeadoradores.com
- AZURACAST_STATION   : shortcode da estação, ex. encontro_de_adoradores
- REPLICATE_API_TOKEN : token de API do Replicate
- ANDERSON_VOICE_URL  : URL pública da amostra de voz de referência

Se as credenciais não estiverem presentes, faz SKIP em vez de falhar.
"""
import base64
import io
import os
import sys
import time
import wave
from xml.etree import ElementTree

import requests

REPLICATE_MODEL_VERSION = "684bc3855b37866c0c65add2ff39c78f3dea3f4ff103a436465326e0f438d55e"

RSS_URL = "https://g1.globo.com/rss/g1/"
HEADLINE_COUNT = 3
HEADLINE_POOL_SIZE = 15  # quantas manchetes olhar no RSS antes de filtrar
PLAYLIST_NAME = "Boletim de Notícias"
UPLOAD_PATH = "boletim_noticias/atual.wav"
LOCAL_AUDIO_PATH = "boletim_atual.wav"

# Termos que derrubam uma manchete do boletim — conteúdo pesado/impróprio
# pra uma rádio gospel (crime, violência, sexual, etc). Lista propositalmente
# ampla: melhor pular uma notícia neutra por engano do que ler algo impróprio.
BLOCKED_TERMS = [
    "estupro", "abuso", "pedofilia", "assédio", "molestad",
    "estuprador", "estupr", "sexual", "stealthing", "consentimento",
    "assassinato", "assassinad", "homicídio", "feminicídio", "chacina",
    "morto a tiros", "morta a tiros", "esfaquead", "decapitad",
    "suicídio", "suicida", "automutilação",
    "violência doméstica", "espancad",
    "cadáver", "corpo encontrado", "corpo carbonizado",
    "tráfico humano", "exploração", "pornografia",
    "tortura", "sequestro", "cárcere privado",
    "overdose", "crack", "drogas", "nudes", "estupra",
]


def is_appropriate(headline):
    lowered = headline.lower()
    return not any(term in lowered for term in BLOCKED_TERMS)


def _creds():
    api_key = os.environ.get("AZURACAST_API_KEY")
    base_url = os.environ.get("AZURACAST_BASE_URL")
    station = os.environ.get("AZURACAST_STATION")
    replicate_token = os.environ.get("REPLICATE_API_TOKEN")
    voice_url = os.environ.get("ANDERSON_VOICE_URL")
    if not api_key or not base_url or not station or not replicate_token or not voice_url:
        print("SKIP: alguma credencial (AZURACAST_*, REPLICATE_API_TOKEN, ANDERSON_VOICE_URL) não configurada.")
        sys.exit(0)
    return api_key, base_url.rstrip("/"), station, replicate_token, voice_url


def fetch_headlines():
    resp = requests.get(RSS_URL, timeout=20)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    titles = [item.findtext("title") for item in root.findall(".//item")]
    candidates = [t.strip() for t in titles if t][:HEADLINE_POOL_SIZE]
    return [t for t in candidates if is_appropriate(t)][:HEADLINE_COUNT]


MAX_CHUNK_LEN = 200  # XTTS-v2 engasga/erra em textos longos numa só chamada


def _split_long_sentence(sentence):
    if len(sentence) <= MAX_CHUNK_LEN:
        return [sentence]
    # Quebra em pontos naturais (; ,) mantendo os pedaços dentro do limite.
    parts, current = [], ""
    for piece in sentence.replace(";", ",").split(","):
        piece = piece.strip()
        if not piece:
            continue
        candidate = f"{current}, {piece}" if current else piece
        if len(candidate) > MAX_CHUNK_LEN and current:
            parts.append(current + ".")
            current = piece
        else:
            current = candidate
    if current:
        parts.append(current if current.endswith((".", "!", "?")) else f"{current}.")
    return parts


def build_script(headlines):
    if not headlines:
        return None
    segments = [
        "Você está ouvindo o boletim de notícias da Rádio Encontro de Adoradores.",
        "As principais notícias desta hora:",
    ]
    for h in headlines:
        sentence = h if h.endswith((".", "!", "?")) else f"{h}."
        segments.extend(_split_long_sentence(sentence))
    segments.append("Fique com a gente.")
    segments.append("Voltamos com mais música e adoração.")
    return segments


def _generate_segment(text, replicate_token, voice_url, retries=4):
    for attempt in range(retries):
        resp = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={
                "Authorization": f"Bearer {replicate_token}",
                "Content-Type": "application/json",
                "Prefer": "wait",
            },
            json={
                "version": REPLICATE_MODEL_VERSION,
                "input": {
                    "text": text,
                    "speaker": voice_url,
                    "language": "pt",
                    "cleanup_voice": False,
                },
            },
            timeout=120,
        )
        if resp.status_code == 429 and attempt < retries - 1:
            time.sleep(2 ** attempt * 3)  # 3s, 6s, 12s...
            continue
        resp.raise_for_status()
        break

    prediction = resp.json()
    if prediction.get("status") != "succeeded":
        raise RuntimeError(f"Geração de voz falhou: {prediction.get('error') or prediction.get('status')}")

    audio_resp = requests.get(prediction["output"], timeout=60)
    audio_resp.raise_for_status()
    return audio_resp.content


def generate_audio(segments, path, replicate_token, voice_url):
    clips = []
    for i, s in enumerate(segments):
        if i > 0:
            time.sleep(1.5)  # evita 429 de rate limit entre chamadas seguidas
        clips.append(_generate_segment(s, replicate_token, voice_url))

    with wave.open(io.BytesIO(clips[0]), "rb") as first:
        params = first.getparams()

    with wave.open(path, "wb") as out:
        out.setparams(params)
        for clip in clips:
            with wave.open(io.BytesIO(clip), "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))


def api_request(method, base_url, api_key, path, **kwargs):
    url = f"{base_url}/api{path}"
    headers = {"X-API-Key": api_key}
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp.json() if resp.content else None


def ensure_playlist(base_url, api_key, station):
    playlists = api_request("GET", base_url, api_key, f"/station/{station}/playlists")
    for p in playlists:
        if p.get("name") == PLAYLIST_NAME:
            # Não interrompe o que estiver tocando — entra só depois que a
            # faixa/segmento atual terminar. Sincroniza isso mesmo em
            # playlists já criadas por uma execução anterior.
            api_request(
                "PUT", base_url, api_key, f"/station/{station}/playlist/{p['id']}",
                json={"backend_options": []},
            )
            return p["id"]

    print(f"Criando playlist '{PLAYLIST_NAME}'...")
    created = api_request(
        "POST", base_url, api_key, f"/station/{station}/playlists",
        json={
            "name": PLAYLIST_NAME,
            "type": "once_per_hour",
            "play_per_hour_minute": 0,
            "backend_options": [],
            "is_enabled": True,
            "weight": 3,
            "schedule_items": [
                {"start_time": 600, "end_time": 2200, "days": [1, 2, 3, 4, 5, 6, 7]}
            ],
        },
    )
    return created["id"]


def remove_previous_bulletin(base_url, api_key, station):
    files = api_request("GET", base_url, api_key, f"/station/{station}/files")
    for f in files:
        if f.get("path") == UPLOAD_PATH:
            api_request("DELETE", base_url, api_key, f"/station/{station}/file/{f['id']}")


def upload_bulletin(base_url, api_key, station, local_path):
    with open(local_path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode("ascii")
    media = api_request(
        "POST", base_url, api_key, f"/station/{station}/files",
        json={"path": UPLOAD_PATH, "file": encoded},
    )
    return media["id"]


def assign_playlist(base_url, api_key, station, media_id, playlist_id):
    api_request(
        "PUT", base_url, api_key, f"/station/{station}/file/{media_id}",
        json={"playlists": [playlist_id]},
    )


def main():
    api_key, base_url, station, replicate_token, voice_url = _creds()

    headlines = fetch_headlines()
    script = build_script(headlines)
    if not script:
        print("SKIP: nenhuma manchete encontrada no RSS.")
        sys.exit(0)

    print(f"Boletim: {len(headlines)} manchete(s).")
    generate_audio(script, LOCAL_AUDIO_PATH, replicate_token, voice_url)

    playlist_id = ensure_playlist(base_url, api_key, station)
    remove_previous_bulletin(base_url, api_key, station)
    media_id = upload_bulletin(base_url, api_key, station, LOCAL_AUDIO_PATH)
    assign_playlist(base_url, api_key, station, media_id, playlist_id)

    print(f"OK: boletim publicado (media_id={media_id}, playlist_id={playlist_id}).")


if __name__ == "__main__":
    main()
