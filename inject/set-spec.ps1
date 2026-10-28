param(
    [int]$Mode = 0,
    [double]$Boost = 0.15,
    [double]$Power = 0.0,
    [string]$Game = $env:ARMA3_DIR
)
# GP_spec.txt: mode boost [power]
#   mode 0 = off
#   mode 1 = boost existing specular only (skip grass/clouds)
$ErrorActionPreference = 'Stop'
if (-not $Game) { throw 'Set ARMA3_DIR or pass -Game "<path to Arma 3>"' }
if (-not (Test-Path -LiteralPath $Game)) { throw "Game directory not found: $Game" }

"$Mode $Boost $Power" | Set-Content -LiteralPath (Join-Path $Game 'GP_spec.txt') -Encoding ASCII
if ($Mode -le 0) { Write-Host 'specular: off (mode 0)' -ForegroundColor Yellow }
else { Write-Host ("specular: mode=1 boost=$Boost power=$Power") -ForegroundColor Green }
