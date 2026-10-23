param(
    [switch]$Remove
)
# Deploy mission\GP_Min.Altis to Documents\Arma 3\missions\
# ASCII only: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI and would
# fail on non-ASCII quotes/box characters.
$ErrorActionPreference = 'Stop'
$src = Join-Path $PSScriptRoot 'GP_Min.Altis'
$dst = Join-Path $env:USERPROFILE 'Documents\Arma 3\missions\GP_Min.Altis'

if ($Remove) {
    if (Test-Path $dst) {
        Remove-Item $dst -Recurse -Force
        Write-Host "Removed $dst" -ForegroundColor Yellow
    }
    return
}

if (-not (Test-Path $src)) { throw "Source not found: $src" }
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item (Join-Path $src '*') $dst -Force

Write-Host "Deployed -> $dst" -ForegroundColor Green
Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  1. Start Arma 3. No mods, no d3d11.dll."
Write-Host "  2. Main menu -> PLAY -> SCENARIOS -> pick 'GP Min'."
Write-Host "  3. After the scene appears wait ~15 s, then Esc -> Abort."
Write-Host "  4. Tell me 'done'. I will read the RPT and screenshots."
Write-Host ""
Write-Host "Output:" -ForegroundColor Cyan
Write-Host "  log:    $env:USERPROFILE\Documents\Arma 3\arma3_x64_*.rpt  (search [GP] MAT)"
Write-Host "  shots:  $env:USERPROFILE\Documents\Arma 3\Screenshots\gp_min_base*.png"
