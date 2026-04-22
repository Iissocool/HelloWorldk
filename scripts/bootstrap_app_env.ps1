param(
  [switch]$Quiet = $false
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPath = Join-Path $root ".venv"
$python = Join-Path $venvPath "Scripts\python.exe"

function Write-Step([string]$Message) {
  if (-not $Quiet) {
    Write-Host $Message
  }
}

if (-not (Test-Path $python)) {
  Write-Step "Creating minimal desktop environment..."
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    & py -3.12 -m venv $venvPath
  } else {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
      throw "Python 3.12 was not found. Install Python before starting NeonPilot."
    }
    & python -m venv $venvPath
  }
}

$python = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $python)) {
  throw "Minimal desktop environment creation failed: $python"
}

Write-Step "Installing minimal desktop dependencies..."
& $python -m pip install --upgrade pip | Out-Host
& $python -m pip install -r (Join-Path $root "requirements-app.txt") | Out-Host
Write-Step "Minimal desktop dependencies are ready."
