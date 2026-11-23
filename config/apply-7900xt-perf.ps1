param(
    [string]$ProfileName = 'ViVi141',
    [ValidateSet('ultragpu_smartcpu', 'high_fps_noclouds')]
    [string]$Preset = 'ultragpu_smartcpu',
    [switch]$Restore
)
$ErrorActionPreference = 'Stop'
if (Get-Process arma3* -ErrorAction SilentlyContinue) {
    Write-Host "请先完全退出 Arma 3 再修改配置。" -ForegroundColor Yellow
    exit 1
}

$cfgPath = Join-Path $env:USERPROFILE 'Documents\Arma 3\Arma3.cfg'
$profPath = Join-Path $env:USERPROFILE "Documents\Arma 3 - Other Profiles\$ProfileName\$ProfileName.Arma3Profile"
$bakDir = Join-Path $PSScriptRoot "backup-7900xt-$ProfileName"

if ($Restore) {
    if (-not (Test-Path $bakDir)) { throw "未找到备份目录: $bakDir" }
    Copy-Item (Join-Path $bakDir 'Arma3.cfg') $cfgPath -Force
    Copy-Item (Join-Path $bakDir "$ProfileName.Arma3Profile") $profPath -Force
    Write-Host "已从 $bakDir 恢复原版 Arma3.cfg 与 $ProfileName.Arma3Profile" -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $bakDir)) {
    New-Item -ItemType Directory -Force -Path $bakDir | Out-Null
    Copy-Item $cfgPath (Join-Path $bakDir 'Arma3.cfg') -Force
    Copy-Item $profPath (Join-Path $bakDir "$ProfileName.Arma3Profile") -Force
    Write-Host "已备份原始配置 -> $bakDir" -ForegroundColor Cyan
}

function Apply-KV([string]$text, [hashtable]$map) {
    foreach ($k in $map.Keys) {
        $v = $map[$k]
        if ($text -match "(?m)^$k=[^;]*;") {
            $text = [regex]::Replace($text, "(?m)^$k=[^;]*;", "$k=$v;")
        } else {
            $text += "`r`n$k=$v;"
        }
    }
    return $text
}

# PowerShell 5.1's "-Encoding UTF8" writes a BOM, which would prefix the first
# Arma 3 key with U+FEFF. Write UTF-8 without a BOM and strip an existing one.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Write-TextNoBom([string]$path, [string]$text) {
    if ($text.Length -gt 0 -and $text[0] -eq [char]0xFEFF) { $text = $text.Substring(1) }
    [System.IO.File]::WriteAllText($path, $text, $utf8NoBom)
}

$cfgMap = @{
    vsync = 0
    GPU_MaxFramesAhead = 1
    multiSampleCount = 4
    AToC = 15
    PPAA = 2
    ppSSAO = 6
    cloudsQuality = $(if ($Preset -eq 'high_fps_noclouds') { 0 } else { 4 })
}
$profMap = @{
    sceneComplexity = 400000
    preferredObjectViewDistance = 1000
    viewDistance = 3800
    shadowQuality = 5
    shadowZDistance = 100
    terrainGrid = $(if ($Preset -eq 'high_fps_noclouds') { 25 } else { 12.5 })
    pipViewDistance = 500
}

Write-TextNoBom $cfgPath (Apply-KV (Get-Content $cfgPath -Raw) $cfgMap)
Write-TextNoBom $profPath (Apply-KV (Get-Content $profPath -Raw) $profMap)
Write-Host "已应用 7900X + 7900 XT 性能档 [$Preset]（保留 1440p / 4x MSAA / Ultra 贴图与阴影 / 3800m 地形视距）" -ForegroundColor Green
Write-Host "实测搭配 DXVK 3.1.1：ultragpu_smartcpu = 71.05 FPS (+17.5%, 1% Low +20.9%)；high_fps_noclouds = 74.57 FPS (+23.4%, 1% Low +32.2%)" -ForegroundColor Cyan
Write-Host "一键还原：powershell -File config\apply-7900xt-perf.ps1 -Restore" -ForegroundColor DarkGray
