#!/usr/bin/env bash
# Builds dist/PACE.app and dist/PACE-macOS.dmg   (Python from python.org or Homebrew python-tk)
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install -r requirements-build.txt
python3 tools/make_icon.py
python3 -m PyInstaller packaging/pace.spec --noconfirm
hdiutil create -volname "PACE" -srcfolder dist/PACE.app -ov -format UDZO dist/PACE-macOS.dmg
echo "Done: dist/PACE.app  and  dist/PACE-macOS.dmg"
