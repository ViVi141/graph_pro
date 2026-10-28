param([string]$GroupList = '96,144,192', [int]$SettleSec = 12, [int]$SampleSec = 10)
$Groups = $GroupList.Split(',') | ForEach-Object { [int]$_.Trim() }
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_paths.ps1')
$exe = Join-Path $game 'arma3server_x64.exe'
$prof = Join-Path $env:LOCALAPPDATA 'GP_arma_server'
$cfg = (Join-Path $repo 'server\server.cfg')
$basic = (Join-Path $repo 'server\basic.cfg')
$m = Join-Path $game 'MPMissions\GP_ServerTest.Altis'
$bak = (Join-Path $work 'initServer_saturate_backup.sqf')
$outDir = $work

Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class TC2 {
  [StructLayout(LayoutKind.Sequential)] public struct FT { public uint lo; public uint hi; }
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Auto)] public struct TE { public uint dwSize; public uint cntUsage; public uint tid; public uint pid; public int basePri; public int deltaPri; public uint flags; }
  [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr CreateToolhelp32Snapshot(uint f, uint pid);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool Thread32First(IntPtr h, ref TE e);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool Thread32Next(IntPtr h, ref TE e);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenThread(uint a, bool i, uint tid);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GetThreadTimes(IntPtr h, out FT c, out FT e, out FT k, out FT u);
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] public static extern int GetThreadDescription(IntPtr h, out IntPtr s);
  [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
  static long Ms(FT a, FT b) { long x = ((long)a.hi << 32) | a.lo; long y = ((long)b.hi << 32) | b.lo; return (y - x) / 10000; }
  public static string[] Run(uint pid, int ms) {
    var tids = new List<uint>();
    IntPtr snap = CreateToolhelp32Snapshot(4, 0);
    TE te = new TE(); te.dwSize = (uint)Marshal.SizeOf(te);
    if (Thread32First(snap, ref te)) { do { if (te.pid == pid) tids.Add(te.tid); } while (Thread32Next(snap, ref te)); }
    CloseHandle(snap);
    var h1 = new Dictionary<uint, long>(); var hs = new Dictionary<uint, IntPtr>(); var nm = new Dictionary<uint, string>();
    foreach (uint t in tids) {
      IntPtr h = OpenThread(0x0040, false, t);
      if (h == IntPtr.Zero) h = OpenThread(0x0800, false, t);
      if (h == IntPtr.Zero) continue;
      FT c, e, k, u;
      if (GetThreadTimes(h, out c, out e, out k, out u)) h1[t] = Ms(k, u);
      hs[t] = h;
      IntPtr sp; string name = "";
      try { if (GetThreadDescription(h, out sp) >= 0 && sp != IntPtr.Zero) name = Marshal.PtrToStringUni(sp); } catch {}
      nm[t] = name;
    }
    System.Threading.Thread.Sleep(ms);
    var rows = new List<Tuple<double, string>>(); double total = 0;
    foreach (uint t in tids) {
      if (!hs.ContainsKey(t)) continue;
      FT c, e, k, u; long now = 0;
      if (GetThreadTimes(hs[t], out c, out e, out k, out u)) now = Ms(k, u);
      double pct = 100.0 * (now - h1[t]) / ms; total += pct;
      string name = nm[t]; if (name == null) name = "";
      rows.Add(Tuple.Create(pct, String.Format("{0}|{1:F1}", name, pct)));
      CloseHandle(hs[t]);
    }
    rows.Sort((a, b) => b.Item1.CompareTo(a.Item1));
    var outp = new List<string>(); outp.Add("TOTAL|" + total.ToString("F1"));
    foreach (var r in rows) outp.Add(r.Item2);
    return outp.ToArray();
  }
}
"@

function Make-Init([int]$n) {
$t = @'
diag_log "[GP] sat begin";
enableSaving [false, false];
setDate [2035, 7, 12, 12, 0];
0 setOvercast 0.25; 0 setFog 0; 0 setRain 0;
private _center = [15360, 15360, 0];
private _nGroups = __N__;
private _perGroup = 4;
private _radius = 800;
private _types = ["B_Soldier_F", "B_Soldier_AR_F", "B_Soldier_LAT_F", "O_Soldier_F", "O_Soldier_AR_F"];
private _sides = [west, west, west, east, east];
diag_log format ["[GP] spawn begin groups=%1", _nGroups];
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
  return $t.Replace('__N__', [string]$n)
}

Copy-Item (Join-Path $m 'initServer.sqf') $bak -Force
$results = @()
try {
  foreach ($n in $Groups) {
   try {
    Set-Content -Path (Join-Path $m 'initServer.sqf') -Value (Make-Init $n) -Encoding UTF8
    Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
    $start = Get-Date
    Write-Host ("=== groups=" + $n + " ===")
    $p = Start-Process -FilePath $exe -WorkingDirectory $game -ArgumentList @('-port=2302', "-config=$cfg", "-cfg=$basic", "-profiles=$prof", '-world=empty', '-autoInit', '-name=GPTest', '-nosound') -PassThru
    $rpt = $null
    for ($i = 0; $i -lt 150; $i++) {
      Start-Sleep -Seconds 2
      $rpt = Get-ChildItem $prof -Filter 'arma3server_x64_*.rpt' | Where-Object { $_.LastWriteTime -gt $start.AddSeconds(-5) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
      if ($rpt) {
        $hit = Select-String -Path $rpt.FullName -Pattern 'spawn done units=' -EA SilentlyContinue | Select-Object -Last 1
        if ($hit) { break }
      }
    }
    $spawnLine = (Select-String -Path $rpt.FullName -Pattern 'spawn done units=(\d+)' | Select-Object -Last 1).Line
    Write-Host ("   " + $spawnLine)
    Start-Sleep -Seconds $SettleSec
    if (-not (Get-Process -Id $p.Id -EA SilentlyContinue)) { throw 'server died' }
    $lines = [TC2]::Run([uint32]$p.Id, $SampleSec * 1000)
    $total = ($lines | Where-Object { $_ -like 'TOTAL|*' }) -replace 'TOTAL\|',''
    $top = $lines | Where-Object { $_ -notlike 'TOTAL|*' } | Select-Object -First 8
    Start-Sleep -Seconds 1
    $rpt = Get-ChildItem $prof -Filter 'arma3server_x64_*.rpt' | Where-Object { $_.LastWriteTime -gt $start.AddSeconds(-5) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $fps = @()
    foreach ($fl in (Select-String -Path $rpt.FullName -Pattern 'fps=([\d.]+)' | Select-Object -Last 3)) {
      if ($fl.Line -match 'fps=([\d.]+)') { $fps += [double]$Matches[1] }
    }
    $fpsAvg = if ($fps.Count) { [math]::Round(($fps | Measure-Object -Average).Average, 2) } else { -1 }
    $units = if ($spawnLine -match 'units=(\d+)') { [int]$Matches[1] } else { 0 }
    $results += [pscustomobject]@{ groups=$n; units=$units; total_cpu=[double]$total; fps=$fpsAvg; top=@($top) }
    Write-Host ("RESULT groups={0} units={1} cpu={2} fps={3}" -f $n, $units, $total, $fpsAvg)
    $top | ForEach-Object { Write-Host ("   " + $_) }
    Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 3
   } catch {
    Write-Host ("FAILED groups=" + $n + ": " + $_.Exception.Message)
    Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
   }
  }
} finally {
  Copy-Item $bak (Join-Path $m 'initServer.sqf') -Force
  Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
  $results | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $outDir 'saturation.json') -Encoding UTF8
  Write-Host 'restored initServer.sqf'
}