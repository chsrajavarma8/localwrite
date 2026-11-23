@echo off
rem LocalWrite installer - double-click to install. Pass /desktop to also create a desktop shortcut.
setlocal
set EXTRA=
if /I "%~1"=="/desktop" set EXTRA=-DesktopShortcut
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %EXTRA%
echo.
pause
