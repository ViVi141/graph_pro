param(
    [Parameter(Mandatory)][int]$Groups,
    [ValidateSet('none', 'move1', 'cycle2', 'cycle4')]
    [string]$WpMode = 'cycle2',
    [int]$PerGroup = 4,
    [int]$AttachDelaySec = 18,
    [int]$SampleSec = 55
)
# One cell of the AI×waypoint cost grid. Metric = gpsample exe_fn / exe%.
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$game = $env:ARMA3_DIR
if (-not $game) { throw 'Set ARMA3_DIR to the Arma 3 install directory.' }
$serverExe = Join-Path $game 'arma3server_x64.exe'
$counter = Join-Path $repo 'inject\counter'
$missionSrc = Join-Path $repo 'mission\GP_ServerTest.Altis'
$missionDst = Join-Path $game 'MPMissions\GP_ServerTest.Altis'
$prof = Join-Path $env:LOCALAPPDATA 'GP_arma_server'
$cfg = Join-Path $PSScriptRoot 'server.cfg'
$basic = Join-Path $PSScriptRoot 'basic.cfg'
$outDir = Join-Path $repo 'extract\cpu_samples'
New-Item -ItemType Directory -Force -Path $prof, $missionDst, $outDir | Out-Null
Remove-Item (Join-Path $game 'd3d11.dll') -Force -EA SilentlyContinue

$wpBlock = switch ($WpMode) {
    'none' {
@'
	_grp setBehaviour "SAFE";
	{ _x disableAI "PATH"; _x disableAI "MOVE"; } forEach units _grp;
'@
    }
    'move1' {
@'
	private _wp = _grp addWaypoint [
		[(_pos select 0) + (sin (_ang + 90)) * 120, (_pos select 1) + (cos (_ang + 90)) * 120, 0],
		0
	];
	_wp setWaypointType "MOVE";
	_wp setWaypointSpeed "LIMITED";
	_wp setWaypointBehaviour "AWARE";
'@
    }
    'cycle2' {
@'
	private _wp = _grp addWaypoint [
		[(_pos select 0) + (sin (_ang + 90)) * 120, (_pos select 1) + (cos (_ang + 90)) * 120, 0],
		0
	];
	_wp setWaypointType "MOVE";
	_wp setWaypointSpeed "LIMITED";
	_wp setWaypointBehaviour "AWARE";
	private _wp2 = _grp addWaypoint [_pos, 0];
	_wp2 setWaypointType "CYCLE";
'@
    }
    'cycle4' {
@'
	private _r = 100;
	{
		private _a = _ang + _x;
		private _wpos = [
			(_pos select 0) + (sin _a) * _r,
			(_pos select 1) + (cos _a) * _r,
			0
		];
		private _wp = _grp addWaypoint [_wpos, 0];
		_wp setWaypointType "MOVE";
		_wp setWaypointSpeed "LIMITED";
		_wp setWaypointBehaviour "AWARE";
	} forEach [0, 90, 180, 270];
	private _wpc = _grp addWaypoint [_pos, 0];
	_wpc setWaypointType "CYCLE";
'@
    }
}

$wpPerGroup = switch ($WpMode) {
    'none' { 0 }
    'move1' { 1 }
    'cycle2' { 2 }
    'cycle4' { 5 }  # 4 MOVE + 1 CYCLE
}

$init = @"
diag_log format ["[GP] sweep groups=$Groups wp=$WpMode per=$PerGroup"];
enableSaving [false, false];
setDate [2035, 7, 12, 12, 0];
0 setOvercast 0.25; 0 setFog 0; 0 setRain 0;
private _center = [15360, 15360, 0];
private _nGroups = $Groups;
private _perGroup = $PerGroup;
private _radius = 800;
private _types = ["B_Soldier_F", "B_Soldier_AR_F", "B_Soldier_LAT_F", "O_Soldier_F", "O_Soldier_AR_F"];
private _sides = [west, west, west, east, east];
if (_nGroups > 0) then {
	for "_g" from 0 to (_nGroups - 1) do {
		private _ang = (_g / _nGroups) * 360;
		private _r = 200 + (_g % 6) * (_radius / 6);
		private _pos = [
			(_center select 0) + (sin _ang) * _r,
			(_center select 1) + (cos _ang) * _r,
			0
		];
		private _side = _sides select (_g % (count _sides));
		private _grp = createGroup [_side, true];
		for "_u" from 0 to (_perGroup - 1) do {
			private _cls = _types select ((_g + _u) % (count _types));
			private _unit = _grp createUnit [_cls, _pos, [], 8, "FORM"];
			_unit setSkill 0.5;
			_unit allowFleeing 0;
			_unit allowDamage false;
		};
$wpBlock
	};
};
diag_log format ["[GP] spawn done units=%1 groups=%2", count allUnits, _nGroups];
[] spawn {
	for "_i" from 1 to 30 do {
		uiSleep 5;
		diag_log format ["[GP] tick=%1 units=%2 fps=%3", _i, count allUnits, diag_fps];
	};
};
"@

Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

# Only rewrite initServer (description.ext stays locked if DS still shutting down).
if (-not (Test-Path $missionDst)) {
    New-Item -ItemType Directory -Force -Path $missionDst | Out-Null
    Copy-Item (Join-Path $missionSrc '*') $missionDst -Force
} else {
    Copy-Item (Join-Path $missionSrc 'mission.sqm') (Join-Path $missionDst 'mission.sqm') -Force -EA SilentlyContinue
    Copy-Item (Join-Path $missionSrc 'description.ext') (Join-Path $missionDst 'description.ext') -Force -EA SilentlyContinue
}
Set-Content -Path (Join-Path $missionDst 'initServer.sqf') -Value $init -Encoding UTF8

Copy-Item (Join-Path $counter 'funcs_server.bin') (Join-Path $counter 'funcs.bin') -Force
Set-Content (Join-Path $counter 'GP_sample.txt') -Value '50 30 1' -Encoding Ascii -NoNewline
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $counter 'deploy_sample.ps1') -Game $game | Out-Null
Start-Sleep -Seconds 1

$srvArgs = @(
    '-port=2302', "-config=$cfg", "-cfg=$basic", "-profiles=$prof",
    '-world=empty', '-autoInit', '-name=GPTest', '-nosound'
)
$p = Start-Process -FilePath $serverExe -WorkingDirectory $game -ArgumentList $srvArgs -PassThru
Write-Host "sweep g=$Groups wp=$WpMode pid=$($p.Id)" -ForegroundColor Cyan
Start-Sleep -Seconds $AttachDelaySec
if (-not (Get-Process -Id $p.Id -EA SilentlyContinue)) { throw 'server died early' }

# Units from RPT
$rpt = Get-ChildItem $prof -Filter 'arma3server*.rpt' |
    Where-Object { $_.LastWriteTime -gt $p.StartTime.AddSeconds(-5) } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
$units = 0
if ($rpt) {
    $m = Select-String -Path $rpt.FullName -Pattern 'spawn done units=(\d+)' | Select-Object -Last 1
    if ($m) { $units = [int]$m.Matches[0].Groups[1].Value }
}

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $counter 'attach_sample.ps1') `
    -Game $game -Process 'arma3server_x64.exe' | Out-Null
Start-Sleep -Seconds $SampleSec
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $counter 'dump_sample.ps1') -Game $game | Out-Null

$mods = Get-Content (Join-Path $game 'GP_sample_modules.txt') -Raw
$total = if ($mods -match 'total (\d+)') { [int]$Matches[1] } else { 0 }
$exeFn = if ($mods -match 'exe_fn (\d+)') { [int]$Matches[1] } else { 0 }
$exePct = 0.0
if ($mods -match '([\d.]+)\s+arma3server_x64\.exe') { $exePct = [double]$Matches[1] }

$wpTotal = $Groups * $wpPerGroup
$result = [ordered]@{
    groups       = $Groups
    per_group    = $PerGroup
    units        = $units
    wp_mode      = $WpMode
    wp_per_group = $wpPerGroup
    wp_total     = $wpTotal
    total_hits   = $total
    exe_fn       = $exeFn
    exe_pct      = $exePct
    sample_sec   = $SampleSec
    interval_ms  = 50
}
$tag = "g${Groups}_$WpMode"
$result | ConvertTo-Json | Set-Content (Join-Path $outDir "sweep_$tag.json") -Encoding UTF8
$result | Format-List
Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
return [pscustomobject]$result
