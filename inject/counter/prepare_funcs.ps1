# Regenerate funcs_client.bin / funcs_server.bin / funcs.bin (client default).
$ErrorActionPreference = 'Stop'
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Py = Get-Command python -ErrorAction SilentlyContinue
if (-not $Py) { Write-Host 'python not in PATH' -ForegroundColor Red; exit 1 }
& python (Join-Path $Root 'tools\gen_funcs_both.py')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'OK: funcs.bin = client table' -ForegroundColor Green
