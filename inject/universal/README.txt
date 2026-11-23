GraphPro Universal — Arma 3 全硬件通用性能与画质一键优化/重置工具
==========================================================================

最简单用法（推荐）：
  直接双击运行 GraphPro_Manager.bat
  即可通过中文交互菜单一键切换性能/画质档位，或一键完整重置还原！

内置 4 档模式 + 1 键重置：
  [1] 纯净性能底座 (-Graphics off)：
      直接部署纯净 DXVK 3.1.1 (D3D11 -> Vulkan)，零额外代理开销，100% 保留原版画面。
      7900X + 7900 XT / 2560x1440 / YAAB 实测（基线 60.45 FPS；原始数据
      extract/bench_7900x/*.json，总表 docs/20-route2-7900x-7900xt-perf.md）：
        - 保留原配置 (-Tier none)     : 64.08 FPS（+6.0% 平均帧，1% Low +9.3%，纯 Vulkan 收益）
        - 均衡高画质 (-Tier high)     : 71.05 FPS（+17.5%，1% Low 43.30 = +20.9%）
        - 极限帧率   (-Tier high_fps) : 74.57 FPS（+23.4%，1% Low 47.35 = +32.2%）
      零 Present 钩子：100% 兼容 AMD AFMF 2（开启后翻倍至 140–150+ FPS）与 Steam 覆盖层。

  [2] 新一代画质 (-Graphics agx)：
      - 路线 A：3D 前向材质着色器 GGX PBR 升级（替换 PSSSSMSuper，真实菲涅尔与天空/地面 IBL 反射）
      - AgX Punchy v4.2（日间 + 夜间全时段）：无过曝高光滚降 + FidelityFX CAS 锐化 + 日光冷暖分离 + IGN 去色带
      - 物理 HDR Bloom（Karis 防闪烁，修复原版白墙发雾与车灯/手电死白）
      - IGN Vogel 柔和蓝噪声阴影 + 深度连续性保护光照前接触阴影（草叶无黑斑）+ Grounded SSAO

  [3] 终极旗舰画质 (-Graphics ultra)：
      三 Pass 渲染管线：半分辨率 32-Ray 地平线遮挡追踪 RTGI（堵死薄墙漏光）+ 5×5 深度边缘感知
      À-Trous 空间光线重建降噪器 + 联合双边上采样 + 深度驱动物理瑞利/米氏大气散射（远山空气透视）
      + 3D GGX PBR + HDR Bloom + 柔和接触阴影 + 日/夜 AgX + CAS。

  [4] 轻量画质 (-Graphics agx_lite)：
      仅保留日/夜 AgX + 物理 HDR Bloom + Natural SSAO（不含接触阴影与 RTGI，适合核显或 A/B 对比）。

  [5] 一键完全重置 / 卸载还原 (uninstall.ps1)：
      自动清理全部注入 DLL/着色器/配置，并 100% 还原安装前备份的 Arma3.cfg 与全部 .Arma3Profile。

量化边界（请按此理解上面三档画质包的收益）：
  性能数字只覆盖 DXVK 后端与 Tier 配置这两件事。
  画质包（AgX v4.2 / GGX PBR / SSGI / RTGI / HDR Bloom / 柔和阴影）目前只有启动日志与
  截图链，没有图像指标，也没有帧率代价测量；ultra 额外增加三个 pass。仓库按自己的标准
  把它们归类为"已接线、未量化"（docs/21-project-review.md §3、docs/RESULTS.md 2026-11-23）。

命令行用法（高级/静默脚本）：
  安装：powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Graphics off|agx|ultra|ssgi|agx_lite|legacy -Tier none|auto|high|high_fps|mid|igpu
  重置：powershell -NoProfile -ExecutionPolicy Bypass -File uninstall.ps1
  -Graphics legacy 部署的是已归档经典线的画质包（ACES 色调映射 + 旧 SSAO + GP_amb/GP_expo/
  GP_spec 预设），只用于复现历史对照，不再是默认推荐；经典线源码在 archive\legacy-proxy\。

运行时行为（代理侧）：
  - 不改任何模型 / 贴图 / rvmat；只替换 (size, crc32) 指纹命中后处理/材质着色器。
  - GP_amb.txt / GP_expo.txt / GP_spec.txt 每 2 秒按文件时间戳检查一次：改内容立即生效，
    启动后再放入这些文件也会被识别（日志写 "constant injection enabled by a config file
    that appeared after launch"）。注意 GP_replace.txt / 各 .dxbc 载荷仍需重启游戏。
  - 启动日志 device hooks active (... ctxHook=0, mapHook=1 ...)：ctxHook=0 表示没有启用任何
    常量注入（画质包档位的常态）；Map/Unmap 始终挂着直通包装器，未配置时只多一次布尔判断。
  - 创建 50 个像素着色器仍无任何替换命中时写 WARN（说明游戏已更新、指纹过期）。

安全提示：
  仅建议在单人模式或无 BattlEye 的私服使用；联机官方服前请先执行 [5] 一键重置还原。
  经典画面旁路线已归档（archive\legacy-proxy\），Universal 是唯一在维护的注入线。
  如果你的游戏目录仍部署着经典代理，先跑 archive\legacy-proxy\inject\remove.ps1，
  再跑 install.ps1；不需要再切回经典线。
  安装器会先清理经典线残留的 GP_* 配置与陈旧后端文件，并把游戏目录原有
  d3d11.dll / dxgi.dll / dxvk.conf 备份到 _gp_universal_backup。
  安装器写 Arma3.cfg 与 .Arma3Profile 时使用无 BOM 的 UTF-8（PowerShell 5.1 的
  -Encoding UTF8 会带 BOM，已避免）。

只读自检（不启动游戏）：
  powershell -NoProfile -ExecutionPolicy Bypass -File ..\..\tools\verify_universal.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File ..\..\tools\verify_universal.ps1 -Expect ultra
  检查部署身份、SHA256、GP_universal.log 命中与最新 RPT；退出码 0 = 全部通过。
  发行包自带 MANIFEST.json（git commit + 每个文件 sha256），verify 会打印它并与当前构建比对。
