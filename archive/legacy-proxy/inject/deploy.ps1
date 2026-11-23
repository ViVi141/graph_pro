param([string]$Game = $env:ARMA3_DIR)
# Deploy the proxy DLL + the shipped default presets.
# The game is never started/stopped/focused by this script.
$ErrorActionPreference = 'Stop'

if (-not $Game) { throw 'Set ARMA3_DIR or pass -Game "<path to Arma 3>"' }
if (-not (Test-Path -LiteralPath $Game)) { throw "Game directory not found: $Game" }

$dll = Join-Path $PSScriptRoot 'proxy\d3d11.dll'
if (-not (Test-Path -LiteralPath $dll)) { throw "Missing $dll; run inject\proxy\build.bat first" }

$src = Join-Path $PSScriptRoot 'proxy\d3d11_proxy.cpp'
if ((Test-Path -LiteralPath $src) -and ((Get-Item -LiteralPath $dll).LastWriteTime -lt (Get-Item -LiteralPath $src).LastWriteTime)) {
    throw 'd3d11.dll is older than d3d11_proxy.cpp; rebuild with inject\proxy\build.bat'
}

# The universal line (inject\universal) writes its own d3d11.dll plus dxgi.dll /
# dxvk.conf; mixing them with the classic proxy loads two backends into one
# process. Refuse before overwriting anything. Only uninstall.ps1 can restore
# the Arma3.cfg / profile keys the universal installer changed.
$universalBackup = Join-Path $Game '_gp_universal_backup'
$universalFiles = @(
    'gp_dxvk_d3d11.dll',
    'dxgi.dll', 'dxvk.conf'
)
$universalPresent = Test-Path -LiteralPath (Join-Path $Game 'gp_dxvk_d3d11.dll')
if (-not $universalPresent -and (Test-Path -LiteralPath $universalBackup)) {
    $universalPresent = @($universalFiles | Where-Object { Test-Path -LiteralPath (Join-Path $Game $_) }).Count -gt 0
}
if ($universalPresent) {
    throw 'Universal line files are still deployed. Run inject\universal\uninstall.ps1 first, then re-run this script.'
}

Copy-Item -LiteralPath $dll -Destination (Join-Path $Game 'd3d11.dll') -Force

# Experimental presets stay in the repo but are never copied: "default off"
# must really be the default.
$skip = @(
    'GP_present_contact.txt', 'GP_present_off.txt', 'GP_present_on.txt',
    'GP_expo_tight.txt', 'GP_expo_adapt.txt',
    'GP_light_auto.txt', 'GP_spec_boost.txt',
    'GP_replace_aces.txt', 'GP_replace_agx_neutral.txt', 'GP_replace_fsr1.txt',
    'GP_amb_stylized.txt'
)

# Files a previous campaign may have left behind. Without this, "default off"
# silently keeps whatever was last enabled.
# Covers the classic line's own probes plus everything the universal line
# (inject\universal) writes, so switching between the two starts clean.
$stale = @(
    'GP_adapt.txt', 'GP_light_bind.txt', 'GP_cb_dump.txt',
    'GP_probe.txt', 'GP_probe_mrt.txt', 'GP_probe_scale.txt',
    'GP_dump.txt', 'GP_drawlog.txt', 'GP_candhooks.txt', 'GP_canddump.txt',
    'GP_upscale_dump.txt', 'GP_upscale_dump_input.txt',
    'GP_capture_now.txt', 'GP_passseq.txt', 'GP_bindseq.txt',
    'GP_shaders.txt', 'GP_upscale.txt', 'GP_shader.log',
    'GP_ssgi.txt', 'GP_rtgi_trace.dxbc', 'GP_rtgi_denoise.dxbc',
    'GP_tonemap_night.dxbc', 'GP_bloom_init.dxbc', 'GP_sssm_high.dxbc',
    'GP_sssm_veryhigh.dxbc', 'GP_super_pbr.dxbc',
    'GP_backend.txt', 'GP_enable_dump.txt', 'GP_universal.log'
)

Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'presets') -File | ForEach-Object {
    if ($skip -contains $_.Name) { return }
    if ($_.Name -like '*.example') { return }
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Game $_.Name) -Force
}

foreach ($name in $stale) {
    $p = Join-Path $Game $name
    if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force; Write-Host "removed stale $name" -ForegroundColor DarkYellow }
}
Get-ChildItem -LiteralPath $Game -Filter 'GP_up_in_*.raw' -File -ErrorAction SilentlyContinue | Remove-Item -Force

Write-Host 'Deployed d3d11.dll + default presets.' -ForegroundColor Green
Write-Host 'Shipped: AgX tonemap, ambient, exposure clamp, SSAO resolve, manual light.' -ForegroundColor Green
Write-Host 'Contact shadows are SHELVED (forced mode 2); GP_present has no effect.' -ForegroundColor Yellow
Write-Host 'Single-player / private-server use only. Do not use with BattlEye.' -ForegroundColor Red
Write-Host ''
Write-Host 'Optional experiments (copy in the game dir):' -ForegroundColor Cyan
Write-Host '  auto light:      GP_light_bind.txt + GP_light_auto.txt -> GP_light.txt'
Write-Host '  adaptive expo:   GP_expo_adapt.txt -> GP_expo.txt'
Write-Host '  specular boost:  GP_spec_boost.txt -> GP_spec.txt'
Write-Host '  CB dump:         GP_cb_dump.txt.example -> GP_cb_dump.txt'
