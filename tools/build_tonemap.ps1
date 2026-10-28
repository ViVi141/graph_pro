param(
    [string]$Fxc = ''
)
# Compile the tonemap / SSAO replacement payloads into presets\.
#
# Arma's runtime tonemap pass is matched on the ORIGINAL shader's (size, crc),
# not on our payload, so payload size may change freely between builds.
# presets\GP_replace.txt points at GP_tonemap_agx.dxbc by filename.
#
# Compiler flags are part of the contract, not a preference. All four shipped
# payloads were built as ps_4_0 WITHOUT /O3; that reproduces the shipped bytes
# exactly (GP_ssao.dxbc -> sha256 5A2370A56BA8, GP_tonemap.dxbc -> 8BD7FDE4571B).
# Building SSAO as ps_5_0 silently changes the sample instruction
# (sample_indexable, r0.x only) and therefore the AO output, so do not
# "modernise" the target profile casually.
$ErrorActionPreference = 'Stop'

if (-not $Fxc) {
    # Pick the newest installed Windows SDK fxc instead of pinning a version.
    $roots = @(
        'C:\Program Files (x86)\Windows Kits\10\bin',
        'C:\Program Files\Windows Kits\10\bin'
    ) | Where-Object { Test-Path $_ }
    $cand = foreach ($r in $roots) {
        Get-ChildItem $r -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $p = Join-Path $_.FullName 'x64\fxc.exe'
            if (Test-Path $p) { [pscustomobject]@{ Ver = [version]$_.Name; Path = $p } }
        }
    }
    $Fxc = ($cand | Sort-Object Ver -Descending | Select-Object -First 1).Path
}
if (-not $Fxc -or -not (Test-Path $Fxc)) { throw "fxc.exe not found; pass -Fxc <path> or install the Windows SDK" }
Write-Host "fxc: $Fxc" -ForegroundColor DarkGray

$inject = Split-Path $PSScriptRoot -Parent | Join-Path -ChildPath 'inject'
$presets = Join-Path $inject 'presets'

$jobs = @(
    @{ Src = 'tonemap_agx.hlsl';         Out = 'GP_tonemap_agx.dxbc';         T = 'ps_4_0'; E = 'main'; O3 = $false },
    @{ Src = 'tonemap_agx_neutral.hlsl'; Out = 'GP_tonemap_agx_neutral.dxbc'; T = 'ps_4_0'; E = 'main'; O3 = $false },
    @{ Src = 'tonemap_aces.hlsl';        Out = 'GP_tonemap.dxbc';              T = 'ps_4_0'; E = 'main'; O3 = $false },
    @{ Src = 'ssao_final.hlsl';          Out = 'GP_ssao.dxbc';                 T = 'ps_4_0'; E = 'main'; O3 = $false },
    @{ Src = 'fsr1_easu.hlsl';           Out = 'GP_fsr1.dxbc';                 T = 'ps_4_0'; E = 'main'; O3 = $false }
)

foreach ($j in $jobs) {
    $src = Join-Path $inject $j.Src
    if (-not (Test-Path $src)) { Write-Host ("skip  {0} (no source)" -f $j.Src) -ForegroundColor Yellow; continue }
    $out = Join-Path $presets $j.Out
    $fxcArgs = @('/nologo', '/T', $j.T, '/E', $j.E)
    if ($j.O3) { $fxcArgs += '/O3' }
    $fxcArgs += @('/Fo', $out, $src)
    & $Fxc @fxcArgs | Out-Host
    if ($LASTEXITCODE -ne 0) { throw ("fxc failed: {0} -> {1}" -f $j.Src, $j.Out) }
    $len = (Get-Item $out).Length
    $sha = (Get-FileHash $out -Algorithm SHA256).Hash.Substring(0, 12)
    Write-Host ("built {0,-28} {1,6} B  {2}  [{3}]" -f $j.Out, $len, $sha, $j.T) -ForegroundColor Green
}

# Sanity: the active replacement table must point at a payload that exists.
$rep = Join-Path $presets 'GP_replace.txt'
if (Test-Path $rep) {
    $line = (Get-Content $rep -TotalCount 1)
    if ($line -match '^\s*(\d+)\s+([0-9A-Fa-f]+)\s+(\S+)') {
        $target = Join-Path $presets $Matches[3]
        if (Test-Path $target) {
            Write-Host ("GP_replace -> {0} OK" -f $Matches[3]) -ForegroundColor Green
        } else {
            Write-Warning ("GP_replace points at missing payload: " + $Matches[3])
        }
    }
}
