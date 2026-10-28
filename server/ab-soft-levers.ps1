param(
    [ValidateSet('skill_low', 'skill_high', 'wp_none', 'wp_cycle', 'physx_off', 'physx_on')]
    [string]$Variant,
    [int]$AttachDelaySec = 20,
    [int]$SampleSec = 70
)
# Headless soft-lever A/B via gpsample exe_fn (NOT diag_fps).
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

$skill = 0.5
$nGroups = 48
$doWp = $true
$nVehicles = 0
switch ($Variant) {
    'skill_low'  { $skill = 0.1 }
    'skill_high' { $skill = 1.0 }
    'wp_none'    { $doWp = $false }
    'wp_cycle'   { $doWp = $true }
    'physx_off'  { $nVehicles = 0; $nGroups = 24 }
    'physx_on'   { $nVehicles = 24; $nGroups = 24 }
}

$wpBlock = if ($doWp) {
@'
	private _wp = _grp addWaypoint [
		[
			(_pos select 0) + (sin (_ang + 90)) * 120,
			(_pos select 1) + (cos (_ang + 90)) * 120,
			0
		],
		0
	];
	_wp setWaypointType "MOVE";
	_wp setWaypointSpeed "LIMITED";
	_wp setWaypointBehaviour "AWARE";
	private _wp2 = _grp addWaypoint [_pos, 0];
	_wp2 setWaypointType "CYCLE";
'@
} else {
@'
	_grp setBehaviour "SAFE";
	{ _x disableAI "PATH"; _x disableAI "MOVE"; } forEach units _grp;
'@
}

$vehBlock = if ($nVehicles -gt 0) {
	# Single-quoted here-string: no PS expansion / quote doubling.
@'
private _vehTypes = ["B_MRAP_01_F", "O_MRAP_02_F", "B_LSV_01_unarmed_F", "B_Truck_01_transport_F"];
private _nVeh = __NVEH__;
for "_v" from 0 to (_nVeh - 1) do {
	private _ang = (_v / _nVeh) * 360;
	private _pos = [
		(_center select 0) + (sin _ang) * 400,
		(_center select 1) + (cos _ang) * 400,
		0
	];
	private _cls = _vehTypes select (_v % (count _vehTypes));
	private _veh = createVehicle [_cls, _pos, [], 0, "NONE"];
	_veh setDir _ang;
	createVehicleCrew _veh;
	_veh allowDamage false;
	private _dest = [
		(_pos select 0) + (sin (_ang + 40)) * 200,
		(_pos select 1) + (cos (_ang + 40)) * 200,
		0
	];
	(group driver _veh) addWaypoint [_dest, 0];
};
diag_log format ["[GP] vehicles=%1", _nVeh];
'@ -replace '__NVEH__', "$nVehicles"
} else {
	'diag_log "[GP] vehicles=0";'
}

$init = @"
diag_log "[GP] initServer begin variant=$Variant";
enableSaving [false, false];
setDate [2035, 7, 12, 12, 0];
0 setOvercast 0.25;
0 setFog 0;
0 setRain 0;
private _center = [15360, 15360, 0];
private _nGroups = $nGroups;
private _perGroup = 4;
private _radius = 800;
private _skill = $skill;
diag_log format ["[GP] spawning groups=%1 skill=%2 wp=$doWp veh=$nVehicles", _nGroups, _skill];
private _types = ["B_Soldier_F", "B_Soldier_AR_F", "B_Soldier_LAT_F", "O_Soldier_F", "O_Soldier_AR_F"];
private _sides = [west, west, west, east, east];
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
		_unit setSkill _skill;
		_unit allowFleeing 0;
		_unit allowDamage false;
	};
$wpBlock
};
$vehBlock
diag_log format ["[GP] spawn done units=%1 fps=%2", count allUnits, diag_fps];
[] spawn {
	for "_i" from 1 to 40 do {
		uiSleep 5;
		diag_log format ["[GP] tick=%1 units=%2 fps=%3", _i, count allUnits, diag_fps];
	};
};
"@

Copy-Item (Join-Path $missionSrc '*') $missionDst -Force
Set-Content -Path (Join-Path $missionDst 'initServer.sqf') -Value $init -Encoding UTF8

Copy-Item (Join-Path $counter 'funcs_server.bin') (Join-Path $counter 'funcs.bin') -Force
Set-Content (Join-Path $counter 'GP_sample.txt') -Value '50 30 1' -Encoding Ascii -NoNewline
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $counter 'deploy_sample.ps1') -Game $game | Out-Null

Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

$srvArgs = @(
    '-port=2302', "-config=$cfg", "-cfg=$basic", "-profiles=$prof",
    '-world=empty', '-autoInit', '-name=GPTest', '-nosound'
)
$p = Start-Process -FilePath $serverExe -WorkingDirectory $game -ArgumentList $srvArgs -PassThru
Write-Host "variant=$Variant pid=$($p.Id) skill=$skill wp=$doWp veh=$nVehicles groups=$nGroups" -ForegroundColor Cyan
Start-Sleep -Seconds $AttachDelaySec
if (-not (Get-Process -Id $p.Id -EA SilentlyContinue)) { throw 'server died early' }

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $counter 'attach_sample.ps1') `
    -Game $game -Process 'arma3server_x64.exe' | Out-Null
Start-Sleep -Seconds $SampleSec
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $counter 'dump_sample.ps1') -Game $game | Out-Null

$modsPath = Join-Path $game 'GP_sample_modules.txt'
$mods = Get-Content $modsPath -Raw
$total = if ($mods -match 'total (\d+)') { [int]$Matches[1] } else { 0 }
$exeFn = if ($mods -match 'exe_fn (\d+)') { [int]$Matches[1] } else { 0 }
$exePct = 0.0
if ($mods -match '([\d.]+)\s+arma3server_x64\.exe') { $exePct = [double]$Matches[1] }
$physxPct = 0.0
if ($mods -match '([\d.]+)\s+PhysX') { $physxPct = [double]$Matches[1] }

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
Copy-Item $modsPath (Join-Path $outDir "modules_${Variant}_$stamp.txt") -Force
Copy-Item (Join-Path $game 'GP_sample_top.txt') (Join-Path $outDir "top_${Variant}_$stamp.txt") -Force -EA SilentlyContinue

$result = [pscustomobject]@{
    Variant = $Variant
    Skill = $skill
    Waypoints = $doWp
    Vehicles = $nVehicles
    Groups = $nGroups
    Total = $total
    ExeFn = $exeFn
    ExePct = $exePct
    PhysXPct = $physxPct
}
$result | Format-List
$result | ConvertTo-Json | Set-Content (Join-Path $outDir "ab_$Variant.json") -Encoding UTF8

Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
return $result
