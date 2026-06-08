#!/bin/sh
set -eu

mkdir -p /opt/python-standalone-3.9 /opt/src
cd /opt/src

url='https://github.com/indygreg/python-build-standalone/releases/download/20240726/cpython-3.9.19+20240726-aarch64-unknown-linux-gnu-install_only.tar.gz'

if [ ! -f python-standalone-3.9.tar.gz ]; then
  wget -O python-standalone-3.9.tar.gz "$url"
fi

rm -rf /opt/python-standalone-3.9/*
tar -xzf python-standalone-3.9.tar.gz -C /opt/python-standalone-3.9 --strip-components=1

/opt/python-standalone-3.9/bin/python3.9 --version
/opt/python-standalone-3.9/bin/python3.9 -c 'import sys; print(sys.executable)'
