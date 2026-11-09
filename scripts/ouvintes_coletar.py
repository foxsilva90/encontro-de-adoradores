#!/usr/bin/env python3
"""
Coleta as sessões de ouvintes do AzuraCast e acumula em arquivos diários.

O AzuraCast não mantém o histórico de conexões por muito tempo, então este
script roda várias vezes ao dia (GitHub Actions) e grava cada sessão em
<dir>/AAAA-MM-DD.json (data no horário de Brasília). Sessões repetidas entre
coletas são mescladas pela chave (hash do ouvinte + início da conexão).

Privacidade (LGPD): o IP NÃO é gravado — só o hash anônimo que o próprio
AzuraCast gera, cidade/país e o tipo de aparelho.

Uso: python ouvintes_coletar.py --dir caminho/para/dados
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE_URL = os.environ.get("AZURACAST_BASE_URL", "https://radio.encontrodeadoradores.com").rstrip("/")
STATION_ID = os.environ.get("AZURACAST_STATION", "1")
BRT = timezone(timedelta(hours=-3))
TIMEOUT_S = 60


def buscar_sessoes(api_key: str, inicio: datetime, fim: datetime) -> list:
    url = f"{BASE_URL}/api/station/{STATION_ID}/listeners"
    params = {"start": inicio.isoformat(timespec="seconds"), "end": fim.isoformat(timespec="seconds")}
    r = requests.get(url, headers={"X-API-Key": api_key}, params=params, timeout=TIMEOUT_S)
    r.raise_for_status()
    dados = r.json()
    if not isinstance(dados, list):
        raise ValueError(f"Resposta inesperada da API: {str(dados)[:200]}")
    return dados


def resumir_sessao(s: dict) -> dict:
    """Mantém só o necessário para o relatório — sem IP."""
    device = s.get("device") or {}
    loc = s.get("location") or {}
    return {
        "hash": s.get("hash"),
        "inicio": s.get("connected_on"),
        "fim": s.get("connected_until"),
        "segundos": s.get("connected_time") or 0,
        "user_agent": (s.get("user_agent") or "")[:200],
        "cliente": device.get("client"),
        "is_bot": bool(device.get("is_bot")),
        "is_mobile": bool(device.get("is_mobile")),
        "is_browser": bool(device.get("is_browser")),
        "cidade": loc.get("city"),
        "estado": loc.get("region"),
        "pais": loc.get("country"),
    }


def chave(sessao: dict) -> str:
    return f"{sessao['hash']}:{sessao['inicio']}"


def mesclar(existentes: list, novas: list) -> list:
    """Retorna nova lista; para a mesma sessão fica a versão mais longa."""
    por_chave = {chave(s): s for s in existentes}
    for s in novas:
        atual = por_chave.get(chave(s))
        if atual is None or s["segundos"] >= atual["segundos"]:
            por_chave[chave(s)] = s
    return sorted(por_chave.values(), key=lambda s: (s["inicio"] or 0, s["hash"] or ""))


def agrupar_por_dia(sessoes: list) -> dict:
    dias = {}
    for s in sessoes:
        if not s["hash"] or not s["inicio"]:
            continue
        dia = datetime.fromtimestamp(s["inicio"], BRT).date().isoformat()
        dias.setdefault(dia, []).append(s)
    return dias


def gravar(pasta: Path, dias: dict) -> int:
    pasta.mkdir(parents=True, exist_ok=True)
    total_novas = 0
    for dia, novas in dias.items():
        arquivo = pasta / f"{dia}.json"
        existentes = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else []
        mescladas = mesclar(existentes, novas)
        total_novas += len(mescladas) - len(existentes)
        arquivo.write_text(json.dumps(mescladas, ensure_ascii=False, indent=1), encoding="utf-8")
    return total_novas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="pasta onde ficam os JSON diários")
    args = parser.parse_args()

    api_key = os.environ.get("AZURACAST_API_KEY")
    if not api_key:
        print("ERRO: defina AZURACAST_API_KEY", file=sys.stderr)
        return 1

    agora = datetime.now(BRT)
    inicio = (agora - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        brutas = buscar_sessoes(api_key, inicio, agora)
    except requests.exceptions.RequestException as e:
        print(f"SKIP: AzuraCast indisponível ({e})")
        return 0

    sessoes = [resumir_sessao(s) for s in brutas]
    novas = gravar(Path(args.dir), agrupar_por_dia(sessoes))
    print(f"{len(sessoes)} sessões lidas, {novas} novas gravadas em {args.dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
