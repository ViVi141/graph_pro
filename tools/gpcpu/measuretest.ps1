param([int]$N = 160, [int]$Sec = 15)
$ErrorActionPreference = 'Stop'
$game = 'D:\SteamLibrary\steamapps\common\Arma 3'
$exe = Join-Path $game 'arma3server_x64.exe'
$prof = Join-Path $env:LOCALAPPDATA 'GP_arma_server'
$cfg = 'C:\Users\74738\Desktop\Projects\Arma3\graph_pro\server\server.cfg'
$basic = 'C:\Users\74738\Desktop\Projects\Arma3\graph_pro\server\basic.cfg'
$m = Join-Path $game 'MPMissions\GP_ServerTest.Altis'
$bak = 'C:\Users\74738\gp_re\initServer_measure_backup.sqf'
$tpl = @'
enableSaving [false, false];
setDate [2035, 7, 12, 12, 0];
0 setOvercast 0.25; 0 setFog 0; 0 setRain 0;
private _center = [15360, 15360, 0];
private _nGroups = __N__;
private _perGroup = 4;
private _radius = 800;
private _types = ["B_Soldier_F", "B_Soldier_AR_F", "B_Soldier_LAT_F", "O_Soldier_F", "O_Soldier_AR_F"];
private _sides = [west, west, west, east, east];
for "_g" from 0 to (_nGroups - 1) do {
	private _ang = (_g / _nGroups) * 360;
	private _r = 200 + (_g % 6) * (_radius / 6);
	private _pos = [(_center select 0) + (sin _ang) * _r, (_center select 1) + (cos _ang) * _r, 0];
	private _side = _sides select (_g % (count _sides));
	private _grp = createGroup [_side, true];
	for "_u" from 0 to (_perGroup - 1) do {
		private _cls = _types select ((_g + _u) % (count _types));
		private _unit = _grp createUnit [_cls, _pos, [], 8, "FORM"];
		_unit setSkill 0.5;
		_unit allowFleeing 0;
		_unit allowDamage false;
	};
	private _r2 = 100;
	{
		private _a = _ang + _x;
		private _wpos = [(_pos select 0) + (sin _a) * _r2, (_pos select 1) + (cos _a) * _r2, 0];
		private _wp = _grp addWaypoint [_wpos, 0];
		_wp setWaypointType "MOVE";
		_wp setWaypointSpeed "LIMITED";
		_wp setWaypointBehaviour "AWARE";
	} forEach [0, 90, 180, 270];
	private _wpc = _grp addWaypoint [_pos, 0];
	_wpc setWaypointType "CYCLE";
	if ((_g % 8) == 0) then { uiSleep 0.05; };
};
diag_log format ["[GP] spawn done units=%1 groups=%2", count allUnits, _nGroups];
'@
Copy-Item (Join-Path $m 'initServer.sqf') $bak -Force
try {
  Set-Content -Path (Join-Path $m 'initServer.sqf') -Value ($tpl.Replace('__N__', [string]$N)) -Encoding UTF8
  Copy-Item 'C:\Users\74738\gp_re\gpmeasure.dll' $game -Force
  Copy-Item 'C:\Users\74738\Desktop\Projects\Arma3\graph_pro\inject\counter\injector.exe' $game -Force
  Set-Content (Join-Path $game 'GP_measure.cfg') -Encoding Ascii -Value @('rva=646FC0','back=646FC5','bytes=48895C2410')
  Remove-Item (Join-Path $game 'GP_measure.log') -Force -EA SilentlyContinue
  Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
  $start = Get-Date
  $p = Start-Process -FilePath $exe -WorkingDirectory $game -ArgumentList @('-port=2302', "-config=$cfg", "-cfg=$basic", "-profiles=$prof", '-world=empty', '-autoInit', '-name=GPTest', '-nosound') -PassThru
  $rpt = $null
  for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Seconds 1
    $rpt = Get-ChildItem $prof -Filter 'arma3server_x64_*.rpt' | Where-Object { $_.LastWriteTime -gt $start.AddSeconds(-5) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($rpt) {
      $hit = Select-String -Path $rpt.FullName -Pattern 'spawn done units=' -EA SilentlyContinue | Select-Object -Last 1
      if ($hit) { Write-Host $hit.Line; break }
    }
  }
  Start-Sleep -Seconds 5
  & (Join-Path $game 'injector.exe') 'arma3server_x64.exe' (Join-Path $game 'gpmeasure.dll')
  Start-Sleep -Seconds $Sec
  Write-Host '--- log ---'
  Get-Content (Join-Path $game 'GP_measure.log') -EA SilentlyContinue | Select-Object -First 6
  Write-Host '--- submit ---'
  Get-Content (Join-Path $game 'GP_submit.txt') -EA SilentlyContinue
  $alive = [bool](Get-Process -Id $p.Id -EA SilentlyContinue)
  Write-Host ("server alive=" + $alive)
} finally {
  Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
  Copy-Item $bak (Join-Path $m 'initServer.sqf') -Force
  Remove-Item (Join-Path $game 'gpmeasure.dll'),(Join-Path $game 'injector.exe') -Force -EA SilentlyContinue
  Write-Host 'restored + cleaned'
}