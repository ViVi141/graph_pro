param([int]$N = 160, [int]$Reps = 5, [int]$Sec = 15)
$ErrorActionPreference = 'Stop'
$game = 'D:\SteamLibrary\steamapps\common\Arma 3'
$exe = Join-Path $game 'arma3server_x64.exe'
$prof = Join-Path $env:LOCALAPPDATA 'GP_arma_server'
$cfg = 'C:\Users\74738\Desktop\Projects\Arma3\graph_pro\server\server.cfg'
$basic = 'C:\Users\74738\Desktop\Projects\Arma3\graph_pro\server\basic.cfg'
$m = Join-Path $game 'MPMissions\GP_ServerTest.Altis'
$bak = 'C:\Users\74738\gp_re\initServer_ab5_backup.sqf'
$prog = 'C:\Users\74738\gp_re\ab5_progress.txt'
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
[] spawn {
	for "_i" from 1 to 40 do {
		uiSleep 5;
		diag_log format ["[GP] tick=%1 units=%2 fps=%3", _i, count allUnits, diag_fps];
	};
};
'@

function Run-One([int]$mode, [int]$num, [int]$den) {
  Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
  Set-Content (Join-Path $game 'GP_gatemode.txt') -Value ("$mode $num $den") -Encoding Ascii -NoNewline
  Remove-Item (Join-Path $game 'GP_gate.log') -Force -EA SilentlyContinue
  $start = Get-Date
  $p = Start-Process -FilePath $exe -WorkingDirectory $game -ArgumentList @('-port=2302', "-config=$cfg", "-cfg=$basic", "-profiles=$prof", '-world=empty', '-autoInit', '-name=GPTest', '-nosound') -PassThru
  $rpt = $null
  for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Seconds 1
    $rpt = Get-ChildItem $prof -Filter 'arma3server_x64_*.rpt' | Where-Object { $_.LastWriteTime -gt $start.AddSeconds(-5) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($rpt) {
      $hit = Select-String -Path $rpt.FullName -Pattern 'spawn done units=' -EA SilentlyContinue | Select-Object -Last 1
      if ($hit) { break }
    }
  }
  Start-Sleep -Seconds 5
  if (-not (Get-Process -Id $p.Id -EA SilentlyContinue)) { throw 'server died before inject' }
  & (Join-Path $game 'injector.exe') 'arma3server_x64.exe' (Join-Path $game 'gpgate3.dll') | Out-Null
  Start-Sleep -Seconds $Sec
  $rpt = Get-ChildItem $prof -Filter 'arma3server_x64_*.rpt' | Where-Object { $_.LastWriteTime -gt $start.AddSeconds(-5) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  $fps = @()
  foreach ($fl in (Select-String -Path $rpt.FullName -Pattern 'fps=([\d.]+)' | Select-Object -Last 2)) {
    if ($fl.Line -match 'fps=([\d.]+)') { $fps += [double]$Matches[1] }
  }
  $alive = [bool](Get-Process -Id $p.Id -EA SilentlyContinue)
  Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
  $avg = if ($fps.Count) { [math]::Round(($fps | Measure-Object -Average).Average, 2) } else { -1 }
  return [pscustomobject]@{ fps=$avg; samples=($fps -join ','); alive=$alive }
}

Copy-Item (Join-Path $m 'initServer.sqf') $bak -Force
Remove-Item $prog -Force -EA SilentlyContinue
$results = @()
try {
  Set-Content -Path (Join-Path $m 'initServer.sqf') -Value ($tpl.Replace('__N__', [string]$N)) -Encoding UTF8
  Copy-Item 'C:\Users\74738\gp_re\gpgate3.dll' $game -Force
  Copy-Item 'C:\Users\74738\Desktop\Projects\Arma3\graph_pro\inject\counter\injector.exe' $game -Force
  $cfgs = @(
    @{m=0; n=0; d=1; label='pass'},
    @{m=2; n=1; d=2; label='pair50'}
  )
  foreach ($c in $cfgs) {
    for ($r = 1; $r -le $Reps; $r++) {
      try {
        $rec = Run-One $c.m $c.n $c.d
        $line = "{0} rep{1} fps={2} samples={3} alive={4}" -f $c.label, $r, $rec.fps, $rec.samples, $rec.alive
        Add-Content $prog $line
        Write-Host $line
        $results += [pscustomobject]@{ label=$c.label; rep=$r; fps=$rec.fps; samples=$rec.samples; alive=$rec.alive }
      } catch {
        $line = "{0} rep{1} FAILED {2}" -f $c.label, $r, $_.Exception.Message
        Add-Content $prog $line
        Write-Host $line
        Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
        Start-Sleep -Seconds 2
      }
    }
  }
} finally {
  Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
  Copy-Item $bak (Join-Path $m 'initServer.sqf') -Force
  Remove-Item (Join-Path $game 'gpgate3.dll'),(Join-Path $game 'injector.exe') -Force -EA SilentlyContinue
  $results | ConvertTo-Json -Depth 4 | Set-Content 'C:\Users\74738\gp_re\ab5_results.json' -Encoding UTF8
  Add-Content $prog 'DONE'
}