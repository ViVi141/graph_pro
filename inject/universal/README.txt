GraphPro Universal — Arma 3 精简版性能与画质一键优化/重置工具
======================================================================

最简单用法：
  直接双击 GraphPro_Manager.bat，按中文菜单一键安装或一键完全重置还原。

三档精简模式 + 一键重置（零冗余、全部基于 Arma 3 真实材质数据设计）：
  [1] 纯净性能底座 (-Graphics off)：
      纯净 DXVK 3.1.1 (D3D11 -> Vulkan)，零代理额外开销，100% 保留原版画面。
      零 Present 钩子，100% 兼容 AMD AFMF 2 与 Steam 覆盖层。

  [2] 均衡画质 + 性能 (-Graphics agx，零 CPU 开销 ctxHook=0)：
      - 3D 材质层（精准匹配原版有数据的 3 个主着色器）：
        * PSSSSMSuper（载具/武器）：GGX PBR + 柔和 3D 天空/地面 IBL
        * PSSSSMGlass（建筑/载具玻璃）：去 2009 倒立假照片 & 背景树影，改物理 IOR 1.5 玻璃反射
        * PSSSSMTreeAdv（树冠叶片）：3D 逆光次表面散射 SSS（自动排除 AToC 与树干）
      - 全局光影层：24-tap IGN 柔和阴影 + 物理 HDR Bloom + 广色域中性 AgX（日/夜全覆盖）

  [3] 终极旗舰画质 (-Graphics ultra)：
      在 [2] 基础上启用 3-Pass 半分辨率 32-Ray 地平线追踪 RTGI + 5×5 À-Trous 边缘降噪 +
      6.5 m 屋檐深度衰减 GTAO（通吃所有民房 Multi 与地形 TerrainX）。

  [4] 一键完全重置 / 卸载还原 (uninstall.ps1)：
      清理全部注入 DLL/着色器/配置，100% 恢复安装前备份的 Arma3.cfg 与全部 .Arma3Profile。

游戏内实时热调参（无需重启游戏）：
  安装 [2] 或 [3] 后，直接用记事本编辑游戏根目录下的 GP_tune.txt 并保存，1 秒内自动生效：
    exposure / contrast / vibrance / sharpness / rtgiBounce / rtgiAo / treeSss / glassRefl

注意事项：
  - 仅建议单人模式或无 BattlEye 私服使用；联机官方服前请先执行 [4] 一键重置。
  - DXVK + AMD 显卡下请保持游戏内 ATOC = 已禁用（AToC=0），避免树叶透出天空色块。
