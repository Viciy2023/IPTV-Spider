#!/bin/sh
set -eu

echo "[start] starting OneTV updater in background"
python3 /app/scripts/update_onetv_m3u.py &

echo "[start] starting IPTV-Spider: $*"
exec "$@"
