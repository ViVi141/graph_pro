GraphPro Universal — Arma 3 全硬件通用性能底座（+ 零CPU开销新一代画质层）
==========================================================================

默认模式（纯净性能底座，-Graphics off）：
  - 直接部署纯净 DXVK 3.1.1 (D3D11 -> Vulkan)，零额外代理开销，100% 保留原版/你的光照模组画面
  - 自动识别游戏路径、CPU 线程数（动态调优 dxvk.numCompilerThreads）、显卡档位与全部存档
  - 7900X + 7900 XT 实测：
      * -Tier none     : +6.0% 平均帧 / +9.3% 1% Low（一刀不剪纯 Vulkan 收益）
      * -Tier high     : 71.05 FPS（+17.5%，1% Low +20.9%，保留 4x MSAA + Ultra 贴图/阴影/云层 + 3800m 视距）
      * -Tier high_fps : 74.57 FPS（+23.4%，1% Low +32.2%，关云层 + tg=25）
  - 零 Present 钩子：100% 兼容 AMD AFMF 2（开启后 71-75 原生帧可翻倍至 142-150+ FPS）与 Steam 覆盖层

新一代画质层（-Graphics agx，全程仅 CreatePixelShader 替换，ctxHook=0，零 CPU 开销）：
  1. AgX Punchy v3（日间 + 夜间全时段）：无过曝高光滚降 + 边缘保护微对比度 + IGN 8-bit 去色带
  2. 物理 HDR Bloom（替换 BloomInitDownsample4x）：修复原版 saturate(luma) 截断 HDR 的雾感泛光缺陷，Karis 防闪烁
  3. 柔和蓝噪声阴影 + 光照前屏幕空间接触阴影（替换 SSSM VeryHigh/High/Normal）：
     - Interleaved Gradient Noise (IGN) + 16-tap Vogel Disk 消除原版 2008 颗粒噪点
     - 直接从引擎 ShadowmapMatrix 读取每帧精确太阳方向，在光照前衰减直射光（保留 100% 天空环境光，不黑天、不伤 UI）
  4. Natural SSAO：平滑去黑斑环境光遮蔽

  * 若仅需 AgX + HDR Bloom + Natural SSAO（不含接触阴影，适合低端核显或 A/B 对比），可使用 -Graphics agx_lite。

一键安装：
  powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1

常用参数：
  -Tier auto|high|high_fps|mid|igpu|none       (默认 auto；选 none 仅装 DXVK 不改游戏配置)
  -Backend auto|dxvk|native                    (默认 auto)
  -Graphics off|agx|agx_lite|ssgi|legacy       (默认 off 纯净性能；agx = 3D GGX PBR + v4.2；ssgi = 路线A 3D PBR + 路线B 线性HDR SSGI 间接光反弹)

一键卸载（完整恢复所有备份配置与文件）：
  powershell -NoProfile -ExecutionPolicy Bypass -File uninstall.ps1
