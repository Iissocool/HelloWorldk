param(
    [string]$InputDir = "",
    [string]$OutputDir = "",
    [string]$MaskPreviewDir = ""
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $InputDir) {
    $InputDir = Join-Path $root 'input'
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $root 'output'
}
if (-not $MaskPreviewDir) {
    $MaskPreviewDir = Join-Path $root 'mask-preview'
}

$env:PYTHONPATH = Join-Path $root 'vendor'
$preferredPython = Join-Path $root '.venv\Scripts\python.exe'
$python = if (Test-Path $preferredPython) { $preferredPython } else { 'python' }

& $python (Join-Path $root 'replace_backgrounds.py') `
    --input-dir $InputDir `
    --output-dir $OutputDir `
    --mask-preview-dir $MaskPreviewDir
