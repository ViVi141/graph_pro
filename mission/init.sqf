// GraphPro shot rig — player INTERNAL at fixed hill vantage.
// camCreate caused strong radial motion blur; the sharp 22:20 vanilla shot used player cam.
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
    player allowDamage false;
    uiSleep 0.5;
};

setDate [2035, 7, 12, 12, 0];
0 setOvercast 0.25;
0 setFog [0.02, 0.008, 0];
0 setRain 0;
0 setWaves 0.1;
setViewDistance 4000;
setObjectViewDistance 3000;
setTerrainGrid 6.25;
setShadowDistance 200;

private _locs = nearestLocations [[15360, 15360, 0], ["NameCity", "NameVillage", "NameCityCapital"], 30000];
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

player setPosATL [_bx, _by, 0.5];
player allowDamage false;
player setDir ((_tx - _bx) atan2 (_ty - _by));
player switchCamera "INTERNAL";
uiSleep 2.0;

// Aim then freeze so the eye cam does not keep drifting into grass.
player lookAt [_tx, _ty, _gz + 6];
uiSleep 3.0;
player enableSimulation false;
uiSleep 4.0;

diag_log format ["[GP] atl=%1 dir=%2 cam=%3 fps=%4", getPosATL player, getDir player, cameraView, diag_fps];
screenshot "gp_r_baseline.png";
uiSleep 1.2;
screenshot "gp_r_baseline_b.png";
diag_log "[GP] done";

player enableSimulation true;
