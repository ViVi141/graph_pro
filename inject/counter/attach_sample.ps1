# Inject gpsample.dll into a running Arma3_x64 process.
# ASCII-only messages: PS 5.1 defaults to system codepage without BOM.
param(
  [string]$Game = 'D:\SteamLibrary\steamapps\common\Arma 3',
  [string]$Process = 'Arma3_x64.exe'
)
$ErrorActionPreference = 'Stop'
$dll = Join-Path $Game 'gpsample.dll'
$inj = Join-Path $Game 'injector.exe'
if (-not (Test-Path $dll)) {
  Write-Host "Missing $dll - run deploy_sample.ps1 first" -ForegroundColor Red
  exit 1
}
if (-not (Test-Path $inj)) {
  Write-Host "Missing $inj" -ForegroundColor Red
  exit 1
}
& $inj $Process $dll
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Injected. After YAAB: dump_sample.ps1 (or wait auto-dump)." -ForegroundColor Green
Write-Host "Log: $Game\GP_sample.log / GP_sample_top.txt" -ForegroundColor Cyan
