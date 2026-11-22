param(
    [string]$Game = 'F:\SteamLibrary\steamapps\common\Arma 3'
)
$ErrorActionPreference = 'Stop'
if (Get-Process arma3* -ErrorAction SilentlyContinue) {
    Write-Host "请先完全退出 Arma 3 再卸载 DXVK。" -ForegroundColor Yellow
    exit 1
}
foreach ($f in @('d3d11.dll','dxgi.dll','dxvk.conf')) {
    $p = Join-Path $Game $f
    if (Test-Path $p) { Remove-Item $p -Force; Write-Host "Removed $p" -ForegroundColor DarkGray }
    $bak = "$p.bak_before_dxvk"
    if (Test-Path $bak) { Move-Item $bak $p -Force; Write-Host "Restored $p from backup" -ForegroundColor Green }
}
Write-Host "已卸载 DXVK，恢复原版 DX11 渲染。" -ForegroundColor Green
