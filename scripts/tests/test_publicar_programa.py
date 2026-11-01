import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

import publicar_programa as pw  # noqa: E402


def test_slugify_remove_acentos_e_simbolos():
    assert pw.slugify("Manhã com Deus!") == "manha-com-deus"
    assert pw.slugify("  Louvor & Adoração  ") == "louvor-adoracao"
    assert pw.slugify("***") == "programa"


def test_parse_program_map_normaliza_numeros_e_descarta_lixo():
    raw = '{"+55 11 98888-7777": " Manhã com Deus ", "x": "", "5521": 3}'
    assert pw.parse_program_map(raw) == {"5511988887777": "Manhã com Deus"}
    assert pw.parse_program_map("não é json") == {}
    assert pw.parse_program_map(None) == {}


def test_phones_for_program_acha_todos_os_locutores():
    mapping = {"5511988887777": "A", "5521977776666": "B", "5531966665555": "A"}
    assert sorted(pw.phones_for_program(mapping, "A")) == ["5511988887777", "5531966665555"]
    assert pw.phones_for_program(mapping, "C") == []


BLOB = "https://abc123.public.blob.vercel-storage.com/programas/x-AbC.mp3"


def test_resolve_source_aceita_link_do_blob():
    assert pw.resolve_source(BLOB, "", "Qualquer", {}) == ("url", BLOB)


def test_resolve_source_recusa_link_de_outro_site():
    for url in ["http://abc.public.blob.vercel-storage.com/x.mp3",
                "https://evil.com/x.mp3",
                "https://abc.public.blob.vercel-storage.com.evil.com/x.mp3"]:
        with pytest.raises(ValueError):
            pw.resolve_source(url, "", "P", {})


DRIVE = "https://drive.usercontent.google.com/download?id=1AbCdEfGhIjKlMnOpQrStUvWxYz012345&export=download&confirm=t"


def test_resolve_source_aceita_link_do_drive():
    assert pw.resolve_source(DRIVE, "", "P", {}) == ("url", DRIVE)


def test_resolve_source_recusa_drive_fora_do_formato():
    for url in ["https://drive.usercontent.google.com/download?id=../x",
                "https://drive.usercontent.google.com/outra?id=1AbCdEfGhIjKlMnOpQrStUvWxYz012345",
                "https://drive.usercontent.google.com.evil.com/download?id=1AbCdEfGhIjKlMnOpQrStUvWxYz012345",
                "http://drive.usercontent.google.com/download?id=1AbCdEfGhIjKlMnOpQrStUvWxYz012345"]:
        with pytest.raises(ValueError):
            pw.resolve_source(url, "", "P", {})


class _FakeDownload:
    def __init__(self, content_type, body=b"abc", status=200):
        self.headers = {"Content-Type": content_type}
        self._body = body
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, chunk_size):
        yield self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_url_recusa_pagina_html_do_drive(tmp_path, monkeypatch):
    monkeypatch.setattr(pw.requests, "get", lambda *a, **k: _FakeDownload("text/html; charset=utf-8"))
    with pytest.raises(ValueError, match="compartilhado"):
        pw.download_url(DRIVE, str(tmp_path / "voz"))


def test_download_url_baixa_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(pw.requests, "get", lambda *a, **k: _FakeDownload("audio/mpeg", b"ID3data"))
    dest = tmp_path / "voz"
    pw.download_url(DRIVE, str(dest))
    assert dest.read_bytes() == b"ID3data"


def test_resolve_source_whatsapp_exige_programa_cadastrado():
    mapping = {"5511988887777": "Manhã com Deus"}
    assert pw.resolve_source("", "12345", "Manhã com Deus", mapping) == ("whatsapp", "12345")
    with pytest.raises(ValueError):
        pw.resolve_source("", "12345", "Outro", mapping)
    with pytest.raises(ValueError):
        pw.resolve_source("", "../x", "Manhã com Deus", mapping)


def test_resolve_source_exige_exatamente_uma_origem():
    with pytest.raises(ValueError):
        pw.resolve_source("", "", "P", {})
    with pytest.raises(ValueError):
        pw.resolve_source(BLOB, "123", "P", {})
    with pytest.raises(ValueError):
        pw.resolve_source(BLOB, "", "", {})


def test_trilha_paths_avisa_quando_falta_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "TRILHAS_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="trilhas/"):
        pw.trilha_paths()
    (tmp_path / pw.INTRO_FILE).write_bytes(b"x")
    (tmp_path / pw.BED_FILE).write_bytes(b"x")
    assert pw.trilha_paths() == (str(tmp_path / pw.INTRO_FILE), str(tmp_path / pw.BED_FILE))


def _file(fid, path, playlist_ids):
    return {"id": fid, "path": path, "playlists": [{"id": p, "name": f"P{p}"} for p in playlist_ids]}


def test_plan_replacement_apaga_episodio_gerenciado_e_desvincula_upload_manual():
    files = [
        _file(1, "programas/manha-com-deus/20261024-080000.mp3", [10]),
        _file(2, "uploads/manha_antigo.mp3", [10, 20]),
        _file(3, "musicas/louvor.mp3", [20]),
        _file(4, "programas/manha-com-deus/20261031-080000.mp3", [10]),  # o recém-enviado
    ]
    plan = pw.plan_replacement(files, [10], new_media_id=4, managed_prefix="programas/manha-com-deus/")
    assert plan == {"delete": [1], "unassign": [(2, [20])]}


def test_plan_replacement_com_varias_playlists_tira_de_todas():
    files = [
        _file(1, "programas/encontro/antigo.mp3", [10, 11, 12, 13]),
        _file(2, "manual/encontro_06h.mp3", [10, 30]),
        _file(3, "manual/encontro_22h.mp3", [13]),
        _file(9, "programas/encontro/novo.mp3", [10, 11, 12, 13]),
    ]
    plan = pw.plan_replacement(files, [10, 11, 12, 13], 9, "programas/encontro/")
    assert plan == {"delete": [1], "unassign": [(2, [30]), (3, [])]}


def test_plan_replacement_sem_episodio_anterior_nao_mexe_em_nada():
    files = [_file(3, "musicas/louvor.mp3", [20]), _file(4, "programas/x/novo.mp3", [10])]
    assert pw.plan_replacement(files, [10], 4, "programas/x/") == {"delete": [], "unassign": []}


PLAYLISTS = [
    {"id": 1, "name": "Boletim"},
    {"id": 7, "name": "PG Encontro de Adoradores - Bp. Anderson Gustavo (11h"},
    {"id": 8, "name": "PG Palavra Viva - 15h (Seg) - Patricia Bambrila "},
]


def test_find_playlist_ids_tolera_parenteses_espacos_e_maiusculas():
    ids = pw.find_playlist_ids(PLAYLISTS, [
        "PG Encontro de Adoradores - Bp. Anderson Gustavo (11h)",
        "pg palavra viva - 15h (seg) - patricia bambrila",
    ])
    assert ids == [7, 8]


def test_find_playlist_ids_lista_as_que_faltam():
    with pytest.raises(LookupError, match="Inexistente"):
        pw.find_playlist_ids(PLAYLISTS, ["Boletim", "Inexistente"])


def test_find_playlist_ids_recusa_nome_ambiguo():
    dup = PLAYLISTS + [{"id": 9, "name": "boletim!"}]
    with pytest.raises(LookupError, match="mais de uma"):
        pw.find_playlist_ids(dup, ["Boletim"])


def test_parse_playlists_usa_json_ou_cai_no_programa():
    assert pw.parse_playlists('["A", " B ", ""]', "X") == ["A", "B"]
    assert pw.parse_playlists("", "X") == ["X"]
    with pytest.raises(ValueError):
        pw.parse_playlists("não é json", "X")
    with pytest.raises(ValueError):
        pw.parse_playlists('{"a": 1}', "X")


def test_format_duration():
    assert pw.format_duration(3725.4) == "1h02min"
    assert pw.format_duration(1530) == "25min30s"


def test_chunk_plan_divide_em_pedacos_e_o_ultimo_leva_o_resto():
    assert pw.chunk_plan(10, 4) == [(1, 0, 4), (2, 4, 4), (3, 8, 2)]


def test_chunk_plan_arquivo_menor_que_um_pedaco():
    assert pw.chunk_plan(3, 4) == [(1, 0, 3)]


def test_chunk_plan_recusa_arquivo_vazio():
    with pytest.raises(ValueError):
        pw.chunk_plan(0, 4)


def test_find_media_id_by_path_acha_o_arquivo_enviado():
    files = [{"id": 1, "path": "programas/a/1.mp3"}, {"id": 2, "path": "programas/a/2.mp3"}]
    assert pw.find_media_id_by_path(files, "programas/a/2.mp3") == 2


def test_find_media_id_by_path_avisa_quando_nao_acha():
    with pytest.raises(LookupError):
        pw.find_media_id_by_path([{"id": 1, "path": "x.mp3"}], "programas/a/2.mp3")


class _FakeResp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload
        self.content = b"x" if payload is not None else b""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_upload_in_chunks_manda_todos_os_pedacos_com_campos_do_flow(tmp_path, monkeypatch):
    mp3 = tmp_path / "programa.mp3"
    mp3.write_bytes(b"abcdefghij")
    calls = []

    def fake_post(url, headers, data, files, timeout):
        calls.append((url, data, files["file"][1]))
        last = data["flowChunkNumber"] == data["flowTotalChunks"]
        return _FakeResp(200, {"success": True} if last else None)

    monkeypatch.setattr(pw.requests, "post", fake_post)
    pw.upload_in_chunks("https://r", "k", "st", "programas/talito", "20261031.mp3", str(mp3), chunk_size=4)

    assert [c[2] for c in calls] == [b"abcd", b"efgh", b"ij"]
    url, data, _ = calls[-1]
    assert url == "https://r/api/station/st/files/upload"
    assert data["flowTotalChunks"] == 3 and data["flowTotalSize"] == 10
    assert data["flowCurrentChunkSize"] == 2 and data["flowFilename"] == "20261031.mp3"
    assert data["currentDirectory"] == "programas/talito"


def test_upload_in_chunks_reenvia_ultimo_pedaco_quando_servidor_pede(tmp_path, monkeypatch):
    mp3 = tmp_path / "programa.mp3"
    mp3.write_bytes(b"abcdef")
    answers = iter([_FakeResp(200), _FakeResp(204), _FakeResp(200, {"success": True})])
    sent = []

    def fake_post(url, headers, data, files, timeout):
        sent.append(data["flowChunkNumber"])
        return next(answers)

    monkeypatch.setattr(pw.requests, "post", fake_post)
    pw.upload_in_chunks("https://r", "k", "st", "d", "f.mp3", str(mp3), chunk_size=4)
    assert sent == [1, 2, 2]


def test_upload_in_chunks_falha_quando_azuracast_recusa_o_audio(tmp_path, monkeypatch):
    mp3 = tmp_path / "programa.mp3"
    mp3.write_bytes(b"abc")
    monkeypatch.setattr(
        pw.requests, "post",
        lambda *a, **k: _FakeResp(200, {"success": False, "message": "arquivo corrompido"}),
    )
    with pytest.raises(RuntimeError, match="arquivo corrompido"):
        pw.upload_in_chunks("https://r", "k", "st", "d", "f.mp3", str(mp3), chunk_size=4)


def test_parse_destino_lista_simples_edita():
    assert pw.parse_destino('["A", "B"]', "X") == (["A", "B"], True)
    assert pw.parse_destino("", "X") == (["X"], True)


def test_parse_destino_objeto_pode_desligar_edicao():
    assert pw.parse_destino('{"playlists": ["A"], "editar": false}', "X") == (["A"], False)
    assert pw.parse_destino('{"playlists": ["A"], "editar": true}', "X") == (["A"], True)
    assert pw.parse_destino('{"playlists": ["A"]}', "X") == (["A"], True)


def test_parse_destino_objeto_sem_playlists_e_recusado():
    with pytest.raises(ValueError):
        pw.parse_destino('{"editar": false}', "X")


def test_passthrough_mp3_copia_sem_reencodar():
    cmd = pw.build_passthrough_command("in", "out.mp3", "mp3", "Título", "Rádio")
    assert cmd[cmd.index("-c:a") + 1] == "copy"
    assert "-af" not in cmd and "-filter_complex" not in cmd


def test_passthrough_outro_formato_converte_pra_mp3_sem_filtros():
    cmd = pw.build_passthrough_command("in", "out.mp3", "aac", "Título", "Rádio")
    assert cmd[cmd.index("-c:a") + 1] == "libmp3lame"
    assert "-af" not in cmd and "-filter_complex" not in cmd
