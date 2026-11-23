GraphPro Universal — Arma 3 全硬件通用性能与画质一键优化/重置工具
==========================================================================

最简单用法（推荐）：
  直接双击运行 GraphPro_Manager.bat
  即可通过中文交互菜单一键切换性能/画质档位，或一键完整重置还原！

内置 4 档模式 + 1 键重置：
  [1] 纯净性能底座 (-Graphics off)：
      直接部署纯净 DXVK 3.1.1 (D3D11 -> Vulkan)，零额外代理开销，100% 保留原版画面。
      7900X + 7900 XT 实测：
        - 保留原配置 (-Tier none)     : +6.0% 平均帧 / +9.3% 1% Low（纯 Vulkan 收益）
        - 均衡高画质 (-Tier auto)     : 71–79 FPS（+17.5% ~ +31.1%），1% Low +21% ~ +35%
        - 极限帧率   (-Tier high_fps) : 74.57 FPS（+23.4%，1% Low +32.2%）
      零 Present 钩子：100% 兼容 AMD AFMF 2（开启后翻倍至 140–150+ FPS）与 Steam 覆盖层。

  [2] 新一代画质 (-Graphics agx，零 CPU 开销 ctxHook=0)：
      - 路线 A：3D 前向材质着色器 GGX PBR 升级（替换 PSSSSMSuper，真实菲涅尔与天空/地面 IBL 反射）
      - AgX Punchy v4.2（日间 + 夜间全时段）：无过曝高光滚降 + FidelityFX CAS 锐化 + 日光冷暖分离 + IGN 去色带
      - 物理 HDR Bloom（Karis 防闪烁，修复原版白墙发雾与车灯/手电死白）
      - IGN Vogel 柔和蓝噪声阴影 + 深度连续性保护光照前接触阴影（草叶无黑斑）+ Grounded SSAO

  [3] 旗舰画质 (-Graphics ssgi)：
      在 [2] 基础上启用路线 B（零拷贝线性 HDR 16-Ray SSGI 间接光反弹 + 多米级 GTAO）。
      7900X + 7900 XT 1440p Ultra YAAB 实测 74.29 FPS（比原版 DX11 仍高 +22.9%）。

  [4] 轻量画质 (-Graphics agx_lite)：
      仅保留日/夜 AgX + 物理 HDR Bloom + Natural SSAO（不含接触阴影与 SSGI，适合核显或 A/B 对比）。

  [5] 一键完全重置 / 卸载还原 (uninstall.ps1)：
      自动清理全部注入 DLL/着色器/配置，并 100% 还原安装前备份的 Arma3.cfg 与全部 .Arma3Profile。

命令行用法（高级/静默脚本）：
  安装：powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Graphics off|agx|ssgi|agx_lite -Tier none|auto|high|high_fps|mid|igpu
  重置：powershell -NoProfile -ExecutionPolicy Bypass -File uninstall.ps1

安全提示：
  仅建议在单人模式或无 BattlEye 的私服使用；联机官方服前请先执行 [5] 一键重置还原。
