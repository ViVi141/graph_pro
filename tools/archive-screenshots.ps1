# Move existing screenshots out of Documents\Arma 3\Screenshots so the game can
# write new ones (Arma refuses to save once that folder reaches a 250 MB quota).
# Safe: moves, never deletes. ASCII only.
$ErrorActionPreference = 'Stop'
$src = Join-Path $env:USERPROFILE 'Documents\Arma 3\Screenshots'
$dst = Join-Path $env:USERPROFILE 'Documents\Arma 3\Screenshots_archive'

if (-not (Test-Path $src)) { Write-Host "No screenshots folder: $src" -ForegroundColor Yellow; return }
New-Item -ItemType Directory -Force -Path $dst | Out-Null

$files = Get-ChildItem $src -File
if ($files.Count -eq 0) { Write-Host "Already empty." -ForegroundColor Green; return }

$mb = [math]::Round((($files | Measure-Object Length -Sum).Sum / 1MB), 1)
$files | Move-Item -Destination $dst -Force

Write-Host ("Moved {0} files ({1} MB) -> {2}" -f $files.Count, $mb, $dst) -ForegroundColor Green
Write-Host ("Screenshots folder now: {0} files" -f (Get-ChildItem $src -File).Count)
