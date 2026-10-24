# Arma 3 画面提升工程（graph_pro）

在不改任何游戏资源（模型/贴图/rvmat）的前提下，用「配置 + 运行时常量注入 + 后处理 shader 替换 + Present 旁路」
提升画面，并建立一套可复现的 A/B 测量流程。

---

## 当前生效配置（2026-10-24）

| 层 | 内容 | 关键参数 |
|---|---|---|
| 画质配置 | Arma3.cfg / .Arma3Profile | 贴图 4、AF 16、MSAA 8x、SSAO 8、SMAA、阴影 200m、视距 3800 |
| tonemap | 替换为 ACES v5 | 曝光 0.45、对比 1.12、饱和 1.08 |
| SSAO resolve | 替换为 smoothstep | smoothstep(0.15, 1.0) |
| 环境光 | Map/Unmap 常量注入 | 折中 `0.80 0.90 1.00 1.00`（不冷偏） |
| 曝光钳制 | Map/Unmap · `GP_expo.txt` | size 1696 + **邻槽指纹**；`hi=1.35` |
| 接触阴影 | Present 旁路 | **已搁置**（`kContactShelved`，强制 mode 2） |
| 光向 / CB | `GP_light.txt` + dump/hunt | 基建就绪；接触阴影搁置后优先级低 |
| 材质镜面 | 选择性 boost（默认关） | `GP_spec.txt` = `0 …` |

展示：`demo/` 下 PNG/HTML（大视频不入库）。CPU 无头结论见 [docs/16-cpu-server-soft-levers.md](docs/16-cpu-server-soft-levers.md)。

---

## 能力边界

| 能改 | 手段 | 状态 |
|---|---|---|
| 画质参数 | Arma3.cfg + Profile | ✅ 已打包 |
| 后处理 shader（tonemap / SSAO resolve） | 代理 + 精确替换 | ✅ 已验证 |
| 材质常量（环境光） | 拦截 Map/Unmap | ✅ 已验证 |
| 自动曝光上限 | 拦截 Map/Unmap（cb size 匹配） | ✅ v1 已验收 |
| 屏幕空间接触阴影 | Present + 深度 + 时域/明度保护 | ⚠️ 产品化已接线，**默认关**（待引擎 A/B 后改 mode 0） |
| 自动光向 / CB 普查 | Unmap dump + sun hunt | ✅ 基建就绪，需三情景 dump 绑定 |
| 选择性镜面 / 自适应曝光 | Map/Unmap + 帧亮度 | ✅ 可选预设，默认关 |
| G-buffer 法线 | OMSetRT 全帧普查 | ❌ N1 NO-GO（2026-10-23） |
| 云前干净深度 / stencil 掩码 | DSV 时间线 | ❌ N2 NO-GO（2026-10-23） |
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
| `mission/` | SP 截图任务 `GP_Shot2` / `GP_Min`；无头 DS `GP_ServerTest.Altis` |
| `server/` | DS 配置 + `run-cpu-sample.ps1` / `ab-soft-levers.ps1` |
| `tools/` | 解包、反汇编、图像对比、server Top 命名、simstep 分析 |
| `docs/` | 门禁文档；社区博客见 `docs/blog-arma-optimization.md` |
| `demo/` | A/B 图/HTML（PNG/MP4 不入库） |
| `extract/` | 采样笔记与 A/B JSON；大 `.shdc` / 时间戳 dump 不入库 |

## Git

远程：`origin` → GitHub。忽略：编译产物、日志、`funcs*.bin`、时间戳 dump、demo PNG/MP4、大型 `extract/**/*.shdc`。保留源码、文档、presets、精选 `extract/cpu_samples` 笔记与 `ab_*.json`。

---

## 快速开始

1. 应用画质配置（需先关游戏）
   powershell -File config\apply-quality.ps1

2. 部署注入器 + v1 预设
   powershell -File inject\deploy.ps1

3. 进游戏 → 单人 → 场景 → GP Shot 2（或 `mission\run-cli.ps1`，任务须在游戏目录 `Missions\` + `-init=playMission`）  
   截图：`Documents\Arma 3\Screenshots\`  
   A/B：开/关 `d3d11.dll` 各跑一局（无游戏内滤镜）

4. **无头 CPU（与画面代理互斥）**
   powershell -NoProfile -ExecutionPolicy Bypass -File server\run-cpu-sample.ps1 -SampleMinutes 3
   powershell -NoProfile -ExecutionPolicy Bypass -File server\ab-soft-levers.ps1 -Variant wp_none

5. 调参数（不用重新编译）
   - `GP_amb.txt`：环境光强度 AE强度 R系数 B系数
   - `GP_expo.txt`：`size lo hi [adapt target hiLo hiHi]`
   - `GP_present.txt`：`mode strength radius_m projK frac [alpha luma0 luma1]`
   - `GP_light.txt`：`lx ly lz steps` 或 `auto [steps]`（需 `GP_light_bind.txt`）
   - `GP_spec.txt`：`mode boost [power]`（0=关，1=只 boost 已有 spec）

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
