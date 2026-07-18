#!/usr/bin/env python3
"""
Gera e publica o boletim de notícias horário na rádio via API do AzuraCast.

Fluxo: busca manchetes no RSS do G1 -> monta um texto de locução ->
gera áudio (gTTS) -> sobe pro AzuraCast, substituindo o boletim da hora
anterior -> garante que está atribuído à playlist "Boletim de Notícias"
(criada automaticamente na primeira execução, tipo once_per_hour +
interrupt, agendada só entre 6h e 22h).

Credenciais vêm de variáveis de ambiente (secrets do GitHub Actions):
- AZURACAST_API_KEY : chave de API com permissão de estação
- AZURACAST_BASE_URL: ex. https://radio.encontrodeadoradores.com
- AZURACAST_STATION : shortcode da estação, ex. encontro_de_adoradores

Se as credenciais não estiverem presentes, faz SKIP em vez de falhar.
"""
import base64
import os
import sys
from xml.etree import ElementTree

import requests
from gtts import gTTS

RSS_URL = "https://g1.globo.com/rss/g1/"
HEADLINE_COUNT = 3
HEADLINE_POOL_SIZE = 15  # quantas manchetes olhar no RSS antes de filtrar
PLAYLIST_NAME = "Boletim de Notícias"
UPLOAD_PATH = "boletim_noticias/atual.mp3"
LOCAL_AUDIO_PATH = "boletim_atual.mp3"

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
    if not api_key or not base_url or not station:
        print("SKIP: AZURACAST_API_KEY, AZURACAST_BASE_URL ou AZURACAST_STATION não configurados.")
        sys.exit(0)
    return api_key, base_url.rstrip("/"), station


def fetch_headlines():
    resp = requests.get(RSS_URL, timeout=20)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    titles = [item.findtext("title") for item in root.findall(".//item")]
    candidates = [t.strip() for t in titles if t][:HEADLINE_POOL_SIZE]
    return [t for t in candidates if is_appropriate(t)][:HEADLINE_COUNT]


def build_script(headlines):
    if not headlines:
        return None
    partes = [
        "Você está ouvindo o boletim de notícias da Rádio Encontro de Adoradores.",
        "As principais notícias desta hora:",
    ]
    partes.extend(headlines)
    partes.append("Fique com a gente. Voltamos com mais música e adoração.")
    return " ... ".join(partes)


def generate_audio(text, path):
    gTTS(text=text, lang="pt", tld="com.br").save(path)


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
    api_key, base_url, station = _creds()

    headlines = fetch_headlines()
    script = build_script(headlines)
    if not script:
        print("SKIP: nenhuma manchete encontrada no RSS.")
        sys.exit(0)

    print(f"Boletim: {len(headlines)} manchete(s).")
    generate_audio(script, LOCAL_AUDIO_PATH)

    playlist_id = ensure_playlist(base_url, api_key, station)
    remove_previous_bulletin(base_url, api_key, station)
    media_id = upload_bulletin(base_url, api_key, station, LOCAL_AUDIO_PATH)
    assign_playlist(base_url, api_key, station, media_id, playlist_id)

    print(f"OK: boletim publicado (media_id={media_id}, playlist_id={playlist_id}).")


if __name__ == "__main__":
    main()
