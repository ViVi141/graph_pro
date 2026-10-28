param(
    [string]$Documents = (Join-Path $env:USERPROFILE 'Documents\Arma 3'),
    [switch]$Force
)
# Restore the most recent backup created by apply-quality.ps1.
$ErrorActionPreference = 'Stop'

$running = Get-Process arma3_x64 -ErrorAction SilentlyContinue
if ($running -and -not $Force) { throw 'Close Arma 3 first, or pass -Force.' }
if (-not (Test-Path -LiteralPath $Documents)) { throw "Documents directory not found: $Documents" }

$root = Join-Path $PSScriptRoot 'backups'
if (-not (Test-Path -LiteralPath $root)) { throw "No backups under $root" }
$latest = Get-ChildItem -LiteralPath $root -Directory | Sort-Object Name -Descending | Select-Object -First 1
if (-not $latest) { throw "No backups under $root" }

Get-ChildItem -LiteralPath $latest.FullName -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Documents $_.Name) -Force
    Write-Host "restored $($_.Name)" -ForegroundColor Yellow
}
Write-Host "Restart Arma 3 for the restored .cfg to take effect." -ForegroundColor Green
