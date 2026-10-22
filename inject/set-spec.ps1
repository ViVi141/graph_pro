param([double]$Scale = 0.0, [double]$Power = 12.0)
# 设置材质镜面注入：Scale=0 表示关闭
$game = 'D:\SteamLibrary\steamapps\common\Arma 3'
"$Scale $Power" | Set-Content (Join-Path $game 'GP_spec.txt') -Encoding ASCII
if ($Scale -le 0) { Write-Host "镜面注入：关闭" -ForegroundColor Yellow }
else { Write-Host ("镜面注入：F0=" + $Scale + " power=" + $Power) -ForegroundColor Green }
