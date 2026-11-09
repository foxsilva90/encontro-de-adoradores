#!/usr/bin/env python3
"""
Gera o relatório semanal de ouvintes únicos a partir dos JSON diários
gravados por ouvintes_coletar.py.

Conta como "pessoa" a sessão que:
  - não é robô/serviço (diretórios de rádio, monitores, bibliotecas HTTP);
  - ficou conectada pelo menos MIN_SEGUNDOS (descarta testes/sondagens).

Uso: python ouvintes_relatorio.py --dir dados/ouvintes --saida relatorio.md
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BRT = timezone(timedelta(hours=-3))
MIN_SEGUNDOS = 60
TOP_CIDADES = 10
DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

# Agentes que não são pessoas ouvindo: robôs de diretórios, monitores,
# bibliotecas de programação e reprodutores de servidor (relays).
PADRAO_ROBO = re.compile(
    r"bot|crawler|spider|lavf|ffmpeg|go-http-client|python|curl|wget|java/"
    r"|libwww|node-fetch|axios|amplitudeairplay|onlineradiobox|monitor|uptime|check",
    re.IGNORECASE,
)


def is_pessoa(s: dict) -> bool:
    if s.get("is_bot") or s.get("segundos", 0) < MIN_SEGUNDOS:
        return False
    return not PADRAO_ROBO.search(s.get("user_agent") or "")


def tipo_aparelho(s: dict) -> str:
    if s.get("is_mobile"):
        return "Celular (navegador)" if s.get("is_browser") else "Celular (app)"
    if s.get("is_browser"):
        return "Computador (navegador)"
    return "App / player de rádio"


def carregar(pasta: Path) -> list:
    sessoes = []
    for arquivo in sorted(pasta.glob("*.json")):
        sessoes.extend(json.loads(arquivo.read_text(encoding="utf-8")))
    return sessoes


def semana_de(ts: int) -> date:
    """Segunda-feira da semana (horário de Brasília)."""
    d = datetime.fromtimestamp(ts, BRT).date()
    return d - timedelta(days=d.weekday())


def local(s: dict) -> str:
    partes = [p for p in (s.get("cidade"), s.get("estado"), s.get("pais")) if p]
    return ", ".join(partes) or "Desconhecido"


def resumo_semana(sessoes: list) -> dict:
    pessoas = [s for s in sessoes if is_pessoa(s)]
    unicos = {s["hash"] for s in pessoas}
    por_dia = defaultdict(set)
    for s in pessoas:
        por_dia[datetime.fromtimestamp(s["inicio"], BRT).weekday()].add(s["hash"])
    primeiro_local = {}
    primeiro_aparelho = {}
    for s in pessoas:
        primeiro_local.setdefault(s["hash"], local(s))
        primeiro_aparelho.setdefault(s["hash"], tipo_aparelho(s))
    segundos = sum(s["segundos"] for s in pessoas)
    return {
        "unicos": len(unicos),
        "sessoes": len(pessoas),
        "horas": segundos / 3600,
        "media_min": (segundos / len(pessoas) / 60) if pessoas else 0,
        "por_dia": {d: len(h) for d, h in por_dia.items()},
        "cidades": Counter(primeiro_local.values()).most_common(TOP_CIDADES),
        "aparelhos": Counter(primeiro_aparelho.values()).most_common(),
        "robos": len({s["hash"] for s in sessoes} - unicos),
    }


def formatar_semana(inicio: date, r: dict) -> list:
    fim = inicio + timedelta(days=6)
    linhas = [
        f"## Semana {inicio:%d/%m} a {fim:%d/%m/%Y}",
        "",
        f"- **Ouvintes únicos:** {r['unicos']}",
        f"- **Sessões de escuta:** {r['sessoes']}",
        f"- **Horas ouvidas:** {r['horas']:.1f} h (média de {r['media_min']:.0f} min por sessão)",
        f"- Conexões descartadas (robôs, diretórios, testes < {MIN_SEGUNDOS}s): {r['robos']}",
        "",
        "| " + " | ".join(DIAS_SEMANA) + " |",
        "|" + "---|" * 7,
        "| " + " | ".join(str(r["por_dia"].get(i, 0)) for i in range(7)) + " |",
        "",
    ]
    if r["cidades"]:
        linhas += ["**De onde ouvem:** " + "; ".join(f"{c} ({n})" for c, n in r["cidades"]), ""]
    if r["aparelhos"]:
        linhas += ["**Como ouvem:** " + "; ".join(f"{a} ({n})" for a, n in r["aparelhos"]), ""]
    return linhas


def gerar(sessoes: list) -> str:
    semanas = defaultdict(list)
    for s in sessoes:
        if s.get("hash") and s.get("inicio"):
            semanas[semana_de(s["inicio"])].append(s)
    linhas = [
        "# Ouvintes da Rádio Encontro de Adoradores",
        "",
        f"_Atualizado em {datetime.now(BRT):%d/%m/%Y %H:%M} (Brasília). "
        "Ouvinte único = mesmo aparelho/conexão contado uma vez por semana._",
        "",
    ]
    if not semanas:
        return "\n".join(linhas + ["Ainda não há dados coletados."]) + "\n"
    for inicio in sorted(semanas, reverse=True):
        linhas += formatar_semana(inicio, resumo_semana(semanas[inicio]))
    return "\n".join(linhas) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    parser.add_argument("--saida", required=True)
    args = parser.parse_args()
    texto = gerar(carregar(Path(args.dir)))
    Path(args.saida).write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
