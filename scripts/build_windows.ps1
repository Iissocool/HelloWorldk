param(
  [switch]$SkipInstaller = $false,
  [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  throw "Project virtual environment not found: $python"
}

Push-Location $root
try {
  if ($Clean) {
    Remove-Item -Recurse -Force .\build -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force .\dist -ErrorAction SilentlyContinue
  }

  & $python -m pip install --upgrade pip | Out-Host
  & $python -m pip install pyinstaller | Out-Host
  & $python -m PyInstaller --noconfirm .\NeonPilot.spec | Out-Host

  $iscc = $null
  $commandIscc = Get-Command iscc -ErrorAction SilentlyContinue
  if ($commandIscc) {
    $iscc = $commandIscc.Source
  } elseif (Test-Path "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe") {
    $iscc = "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe"
  } elseif (Test-Path "$env:ProgramFiles\Inno Setup 6\ISCC.exe") {
    $iscc = "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
  } elseif (Test-Path "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") {
    $iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
  }

  if (-not $SkipInstaller) {
    if (-not $iscc) {
      Write-Warning "Inno Setup not found. Portable build is ready at .\dist\NeonPilot"
    } else {
      & $iscc .\packaging\NeonPilot.iss | Out-Host
    }
  }

  Write-Host "Build complete."
  Write-Host "Portable app: $root\dist\NeonPilot\NeonPilot.exe"
  Write-Host "Installer: $root\dist\installer\NeonPilot-Setup.exe"
}
finally {
  Pop-Location
}
