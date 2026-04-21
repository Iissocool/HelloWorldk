$ErrorActionPreference = 'Stop'
$env:GEMINI_ROOT = $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  throw "Python virtual environment not found: $python"
}
Push-Location $PSScriptRoot
try {
  & $python -m app.self_test @args
}
finally {
  Pop-Location
}
