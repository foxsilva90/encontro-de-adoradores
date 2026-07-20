#!/usr/bin/env python3
"""
Gera e publica o boletim de notícias horário na rádio via API do AzuraCast.

Fluxo: busca manchetes no RSS do G1 -> monta um texto de locução ->
gera áudio com voz da ElevenLabs (Sarah) -> sobe pro AzuraCast,
substituindo o boletim da hora anterior -> garante que está atribuído à
playlist "Boletim de Notícias" (criada automaticamente na primeira
execução, tipo once_per_hour, sem interromper a faixa atual, agendada só
entre 6h e 22h).

Credenciais vêm de variáveis de ambiente (secrets do GitHub Actions):
- AZURACAST_API_KEY   : chave de API com permissão de estação
- AZURACAST_BASE_URL  : ex. https://radio.encontrodeadoradores.com
- AZURACAST_STATION   : shortcode da estação, ex. encontro_de_adoradores
- ELEVENLABS_API_KEY  : chave de API da ElevenLabs
- ELEVENLABS_VOICE_ID : id da voz na ElevenLabs (Sarah)

Se as credenciais não estiverem presentes, faz SKIP em vez de falhar.
"""
import base64
import datetime
import os
import subprocess
import sys
import time
import wave
from xml.etree import ElementTree

import requests

ELEVENLABS_MODEL_ID = "eleven_v3"
ELEVENLABS_SAMPLE_RATE = 24000

# Feeds por editoria — cobre só o essencial (economia, política, mundo,
# esportes, entretenimento). O boletim gira a ordem a cada hora pra não
# ficar sempre nas mesmas 3 categorias.
CATEGORY_FEEDS = [
    ("Economia", "https://g1.globo.com/rss/g1/economia/"),
    ("Política", "https://g1.globo.com/rss/g1/politica/"),
    ("Mundo", "https://g1.globo.com/rss/g1/mundo/"),
    ("Esportes", "https://ge.globo.com/rss/ge/"),
    ("Entretenimento", "https://g1.globo.com/rss/g1/pop-arte/"),
]
HEADLINE_COUNT = 3
HEADLINE_POOL_SIZE = 15  # quantas manchetes olhar por editoria antes de filtrar
PLAYLIST_NAME = "Boletim de Notícias"
UPLOAD_PATH = "boletim_noticias/atual.wav"
VOICE_AUDIO_PATH = "boletim_voz.wav"
LOCAL_AUDIO_PATH = "boletim_atual.wav"
MUSIC_BED_PATH = "trilha_fundo.mp3"  # opcional; se ausente, publica só a voz
MUSIC_BED_VOLUME = "0.07"

# Termos que derrubam uma manchete do boletim — conteúdo pesado/impróprio
# pra uma rádio gospel (crime, violência, sexual, etc). Lista propositalmente
# ampla: melhor pular uma notícia neutra por engano do que ler algo impróprio.
BLOCKED_TERMS = [
    "estupro", "abuso", "pedofilia", "assédio", "molestad",
    "estuprador", "estupr", "sexual", "stealthing", "consentimento",
    "assassinato", "assassinad", "homicídio", "feminicídio", "chacina",
    "morto a tiros", "morta a tiros", "esfaquead", "decapitad", "atropelad",
    "suicídio", "suicida", "automutilação",
    "violência doméstica", "espancad",
    "cadáver", "corpo encontrado", "corpo carbonizado",
    "tráfico humano", "exploração", "pornografia",
    "tortura", "sequestro", "cárcere privado",
    "overdose", "crack", "drogas", "nudes", "estupra",
]

# Notícias de shows/entretenimento secular que não têm a ver com o
# segmento gospel da rádio — fora as exceções abaixo.
ENTERTAINMENT_TERMS = [
    "show", "shows", "turnê", "turne", "festival de música", "festival de musica",
    "novela", "balada", "boate", "carnaval",
    # estilos musicais seculares — só passa se for exceção gospel abaixo
    "sertanejo", "pagode", "funk", "rock", "rap", "trap", "axé", "axe",
    "forró", "forro", "samba", "eletrônica", "eletronica", "k-pop", "kpop",
    "pop nacional", "cantora pop", "cantor pop",
]

# Reality show e fofoca de celebridade: bloqueados sempre, sem exceção
# gospel — o boletim deve se ater ao essencial (economia, política,
# esportes, entretenimento relevante etc), não vida alheia de famoso.
GOSSIP_TERMS = [
    "reality show", "bbb", "big brother", "a fazenda", "power couple",
    "ex-bbb", "ex-participante", "famosos", "celebridade", "affair",
    "climão", "climao", "treta", "fofoca", "vida amorosa", "términou o namoro",
    "terminou o namoro", "term de namoro", "romance de", "namoro de", "affair de",
    "relacionamento", "se separaram", "reataram", "estão namorando", "estao namorando",
    "novo romance", "términou", "terminaram o", "traição", "traicao",
]

# Artefatos de placar ao vivo do RSS de esporte — não são manchete de
# verdade, são tickers de partida em andamento.
LIVE_SCORE_MARKERS = ["ao vivo", "globoesporte.com"]

GOSPEL_EXCEPTIONS = ["gospel", "evangélic", "evangelic", "cristã", "crista", "igreja", "adoração", "adoracao", "louvor"]


def is_appropriate(headline):
    lowered = headline.lower()
    if any(term in lowered for term in BLOCKED_TERMS):
        return False
    if any(term in lowered for term in GOSSIP_TERMS):
        return False
    if any(term in lowered for term in LIVE_SCORE_MARKERS):
        return False
    if any(term in lowered for term in ENTERTAINMENT_TERMS):
        return any(term in lowered for term in GOSPEL_EXCEPTIONS)
    return True


def _creds():
    api_key = os.environ.get("AZURACAST_API_KEY")
    base_url = os.environ.get("AZURACAST_BASE_URL")
    station = os.environ.get("AZURACAST_STATION")
    eleven_api_key = os.environ.get("ELEVENLABS_API_KEY")
    eleven_voice_id = os.environ.get("ELEVENLABS_VOICE_ID")
    if not api_key or not base_url or not station or not eleven_api_key or not eleven_voice_id:
        print("SKIP: alguma credencial (AZURACAST_*, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID) não configurada.")
        sys.exit(0)
    return api_key, base_url.rstrip("/"), station, eleven_api_key, eleven_voice_id


def _fetch_feed_titles(url):
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    titles = [item.findtext("title") for item in root.findall(".//item")]
    return [t.strip() for t in titles if t]


def fetch_headlines():
    # Roda a ordem das editorias por hora, pra variar o que entra nas 3
    # manchetes ao longo do dia em vez de sempre priorizar as mesmas.
    start = datetime.datetime.utcnow().hour % len(CATEGORY_FEEDS)
    rotated = CATEGORY_FEEDS[start:] + CATEGORY_FEEDS[:start]

    headlines = []
    for _name, url in rotated:
        try:
            titles = _fetch_feed_titles(url)
        except requests.RequestException:
            continue
        for t in titles[:HEADLINE_POOL_SIZE]:
            if is_appropriate(t):
                headlines.append(t)
                break
        if len(headlines) >= HEADLINE_COUNT:
            break
    return headlines[:HEADLINE_COUNT]


def build_script(headlines):
    if not headlines:
        return None
    lines = [
        "Você está ouvindo o boletim de notícias da Rádio Encontro de Adoradores.",
        "As principais notícias desta hora:",
    ]
    for h in headlines:
        lines.append(h if h.endswith((".", "!", "?")) else f"{h}.")
    lines.append("Fique com a gente.")
    lines.append("Voltamos com mais música e adoração.")
    return " ".join(lines)


def _generate_voice(text, eleven_api_key, eleven_voice_id, retries=4):
    for attempt in range(retries):
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{eleven_voice_id}",
            params={"output_format": f"pcm_{ELEVENLABS_SAMPLE_RATE}"},
            headers={
                "xi-api-key": eleven_api_key,
                "Content-Type": "application/json",
                "Accept": "audio/pcm",
            },
            json={
                "text": text,
                "model_id": ELEVENLABS_MODEL_ID,
            },
            timeout=120,
        )
        if resp.status_code == 429 and attempt < retries - 1:
            time.sleep(2 ** attempt * 3)  # 3s, 6s, 12s...
            continue
        resp.raise_for_status()
        return resp.content
    raise RuntimeError("Geração de voz falhou: excedeu tentativas após 429.")


def generate_audio(text, path, eleven_api_key, eleven_voice_id):
    pcm = _generate_voice(text, eleven_api_key, eleven_voice_id)
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)  # PCM 16-bit
        out.setframerate(ELEVENLABS_SAMPLE_RATE)
        out.writeframes(pcm)


def mix_with_music(voice_path, music_path, output_path):
    # Loopa a trilha de fundo, abaixa o volume dela e mixa com a voz;
    # duration=first corta a mixagem no tamanho da voz (faixa da locução).
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", voice_path,
            "-stream_loop", "-1", "-i", music_path,
            "-filter_complex",
            f"[1:a]volume={MUSIC_BED_VOLUME}[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=3",
            "-ac", "1",
            output_path,
        ],
        check=True,
        capture_output=True,
    )


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
    api_key, base_url, station, eleven_api_key, eleven_voice_id = _creds()

    headlines = fetch_headlines()
    script = build_script(headlines)
    if not script:
        print("SKIP: nenhuma manchete encontrada no RSS.")
        sys.exit(0)

    print(f"Boletim: {len(headlines)} manchete(s).")
    generate_audio(script, VOICE_AUDIO_PATH, eleven_api_key, eleven_voice_id)

    if os.path.exists(MUSIC_BED_PATH):
        mix_with_music(VOICE_AUDIO_PATH, MUSIC_BED_PATH, LOCAL_AUDIO_PATH)
    else:
        os.replace(VOICE_AUDIO_PATH, LOCAL_AUDIO_PATH)

    playlist_id = ensure_playlist(base_url, api_key, station)
    remove_previous_bulletin(base_url, api_key, station)
    media_id = upload_bulletin(base_url, api_key, station, LOCAL_AUDIO_PATH)
    assign_playlist(base_url, api_key, station, media_id, playlist_id)

    print(f"OK: boletim publicado (media_id={media_id}, playlist_id={playlist_id}).")


if __name__ == "__main__":
    main()
