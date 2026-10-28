# Trigger an immediate sample dump.
param(
  [string]$Game = $env:ARMA3_DIR,
  [string]$OutDir = ''
)
$ErrorActionPreference = 'Stop'
$trig = Join-Path $Game 'GP_sampledump.txt'
Set-Content -Path $trig -Value 'dump' -Encoding ascii
Write-Host "Dump triggered; waiting 2s..." -ForegroundColor Cyan
Start-Sleep -Seconds 2
$top = Join-Path $Game 'GP_sample_top.txt'
$mods = Join-Path $Game 'GP_sample_modules.txt'
$log = Join-Path $Game 'GP_sample.log'
if (-not (Test-Path $mods) -and -not (Test-Path $top)) {
  Write-Host "No GP_sample_modules.txt / top yet (DLL not injected?)" -ForegroundColor Yellow
  exit 2
}
if (-not $OutDir) {
  $OutDir = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'extract\cpu_samples'
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
if (Test-Path $mods) { Copy-Item $mods (Join-Path $OutDir "modules_$stamp.txt") -Force }
if (Test-Path $top) { Copy-Item $top (Join-Path $OutDir "top_$stamp.txt") -Force }
if (Test-Path $log) { Copy-Item $log (Join-Path $OutDir "log_$stamp.txt") -Force }
Write-Host "Copied to $OutDir" -ForegroundColor Green
if (Test-Path $mods) {
  Write-Host "--- modules ---" -ForegroundColor Cyan
  Get-Content $mods | Select-Object -First 20
}
if (Test-Path $top) {
  Write-Host "--- exe top ---" -ForegroundColor Cyan
  Get-Content $top | Select-Object -First 15
}
