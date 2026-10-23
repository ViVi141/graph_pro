param(
    [int]$Mode = 0,
    [double]$Boost = 0.15,
    [double]$Power = 0.0
)
# GP_spec.txt: mode boost [power]
#   mode 0 = off
#   mode 1 = boost existing specular only (skip grass/clouds)
$game = 'D:\SteamLibrary\steamapps\common\Arma 3'
"$Mode $Boost $Power" | Set-Content (Join-Path $game 'GP_spec.txt') -Encoding ASCII
if ($Mode -le 0) { Write-Host "镜面：关闭 (mode 0)" -ForegroundColor Yellow }
else { Write-Host ("镜面：mode=1 boost=" + $Boost + " power=" + $Power) -ForegroundColor Green }
