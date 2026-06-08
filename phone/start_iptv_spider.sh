#!/bin/sh
set -eu

ROOTFS=/opt/iptv-spider-rootfs
LOG=/root/iptv-spider.log
PID=/root/iptv-spider.pid

if [ -f "$PID" ]; then
  oldpid=$(cat "$PID" 2>/dev/null || true)
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    echo "iptv-spider already running: $oldpid"
    exit 0
  fi
fi

cd "$ROOTFS/app"
export PORT=50085
export DATA_DIR=/app/data
export IPTV_DATA_DIR=/app/data

nohup chroot "$ROOTFS" /bin/sh -lc 'cd /app && PORT=50085 DATA_DIR=/app/data IPTV_DATA_DIR=/app/data PYTHONPATH=/app /usr/local/bin/python wsgi.py' > "$LOG" 2>&1 &
echo $! > "$PID"
echo "started iptv-spider pid $(cat "$PID")"
