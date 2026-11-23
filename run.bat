@echo off
rem Launch LocalWrite without a console window. Use "run.bat --setup" to reopen the setup wizard.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo LocalWrite is not installed yet. Running the installer first...
    call install.bat
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0launch.pyw" %*
