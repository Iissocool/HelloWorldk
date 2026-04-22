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
  & $python -m app.self_test @args
}
finally {
  Pop-Location
}
