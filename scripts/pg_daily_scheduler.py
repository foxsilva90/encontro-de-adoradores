#!/usr/bin/env python3
"""
Atualiza as playlists de PG do AzuraCast para tocar apenas o programa do dia.
Detecta automaticamente pela pasta (Semana DD a DD/Mês) e ordem dos arquivos.
- pg_006 = 1º dia da semana, pg_007 = 2º, etc.
- Roda via GitHub Actions junto com azuracast_scheduler.py
"""
import os
import re
import sys
import requests
from datetime import date

API_KEY = os.environ["AZURACAST_API_KEY"]
BASE_URL = "https://radio.encontrodeadoradores.com/api"
STATION_ID = 1
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

MONTH_MAP = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12
}

PG_PLAYLIST_KEYWORDS = [
    "PG Encontro de Adoradores - 10h",
    "PG Encontro de Adoradores - 17h",
]

today = date.today()
print(f"Date: {today}")


def get_playlists():
    r = requests.get(f"{BASE_URL}/station/{STATION_ID}/playlists", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_all_pg_files():
    files, page = [], 1
    while True:
        r = requests.get(
            f"{BASE_URL}/station/{STATION_ID}/files",
            headers=HEADERS,
            params={"rowCount": 100, "current": page, "searchPhrase": "PG Encontro de Adoradores"},
        )
        r.raise_for_status()
        data = r.json()
        rows = data.get("rows", [])
        if not rows:
            break
        files.extend(rows)
        if len(rows) < 100:
            break
        page += 1
    return files


def update_file_playlists(file_id, playlist_ids):
    r = requests.put(
        f"{BASE_URL}/station/{STATION_ID}/file/{file_id}",
        headers=HEADERS,
        json={"playlists": playlist_ids},
    )
    r.raise_for_status()


def parse_week_start(folder_path):
    match = re.search(r"[Ss]emana\s+(\d+)\s+a\s+\d+[/\s]+(\w+)", folder_path)
    if not match:
        return None
    day = int(match.group(1))
    month_str = match.group(2)[:3].lower()
    month = MONTH_MAP.get(month_str)
    if not month:
        return None
    return date(today.year, month, day)


def get_file_playlist_ids(f):
    return [p["id"] if isinstance(p, dict) else p for p in f.get("playlists", [])]


# --- Main ---

all_playlists = get_playlists()
pg_playlists = {
    pl["id"]: pl
    for pl in all_playlists
    if any(kw in pl["name"] for kw in PG_PLAYLIST_KEYWORDS)
}

if not pg_playlists:
    print("ERROR: PG playlists not found")
    sys.exit(1)

print(f"Playlists: {[pl['name'] for pl in pg_playlists.values()]}")
pg_playlist_ids = set(pg_playlists.keys())

pg_files = get_all_pg_files()

# Group files by week folder
week_groups = {}
for f in pg_files:
    path = f.get("path", "")
    m = re.search(r"[Ss]emana [^/]+", path)
    if m:
        week_groups.setdefault(m.group(0), []).append(f)

# Find today's file
today_file = None
for week_key, files in week_groups.items():
    start = parse_week_start(week_key)
    if not start:
        continue
    files_sorted = sorted(files, key=lambda x: x.get("path", ""))
    day_idx = (today - start).days
    if 0 <= day_idx < len(files_sorted):
        today_file = files_sorted[day_idx]
        print(f"Today's file: {today_file['path'].split('/')[-1]} (day {day_idx}, week starts {start})")
        break

if not today_file:
    print(f"ERROR: No file found for {today}")
    sys.exit(1)

# Update playlists: only today's file stays in PG playlists
errors = []

for f in pg_files:
    file_pl_ids = get_file_playlist_ids(f)
    in_pg = [pid for pid in file_pl_ids if pid in pg_playlist_ids]

    if not in_pg and f["id"] != today_file["id"]:
        continue

    if f["id"] == today_file["id"]:
        missing = [pid for pid in pg_playlist_ids if pid not in file_pl_ids]
        if missing:
            try:
                update_file_playlists(f["id"], file_pl_ids + list(missing))
                print(f"Added to playlists: {f['path'].split('/')[-1]}")
            except Exception as e:
                print(f"ERROR adding today's file: {e}")
                errors.append(str(e))
        else:
            print(f"Already in playlists: {f['path'].split('/')[-1]}")
    else:
        new_pls = [pid for pid in file_pl_ids if pid not in pg_playlist_ids]
        try:
            update_file_playlists(f["id"], new_pls)
            print(f"Removed: {f['path'].split('/')[-1]}")
        except Exception as e:
            print(f"ERROR removing {f['path'].split('/')[-1]}: {e}")
            errors.append(str(e))

if errors:
    print(f"\nFailed: {errors}")
    sys.exit(1)

print("Done.")
