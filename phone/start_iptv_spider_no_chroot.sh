#!/bin/sh
set -eu

APP_DIR=/opt/iptv-spider-rootfs/app
VENV=/opt/iptv-spider-venv
DATA_DIR=/opt/iptv-spider-data
LOG=/root/iptv-spider.log
PID=/root/iptv-spider.pid

if [ -f "$PID" ]; then
  oldpid=$(cat "$PID" 2>/dev/null || true)
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    echo "iptv-spider already running: $oldpid"
    exit 0
  fi
fi

mkdir -p "$DATA_DIR"

cd "$APP_DIR"
nohup env \
  PORT=50085 \
  DATA_DIR="$DATA_DIR" \
  IPTV_DATA_DIR="$DATA_DIR" \
  PYTHONPATH="$APP_DIR" \
  "$VENV/bin/python" wsgi.py > "$LOG" 2>&1 &

echo $! > "$PID"
echo "started iptv-spider pid $(cat "$PID")"
