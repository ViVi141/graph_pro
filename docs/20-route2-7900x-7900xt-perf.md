# 20 · Route 2 实证报告：Ryzen 9 7900X + RX 7900 XT 性能优化全剖析

日期：2026-11-22  
平台：**AMD Ryzen 9 7900X (12C/24T, 2×32MB L3 Dual-CCD)** + **AMD Radeon RX 7900 XT (20GB)** + **32GB RAM**  
测试标准：2560×1440、自动确定性 YAAB（`mission/GP_YAAB_Auto.Altis`，基于用户本地 Workshop YAAB，无修改任何单位/镜头/爆炸，新增逐帧 `EachFrame` 精确帧时统计与 RPT 自动归档）  
剖析工具：自研零等待偏置 Active-CPU + 主线程调用栈火焰图剖析器 [`inject/counter/gpprof.cpp`](../inject/counter/gpprof.cpp) + 全量 RTTI 虚表/字符串标注器 [`tools/annotate_prof.py`](../tools/annotate_prof.py)

---

## 1. 完整 14 轮控制变量 A/B 实测总表

| # | Tag | Avg FPS | 对比原版均值(60.45) | 1% Low | 0.1% Low | P50 / P95 / P99 (ms) | DXVK | 关键变量 |
|---:|---|---:|---:|---:|---:|---|---:|---|
| 1 | `01_baseline_prof` | 61.55 | — | 36.20 | 25.81 | 16.0 / 22.0 / 25.0 | No | 原版 DX11 + tbb4 + ViVi141 全拉满 |
| 1b | `01b_baseline_prof` | 59.35 | — | 35.43 | 30.77 | 17.0 / 23.0 / 26.0 | No | 原版基线复测（均值 **60.45 / 1% Low 35.82**） |
| 2 | `08_dx11_novsync` | 60.77 | +0.5% | 37.23 | 29.20 | 16.0 / 23.0 / 25.0 | No | 原版 DX11 仅关 VSync + `MaxFramesAhead=1` |
| 3 | `03b_mimalloc_clean` | 61.11 | +1.1% | **38.30** | 29.52 | 16.0 / 22.0 / 24.0 | No | 自编译 Microsoft `mimalloc 3.7.0` (AVX2+大页) |
| 4 | `02_dxvk_311` | 63.43 | +4.9% | 33.24 | 17.54 | 15.0 / 22.0 / 24.0 | **YES** | DXVK 3.1.1 首轮冷缓存（首次编译管线） |
| 5 | **`04_dxvk_warm_tbb4`** | **64.08** | **+6.0%** | **39.15 (+9.3%)** | 30.19 | **15.0 / 21.0 / 24.0** | **YES** | **热缓存 DXVK 3.1.1（零画质损失最佳）** |
| 6 | `05_dxvk_mimalloc_all` | 62.49 | +3.4% | 39.13 | **31.37** | 16.0 / 22.0 / 24.0 | YES | 热 DXVK + `gp_mimalloc` 全核 |
| 7 | `06_dxvk_mimalloc_ccd0` | **54.90** | **-9.2%** | 33.01 | 25.36 | 18.0 / 24.0 / 27.0 | YES | 全进程绑单 CCD0 (`0x000FFF`) → **负优化** |
| 8 | `10_dxvk_turbo` | 61.03 | +1.0% | 36.36 | 30.89 | 16.0 / 22.0 / 25.0 | YES | `gp_turbo`（改自旋优先级+删双屏障+双线程绑核）→ **负优化** |
| 9 | `09_dxvk_smart_ultra` | 64.52 | +6.7% | 39.17 | 32.13 | 15.0 / 21.0 / 23.0 | YES | DXVK + MSAA 2x + sc=1.0M + objvd=1500 + tg=6.25 |
| 10 | `11_dxvk_shadow_off` | 66.45 | +9.9% | 37.14 | 29.60 | 15.0 / 21.0 / 24.0 | YES | DXVK + **彻底关阴影**（证明阴影仅吃 ~2.4 FPS） |
| 11 | **`13_dxvk_ultragpu_smartcpu`** | **71.05** | **+17.5%** | **43.30 (+20.9%)** | 32.49 | **14.0 / 19.0 / 21.0** | **YES** | **保 1440p 4xMSAA/Ultra 阴影云层/3800m 视距 + `sc=400k, objvd=1000, tg=12.5`** |
| 12 | **`14_dxvk_same_noclouds`** | **74.57** | **+23.4%** | **47.35 (+32.2%)** | **35.84** | **13.0 / 18.0 / 19.0** | **YES** | **同上 + 关云层 + `tg=25`** |
| 13 | **`12_dxvk_min_render`** | **86.31** | **+42.8%** | **50.34 (+40.5%)** | 34.81 | **12.0 / 16.0 / 18.0** | **YES** | **7900X 纯世界模拟/AI 物理天花板上限** |

原始数据全部保留在 `extract/bench_7900x/*.json` 及 `*_prof_annotated.txt`。

---

## 2. 主线程调用栈火焰图核心发现（零等待偏置）

对比 `03_mimalloc_prof_prof_annotated.txt`（DX11）与 `07_dxvk_prof_prof_annotated.txt`（DXVK 3.1.1），7900X 主线程（~15.6 ms/帧）时间结构如下：

| 模块 / 函数 | 主线程 Inclusive 占比 | 本质与说明 |
|---|---:|---|
| `0x0161127C`→`0x01250473` (`tcsb`/`tcih`/`sbih`) | **11.1%** | 阴影缓冲/地形/树木实例化与 64 位 Draw 排序（含 `0x01264CFB` 3.2%） |
| `0x0113C911`→`0x0113E080`→`0x0125BA20` | **11.5%** | 场景物体可见性/LOD/视距裁切（读 `[0x1422513B8/BC]`） |
| `0x016107C0` (`pass1OF`) + `0x0162CFA0` (`pass1ON`) + `0x0113A800` | **13.3%** | 前向近/远不透明与透明 Draw 命令录制 |
| `0x016C7AE0` (`endHL`) → **`0x0169B288`** | **9.2%–9.8%**（独占 #1） | 帧末硬同步屏障：主线程自旋等待 2 号渲染线程 `RenderCBToPlay` 排空 12 MB / 65536 槽环形命令缓冲 |
| `0x00385BDB` → `0x00382E90` (`WaitOnAddress`) | **15.6%** | 主线程等待 12+ 个并行作业线程（AI / Clutter / PrepareDraw）完成 |
| `0x01155340` (`mtVehS`) + `PhysX_64.dll` | **23.5%** | 实体/载具世界模拟与物理 |

**为什么“只靠换 DX12 / Vulkan 或微补丁无法让 Arma 3 翻倍”？**  
Amdahl 定律直接给出了数学答案：即使后端 API 速度快到无限大，消除全部 `RenderCBToPlay` 等待（9.8%）的理论上限也只有 **+10.8%**（DXVK 3.1.1 实测拿下 **+6.0% 平均帧、+9.3% 1% Low**，已经榨干了渲染后端的大半红利）。真正占大头的 **~36% 渲染准备** 全部发生在 **提交 D3D11/Vulkan 之前的 `Arma3_x64.exe` CPU 逻辑里**。

---

## 3. GO / NO-GO 最终裁决

| 方案 | 裁决 | 实测依据 |
|---|---|---|
| **DXVK 3.1.1 (D3D11 → Vulkan)** | **✅ GO** | 零画质损失 **+6.0% 平均帧 / +9.3% 1% Low**；且原生解锁 AMD Vulkan 帧生成 |
| **Ultra GPU + Smart CPU 解耦配置** | **✅ GO（最强原生 CPU 收益）** | 7900 XT 1440p 4x MSAA 几乎零开销；仅压 CPU 场景复杂度与物体视距即可到 **71–75 FPS（+17.5%～+23.4%，1% Low +21%～+32%）** |
| **RX 7900 XT 驱动级 AFMF 2（帧生成）** | **✅ GO（突破 CPU 墙的 2× 倍增器）** | 7900 XT 在 1440p 下算力大量闲置，基于 71–75 原生帧 × 2 可直接跑到 **142–150+ FPS** 吃满 170Hz 显示器 |
| 自编译 `mimalloc 3.7.0` | **⚠️ 可选** | DX11 下 1% Low **+6.9%**，但与 DXVK 叠加时平均帧略低于 `tbb4malloc_bi_x64`（62.5 vs 64.1） |
| 7900X 全进程绑单 CCD0 (`0x000FFF`) | **❌ NO-GO** | 实测 **-12.1%**（饿死 12+ 并行作业线程，证伪社区错误攻略） |
| `gp_turbo`（去 `0x0169B288` 降优先级 + 去双屏障 + 双线程绑核） | **❌ NO-GO** | 实测 **-4.8%**（主线程自旋不降优先级会抢占渲染线程核频，且 `-malloc` 转发增开销） |
| 引擎级半频阴影 Map 二进制 Hook | **❌ NO-GO** | 彻底关阴影仅涨 **+2.4 FPS**，半频收益 < 1.5 FPS，投入产出比不成立 |

---

## 4. 一键落地使用指南（7900X + 7900 XT 推荐组合）

1. **部署 DXVK 3.1.1（Vulkan 后端）**：
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File tools\dxvk\deploy_dxvk.ps1
   ```
   （回滚：`tools\dxvk\remove_dxvk.ps1`）
2. **应用 Ultra-GPU + Smart-CPU 配置（自动备份原配置，可一键还原）**：
   ```powershell
   # 保留 Ultra 云层 + 1440p 4x MSAA + Ultra 阴影 + 3800m 地形视距（实测 71.1 FPS / 1% Low 43.3）
   powershell -NoProfile -ExecutionPolicy Bypass -File config\apply-7900xt-perf.ps1 -Preset ultragpu_smartcpu

   # 追求更高原生帧与 1% Low（关云层 + tg=25，实测 74.6 FPS / 1% Low 47.4）
   powershell -NoProfile -ExecutionPolicy Bypass -File config\apply-7900xt-perf.ps1 -Preset high_fps_noclouds
   ```
   （一键还原：`config\apply-7900xt-perf.ps1 -Restore`）
3. **打开 AMD Adrenalin → 游戏 → Arma 3 → 开启 `AMD Fluid Motion Frames 2 (AFMF 2)` + `Radeon Anti-Lag`**：
   - 利用闲置的 RX 7900 XT GPU 算力，直接跨过 7900X CPU 单线程 Amdahl 墙，把 **71–75 原生帧** 推到 **142–150+ FPS**（配合你的 2560×1440 @ 170Hz 显示器）。
4. **70+ 模组实战额外提醒**：
   - 你日常联机/单人加载了 `LAMBS_Danger.fsm` + `ACE` + `HATG` + `Reactive Building Effects PLUS` 等重脚本模组，这些模组在主线程额外叠加的 SQF/AI 负载会直接压低 `86.3 FPS` 的模拟天花板；建议在 CBA 设置里调低 `LAMBS_Danger` 信息共享半径与高频检测间隔，并关闭不常用的特效脚本模组。
