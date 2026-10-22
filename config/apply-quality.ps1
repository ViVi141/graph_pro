param([switch]$Force)
# 把 config\quality 下的画质配置写入 Documents\Arma 3
$ErrorActionPreference = 'Stop'
$game = Get-Process arma3_x64 -ErrorAction SilentlyContinue
if ($game -and -not $Force) { Write-Host "游戏正在运行，配置会在退出时被覆写。关闭游戏或加 -Force" -ForegroundColor Yellow; exit 1 }
$src = Join-Path $PSScriptRoot 'quality'
$dst = Join-Path $env:USERPROFILE 'Documents\Arma 3'
Copy-Item (Join-Path $src 'Arma3.cfg') $dst -Force
Copy-Item (Join-Path $src '74738.Arma3Profile') $dst -Force
Write-Host "已应用画质配置（需重启游戏生效）" -ForegroundColor Green
