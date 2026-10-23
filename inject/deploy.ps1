param([string]$Game = 'D:\SteamLibrary\steamapps\common\Arma 3')
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $Game)) { Write-Host "找不到游戏目录: $Game" -ForegroundColor Red; exit 1 }
$dll = Join-Path $PSScriptRoot 'proxy\d3d11.dll'
if (-not (Test-Path $dll)) { Write-Host "缺少 $dll，先跑 inject\proxy\build.bat" -ForegroundColor Red; exit 1 }
Copy-Item $dll (Join-Path $Game 'd3d11.dll') -Force
# Ship v1 defaults from presets\ (tonemap + amb + expo + present mode0 + light).
# Skip debug-only / example files that must not override the ship present mode.
$skip = @('GP_present_contact.txt', 'GP_present_off.txt', 'GP_expo_tight.txt', 'GP_probe.txt.example')
Get-ChildItem (Join-Path $PSScriptRoot 'presets') -File | ForEach-Object {
    if ($skip -contains $_.Name) { return }
    Copy-Item $_.FullName (Join-Path $Game $_.Name) -Force
}
# Always refresh DXBC payloads sitting next to presets.
foreach ($extra in @('GP_tonemap.dxbc', 'GP_ssao.dxbc')) {
    $src = Join-Path $PSScriptRoot "presets\$extra"
    if (-not (Test-Path $src)) { $src = Join-Path $PSScriptRoot $extra }
    if (Test-Path $src) { Copy-Item $src (Join-Path $Game $extra) -Force }
}
Write-Host "已部署 v1：d3d11.dll + tonemap/amb/expo/present(mode0)/light（spec 关闭）" -ForegroundColor Green
Write-Host "关接触阴影：复制 presets\GP_present_off.txt -> 游戏目录 GP_present.txt" -ForegroundColor Cyan
Write-Host "紧曝光实验：复制 presets\GP_expo_tight.txt -> GP_expo.txt" -ForegroundColor Cyan
Write-Host "红 debug：复制 presets\GP_present_contact.txt -> GP_present.txt" -ForegroundColor Cyan
