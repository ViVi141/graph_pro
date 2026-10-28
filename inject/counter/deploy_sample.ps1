# Deploy CPU sampler only (no d3d11 proxy).
param(
  [string]$Game = $env:ARMA3_DIR
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $Game)) {
  Write-Host "Game dir not found: $Game" -ForegroundColor Red
  exit 1
}
$src = $PSScriptRoot
$need = @('gpsample.dll', 'funcs.bin', 'injector.exe', 'GP_sample.txt')
foreach ($n in $need) {
  $p = Join-Path $src $n
  if (-not (Test-Path $p)) {
    Write-Host "Missing $n - run prepare_funcs.ps1 / build_sample.bat" -ForegroundColor Red
    exit 1
  }
  Copy-Item $p (Join-Path $Game $n) -Force
}
$proxy = Join-Path $Game 'd3d11.dll'
if (Test-Path $proxy) {
  Write-Host "WARN: d3d11.dll still in game dir; prefer inject\remove.ps1 first" -ForegroundColor Yellow
}
Write-Host "Deployed sampler to: $Game" -ForegroundColor Green
Write-Host "Next: start Arma3_x64 / YAAB, then attach_sample.ps1" -ForegroundColor Cyan
