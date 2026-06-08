#!/bin/sh
set -eu

for v in 20240107 20240224 20240415 20240726 20241002 20241219 20250317 20250529 20250818 20251022 20251120; do
  url="https://github.com/indygreg/python-build-standalone/releases/download/$v/cpython-3.9.19+${v}-aarch64-unknown-linux-gnu-install_only.tar.gz"
  code=$(wget --spider -S "$url" 2>&1 | awk '/HTTP\// {c=$2} END {print c}')
  echo "$v $code $url"
done
