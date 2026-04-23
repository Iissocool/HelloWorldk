param(
  [Parameter(Mandatory = $true)] [string]$InputDir,
  [Parameter(Mandatory = $true)] [string]$OutputDir,
  [int]$Width = 1800,
  [int]$Height = 1800,
  [int]$Dpi = 300,
  [ValidateSet('contain-pad', 'cover-crop', 'stretch', 'keep-ratio')] [string]$Mode = 'contain-pad',
  [switch]$Recurse,
  [switch]$Overwrite
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:GEMINI_ROOT = $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  throw "Python virtual environment not found: $python"
}

$argv = @(
  '-m', 'app.command_bridge',
  'resize-batch',
  '--input-dir', $InputDir,
  '--output-dir', $OutputDir,
  '--width', $Width,
  '--height', $Height,
  '--dpi', $Dpi,
  '--mode', $Mode
)
if ($Recurse) { $argv += '--recurse' }
if ($Overwrite) { $argv += '--overwrite' }

Push-Location $projectRoot
try {
  & $python @argv
}
finally {
  Pop-Location
}
