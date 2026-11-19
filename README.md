<p align="center"><img src="assets/pace_256.png" width="128" alt="PACE icon"></p>

# PACE — Power Automation Cycle Engine
**Automated Reliability Stress-Test Platform** for up to 8× Aim-TTi CPX400DP power supplies
(synchronous / asynchronous / constant modes, scenario editor, watchdog failsafe, live graph & logs).

Runs on **Windows, macOS, Linux and Raspberry Pi**. Python + tkinter + pyserial; ports (COMx, /dev/ttyACMx, /dev/cu.usbmodem*) are auto-detected.

## Download (no Python needed)
Get the build for your system from the **Releases** page:

| System | File | Start |
|---|---|---|
| Windows 10/11 | `PACE-Windows-x64.zip` | unzip, double-click `PACE.exe` |
| macOS (Apple Silicon) | `PACE-macOS-AppleSilicon.dmg` | drag `PACE.app` to Applications |
| Linux x86-64 | `PACE-Linux-x64.tar.gz` | extract, run `./PACE/PACE` |
| Raspberry Pi (64-bit OS) | `PACE-Linux-arm64-RaspberryPi.tar.gz` | extract, run `./PACE/PACE` |

*Unsigned app warnings:* Windows SmartScreen → "More info → Run anyway". macOS → right-click `PACE.app` → Open (or `xattr -cr /Applications/PACE.app`).

## Raspberry Pi / Linux: install with menu entry + desktop icon
Works on any Pi incl. 32-bit Raspberry Pi OS (runs from source, nothing to compile):
```bash
git clone https://github.com/omeracar/-PACE-Power-Automation-Cycle-Engine-Automated-Reliability-Stress-Test-Platform-.git pace
cd pace && ./install_linux.sh
```
Log out/in once afterwards (adds you to the `dialout` group for USB serial access). Remove with `./install_linux.sh --uninstall`.

## Run from source (any OS)
```bash
pip install pyserial
python PACE.py            # Linux may need: sudo apt install python3-tk
```

## Build the apps yourself
* **Automatic (all 4 platforms):** push a tag `git tag v22.0 && git push --tags` — GitHub Actions builds everything and attaches it to a Release. Or run *Actions → Build desktop apps → Run workflow*.
* **Local:** `packaging\build_windows.bat` · `packaging/build_macos.sh` · `packaging/build_linux.sh`

## Layout
```
PACE.py            the application
assets/            icons (png set, .ico, .icns)
tools/make_icon.py regenerates the icons
packaging/         PyInstaller spec + build scripts
install_linux.sh   Raspberry Pi / Linux installer
.github/workflows  CI builds for Win / macOS / Linux / Pi
```
User data lives in your home folder (`~/cpx400dp_scenarios`, `~/cpx400dp_cycle_programs`, `~/cpx400dp_settings.json`, …), so updating the app never touches it.
