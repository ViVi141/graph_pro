# Remove CPU sampler files from the game directory.
param(
  [string]$Game = $env:ARMA3_DIR
)
$ErrorActionPreference = 'Continue'
$names = @(
  'gpsample.dll', 'funcs.bin', 'injector.exe', 'GP_sample.txt',
  'GP_sample.log', 'GP_sample_top.txt', 'GP_sample_modules.txt', 'GP_sampledump.txt',
  'gpcount.dll', 'GP_cand.log'
)
foreach ($n in $names) {
  $p = Join-Path $Game $n
  if (Test-Path $p) {
    Remove-Item $p -Force -ErrorAction SilentlyContinue
    if (Test-Path $p) { Write-Host "Locked: $n (exit game first)" -ForegroundColor Yellow }
    else { Write-Host "Removed $n" }
  }
}
Write-Host "Cleanup done. Fully exit game if DLL still loaded." -ForegroundColor Green
