param(
    [ValidateSet('shot2', 'min')]
    [string]$Mission = 'shot2',
    [string]$Game = $env:ARMA3_DIR
)
# Deploy the SP screenshot missions and STOP THERE.
#
# This script never starts, stops, focuses or otherwise touches the game process.
# Launching Arma 3 is the user's job: open Play -> Scenarios -> GP Shot 2, or use
# the launcher. (The old run-cli.ps1 did launch the client and has been deleted.)
$ErrorActionPreference = 'Stop'

if (-not $Game) { throw 'Set ARMA3_DIR or pass -Game "<path to Arma 3>"' }
if (-not (Test-Path -LiteralPath $Game)) { Write-Host "Game directory not found: $Game" -ForegroundColor Red; exit 1 }

$repoMission = $PSScriptRoot
$gameMissions = Join-Path $Game 'Missions'
New-Item -ItemType Directory -Force -Path $gameMissions | Out-Null

switch ($Mission) {
    'shot2' {
        $name = 'GP_Shot2.Altis'
        $srcFiles = @(
            @{ Src = (Join-Path $repoMission 'mission.sqm'); Dst = 'mission.sqm' },
            @{ Src = (Join-Path $repoMission 'init.sqf');     Dst = 'init.sqf' }
        )
    }
    'min' {
        $name = 'GP_Min.Altis'
        $srcDir = Join-Path $repoMission 'GP_Min.Altis'
        $srcFiles = Get-ChildItem $srcDir -File | ForEach-Object { @{ Src = $_.FullName; Dst = $_.Name } }
    }
}

# Game-side copy: required for "Play -> Scenarios" (Arma only lists Missions\).
$dst = Join-Path $gameMissions $name
New-Item -ItemType Directory -Force -Path $dst | Out-Null
foreach ($f in $srcFiles) {
    if (-not (Test-Path $f.Src)) { throw "Missing $($f.Src)" }
    Copy-Item $f.Src (Join-Path $dst $f.Dst) -Force
}
Write-Host "Deployed (game):      $dst" -ForegroundColor Green

# Documents copy: keeps the mission visible in the editor too.
$docDst = Join-Path $env:USERPROFILE "Documents\Arma 3\missions\$name"
New-Item -ItemType Directory -Force -Path $docDst | Out-Null
foreach ($f in $srcFiles) { Copy-Item $f.Src (Join-Path $docDst $f.Dst) -Force }
Write-Host "Deployed (documents): $docDst" -ForegroundColor Green

$dll = Join-Path $Game 'd3d11.dll'
if (Test-Path $dll) {
    Write-Host "Proxy present: $dll" -ForegroundColor DarkGray
} else {
    Write-Host "WARN: no d3d11.dll in the game dir -> vanilla render" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Next step is manual: start Arma 3 yourself, then Play -> Scenarios -> $name" -ForegroundColor Cyan
Write-Host "Screenshots land in: $env:USERPROFILE\Documents\Arma 3\Screenshots" -ForegroundColor Cyan
Write-Host "NOTE: Arma refuses to save once that folder passes 250 MB." -ForegroundColor Yellow
