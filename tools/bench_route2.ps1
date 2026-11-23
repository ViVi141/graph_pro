param(
    [ValidateSet('Deploy', 'Trigger', 'Collect')]
    [string]$Action = 'Deploy',
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [string]$Game = $env:ARMA3_DIR,
    [string]$ProfileName = '',
    [switch]$UseDXVK,
    [string]$DxvkConf = '',
    [string]$Malloc = '',
    [string]$AffinityHex = '',
    [switch]$ProfileCpu,
    [int]$ProfIntervalMs = 4,
    [switch]$Windowed
)
# Route 2 benchmark helper for GP_YAAB_Auto.
# This script only reads and writes files: it never starts, stops, focuses or
# injects into Arma 3. Start the game yourself when Deploy tells you to.
#
#   Deploy  : copy the mission, stage DXVK / malloc / profiler triggers, and
#             write <Tag>.deploy.json plus the exact launch command.
#   Trigger : write GP_profload.txt so the in-process loader (gp_mimalloc /
#             gp_turbo, launched with -malloc=) loads gpprof.dll.
#   Collect : find the RPT produced after Deploy, parse [GP_YAAB_*] lines and
#             write <Tag>.json in the same schema as the 2026-11-22 runs.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $repo 'extract\bench_7900x'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$manifestPath = Join-Path $outDir "$Tag.deploy.json"
$missionName = 'GP_YAAB_Auto.Altis'

if (-not $Game) {
    $reg = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Bohemia Interactive\Arma 3' -ErrorAction SilentlyContinue
    if ($reg -and $reg.main) { $Game = $reg.main }
}
if (-not $Game -or -not (Test-Path (Join-Path $Game 'Arma3_x64.exe'))) {
    throw 'Arma 3 not found. Set ARMA3_DIR or pass -Game "<path to Arma 3>".'
}

function Get-LaunchArgs {
    $a = @('-skipIntro', '-noSplash', '-enableHT', '-hugePages', '-noPause',
           "-init=playMission['','$missionName']")
    if ($ProfileName) { $a += "-name=$ProfileName" }
    if ($Windowed) { $a += '-window' }
    if ($Malloc) { $a += "-malloc=$Malloc" }
    return $a
}

switch ($Action) {
    'Deploy' {
        $srcMission = Join-Path $repo "mission\$missionName"
        if (-not (Test-Path $srcMission)) { throw "Missing mission source: $srcMission" }
        $dstMission = Join-Path $Game "Missions\$missionName"
        New-Item -ItemType Directory -Force -Path $dstMission | Out-Null
        Copy-Item "$srcMission\*" $dstMission -Recurse -Force
        Write-Host "[$Tag] Mission deployed to $dstMission" -ForegroundColor Cyan

        # Remove artifacts a previous campaign left behind (this tool's own
        # outputs only; nothing here belongs to the game).
        foreach ($f in @('GP_prof.txt', 'GP_profdump.txt', 'GP_profstop.txt', 'GP_profload.txt',
                         'GP_affinity.txt', 'GP_prof_report.txt', 'GP_prof.log',
                         'd3d11.dll', 'dxgi.dll', 'dxvk.conf')) {
            $p = Join-Path $Game $f
            if (Test-Path $p) { Remove-Item $p -Force }
        }

        if ($UseDXVK) {
            $dxvkDir = Join-Path $repo 'tools\dxvk\dxvk-3.1.1\x64'
            Copy-Item (Join-Path $dxvkDir 'd3d11.dll') (Join-Path $Game 'd3d11.dll') -Force
            Copy-Item (Join-Path $dxvkDir 'dxgi.dll') (Join-Path $Game 'dxgi.dll') -Force
            $confSrc = if ($DxvkConf) { $DxvkConf } else { Join-Path $repo 'tools\dxvk\dxvk.conf' }
            if (Test-Path $confSrc) { Copy-Item $confSrc (Join-Path $Game 'dxvk.conf') -Force }
            Write-Host "[$Tag] DXVK 3.1.1 staged (d3d11.dll + dxgi.dll + dxvk.conf)" -ForegroundColor Cyan
        }

        if ($ProfileCpu) {
            $profDll = Join-Path $repo 'inject\counter\gpprof.dll'
            $funcs = Join-Path $repo 'inject\counter\funcs_client.bin'
            foreach ($p in @($profDll, $funcs)) {
                if (-not (Test-Path $p)) { throw "Missing $p; run inject\counter\build_prof.bat first" }
            }
            Copy-Item $profDll (Join-Path $Game 'gpprof.dll') -Force
            Copy-Item $funcs (Join-Path $Game 'funcs_client.bin') -Force
            Set-Content -Path (Join-Path $Game 'GP_prof.txt') -Value "$ProfIntervalMs 90 10" -Encoding Ascii
        }

        if ($Malloc -eq 'gp_mimalloc' -or $Malloc -eq 'gp_mimalloc_x64') {
            $srcM = Join-Path $repo 'inject\malloc\gp_mimalloc_x64.dll'
            if (-not (Test-Path $srcM)) { throw "Missing $srcM" }
            New-Item -ItemType Directory -Force -Path (Join-Path $Game 'Dll') | Out-Null
            Copy-Item $srcM (Join-Path $Game 'Dll\gp_mimalloc_x64.dll') -Force
        }
        if ($Malloc -eq 'gp_turbo' -or $Malloc -eq 'gp_turbo_x64') {
            $srcT = Join-Path $repo 'inject\turbo\gp_turbo_x64.dll'
            if (-not (Test-Path $srcT)) { throw "Missing $srcT" }
            New-Item -ItemType Directory -Force -Path (Join-Path $Game 'Dll') | Out-Null
            Copy-Item $srcT (Join-Path $Game 'Dll\gp_turbo_x64.dll') -Force
        }

        if ($AffinityHex) {
            Set-Content -Path (Join-Path $Game 'GP_affinity.txt') -Value $AffinityHex -Encoding Ascii
        }

        $manifest = [ordered]@{
            tag            = $Tag
            deployed_at    = (Get-Date).ToString('s')
            game           = $Game
            use_dxvk       = [bool]$UseDXVK
            malloc         = $Malloc
            affinity       = $AffinityHex
            windowed       = [bool]$Windowed
            profile_cpu    = [bool]$ProfileCpu
            prof_interval  = $ProfIntervalMs
            launch_args    = @(Get-LaunchArgs)
        }
        $manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestPath -Encoding UTF8

        $exe = Join-Path $Game 'Arma3_x64.exe'
        Write-Host ''
        Write-Host "[$Tag] Now start Arma 3 YOURSELF (the script never does):" -ForegroundColor Green
        Write-Host "  `"$exe`" $((Get-LaunchArgs) -join ' ')" -ForegroundColor White
        if ($ProfileCpu) {
            Write-Host "[$Tag] After [GP_YAAB_START] appears in the RPT, run: .\tools\bench_route2.ps1 -Action Trigger -Tag $Tag -ProfileCpu" -ForegroundColor Yellow
        }
        Write-Host "[$Tag] After the run, exit the game and run: .\tools\bench_route2.ps1 -Action Collect -Tag $Tag" -ForegroundColor Yellow
    }

    'Trigger' {
        if (-not $ProfileCpu) { Write-Host "[$Tag] Nothing to trigger (no -ProfileCpu)." -ForegroundColor DarkGray; exit 0 }
        if ($Malloc -notmatch 'gp_mimalloc|gp_turbo') {
            Write-Host "[$Tag] WARNING: the in-process loader lives in gp_mimalloc / gp_turbo." -ForegroundColor Yellow
            Write-Host "        Launch the game with -Malloc gp_mimalloc (or gp_turbo) for this trigger." -ForegroundColor Yellow
        }
        Set-Content -Path (Join-Path $Game 'GP_profload.txt') -Value '1' -Encoding Ascii
        Start-Sleep -Seconds 3
        if (Test-Path (Join-Path $Game 'GP_profload.txt')) {
            Write-Host "[$Tag] GP_profload.txt was not consumed. No in-process loader is running;" -ForegroundColor Red
            Write-Host "        relaunch with -Malloc gp_mimalloc (or gp_turbo) and trigger again." -ForegroundColor Red
            exit 1
        }
        Write-Host "[$Tag] gpprof.dll loaded in-process via GP_profload.txt." -ForegroundColor Magenta
    }

    'Collect' {
        if (-not (Test-Path $manifestPath)) { throw "Missing $manifestPath; run -Action Deploy first" }
        $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
        $deployedAt = [datetime]::Parse($manifest.deployed_at)

        $rptDir = Join-Path $env:LOCALAPPDATA 'Arma 3'
        $rpt = Get-ChildItem $rptDir -Filter 'Arma3_x64_*.rpt' -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $deployedAt } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $rpt) { throw "No RPT newer than $($manifest.deployed_at) under $rptDir. Run the benchmark first." }
        $text = Get-Content $rpt.FullName -Raw

        $allocLine = if ($text -match 'Allocator:[^\r\n]+') { $Matches[0] } else { $null }
        $startLine = if ($text -match '\[GP_YAAB_START\][^\r\n]+') { $Matches[0] } else { $null }
        $resultMatches = [regex]::Matches($text, '\[GP_YAAB_RESULT\][^\r\n]+')
        $resultLine = if ($resultMatches.Count) { $resultMatches[$resultMatches.Count - 1].Value } else { $null }
        if (-not $resultLine) { throw "No [GP_YAAB_RESULT] in $($rpt.FullName). Did the run finish?" }

        $profDst = $null
        if ($manifest.profile_cpu) {
            $profSrc = Join-Path $Game 'GP_prof_report.txt'
            if (Test-Path $profSrc) {
                $profDst = Join-Path $outDir "${Tag}_prof.txt"
                Copy-Item $profSrc $profDst -Force
                Write-Host "[$Tag] Saved profiler report -> $profDst" -ForegroundColor Magenta
            } else {
                Write-Host "[$Tag] WARN: GP_prof_report.txt not found" -ForegroundColor Yellow
            }
        }

        $rec = [ordered]@{
            tag           = $Tag
            timestamp     = (Get-Date).ToString('s')
            use_dxvk      = [bool]$manifest.use_dxvk
            malloc        = $manifest.malloc
            affinity      = $manifest.affinity
            windowed      = [bool]$manifest.windowed
            allocator_rpt = $allocLine
            start_line    = $startLine
            result_line   = $resultLine
            rpt_path      = $rpt.FullName
            prof_report   = $profDst
        }
        foreach ($m in [regex]::Matches($resultLine, '(\w+)=([0-9.]+)')) {
            $rec[$m.Groups[1].Value] = [double]$m.Groups[2].Value
        }
        $jsonPath = Join-Path $outDir "$Tag.json"
        $rec | ConvertTo-Json -Depth 4 | Set-Content -Path $jsonPath -Encoding UTF8
        Write-Host "[$Tag] $resultLine" -ForegroundColor Green
        Write-Host "[$Tag] Saved result -> $jsonPath" -ForegroundColor Green
        if ($profDst) {
            Write-Host "[$Tag] Next: python tools\annotate_prof.py `"$profDst`"" -ForegroundColor Cyan
        }
    }
}
