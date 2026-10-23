param([string]$Game = 'D:\SteamLibrary\steamapps\common\Arma 3')
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $Game)) { Write-Host "找不到游戏目录: $Game" -ForegroundColor Red; exit 1 }
$dll = Join-Path $PSScriptRoot 'proxy\d3d11.dll'
if (-not (Test-Path $dll)) { Write-Host "缺少 $dll，先跑 inject\proxy\build.bat" -ForegroundColor Red; exit 1 }
Copy-Item $dll (Join-Path $Game 'd3d11.dll') -Force
# Ship polished defaults from presets\. Skip debug / alternate / example files.
$skip = @(
    'GP_present_contact.txt', 'GP_present_off.txt', 'GP_present_on.txt',
    'GP_expo_tight.txt', 'GP_expo_adapt.txt',
    'GP_light_auto.txt', 'GP_spec_boost.txt',
    'GP_probe.txt.example', 'GP_probe_mrt.txt.example',
    'GP_cb_dump.txt.example', 'GP_light_bind.txt.example'
)
Get-ChildItem (Join-Path $PSScriptRoot 'presets') -File | ForEach-Object {
    if ($skip -contains $_.Name) { return }
    if ($_.Name -like '*.example') { return }
    Copy-Item $_.FullName (Join-Path $Game $_.Name) -Force
}
# Always refresh DXBC payloads sitting next to presets.
foreach ($extra in @('GP_tonemap.dxbc', 'GP_ssao.dxbc')) {
    $src = Join-Path $PSScriptRoot "presets\$extra"
    if (-not (Test-Path $src)) { $src = Join-Path $PSScriptRoot $extra }
    if (Test-Path $src) { Copy-Item $src (Join-Path $Game $extra) -Force }
}
Write-Host "已部署：d3d11.dll + tonemap/amb/expo/light（接触阴影已搁置，强制 mode2）" -ForegroundColor Green
Write-Host "接触阴影：SHELVED（代码 kContactShelved=true，改 GP_present 无效）" -ForegroundColor Yellow
Write-Host "自动光向：GP_light_bind.txt + 复制 GP_light_auto.txt -> GP_light.txt" -ForegroundColor Cyan
Write-Host "自适应曝光：复制 GP_expo_adapt.txt -> GP_expo.txt" -ForegroundColor Cyan
Write-Host "镜面 boost：复制 GP_spec_boost.txt -> GP_spec.txt" -ForegroundColor Cyan
Write-Host "CB dump：复制 GP_cb_dump.txt.example -> GP_cb_dump.txt" -ForegroundColor Cyan
Write-Host "红 debug：复制 presets\GP_present_contact.txt -> GP_present.txt" -ForegroundColor Cyan
