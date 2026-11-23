@echo off
rem Build a standalone LocalWrite.exe folder in dist\LocalWrite with PyInstaller.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Dev || exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt --quiet || exit /b 1
".venv\Scripts\python.exe" tools\make_icons.py || exit /b 1
".venv\Scripts\python.exe" -m PyInstaller localwrite.spec --noconfirm --clean || exit /b 1
echo.
echo Built: %~dp0dist\LocalWrite\LocalWrite.exe
