param(
    [int]$SampleMinutes = 3,
    [int]$AttachDelaySec = 25,
    [switch]$SkipBuild,
    [switch]$KeepServer
)
# Headless DS CPU path: deploy MP mission -> arma3server_x64 -autoInit -> gpsample.
# Do NOT use d3d11 proxy. Client YAAB is separate (docs/13); this is server sim/AI.
$ErrorActionPreference = 'Stop'

$repo = Split-Path $PSScriptRoot -Parent
$game = 'D:\SteamLibrary\steamapps\common\Arma 3'
$serverExe = Join-Path $game 'arma3server_x64.exe'
$counter = Join-Path $repo 'inject\counter'
$missionSrc = Join-Path $repo 'mission\GP_ServerTest.Altis'
$missionDst = Join-Path $game 'MPMissions\GP_ServerTest.Altis'
# Entire profiles path must be space-free (game dir contains "Arma 3").
$prof = Join-Path $env:LOCALAPPDATA 'GP_arma_server'
$cfg = Join-Path $PSScriptRoot 'server.cfg'
$basic = Join-Path $PSScriptRoot 'basic.cfg'
New-Item -ItemType Directory -Force -Path $prof | Out-Null

if (-not (Test-Path $serverExe)) { throw "Missing $serverExe" }
if (-not (Test-Path $missionSrc)) { throw "Missing $missionSrc" }

# --- strip graphics proxy (conflicts with CPU sampler docs) ---
$proxy = Join-Path $game 'd3d11.dll'
if (Test-Path $proxy) {
    Remove-Item $proxy -Force
    Write-Host "Removed d3d11.dll (CPU path)" -ForegroundColor Yellow
}

# --- deploy mission ---
if (Test-Path $missionDst) { Remove-Item $missionDst -Recurse -Force }
New-Item -ItemType Directory -Force -Path $missionDst | Out-Null
Copy-Item (Join-Path $missionSrc '*') $missionDst -Force
Write-Host "Mission -> $missionDst" -ForegroundColor Green

# --- funcs table = SERVER pdata ---
if (-not $SkipBuild) {
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $counter 'prepare_funcs.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'prepare_funcs failed' }
}
$serverFuncs = Join-Path $counter 'funcs_server.bin'
if (-not (Test-Path $serverFuncs)) { throw "Missing $serverFuncs - prepare_funcs.ps1" }
Copy-Item $serverFuncs (Join-Path $counter 'funcs.bin') -Force
Write-Host "funcs.bin <= funcs_server.bin" -ForegroundColor DarkGray

# GP_sample.txt: interval_ms auto_dump_sec max_min
$sampleTxt = Join-Path $counter 'GP_sample.txt'
Set-Content -Path $sampleTxt -Value "50 60 $SampleMinutes" -Encoding Ascii -NoNewline

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $counter 'deploy_sample.ps1') -Game $game
if ($LASTEXITCODE -ne 0) { throw 'deploy_sample failed' }

# --- stop old server/client ---
Get-Process arma3server_x64, arma3_x64 -EA SilentlyContinue | ForEach-Object {
    Write-Host "Stopping $($_.Name) pid=$($_.Id)" -ForegroundColor Yellow
    $_ | Stop-Process -Force
}
Start-Sleep -Seconds 2

# --- start DS ---
# Start-Process quotes each arg that contains spaces; do not nest extra quotes.
$srvArgs = @(
    '-port=2302',
    "-config=$cfg",
    "-cfg=$basic",
    "-profiles=$prof",
    '-world=empty',
    '-autoInit',
    '-name=GPTest',
    '-nosound'
)
Write-Host ("Launch: {0} {1}" -f $serverExe, ($srvArgs -join ' ')) -ForegroundColor Cyan
$proc = Start-Process -FilePath $serverExe -WorkingDirectory $game -ArgumentList $srvArgs -PassThru
Write-Host "Server pid=$($proc.Id)" -ForegroundColor Green

Write-Host "Waiting ${AttachDelaySec}s for mission init..." -ForegroundColor DarkGray
Start-Sleep -Seconds $AttachDelaySec

if (-not (Get-Process -Id $proc.Id -EA SilentlyContinue)) {
    throw 'Server exited early — check Documents\Arma 3\*.rpt'
}

# RPT quick check
$rpt = Get-ChildItem $prof -Filter 'arma3server_x64_*.rpt' -EA SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($rpt) {
    $hits = @(Select-String -Path $rpt.FullName -Pattern '\[GP\]|cannot play|deleted|Mission' -EA SilentlyContinue | Select-Object -Last 15)
    $hits | ForEach-Object { Write-Host ("RPT: " + $_.Line) -ForegroundColor DarkCyan }
    if (Select-String -Path $rpt.FullName -Pattern 'cannot play/edit this mission|downloadable content that has been deleted' -Quiet) {
        throw "Mission rejected by DS — see $($rpt.FullName)"
    }
}

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $counter 'attach_sample.ps1') `
    -Game $game -Process 'arma3server_x64.exe'
if ($LASTEXITCODE -ne 0) { throw 'attach_sample failed' }

$waitSec = [Math]::Max(60, $SampleMinutes * 60 + 15)
Write-Host "Sampling ~${SampleMinutes} min (wait ${waitSec}s)..." -ForegroundColor Cyan
Start-Sleep -Seconds $waitSec

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $counter 'dump_sample.ps1') -Game $game
Write-Host "---- GP_sample_modules (top) ----" -ForegroundColor Green
Get-Content (Join-Path $game 'GP_sample_modules.txt') -EA SilentlyContinue | Select-Object -First 25
Write-Host "---- GP_sample_top (top 15) ----" -ForegroundColor Green
Get-Content (Join-Path $game 'GP_sample_top.txt') -EA SilentlyContinue | Select-Object -First 20

if (-not $KeepServer) {
    Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
    Write-Host "Server stopped." -ForegroundColor Yellow
} else {
    Write-Host "Server left running (KeepServer)." -ForegroundColor Cyan
}

Write-Host "Done. Backups under extract\cpu_samples\ ; live files in game dir." -ForegroundColor Green
