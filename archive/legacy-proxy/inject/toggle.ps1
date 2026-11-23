param(
    [switch]$On,
    [switch]$Off,
    [string]$Game = $env:ARMA3_DIR
)
# Toggle the proxy: d3d11.dll <-> d3d11.dll.off
$ErrorActionPreference = 'Stop'

if (-not $Game) { throw 'Set ARMA3_DIR or pass -Game "<path to Arma 3>"' }
if (-not (Test-Path -LiteralPath $Game)) { throw "Game directory not found: $Game" }

$dll = Join-Path $Game 'd3d11.dll'
$offPath = Join-Path $Game 'd3d11.dll.off'

if ($On) {
    # Never let an old parked build overwrite a newer deployed one: that is how a
    # `toggle -Off` / `deploy` / `toggle -On` sequence silently rolls the proxy back.
    if (Test-Path -LiteralPath $offPath) {
        $parked = Get-Item -LiteralPath $offPath
        $live = if (Test-Path -LiteralPath $dll) { Get-Item -LiteralPath $dll } else { $null }
        if ($live -and $live.LastWriteTime -ge $parked.LastWriteTime) {
            Remove-Item -LiteralPath $offPath -Force
            Write-Host 'kept the newer d3d11.dll; ignored the older d3d11.dll.off' -ForegroundColor DarkYellow
        } else {
            Move-Item -LiteralPath $offPath -Destination $dll -Force
        }
    }
    Write-Host 'proxy: ON' -ForegroundColor Green
} elseif ($Off) {
    if (Test-Path -LiteralPath $dll) { Move-Item -LiteralPath $dll -Destination $offPath -Force }
    Write-Host 'proxy: OFF (native rendering)' -ForegroundColor Yellow
} else {
    if (Test-Path -LiteralPath $dll) { Write-Host 'proxy: ON' -ForegroundColor Green } else { Write-Host 'proxy: OFF' -ForegroundColor Yellow }
}

if (Test-Path -LiteralPath (Join-Path $Game 'GP_spec.txt')) {
    Write-Host ('GP_spec: ' + (Get-Content -LiteralPath (Join-Path $Game 'GP_spec.txt')))
}
