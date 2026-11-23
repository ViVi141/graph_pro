param(
    [string]$Graphics = 'agx',
    [string]$Tier = 'auto'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$game = 'F:\SteamLibrary\steamapps\common\Arma 3'

& (Join-Path $repo 'dist\graph_pro_universal\install.ps1') -Graphics $Graphics -Tier $Tier -Silent

$rptDir = Join-Path $env:LOCALAPPDATA 'Arma 3'
$before = @{}
Get-ChildItem $rptDir -Filter 'Arma3_x64_*.rpt' -ErrorAction SilentlyContinue | ForEach-Object { $before[$_.FullName] = $true }

$argsList = @('-skipIntro','-noSplash','-name=ViVi141','-enableHT','-hugePages','-noPause',"-init=playMission['','GP_YAAB_Auto.Altis']")
$p = Start-Process -FilePath (Join-Path $game 'Arma3_x64.exe') -WorkingDirectory $game -ArgumentList $argsList -PassThru

$t0 = Get-Date
$rpt = $null
while (-not $rpt -and ((Get-Date) - $t0).TotalSeconds -lt 45) {
    Start-Sleep -Milliseconds 500
    $cand = Get-ChildItem $rptDir -Filter 'Arma3_x64_*.rpt' -ErrorAction SilentlyContinue |
        Where-Object { -not $before.ContainsKey($_.FullName) } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($cand) { $rpt = $cand.FullName }
}
Write-Host "E2E RPT: $rpt" -ForegroundColor DarkGray

$res = $null
while (((Get-Date) - $t0).TotalSeconds -lt 220) {
    if ($p.HasExited) { break }
    Start-Sleep -Seconds 1
    $txt = Get-Content $rpt -Raw -ErrorAction SilentlyContinue
    if ($txt -and $txt -match '\[GP_YAAB_RESULT\][^\r\n]+') {
        $res = $Matches[0]
        Write-Host "E2E RESULT: $res" -ForegroundColor Green
        break
    }
}
if (-not $p.HasExited) {
    Start-Sleep -Seconds 2
    if (-not $p.HasExited) { $p | Stop-Process -Force }
}
Start-Sleep -Seconds 2

Write-Host "=== GP_universal.log ===" -ForegroundColor Cyan
Get-Content (Join-Path $game 'GP_universal.log') -ErrorAction SilentlyContinue

Write-Host "=== UNINSTALL TEST ===" -ForegroundColor Yellow
& (Join-Path $repo 'dist\graph_pro_universal\uninstall.ps1') -Silent
