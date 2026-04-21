param(
  [switch]$IncludeOpenVINO = $true,
  [switch]$IncludeNvidia = $false,
  [switch]$ForceReinstall = $false
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonBootstrap = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonBootstrap)) {
  throw "Bootstrap Python not found at $pythonBootstrap. Create the project .venv first or install Python 3.12."
}

function Ensure-Venv([string]$Path) {
  if ((Test-Path $Path) -and $ForceReinstall) {
    Remove-Item -Recurse -Force $Path
  }
  if (-not (Test-Path $Path)) {
    & $pythonBootstrap -m venv $Path
  }
}

function Install-IntoVenv([string]$VenvPath, [string[]]$Packages, [switch]$UseEditableRembg) {
  $python = Join-Path $VenvPath 'Scripts\python.exe'
  & $python -m pip install --upgrade pip
  if ($UseEditableRembg) {
    & $python -m pip uninstall -y onnxruntime onnxruntime-directml onnxruntime-openvino onnxruntime-gpu | Out-Null
    & $python -m pip install -e "$root\rembg[cli]"
  }
  if ($Packages.Count -gt 0) {
    & $python -m pip uninstall -y onnxruntime onnxruntime-directml onnxruntime-openvino onnxruntime-gpu | Out-Null
    & $python -m pip install @Packages
  }
}

if (-not (Test-Path (Join-Path $root 'rembg\.git'))) {
  git clone https://github.com/danielgatis/rembg.git (Join-Path $root 'rembg')
}

Copy-Item -Force (Join-Path $root 'patches\rembg\rembg\session_factory.py') (Join-Path $root 'rembg\rembg\session_factory.py')
Copy-Item -Force (Join-Path $root 'patches\rembg\rembg\sessions\sam.py') (Join-Path $root 'rembg\rembg\sessions\sam.py')

Ensure-Venv (Join-Path $root '.venv')
& $pythonBootstrap -m pip install -r (Join-Path $root 'requirements-app.txt')

Ensure-Venv (Join-Path $root 'venvs\rembg-dml')
Install-IntoVenv (Join-Path $root 'venvs\rembg-dml') @('onnxruntime-directml') -UseEditableRembg

Ensure-Venv (Join-Path $root 'venvs\rembg-cpu')
Install-IntoVenv (Join-Path $root 'venvs\rembg-cpu') @('onnxruntime') -UseEditableRembg

if ($IncludeOpenVINO) {
  Ensure-Venv (Join-Path $root 'venvs\rembg-openvino')
  Install-IntoVenv (Join-Path $root 'venvs\rembg-openvino') @('onnxruntime-openvino', 'openvino') -UseEditableRembg
}

if ($IncludeNvidia) {
  Ensure-Venv (Join-Path $root 'venvs\rembg-nvidia')
  Install-IntoVenv (Join-Path $root 'venvs\rembg-nvidia') @('onnxruntime-gpu') -UseEditableRembg
}

Write-Host "Runtime setup complete for $root"
Write-Host "AMD Windows path: DirectML via runtime\\rembg\\run_rembg_amd.cmd"
