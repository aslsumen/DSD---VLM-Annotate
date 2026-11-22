# VLM Annotate - one-command setup for Windows (PowerShell).
#
# Usage (from the repository root):
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SkipFrontend
#
# The script installs the backend dependencies into .venv, applies Alembic
# migrations, and (unless -SkipFrontend) installs and builds the React UI.
# It never deletes data and never touches .env.

[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "VLM Annotate setup - $root"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python not found on PATH. Install Python 3.12-3.14 and retry."
}
$pythonVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$pythonVersion -lt [version]"3.12") {
    throw "Python 3.12+ required (found $pythonVersion)."
}
Write-Host "Python $pythonVersion OK"

if (-not (Test-Path (Join-Path $root ".venv\Scripts\python.exe"))) {
    Write-Host "Creating .venv ..."
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "python -m venv failed" }
}
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if (-not $SkipInstall) {
    Write-Host "Installing backend dependencies ..."
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r (Join-Path $root "backend\requirements.lock.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}

Write-Host "Applying database migrations ..."
Push-Location (Join-Path $root "backend")
& $venvPython -m alembic upgrade head
$alembicExit = $LASTEXITCODE
Pop-Location
if ($alembicExit -ne 0) {
    Write-Host ""
    Write-Host "Migration failed." -ForegroundColor Yellow
    Write-Host "Most common cause: the API was started before running migrations, so" -ForegroundColor Yellow
    Write-Host "data\vlm_annotate.db exists without Alembic's version row." -ForegroundColor Yellow
    Write-Host "Stop the API/worker, delete data\vlm_annotate.db (development only) and rerun this script." -ForegroundColor Yellow
    exit 1
}

if (-not $SkipFrontend) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm not found. Install Node.js 20.19+ (22 LTS recommended)."
    }
    Write-Host "Installing and building the frontend ..."
    Push-Location (Join-Path $root "frontend")
    npm ci
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm ci failed - check Node >= 20.19" }
    npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm run build failed" }
    Pop-Location
}

Write-Host ""
Write-Host "Setup complete. Start two terminals:" -ForegroundColor Green
Write-Host "  1) cd backend; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
Write-Host "  2) cd backend; ..\.venv\Scripts\python.exe -m app.worker --loop"
Write-Host "Then open http://127.0.0.1:8000  (API docs: http://127.0.0.1:8000/api/docs)"
Write-Host "The real GPU engine is optional: see video_grounding/README.md."
