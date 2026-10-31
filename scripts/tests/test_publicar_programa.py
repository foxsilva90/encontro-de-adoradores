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
    plan = pw.plan_replacement(files, playlist_id=10, new_media_id=4, managed_prefix="programas/manha-com-deus/")
    assert plan == {"delete": [1], "unassign": [(2, [20])]}


def test_plan_replacement_sem_episodio_anterior_nao_mexe_em_nada():
    files = [_file(3, "musicas/louvor.mp3", [20]), _file(4, "programas/x/novo.mp3", [10])]
    assert pw.plan_replacement(files, 10, 4, "programas/x/") == {"delete": [], "unassign": []}


def test_find_playlist_ignora_maiusculas_e_espacos():
    playlists = [{"id": 1, "name": "Boletim"}, {"id": 7, "name": "Manhã com Deus "}]
    assert pw.find_playlist_id(playlists, "manhã com deus") == 7
    with pytest.raises(LookupError):
        pw.find_playlist_id(playlists, "Inexistente")


def test_format_duration():
    assert pw.format_duration(3725.4) == "1h02min"
    assert pw.format_duration(1530) == "25min30s"
