#!/usr/bin/env python3
"""
Habilita/desabilita playlists do AzuraCast automaticamente com base nas datas
configuradas nos agendamentos (start_date / end_date).

- Playlists SEM datas no agendamento (ex: Louvores 24h) não são tocadas.
- Playlists com datas: habilitadas quando start_date <= amanhã E end_date >= hoje.
  (Habilita 1 dia antes do início para garantir que o AzuraCast reconheça antes da meia-noite.)
"""
import os
import sys
import requests
from datetime import date, timedelta

API_KEY = os.environ["AZURACAST_API_KEY"]
BASE_URL = "https://radio.encontrodeadoradores.com/api"
STATION_ID = 1
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

today = date.today()
tomorrow = today + timedelta(days=1)
print(f"Date: {today} (checking through: {tomorrow})")

r = requests.get(f"{BASE_URL}/station/{STATION_ID}/playlists", headers=HEADERS)
r.raise_for_status()
playlists = r.json()

errors = []

for pl in playlists:
    items = pl.get("schedule_items", [])
    dated_items = [i for i in items if i.get("start_date") and i.get("end_date")]

    if not dated_items:
        continue

    should_be_active = any(
        date.fromisoformat(i["start_date"]) <= tomorrow and
        date.fromisoformat(i["end_date"]) >= today
        for i in dated_items
    )

    currently_enabled = pl["is_enabled"]

    if should_be_active == currently_enabled:
        print(f"OK ({'on' if currently_enabled else 'off'}): {pl['name']}")
        continue

    try:
        t = requests.put(pl["links"]["toggle"], headers=HEADERS)
        t.raise_for_status()
        action = "ENABLED" if should_be_active else "DISABLED"
        print(f"{action}: {pl['name']}")
    except Exception as e:
        print(f"ERROR: {pl['name']}: {e}")
        errors.append(pl["name"])

if errors:
    print(f"\nFailed: {errors}")
    sys.exit(1)

print("Done.")
