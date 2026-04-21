param(
    [string]$InputDir = "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\input",
    [string]$OutputDir = "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\api-batch-workflow\output",
    [string]$MaskConfig = "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\api-batch-workflow\product_masks.json",
    [string]$PromptFile = "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\api-batch-workflow\prompt.txt",
    [string]$Model = "gpt-image-1",
    [int]$Workers = 2,
    [string]$ApiSize = "1024x1024",
    [string]$InputFidelity = "omit",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$preferredPython = "C:\Users\F1736\AppData\Local\Programs\Python\Python313\python.exe"
$python = if (Test-Path $preferredPython) { $preferredPython } else { "python" }
$script = "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\api-batch-workflow\openai_batch_edit.py"

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
