$ErrorActionPreference = 'Stop'
$env:GEMINI_ROOT = $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  throw "Python virtual environment not found: $python"
}
Push-Location $PSScriptRoot
try {
  & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements-app.txt') | Out-Host
  & $python -m app.desktop_app
}
finally {
  Pop-Location
}
