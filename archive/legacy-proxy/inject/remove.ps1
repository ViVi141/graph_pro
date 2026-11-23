param([string]$Game = $env:ARMA3_DIR)
# Remove the proxy and all GP_* runtime files from the game directory.
$ErrorActionPreference = 'Stop'

if (-not $Game) { throw 'Set ARMA3_DIR or pass -Game "<path to Arma 3>"' }
if (-not (Test-Path -LiteralPath $Game)) { throw "Game directory not found: $Game" }

$removed = 0
# Both the active proxy and the parked copy toggle.ps1 leaves behind. If the .off
# file survives, a later `toggle.ps1 -On` silently re-enables injection.
foreach ($name in @('d3d11.dll', 'd3d11.dll.off')) {
    $p = Join-Path $Game $name
    if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force; Write-Host "removed $name" -ForegroundColor Yellow; $removed++ }
}

Get-ChildItem -LiteralPath $Game -Filter 'GP_*' -File -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Force
    $removed++
}

if ($removed -eq 0) {
    Write-Host 'Nothing to remove.' -ForegroundColor DarkGray
} else {
    Write-Host 'Removed proxy and GP_* files; the game is back to native rendering.' -ForegroundColor Yellow
}
