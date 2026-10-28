# Shared paths for the gpcpu lab scripts.
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$game = $env:ARMA3_DIR
if (-not $game) { throw 'Set ARMA3_DIR to the Arma 3 install directory.' }
$work = if ($env:GP_WORK) { $env:GP_WORK } else { Join-Path $repo '_local\gp_re' }
New-Item -ItemType Directory -Force -Path $work | Out-Null
