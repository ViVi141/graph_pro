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

- a `d3d11.dll` proxy that replaces post-process shaders by exact
  `(size, crc)` fingerprints and injects material/post-process constants;
- an offline A/B pipeline for colour, sharpness, exposure and pass-order
  analysis;
- a separate CPU-attribution track (`gpsample` / `gpwatch` / `gpmeasure`) that
  measures headless-server and client hotspots.

The most reusable output is not the injector: it is the **evidence** — which
hooks work, which are structurally impossible, and which "improvements" turned
out to be no-ops or regressions. The current status is deliberately honest:
only AgX tonemapping and ambient/colour-temperature injection have quantified
before/after gains; several other features are wired but unproven, and contact
shadows are shelved.

The repo contains **no game assets** and no personal profiles. Some lab scripts
use `<ARMA3>` / `<REPO>` placeholders; the maintained entry points read
`ARMA3_DIR` (see [Quick start](#quick-start)).

---

## 中文

### 这是什么

一个围绕 Arma 3（RV4 / D3D11）的**逆向与测量仓库**，两条互相独立的线：

| 线 | 目标 | 主要产物 |
|---|---|---|
| 画面旁路 | 回答“后处理/常量层还能改什么” | `d3d11.dll` 代理 + DXBC 载荷 + `GP_*.txt` 预设 |
| CPU 归因 | 回答“帧时间到底花在哪” | `gpsample` / `gpwatch` / `gpmeasure` + 软杠杆表 |

**它不是**：外挂、BattlEye 绕过、多人可用工具、完整渲染器重写、一键画质包。
**它是**：一套可复现的实验记录，包括大量“此路不通”的负面结论。

### 当前状态（2026-10-28）

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

### 已知边界

- 不改模型、贴图、rvmat、地形；因此 GI、材质粗糙度、接触阴影的结构问题解决不了。
- 材质常量是**每材质一个值**，做不出“朝天的面偏蓝、墙根更暗”的逐像素梯度。
- 替换键是游戏 shader 的 `(size, crc)`；A3 更新后可能**静默失效**，仓库没有版本自检。
- CPU 结论来自单机、单场景、小样本；趋势可信，绝对系数不要外推。
- 代理只应在单人/私有、无 BattlEye 的环境使用。

---

## 仓库结构

| 目录 | 内容 |
|---|---|
| `config/` | 画质模板 + `apply-quality.ps1` / `restore.ps1`（只改图形键，备份原 profile） |
| `inject/` | `proxy/`（d3d11 代理源码）、`presets/`、`counter/`（CPU 采样器）、`present/` |
| `mission/` | 单人截图任务 `GP_Min` / 无头 DS 任务 `GP_ServerTest`；部署脚本**不启动**客户端 |
| `server/` | 无头 DS 配置 + CPU 采样/A-B 脚本 |
| `mod/` | `@gpmat` 单材质 rvmat 覆盖（A/B 对照源码） |
| `tools/` | 构建、验证、图像分析、PBO/shdc 逆向、CPU 归因；`tools/gpcpu/` 为独立采样器源码 |
| `docs/` | 21 篇编号文档 + `RESULTS.md` + 博客；入口见 [docs/README.md](docs/README.md) |
| `extract/` | 精选采样数据、RDC 笔记、A/B JSON；大文件不入库 |
| `demo/` | 本地 A/B 图/HTML（PNG/MP4 被 `.gitignore` 排除，约 1.2 GB） |

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

### 1. 编译

```powershell
cd inject\proxy
build.bat                       # -> inject\proxy\d3d11.dll
cd ..\..
powershell -File tools\build_tonemap.ps1   # -> inject\presets\GP_*.dxbc
powershell -File tools\build_present.ps1   # optional: Present-pass payloads
```

着色器构建契约：tonemap/SSAO 用 **`ps_4_0` 且不带 `/O3`**，可逐位复现已出货的
`GP_ssao.dxbc`（sha256 `5A2370A56BA8`）和 `GP_tonemap.dxbc`（`8BD7FDE4571B`）。
把 SSAO 改成 `ps_5_0` 会静默改变 AO 输出，不要“现代化”。

### 2. 部署 / 回滚（画面线）

```powershell
powershell -File inject\deploy.ps1      # 复制 d3d11.dll + 默认预设
powershell -File inject\remove.ps1      # 移除代理与 GP_* 文件
powershell -File inject\toggle.ps1 -Off # 暂时关闭（保留 d3d11.dll.off）
```

**仓库里没有任何启动客户端的脚本。** 部署完请自己启动 Arma 3。
预设可在游戏运行时热改（除 `GP_adapt` 外约 60 帧重读）；删除文件即回落默认。

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
python tools\proxy_smoke_test.py      # 真 D3D11 设备，不启动游戏
python tools\probe_smoke_test.py      # 放大探针 + 颜色空间回读
python tools\analyze_capture.py "$env:ARMA3_DIR"   # 解释探针抓帧
```

`proxy_smoke_test.py` 需要先编译 `inject\proxy\d3d11.dll`；它用仓库自带的
DXBC 载荷做替换测试，不依赖游戏目录。

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
