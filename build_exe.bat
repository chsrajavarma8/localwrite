@echo off
rem ---------------------------------------------------------------------------
rem Build a fresh standalone LocalWrite.exe with PyInstaller.
rem Output: dist\LocalWrite\LocalWrite.exe (one-folder app; copy the whole folder).
rem
rem The executable is not code-signed, so Windows SmartScreen or Smart App Control
rem may warn about it or block it. During development, use run.bat instead.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up the development environment first...
    powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Dev || exit /b 1
)

echo [1/5] Installing build requirements...
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt --quiet || exit /b 1

echo [2/5] Removing previous build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist build ( echo Could not delete the build folder - close any program using it. & exit /b 1 )
if exist dist ( echo Could not delete the dist folder - close LocalWrite.exe if it is running. & exit /b 1 )
for /d /r localwrite %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"

echo [3/5] Checking the source...
".venv\Scripts\python.exe" -m compileall -q localwrite launch.pyw || exit /b 1
".venv\Scripts\python.exe" -c "import localwrite.main, localwrite.app_controller" || exit /b 1

echo [4/5] Generating the icon...
".venv\Scripts\python.exe" tools\make_icons.py || exit /b 1

echo [5/5] Building with PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller localwrite.spec --noconfirm --clean --log-level WARN || exit /b 1

if not exist "dist\LocalWrite\LocalWrite.exe" ( echo Build failed: LocalWrite.exe was not produced. & exit /b 1 )
echo.
echo Built: %~dp0dist\LocalWrite\LocalWrite.exe
echo Note: the executable is unsigned; Windows may show a security warning the first time it runs.
