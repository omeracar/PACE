# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PACE — one file for Windows, macOS and Linux.
#   pyinstaller packaging/pace.spec --noconfirm
import os, sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
A = lambda *p: os.path.join(ROOT, *p)

datas = [(A("assets", f"pace_{n}.png"), "assets") for n in (32, 64, 128, 256)]
datas.append((A("assets", "pace.ico"), "assets"))

hidden = ["serial.tools.list_ports"]
if sys.platform.startswith("win"):
    hidden += ["serial.tools.list_ports_windows", "serial.win32"]
elif sys.platform == "darwin":
    hidden += ["serial.tools.list_ports_osx", "serial.tools.list_ports_posix"]
else:
    hidden += ["serial.tools.list_ports_linux", "serial.tools.list_ports_posix"]

a = Analysis([A("PACE.py")], pathex=[ROOT], datas=datas, hiddenimports=hidden,
             excludes=["numpy", "matplotlib", "scipy", "pandas", "PIL"], noarchive=False)
pyz = PYZ(a.pure)

if sys.platform.startswith("win"):
    # single self-contained PACE.exe, no console window
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="PACE",
              console=False, icon=A("assets", "pace.ico"), upx=False)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PACE",
              console=False, upx=False,
              icon=A("assets", "pace.icns") if sys.platform == "darwin" else None)
    coll = COLLECT(exe, a.binaries, a.datas, name="PACE", upx=False)
    if sys.platform == "darwin":
        app = BUNDLE(coll, name="PACE.app", icon=A("assets", "pace.icns"),
                     bundle_identifier="com.rel.pace",
                     info_plist={
                         "CFBundleName": "PACE",
                         "CFBundleDisplayName": "PACE - Power Automation Cycle Engine",
                         "CFBundleShortVersionString": "22",
                         "NSHighResolutionCapable": True,
                     })
