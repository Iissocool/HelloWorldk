$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:GEMINI_ROOT = $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  throw "Python virtual environment not found: $python"
}
Push-Location $projectRoot
try {
  & $python -m app.command_bridge @args
}
finally {
  Pop-Location
}
