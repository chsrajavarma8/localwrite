<#
  LocalWrite installer.
  - Finds Python 3.11+ (via the py launcher or PATH)
  - Creates a private virtual environment in .venv and installs requirements
  - Generates the app icon and creates a Start Menu shortcut (and optionally a desktop shortcut)
  - Checks whether Ollama is installed/running and explains what to do if not
  It never installs Ollama or downloads AI models.

  Usage:  powershell -ExecutionPolicy Bypass -File install.ps1 [-DesktopShortcut] [-Dev]
#>
param(
    [switch]$DesktopShortcut,
    [switch]$Dev
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

Write-Step "Looking for Python 3.11 or newer"
$python = $null
foreach ($candidate in @(@("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("python"), @("python3"))) {
    try {
        $exe = $candidate[0]; $pyArgs = @($candidate | Select-Object -Skip 1)
        $ver = & $exe @pyArgs -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver) {
            $parts = $ver.Trim().Split(".")
            if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11) { $python = $candidate; break }
        }
    } catch { }
}
if (-not $python) {
    Write-Host ""
    Write-Host "Python 3.11+ was not found." -ForegroundColor Red
    Write-Host "Install it from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH'),"
    Write-Host "then run this installer again."
    exit 1
}
Write-Ok ("Using: " + ($python -join " ") + " (Python $ver)")

Write-Step "Creating virtual environment (.venv)"
if (-not (Test-Path "$Root\.venv\Scripts\python.exe")) {
    $exe = $python[0]; $pyArgs = @($python | Select-Object -Skip 1)
    & $exe @pyArgs -m venv "$Root\.venv"
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment" }
}
$venvPy = "$Root\.venv\Scripts\python.exe"
$venvPyw = "$Root\.venv\Scripts\pythonw.exe"
Write-Ok "OK"

Write-Step "Installing dependencies (PySide6, requests)"
& $venvPy -m pip install --upgrade pip --quiet
$req = if ($Dev) { "requirements-dev.txt" } else { "requirements.txt" }
& $venvPy -m pip install -r "$Root\$req" --quiet
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
Write-Ok "OK"

Write-Step "Generating icon"
& $venvPy "$Root\tools\make_icons.py" | Out-Null
Write-Ok "OK"

Write-Step "Creating shortcuts"
$shell = New-Object -ComObject WScript.Shell
$targets = @("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\LocalWrite.lnk")
if ($DesktopShortcut) { $targets += [Environment]::GetFolderPath("Desktop") + "\LocalWrite.lnk" }
foreach ($lnkPath in $targets) {
    $lnk = $shell.CreateShortcut($lnkPath)
    $lnk.TargetPath = $venvPyw
    $lnk.Arguments = "`"$Root\launch.pyw`""
    $lnk.WorkingDirectory = $Root
    $lnk.IconLocation = "$Root\resources\icons\app.ico"
    $lnk.Description = "LocalWrite - private AI writing assistant"
    $lnk.Save()
    Write-Ok $lnkPath
}

Write-Step "Checking Ollama"
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama -and (Test-Path "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe")) { $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }
if ($ollama) {
    Write-Ok "Ollama is installed."
    try {
        $v = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 3
        Write-Ok "Ollama server is running (version $($v.version))."
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
        if ($tags.models.Count -eq 0) {
            Write-Warn "No models installed yet. Recommended:  ollama pull qwen2.5:3b"
        } else {
            Write-Ok ("Installed models: " + (($tags.models | ForEach-Object { $_.name }) -join ", "))
        }
    } catch {
        Write-Warn "Ollama is installed but not running. Start it from the Start menu (or run 'ollama serve')."
    }
} else {
    Write-Warn "Ollama is not installed. LocalWrite needs it to run AI models locally."
    Write-Warn "Download the official installer: https://ollama.com/download/windows"
    Write-Warn "Then install a model, e.g.:  ollama pull qwen2.5:3b"
}

Write-Host ""
Write-Host "LocalWrite is installed." -ForegroundColor Green
Write-Host "Start it from the Start menu ('LocalWrite') or run:  run.bat"
