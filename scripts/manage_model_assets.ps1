param(
  [ValidateSet("install", "uninstall")]
  [string]$Action = "install",
  [Parameter(Mandatory = $true)]
  [string]$ModelId,
  [ValidateSet("cpu", "directml", "amd", "openvino", "cuda", "tensorrt")]
  [string]$Backend = "cpu"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workspaceRoot = if ($env:GEMINI_ROOT -and (Test-Path $env:GEMINI_ROOT)) { (Resolve-Path $env:GEMINI_ROOT).Path } else { $repoRoot }
$modelsRoot = Join-Path $workspaceRoot "models\.u2net"
$installRoot = Join-Path $workspaceRoot "data\neonpilot\model-installer"
$runtimeRoot = Join-Path $workspaceRoot "runtime\rembg"

$modelFiles = @{
  "u2net" = @("u2net.onnx")
  "u2netp" = @("u2netp.onnx")
  "u2net_human_seg" = @("u2net_human_seg.onnx")
  "u2net_cloth_seg" = @("u2net_cloth_seg.onnx")
  "silueta" = @("silueta.onnx")
  "isnet-general-use" = @("isnet-general-use.onnx")
  "isnet-anime" = @("isnet-anime.onnx")
  "sam" = @("sam_vit_b_01ec64.encoder.onnx", "sam_vit_b_01ec64.decoder.onnx")
  "birefnet-general" = @("birefnet-general.onnx")
  "birefnet-general-lite" = @("birefnet-general-lite.onnx")
  "birefnet-portrait" = @("birefnet-portrait.onnx")
  "birefnet-dis" = @("birefnet-dis.onnx")
  "birefnet-hrsod" = @("birefnet-hrsod.onnx")
  "birefnet-cod" = @("birefnet-cod.onnx")
  "birefnet-massive" = @("birefnet-massive.onnx")
  "bria-rmbg" = @("bria-rmbg.onnx")
}

$runnerMap = @{
  "cpu" = "run_rembg_cpu.cmd"
  "directml" = "run_rembg_dml.cmd"
  "amd" = "run_rembg_amd.cmd"
  "openvino" = "run_rembg_openvino.cmd"
  "cuda" = "run_rembg_cuda.cmd"
  "tensorrt" = "run_rembg_tensorrt.cmd"
}

if (-not $modelFiles.ContainsKey($ModelId)) {
  throw "Unknown model: $ModelId"
}

$targets = $modelFiles[$ModelId] | ForEach-Object { Join-Path $modelsRoot $_ }

if ($Action -eq "uninstall") {
  foreach ($target in $targets) {
    if (Test-Path $target) {
      Write-Host "Removing model file: $target"
      Remove-Item -Force $target
    } else {
      Write-Host "Skipping missing file: $target"
    }
  }
  Write-Host "Model uninstall complete."
  exit 0
}

$missingTargets = $targets | Where-Object { -not (Test-Path $_) }
if ($missingTargets.Count -eq 0) {
  Write-Host "Model already present. Nothing to download."
  exit 0
}

New-Item -ItemType Directory -Force -Path $modelsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null

$runnerName = $runnerMap[$Backend]
$runner = Join-Path $runtimeRoot $runnerName
if (-not (Test-Path $runner)) {
  throw "Runner not found: $runner"
}

$probeInput = Join-Path $installRoot "__probe_input.png"
$probeOutput = Join-Path $installRoot "__probe_output.png"
[IO.File]::WriteAllBytes(
  $probeInput,
  [Convert]::FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAukB9VE3d2kAAAAASUVORK5CYII=")
)

Write-Host "Downloading model: $ModelId"
Write-Host "Backend: $Backend"
& cmd /c $runner --model $ModelId --input $probeInput --output $probeOutput
if ($LASTEXITCODE -ne 0) {
  throw "Model download failed with exit code $LASTEXITCODE"
}

$missingAfter = $targets | Where-Object { -not (Test-Path $_) }
if ($missingAfter.Count -gt 0) {
  throw "Model download finished but files are still missing: $($missingAfter -join ', ')"
}

Write-Host "Model download complete."
