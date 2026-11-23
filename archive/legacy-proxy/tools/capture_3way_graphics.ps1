#Requires -Version 5.0
<#
Three-step offline capture using the in-repo payloads (no dist needed).

Arma 3 is NEVER started, stopped, focused or injected into by this script.

  1) Deploy   copy the universal proxy + DXVK + one of the three payload sets
  2) run the game yourself (deploy the shot mission first: mission\deploy-shot2.ps1)
  3) Trigger  create GP_dump.txt while the 3D scene is up -> GP_shot.raw
  4) Collect  convert GP_shot.raw to extract\ab_graphics\<mode>.png + archive the log

  powershell -File tools\capture_3way_graphics.ps1 -Action Deploy -Mode vanilla
  powershell -File tools\capture_3way_graphics.ps1 -Action Trigger
  powershell -File tools\capture_3way_graphics.ps1 -Action Collect -Mode new_agx

Modes:
  vanilla      DXVK only (proxy loaded, no shader overrides) - baseline
  legacy_aces  ACES tonemap + SSAO smoothstep + amb/expo/spec presets
  new_agx      AgX tonemap + natural SSAO
#>
param(
    [ValidateSet('Deploy', 'Trigger', 'Collect')]
    [string]$Action = 'Deploy',
    [ValidateSet('vanilla', 'legacy_aces', 'new_agx')]
    [string]$Mode = 'vanilla',
    [string]$Game = $env:ARMA3_DIR
)
$ErrorActionPreference = 'Stop'
# Archived with the classic line (2026-11-23): this script lives in
# archive\legacy-proxy\tools, so the repo root is two levels up; the classic
# payloads (presets, tonemap_agx.dxbc, ssao_natural.dxbc) stay inside the archive.
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$legacy = Split-Path -Parent $PSScriptRoot
$dxvk = Join-Path $repo 'tools\dxvk\dxvk-3.1.1\x64'
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
        'GP_replace.txt', 'GP_tonemap.dxbc', 'GP_ssao.dxbc',
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
        foreach ($f in @((Join-Path $dxvk 'd3d11.dll'), (Join-Path $repo 'inject\universal\d3d11.dll'))) {
            if (-not (Test-Path $f)) { throw "Missing $f (build inject\universal first, or use capture_nextgen_ab.ps1 with dist/)." }
        }
        Clean-GpDeployment $Game
        Copy-Item -LiteralPath (Join-Path $repo 'inject\universal\d3d11.dll') -Destination (Join-Path $Game 'd3d11.dll') -Force
        Copy-Item -LiteralPath (Join-Path $dxvk 'd3d11.dll') -Destination (Join-Path $Game 'gp_dxvk_d3d11.dll') -Force
        Copy-Item -LiteralPath (Join-Path $dxvk 'dxgi.dll') -Destination (Join-Path $Game 'dxgi.dll') -Force
        Copy-Item -LiteralPath (Join-Path $repo 'tools\dxvk\dxvk.conf') -Destination (Join-Path $Game 'dxvk.conf') -Force
        Set-Content -Path (Join-Path $Game 'GP_backend.txt') -Value 'auto' -Encoding Ascii
        Set-Content -Path (Join-Path $Game 'GP_enable_dump.txt') -Value '1' -Encoding Ascii

        if ($Mode -eq 'legacy_aces') {
            foreach ($f in @('GP_tonemap.dxbc', 'GP_ssao.dxbc', 'GP_amb.txt', 'GP_expo.txt', 'GP_spec.txt')) {
                Copy-Item -LiteralPath (Join-Path $legacy "inject\presets\$f") -Destination (Join-Path $Game $f) -Force
            }
            Set-Content -Path (Join-Path $Game 'GP_replace.txt') -Value '5860 42670B06 GP_tonemap.dxbc' -Encoding Ascii
        } elseif ($Mode -eq 'new_agx') {
            Copy-Item -LiteralPath (Join-Path $legacy 'inject\tonemap_agx.dxbc') -Destination (Join-Path $Game 'GP_tonemap.dxbc') -Force
            Copy-Item -LiteralPath (Join-Path $legacy 'inject\ssao_natural.dxbc') -Destination (Join-Path $Game 'GP_ssao.dxbc') -Force
            Set-Content -Path (Join-Path $Game 'GP_replace.txt') -Value '5860 42670B06 GP_tonemap.dxbc' -Encoding Ascii
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
