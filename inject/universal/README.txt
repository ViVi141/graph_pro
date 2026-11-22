GraphPro Universal — Arma 3 全硬件通用性能底座（+ 可插拔画质层）
===============================================================

默认模式（纯净性能底座，-Graphics off）：
  - 直接部署纯净 DXVK 3.1.1 (D3D11 -> Vulkan)，零额外代理开销，100% 保留原版/你的光照模组画面
  - 自动识别游戏路径、CPU 线程数（动态调优 dxvk.numCompilerThreads）、显卡档位与全部存档
  - 7900X + 7900 XT 实测：
      * -Tier none     : +6.0% 平均帧 / +9.3% 1% Low（一刀不剪纯 Vulkan 收益）
      * -Tier high     : 71.05 FPS（+17.5%，1% Low +20.9%，保留 4x MSAA + Ultra 贴图/阴影/云层 + 3800m 视距）
      * -Tier high_fps : 74.57 FPS（+23.4%，1% Low +32.2%，关云层 + tg=25）
  - 零 Present 钩子：100% 兼容 AMD AFMF 2（开启后 71-75 原生帧可翻倍至 142-150+ FPS）与 Steam 覆盖层

一键安装：
  powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1

常用参数：
  -Tier auto|high|high_fps|mid|igpu|none   (默认 auto；选 none 仅装 DXVK 不改游戏配置)
  -Backend auto|dxvk|native                (默认 auto)
  -Graphics off|agx|legacy                 (默认 off 纯净原版画面；选 agx 启用零帧率损耗的新版无过曝 AgX Punchy v3 + Natural SSAO)

一键卸载（完整恢复所有备份配置与文件）：
  powershell -NoProfile -ExecutionPolicy Bypass -File uninstall.ps1
