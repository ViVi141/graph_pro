#Requires -Version 5.0
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$installPs1   = Join-Path $here 'install.ps1'
$uninstallPs1 = Join-Path $here 'uninstall.ps1'

function Find-Arma3Dir {
    $reg = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Bohemia Interactive\Arma 3' -ErrorAction SilentlyContinue
    if ($reg -and $reg.main -and (Test-Path (Join-Path $reg.main 'Arma3_x64.exe'))) { return $reg.main }
    $sreg = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam','HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue
    $steam = ($sreg.InstallPath + $sreg.SteamPath) | Where-Object { $_ } | Select-Object -First 1
    if ($steam) {
        $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
        if (Test-Path $vdf) {
            $libs = Select-String -Path $vdf -Pattern '"path"\s+"([^"]+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value -replace '\\\\','\' }
            foreach ($l in $libs) {
                $cand = Join-Path $l 'steamapps\common\Arma 3'
                if (Test-Path (Join-Path $cand 'Arma3_x64.exe')) { return $cand }
            }
        }
    }
    return ''
}

function Get-Status([string]$gameDir) {
    if (-not $gameDir -or -not (Test-Path (Join-Path $gameDir 'Arma3_x64.exe'))) {
        return '未自动检测到 Arma 3 目录'
    }
    $hasD3d       = Test-Path (Join-Path $gameDir 'd3d11.dll')
    $hasDxvkChain = Test-Path (Join-Path $gameDir 'gp_dxvk_d3d11.dll')
    $hasRtgi      = Test-Path (Join-Path $gameDir 'GP_rtgi_trace.dxbc')
    $hasRepl      = Test-Path (Join-Path $gameDir 'GP_replace.txt')
    $hasBak       = Test-Path (Join-Path $gameDir '_gp_universal_backup')

    if (-not $hasD3d) { return '原版纯净状态（未安装）' }
    $mode = if ($hasRtgi) { '已安装：终极旗舰画质 (DXVK + 3-Pass RTGI + 24-tap柔影 + 3D PBR/Glass/TreeSSS)' }
            elseif ($hasRepl) { '已安装：均衡画质 (DXVK + 24-tap柔影 + 3D PBR/Glass/TreeSSS + AgX)' }
            elseif (-not $hasDxvkChain) { '已安装：纯净性能底座 (DXVK 3.1.1 Vulkan，原版画面)' }
            else { '已安装：Universal Proxy' }
    if ($hasBak) { $mode += ' [已备份原配置]' }
    return $mode
}

function Ask-Tier {
    Write-Host ''
    Write-Host '  是否同时应用硬件自适应游戏配置？' -ForegroundColor Cyan
    Write-Host '    [1] 保留我现有的 Arma3.cfg / 存档画质设置（推荐：不降 terrainGrid / 视距）'
    Write-Host '    [2] 自动应用高帧率均衡配置（自动识别显卡档位，大幅提帧，AToC=0）'
    Write-Host '    [3] 自动应用极限帧率配置（关云层 + tg=25，最高帧率）'
    $c = Read-Host '  请选择 [1-3] (默认 1)'
    switch ($c) {
        '2' { return 'auto' }
        '3' { return 'high_fps' }
        default { return 'none' }
    }
}

$gameDir = Find-Arma3Dir
$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name.Trim()
$gpu = (Get-CimInstance Win32_VideoController | Where-Object { $_.Name -notmatch 'Virtual|Microsoft Basic|GameViewer' } | Select-Object -First 1).Name

while ($true) {
    Clear-Host
    $status = Get-Status $gameDir
    Write-Host '======================================================================' -ForegroundColor Cyan
    Write-Host '   GraphPro Universal — Arma 3 性能与画质一键优化 / 重置工具' -ForegroundColor White
    Write-Host '======================================================================' -ForegroundColor Cyan
    Write-Host "  游戏目录 : $(if ($gameDir) { $gameDir } else { '(未检测到，安装时可手动输入)' })" -ForegroundColor Gray
    Write-Host "  本机硬件 : $cpu | $gpu" -ForegroundColor Gray
    Write-Host "  当前状态 : $status" -ForegroundColor Yellow
    Write-Host '----------------------------------------------------------------------' -ForegroundColor DarkGray
    Write-Host '  [1] 纯净性能底座（DXVK 3.1.1 Vulkan，零代理开销，100% 保留原版画面）' -ForegroundColor Green
    Write-Host '  [2] 均衡画质 + 性能（3D PBR/玻璃/树叶SSS + 24-tap柔影 + HDR Bloom + 广色域AgX）' -ForegroundColor Cyan
    Write-Host '  [3] 终极旗舰画质（在[2]基础上开启 3-Pass 32射线RTGI + À-Trous降噪 + 6.5m屋檐GTAO）' -ForegroundColor Magenta
    Write-Host '  [4] 一键完全重置 / 卸载还原（删除全部注入文件并 100% 恢复原始配置）' -ForegroundColor Red
    Write-Host '  [0] 退出' -ForegroundColor DarkGray
    Write-Host '----------------------------------------------------------------------' -ForegroundColor DarkGray
    Write-Host '  提示：仅限单人/无 BattlEye 私服；DXVK 下建议游戏内 ATOC=禁用；游戏内可热改 GP_tune.txt。' -ForegroundColor DarkYellow
    Write-Host ''

    $choice = Read-Host '请输入选项编号 [0-4]'
    try {
        switch ($choice) {
            '1' {
                $tier = Ask-Tier
                & $installPs1 -Game $gameDir -Graphics off -Tier $tier -Silent
                Write-Host ''
                pause
            }
            '2' {
                $tier = Ask-Tier
                & $installPs1 -Game $gameDir -Graphics agx -Tier $tier -Silent
                Write-Host ''
                pause
            }
            '3' {
                $tier = Ask-Tier
                & $installPs1 -Game $gameDir -Graphics ultra -Tier $tier -Silent
                Write-Host ''
                pause
            }
            '4' {
                & $uninstallPs1 -Game $gameDir -Silent
                Write-Host ''
                pause
            }
            '0' {
                break
            }
            default {
                Write-Host '无效选项，请重新输入。' -ForegroundColor Yellow
                Start-Sleep -Seconds 1
            }
        }
    } catch {
        Write-Host "[错误] $($_.Exception.Message)" -ForegroundColor Red
        pause
    }
    if ($choice -eq '0') { break }
}
