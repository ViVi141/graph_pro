# Deploy gptimer.dll (no d3d11 proxy). Exit Arma first if overwriting.
param([string]$Game = 'D:\SteamLibrary\steamapps\common\Arma 3')
$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot
foreach ($n in @('gptimer.dll', 'injector.exe')) {
  $p = Join-Path $src $n
  if (-not (Test-Path $p)) { Write-Host "Missing $n - run build_timer.bat" -ForegroundColor Red; exit 1 }
  Copy-Item $p (Join-Path $Game $n) -Force
}
Write-Host "Deployed gptimer to $Game" -ForegroundColor Green
Write-Host "Start YAAB, then: attach_timer.ps1" -ForegroundColor Cyan
