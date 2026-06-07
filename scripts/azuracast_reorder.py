#!/usr/bin/env python3
"""
Detecta músicas novas na playlist Louvores 24h e as posiciona
para tocar logo após a música atual.

Roda automaticamente via cron a cada 6h no VPS:
  0 */6 * * * python3 /root/reorder_playlist.py >> /root/reorder.log 2>&1
"""
import heapq
import os
import time
import requests
from collections import defaultdict, deque
from datetime import datetime, timezone

API_KEY = os.environ["AZURACAST_API_KEY"]
BASE_URL = "https://radio.encontrodeadoradores.com/api"
STATION_ID = 1
PLAYLIST_ID = 2  # Louvores 24h
LAST_RUN_FILE = "/root/.reorder_last_run"

HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def load_last_run():
    if os.path.exists(LAST_RUN_FILE):
        with open(LAST_RUN_FILE) as f:
            return float(f.read().strip())
    return 0.0


def save_last_run():
    with open(LAST_RUN_FILE, "w") as f:
        f.write(str(time.time()))


def fetch_order():
    r = requests.get(
        f"{BASE_URL}/station/{STATION_ID}/playlist/{PLAYLIST_ID}/order",
        headers=HEADERS,
    )
    r.raise_for_status()
    return r.json()


def get_nowplaying_song_id():
    r = requests.get(f"{BASE_URL}/nowplaying/{STATION_ID}")
    r.raise_for_status()
    return r.json().get("now_playing", {}).get("song", {}).get("id")


def apply_order(ordered_ids):
    resp = requests.put(
        f"{BASE_URL}/station/{STATION_ID}/playlist/{PLAYLIST_ID}/order",
        headers=HEADERS,
        json=ordered_ids,
    )
    resp.raise_for_status()


def interleave(items):
    """Max-heap: minimiza músicas consecutivas do mesmo artista."""
    buckets = defaultdict(list)
    for item in items:
        artist = (item.get("media", {}).get("artist") or "").strip() or "Desconhecido"
        buckets[artist].append(item["id"])

    heap = [(-len(ids), artist, deque(ids)) for artist, ids in buckets.items()]
    heapq.heapify(heap)

    ordered = []
    prev_artist = None
    while heap:
        neg, artist, ids = heapq.heappop(heap)
        if artist == prev_artist and heap:
            neg2, artist2, ids2 = heapq.heappop(heap)
            ordered.append(ids2.popleft())
            prev_artist = artist2
            if ids2:
                heapq.heappush(heap, (-len(ids2), artist2, ids2))
            heapq.heappush(heap, (neg, artist, ids))
        else:
            ordered.append(ids.popleft())
            prev_artist = artist
            if ids:
                heapq.heappush(heap, (-len(ids), artist, ids))
    return ordered


def main():
    last_run = load_last_run()
    if last_run:
        last_run_str = datetime.fromtimestamp(last_run, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        last_run_str = "nunca"
    log(f"Última execução: {last_run_str}")

    items = fetch_order()
    log(f"Total na playlist: {len(items)} músicas")

    # Músicas novas = uploaded_at depois da última execução
    new_items = [i for i in items if i.get("media", {}).get("uploaded_at", 0) > last_run]
    old_items = [i for i in items if i not in new_items]

    if not new_items:
        log("Nenhuma música nova. Nada a fazer.")
        save_last_run()
        return

    log(f"Músicas novas detectadas: {len(new_items)}")
    for i in new_items:
        m = i.get("media", {})
        log(f"  + {m.get('artist', '?')} - {m.get('title', '?')}")

    # Ordena músicas existentes intercaladas
    old_ordered = interleave(old_items)
    # Ordena músicas novas intercaladas entre si
    new_ordered = interleave(new_items)

    # Descobre posição atual na playlist pra inserir novas LOGO APÓS
    insert_pos = 0
    try:
        nowplaying_song_id = get_nowplaying_song_id()
        if nowplaying_song_id:
            song_id_map = {
                i.get("media", {}).get("song_id"): i["id"]
                for i in old_items
            }
            current_spm = song_id_map.get(nowplaying_song_id)
            if current_spm and current_spm in old_ordered:
                insert_pos = old_ordered.index(current_spm) + 1
                log(f"Música atual na posição {insert_pos} — novas entram logo depois")
            else:
                log("Música atual não encontrada na lista existente — novas vão ao início")
    except Exception as e:
        log(f"Aviso: não consegui detectar música atual ({e}) — novas vão ao início")

    # Monta ordem final: [antes do atual] + [novas] + [depois do atual]
    final_order = old_ordered[:insert_pos] + new_ordered + old_ordered[insert_pos:]

    first_new = insert_pos + 1
    last_new = insert_pos + len(new_ordered)
    log(f"Novas músicas tocam nas posições {first_new} a {last_new} (logo em seguida)")
    log(f"Aplicando ordem ({len(final_order)} músicas)...")
    apply_order(final_order)
    log("Concluído.")
    save_last_run()


if __name__ == "__main__":
    main()
