@echo off
REM Builds dist\PACE.exe  (run from anywhere; needs Python 3.9+ from python.org with tcl/tk)
cd /d "%~dp0\.."
python -m pip install -r requirements-build.txt || goto :err
python tools\make_icon.py || goto :err
python -m PyInstaller packaging\pace.spec --noconfirm || goto :err
echo.
echo Done:  %cd%\dist\PACE.exe
pause & exit /b 0
:err
echo BUILD FAILED & pause & exit /b 1
