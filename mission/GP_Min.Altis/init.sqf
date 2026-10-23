// GP_Min v3.0 - one-frame material A/B, no setObjectMaterial, no mod API.
// Spawns three H-Barriers 12 m ahead of the player's first-person camera and
// takes one screenshot.  Whether the @gpmat override is loaded is detected via
// CfgPatches and encoded in the filename (gp_mat_nomod.png / gp_mat_mod.png).
diag_log "[GP] GP_Min v3.0 init begin";
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
    diag_log format ["[GP] after selectPlayer isnull=%1", isNull player];
};

setDate [2035, 7, 12, 12, 0];
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

// position, then let the internal camera attach (no enableSimulation false!)
player setPosATL [_bx, _by, 0.2];
player allowDamage false;
player setDir ((_tx - _bx) atan2 (_ty - _by));
player switchCamera "INTERNAL";
uiSleep 2.0;
player lookAt [_tx, _ty, _gz + 6];
uiSleep 1.5;
diag_log format ["[GP] player atl=%1 dir=%2 cam=%3", getPosATL player, getDir player, cameraView];

// ---- three H-Barriers, 12 m ahead, 3.6 m apart ----
private _eye = (getPosATL player) vectorAdd [0, 0, 1.6];
private _tgt = [_tx, _ty, _gz + 6];
private _dir = vectorNormalized (_tgt vectorDiff _eye);
private _right = vectorNormalized (_dir vectorCrossProduct [0, 0, 1]);
private _dirTo = ((_dir select 0) atan2 (_dir select 1));
private _bars = [];

{
    private _p = _eye vectorAdd (_dir vectorMultiply 8) vectorAdd (_right vectorMultiply _x);
    private _z = getTerrainHeightASL _p;
    _p set [2, _z + 0.6];
    private _b = createVehicle ["Land_HBarrier_5_F", _p, [], 0, "CAN_COLLIDE"];
    _b setDir (_dirTo + 90);
    _b setPosASL _p;
    _b allowDamage false;
    _bars pushBack _b;
    uiSleep 0.2;
} forEach [-3.8, 0, 3.8];

uiSleep 1.5;
{
    diag_log format ["[GP] BAR %1 pos=%2 sp=%3", _forEachIndex, getPosATL _x, worldToScreen (getPosATL _x)];
} forEach _bars;

private _modTag = if (isClass (configFile >> "CfgPatches" >> "gpmat")) then { "mod" } else { "nomod" };
diag_log format ["[GP] modtag=%1 cam=%2", _modTag, cameraView];

uiSleep 2.0;
screenshot format ["gp_mat_%1.png", _modTag];
uiSleep 1.0;
screenshot format ["gp_mat_%1_b.png", _modTag];
diag_log "[GP] done";
