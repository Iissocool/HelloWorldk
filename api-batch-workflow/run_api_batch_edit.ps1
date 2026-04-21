param(
    [string]$InputDir = "",
    [string]$OutputDir = "",
    [string]$MaskConfig = "",
    [string]$PromptFile = "",
    [string]$Model = "gpt-image-1",
    [int]$Workers = 2,
    [string]$ApiSize = "1024x1024",
    [string]$InputFidelity = "omit",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $InputDir) {
    $InputDir = Join-Path $repoRoot 'input'
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $PSScriptRoot 'output'
}
if (-not $MaskConfig) {
    $MaskConfig = Join-Path $PSScriptRoot 'product_masks.json'
}
if (-not $PromptFile) {
    $PromptFile = Join-Path $PSScriptRoot 'prompt.txt'
}

$preferredPython = Join-Path $repoRoot '.venv\\Scripts\\python.exe'
$python = if (Test-Path $preferredPython) { $preferredPython } else { "python" }
$script = Join-Path $PSScriptRoot 'openai_batch_edit.py'

$args = @(
    $script,
    "--input-dir", $InputDir,
    "--output-dir", $OutputDir,
    "--mask-config", $MaskConfig,
    "--prompt-file", $PromptFile,
    "--model", $Model,
    "--workers", $Workers,
    "--api-size", $ApiSize,
    "--input-fidelity", $InputFidelity
)

if ($DryRun) {
    $args += "--dry-run"
}

& $python @args
