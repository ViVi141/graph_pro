param(
    [Parameter(Mandatory=$true)]
    [string]$Tag,
    [string]$Game = 'F:\SteamLibrary\steamapps\common\Arma 3',
    [string]$ProfileName = 'ViVi141',
    [switch]$UseDXVK,
    [string]$DxvkConf = '',
    [string]$Malloc = '',
    [string]$AffinityHex = '',
    [switch]$ProfileCpu,
    [int]$ProfIntervalMs = 4,
    [switch]$Windowed,
    [switch]$NoVsyncOverride,
    [int]$TimeoutSec = 240
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $repo 'extract\bench_7900x'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$exe = Join-Path $Game 'Arma3_x64.exe'
if (-not (Test-Path $exe)) { throw "Arma3_x64.exe not found at $exe" }

# 1. Deploy GP_YAAB_Auto.Altis to <Game>\Missions\
$missionName = 'GP_YAAB_Auto.Altis'
$srcMission = Join-Path $repo "mission\$missionName"
$dstMission = Join-Path $Game "Missions\$missionName"
New-Item -ItemType Directory -Force -Path $dstMission | Out-Null
Copy-Item "$srcMission\*" $dstMission -Recurse -Force

# 2. Stop any running Arma 3
Get-Process arma3_x64 -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# Clean old profiler triggers/outputs
foreach ($f in @('GP_prof.txt','GP_profdump.txt','GP_profstop.txt','GP_profload.txt','GP_affinity.txt','GP_prof_report.txt','GP_prof.log','d3d11.dll','dxgi.dll','dxvk.conf')) {
    $p = Join-Path $Game $f
    if (Test-Path $p) { Remove-Item $p -Force }
}

# Deploy DXVK if requested
$deployedDxvk = $false
try {
    if ($UseDXVK) {
        $dxvkDir = Join-Path $repo 'tools\dxvk\dxvk-3.1.1\x64'
        Copy-Item (Join-Path $dxvkDir 'd3d11.dll') (Join-Path $Game 'd3d11.dll') -Force
        Copy-Item (Join-Path $dxvkDir 'dxgi.dll') (Join-Path $Game 'dxgi.dll') -Force
        $confSrc = if ($DxvkConf) { $DxvkConf } else { Join-Path $repo 'tools\dxvk\dxvk.conf' }
        if (Test-Path $confSrc) {
            Copy-Item $confSrc (Join-Path $Game 'dxvk.conf') -Force
        }
        $deployedDxvk = $true
        Write-Host "[$Tag] Deployed DXVK 3.1.1 (d3d11.dll + dxgi.dll + dxvk.conf)" -ForegroundColor Cyan
    }

    if ($ProfileCpu) {
        Copy-Item (Join-Path $repo 'inject\counter\gpprof.dll') (Join-Path $Game 'gpprof.dll') -Force
        Copy-Item (Join-Path $repo 'inject\counter\funcs_client.bin') (Join-Path $Game 'funcs_client.bin') -Force
        Set-Content -Path (Join-Path $Game 'GP_prof.txt') -Value "$ProfIntervalMs 90 10" -Encoding Ascii
    }

    # Record existing RPTs so we find the exact new one
    $rptDir = Join-Path $env:LOCALAPPDATA 'Arma 3'
    $beforeRpts = @{}
    Get-ChildItem $rptDir -Filter 'Arma3_x64_*.rpt' -ErrorAction SilentlyContinue | ForEach-Object { $beforeRpts[$_.FullName] = $true }

    # Build launch args (vanilla, no mods, deterministic YAAB)
    $argsList = @(
        '-skipIntro',
        '-noSplash',
        "-name=$ProfileName",
        '-enableHT',
        '-hugePages',
        '-noPause',
        "-init=playMission['','$missionName']"
    )
    if ($Windowed) { $argsList += '-window' }
    if ($Malloc) { $argsList += "-malloc=$Malloc" }

    if ($Malloc -eq 'gp_mimalloc' -or $Malloc -eq 'gp_mimalloc_x64') {
        $srcM = Join-Path $repo 'inject\malloc\gp_mimalloc_x64.dll'
        if (-not (Test-Path $srcM)) { throw "Missing $srcM" }
        Copy-Item $srcM (Join-Path $Game 'Dll\gp_mimalloc_x64.dll') -Force
    }
    if ($Malloc -eq 'gp_turbo' -or $Malloc -eq 'gp_turbo_x64') {
        $srcT = Join-Path $repo 'inject\turbo\gp_turbo_x64.dll'
        if (-not (Test-Path $srcT)) { throw "Missing $srcT" }
        Copy-Item $srcT (Join-Path $Game 'Dll\gp_turbo_x64.dll') -Force
    }

    if ($AffinityHex) {
        Set-Content -Path (Join-Path $Game 'GP_affinity.txt') -Value $AffinityHex -Encoding Ascii
    }

    Write-Host "[$Tag] Launching Arma3_x64.exe $($argsList -join ' ')" -ForegroundColor Green
    $proc = Start-Process -FilePath $exe -WorkingDirectory $Game -ArgumentList $argsList -PassThru

    if ($AffinityHex) {
        Start-Sleep -Seconds 2
        $mask = [Convert]::ToInt64($AffinityHex.Replace('0x',''), 16)
        Get-Process arma3_x64 -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $_.ProcessorAffinity = [IntPtr]$mask
                Write-Host ("[$Tag] Set ProcessorAffinity(pid={0}) = 0x{1:X}" -f $_.Id, $mask) -ForegroundColor Yellow
            } catch {
                Write-Host "[$Tag] External ProcessorAffinity denied (using in-process GP_affinity.txt)" -ForegroundColor DarkYellow
            }
        }
    }

    # Wait for new RPT file
    $rptPath = $null
    $tStart = Get-Date
    while (-not $rptPath -and ((Get-Date) - $tStart).TotalSeconds -lt 45) {
        Start-Sleep -Milliseconds 500
        $cand = Get-ChildItem $rptDir -Filter 'Arma3_x64_*.rpt' -ErrorAction SilentlyContinue |
            Where-Object { -not $beforeRpts.ContainsKey($_.FullName) } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($cand) { $rptPath = $cand.FullName }
    }
    if (-not $rptPath) { throw "No new RPT created within 45s" }
    Write-Host "[$Tag] Tracking RPT: $rptPath" -ForegroundColor DarkGray

    $attached = $false
    $resultLine = $null
    $startLine = $null
    $allocLine = $null

    while (((Get-Date) - $tStart).TotalSeconds -lt $TimeoutSec) {
        if ($proc.HasExited) { break }
        Start-Sleep -Seconds 1
        $text = Get-Content $rptPath -Raw -ErrorAction SilentlyContinue
        if (-not $text) { continue }

        if (-not $allocLine -and $text -match 'Allocator:[^\r\n]+') {
            $allocLine = $Matches[0]
            Write-Host "[$Tag] $allocLine" -ForegroundColor DarkCyan
        }

        if (-not $startLine -and $text -match '\[GP_YAAB_START\][^\r\n]+') {
            $startLine = $Matches[0]
            Write-Host "[$Tag] $startLine" -ForegroundColor Cyan
            if ($ProfileCpu -and -not $attached) {
                # Trigger in-process loader first (works even if game runs elevated), fallback to injector.exe
                Set-Content -Path (Join-Path $Game 'GP_profload.txt') -Value '1' -Encoding Ascii
                Start-Sleep -Seconds 1
                if (Test-Path (Join-Path $Game 'GP_profload.txt')) {
                    $inj = Join-Path $repo 'inject\counter\injector.exe'
                    $dll = Join-Path $Game 'gpprof.dll'
                    $liveProc = Get-Process arma3_x64 -ErrorAction SilentlyContinue | Select-Object -First 1
                    $targetPid = if ($liveProc) { $liveProc.Id } else { $proc.Id }
                    Write-Host "[$Tag] Attaching gpprof.dll via injector pid=$targetPid..." -ForegroundColor Magenta
                    & $inj "$targetPid" $dll
                } else {
                    Write-Host "[$Tag] gpprof.dll loaded in-process via GP_profload.txt!" -ForegroundColor Magenta
                }
                $attached = $true
            }
        }

        if ($text -match '\[GP_YAAB_RESULT\][^\r\n]+') {
            $resultLine = $Matches[0]
            Write-Host "[$Tag] $resultLine" -ForegroundColor Green
            if ($ProfileCpu -and $attached) {
                Set-Content -Path (Join-Path $Game 'GP_profstop.txt') -Value '1' -Encoding Ascii
                Start-Sleep -Seconds 2
            }
            break
        }
    }

    # Clean exit
    if (-not $proc.HasExited) {
        Start-Sleep -Seconds 2
        if (-not $proc.HasExited) { $proc | Stop-Process -Force }
    }
    Start-Sleep -Seconds 2

    # Archive profiler output
    $profDst = $null
    if ($ProfileCpu) {
        $profSrc = Join-Path $Game 'GP_prof_report.txt'
        if (Test-Path $profSrc) {
            $profDst = Join-Path $outDir "${Tag}_prof.txt"
            Copy-Item $profSrc $profDst -Force
            Write-Host "[$Tag] Saved profiler report -> $profDst" -ForegroundColor Magenta
        } else {
            Write-Host "[$Tag] WARN: GP_prof_report.txt not found" -ForegroundColor Yellow
        }
    }

    # Parse result & save JSON
    $rec = [ordered]@{
        tag = $Tag
        timestamp = (Get-Date).ToString('s')
        use_dxvk = [bool]$UseDXVK
        malloc = $Malloc
        affinity = $AffinityHex
        windowed = [bool]$Windowed
        allocator_rpt = $allocLine
        start_line = $startLine
        result_line = $resultLine
        rpt_path = $rptPath
        prof_report = $profDst
    }
    if ($resultLine) {
        foreach ($m in [regex]::Matches($resultLine, '(\w+)=([0-9.]+)')) {
            $rec[$m.Groups[1].Value] = [double]$m.Groups[2].Value
        }
    }
    $jsonPath = Join-Path $outDir "${Tag}.json"
    $rec | ConvertTo-Json -Depth 4 | Set-Content -Path $jsonPath -Encoding UTF8
    Write-Host "[$Tag] Saved result -> $jsonPath" -ForegroundColor Green
}
finally {
    if ($deployedDxvk) {
        foreach ($f in @('d3d11.dll','dxgi.dll','dxvk.conf')) {
            $p = Join-Path $Game $f
            if (Test-Path $p) { Remove-Item $p -Force -ErrorAction SilentlyContinue }
        }
        Write-Host "[$Tag] Cleaned up DXVK DLLs from game dir" -ForegroundColor DarkGray
    }
    foreach ($f in @('GP_prof.txt','GP_profdump.txt','GP_profstop.txt')) {
        $p = Join-Path $Game $f
        if (Test-Path $p) { Remove-Item $p -Force -ErrorAction SilentlyContinue }
    }
}
