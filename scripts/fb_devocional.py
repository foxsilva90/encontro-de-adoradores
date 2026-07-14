#!/usr/bin/env python3
"""Publica o devocional do dia na Página do Facebook. Roda 1x/dia."""
from datetime import datetime
from zoneinfo import ZoneInfo

from devocionais import devocional_do_dia
from facebook_lib import post_text

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]

agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
ref, verso, reflexao = devocional_do_dia(agora.day)
dia_semana = DIAS[agora.weekday()].capitalize()

mensagem = (
    f"📖 DEVOCIONAL DO DIA — {dia_semana}\n\n"
    f"\"{verso}\"\n"
    f"— {ref}\n\n"
    f"{reflexao}\n\n"
    f"🎵 Ouça a Rádio Encontro de Adoradores ao vivo, 24h:\n"
    f"https://encontrodeadoradores.com\n\n"
    f"#EncontroDeAdoradores #Devocional #Fé #Gospel"
)

print(f"Devocional {agora.day:02d} — {ref}")
post_text(mensagem)
