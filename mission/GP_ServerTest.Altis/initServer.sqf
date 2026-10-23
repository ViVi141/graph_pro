// Headless DS CPU load — no clients, no rendering. Spawns AI patrols so
// World::Simulate / AI / PhysX show up under gpsample on arma3server_x64.
diag_log "[GP] initServer begin";
enableSaving [false, false];

setDate [2035, 7, 12, 12, 0];
0 setOvercast 0.25;
0 setFog 0;
0 setRain 0;

private _center = [15360, 15360, 0];
private _nGroups = 48;
private _perGroup = 4;
private _radius = 800;

diag_log format ["[GP] spawning groups=%1 x %2 around %3", _nGroups, _perGroup, _center];

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
		_unit setSkill 0.5;
		_unit allowFleeing 0;
		_unit allowDamage false; // sustained AI load for sampling
	};
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
	_wp setWaypointBehaviour "SAFE";
	private _wp2 = _grp addWaypoint [_pos, 0];
	_wp2 setWaypointType "CYCLE";
	if ((_g % 8) == 0) then {
		diag_log format ["[GP] group %1 at %2 side=%3", _g, _pos, _side];
	};
};

diag_log format ["[GP] spawn done units=%1 fps=%2", count allUnits, diag_fps];

// Periodic heartbeat so RPT proves sim is alive while gpsample runs.
[] spawn {
	for "_i" from 1 to 120 do {
		uiSleep 5;
		diag_log format ["[GP] tick=%1 units=%2 fps=%3", _i, count allUnits, diag_fps];
	};
	diag_log "[GP] initServer heartbeat done";
};
