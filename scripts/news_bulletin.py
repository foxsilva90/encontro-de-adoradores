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
import re
import subprocess
import sys
import time
import wave
from xml.etree import ElementTree

import requests

ELEVENLABS_MODEL_ID = "eleven_v3"
ELEVENLABS_SAMPLE_RATE = 24000

# Feed(s) gospel — sempre tenta reservar 1 das manchetes pra cá.
GOSPEL_FEEDS = [
    "https://guiame.com.br/rss",
    "https://noticias.gospelmais.com.br/feed",
]

# Feeds por editoria pras manchetes restantes — cobre só o essencial
# (economia, política, mundo, entretenimento), com fontes variadas além
# do G1. Gira a ordem a cada hora pra não ficar sempre nas mesmas
# categorias. Esportes fora, a pedido.
CATEGORY_FEEDS = [
    ("Economia", "https://g1.globo.com/rss/g1/economia/"),
    ("Política", "https://g1.globo.com/rss/g1/politica/"),
    ("Mundo", "https://g1.globo.com/rss/g1/mundo/"),
    ("Entretenimento", "https://g1.globo.com/rss/g1/pop-arte/"),
    ("Geral", "https://www.cnnbrasil.com.br/feed/"),
    ("Geral", "https://rss.uol.com.br/feed/noticias.xml"),
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


def _clean_env(name):
    # Remove BOM/espaços perdidos que secrets configurados via alguns
    # clientes (ex. pipe do PowerShell pro gh CLI) podem injetar.
    value = os.environ.get(name)
    return value.strip().lstrip("﻿") if value else value


def _creds():
    api_key = _clean_env("AZURACAST_API_KEY")
    base_url = _clean_env("AZURACAST_BASE_URL")
    station = _clean_env("AZURACAST_STATION")
    eleven_api_key = _clean_env("ELEVENLABS_API_KEY")
    eleven_voice_id = _clean_env("ELEVENLABS_VOICE_ID")
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


QUOTE_CHARS = "\"'‘’“”"


def _pick_headline(titles):
    for t in titles[:HEADLINE_POOL_SIZE]:
        if not is_appropriate(t):
            continue
        # Pula manchete com fala citada em vez de tentar remendar — cortar
        # só o trecho entre aspas costuma quebrar a gramática da frase.
        if any(c in t for c in QUOTE_CHARS):
            continue
        if len(t) >= 20:
            return t
    return None


def fetch_headlines():
    headlines = []

    # Reserva 1 manchete de fonte gospel quando disponível.
    for url in GOSPEL_FEEDS:
        try:
            titles = _fetch_feed_titles(url)
        except requests.RequestException:
            continue
        found = _pick_headline(titles)
        if found:
            headlines.append(found)
            break

    # Roda a ordem das editorias por hora, pra variar o que entra nas
    # manchetes restantes ao longo do dia em vez de sempre priorizar as
    # mesmas fontes/categorias.
    start = datetime.datetime.utcnow().hour % len(CATEGORY_FEEDS)
    rotated = CATEGORY_FEEDS[start:] + CATEGORY_FEEDS[:start]

    for _name, url in rotated:
        if len(headlines) >= HEADLINE_COUNT:
            break
        try:
            titles = _fetch_feed_titles(url)
        except requests.RequestException:
            continue
        found = _pick_headline(titles)
        if found:
            headlines.append(found)
    return headlines[:HEADLINE_COUNT]


def build_script(headlines):
    if not headlines:
        return None
    blocks = [
        "Você está ouvindo o boletim de notícias da Rádio Encontro de Adoradores. As principais notícias desta hora.",
    ]
    for h in headlines:
        blocks.append(h if h.endswith((".", "!", "?")) else f"{h}.")
    blocks.append("Fique com a gente. Voltamos com mais música e adoração.")
    # Cada bloco vira uma chamada de voz separada (ver generate_audio) —
    # assim a pausa fica só entre uma notícia e outra, controlada por nós,
    # em vez de depender da ElevenLabs pausar certo dentro de um texto
    # corrido (o que também pausava em vírgulas no meio da frase).
    return blocks


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


PAUSE_BETWEEN_ITEMS = 0.7  # segundos de silêncio real entre cada bloco do boletim
TRAILING_PADDING = " Um abraço e continue com a gente."
VOICE_FADE_OUT = 0.3  # segundos
SILENCE_NOISE_DB = "-28dB"
SILENCE_MIN_DURATION = 0.15  # segundos
GAP_MUSIC_VOLUME = 0.20  # trilha mais alta durante as pausas entre blocos


def _get_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def _detect_silences(path):
    result = subprocess.run(
        [
            "ffmpeg", "-i", path, "-af",
            f"silencedetect=noise={SILENCE_NOISE_DB}:d={SILENCE_MIN_DURATION}",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    log = result.stderr
    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", log)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", log)]
    return list(zip(starts, ends))


def _protect_last_segment(pcm):
    # A ElevenLabs às vezes corta a última fração de segundo do áudio de
    # forma abrupta. Gera esse bloco com uma frase descartável colada no
    # final (TRAILING_PADDING), detecta a pausa entre o conteúdo real e
    # essa frase, e corta ali — a frase nunca fica audível. Como esse
    # bloco é só "Fique com a gente. Voltamos com mais música e adoração."
    # + a frase descartável (sem vírgulas), a única pausa esperada aqui é
    # exatamente essa fronteira, sem ambiguidade com pausas de vírgula.
    tmp_path = "_tail_segment.wav"
    with wave.open(tmp_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(ELEVENLABS_SAMPLE_RATE)
        w.writeframes(pcm)
    silences = _detect_silences(tmp_path)
    duration = _get_duration(tmp_path)
    os.remove(tmp_path)

    # Corta no FIM da pausa (não no início) — o início já é onde
    # "adoração" está decaindo, cortar ali arrisca comer o final da
    # palavra. O fim da pausa é o ponto seguro logo antes de "Um" começar.
    trim_end = silences[-1][1] if silences else max(duration - 2.0, 0.1)
    trim_frames = int(trim_end * ELEVENLABS_SAMPLE_RATE)
    return pcm[: trim_frames * 2]  # 2 bytes por sample (PCM 16-bit)


def generate_audio(blocks, path, eleven_api_key, eleven_voice_id):
    clips = []
    for i, block in enumerate(blocks):
        is_last = i == len(blocks) - 1
        text = f"{block}{TRAILING_PADDING}" if is_last else block
        pcm = _generate_voice(text, eleven_api_key, eleven_voice_id)
        if is_last:
            pcm = _protect_last_segment(pcm)
        clips.append(pcm)

    silence_bytes = b"\x00\x00" * int(ELEVENLABS_SAMPLE_RATE * PAUSE_BETWEEN_ITEMS)

    gaps = []
    t = 0.0
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)  # PCM 16-bit
        out.setframerate(ELEVENLABS_SAMPLE_RATE)
        for i, pcm in enumerate(clips):
            out.writeframes(pcm)
            t += len(pcm) / 2 / ELEVENLABS_SAMPLE_RATE
            if i < len(clips) - 1:
                out.writeframes(silence_bytes)
                gaps.append((t, t + PAUSE_BETWEEN_ITEMS))
                t += PAUSE_BETWEEN_ITEMS
    return gaps


def mix_with_music(voice_path, music_path, output_path, gaps=None):
    voice_duration = _get_duration(voice_path)
    fade_start = max(voice_duration - VOICE_FADE_OUT, 0)

    if gaps:
        volume_expr = MUSIC_BED_VOLUME
        for start, end in gaps:
            volume_expr = f"if(between(t,{start:.2f},{end:.2f}),{GAP_MUSIC_VOLUME},{volume_expr})"
        bg_filter = f"volume=eval=frame:volume='{volume_expr}'"
    else:
        bg_filter = f"volume={MUSIC_BED_VOLUME}"

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", voice_path,
            "-stream_loop", "-1", "-i", music_path,
            "-filter_complex",
            (
                f"[0:a]afade=t=out:st={fade_start:.3f}:d={VOICE_FADE_OUT}[voice];"
                f"[1:a]{bg_filter}[bg];"
                "[voice][bg]amix=inputs=2:duration=first:dropout_transition=3"
            ),
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
    gaps = generate_audio(script, VOICE_AUDIO_PATH, eleven_api_key, eleven_voice_id)

    if os.path.exists(MUSIC_BED_PATH):
        mix_with_music(VOICE_AUDIO_PATH, MUSIC_BED_PATH, LOCAL_AUDIO_PATH, gaps)
    else:
        os.replace(VOICE_AUDIO_PATH, LOCAL_AUDIO_PATH)

    playlist_id = ensure_playlist(base_url, api_key, station)
    remove_previous_bulletin(base_url, api_key, station)
    media_id = upload_bulletin(base_url, api_key, station, LOCAL_AUDIO_PATH)
    assign_playlist(base_url, api_key, station, media_id, playlist_id)

    print(f"OK: boletim publicado (media_id={media_id}, playlist_id={playlist_id}).")


if __name__ == "__main__":
    main()
