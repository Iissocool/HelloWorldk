param(
  [ValidateSet("install", "uninstall")]
  [string]$Action = "install",
  [string[]]$Components = @("core", "cpu"),
  [switch]$ForceReinstall = $false
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvRoot = Join-Path $root "venvs"
$bootstrapScript = Join-Path $root "scripts\bootstrap_app_env.ps1"
$bootstrapPython = Join-Path $root ".venv\Scripts\python.exe"

if ($Components.Count -eq 1 -and $Components[0] -match ",") {
  $Components = $Components[0].Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}

function Write-Step([string]$Message) {
  Write-Host $Message
}

function Ensure-Core {
  & $bootstrapScript
}

function Ensure-RembgSource {
  $rembgRoot = Join-Path $root "rembg"
  if (-not (Test-Path (Join-Path $rembgRoot ".git"))) {
    Write-Step "Cloning rembg source..."
    git clone https://github.com/danielgatis/rembg.git $rembgRoot
  }

  $sessionPatch = Join-Path $root "patches\rembg\rembg\session_factory.py"
  $samPatch = Join-Path $root "patches\rembg\rembg\sessions\sam.py"
  if (Test-Path $sessionPatch) {
    Copy-Item -Force $sessionPatch (Join-Path $rembgRoot "rembg\session_factory.py")
  }
  if (Test-Path $samPatch) {
    Copy-Item -Force $samPatch (Join-Path $rembgRoot "rembg\sessions\sam.py")
  }
}

function Ensure-Venv([string]$Path) {
  if ((Test-Path $Path) -and $ForceReinstall) {
    Remove-Item -Recurse -Force $Path
  }
  if (-not (Test-Path $Path)) {
    & $bootstrapPython -m venv $Path
  }
}

function Install-IntoVenv([string]$Path, [string[]]$Packages) {
  Ensure-Venv $Path
  $python = Join-Path $Path "Scripts\python.exe"
  & $python -m pip install --upgrade pip | Out-Host
  & $python -m pip uninstall -y onnxruntime onnxruntime-directml onnxruntime-openvino onnxruntime-gpu | Out-Null
  & $python -m pip install -e "$root\rembg[cli]" | Out-Host
  if ($Packages.Count -gt 0) {
    & $python -m pip install @Packages | Out-Host
  }
}

function Remove-ComponentVenv([string]$Path, [string]$Label) {
  if (Test-Path $Path) {
    Write-Step "Removing $Label ..."
    Remove-Item -Recurse -Force $Path
  } else {
    Write-Step "$Label is already absent."
  }
}

function Install-Component([string]$Component) {
  switch ($Component) {
    "core" {
      Write-Step "Installing core desktop dependencies..."
      Ensure-Core
    }
    "cpu" {
      Ensure-Core
      Ensure-RembgSource
      Write-Step "Installing CPU runtime..."
      Install-IntoVenv (Join-Path $venvRoot "rembg-cpu") @("onnxruntime")
    }
    "directml" {
      Ensure-Core
      Ensure-RembgSource
      Write-Step "Installing DirectML runtime..."
      Install-IntoVenv (Join-Path $venvRoot "rembg-dml") @("onnxruntime-directml")
    }
    "openvino" {
      Ensure-Core
      Ensure-RembgSource
      Write-Step "Installing OpenVINO runtime..."
      Install-IntoVenv (Join-Path $venvRoot "rembg-openvino") @("onnxruntime-openvino", "openvino")
    }
    "nvidia" {
      Ensure-Core
      Ensure-RembgSource
      Write-Step "Installing NVIDIA runtime..."
      Install-IntoVenv (Join-Path $venvRoot "rembg-nvidia") @("onnxruntime-gpu")
    }
    default {
      throw "Unsupported component: $Component"
    }
  }
}

function Uninstall-Component([string]$Component) {
  switch ($Component) {
    "core" {
      Write-Step "The core desktop dependency is kept to avoid breaking app startup."
    }
    "cpu" {
      Remove-ComponentVenv (Join-Path $venvRoot "rembg-cpu") "CPU runtime"
    }
    "directml" {
      Remove-ComponentVenv (Join-Path $venvRoot "rembg-dml") "DirectML runtime"
    }
    "openvino" {
      Remove-ComponentVenv (Join-Path $venvRoot "rembg-openvino") "OpenVINO runtime"
    }
    "nvidia" {
      Remove-ComponentVenv (Join-Path $venvRoot "rembg-nvidia") "NVIDIA runtime"
    }
    default {
      throw "Unsupported component: $Component"
    }
  }
}

foreach ($component in $Components) {
  if ($Action -eq "install") {
    Install-Component $component
  } else {
    Uninstall-Component $component
  }
}

Write-Step "Runtime operation finished."
