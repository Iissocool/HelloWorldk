param(
  [string]$WorkspaceRoot = "W:\gemini"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$portableSource = Join-Path $repoRoot "dist\NeonPilot"
$installerSource = Join-Path $repoRoot "dist\installer\NeonPilot-Setup.exe"
if (-not (Test-Path $portableSource)) {
  throw "Portable build not found: $portableSource`nPlease run .\scripts\build_windows.ps1 first."
}

$workspaceRoot = (Resolve-Path $WorkspaceRoot).Path
$appRoot = Join-Path $workspaceRoot "apps\NeonPilot"
$installerRoot = Join-Path $appRoot "installer"
$docsRoot = Join-Path $workspaceRoot "docs"
$hermesRoot = Join-Path $workspaceRoot "data\neonpilot\hermes"

Get-Process -Name "NeonPilot" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "CutCanvas" -ErrorAction SilentlyContinue | Stop-Process -Force

New-Item -ItemType Directory -Force -Path $appRoot | Out-Null
New-Item -ItemType Directory -Force -Path $docsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $hermesRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $hermesRoot "skills") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $hermesRoot "logs") | Out-Null

robocopy $portableSource $appRoot /MIR /R:1 /W:1 | Out-Null
New-Item -ItemType Directory -Force -Path $installerRoot | Out-Null
if (Test-Path $installerSource) {
  Copy-Item -Path $installerSource -Destination (Join-Path $installerRoot "NeonPilot-Setup.exe") -Force
}
Copy-Item -Path (Join-Path $repoRoot "docs\*") -Destination $docsRoot -Recurse -Force

$psLauncher = @(
  '$ErrorActionPreference = "Stop"',
  ('$env:GEMINI_ROOT = "' + $workspaceRoot + '"'),
  ('& "' + (Join-Path $appRoot 'NeonPilot.exe') + '"')
) -join "`r`n"

$cmdLauncher = @(
  '@echo off',
  ('set GEMINI_ROOT=' + $workspaceRoot),
  ('start "" "' + (Join-Path $appRoot 'NeonPilot.exe') + '"')
) -join "`r`n"

$readme = @(
  '# W:\gemini Workspace',
  '',
  'This folder is the local runtime workspace for NeonPilot.',
  '',
  '## Main Paths',
  '',
  '- Portable app: `W:\gemini\apps\NeonPilot\NeonPilot.exe`',
  '- Installer: `W:\gemini\apps\NeonPilot\installer\NeonPilot-Setup.exe`',
  '- Launcher: `W:\gemini\run_neonpilot.cmd`',
  '- Hermes data: `W:\gemini\data\neonpilot\hermes`'
) -join "`r`n"

Set-Content -Path (Join-Path $workspaceRoot "run_neonpilot.ps1") -Value $psLauncher -Encoding utf8
Set-Content -Path (Join-Path $workspaceRoot "run_neonpilot.cmd") -Value $cmdLauncher -Encoding ascii
Set-Content -Path (Join-Path $workspaceRoot "run_cutcanvas.ps1") -Value $psLauncher -Encoding utf8
Set-Content -Path (Join-Path $workspaceRoot "run_cutcanvas.cmd") -Value $cmdLauncher -Encoding ascii
Set-Content -Path (Join-Path $workspaceRoot "run_background_desktop.ps1") -Value $psLauncher -Encoding utf8
Set-Content -Path (Join-Path $workspaceRoot "run_background_desktop.cmd") -Value $cmdLauncher -Encoding ascii
Set-Content -Path (Join-Path $workspaceRoot "README.md") -Value $readme -Encoding utf8

Write-Host "Deployment complete."
Write-Host "Portable app: $appRoot\NeonPilot.exe"
if (Test-Path (Join-Path $installerRoot "NeonPilot-Setup.exe")) {
  Write-Host "Installer: $installerRoot\NeonPilot-Setup.exe"
}
