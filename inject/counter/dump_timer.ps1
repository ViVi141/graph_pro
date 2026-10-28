param(
  [string]$Game = $env:ARMA3_DIR,
  [string]$OutDir = ''
)
$ErrorActionPreference = 'Stop'
Set-Content -Path (Join-Path $Game 'GP_timerdump.txt') -Value 'dump' -Encoding ascii
Start-Sleep -Seconds 2
$txt = Join-Path $Game 'GP_timer.txt'
$log = Join-Path $Game 'GP_timer.log'
if (-not (Test-Path $txt)) {
  Write-Host "No GP_timer.txt yet (hook not installed or game exited)" -ForegroundColor Yellow
  if (Test-Path $log) { Get-Content $log -Tail 20 }
  exit 2
}
if (-not $OutDir) {
  $OutDir = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'extract\cpu_samples'
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
Copy-Item $txt (Join-Path $OutDir "timer_$stamp.txt") -Force
if (Test-Path $log) { Copy-Item $log (Join-Path $OutDir "timerlog_$stamp.txt") -Force }
Write-Host "--- GP_timer.txt ---" -ForegroundColor Cyan
Get-Content $txt
