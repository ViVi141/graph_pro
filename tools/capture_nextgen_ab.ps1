#Requires -Version 5.0
<#
Three-step offline capture for the packaged (dist) graphics packs.

Arma 3 is NEVER started, stopped, focused or injected into by this script.
The user runs the game; this script only copies files and reads the result.

  1) Deploy   copy d3d11.dll + DXVK 3.1.1 + the chosen graphics_* payloads
  2) run the game yourself (deploy the shot mission first: mission\deploy-shot2.ps1)
  3) Trigger  create GP_dump.txt while the 3D scene is up -> GP_shot.raw
  4) Collect  convert GP_shot.raw to extract\ab_graphics\<mode>.png + archive the log

  powershell -File tools\capture_nextgen_ab.ps1 -Action Deploy -Mode agx_v2
  powershell -File tools\capture_nextgen_ab.ps1 -Action Trigger
  powershell -File tools\capture_nextgen_ab.ps1 -Action Collect -Mode agx_v2
#>
param(
    [ValidateSet('Deploy', 'Trigger', 'Collect')]
    [string]$Action = 'Deploy',
    [ValidateSet('agx_lite', 'agx_v2')]
    [string]$Mode = 'agx_v2',
    [string]$Game = $env:ARMA3_DIR
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$src = Join-Path $repo 'dist\graph_pro_universal\files'
$outDir = Join-Path $repo 'extract\ab_graphics'

function Find-Arma3Dir {
    $reg = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Bohemia Interactive\Arma 3' -ErrorAction SilentlyContinue
    if ($reg -and $reg.main -and (Test-Path (Join-Path $reg.main 'Arma3_x64.exe'))) { return $reg.main }
    $sreg = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam', 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue
    $steam = ($sreg.InstallPath + $sreg.SteamPath) | Where-Object { $_ } | Select-Object -First 1
    if ($steam) {
        $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
        if (Test-Path $vdf) {
            $libs = Select-String -Path $vdf -Pattern '"path"\s+"([^"]+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value -replace '\\\\', '\' }
            foreach ($l in $libs) {
                $cand = Join-Path $l 'steamapps\common\Arma 3'
                if (Test-Path (Join-Path $cand 'Arma3_x64.exe')) { return $cand }
            }
        }
    }
    return ''
}

function Clean-GpDeployment([string]$Game) {
    $files = @(
        'd3d11.dll', 'gp_dxvk_d3d11.dll', 'dxgi.dll', 'dxvk.conf', 'GP_backend.txt',
        'GP_replace.txt', 'GP_tonemap.dxbc', 'GP_tonemap_night.dxbc', 'GP_bloom_init.dxbc',
        'GP_sssm_veryhigh.dxbc', 'GP_sssm_high.dxbc', 'GP_ssao.dxbc', 'GP_super_pbr.dxbc',
        'GP_ssgi.txt', 'GP_rtgi_trace.dxbc', 'GP_rtgi_denoise.dxbc',
        'GP_amb.txt', 'GP_expo.txt', 'GP_spec.txt', 'GP_universal.log',
        'GP_enable_dump.txt', 'GP_dump.txt', 'GP_shot.raw'
    )
    foreach ($f in $files) {
        $p = Join-Path $Game $f
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force }
    }
}

if (-not $Game) { $Game = Find-Arma3Dir }
if (-not $Game -or -not (Test-Path (Join-Path $Game 'Arma3_x64.exe'))) {
    throw 'Arma 3 not found. Set ARMA3_DIR or pass -Game "<path to Arma 3>".'
}

switch ($Action) {
    'Deploy' {
        if (-not (Test-Path (Join-Path $src 'd3d11.dll'))) {
            throw "Packaged files not found under $src (build/dist first)."
        }
        Clean-GpDeployment $Game
        foreach ($f in @('d3d11.dll', 'gp_dxvk_d3d11.dll', 'dxgi.dll', 'dxvk.conf')) {
            Copy-Item -LiteralPath (Join-Path $src $f) -Destination (Join-Path $Game $f) -Force
        }
        Set-Content -Path (Join-Path $Game 'GP_backend.txt') -Value 'auto' -Encoding Ascii
        Set-Content -Path (Join-Path $Game 'GP_enable_dump.txt') -Value '1' -Encoding Ascii
        if ($Mode -eq 'agx_v2') {
            Get-ChildItem -LiteralPath (Join-Path $src 'graphics_agx') -File |
                ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Game $_.Name) -Force }
        } else {
            Get-ChildItem -LiteralPath (Join-Path $src 'graphics_agx_lite') -File |
                ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Game $_.Name) -Force }
        }
        Write-Host "[$Mode] deployed to $Game" -ForegroundColor Green
        Write-Host 'Next: deploy the shot mission (mission\deploy-shot2.ps1), start Arma 3 yourself,' -ForegroundColor Cyan
        Write-Host 'get into the 3D scene, then run:  -Action Trigger' -ForegroundColor Cyan
    }

    'Trigger' {
        Set-Content -Path (Join-Path $Game 'GP_dump.txt') -Value '1' -Encoding Ascii
        Write-Host 'GP_dump.txt written; the proxy captures the next Present into GP_shot.raw.' -ForegroundColor Green
    }

    'Collect' {
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
        $rawPath = Join-Path $Game 'GP_shot.raw'
        if (-not (Test-Path $rawPath)) { throw "Missing $rawPath - run -Action Trigger while the game shows the scene." }
        $pngPath = Join-Path $outDir "$Mode.png"
        python -c "
import struct, sys
import numpy as np
from PIL import Image
b = open(sys.argv[1], 'rb').read()
w, h, fmt = struct.unpack_from('<III', b, 0)
arr = np.frombuffer(b, dtype=np.uint8, offset=12).reshape(h, w, 4)
rgb = arr[:, :, [2, 1, 0]] if fmt in (87, 90, 91, 93) else arr[:, :, :3]
Image.fromarray(rgb, 'RGB').save(sys.argv[2])
print(f'Converted {w}x{h} fmt={fmt} -> ' + sys.argv[2])
" $rawPath $pngPath
        if ($LASTEXITCODE -ne 0) { throw 'raw -> PNG conversion failed (pip install -r requirements.txt)' }
        $log = Join-Path $Game 'GP_universal.log'
        if (Test-Path $log) {
            Copy-Item -LiteralPath $log -Destination (Join-Path $outDir "${Mode}_log.txt") -Force
            Get-Content -LiteralPath $log | Where-Object { $_ -match 'REPLACED|backend loaded|device hooks|no replacement matched' }
        }
        Write-Host "Collected $pngPath" -ForegroundColor Green
    }
}
