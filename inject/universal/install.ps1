#Requires -Version 5.0
param(
    [string]$Game = '',
    [ValidateSet('auto', 'high', 'high_fps', 'mid', 'igpu', 'none')]
    [string]$Tier = 'auto',
    [ValidateSet('auto', 'dxvk', 'native')]
    [string]$Backend = 'auto',
    [ValidateSet('off', 'agx', 'legacy')]
    [string]$Graphics = 'off',
    [switch]$Silent
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src  = Join-Path $here 'files'

if (Get-Process arma3*, arma3_x64, arma3server* -ErrorAction SilentlyContinue) {
    Write-Host "请先完全退出 Arma 3 再安装。" -ForegroundColor Yellow
    exit 1
}

# 1. Auto-detect Arma 3 installation directory
function Find-Arma3Dir {
    $reg = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Bohemia Interactive\Arma 3' -ErrorAction SilentlyContinue
    if ($reg -and $reg.main -and (Test-Path (Join-Path $reg.main 'Arma3_x64.exe'))) { return $reg.main }
    $sreg = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam','HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue
    $steam = ($sreg.InstallPath + $sreg.SteamPath) | Where-Object { $_ } | Select-Object -First 1
    if ($steam) {
        $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
        if (Test-Path $vdf) {
            $libs = Select-String -Path $vdf -Pattern '"path"\s+"([^"]+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value -replace '\\\\','\' }
            foreach ($l in $libs) {
                $cand = Join-Path $l 'steamapps\common\Arma 3'
                if (Test-Path (Join-Path $cand 'Arma3_x64.exe')) { return $cand }
            }
        }
    }
    return ''
}

if (-not $Game) { $Game = Find-Arma3Dir }
if (-not $Game -or -not (Test-Path (Join-Path $Game 'Arma3_x64.exe'))) {
    if ($Silent) { throw "Arma 3 not found. Pass -Game <path>" }
    $Game = Read-Host '请输入 Arma 3 根目录（包含 Arma3_x64.exe）'
}
if (-not (Test-Path (Join-Path $Game 'Arma3_x64.exe'))) {
    throw "未找到 Arma3_x64.exe: $Game"
}

# 2. Detect CPU & GPU hardware
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$logicalCores = [int]$cpu.NumberOfLogicalProcessors
$compThreads = [Math]::Min(8, [Math]::Max(2, [int]($logicalCores / 2)))

$gpus = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -notmatch 'Virtual|Microsoft Basic|GameViewer' }
$bestGpu = $gpus | Sort-Object {
    $n = $_.Name
    if ($n -match 'RTX|RX 7|RX 6|RX 9|GTX 1080|GTX 1070|Arc A7|Arc B5') { 3 }
    elseif ($n -match 'GTX|RX 5|Radeon Pro|Arc') { 2 }
    else { 1 }
} -Descending | Select-Object -First 1
$gpuName = if ($bestGpu) { $bestGpu.Name } else { 'Unknown GPU' }

if ($Tier -eq 'auto') {
    if ($gpuName -match '7900|7800|7700|6900|6800|9070|4090|4080|4070|5090|5080|5070|3090|3080|3070') { $Tier = 'high' }
    elseif ($gpuName -match 'RTX|RX 6|RX 7|RX 5|GTX 16|GTX 10|Arc') { $Tier = 'mid' }
    else { $Tier = 'igpu' }
}

Write-Host "=== GraphPro Universal Installer (Pure-Perf Base) ===" -ForegroundColor Cyan
Write-Host "  Arma 3   : $Game"
Write-Host "  CPU      : $($cpu.Name.Trim()) ($logicalCores threads -> dxvk.numCompilerThreads=$compThreads)"
Write-Host "  GPU      : $gpuName (tier=$Tier, backend=$Backend, graphics=$Graphics)"

# 3. Backup any existing user d3d11/dxgi DLLs
$bakDir = Join-Path $Game '_gp_universal_backup'
New-Item -ItemType Directory -Force -Path $bakDir | Out-Null
foreach ($f in @('d3d11.dll','dxgi.dll','dxvk.conf')) {
    $dst = Join-Path $Game $f
    $bak = Join-Path $bakDir $f
    if ((Test-Path $dst) -and -not (Test-Path $bak)) {
        Copy-Item $dst $bak -Force
    }
}

# Clean any leftover GP_* graphics configs before deploying
foreach ($f in @('GP_replace.txt','GP_tonemap.dxbc','GP_ssao.dxbc','GP_amb.txt','GP_amb_stylized.txt','GP_expo.txt','GP_spec.txt')) {
    $p = Join-Path $Game $f
    if (Test-Path $p) { Remove-Item $p -Force }
}

# 4. Deploy Backend (Pure DXVK when Graphics=off for ZERO proxy overhead; Chained Universal Proxy when Graphics!=off)
if ($Graphics -eq 'off' -and $Backend -ne 'native') {
    Copy-Item (Join-Path $src 'gp_dxvk_d3d11.dll') (Join-Path $Game 'd3d11.dll') -Force
    Copy-Item (Join-Path $src 'dxgi.dll') (Join-Path $Game 'dxgi.dll') -Force
    Copy-Item (Join-Path $src 'dxvk.conf') (Join-Path $Game 'dxvk.conf') -Force
    $dxvkConf = Join-Path $Game 'dxvk.conf'
    $confTxt = (Get-Content $dxvkConf -Raw) -replace 'dxvk\.numCompilerThreads\s*=\s*\d+', "dxvk.numCompilerThreads = $compThreads"
    Set-Content -Path $dxvkConf -Value $confTxt -NoNewline -Encoding Ascii
    Write-Host "[OK] 已部署纯净 DXVK 3.1.1 (Vulkan) — 零代理额外开销、100% 保留原版/模组画面" -ForegroundColor Green
} elseif ($Graphics -ne 'off') {
    Copy-Item (Join-Path $src 'd3d11.dll') (Join-Path $Game 'd3d11.dll') -Force
    Copy-Item (Join-Path $src 'gp_dxvk_d3d11.dll') (Join-Path $Game 'gp_dxvk_d3d11.dll') -Force
    Copy-Item (Join-Path $src 'dxgi.dll') (Join-Path $Game 'dxgi.dll') -Force
    Copy-Item (Join-Path $src 'dxvk.conf') (Join-Path $Game 'dxvk.conf') -Force
    Set-Content -Path (Join-Path $Game 'GP_backend.txt') -Value $Backend -Encoding Ascii
    $dxvkConf = Join-Path $Game 'dxvk.conf'
    $confTxt = (Get-Content $dxvkConf -Raw) -replace 'dxvk\.numCompilerThreads\s*=\s*\d+', "dxvk.numCompilerThreads = $compThreads"
    Set-Content -Path $dxvkConf -Value $confTxt -NoNewline -Encoding Ascii
    $gDir = if ($Graphics -eq 'agx') { 'graphics_agx' } else { 'graphics_legacy' }
    Get-ChildItem (Join-Path $src $gDir) -File -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $Game $_.Name) -Force
    }
    Write-Host "[OK] 已部署 Universal Proxy + DXVK 3.1.1 + 画质包 ($Graphics)" -ForegroundColor Green
} else {
    Write-Host "[OK] Backend=native 且 Graphics=off：不部署任何 DLL，仅应用硬件自适应性能配置" -ForegroundColor Green
}

if (Test-Path (Join-Path $src 'Dll\gp_mimalloc_x64.dll')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Game 'Dll') | Out-Null
    Copy-Item (Join-Path $src 'Dll\gp_mimalloc_x64.dll') (Join-Path $Game 'Dll\gp_mimalloc_x64.dll') -Force
}

# 5. Apply Hardware-Adaptive Performance + Quality Config (with full backup)
if ($Tier -ne 'none') {
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

    switch ($Tier) {
        'high' {
            $cfgMap  = @{ vsync=0; GPU_MaxFramesAhead=1; multiSampleCount=4; AToC=15; PPAA=2; ppSSAO=6; cloudsQuality=4 }
            $profMap = @{ textureQuality=4; anisoFilter=16; shadowQuality=5; shadowZDistance=100; sceneComplexity=400000; preferredObjectViewDistance=1000; viewDistance=3800; terrainGrid=12.5; pipViewDistance=500 }
        }
        'high_fps' {
            $cfgMap  = @{ vsync=0; GPU_MaxFramesAhead=1; multiSampleCount=4; AToC=15; PPAA=2; ppSSAO=6; cloudsQuality=0 }
            $profMap = @{ textureQuality=4; anisoFilter=16; shadowQuality=5; shadowZDistance=100; sceneComplexity=400000; preferredObjectViewDistance=1000; viewDistance=3800; terrainGrid=25; pipViewDistance=500 }
        }
        'mid' {
            $cfgMap  = @{ vsync=0; GPU_MaxFramesAhead=1; multiSampleCount=2; AToC=15; PPAA=2; ppSSAO=4; cloudsQuality=2 }
            $profMap = @{ textureQuality=4; anisoFilter=16; shadowQuality=4; shadowZDistance=100; sceneComplexity=350000; preferredObjectViewDistance=1000; viewDistance=3000; terrainGrid=12.5; pipViewDistance=500 }
        }
        'igpu' {
            $cfgMap  = @{ vsync=0; GPU_MaxFramesAhead=1; multiSampleCount=1; AToC=0; PPAA=2; ppSSAO=2; cloudsQuality=1 }
            $profMap = @{ textureQuality=3; anisoFilter=16; shadowQuality=3; shadowZDistance=100; sceneComplexity=300000; preferredObjectViewDistance=900; viewDistance=2000; terrainGrid=25; pipViewDistance=500 }
        }
    }

    $docRoot = Join-Path $env:USERPROFILE 'Documents\Arma 3'
    $cfgPath = Join-Path $docRoot 'Arma3.cfg'
    if (Test-Path $cfgPath) {
        $cfgBak = Join-Path $bakDir 'Arma3.cfg'
        if (-not (Test-Path $cfgBak)) { Copy-Item $cfgPath $cfgBak -Force }
        Set-Content -Path $cfgPath -Value (Apply-KV (Get-Content $cfgPath -Raw) $cfgMap) -NoNewline -Encoding UTF8
        Write-Host "[OK] 已优化 Arma3.cfg (tier=$Tier)" -ForegroundColor Green
    }

    $profiles = @()
    if (Test-Path $docRoot) {
        $profiles += Get-ChildItem $docRoot -Filter '*.Arma3Profile' -File | Where-Object { $_.Name -notmatch '\.(vars|3den)\.Arma3Profile$' }
    }
    $otherRoot = Join-Path $env:USERPROFILE 'Documents\Arma 3 - Other Profiles'
    if (Test-Path $otherRoot) {
        $profiles += Get-ChildItem $otherRoot -Filter '*.Arma3Profile' -Recurse -File | Where-Object { $_.Name -notmatch '\.(vars|3den)\.Arma3Profile$' }
    }
    foreach ($pf in $profiles) {
        $pfBak = Join-Path $bakDir ($pf.Name + '.bak')
        if (-not (Test-Path $pfBak)) { Copy-Item $pf.FullName $pfBak -Force }
        Set-Content -Path $pf.FullName -Value (Apply-KV (Get-Content $pf.FullName -Raw) $profMap) -NoNewline -Encoding UTF8
        Write-Host "[OK] 已优化存档配置: $($pf.FullName)" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "安装完成！建议单人/私服（无 BattlEye）使用。" -ForegroundColor Green
Write-Host "一键卸载还原：powershell -ExecutionPolicy Bypass -File uninstall.ps1" -ForegroundColor DarkGray
if (-not $Silent) { pause }
