param(
    [ValidateSet('shot2', 'min')]
    [string]$Mission = 'shot2',
    [switch]$KeepRunning,
    [switch]$NoProxyCheck
)
# Auto-enter SP mission via -init=playMission (BI wiki).
# Mission MUST live under <game>\Missions\, NOT Documents\Arma 3\missions\.
# -mission=... is wrong for SP play; bare mission.sqm path opens Eden.
# Dedicated server does NOT render — graphics A/B needs this client path.
$ErrorActionPreference = 'Stop'

$game = 'D:\SteamLibrary\steamapps\common\Arma 3'
$exe = Join-Path $game 'arma3_x64.exe'
$gameMissions = Join-Path $game 'Missions'
$repoMission = $PSScriptRoot

if (-not (Test-Path $exe)) { throw "Game not found: $exe" }
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
        $srcFiles = Get-ChildItem $srcDir -File | ForEach-Object {
            @{ Src = $_.FullName; Dst = $_.Name }
        }
    }
}

$dst = Join-Path $gameMissions $name
New-Item -ItemType Directory -Force -Path $dst | Out-Null
foreach ($f in $srcFiles) {
    if (-not (Test-Path $f.Src)) { throw "Missing $($f.Src)" }
    Copy-Item $f.Src (Join-Path $dst $f.Dst) -Force
}
Write-Host "Deployed -> $dst" -ForegroundColor Green

# Keep a Documents copy for manual PLAY -> SCENARIOS too.
$docDst = Join-Path $env:USERPROFILE "Documents\Arma 3\missions\$name"
New-Item -ItemType Directory -Force -Path $docDst | Out-Null
foreach ($f in $srcFiles) {
    Copy-Item $f.Src (Join-Path $docDst $f.Dst) -Force
}

if (-not $NoProxyCheck) {
    $dll = Join-Path $game 'd3d11.dll'
    if (Test-Path $dll) {
        Write-Host "proxy OK: $dll" -ForegroundColor DarkGray
    } else {
        Write-Host "WARN: no d3d11.dll in game dir (vanilla render)" -ForegroundColor Yellow
    }
}

if (-not $KeepRunning) {
    Get-Process arma3_x64 -EA SilentlyContinue | ForEach-Object {
        Write-Host "Stopping pid=$($_.Id)" -ForegroundColor Yellow
        $_ | Stop-Process -Force
    }
    Start-Sleep -Seconds 2
}

# SQF single-quoted strings avoid PowerShell escaping hell.
# Wiki: arma3_x64.exe -init=playMission["","Test.VR"]
# Prefer Steam applaunch so Windows GPU preference / Steam overlay match normal play
# (direct Start-Process has been observed to bind Intel iGPU on this machine).
$init = "-init=playMission['','$name']"
$gameArgs = @(
    '-skipIntro',
    '-noSplash',
    '-window',
    '-showScriptErrors',
    '-noPause',
    '-enableHT',
    $init
)
$steam = @(
    "${env:ProgramFiles(x86)}\Steam\steam.exe",
    "$env:ProgramFiles\Steam\steam.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($steam) {
    $launch = @('-applaunch', '107410') + $gameArgs
    Write-Host ("Launch via Steam: {0} {1}" -f $steam, ($launch -join ' ')) -ForegroundColor Cyan
    Start-Process -FilePath $steam -ArgumentList $launch
} else {
    Write-Host ("Launch direct: {0} {1}" -f $exe, ($gameArgs -join ' ')) -ForegroundColor Yellow
    Start-Process -FilePath $exe -WorkingDirectory $game -ArgumentList $gameArgs
}

Write-Host ""
Write-Host "playMission from main menu -> $name" -ForegroundColor Green
Write-Host "Shots: $env:USERPROFILE\Documents\Arma 3\Screenshots\"
Write-Host "RPT:   $env:USERPROFILE\AppData\Local\Arma 3\arma3_x64_*.rpt  (search [GP])"
Write-Host "Proxy: $game\GP_shader.log"
