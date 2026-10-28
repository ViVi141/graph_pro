param([string]$Game = $env:ARMA3_DIR)
$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot
foreach ($n in @('gpindirect.dll', 'injector.exe')) {
  $p = Join-Path $src $n
  if (-not (Test-Path $p)) { Write-Host "Missing $n - run build_indirect.bat" -ForegroundColor Red; exit 1 }
  Copy-Item $p (Join-Path $Game $n) -Force
}
Write-Host "Deployed gpindirect to $Game" -ForegroundColor Green
Write-Host "Start YAAB, then: attach_indirect.ps1" -ForegroundColor Cyan
