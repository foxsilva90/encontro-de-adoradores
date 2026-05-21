#!/usr/bin/env python3
"""
Atualiza playlists de PG do AzuraCast para tocar apenas o programa do dia.
- Semana atual detectada pelo nome da playlist: "PG ... - Xh (DD a DD/Mês)"
- Arquivos buscados pela pasta: "Semana DD a DD"
- Ordem alfabética dos arquivos = ordem dos dias
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

PROGRAM_GROUPS = [
    {
        "name": "PG Encontro de Adoradores",
        "search": "PG Encontro de Adoradores",
        "keywords": [
            "PG Encontro de Adoradores - 10h",
            "PG Encontro de Adoradores - 17h",
        ],
    },
    {
        "name": "PG Lugar Secreto",
        "search": "PG Lugar Secreto",
        "keywords": [
            "PG Lugar Secreto (Elivelton) - 03h",
            "PG Lugar Secreto (Elivelton) - 12h",
        ],
    },
]

today = date.today()
print(f"Date: {today}")


def get_playlists():
    r = requests.get(f"{BASE_URL}/station/{STATION_ID}/playlists", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_files(search_phrase):
    files, page = [], 1
    while True:
        r = requests.get(
            f"{BASE_URL}/station/{STATION_ID}/files",
            headers=HEADERS,
            params={"rowCount": 100, "current": page, "searchPhrase": search_phrase},
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


def parse_playlist_week(name):
    """Extract (week_start, start_day, end_day) from '(DD a DD/Mês)' in playlist name."""
    m = re.search(r"\((\d+)\s+a\s+(\d+)/(\w+)\)", name)
    if not m:
        return None, None, None
    start_day = int(m.group(1))
    end_day = int(m.group(2))
    month_str = m.group(3)[:3].lower()
    month = MONTH_MAP.get(month_str)
    if not month:
        return None, None, None
    return date(today.year, month, start_day), start_day, end_day


def get_file_playlist_ids(f):
    return [p["id"] if isinstance(p, dict) else p for p in f.get("playlists", [])]


def process_group(group, all_playlists):
    name = group["name"]
    print(f"\n--- {name} ---")

    pg_playlists = {
        pl["id"]: pl
        for pl in all_playlists
        if any(kw in pl["name"] for kw in group["keywords"])
    }

    if not pg_playlists:
        print(f"No playlists found, skipping.")
        return []

    print(f"Playlists: {[pl['name'] for pl in pg_playlists.values()]}")

    # Find current week from playlist names
    week_start = None
    week_end = None
    current_week_pl_ids = set()

    for pl_id, pl in pg_playlists.items():
        wstart, start_day, end_day = parse_playlist_week(pl["name"])
        if not wstart:
            continue
        wend = date(today.year, wstart.month, end_day)
        if wstart <= today <= wend:
            week_start = wstart
            week_end = wend
            current_week_pl_ids.add(pl_id)

    if not week_start:
        print(f"No current week playlist for {today}, skipping.")
        return []

    week_folder = f"Semana {week_start.day} a {week_end.day}"
    print(f"Current week: {week_folder} ({week_start} to {week_end})")
    print(f"Active playlists: {[pg_playlists[pid]['name'] for pid in current_week_pl_ids]}")

    all_files = get_files(group["search"])
    week_files = [f for f in all_files if week_folder in f.get("path", "")]
    week_files_sorted = sorted(week_files, key=lambda x: x.get("path", ""))
    print(f"Week files: {[f['path'].split('/')[-1] for f in week_files_sorted]}")

    if not week_files_sorted:
        print(f"All files found ({len(all_files)}): {[f.get('path','?') for f in all_files[:10]]}")
        print(f"ERROR: No files in folder '{week_folder}'")
        return [f"[{name}] No files in '{week_folder}'"]

    day_idx = (today - week_start).days
    print(f"Day index: {day_idx}")

    if not (0 <= day_idx < len(week_files_sorted)):
        print(f"ERROR: day_idx {day_idx} out of range (have {len(week_files_sorted)} files)")
        return [f"[{name}] day_idx {day_idx} out of range"]

    today_file = week_files_sorted[day_idx]
    print(f"Today's file: {today_file['path'].split('/')[-1]}")

    errors = []
    for f in week_files_sorted:
        file_pl_ids = get_file_playlist_ids(f)
        in_current = [pid for pid in file_pl_ids if pid in current_week_pl_ids]

        if f["id"] == today_file["id"]:
            missing = [pid for pid in current_week_pl_ids if pid not in file_pl_ids]
            if missing:
                try:
                    update_file_playlists(f["id"], file_pl_ids + missing)
                    print(f"Added: {f['path'].split('/')[-1]}")
                except Exception as e:
                    print(f"ERROR adding {f['path'].split('/')[-1]}: {e}")
                    errors.append(str(e))
            else:
                print(f"Already in playlists: {f['path'].split('/')[-1]}")
        else:
            if in_current:
                new_pls = [pid for pid in file_pl_ids if pid not in current_week_pl_ids]
                try:
                    update_file_playlists(f["id"], new_pls)
                    print(f"Removed: {f['path'].split('/')[-1]}")
                except Exception as e:
                    print(f"ERROR removing {f['path'].split('/')[-1]}: {e}")
                    errors.append(str(e))
            else:
                print(f"Already not in playlists: {f['path'].split('/')[-1]}")

    return errors


# --- Main ---

all_playlists = get_playlists()
all_errors = []

for group in PROGRAM_GROUPS:
    errs = process_group(group, all_playlists)
    all_errors.extend(errs)

if all_errors:
    print(f"\nFailed: {all_errors}")
    sys.exit(1)

print("\nDone.")
