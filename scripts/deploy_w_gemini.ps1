param(
  [string]$WorkspaceRoot = "W:\gemini"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$portableSource = Join-Path $repoRoot "dist\CutCanvas"
$installerSource = Join-Path $repoRoot "dist\installer\CutCanvas-Setup.exe"

if (-not (Test-Path $portableSource)) {
  throw "Portable build not found: $portableSource`nPlease run .\scripts\build_windows.ps1 first."
}

$workspaceRoot = (Resolve-Path $WorkspaceRoot).Path
$cutCanvasRoot = Join-Path $workspaceRoot "apps\CutCanvas"
$installerRoot = Join-Path $cutCanvasRoot "installer"
$docsRoot = Join-Path $workspaceRoot "docs"

Get-Process -Name "CutCanvas" -ErrorAction SilentlyContinue | Stop-Process -Force

if (Test-Path $cutCanvasRoot) {
  Remove-Item -LiteralPath $cutCanvasRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $cutCanvasRoot | Out-Null
New-Item -ItemType Directory -Force -Path $installerRoot | Out-Null
New-Item -ItemType Directory -Force -Path $docsRoot | Out-Null

Copy-Item -Path (Join-Path $portableSource "*") -Destination $cutCanvasRoot -Recurse -Force

if (Test-Path $installerSource) {
  Copy-Item -Path $installerSource -Destination (Join-Path $installerRoot "CutCanvas-Setup.exe") -Force
}

Copy-Item -Path (Join-Path $repoRoot "docs\*") -Destination $docsRoot -Recurse -Force

$psLauncher = @(
  '$ErrorActionPreference = "Stop"',
  ('$env:GEMINI_ROOT = "' + $workspaceRoot + '"'),
  ('& "' + (Join-Path $cutCanvasRoot 'CutCanvas.exe') + '"')
) -join "`r`n"

$cmdLauncher = @(
  '@echo off',
  ('set GEMINI_ROOT=' + $workspaceRoot),
  ('start "" "' + (Join-Path $cutCanvasRoot 'CutCanvas.exe') + '"')
) -join "`r`n"

$workspaceReadme = @(
  '# W:\gemini Workspace',
  '',
  'This folder is the local runtime workspace for CutCanvas.',
  '',
  '## Main Paths',
  '',
  '- Portable app: `W:\gemini\apps\CutCanvas\CutCanvas.exe`',
  '- Installer: `W:\gemini\apps\CutCanvas\installer\CutCanvas-Setup.exe`',
  '- Launcher: `W:\gemini\run_cutcanvas.cmd`',
  '',
  '## Launch',
  '',
  'Start CutCanvas:',
  '',
  '```powershell',
  'W:\gemini\run_cutcanvas.cmd',
  '```',
  '',
  'Or:',
  '',
  '```powershell',
  'powershell -ExecutionPolicy Bypass -File W:\gemini\run_cutcanvas.ps1',
  '```',
  '',
  'Legacy launcher:',
  '',
  '```powershell',
  'W:\gemini\run_background_desktop.cmd',
  '```',
  '',
  '## Related Directories',
  '',
  '- `W:\gemini\apps\CutCanvas\`: portable app',
  '- `W:\gemini\runtime\rembg\`: runtime scripts',
  '- `W:\gemini\models\`: models',
  '- `W:\gemini\docs\`: manuals and architecture docs',
  '- `W:\gemini\data\`: history and app data',
  '- `W:\gemini\reports\`: reports and test outputs'
) -join "`r`n"

Set-Content -Path (Join-Path $workspaceRoot "run_cutcanvas.ps1") -Value $psLauncher -Encoding utf8
Set-Content -Path (Join-Path $workspaceRoot "run_cutcanvas.cmd") -Value $cmdLauncher -Encoding ascii
Set-Content -Path (Join-Path $workspaceRoot "run_background_desktop.ps1") -Value $psLauncher -Encoding utf8
Set-Content -Path (Join-Path $workspaceRoot "run_background_desktop.cmd") -Value $cmdLauncher -Encoding ascii
Set-Content -Path (Join-Path $workspaceRoot "README.md") -Value $workspaceReadme -Encoding utf8

Write-Host "Deployment complete."
Write-Host "Portable app: $cutCanvasRoot\CutCanvas.exe"
if (Test-Path (Join-Path $installerRoot "CutCanvas-Setup.exe")) {
  Write-Host "Installer: $cutCanvasRoot\installer\CutCanvas-Setup.exe"
}
