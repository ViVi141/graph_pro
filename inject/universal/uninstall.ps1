#Requires -Version 5.0
param(
    [string]$Game = '',
    [switch]$Silent
)
$ErrorActionPreference = 'Stop'

if (Get-Process arma3*, arma3_x64, arma3server* -ErrorAction SilentlyContinue) {
    Write-Host "请先完全退出 Arma 3 再卸载。" -ForegroundColor Yellow
    exit 1
}

if (-not $Game) {
    $reg = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Bohemia Interactive\Arma 3' -ErrorAction SilentlyContinue
    if ($reg -and $reg.main) { $Game = $reg.main }
}
if (-not $Game -or -not (Test-Path (Join-Path $Game 'Arma3_x64.exe'))) {
    if ($Silent) { throw "Arma 3 not found. Pass -Game <path>" }
    $Game = Read-Host '请输入 Arma 3 根目录（包含 Arma3_x64.exe）'
}

$removeList = @(
    'd3d11.dll','gp_dxvk_d3d11.dll','dxgi.dll','dxvk.conf',
    'GP_backend.txt','GP_replace.txt','GP_tonemap.dxbc','GP_tonemap_night.dxbc',
    'GP_bloom_init.dxbc','GP_sssm_veryhigh.dxbc','GP_sssm_high.dxbc','GP_ssao.dxbc','GP_super_pbr.dxbc',
    'GP_ssgi.txt','GP_rtgi_trace.dxbc','GP_rtgi_denoise.dxbc',
    'GP_amb.txt','GP_amb_stylized.txt','GP_expo.txt','GP_spec.txt','GP_universal.log',
    'GP_enable_dump.txt','GP_dump.txt','GP_dump_ps.txt','GP_dump_bytes.txt','GP_shot.raw',
    # classic proxy line leftovers (inject\deploy.ps1)
    'GP_tonemap_agx.dxbc','GP_tonemap_agx_neutral.dxbc','GP_fsr1.dxbc',
    'GP_light.txt','GP_light_auto.txt','GP_light_bind.txt',
    'GP_present.txt','GP_present_on.txt','GP_present_off.txt','GP_present_contact.txt',
    'GP_expo_adapt.txt','GP_expo_tight.txt','GP_spec_boost.txt',
    'GP_replace_aces.txt','GP_replace_agx_neutral.txt','GP_replace_fsr1.txt',
    'GP_adapt.txt','GP_cb_dump.txt',
    'GP_probe.txt','GP_probe_mrt.txt','GP_probe_scale.txt',
    'GP_upscale.txt','GP_upscale_dump.txt','GP_upscale_dump_input.txt',
    'GP_passseq.txt','GP_shaders.txt','GP_shader.log','GP_drawlog.txt',
    'GP_candhooks.txt','GP_canddump.txt'
)
foreach ($f in $removeList) {
    $p = Join-Path $Game $f
    if (Test-Path $p) { Remove-Item $p -Force; Write-Host "  - removed $f" -ForegroundColor DarkGray }
}
$psdump = Join-Path $Game 'GP_psdump'
if (Test-Path -LiteralPath $psdump) { Remove-Item -LiteralPath $psdump -Recurse -Force; Write-Host "  - removed GP_psdump\" -ForegroundColor DarkGray }
$mDll = Join-Path $Game 'Dll\gp_mimalloc_x64.dll'
if (Test-Path $mDll) { Remove-Item $mDll -Force }

$bakDir = Join-Path $Game '_gp_universal_backup'
if (Test-Path $bakDir) {
    foreach ($f in @('d3d11.dll','dxgi.dll','dxvk.conf')) {
        $b = Join-Path $bakDir $f
        if (Test-Path $b) { Copy-Item $b (Join-Path $Game $f) -Force; Write-Host "  + restored $f" -ForegroundColor Green }
    }
    $cfgBak = Join-Path $bakDir 'Arma3.cfg'
    $cfgDst = Join-Path $env:USERPROFILE 'Documents\Arma 3\Arma3.cfg'
    if (Test-Path $cfgBak) { Copy-Item $cfgBak $cfgDst -Force; Write-Host "  + restored Arma3.cfg" -ForegroundColor Green }

    $allProfs = @()
    $docRoot = Join-Path $env:USERPROFILE 'Documents\Arma 3'
    if (Test-Path $docRoot) { $allProfs += Get-ChildItem $docRoot -Filter '*.Arma3Profile' -File }
    $otherRoot = Join-Path $env:USERPROFILE 'Documents\Arma 3 - Other Profiles'
    if (Test-Path $otherRoot) { $allProfs += Get-ChildItem $otherRoot -Filter '*.Arma3Profile' -Recurse -File }
    foreach ($pf in $allProfs) {
        $b = Join-Path $bakDir ($pf.Name + '.bak')
        if (Test-Path $b) { Copy-Item $b $pf.FullName -Force; Write-Host "  + restored $($pf.FullName)" -ForegroundColor Green }
    }
    Remove-Item $bakDir -Recurse -Force
}

Write-Host "已完整卸载 GraphPro Universal 并还原全部原始配置。" -ForegroundColor Green
if (-not $Silent) { pause }
