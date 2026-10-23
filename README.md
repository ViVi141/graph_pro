# Arma 3 画面提升工程（graph_pro）

在不改任何游戏资源（模型/贴图/rvmat）的前提下，用「配置 + 运行时常量注入 + 后处理 shader 替换 + Present 旁路」
提升画面，并建立一套可复现的 A/B 测量流程。

---

## 当前生效配置（2026-10-23 · 屏幕空间旁路 v1）

| 层 | 内容 | 关键参数 |
|---|---|---|
| 画质配置 | Arma3.cfg / .Arma3Profile | 贴图 4、AF 16、MSAA 8x、SSAO 8、SMAA、阴影 200m、视距 3800 |
| tonemap | 替换为 ACES v5 | 曝光 0.45、对比 1.12、饱和 1.08 |
| SSAO resolve | 替换为 smoothstep | smoothstep(0.15, 1.0) |
| 环境光 | Map/Unmap 常量注入 | 强度 0.60 / AE 0.80、色温 R×0.93 B×1.10 |
| 曝光钳制 | Map/Unmap · `GP_expo.txt` | size **1696**、f150=`c[37].z`、`lo=0` `hi=1.10` |
| 接触阴影 | Present pass · `GP_present.txt` | **默认 mode 2 关闭**（云层 d≈0.95–0.99 会误伤天空；需试验时再改 mode 0） |
| 材质镜面 | — | **关闭**（`GP_spec.txt` = `0 0`） |

展示图：`demo/ab-side-by-side.png`（ACES+amb）、`demo/expo-ab-compare.png`、`demo/ab-contact-off-vs-on.png`。

---

## 能力边界

| 能改 | 手段 | 状态 |
|---|---|---|
| 画质参数 | Arma3.cfg + Profile | ✅ 已打包 |
| 后处理 shader（tonemap / SSAO resolve） | 代理 + 精确替换 | ✅ 已验证 |
| 材质常量（环境光） | 拦截 Map/Unmap | ✅ 已验证 |
| 自动曝光上限 | 拦截 Map/Unmap（cb size 匹配） | ✅ v1 已验收 |
| 屏幕空间接触阴影 | Present + 深度 SRV | ✅ v1 默认开 |
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

2. 部署注入器 + v1 预设
   powershell -File inject\deploy.ps1

3. 进游戏 → 单人游戏 → 场景 → GP Shot 2 → 等约 **10 秒**（脚本相机俯视）→ Esc  
   截图：`Documents\Arma 3\Screenshots\gp_r_baseline.png`（应为城镇俯视，不是第一人称草丛）  
   A/B：开/关 `d3d11.dll` 各跑一局（无游戏内滤镜）

4. 调参数（不用重新编译）
   - `GP_amb.txt`：环境光强度 AE强度 R系数 B系数
   - `GP_expo.txt`：`size lo hi`
   - `GP_present.txt`：`mode strength radius_m projK frac`（热重读）
   - `GP_light.txt`：屏幕空间光向 x y z steps

---

## 回滚

| 目标 | 操作 |
|---|---|
| 移除注入 | powershell -File inject\remove.ps1 |
| 关闭 tonemap | 把 GP_replace.txt 改名 .off |
| 关闭接触阴影 | 复制 `presets\GP_present_off.txt` → 游戏目录 `GP_present.txt` |
| 关闭曝光钳制 | 删除或改名游戏目录 `GP_expo.txt` |
| 紧曝光实验 | 复制 `presets\GP_expo_tight.txt` → `GP_expo.txt` |
| 恢复画质配置 | config\restore.ps1 |

---

## 风险

- 注入器是 d3d11 代理，只建议单人/私有服使用
- 已回滚 GFSDK_SSAO 代理（会导致崩溃）
- A3 每次更新后着色器 size/crc 与 expo 缓冲 size 会变，替换表需重新采样
