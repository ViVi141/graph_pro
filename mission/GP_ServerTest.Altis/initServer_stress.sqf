// Script-CPU stress — proves diag_fps can move when work is real.
diag_log "[GP] initServer STRESS begin";
enableSaving [false, false];
setDate [2035, 7, 12, 12, 0];

private _center = [15360, 15360, 0];
private _dummy = createGroup [west, true];
private _u = _dummy createUnit ["B_Soldier_F", _center, [], 0, "NONE"];
_u allowDamage false;

[] spawn {
	private _i = 0;
	while { true } do {
		private _t0 = diag_tickTime;
		for "_k" from 1 to 100 do {
			private _p = [
				15360 + (_k * 17),
				15360 - (_k * 13),
				0
			];
			nearestObjects [_p, ["House", "Building", "All"], 150];
			_p findEmptyPosition [1, 60, "B_Soldier_F"];
			terrainIntersectASL [_p vectorAdd [0, 0, 50], _p];
		};
		_i = _i + 1;
		if ((_i % 5) == 0) then {
			diag_log format [
				"[GP] tick=%1 units=%2 fps=%3 workMs=%4",
				_i,
				count allUnits,
				diag_fps,
				(diag_tickTime - _t0) * 1000
			];
		};
		uiSleep 0.05;
	};
};
