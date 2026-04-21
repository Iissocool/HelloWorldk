param(
    [string]$InputDir = "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\input",
    [string]$OutputDir = "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\output",
    [string]$MaskPreviewDir = "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\mask-preview"
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\vendor"

& "W:\Miniconda3\python.exe" "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\replace_backgrounds.py" `
    --input-dir $InputDir `
    --output-dir $OutputDir `
    --mask-preview-dir $MaskPreviewDir
