param(
  [int] $Port = 8787
)
$ErrorActionPreference = 'Stop'
$env:GEMINI_ROOT = $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  throw "Python virtual environment not found: $python"
}
Push-Location $PSScriptRoot
try {
  & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements-app.txt') | Out-Host
  & $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
}
finally {
  Pop-Location
}
