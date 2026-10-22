$ErrorActionPreference = 'Stop'
$game = Get-Process arma3_x64 -ErrorAction SilentlyContinue
if ($game) { Write-Host "请先关闭游戏" -ForegroundColor Yellow; exit 1 }
$src = Join-Path $PSScriptRoot 'original'
$dst = Join-Path $env:USERPROFILE 'Documents\Arma 3'
Copy-Item (Join-Path $src 'Arma3.cfg') $dst -Force
Copy-Item (Join-Path $src '74738.Arma3Profile') $dst -Force
Write-Host "已恢复原始配置" -ForegroundColor Green
