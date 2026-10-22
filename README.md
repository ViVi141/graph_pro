# Arma 3 画面提升工程（graph_pro）

在不改任何游戏资源（模型/贴图/rvmat）的前提下，用「配置 + 运行时常量注入 + 后处理 shader 替换」
提升画面，并建立一套可复现的 A/B 测量流程。

---

## 当前生效配置（2026-10-22 定稿）

| 层 | 内容 | 关键参数 |
|---|---|---|
| 画质配置 | Arma3.cfg / .Arma3Profile | 贴图 4、AF 16、MSAA 8x、SSAO 8、SMAA、阴影 200m、视距 3800 |
| tonemap | 替换为 ACES v5 | 曝光 0.45、对比 1.12、饱和 1.08 |
| SSAO resolve | 替换为 smoothstep | smoothstep(0.15, 1.0) |
| 材质镜面 | 常量注入 | F0 = 0.12、power = 12 |
| 环境光 | 常量注入 | 强度 0.60 / AE 0.80、色温 R×0.93 B×1.10 |

实测：暗部占比 3.3% → 14%，暗部色温 +0.03 → −0.05（暖阳冷影成立），锐度 0.42 → 2.19。

---

## 能力边界

| 能改 | 手段 | 状态 |
|---|---|---|
| 画质参数 | Arma3.cfg + Profile | ✅ 已打包 |
| 后处理 shader（tonemap / SSAO resolve） | 代理 + 精确替换 | ✅ 已验证 |
| 材质常量（镜面 / 环境光） | 拦截 Map/Unmap | ✅ 已验证 |
| 材质着色器代码 | — | ❌ 编译器在 exe 内 |
| 第三方 AO 库（GFSDK） | 代理 DLL | ❌ 尝试后崩溃，已回滚 |
| 模型 / 贴图 / 植被 / 地形 | — | ❌ 需改资源 |

---

## 目录

| 目录 | 内容 |
|---|---|
| `config/` | 画质配置（original / quality）+ apply / restore |
| `inject/` | d3d11 代理源码、presets、deploy / remove |
| `inject/counter/` | CPU：gpsample / gptimer / gpindirect（源码 + ps1；DLL 需本地编译） |
| `mission/` | 固定机位截图任务 GP_Shot2 |
| `tools/` | 解包、反汇编、图像对比、simstep 静态分析脚本 |
| `docs/` | 设计/门禁文档（含 `13` CPU、`14` World::Simulate） |
| `demo/` | A/B 对比图（PNG 不入库，本地生成） |
| `extract/` | 导出与采样笔记；大 `.shdc` / 时间戳 dump 不入库 |
| `baseline/` `server/` | 基线 RPT 片段、服务端相关 |

## Git

仓库尚未做首次提交。`.gitignore` 已排除：编译产物（`*.dll`/`*.obj`/`*.exe`）、日志、`funcs*.bin`、时间戳采样 dump、demo 截图、大型 `extract/**/*.shdc`。保留源码、文档、presets、精选 `extract/cpu_samples/*_notes` / `*_summary` / deep xref。

---

## 快速开始

1. 应用画质配置（需先关游戏）
   powershell -File config\apply-quality.ps1

2. 部署注入器 + 预设
   powershell -File inject\deploy.ps1

3. 进游戏 → 单人游戏 → 场景 → GP Shot 2 → 等 35 秒 → Esc
   截图落在 Documents\Arma 3\Screenshots\gp_r_*.png

4. 调参数（不用重新编译）
   inject\set-spec.ps1 -Scale 0.12 -Power 12
   GP_amb.txt 格式：环境光强度 AE强度 R系数 B系数

---

## 回滚

| 目标 | 操作 |
|---|---|
| 移除注入 | powershell -File inject\remove.ps1 |
| 关闭 tonemap | 把 GP_replace.txt 改名 .off |
| 关闭镜面 | inject\set-spec.ps1 -Scale 0 |
| 恢复画质配置 | config\restore.ps1 |

---

## 风险

- 注入器是 d3d11 代理，只建议单人/私有服使用
- 已回滚 GFSDK_SSAO 代理（会导致崩溃），当前游戏目录是原版 DLL
- A3 每次更新后着色器 size/crc 会变，替换表需重新采样
