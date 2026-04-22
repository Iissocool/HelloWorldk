param(
  [int] $Port = 8787
)

$ErrorActionPreference = "Stop"
$env:GEMINI_ROOT = $PSScriptRoot
$bootstrap = Join-Path $PSScriptRoot "scripts\bootstrap_app_env.ps1"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Push-Location $PSScriptRoot
try {
  & $bootstrap | Out-Host
  if (-not (Test-Path $python)) {
    throw "Python virtual environment not found: $python"
  }
  & $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
}
finally {
  Pop-Location
}
