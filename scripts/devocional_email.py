#!/usr/bin/env python3
"""Envia o devocional do dia por e-mail a todos os cadastrados (Supabase + Resend). Roda 1x/dia."""
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from devocionais import devocional_do_dia

FROM_EMAIL = "Rádio Encontro de Adoradores <devocional@encontrodeadoradores.com>"
LOGO_URL = "https://encontrodeadoradores.com/logo_tunein_1200x1200.jpg"


def _creds():
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    resend_key = os.environ.get("RESEND_API_KEY")
    if not supabase_url or not service_key or not resend_key:
        print("Credenciais ausentes (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / RESEND_API_KEY) — pulando.")
        sys.exit(0)
    return supabase_url, service_key, resend_key


def _fetch_subscribers(supabase_url, service_key):
    resp = requests.get(
        f"{supabase_url}/rest/v1/devocional_subscribers",
        params={"select": "nome,email"},
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _email_html(nome, dia_semana, ref, verso, reflexao):
    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; color: #1a1a1a;">
      <div style="text-align:center;margin-bottom:16px;"><img src="{LOGO_URL}" alt="Encontro de Adoradores" width="80" height="80" style="border-radius:50%;"></div>
      <h2 style="color: #0D2A4A;">Devocional do dia — {dia_semana}</h2>
      <p>Olá, {nome}!</p>
      <blockquote style="border-left: 3px solid #F5A324; margin: 16px 0; padding: 4px 16px; font-style: italic;">
        "{verso}"<br><strong>— {ref}</strong>
      </blockquote>
      <p>{reflexao}</p>
      <p><a href="https://encontrodeadoradores.com" style="background:#0D2A4A;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none;display:inline-block;">Ouvir a rádio ao vivo</a></p>
      <p style="margin-top:24px;font-size:13px;color:#666;">Rádio Encontro de Adoradores</p>
    </div>
    """


def _send_email(resend_key, nome, email, dia_semana, ref, verso, reflexao):
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {resend_key}"},
        json={
            "from": FROM_EMAIL,
            "to": email,
            "subject": f"Devocional do dia — {dia_semana} 🙏",
            "html": _email_html(nome, dia_semana, ref, verso, reflexao),
        },
        timeout=30,
    )
    return resp.ok


DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]


def main():
    supabase_url, service_key, resend_key = _creds()

    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    ref, verso, reflexao = devocional_do_dia(agora.day)
    dia_semana = DIAS[agora.weekday()].capitalize()

    subscribers = _fetch_subscribers(supabase_url, service_key)
    print(f"Devocional {agora.day:02d} — {ref} — {len(subscribers)} inscrito(s)")

    ok_count = 0
    for sub in subscribers:
        nome = sub.get("nome") or "amigo(a)"
        email = sub.get("email")
        if not email:
            continue
        if _send_email(resend_key, nome, email, dia_semana, ref, verso, reflexao):
            ok_count += 1
        time.sleep(0.5)

    print(f"Enviados: {ok_count}/{len(subscribers)}")


if __name__ == "__main__":
    main()
