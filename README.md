# graph_pro — Arma 3 rendering & CPU research notes

> **A research notebook, not a mod release.** Everything here is for
> single-player, the editor, or a private server with BattlEye disabled. It is
> not a cheat, not a BattlEye bypass, and not intended for multiplayer.

[中文](#中文) · [English summary](#english-summary) · [Docs index](docs/README.md) · [Privacy](PRIVACY.md) · [License](LICENSE)

---

## English summary

`graph_pro` is a set of reverse-engineering notes and measurement tools for
Arma 3 (Real Virtuality 4, D3D11). It explores what can and cannot be changed
without editing game assets:

- an **archived** `d3d11.dll` proxy (classic line, `archive/legacy-proxy/`) that
  replaced post-process shaders by exact `(size, crc)` fingerprints and injected
  material/post-process constants; kept for the probe evidence, no longer maintained;
- an offline A/B pipeline for colour, sharpness, exposure and pass-order
  analysis;
- a separate CPU-attribution track (`gpsample` / `gpwatch` / `gpmeasure`) that
  measures headless-server and client hotspots;
- the maintained delivery line under `inject/universal/`: a chain-loading
  `d3d11.dll` that can sit on top of DXVK 3.1.1 (Vulkan) with a native-DX11
  fallback, no Present hook, and a four-tier graphics pack.

The most reusable output is not the injector: it is the **evidence** — which
hooks work, which are structurally impossible, and which "improvements" turned
out to be no-ops or regressions. The classic line was archived on 2026-11-23
because Universal covers every product capability; only probe evidence remains.
The current status is deliberately honest: only AgX tonemapping and
ambient/colour-temperature injection have quantified before/after gains; several
other features are wired but unproven, and contact shadows are shelved.

The repo contains **no game assets** and no personal profiles. Some lab scripts
use `<ARMA3>` / `<REPO>` placeholders; the maintained entry points read
`ARMA3_DIR` (see [Quick start](#quick-start)).

---

## 中文

### 这是什么

一个围绕 Arma 3（RV4 / D3D11）的**逆向与测量仓库**，两条活跃线 + 一条已归档的历史线：

| 线 | 目标 | 主要产物 |
|---|---|---|
| Universal 产品线（活跃） | 把注入做成可安装/可回滚的产品 | `inject/universal/`：DXVK 3.1.1 链式代理 + 四档画质包 + 安装/重置器 |
| CPU 归因（活跃） | 回答“帧时间到底花在哪” | `gpsample` / `gpwatch` / `gpmeasure` + 软杠杆表 |
| 经典画面旁路（已归档） | 回答“后处理/常量层还能改什么” | `archive/legacy-proxy/`：代理 + DXBC 载荷 + `GP_*.txt` 预设（只读） |

**它不是**：外挂、BattlEye 绕过、多人可用工具、完整渲染器重写；Universal
的一键安装只是布置文件/备份配置，不等于“画质自动变好”。
**它是**：一套可复现的实验记录，包括大量“此路不通”的负面结论。

### 当前状态：经典线（2026-10-28，已归档）

> 经典画面旁路线已于 2026-11-23 归档到 `archive/legacy-proxy/`。下表是该线停更时的
> 实测结论，保留为历史与证据索引；Universal 线的状态见下一节。

| 能力 | 默认 | 证据 | 判定 |
|---|---|---|---|
| 画质配置 | 开 | 锐度 0.42 → 0.84（中档）/ 2.19（拉满）；FPS ~99 → 95.8 / 49.8（参考核显） | ✅ 有效，但不是免费 |
| AgX tonemap | 开 | 对比 σ 0.116→0.142；暗部 3.3%→14%；暗部 R−B +0.032→−0.050 | ✅ 唯一有量化前后对照的成像改动 |
| 环境光 / 色温 | 开 | 224 B 材质 CB；色调定稿 | ✅ 有效；只有全局常量，无半球梯度 |
| SSAO resolve | 开 | 日志 `SSAO FINAL REPLACED`；无 A/B | ⚠️ 已接线，收益未证 |
| 曝光钳制 | 开（1.35） | 30 万行日志：`f150` 99.9% 恒 1.0；`CLAMPED` 仅 384 次 | ⚠️ 机制成立，常规帧空操作 |
| 自适应 AgX | 关 | `blown≈0.004` < 阈值 0.02 | ⚠️ 从未触发 |
| 选择性镜面 | 关 | 草/云 +2.79，负收益 | ❌ 已判负 |
| 接触阴影 | 强制关 | 文档 0.49 vs 复现 0.023；黑天 | ⛔ 搁置 |
| FSR1 放大 | 关 | 最新探针：1440×810→1920×1080，`psLen=5596`，`crc=B682EAC0` | 🔬 指纹已对上，未做 A/B |
| DLSS 5 / Feeder | — | 需 RTX 50 + ReShade 深度；联机深度会被解绑 | 🔬 外部路线，暂不投入 |
| CPU 软杠杆 | — | 巡逻 `2.69·U`、站岗 `1.02·U`，移动/站岗 ≈2.63× | ✅ 有量化，可复用于任务设计 |

完整评审（代码、文档漂移、缺陷清单）见 [docs/21-project-review.md](docs/21-project-review.md)。
按时间排列的实验日志见 [docs/RESULTS.md](docs/RESULTS.md)。

### Universal 产品线（2026-11-23）

`inject/universal/` 是当前唯一在维护的注入交付线：`d3d11.dll` 代理链式加载 DXVK 3.1.1
（Vulkan），保留原生后端自动回退，**不钩 Present**（与 AMD AFMF 2、Steam
覆盖层兼容），并提供四档画质包与一键安装/重置。经典旁路线已于 2026-11-23 归档
（[archive/legacy-proxy/ARCHIVED.md](archive/legacy-proxy/ARCHIVED.md)），其探针与
预设不再随仓库更新。

- **性能有量化对照**：14 轮控制变量 A/B（`docs/20-route2`）在 7900X + 7900 XT /
  1440p / YAAB 下测到纯 DXVK **+6.0%**、均衡档 **+17.5%**、极限帧率 **+23.4%**
  （1% Low 分别 +9.3% / +20.9% / +32.2%）。
- **画质包尚未量化**：AgX v4.2、GGX PBR、SSGI、3-Pass RTGI、HDR Bloom 目前只有
  启动日志与截图链，没有 `docs/21 §3` 口径的画质 A/B；按本仓库的标准归类为
  “已接线、未量化”。
- **入口**：[inject/universal/README.txt](inject/universal/README.txt)（四档说明）、
  `GraphPro_Manager.bat`（交互菜单）、`install.ps1` / `uninstall.ps1`。
- **只读验证**：`tools/verify_universal.ps1` 检查部署身份、哈希与日志命中，不启动游戏。
- **经典线已归档**：若你的游戏目录里仍部署着经典代理，先运行
  `archive\legacy-proxy\inject\remove.ps1`，再运行 `install.ps1`。Universal 是唯一
  在维护的线，不需要再切回经典线。

### 已知边界

- 不改模型、贴图、rvmat、地形；因此 GI、材质粗糙度、接触阴影的结构问题解决不了。
- 材质常量是**每材质一个值**，做不出“朝天的面偏蓝、墙根更暗”的逐像素梯度。
- 替换键是游戏 shader 的 `(size, crc)`；A3 更新后可能**静默失效**。Universal
  线在创建 50 个 PS 仍无命中时会写警告日志；已归档的经典线没有版本自检。
- Universal 与已归档的经典代理都写游戏目录的 `d3d11.dll`，**互斥**；从经典线
  切换时先跑 `archive\legacy-proxy\inject\remove.ps1` 再安装 Universal。
- Universal 画质包（AgX v4.2 / GGX PBR / SSGI / RTGI / Bloom）目前只有启动日志
  与截图链，没有画质 A/B，按本仓库标准属“已接线、未量化”。
- CPU 结论来自单机、单场景、小样本；趋势可信，绝对系数不要外推。
- 代理只应在单人/私有、无 BattlEye 的环境使用。

---

## 仓库结构

| 目录 | 内容 |
|---|---|
| `config/` | 画质模板 + `apply-quality.ps1` / `restore.ps1`（只改图形键，备份原 profile） |
| `inject/` | `universal/`（当前交付线：DXVK 链式代理 + 四档画质包 + 安装器）、`counter/`（CPU 采样器）、`vcvars64_locate.bat` |
| `archive/legacy-proxy/` | 经典画面旁路线（代理源码、预设、载荷、探针工具）：2026-11-23 归档，只读 |
| `mission/` | 单人截图任务 `GP_Min` / 无头 DS 任务 `GP_ServerTest`；部署脚本**不启动**客户端 |
| `server/` | 无头 DS 配置 + CPU 采样/A-B 脚本 |
| `mod/` | `@gpmat` 单材质 rvmat 覆盖（A/B 对照源码） |
| `tools/` | 构建、验证（`universal_smoke_test.py` / `verify_universal.ps1`）、图像分析、PBO/shdc 逆向、CPU 归因；`tools/gpcpu/` 为独立采样器源码；经典线工具已归档 |
| `docs/` | 22 篇编号文档 + `RESULTS.md` + 博客；入口见 [docs/README.md](docs/README.md) |
| `extract/` | 精选采样数据、RDC 笔记、A/B JSON；大文件不入库 |
| `demo/` | 本地 A/B 图/HTML（PNG/MP4 被 `.gitignore` 排除，约 1.2 GB） |
| `dist/` | 本地打包产物（DXVK + 二进制 + 安装器，**不入库**；`install.ps1` 从这里取文件） |

---

## Quick start

### 0. 环境

- Windows 10/11，Arma 3（RV4，D3D11）
- Visual Studio 2022 Build Tools + Windows SDK（编译代理与 fxc）
- Python 3.11+；`pip install -r requirements.txt`
- 设置游戏目录：

```powershell
$env:ARMA3_DIR = "C:\Program Files (x86)\Steam\steamapps\common\Arma 3"
```

### 1. 编译（Universal）

```powershell
cd inject\universal
build.bat                       # -> inject\universal\d3d11.dll + DXBC 载荷
cd ..\..
```

### 2. 安装 / 回滚（Universal 画面线）

```powershell
powershell -File inject\universal\install.ps1 -Graphics agx -Tier auto   # 或双击 GraphPro_Manager.bat
powershell -File tools\verify_universal.ps1                              # 只读检查部署/日志，不启动游戏
powershell -File inject\universal\uninstall.ps1                          # 完整卸载并还原备份
```

`-Graphics` 可选 `off`（纯 DXVK）/ `agx` / `agx_lite` / `ssgi` / `ultra`；`-Tier`
可选 `none|auto|high|high_fps|mid|igpu`。安装器会先把 `Arma3.cfg` 与全部
`.Arma3Profile` 备份到游戏目录 `_gp_universal_backup`，再修改图形键；它不会启动
游戏。**仓库里没有任何启动客户端的脚本。**

**经典线（已归档，只读复现，不要部署）：**

```powershell
cd archive\legacy-proxy\inject\proxy
build.bat                                    # -> 归档内 d3d11.dll
cd ..\..\..\..
python archive\legacy-proxy\tools\proxy_smoke_test.py
```

经典线的着色器构建契约：tonemap/SSAO 用 **`ps_4_0` 且不带 `/O3`**，可逐位复现已出货的
`GP_ssao.dxbc`（sha256 `5A2370A56BA8`）和 `GP_tonemap.dxbc`（`8BD7FDE4571B`）。
把 SSAO 改成 `ps_5_0` 会静默改变 AO 输出，不要“现代化”。归档内的
`tools/build_tonemap.ps1` 仍按此契约复现。

### 3. 画质配置

```powershell
powershell -File config\apply-quality.ps1   # 备份并只改图形键
powershell -File config\restore.ps1         # 恢复最近一次备份
```

### 4. 无头 CPU（与画面代理互斥）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File server\run-cpu-sample.ps1 -SampleMinutes 3
powershell -NoProfile -ExecutionPolicy Bypass -File server\ab-soft-levers.ps1 -Variant wp_none
```

### 5. 离线验证

```powershell
python tools\universal_smoke_test.py                     # Universal 代理：DllMain 无 IO + 首次建链读配置
python tools\make_manifest.py                            # 刷新 dist/ 后生成发布清单（commit + 逐文件 sha256）
python archive\legacy-proxy\tools\proxy_smoke_test.py    # 经典代理（先编译归档内 d3d11.dll）
python archive\legacy-proxy\tools\probe_smoke_test.py    # 放大探针 + 颜色空间回读
python archive\legacy-proxy\tools\analyze_capture.py "$env:ARMA3_DIR"
```

`universal_smoke_test.py` 需要先编译 `inject\universal\build.bat`；归档 smoke test
需要先编译 `archive\legacy-proxy\inject\proxy\build.bat`。它们都用仓库自带的 DXBC
载荷做替换测试，不依赖游戏目录。

---

## 文档入口

先看：

1. [docs/21-project-review.md](docs/21-project-review.md) — 外部视角的工程评审与缺陷清单
2. [docs/08-capabilities.md](docs/08-capabilities.md) — 能改 / 不能改的清单
3. [docs/RESULTS.md](docs/RESULTS.md) — 按时间排列的实测记录

按主题：

- 渲染管线与注入点：[01](docs/01-render-interaction-map.md)、[03](docs/03-postprocess-primer.md)、[15](docs/15-render-pipeline-injection-map.md)
- 注入方案与可行性：[02](docs/02-injection-plan.md)、[10](docs/10-dll-options.md)、[12](docs/12-pipeline-feasibility.md)
- CPU 归因：[13](docs/13-cpu-hotspot.md)、[16](docs/16-cpu-server-soft-levers.md)、[17](docs/17-ai-wp-cost-table.md)、[18](docs/18-mission-cpu-estimate.md)、[20](docs/20-client-cpu-forensics.md)
- DXVK / Universal 线：[20-route2-7900x-7900xt-perf.md](docs/20-route2-7900x-7900xt-perf.md)、[inject/universal/README.txt](inject/universal/README.txt)
- 着色器目录与重写：[22-shader-catalog.md](docs/22-shader-catalog.md)（9061 个 blob / 2585 个着色器、指纹审计、DXBC→HLSL）
- 社区版解释：[blog-arma-optimization.md](docs/blog-arma-optimization.md)

---

## 隐私与数据

- 跟踪文件中没有个人用户名、绝对路径、邮箱或 profile；路径以 `<ARMA3>` /
  `<REPO>` 等占位符表示，维护中的入口读 `ARMA3_DIR`。
- 个人 `.Arma3Profile`、备份、RPT、机器标识字段已移除；`apply-quality.ps1`
  只改活动 profile 的图形键，并在修改前备份。
- `demo/` 的截图/视频不入库；如果你要发布图片，先检查 HUD、玩家名、服务器名。
- 无遥测、无网络上报。详见 [PRIVACY.md](PRIVACY.md)。

## License

代码 MIT；文档 CC BY 4.0。游戏资源（PBO、DXBC、贴图等）不随仓库分发。
Arma 3 / Bohemia Interactive 是其各自权利人的商标；本项目与 BI 无关联。
详见 [LICENSE](LICENSE) 与 [NOTICE.md](NOTICE.md)。

## Disclaimer

本项目用于单人/编辑器/私有服务器的研究与测量。**不要**在启用 BattlEye 的
服务器上使用注入器；由此产生的封禁、崩溃、存档损坏等风险由使用者承担。
仓库不提供任何反作弊绕过、破解或多人优势功能。
