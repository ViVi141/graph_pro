param([int]$Seconds = 300, [int]$Interval = 3)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Cap {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int L, T, R, B; }
}
"@
[void][Cap]::SetProcessDPIAware()
$out = '<REPO>\demo\_live\frames'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$p = Get-Process arma3_x64 -ErrorAction SilentlyContinue
if (-not $p) { "no game"; exit }
$r = New-Object Cap+RECT
[void][Cap]::GetWindowRect($p.MainWindowHandle, [ref]$r)
$w = $r.R - $r.L; $h = $r.B - $r.T
"rect $($r.L),$($r.T) $($w)x$($h)"
$sw = [Diagnostics.Stopwatch]::StartNew()
$i = 0
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
    $i++
    try {
        $bmp = New-Object System.Drawing.Bitmap($w, $h)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
        $bmp.Save((Join-Path $out ('f_{0:d4}.jpg' -f $i)), [System.Drawing.Imaging.ImageFormat]::Jpeg)
        $g.Dispose(); $bmp.Dispose()
    } catch { }
    Start-Sleep -Seconds $Interval
}
"captured $i frames"
