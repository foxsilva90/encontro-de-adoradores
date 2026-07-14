#!/usr/bin/env python3
"""
Detecta episódio novo do AdoraCast e publica na Página do Facebook.

Usa o endpoint público do próprio site (/api/podcasts) — assim não duplica a
chave do YouTube. Guarda o último vídeo publicado em scripts/fb_state.json.
Se o mais recente for diferente do salvo, publica e atualiza o estado.
O workflow faz commit do estado atualizado quando há episódio novo.
"""
import json
import os
import sys

import requests

from facebook_lib import post_link

FEED_URL = "https://encontrodeadoradores.com/api/podcasts"
STATE_PATH = os.path.join(os.path.dirname(__file__), "fb_state.json")


def carregar_estado():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def salvar_estado(estado):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


try:
    r = requests.get(FEED_URL, timeout=30)
    r.raise_for_status()
    itens = r.json().get("items", [])
except requests.exceptions.RequestException as e:
    print(f"SKIP: feed de podcasts indisponível ({e})")
    sys.exit(0)

if not itens:
    print("SKIP: nenhum episódio no feed.")
    sys.exit(0)

mais_recente = itens[0]
vid = mais_recente.get("videoId")
titulo = (mais_recente.get("title") or "").strip()

if not vid:
    print("SKIP: episódio sem videoId.")
    sys.exit(0)

estado = carregar_estado()
if estado.get("ultimo_podcast") == vid:
    print(f"Sem novidade — último já publicado ({vid}).")
    sys.exit(0)

link = f"https://www.youtube.com/watch?v={vid}"
mensagem = (
    "🎙 NOVO EPISÓDIO DO ADORACAST!\n\n"
    f"{titulo}\n\n"
    "Assista agora no nosso canal 👇\n\n"
    "🎧 E ouça a Rádio Encontro de Adoradores ao vivo, 24h: "
    "https://encontrodeadoradores.com\n\n"
    "#AdoraCast #EncontroDeAdoradores #Podcast #Gospel"
)

print(f"Episódio novo: {titulo} ({vid})")
post_link(mensagem, link)

estado["ultimo_podcast"] = vid
salvar_estado(estado)
print("Estado atualizado.")
