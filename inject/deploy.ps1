param([string]$Game = 'D:\SteamLibrary\steamapps\common\Arma 3')
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $Game)) { Write-Host "找不到游戏目录: $Game" -ForegroundColor Red; exit 1 }
Copy-Item (Join-Path $PSScriptRoot 'proxy\d3d11.dll') (Join-Path $Game 'd3d11.dll') -Force
Copy-Item (Join-Path $PSScriptRoot 'presets\*') $Game -Force
Write-Host "已部署：d3d11.dll + presets（含 GP_light / GP_probe / GP_present_contact）" -ForegroundColor Green
Write-Host "探针：复制 GP_probe.txt.example 为 GP_probe.txt；接触阴影：复制 GP_present_contact.txt 为 GP_present.txt" -ForegroundColor Cyan
