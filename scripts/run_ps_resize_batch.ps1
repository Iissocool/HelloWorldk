param(
  [Parameter(Mandatory = $true)] [string]$InputDir,
  [Parameter(Mandatory = $true)] [string]$OutputDir,
  [string]$Photoshop = 'C:\Program Files\Adobe\Adobe Photoshop (Beta)',
  [string]$ActionSet = '默认动作',
  [string]$ActionName = '高透三折叠套图-透明图',
  [int]$Timeout = 3600
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:GEMINI_ROOT = $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  throw "Python virtual environment not found: $python"
}
Push-Location $projectRoot
try {
  & $python -m app.command_bridge ps-resize --input-dir $InputDir --output-dir $OutputDir --photoshop $Photoshop --action-set $ActionSet --action-name $ActionName --timeout $Timeout
}
finally {
  Pop-Location
}
