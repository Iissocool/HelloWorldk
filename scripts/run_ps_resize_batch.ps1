param(
  [Parameter(Mandatory = $true)] [string]$InputDir,
  [Parameter(Mandatory = $true)] [string]$OutputDir,
  [int]$Width = 1800,
  [int]$Height = 1800,
  [int]$Dpi = 300,
  [ValidateSet('contain-pad', 'cover-crop', 'stretch', 'keep-ratio')] [string]$Mode = 'contain-pad',
  [switch]$Recurse,
  [switch]$Overwrite
)

Write-Warning 'run_ps_resize_batch.ps1 已切换为程序内原生调尺寸。建议以后改用 run_resize_batch.ps1。'
& (Join-Path $PSScriptRoot 'run_resize_batch.ps1') `
  -InputDir $InputDir `
  -OutputDir $OutputDir `
  -Width $Width `
  -Height $Height `
  -Dpi $Dpi `
  -Mode $Mode `
  -Recurse:$Recurse `
  -Overwrite:$Overwrite
