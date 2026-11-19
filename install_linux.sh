#!/usr/bin/env bash
# PACE installer for Raspberry Pi OS / Debian / Ubuntu / Fedora / Arch.
# Installs from source (no compiling): app menu entry + desktop shortcut + icon.
#   ./install_linux.sh            install
#   ./install_linux.sh --uninstall
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/.local/share/pace"
ICON_BASE="$HOME/.local/share/icons/hicolor"
DESKTOP_FILE="$HOME/.local/share/applications/pace.desktop"

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -rf "$APP_DIR" "$DESKTOP_FILE" "$HOME/.local/bin/pace"
  for s in 32 64 128 256 512; do rm -f "$ICON_BASE/${s}x${s}/apps/pace.png"; done
  rm -f "$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")/PACE.desktop"
  echo "PACE removed (your scenarios/logs in ~ were left untouched)."; exit 0
fi

echo "==> System packages (tkinter + pyserial)"
if   command -v apt-get >/dev/null; then sudo apt-get install -y python3 python3-tk python3-serial
elif command -v dnf     >/dev/null; then sudo dnf install -y python3 python3-tkinter python3-pyserial
elif command -v pacman  >/dev/null; then sudo pacman -S --needed --noconfirm python tk python-pyserial
else echo "Unknown package manager: install Python 3, tkinter and pyserial manually."; fi

echo "==> Copying app to $APP_DIR"
mkdir -p "$APP_DIR/assets"
cp "$SRC/PACE.py" "$APP_DIR/"
cp "$SRC"/assets/pace_*.png "$SRC/assets/pace.png" "$SRC/assets/pace.ico" "$APP_DIR/assets/"

echo "==> Icons + launcher"
for s in 32 64 128 256 512; do
  mkdir -p "$ICON_BASE/${s}x${s}/apps"; cp "$SRC/assets/pace_${s}.png" "$ICON_BASE/${s}x${s}/apps/pace.png"
done
mkdir -p "$HOME/.local/bin" "$(dirname "$DESKTOP_FILE")"
cat > "$HOME/.local/bin/pace" <<LAUNCH
#!/usr/bin/env bash
exec python3 "$APP_DIR/PACE.py" "\$@"
LAUNCH
chmod +x "$HOME/.local/bin/pace"

cat > "$DESKTOP_FILE" <<DESK
[Desktop Entry]
Type=Application
Name=PACE
GenericName=Power Cycle Controller
Comment=Power Automation Cycle Engine - Automated Reliability Stress Test Platform
Exec=$HOME/.local/bin/pace
Icon=$APP_DIR/assets/pace_256.png
Terminal=false
Categories=Utility;Electronics;Engineering;
StartupWMClass=Tk
DESK
chmod +x "$DESKTOP_FILE"
DESK_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [[ -d "$DESK_DIR" ]]; then cp "$DESKTOP_FILE" "$DESK_DIR/PACE.desktop"; chmod +x "$DESK_DIR/PACE.desktop"
  command -v gio >/dev/null && gio set "$DESK_DIR/PACE.desktop" metadata::trusted true 2>/dev/null || true; fi
command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
command -v gtk-update-icon-cache  >/dev/null && gtk-update-icon-cache -q "$ICON_BASE" 2>/dev/null || true

# Serial access to the PSUs / MCU (/dev/ttyACM*) needs the 'dialout' group
if ! id -nG "$USER" | grep -qw dialout; then
  sudo usermod -aG dialout "$USER"
  echo "!! Added $USER to 'dialout'. LOG OUT AND BACK IN (or reboot) once, otherwise the USB ports stay 'permission denied'."
fi
echo "Done. Start PACE from the application menu (Utility), the desktop icon, or run:  pace"
