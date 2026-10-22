param([int]$Seconds = 900, [int]$Interval = 3, [string]$Out = 'C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\_live\run2')
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Cap2 {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int L, T, R, B; }
}
"@
[void][Cap2]::SetProcessDPIAware()
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$sw = [Diagnostics.Stopwatch]::StartNew()
$i = 0
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
    $p = Get-Process arma3_x64 -ErrorAction SilentlyContinue
    if ($p -and $p.MainWindowHandle -ne 0) {
        $r = New-Object Cap2+RECT
        [void][Cap2]::GetWindowRect($p.MainWindowHandle, [ref]$r)
        $w = $r.R - $r.L; $h = $r.B - $r.T
        if ($w -gt 200 -and $h -gt 200) {
            $i++
            try {
                $bmp = New-Object System.Drawing.Bitmap($w, $h)
                $g = [System.Drawing.Graphics]::FromImage($bmp)
                $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
                $bmp.Save((Join-Path $Out ('f_{0:d4}.jpg' -f $i)), [System.Drawing.Imaging.ImageFormat]::Jpeg)
                $g.Dispose(); $bmp.Dispose()
            } catch { }
        }
    }
    Start-Sleep -Seconds $Interval
}
"captured $i frames"
