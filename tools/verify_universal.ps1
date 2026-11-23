#Requires -Version 5.0
<#
Offline deployment check for GraphPro Universal.

This script only READS files: it never starts, stops, focuses or injects into
Arma 3, and it never edits the game directory. Run the game yourself, then run
this to verify what was actually deployed and what the proxy logged.

  powershell -File tools\verify_universal.ps1
  powershell -File tools\verify_universal.ps1 -Game "<Arma 3>" -Expect agx

Exit code 0 = every check passed, 1 = at least one failed.
#>
param(
    [string]$Game = $env:ARMA3_DIR,
    [ValidateSet('', 'off', 'agx', 'agx_lite', 'ssgi', 'ultra', 'legacy')]
    [string]$Expect = ''
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

function Find-Arma3Dir {
    $reg = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Bohemia Interactive\Arma 3' -ErrorAction SilentlyContinue
    if ($reg -and $reg.main -and (Test-Path (Join-Path $reg.main 'Arma3_x64.exe'))) { return $reg.main }
    $sreg = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam', 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue
    $steam = ($sreg.InstallPath + $sreg.SteamPath) | Where-Object { $_ } | Select-Object -First 1
    if ($steam) {
        $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
        if (Test-Path $vdf) {
            $libs = Select-String -Path $vdf -Pattern '"path"\s+"([^"]+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value -replace '\\\\', '\' }
            foreach ($l in $libs) {
                $cand = Join-Path $l 'steamapps\common\Arma 3'
                if (Test-Path (Join-Path $cand 'Arma3_x64.exe')) { return $cand }
            }
        }
    }
    return ''
}

if (-not $Game) { $Game = Find-Arma3Dir }
if (-not $Game -or -not (Test-Path (Join-Path $Game 'Arma3_x64.exe'))) {
    throw 'Arma 3 not found. Set ARMA3_DIR or pass -Game "<path to Arma 3>".'
}

$checks = New-Object System.Collections.Generic.List[object]
function Add-Check([string]$Name, [string]$Status, [string]$Detail = '') {
    $checks.Add([pscustomobject]@{ Name = $Name; Status = $Status; Detail = $Detail })
}
function Get-Sha([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }

Write-Host "=== GraphPro Universal offline check ===" -ForegroundColor Cyan
Write-Host "  Arma 3 : $Game"
Write-Host "  Repo   : $repo"

if (Get-Process -Name 'arma3', 'arma3_x64', 'arma3server', 'arma3server_x64' -ErrorAction SilentlyContinue) {
    Write-Host '  NOTE: Arma 3 is running; the log below may be from the current session.' -ForegroundColor Yellow
}

# --- 1. deployment identity -------------------------------------------------
$isInstalled = Test-Path (Join-Path $Game 'd3d11.dll')
$hasDxvkChain = Test-Path (Join-Path $Game 'gp_dxvk_d3d11.dll')
$hasRepl = Test-Path (Join-Path $Game 'GP_replace.txt')
$hasSsgi = Test-Path (Join-Path $Game 'GP_ssgi.txt')
$hasRtgi = Test-Path (Join-Path $Game 'GP_rtgi_trace.dxbc')
$hasPbr = Test-Path (Join-Path $Game 'GP_super_pbr.dxbc')

$mode = if (-not $isInstalled) { 'not installed' }
        elseif ($hasRtgi) { 'ultra' }
        elseif ($hasSsgi) { 'ssgi' }
        elseif ($hasPbr) { 'agx' }
        elseif ($hasRepl) { 'agx_lite' }
        elseif (-not $hasDxvkChain) { 'off' }
        else { 'universal proxy only' }

Write-Host "  Mode   : $mode"
Add-Check 'Arma 3 directory found' 'PASS' $Game
Add-Check 'proxy / DXVK deployed' ($(if ($isInstalled) { 'PASS' } else { 'FAIL' })) 'd3d11.dll'

if ($Expect) {
    $expectOk = ($mode -eq $Expect) -or
                ($Expect -eq 'legacy' -and $hasRepl) -or
                ($Expect -eq 'agx' -and ($mode -eq 'agx' -or $mode -eq 'agx_lite' -or $mode -eq 'ssgi' -or $mode -eq 'ultra'))
    Add-Check "mode matches -Expect $Expect" ($(if ($expectOk) { 'PASS' } else { 'FAIL' })) "detected: $mode"
}

# --- 2. binary identity -----------------------------------------------------
$universalDll = Join-Path $repo 'inject\universal\d3d11.dll'
$distDll = Join-Path $repo 'dist\graph_pro_universal\files\d3d11.dll'
$distDxvk = Join-Path $repo 'dist\graph_pro_universal\files\gp_dxvk_d3d11.dll'
$gameDll = Join-Path $Game 'd3d11.dll'

if ($isInstalled) {
    if ($mode -eq 'off' -and (Test-Path $distDxvk)) {
        $same = (Get-Sha $gameDll) -eq (Get-Sha $distDxvk)
        Add-Check 'pure DXVK backend matches dist' ($(if ($same) { 'PASS' } else { 'WARN' })) 'game d3d11.dll vs dist gp_dxvk_d3d11.dll'
    } elseif (Test-Path $universalDll) {
        $same = (Get-Sha $gameDll) -eq (Get-Sha $universalDll)
        Add-Check 'universal proxy matches repo build' ($(if ($same) { 'PASS' } else { 'WARN' })) 'game d3d11.dll vs inject\universal\d3d11.dll'
    } elseif (Test-Path $distDll) {
        $same = (Get-Sha $gameDll) -eq (Get-Sha $distDll)
        Add-Check 'universal proxy matches dist build' ($(if ($same) { 'PASS' } else { 'WARN' })) 'game d3d11.dll vs dist\...\d3d11.dll'
    } else {
        Add-Check 'build artifact available for comparison' 'WARN' 'run inject\universal\build.bat'
    }
}

# --- 2b. release manifest ----------------------------------------------------
# MANIFEST.json is written by tools\make_manifest.py into the dist tree and
# travels with the zip, so "which build is this?" has an answer that does not
# depend on remembering what was compiled last.
$manifestPath = Join-Path $repo 'dist\graph_pro_universal\MANIFEST.json'
if (Test-Path $manifestPath) {
    $man = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $dirty = if ($man.git_dirty) { ' (dirty tree)' } else { '' }
    Write-Host "  Build  : $($man.git_commit_short)$dirty"
    $shaMan = $null
    try { $shaMan = $man.files.'files/d3d11.dll'.sha256 } catch { }
    if ($shaMan -and (Test-Path $universalDll)) {
        $repoSha = Get-Sha $universalDll
        $same2 = $repoSha -eq $shaMan
        Add-Check 'dist manifest matches repo build' ($(if ($same2) { 'PASS' } else { 'FAIL' })) ("manifest {0} vs build {1}" -f $shaMan.Substring(0, 12), $repoSha.Substring(0, 12))
    } elseif ($shaMan) {
        Add-Check 'dist manifest has a build to compare' 'WARN' 'run inject\universal\build.bat'
    }
    $head = ''
    try { $head = (& git -C $repo rev-parse --short HEAD 2>$null) } catch { }
    if ($head -and $man.git_commit_short -and $man.git_commit_short -ne $head) {
        Add-Check 'manifest built from current HEAD' 'WARN' "manifest $($man.git_commit_short), HEAD $head (rebuild dist)"
    } elseif ($head) {
        Add-Check 'manifest built from current HEAD' 'PASS' $head
    }
} else {
    Add-Check 'release manifest present' 'WARN' 'run python tools\make_manifest.py after building dist'
}

# --- 3. proxy log -----------------------------------------------------------
$logPath = Join-Path $Game 'GP_universal.log'
if (-not (Test-Path $logPath)) {
    if ($mode -ne 'off') { Add-Check 'GP_universal.log exists' 'WARN' 'no run data yet; start the game once' }
} else {
    $logText = Get-Content -LiteralPath $logPath -ErrorAction SilentlyContinue
    $backend = @($logText | Select-String -Pattern 'backend loaded:' | Select-Object -Last 1)
    $replaced = @($logText | Select-String -Pattern 'REPLACED PS').Count
    $ssao = @($logText | Select-String -Pattern 'REPLACED SSAOFinal').Count
    $warn = @($logText | Select-String -Pattern 'no replacement matched').Count
    $hooks = @($logText | Select-String -Pattern 'device hooks active' | Select-Object -Last 1)

    if ($backend) { Write-Host "  Backend: $($backend.Line.Trim())" }
    if ($hooks)   { Write-Host "  Hooks  : $($hooks.Line.Trim())" }
    Write-Host ("  Hits   : tonemap/PS={0}  SSAO={1}" -f $replaced, $ssao)

    $dllTime = if ($isInstalled) { (Get-Item $gameDll).LastWriteTime } else { Get-Date }
    $stale = (Get-Item $logPath).LastWriteTime -lt $dllTime
    Add-Check 'log newer than deployed dll' ($(if ($stale) { 'WARN' } else { 'PASS' })) 're-run the game after redeploying'
    Add-Check 'backend line present' ($(if ($backend) { 'PASS' } else { 'FAIL' })) ''
    Add-Check 'replacement fingerprint matched' ($(if ($mode -eq 'off') { 'SKIP' } elseif ($replaced + $ssao -gt 0) { 'PASS' } else { 'FAIL' })) "PS=$replaced SSAO=$ssao"
    Add-Check 'no "game updated" warning' ($(if ($warn -gt 0) { 'FAIL' } else { 'PASS' })) ''
}

# --- 4. latest RPT (read only; the benchmark line is written by GP_YAAB) ----
$rptDir = Join-Path $env:LOCALAPPDATA 'Arma 3'
$rpt = Get-ChildItem $rptDir -Filter 'Arma3_x64_*.rpt' -File -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($rpt) {
    $result = Select-String -LiteralPath $rpt.FullName -Pattern '\[GP_YAAB_RESULT\][^\r\n]+' | Select-Object -Last 1
    if ($result) { Write-Host "  YAAB   : $($result.Matches[0].Value)" -ForegroundColor Green }
    else { Write-Host "  YAAB   : (no GP_YAAB_RESULT in $($rpt.Name))" -ForegroundColor DarkGray }
}

# --- 5. summary -------------------------------------------------------------
Write-Host ''
$failed = @($checks | Where-Object { $_.Status -eq 'FAIL' })
$warned = @($checks | Where-Object { $_.Status -eq 'WARN' })
$checks | Format-Table -AutoSize Name, Status, Detail
Write-Host ("{0} passed, {1} warnings, {2} failed" -f (@($checks | Where-Object { $_.Status -eq 'PASS' }).Count), $warned.Count, $failed.Count)
if ($failed.Count -gt 0) { exit 1 }
exit 0
