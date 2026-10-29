# Load backend/.env into this process, then start the local API on port 8010.
# Secrets stay in .env (gitignored); this script never prints variable values.

$ErrorActionPreference = "Stop"
$BackendRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $BackendRoot ".env"

if (-not (Test-Path $EnvFile)) {
    Write-Host "Missing backend/.env"
    Write-Host "Copy backend/.env.example to backend/.env and set APP_ENV=local and DATABASE_URL."
    Write-Host "Then run: backend/scripts/start-local-api.ps1"
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $eq = $line.IndexOf("=")
    if ($eq -lt 1) { return }
    $name = $line.Substring(0, $eq).Trim()
    $value = $line.Substring($eq + 1).Trim()
    if ($value.StartsWith("<") -and $value.EndsWith(">")) {
        return
    }
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
}

if (-not $env:APP_ENV) {
    $env:APP_ENV = "local"
}

if (-not $env:DATABASE_URL) {
    Write-Host "DATABASE_URL is missing in backend/.env"
    exit 1
}

Set-Location $BackendRoot
$Python = Join-Path $BackendRoot ".venv/Scripts/python.exe"
if (-not (Test-Path $Python)) {
    throw "Missing backend virtual environment. Install dependencies with uv first."
}

# Fail closed before startup if this is not the isolated local development DB.
& $Python (Join-Path $PSScriptRoot "preflight_local_api.py")
if ($LASTEXITCODE -ne 0) {
    throw "Local startup requires APP_ENV=local and database 127.0.0.1:55432/szzsbj_dev."
}

Write-Host "Starting local uvicorn at http://127.0.0.1:8010"
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
