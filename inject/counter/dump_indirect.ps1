param(
  [string]$Game = $env:ARMA3_DIR,
  [string]$OutDir = ''
)
$ErrorActionPreference = 'Stop'
Set-Content -Path (Join-Path $Game 'GP_indirectdump.txt') -Value 'dump' -Encoding ascii
Start-Sleep -Seconds 2
$txt = Join-Path $Game 'GP_indirect.txt'
$log = Join-Path $Game 'GP_indirect.log'
if (-not (Test-Path $txt)) {
  Write-Host "No GP_indirect.txt yet" -ForegroundColor Yellow
  if (Test-Path $log) { Get-Content $log -Tail 30 }
  exit 2
}
if (-not $OutDir) {
  $OutDir = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'extract\cpu_samples'
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
Copy-Item $txt (Join-Path $OutDir "indirect_$stamp.txt") -Force
if (Test-Path $log) { Copy-Item $log (Join-Path $OutDir "indirectlog_$stamp.txt") -Force }
Write-Host "--- GP_indirect.txt ---" -ForegroundColor Cyan
Get-Content $txt
