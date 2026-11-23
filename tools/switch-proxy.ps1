#Requires -Version 5.0
<#
Switch the deployed Universal proxy between two builds, without touching the
graphics pack or the game configs.

  powershell -ExecutionPolicy Bypass -File tools\switch-proxy.ps1 -Build old

(On a machine with the default Restricted policy the plain form is blocked with
"not digitally signed"; add -ExecutionPolicy Bypass as above.)
  powershell -File tools\switch-proxy.ps1 -Build old   # pre-2026-11-23 build (1345aed)
  powershell -File tools\switch-proxy.ps1 -Build new   # current HEAD build

The "old" build is compiled from the last commit that predates the
2026-11-23 fix batch; it is kept in dist\_builds so a regression can be pinned
to a build in one command instead of a rebuild.

Only d3d11.dll is swapped. GP_*.dxbc / GP_replace.txt / dxvk.conf are untouched.
#>
param(
    [string]$Game = $env:ARMA3_DIR,
    [ValidateSet('', 'old', 'new')]
    [string]$Build = ''
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$old = Join-Path $repo 'dist\_builds\d3d11_pre20261123.dll'
$new = Join-Path $repo 'inject\universal\d3d11.dll'

function Find-Arma3Dir {
    $reg = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Bohemia Interactive\Arma 3' -ErrorAction SilentlyContinue
    if ($reg -and $reg.main -and (Test-Path (Join-Path $reg.main 'Arma3_x64.exe'))) { return $reg.main }
    return ''
}

if (-not $Game) { $Game = Find-Arma3Dir }
if (-not $Game -or -not (Test-Path (Join-Path $Game 'Arma3_x64.exe'))) {
    throw 'Arma 3 not found. Set ARMA3_DIR or pass -Game "<path>".'
}
$dst = Join-Path $Game 'd3d11.dll'
function Show([string]$p) {
    if (-not (Test-Path $p)) { return 'missing' }
    $h = (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.Substring(0, 16)
    return "$h  $([math]::Round((Get-Item $p).Length / 1KB, 0)) KB"
}

Write-Host "Arma 3 : $Game"
Write-Host "deployed : $(Show $dst)"
Write-Host "old build: $(Show $old)"
Write-Host "new build: $(Show $new)"

# A DXVK dxgi.dll with no proxy d3d11.dll is an illegal mix: the system d3d11
# pairs with DXVK's DXGI and the client dies inside d3d11.dll at adapter init
# (minidump 2026-11-23 21:24 shows exactly that). Never leave it that way.
$dxgi = Join-Path $Game 'dxgi.dll'
if ((Test-Path $dxgi) -and -not (Test-Path $dst)) {
    Write-Host 'WARNING: dxgi.dll (DXVK) is deployed but d3d11.dll is missing.' -ForegroundColor Red
    Write-Host '         Launching now crashes the client inside the system d3d11.dll.' -ForegroundColor Red
}

if (-not $Build) { exit 0 }
# Only the game itself locks d3d11.dll; arma3launcher does not, and the wildcard
# "arma3*" used elsewhere matches the launcher and blocks a perfectly safe swap.
$running = Get-Process -Name 'arma3', 'arma3_x64', 'arma3_x64_test' -ErrorAction SilentlyContinue
if ($running) {
    throw "Arma 3 is running ($($running[0].Name)) - close it first."
}
$src = if ($Build -eq 'old') { $old } else { $new }
if (-not (Test-Path $src)) { throw "build not found: $src" }
Copy-Item -LiteralPath $src -Destination $dst -Force
if (-not (Test-Path $dst)) { throw "copy failed: $dst does not exist" }
$want = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
$got = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash
if ($want -ne $got) { throw "copy is not intact: $dst hash mismatch" }
$log = Join-Path $Game 'GP_universal.log'
if (Test-Path $log) { Remove-Item -LiteralPath $log -Force }
Write-Host "deployed $Build -> $(Show $dst)  [verified]" -ForegroundColor Green
