import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("requests", types.ModuleType("requests"))  # coletor importa requests

import ouvintes_coletar as coletar  # noqa: E402
import ouvintes_relatorio as relatorio  # noqa: E402

SEG_09_11_15H = 1794247200  # 2026-11-09 15:00 BRT (segunda)


def sessao(hash_="a", inicio=SEG_09_11_15H, segundos=600, ua="Mozilla/5.0 (iPhone)", **extra):
    base = {"hash": hash_, "inicio": inicio, "fim": inicio + segundos, "segundos": segundos,
            "user_agent": ua, "cliente": None, "is_bot": False, "is_mobile": True,
            "is_browser": True, "cidade": "Rio de Janeiro", "estado": "RJ", "pais": "BR"}
    return {**base, **extra}


def test_resumir_sessao_nao_guarda_ip():
    bruta = {"ip": "1.2.3.4", "hash": "h", "connected_on": 1, "connected_until": 2,
             "connected_time": 1, "user_agent": "x", "device": {}, "location": {}}
    assert "ip" not in coletar.resumir_sessao(bruta)
    assert "1.2.3.4" not in json.dumps(coletar.resumir_sessao(bruta))


def test_mesclar_mantem_versao_mais_longa_sem_duplicar():
    antiga = [sessao(segundos=100)]
    nova = [sessao(segundos=900), sessao(hash_="b")]
    resultado = coletar.mesclar(antiga, nova)
    assert len(resultado) == 2
    assert next(s for s in resultado if s["hash"] == "a")["segundos"] == 900
    assert antiga[0]["segundos"] == 100  # não altera a lista original


def test_gravar_acumula_entre_coletas(tmp_path):
    coletar.gravar(tmp_path, coletar.agrupar_por_dia([sessao()]))
    novas = coletar.gravar(tmp_path, coletar.agrupar_por_dia([sessao(), sessao(hash_="b")]))
    assert novas == 1
    assert len(json.loads((tmp_path / "2026-11-09.json").read_text())) == 2


def test_is_pessoa_descarta_robos_e_conexoes_curtas():
    assert relatorio.is_pessoa(sessao())
    assert not relatorio.is_pessoa(sessao(ua="Lavf/60.16.100"))
    assert not relatorio.is_pessoa(sessao(ua="ORB HisBot/26567"))
    assert not relatorio.is_pessoa(sessao(ua="Go-http-client/2.0"))
    assert not relatorio.is_pessoa(sessao(segundos=14))
    assert not relatorio.is_pessoa(sessao(is_bot=True))


def test_resumo_semana_conta_unicos():
    dia = 86400
    sessoes = [sessao("a"), sessao("a", inicio=SEG_09_11_15H + dia), sessao("b"),
               sessao("robo", ua="Lavf/60")]
    r = relatorio.resumo_semana(sessoes)
    assert r["unicos"] == 2
    assert r["sessoes"] == 3
    assert r["por_dia"] == {0: 2, 1: 1}
    assert r["robos"] == 1


def test_gerar_sem_dados():
    assert "Ainda não há dados" in relatorio.gerar([])


def test_gerar_semana_comeca_na_segunda():
    texto = relatorio.gerar([sessao()])
    assert "Semana 09/11 a 15/11/2026" in texto
    assert "**Ouvintes únicos:** 1" in texto
