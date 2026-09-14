#!/bin/bash
# Vigia da live 24h: roda de 1 em 1 minuto (systemd timer).
# Mede quantos bytes o YouTube CONFIRMOU ter recebido (tcp bytes_acked da
# conexão RTMP do ffmpeg, porta 1935). A live manda ~24 MB/min; se o YouTube
# confirmou quase nada desde a última checagem, está travada -> reinicia.
# Quando saudável, avisa o healthchecks.io (se configurado). Se os avisos
# pararem, o healthchecks manda e-mail — pega até a VPS inteira fora do ar.

SERVICE=youtube-stream
STATE=/var/lib/youtube-stream-watchdog/state
HC_URL_FILE=/etc/youtube-stream-hc.url
MIN_BYTES_PER_MIN=5000000
STARTUP_GRACE_SECONDS=90

mkdir -p "$(dirname "$STATE")"

hc_ping() {
  [ -s "$HC_URL_FILE" ] || return 0
  curl -fsS -m 10 --retry 3 "$(cat "$HC_URL_FILE")" >/dev/null 2>&1
}

restart_stream() {
  logger -t yt-watchdog "$1, reiniciando"
  systemctl restart "$SERVICE"
  rm -f "$STATE"
  exit 0
}

if ! systemctl is-active --quiet "$SERVICE"; then
  logger -t yt-watchdog "servico $SERVICE inativo, iniciando"
  systemctl start "$SERVICE"
  rm -f "$STATE"
  exit 0
fi

now=$(date +%s)
started=$(date -d "$(systemctl show "$SERVICE" -p ActiveEnterTimestamp --value)" +%s)
if [ $((now - started)) -lt "$STARTUP_GRACE_SECONDS" ]; then
  rm -f "$STATE"
  exit 0
fi

# Conexão RTMP do ffmpeg: identidade = porta local (muda se reconectar).
line=$(ss -tinpH state established '( dport = :1935 )' | tr '\n' ' ')
if ! echo "$line" | grep -q 'ffmpeg'; then
  restart_stream "sem conexao RTMP do ffmpeg com o YouTube"
fi
sock=$(ss -tnH state established '( dport = :1935 )' | awk 'NR==1 {print $3}')
acked=$(echo "$line" | grep -o 'bytes_acked:[0-9]*' | head -1 | cut -d: -f2)

read -r last_sock last_acked last_time < "$STATE" 2>/dev/null
echo "$sock $acked $now" > "$STATE"

# Primeira rodada ou conexão nova: só registra a base.
if [ "$sock" != "$last_sock" ] || [ -z "$last_time" ]; then
  exit 0
fi

elapsed=$((now - last_time))
[ "$elapsed" -le 0 ] && exit 0
per_min=$(( (acked - last_acked) * 60 / elapsed ))

if [ "$per_min" -lt "$MIN_BYTES_PER_MIN" ]; then
  restart_stream "travado: YouTube confirmou ${per_min} bytes/min (min ${MIN_BYTES_PER_MIN})"
fi

hc_ping
