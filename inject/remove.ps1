param([string]$Game = 'D:\SteamLibrary\steamapps\common\Arma 3')
$ErrorActionPreference = 'SilentlyContinue'
$dll = Join-Path $Game 'd3d11.dll'
if (Test-Path $dll) { Remove-Item $dll -Force }
Get-ChildItem $Game -Filter 'GP_*' | Remove-Item -Force
Write-Host "已移除注入器与预设，游戏恢复原生渲染" -ForegroundColor Yellow
