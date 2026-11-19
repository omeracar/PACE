#!/usr/bin/env bash
# Builds a standalone dist/PACE-linux-<arch>.tar.gz  (Debian/Ubuntu/Raspberry Pi OS)
set -euo pipefail
cd "$(dirname "$0")/.."
sudo apt-get install -y python3-tk python3-venv python3-pip
python3 -m venv .buildenv && . .buildenv/bin/activate
pip install -r requirements-build.txt
python tools/make_icon.py
pyinstaller packaging/pace.spec --noconfirm
tar -C dist -czf "dist/PACE-linux-$(uname -m).tar.gz" PACE
echo "Done: dist/PACE-linux-$(uname -m).tar.gz"
