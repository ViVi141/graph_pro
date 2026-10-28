# Arma 3 画面提升工程（graph_pro）

在不改任何游戏资源（模型/贴图/rvmat）的前提下，用「配置 + 运行时常量注入 + 后处理 shader 替换 + Present 旁路」
提升画面，并建立一套可复现的 A/B 测量流程。

---

## 当前生效配置（2026-10-24）

| 层 | 内容 | 关键参数 |
|---|---|---|
| 画质配置 | Arma3.cfg / .Arma3Profile | 贴图 4、AF 16、MSAA 8x、SSAO 8、SMAA、阴影 200m、视距 3800 |
| tonemap | 替换为 **AgX**（`GP_tonemap_agx.dxbc`） | E 0.55 / K 1.40 / S 1.20；ACES 为备选（`GP_replace_aces.txt`） |
| SSAO resolve | 替换为 smoothstep | smoothstep(0.15, 1.0) |
| 环境光 | Map/Unmap 常量注入 | 折中 `0.80 0.90 1.00 1.00`（不冷偏） |
| 曝光钳制 | Map/Unmap · `GP_expo.txt` | size 1696 + **邻槽指纹**；`hi=1.35`；见 §曝光实测 |
| 自适应 AgX | `GP_adapt.txt`（默认**关**） | 开则每 15 帧全幅回读；`c[80].w==1.0` 才接管 |
| 接触阴影 | Present 旁路 | **已搁置**（`kContactShelved`，强制 mode 2） |
| 光向 / CB | `GP_light.txt` + dump/hunt | 基建就绪；接触阴影搁置后优先级低 |
| 材质镜面 | 选择性 boost（默认关） | `GP_spec.txt` = `0 …` |

展示：`demo/` 下 PNG/HTML（大视频不入库）。CPU 无头结论见 [docs/16-cpu-server-soft-levers.md](docs/16-cpu-server-soft-levers.md)。

### 曝光钳制实测注记（2026-10-28 复核）

30 万行历史 `GP_shader.log` 里，指纹通过的 `f150` **99.9% 恒为 1.0**（169,790 / 237,720），
`exposure CLAMPED` 仅出现 384 次（几乎全是 `1.6399 → 1.35`）。即 `hi=1.35` 在绝大多数场景是**空操作**。

- 机制本身仍成立（`fp=1` + `fp-ok` 日志可验）。
- 但它只在 AE 短时冲高时生效，不是常驻压暗旋钮。
- 想确认是否还在工作：把 `GP_expo.txt` 临时改为 `1696 0 1.05`，跑一局看 `CLAMPED` 比例。

---

## 构建 shader 载荷

    powershell -File tools\build_tonemap.ps1

四个产物统一用 **`ps_4_0` 且不带 `/O3`** —— 这个组合能逐位复现已出货的
`GP_ssao.dxbc`（sha256 `5A2370A56BA8`）与 `GP_tonemap.dxbc`（`8BD7FDE4571B`）。
改成 `ps_5_0` 会把 SSAO 的采样指令变成 `sample_indexable`/仅 `r0.x`，**静默改变 AO 输出**，勿随意"现代化"。

---

## 能力边界

| 能改 | 手段 | 状态 |
|---|---|---|
| 画质参数 | Arma3.cfg + Profile | ✅ 已打包 |
| 后处理 shader（tonemap / SSAO resolve） | 代理 + 精确替换 | ✅ 已验证 |
| 材质常量（环境光） | 拦截 Map/Unmap | ✅ 已验证 |
| 自动曝光上限 | 拦截 Map/Unmap（cb size 匹配） | ✅ v2 已验收（机制成立；见下方实测注记） |
| 屏幕空间接触阴影 | Present + 深度 + 时域/明度保护 | ⛔ **已搁置**（`kContactShelved`，强制 mode 2） |
| 自动光向 / CB 普查 | Unmap dump + sun hunt | ✅ 基建就绪，需三情景 dump 绑定 |
| 选择性镜面 / 自适应曝光 | Map/Unmap + 帧亮度 | ✅ 可选预设，默认关 |
| 自适应 AgX（c[80]） | 帧亮度回读 → tonemap | ⚠️ 已接线，默认关（开则每 15 帧全幅回读） |
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
| `mod/` | `@gpmat`：单材质 rvmat 覆盖（`hbarrier` specular）作 A/B 对照 |
| `tools/` | 解包、反汇编、图像对比、server Top 命名、simstep 分析；shader 构建见 `build_tonemap.ps1` |
| `tools/gpcpu/` | CPU 归因工具（gpwatch / gpmeasure / gpgate）；说明见该目录 README |
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
