param(
    [string]$Game = $env:ARMA3_DIR,
    [string]$Documents = (Join-Path $env:USERPROFILE 'Documents\Arma 3'),
    [switch]$Force
)
# Apply the graphics-only part of the reference profile.
#
# This deliberately does NOT copy a whole .Arma3Profile file: profile names are
# per-user, and a full profile also carries difficulty/UI/keybind state. We edit
# only the graphics keys in the user's active profile and back it up first.
$ErrorActionPreference = 'Stop'

if (-not $Game) { throw 'Set ARMA3_DIR or pass -Game "<path to Arma 3>"' }
if (-not (Test-Path -LiteralPath $Game)) { throw "Game directory not found: $Game" }
if (-not (Test-Path -LiteralPath $Documents)) { throw "Documents directory not found: $Documents" }

$running = Get-Process arma3_x64 -ErrorAction SilentlyContinue
if ($running -and -not $Force) { throw 'Close Arma 3 first, or pass -Force (the game rewrites config on exit).' }

$profile = Get-ChildItem -LiteralPath $Documents -Filter '*.Arma3Profile' -File |
    Where-Object { $_.Name -notmatch '\.(vars|3den)\.Arma3Profile$' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $profile) { throw "No .Arma3Profile found in $Documents" }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $PSScriptRoot "backups\$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null

Copy-Item -LiteralPath $profile.FullName -Destination (Join-Path $backup $profile.Name) -Force
$cfgPath = Join-Path $Documents 'Arma3.cfg'
if (Test-Path -LiteralPath $cfgPath) { Copy-Item -LiteralPath $cfgPath -Destination (Join-Path $backup 'Arma3.cfg') -Force }

$inv = [System.Globalization.CultureInfo]::InvariantCulture
$keys = [ordered]@{
    anisoFilter                 = 16
    textureQuality              = 4
    shadowQuality               = 5
    sceneComplexity             = 1800000
    shadowZDistance             = 200
    viewDistance                = 3800
    preferredObjectViewDistance = 3000
    pipViewDistance             = 2500
    terrainGrid                 = 3.125
    gamma                       = 1
    ppBrightness                = 1.01
    ppContrast                  = 1.06
    ppSaturation                = 1.08
}

$text = Get-Content -LiteralPath $profile.FullName -Raw
foreach ($k in $keys.Keys) {
    $v = ([double]$keys[$k]).ToString($inv)
    if ($text -match "(?m)^\s*$k\s*=") {
        $text = [regex]::Replace($text, "(?m)^\s*$k\s*=.*$", "$k=$v")
    } else {
        $text = $text.TrimEnd() + "`r`n$k=$v`r`n"
    }
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($profile.FullName, $text, $utf8)

Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'quality\Arma3.cfg') -Destination $cfgPath -Force

Write-Host "Applied graphics profile to: $($profile.Name)" -ForegroundColor Green
Write-Host "Backup: $backup" -ForegroundColor DarkGray
Write-Host "Restart Arma 3 for the .cfg changes to take effect." -ForegroundColor Yellow
