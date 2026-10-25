param([int]$WaitSec = 35, [int]$SampleSec = 10)
$ErrorActionPreference = 'Stop'
$game = 'D:\SteamLibrary\steamapps\common\Arma 3'
$exe = Join-Path $game 'arma3server_x64.exe'
$prof = Join-Path $env:LOCALAPPDATA 'GP_arma_server'
$cfg = 'C:\Users\74738\Desktop\Projects\Arma3\graph_pro\server\server.cfg'
$basic = 'C:\Users\74738\Desktop\Projects\Arma3\graph_pro\server\basic.cfg'
Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
$args = @('-port=2302', "-config=$cfg", "-cfg=$basic", "-profiles=$prof", '-world=empty', '-autoInit', '-name=GPTest', '-nosound')
$p = Start-Process -FilePath $exe -WorkingDirectory $game -ArgumentList $args -PassThru
Write-Host ("server pid=" + $p.Id)
Start-Sleep -Seconds $WaitSec
if (-not (Get-Process -Id $p.Id -EA SilentlyContinue)) { throw 'server died' }
$rpt = Get-ChildItem $prof -Filter 'arma3server*.rpt' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($rpt) { Select-String -Path $rpt.FullName -Pattern '\[GP\] spawn done|\[GP\] sweep' | Select-Object -Last 2 | ForEach-Object { Write-Host $_.Line } }
Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class TC {
  [StructLayout(LayoutKind.Sequential)] public struct FT { public uint lo; public uint hi; }
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Auto)] public struct TE { public uint dwSize; public uint cntUsage; public uint tid; public uint pid; public int basePri; public int deltaPri; public uint flags; }
  [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr CreateToolhelp32Snapshot(uint f, uint pid);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool Thread32First(IntPtr h, ref TE e);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool Thread32Next(IntPtr h, ref TE e);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenThread(uint a, bool i, uint tid);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GetThreadTimes(IntPtr h, out FT c, out FT e, out FT k, out FT u);
  [DllImport("kernel32.dll")] public static extern int GetThreadPriority(IntPtr h);
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
      IntPtr sp;
      string name = "";
      try { if (GetThreadDescription(h, out sp) >= 0 && sp != IntPtr.Zero) { name = Marshal.PtrToStringUni(sp); } } catch {}
      nm[t] = name;
    }
    System.Threading.Thread.Sleep(ms);
    var outp = new List<string>();
    double total = 0;
    var rows = new List<Tuple<double, string>>();
    foreach (uint t in tids) {
      if (!hs.ContainsKey(t)) continue;
      FT c, e, k, u;
      long now = 0;
      if (GetThreadTimes(hs[t], out c, out e, out k, out u)) now = Ms(k, u);
      long d = now - h1[t];
      double pct = 100.0 * d / ms;
      total += pct;
      int pri = GetThreadPriority(hs[t]);
      rows.Add(Tuple.Create(pct, String.Format("{0,7} {1,8:F1} {2,9} {3,4} {4}", t, pct, d, pri, nm[t])));
      CloseHandle(hs[t]);
    }
    rows.Sort((a, b) => b.Item1.CompareTo(a.Item1));
    outp.Add("total_cpu_pct " + total.ToString("F1") + " over " + ms + "ms");
    outp.Add("   tid   cpu%     cpu_ms  pri name");
    foreach (var r in rows) outp.Add(r.Item2);
    return outp.ToArray();
  }
}
"@
$proc = Get-Process -Id $p.Id
Write-Host ("process cpu before: " + [math]::Round($proc.TotalProcessorTime.TotalSeconds,1) + "s")
$lines = [TC]::Run([uint32]$p.Id, $SampleSec * 1000)
$lines | ForEach-Object { Write-Host $_ }
Write-Host ("process cpu after: " + [math]::Round((Get-Process -Id $p.Id).TotalProcessorTime.TotalSeconds,1) + "s")
Get-Process arma3server_x64 -EA SilentlyContinue | Stop-Process -Force
Write-Host 'server stopped'
