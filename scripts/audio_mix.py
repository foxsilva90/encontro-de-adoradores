"""
Monta o programa final a partir da voz enviada pelo locutor:

    [vinheta de responsabilidade] -> [voz + playback com ducking] -> fade-out

- A voz passa por limpeza leve (corta graves de microfone/ruído e reduz chiado)
  e é normalizada.
- O playback entra antes da voz (LEAD_SECONDS), abaixa sozinho quando o
  locutor fala (sidechain) e sobe nas pausas. Repete em loop se a voz for
  mais longa que a trilha, e termina com fade-out depois da última fala.
- O resultado inteiro é normalizado pra -16 LUFS (padrão de rádio web).
"""
import subprocess

SAMPLE_RATE = 44100
MP3_BITRATE = "192k"
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"

LEAD_SECONDS = 3.0     # playback sozinho antes da voz começar
TAIL_SECONDS = 4.0     # playback depois da última fala
FADE_IN_SECONDS = 1.5
FADE_OUT_SECONDS = 4.0
BED_VOLUME = 0.50      # volume do playback nas pausas (antes do ducking)

# Ducking: quanto mais alto o ratio, mais o playback abaixa sob a voz.
DUCK = "threshold=0.015:ratio=10:attack=15:release=700:makeup=1"
VOICE_CLEANUP = "highpass=f=80,afftdn=nf=-25"

_FMT = f"aresample={SAMPLE_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo"


def build_filter(voice_seconds):
    """Filtro do ffmpeg. Entradas: 0 = voz, 1 = playback (em loop), 2 = vinheta."""
    lead_ms = int(LEAD_SECONDS * 1000)
    total = LEAD_SECONDS + voice_seconds + TAIL_SECONDS
    fade_start = max(total - FADE_OUT_SECONDS, 0)
    return ";".join([
        f"[0:a]{_FMT},{VOICE_CLEANUP},{LOUDNORM},"
        f"adelay={lead_ms}:all=1,apad=whole_dur={total:.3f},asplit=2[vmix][vkey]",
        f"[1:a]{_FMT},volume={BED_VOLUME},atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:d={FADE_IN_SECONDS},afade=t=out:st={fade_start:.3f}:d={FADE_OUT_SECONDS}[bedraw]",
        f"[bedraw][vkey]sidechaincompress={DUCK}[bed]",
        "[vmix][bed]amix=inputs=2:duration=first:normalize=0[prog]",
        f"[2:a]{_FMT}[intro]",
        f"[intro][prog]concat=n=2:v=0:a=1,{LOUDNORM},aresample={SAMPLE_RATE}[out]",
    ])


def build_command(voice_path, bed_path, intro_path, out_path, voice_seconds, title, artist, ffmpeg="ffmpeg"):
    return [
        ffmpeg, "-y", "-loglevel", "error",
        "-i", voice_path,
        "-stream_loop", "-1", "-i", bed_path,
        "-i", intro_path,
        "-filter_complex", build_filter(voice_seconds),
        "-map", "[out]", "-ac", "2", "-ar", str(SAMPLE_RATE), "-b:a", MP3_BITRATE,
        "-metadata", f"title={title}", "-metadata", f"artist={artist}",
        out_path,
    ]


def mix_program(voice_path, bed_path, intro_path, out_path, voice_seconds, title, artist, ffmpeg="ffmpeg"):
    subprocess.run(
        build_command(voice_path, bed_path, intro_path, out_path, voice_seconds, title, artist, ffmpeg),
        check=True,
    )
