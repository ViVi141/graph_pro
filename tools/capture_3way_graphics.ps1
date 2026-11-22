$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$game = 'F:\SteamLibrary\steamapps\common\Arma 3'
$outDir = Join-Path $repo 'extract\ab_graphics'
$profRoot = Join-Path $outDir 'prof'
New-Item -ItemType Directory -Force -Path $outDir, $profRoot | Out-Null
Copy-Item (Join-Path $env:USERPROFILE 'Documents\Arma 3\Arma3.cfg') (Join-Path $profRoot 'Arma3.cfg') -Force

# Deploy GP_Shot2.Altis with briefing = 0 so it skips 2D map straight into 3D scene
$dstMission = Join-Path $game 'Missions\GP_Shot2.Altis'
New-Item -ItemType Directory -Force -Path $dstMission | Out-Null
Copy-Item (Join-Path $repo 'mission\mission.sqm') (Join-Path $dstMission 'mission.sqm') -Force
Copy-Item (Join-Path $repo 'mission\init.sqf') (Join-Path $dstMission 'init.sqf') -Force
Set-Content -Path (Join-Path $dstMission 'description.ext') -Value "briefing = 0;`r`ndebriefing = 0;" -Encoding Ascii

function Clean-Proxy {
    foreach ($f in @('d3d11.dll','gp_dxvk_d3d11.dll','dxgi.dll','dxvk.conf','GP_backend.txt','GP_replace.txt','GP_tonemap.dxbc','GP_ssao.dxbc','GP_amb.txt','GP_expo.txt','GP_spec.txt','GP_universal.log','GP_enable_dump.txt','GP_dump.txt','GP_shot.raw')) {
        $p = Join-Path $game $f
        if (Test-Path $p) { Remove-Item $p -Force }
    }
}

function Run-Shot([string]$mode) {
    Get-Process arma3_x64 -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
    Clean-Proxy

    $dxvk = Join-Path $repo 'tools\dxvk\dxvk-3.1.1\x64'
    Copy-Item (Join-Path $repo 'inject\universal\d3d11.dll') (Join-Path $game 'd3d11.dll') -Force
    Copy-Item (Join-Path $dxvk 'd3d11.dll') (Join-Path $game 'gp_dxvk_d3d11.dll') -Force
    Copy-Item (Join-Path $dxvk 'dxgi.dll') (Join-Path $game 'dxgi.dll') -Force
    Copy-Item (Join-Path $repo 'tools\dxvk\dxvk.conf') (Join-Path $game 'dxvk.conf') -Force
    Set-Content -Path (Join-Path $game 'GP_backend.txt') -Value 'auto' -Encoding Ascii
    Set-Content -Path (Join-Path $game 'GP_enable_dump.txt') -Value '1' -Encoding Ascii

    if ($mode -eq 'legacy_aces') {
        foreach ($f in @('GP_replace.txt','GP_tonemap.dxbc','GP_ssao.dxbc','GP_amb.txt','GP_expo.txt','GP_spec.txt')) {
            Copy-Item (Join-Path $repo "inject\presets\$f") (Join-Path $game $f) -Force
        }
    } elseif ($mode -eq 'new_agx') {
        Copy-Item (Join-Path $repo 'inject\tonemap_agx.dxbc') (Join-Path $game 'GP_tonemap.dxbc') -Force
        Copy-Item (Join-Path $repo 'inject\ssao_natural.dxbc') (Join-Path $game 'GP_ssao.dxbc') -Force
        Set-Content -Path (Join-Path $game 'GP_replace.txt') -Value '5860 42670B06 GP_tonemap.dxbc' -Encoding Ascii
    }

    $beforeRpts = @{}
    Get-ChildItem $profRoot -Filter 'Arma3_x64_*.rpt' -ErrorAction SilentlyContinue | ForEach-Object { $beforeRpts[$_.FullName] = $true }

    Write-Host "[$mode] Launching GP_Shot2.Altis..." -ForegroundColor Cyan
    $p = Start-Process -FilePath (Join-Path $game 'Arma3_x64.exe') -WorkingDirectory $game -ArgumentList @('-skipIntro','-noSplash',"-profiles=$profRoot",'-name=GP_Shot','-enableHT','-hugePages','-noPause',"-init=playMission['','GP_Shot2.Altis']") -PassThru

    $t0 = Get-Date; $rpt = $null
    while (-not $rpt -and ((Get-Date)-$t0).TotalSeconds -lt 45) {
        Start-Sleep -Milliseconds 500
        $cand = Get-ChildItem $profRoot -Filter 'Arma3_x64_*.rpt' -EA SilentlyContinue | Where-Object { -not $beforeRpts.ContainsKey($_.FullName) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($cand) { $rpt = $cand.FullName }
    }

    $dumped = $false
    while (((Get-Date)-$t0).TotalSeconds -lt 90) {
        if ($p.HasExited) { break }
        Start-Sleep -Milliseconds 400
        $txt = Get-Content $rpt -Raw -EA SilentlyContinue
        if ($txt -and $txt -match '\[GP\] atl=') {
            Start-Sleep -Milliseconds 800
            Set-Content -Path (Join-Path $game 'GP_dump.txt') -Value '1' -Encoding Ascii
            $tw = Get-Date
            while (-not (Test-Path (Join-Path $game 'GP_shot.raw')) -and ((Get-Date)-$tw).TotalSeconds -lt 8) {
                Start-Sleep -Milliseconds 200
            }
            $dumped = Test-Path (Join-Path $game 'GP_shot.raw')
            break
        }
    }
    Get-Process arma3* -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2

    if ($dumped) {
        $rawPath = Join-Path $game 'GP_shot.raw'
        $pngPath = Join-Path $outDir "$mode.png"
        python -c "
import struct, numpy as np
from PIL import Image
b = open(r'$rawPath','rb').read()
w, h, fmt = struct.unpack_from('<III', b, 0)
arr = np.frombuffer(b, dtype=np.uint8, offset=12).reshape(h, w, 4)
# DXGI_FORMAT_B8G8R8A8_* = 87/91 -> swap B,R; R8G8B8A8_* = 28/29 -> already RGB
if fmt in (87, 90, 91, 93):
    rgb = arr[:, :, [2, 1, 0]]
else:
    rgb = arr[:, :, :3]
Image.fromarray(rgb, 'RGB').save(r'$pngPath')
print(f'Converted {w}x{h} fmt={fmt} -> ' + r'$pngPath')
"
    } else {
        Write-Host "[$mode] WARN: GP_shot.raw not created!" -ForegroundColor Red
    }
    $log = Join-Path $game 'GP_universal.log'
    if (Test-Path $log) { Copy-Item $log (Join-Path $outDir "${mode}_log.txt") -Force }
}

try {
    Run-Shot 'vanilla'
    Run-Shot 'legacy_aces'
    Run-Shot 'new_agx'
} finally {
    Clean-Proxy
}
