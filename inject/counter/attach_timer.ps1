param(
  [string]$Game = $env:ARMA3_DIR,
  [string]$Process = 'Arma3_x64.exe'
)
$ErrorActionPreference = 'Stop'
$dll = Join-Path $Game 'gptimer.dll'
$inj = Join-Path $Game 'injector.exe'
if (-not (Test-Path $dll)) { Write-Host "Missing $dll" -ForegroundColor Red; exit 1 }
& $inj $Process $dll
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Timer injected. After YAAB: dump_timer.ps1" -ForegroundColor Green
