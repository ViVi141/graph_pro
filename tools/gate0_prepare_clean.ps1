# 为 RenderDoc 干净抓帧临时移走 d3d11 代理
param(
  [string]$Game = 'D:\SteamLibrary\steamapps\common\Arma 3',
  [switch]$Restore
)
$ErrorActionPreference = 'Stop'
$dll = Join-Path $Game 'd3d11.dll'
$off = Join-Path $Game 'd3d11.dll.gp_off'
if ($Restore) {
  if (Test-Path $off) {
    if (Test-Path $dll) { Remove-Item $dll -Force }
    Rename-Item $off 'd3d11.dll'
    Write-Host "已恢复代理 d3d11.dll" -ForegroundColor Green
  } else { Write-Host "没有 d3d11.dll.gp_off" -ForegroundColor Yellow }
  exit 0
}
if (-not (Test-Path $dll)) { Write-Host "游戏目录无 d3d11.dll，已是干净状态" -ForegroundColor Cyan; exit 0 }
if (Test-Path $off) { Remove-Item $off -Force }
Rename-Item $dll 'd3d11.dll.gp_off'
Write-Host "已移走代理 -> d3d11.dll.gp_off；可用 RenderDoc 启动游戏" -ForegroundColor Green
Write-Host "结束后: powershell -File tools\gate0_prepare_clean.ps1 -Restore" -ForegroundColor Cyan
