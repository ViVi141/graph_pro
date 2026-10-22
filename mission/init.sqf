// GraphPro v8 - wait for / force a player, then shoot from his eyes
diag_log "[GP] init begin";
enableSaving [false, false];
showHUD false;

private _t0 = diag_tickTime;
waitUntil { !isNull player || (diag_tickTime - _t0) > 15 };
diag_log format ["[GP] after wait isnull=%1 t=%2", isNull player, diag_tickTime - _t0];

if (isNull player) then {
    private _grp = createGroup [west, true];
    private _u = _grp createUnit ["B_Soldier_F", [15360, 5, 15360], [], 0, "NONE"];
    selectPlayer _u;
    uiSleep 1.0;
    player switchCamera "INTERNAL";
    player allowDamage false;
    uiSleep 0.5;
    diag_log format ["[GP] after selectPlayer isnull=%1", isNull player];
};

setDate [2035, 7, 12, 18, 10];
0 setOvercast 0.30;
0 setFog [0.05, 0.01, 0];
0 setRain 0;
0 setWaves 0.25;
setViewDistance 4000;
setObjectViewDistance 3000;
setTerrainGrid 6.25;
setShadowDistance 200;

private _locs = nearestLocations [[15360, 15360, 0], ["NameCityCapital", "NameCity"], 30000];
private _t = if (count _locs > 0) then { locationPosition (_locs select 0) } else { [15360, 15360, 0] };
private _tx = _t select 0;
private _ty = _t select 1;
private _gz = getTerrainHeightASL [_tx, _ty];
diag_log format ["[GP] town=%1 gz=%2", [_tx, _ty], _gz];

private _bx = _tx;
private _by = _ty - 500;
private _bh = -1000;
private _a = 0;
while { _a < 360 } do {
    private _r = 350;
    while { _r <= 750 } do {
        private _px = _tx + (sin _a) * _r;
        private _py = _ty + (cos _a) * _r;
        private _h = getTerrainHeightASL [_px, _py];
        if (_h > _bh) then { _bh = _h; _bx = _px; _by = _py; };
        _r = _r + 100;
    };
    _a = _a + 15;
};
diag_log format ["[GP] vantage=%1 h=%2", [_bx, _by], _bh];

if (!isNull player) then {
    player setPosATL [_bx, _by, 0.2];
    player allowDamage false;
    player enableSimulation false;
    player setDir ((_tx - _bx) atan2 (_ty - _by));
    player lookAt [_tx, _ty, _gz + 6];
    uiSleep 1.0;
    diag_log format ["[GP] player atl=%1 alive=%2 dir=%3", getPosATL player, alive player, getDir player];
} else {
    diag_log "[GP] STILL NO PLAYER";
};

screenshot "gp_r0_spot.png";
uiSleep 1.0;

private _variants = [
    ["baseline", []],
    ["match", [["ColorCorrections", [0.87, 1.30, 0.0, [0.0,0.0,0.0,0.0], [1.0,1.0,1.0,1.0], [1.0,1.0,1.0,0.0]]]]],
    ["film_lowContrast", [["ColorCorrections", [1.05, 1.0, -0.02, [0.02, 0.02, 0.02, 0.0], [0.95, 0.97, 1.0, 0.55], [0.85, 0.88, 0.95, 0.2]]]]],
    ["cold_highContrast", [["ColorCorrections", [1.0, 1.25, 0.0, [0.0, 0.0, 0.0, 0.0], [1.0, 1.0, 1.0, 0.7], [0.75, 0.85, 1.05, 0.35]]]]],
    ["warm_sunset", [["ColorCorrections", [1.0, 1.05, 0.01, [0.03, 0.01, 0.0, 0.0], [1.05, 0.98, 0.9, 0.6], [1.1, 0.95, 0.8, 0.3]]]]]
];

private _effects = [];
{
    private _name = _x select 0;
    private _defs = _x select 1;
    { ppEffectDestroy _x } forEach _effects;
    _effects = [];
    {
        private _h = ppEffectCreate [_x select 0, 2000 + _forEachIndex];
        _h ppEffectEnable true;
        _h ppEffectAdjust (_x select 1);
        _h ppEffectCommit 0;
        _effects pushBack _h;
    } forEach _defs;
    uiSleep 1.0;
    diag_log format ["[GP] variant=%1 fps=%2", _name, diag_fps];
    screenshot format ["gp_r_%1.png", _name];
    uiSleep 6.0;
} forEach _variants;

diag_log "[GP] done";
