param(
    [ValidateSet('high', 'low')]
    [string]$Load = 'high',
    [int]$Seconds = 45
)
# Headless A/B: same mission, different AI counts. Reports mean diag_fps from RPT [GP] tick.
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$game = 'D:\SteamLibrary\steamapps\common\Arma 3'
$serverExe = Join-Path $game 'arma3server_x64.exe'
$missionSrc = Join-Path $repo 'mission\GP_ServerTest.Altis'
$missionDst = Join-Path $game 'MPMissions\GP_ServerTest.Altis'
# Space-free: game dir contains "Arma 3" which breaks -profiles= argv.
$prof = Join-Path $env:LOCALAPPDATA 'GP_arma_server'
$cfg = Join-Path $PSScriptRoot 'server.cfg'
$basic = Join-Path $PSScriptRoot 'basic.cfg'
New-Item -ItemType Directory -Force -Path $prof | Out-Null

# Strip graphics proxy
Remove-Item (Join-Path $game 'd3d11.dll') -Force -EA SilentlyContinue

Get-Process arma3server_x64, arma3_x64 -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# Patch nGroups into a temp initServer
$nGroups = if ($Load -eq 'high') { 48 } else { 8 }
$init = Get-Content (Join-Path $missionSrc 'initServer.sqf') -Raw
$init2 = [regex]::Replace($init, 'private _nGroups = \d+;', "private _nGroups = $nGroups;")
New-Item -ItemType Directory -Force -Path $missionDst | Out-Null
Copy-Item (Join-Path $missionSrc '*') $missionDst -Force
Set-Content -Path (Join-Path $missionDst 'initServer.sqf') -Value $init2 -Encoding UTF8

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
$p = Start-Process -FilePath $serverExe -WorkingDirectory $game -ArgumentList $srvArgs -PassThru
Write-Host "load=$Load nGroups=$nGroups pid=$($p.Id) wait ${Seconds}s" -ForegroundColor Cyan
Start-Sleep -Seconds $Seconds

# Only accept RPTs written after this launch.
$rpt = Get-ChildItem $prof -Recurse -Filter 'arma3server_x64_*.rpt' -EA SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt $p.StartTime.AddSeconds(-5) } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $rpt) { throw "no fresh RPT under $prof (profiles path broken?)" }

$ticks = @(Select-String -Path $rpt.FullName -Pattern '\[GP\] tick=(\d+) units=(\d+) fps=([\d.]+)')
# Prefer ticks that mention our nGroups spawn line epoch — take last N from this file
$fps = @()
$units = @()
foreach ($t in $ticks) {
    $m = $t.Matches[0]
    $fps += [double]$m.Groups[3].Value
    $units += [int]$m.Groups[2].Value
}
# skip first 3 ticks (spawn settle)
if ($fps.Count -gt 3) {
    $fps = $fps[3..($fps.Count - 1)]
    $units = $units[3..($units.Count - 1)]
}
$mean = if ($fps.Count) { ($fps | Measure-Object -Average).Average } else { 0 }
$min = if ($fps.Count) { ($fps | Measure-Object -Minimum).Minimum } else { 0 }
$max = if ($fps.Count) { ($fps | Measure-Object -Maximum).Maximum } else { 0 }
$lastUnits = if ($units.Count) { $units[-1] } else { '?' }

$result = [pscustomobject]@{
    Load = $Load
    NGroups = $nGroups
    Ticks = $fps.Count
    UnitsLast = $lastUnits
    FpsMean = [math]::Round($mean, 2)
    FpsMin = [math]::Round($min, 2)
    FpsMax = [math]::Round($max, 2)
    Rpt = $rpt.FullName
}
$result | Format-List
$out = Join-Path $repo "extract\cpu_samples\ab_ai_$Load.json"
$result | ConvertTo-Json | Set-Content $out -Encoding UTF8
Write-Host "wrote $out" -ForegroundColor Green

Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
