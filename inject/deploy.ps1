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
$stale = @(
    'GP_adapt.txt', 'GP_light_bind.txt', 'GP_cb_dump.txt',
    'GP_probe.txt', 'GP_probe_mrt.txt', 'GP_probe_scale.txt',
    'GP_dump.txt', 'GP_drawlog.txt', 'GP_candhooks.txt', 'GP_canddump.txt',
    'GP_upscale_dump.txt', 'GP_upscale_dump_input.txt',
    'GP_capture_now.txt', 'GP_passseq.txt', 'GP_bindseq.txt',
    'GP_shaders.txt', 'GP_upscale.txt', 'GP_shader.log'
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
