import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import audio_mix as m  # noqa: E402


def test_filtro_calcula_duracao_e_fade_do_playback():
    f = m.build_filter(100.0)
    total = m.LEAD_SECONDS + 100.0 + m.TAIL_SECONDS
    assert f"apad=whole_dur={total:.3f}" in f
    assert f"atrim=0:{total:.3f}" in f
    assert f"afade=t=out:st={total - m.FADE_OUT_SECONDS:.3f}" in f
    assert f"adelay={int(m.LEAD_SECONDS * 1000)}:all=1" in f


def test_filtro_poe_vinheta_antes_do_programa_e_usa_ducking():
    f = m.build_filter(10.0)
    assert "[intro][prog]concat=n=2" in f
    assert "[bedraw][vkey]sidechaincompress" in f


def test_comando_coloca_playback_em_loop_e_metadados():
    cmd = m.build_command("voz", "bed", "intro", "out.mp3", 10.0, "Manhã com Deus", "Rádio")
    assert cmd[cmd.index("bed") - 3:cmd.index("bed")] == ["-stream_loop", "-1", "-i"]
    assert cmd.index("voz") < cmd.index("bed") < cmd.index("intro")
    assert "title=Manhã com Deus" in cmd and cmd[-1] == "out.mp3"
