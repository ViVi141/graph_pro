param([switch]$On, [switch]$Off)
# 开关注入器：d3d11.dll <-> d3d11.dll.off
$ErrorActionPreference = 'Stop'
$game = 'D:\SteamLibrary\steamapps\common\Arma 3'
$dll  = Join-Path $game 'd3d11.dll'
$offPath = Join-Path $game 'd3d11.dll.off'

if ($On) {
    if (Test-Path $offPath) { Move-Item $offPath $dll -Force }
    Write-Host "注入器：已开启" -ForegroundColor Green
} elseif ($Off) {
    if (Test-Path $dll) { Move-Item $dll $offPath -Force }
    Write-Host "注入器：已关闭（原生渲染）" -ForegroundColor Yellow
} else {
    if (Test-Path $dll) { Write-Host "注入器：开启中" -ForegroundColor Green } else { Write-Host "注入器：关闭" -ForegroundColor Yellow }
}
if (Test-Path (Join-Path $game 'GP_spec.txt')) {
    Write-Host ("材质镜面参数: " + (Get-Content (Join-Path $game 'GP_spec.txt')))
}
