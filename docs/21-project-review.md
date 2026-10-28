# 21 · 项目评审（2026-10-28）

> **范围**：`inject/proxy/d3d11_proxy.cpp` 全文（2,841 行）、`inject/` 全部着色器与预设、`config/`、`server/`、`mission/`、`inject/counter/`、`tools/gpcpu/`、`tools/` 抽样，以及 `docs/` 全部 22 篇。
> **方法**：逐文件阅读 + 两次独立子审计（工具面 / 文档面）+ 可复现验证（Python 导入、DXBC 哈希、构建脚本、`git ls-files`）。
> **原则**：只写能指到 `file:line` 的结论；推断一律标记「推断」，没测过的写「未验证」。
> 本文是**外部视角的工程评审**，不替代 README / RESULTS 里的实测记录。

---

## 0. 结论

1. **这个仓库最值钱的不是"画面提升"，而是"证据链"。** 注入点地图、A/B 口径、以及一大批带数据的负面结论（G-buffer 无、干净深度无、逐物体几何不可钩、镜面覆写负收益、setSkill 无效），是可以直接复用的资产。
2. **但出货面已经缩到很小。** 注入侧默认开启的只有四项：AgX tonemap、环境光/色温、曝光钳制、SSAO resolve。其中曝光钳制 99.9% 是空操作、SSAO 只有"替换成功"没有前后对照，所以**默认配置下真正改变像素的只剩 AgX + 环境光**；镜面 boost 已判负收益，接触阴影搁置，自适应 AgX 从未触发。
3. **代码能用，但处于"单人研究脚本"水平，不是"可分发工具"水平。** 三个真实缺陷（DllMain 里做文件 IO、永久持有 backbuffer 引用、跨线程无同步的全局表）任何一个都可能在实际使用中变成死锁 / 改分辨率失败 / 偶发错值。
4. **文档开始"自我覆盖"**：同一文件里既有"已搁置（强制 mode 2）"，又有"待 A/B 通过后把 mode 0 打开"；`RESULTS.md` 里有一条 2026-10-28 的修复记录（`Hook_Map` 加 ByteWidth 缓存）在代码和 git 历史里**都不存在**。这类漂移比 bug 更难发现，也更伤可信度。
5. **当前主要风险不是技术，是维护成本。** A3 每次更新，`size/crc`、`expo size`、RVA 全部失效；而仓库没有版本自检、没有回归测试、没有 CI，全部靠人肉重采。
6. **建议把"研究线"和"交付线"分开**：交付线只留 AgX + 环境光，补齐安装 / 自检 / 回滚；研究线一次只开一条（见 §9）。

---

## 1. 项目全景

**目标**：在不改任何模型 / 贴图 / rvmat 的前提下提升 Arma 3 画面，并建立可复现的 A/B 测量流程。

**两条腿**（互相独立，共用同一套测量习惯）：

| 线 | 目的 | 主要产物 | 状态 |
|---|---|---|---|
| 画面旁路 | 改"算完长什么样" | `d3d11.dll` 代理 + DXBC 载荷 + 预设 | 出货（AgX + amb） |
| CPU 归因 | 回答"到底慢在哪" | `gpsample` / `gpwatch` / `gpmeasure` + 软杠杆表 | 已有量化结论 |

**规模**：369 个跟踪文件 / `.git` 4.1 MB / 工作区 1.3 GB（其中 `demo/` 1.2 GB，未跟踪）；代理 2,841 行单文件；`tools/` 134 个 Python；文档 22 篇。

---

## 2. 架构与数据流

```
Arma3.cfg / .Arma3Profile        ← config/ (纯文本替换)
        │
   游戏进程
        ├── d3d11.dll 代理 (inject/proxy)
        │     ├─ D3D11CreateDevice*   → 设备/上下文/交换链钩
        │     ├─ CreatePixelShader    → (size,crc) 命中即换 DXBC      [tonemap / SSAO / FSR1]
        │     ├─ Map/Unmap            → 常量注入                        [ambient / AE / expo / spec]
        │     ├─ OMSetRenderTargets   → 深度候选 / MRT 普查             [探针]
        │     ├─ Draw* / ExecList     → PP 与几何分类、放大探针          [探针]
        │     └─ Present              → 颜色拷贝 + 全屏 pass            [接触阴影，已搁置]
        │
        └── presets/GP_*.txt          ← 运行时热读（60 帧一次）
```

**设计上值得肯定的三点**：

- 替换以**原件指纹**（`size` + `crc`）为键，而不是"猜 pass 顺序"，因此能精确命中且可回退；
- `Map/Unmap` 注入前有**邻槽指纹**（`c[37]`+`c1.w`+`c0`）与有限值检查，这是踩过 `1696` 共享 size 误伤后加的正确防御（`d3d11_proxy.cpp:1203-1219`、`1255-1270`）；
- 关闭语义统一走"文件缺失即关闭"，而且 `expo` / `light` 都修过"删文件不回滚"的 bug（`2286-2299`、`2317-2324`）。

---

## 3. 出货能力核对

| 能力 | 机制 | 判定 | 证据 | 备注 |
|---|---|---|---|---|
| AgX tonemap | `5860/42670B06` → `GP_tonemap_agx.dxbc` | ✅ **有效** | 三方对比指标（`RESULTS.md` §2026-10-22 05:20） | 唯一有量化前后对照的成像改动 |
| 环境光 / 色温 | 224 B 材质 CB `f[36..38]` / `f[4..6]` | ✅ **有效** | 色调定稿（暗部 R−B −0.05） | 全局常量，做不出梯度 |
| SSAO resolve | 反汇编指纹 → `smoothstep(0.15,1.0)` | ⚠️ **已替换，无对照** | `docs/08:58` 只写"已验证" | 没有前后图/指标；`GP_ssao.dxbc` 780 B |
| 曝光钳制 | 1696 B + 指纹 → `f150` | ⚠️ **机制成立，效果≈0** | 30 万行日志：`f150` 99.9% = 1.0000 | `hi=1.35` 绝大多数帧是空操作 |
| 自适应 AgX | `c[80].w==1.0` 哨兵 | ⚠️ **从未触发** | `blown≈0.004` < 阈值 `0.02` | 默认关；开了也几乎不动 |
| 选择性镜面 | 224 B `f[24..26]` | ❌ **负收益** | `RESULTS.md` 2026-10-22 05:05 | `==0` 是美术意图，不是缺数据 |
| 接触阴影 | Present + 深度 SRV | ⛔ **搁置** | `kContactShelved`（`110`） | 代码/HLSL 保留，**时域已成死代码**（见 §4） |
| 超分 FSR1 | 替换 stretch pass | 🧪 **探针 + 替换件已写** | `fsr1_easu.hlsl`、`GP_replace_fsr1.txt` | 没有 `GP_upscale.txt` 实测报告；画质收益未证 |
| CPU 软杠杆 | `gpsample exe_fn` | ✅ **有量化** | `exe_fn≈2.69U−28.6`（R²0.98） | 与画面线独立，可直接给别人用 |

**一句话**：`README.md` 的能力表把"机制跑通"和"画面变好"混在同一列。建议拆成两列——**"已接线"** 与 **"已量化收益"**，后者目前只有 AgX 和 amb。

---

## 4. 代码评审

> 下面 §4/§5 的行号对应**修复前**的 `3a20697`（2026-10-28 下午）。修复内容见 §11；
> 代码改动后行号会偏移，按函数名搜索即可。

### 4.1 P0：会真出问题的

| # | 问题 | 位置 | 后果 | 修法 |
|---|---|---|---|---|
| 1 | **DllMain 里做文件 IO**：`LoadConfig()` 打开 10+ 个文件并写日志 | `2837-2841` | 加载器锁下 IO，极端情况死锁/卡启动 | 改为首个 `D3D11CreateDevice` 里 lazy init |
| 2 | **永久持有 backbuffer 引用**：`GetBuffer(0)` 的引用存进 `g_bbTex`，且 `g_bbRTV` 也引用同一资源，从不释放 | `2232`、`2277` | DXGI 要求 `ResizeBuffers` 前释放所有 backbuffer 引用 → 改分辨率/切全屏可能失败或黑屏 | 不存 `bbTex`（只存 desc）；按需建 RTV；钩 `ResizeBuffers` 释放重建 |
| 3 | **跨线程共享状态无同步**：`g_maps[64]`、`g_psSizes` 在 `Map/Unmap`、`CreatePixelShader` 里读写；而引擎的 CB 回放跑在 `WorkerThread<RenderCBToPlay>`（`docs/12:98`，**推断** Map/Unmap 也在该线程） | `1089-1110`、`1148+`、`648-678` | 数据竞争：插槽互踩、错误 buffer 被注入常量 | 一把 `SRWLOCK` 或每线程表；`g_psSizes` 至少用 `Interlocked` |
| 4 | **mode 2 下仍然持有全部 Present 资源**：`EnsurePresentResources` 无条件执行 | `2579` | 接触阴影已搁置，却常驻 2×RG16F 历史纹理（1080p ≈ 16 MB）+ 4 个 shader + 采样器 | 改为 `mode != 2` 时才建，切回 2 时释放 |

### 4.2 P1：性能与正确性

| # | 问题 | 位置 | 说明 |
|---|---|---|---|
| 5 | `OMSetRenderTargets` 钩**每次都做** `GetResource`+`QI`+`GetDesc` | `1613-1645` | 该 API 的调用频次与 draw 同量级（每帧数百至数千）；即使已算出 `dsvChanged` 也照做。至少加 `(presentMode!=2 \|\| probeMrt)` 门控并缓存上次 desc |
| 6 | `NotePixelShader` 对每个 PS `AddRef` 且永不释放，表只增不减 | `665` | 换图/重载场景后旧 shader 泄漏，字节码缓存另占最多 16 MB（`672`） |
| 7 | 时域历史 RT 创建但**从未被绑定** | `2274`、`2209-2226` | 合成 shader 只有一个 `SV_Target`（`fullscreen.hlsl:106`），`g_histSRV` 无人使用 → 纯死代码 |
| 8 | `LooksLikeSSAOFinal` 对每个 200–1500 B 的 PS 做一次 `D3DDisassemble` | `1040-1082` | 加载期会对大量材质 PS 反汇编（并拉入 `d3dcompiler_43`），是可感知的卡顿；建议按 crc 缓存 + 快速预筛 |
| 9 | `GP_spec.txt` 删除后不回落 | `2305-2306` | 无 `else` 分支，删文件后 boost 仍然生效（expo/light 都修过同类问题） |
| 10 | `GP_amb.txt` 首载与热载**阈值不一致** | `431` vs `2308` | 首载 `got>=1` 就同时赋 amb 与 ae（一个字段会把 ae 置 0），热载要 `got>=2` |
| 11 | FSR1 载荷的 `keepAlive` 用 `min(x,0)` | `fsr1_easu.hlsl:61,95` | 若 `t1`/`c[39].x` 为负，会**整体压暗**而不是无操作；同一 pass 在 100% 采样时还可能把原 bicubic 降成双线性+锐化 |
| 12 | AgX 的 gamma 事实上被抵消 | `tonemap_agx.hlsl:77,110` | `AgXToneMap` 末尾 `pow(x,2.2)`，随后又乘 `pow(c[1].w≈0.4545)` → 两次幂近似抵消，输出实际是**线性光**；K/S 因此作用在线性空间（对比更强、暗部更沉）。外观是靠 E/K/S 调出来的，但**一旦 `c[1].w` 变化，观感会跳** |
| 13 | `OnDemandDump` 注释承诺写 `.dep` 深度图 | `2425` | 实际只写 `.rgb`；注释与行为不符 |
| 14 | `deploy.ps1` 打印"红 debug：复制 GP_present_contact.txt" | `deploy.ps1:32` | `kContactShelved` 会把 mode 4 强制成 2，这条提示**永远不可能生效** |

### 4.3 P2：结构性问题

- **单文件 2,841 行**、无模块边界；vtables 槽位硬编码在 `HookContext`/`HookDevice`，A3/驱动变化时只能靠日志发现。
- **配置解析是手写 `fscanf`**：没有 schema、没有告警回显。解析失败时静默用默认值，用户无法区分"没生效"和"生效了但没用"。
- **无回归测试**：唯一自动化是 `tools/smoke_test.py`（起真设备验证 `CreatePixelShader` 替换），覆盖不到 `Map/Unmap`、Present、探针。
- **回滚语义不完整**：`README.md:119` 说"关闭 tonemap = 改名 `GP_replace.txt`"，但 `GP_ssao.dxbc` 仍会被加载并替换 SSAO（`423`）——SSAO 替换是独立硬编码路径，关不掉。

---

## 5. 文档与脚本一致性

以下都是**已核对**的（左边是文档，右边是源码/文件事实）。

| # | 文档说法 | 实际 | 证据 |
|---|---|---|---|
| 1 | `RESULTS.md` 称"`Hook_Map` 加 ByteWidth 缓存，消除每次 Map 的 QI+GetDesc" | **代码里没有缓存**，每次 Map 仍 `QI`+`GetDesc`；`git log -S` 显示历史上也从未有过 | `RESULTS.md:361` vs `d3d11_proxy.cpp:1098-1106` |
| 2 | `GP_probe_scale.txt.example` 强调"必须先开探针再启动，着色器记录是 gated 的" | 代码已改成**无条件记录**，注释明说"gating this on g_probeScale meant shaders created before the probe existed were never recorded" | `GP_probe_scale.txt.example:22` vs `d3d11_proxy.cpp:651-656` |
| 3 | `inject/README` 称"时域 RG16F ping-pong 已验证生效" | shader 单 RT、无 MRT 输出，历史纹理从未绑定 → 时域**已不存在** | `inject/README.md:117` vs `fullscreen.hlsl:106` |
| 4 | 同一文件：mode 2 是"待引擎内 A/B 通过后再改" | 代码 `kContactShelved` **无条件强制 2**，改文件无效；同文件 `:33` 已承认这点，`:128` 又反过来写 | `inject/README.md:33/34/128` vs `110/287` |
| 5 | `docs/20` 写驱动"≈活跃样本 2%"，`docs/10` 据此说 GPU 不是瓶颈 | 同一批数据在 `docs/13:136` 是"去等待后 **~23%**"。按 `92.6% ntdll + 3.4% win32u` 反推，活跃样本应是 4%，0.9/4 ≈ 23% —— **"2%" 差了一个数量级** | `docs/20:97` vs `docs/13:131-139` |
| 6 | `docs/09` 写"色调映射替换为 ACES" | 现行是 AgX；ACES 已成备选 | `docs/09:18` vs `presets/GP_replace.txt` |
| 7 | `docs/20` §2 标题写工具在 `<GP_WORK>/` | 已在 `tools/gpcpu/`（同文件第 3 行自述） | `docs/20:26` |
| 8 | `README` 快速开始"进游戏 → 场景 → GP Shot 2" | 仓库里**没有** `mission/GP_Shot2.Altis/`；该任务只在跑过 `mission/run-cli.ps1` 后由平铺的 `mission.sqm`+`init.sqf` 现场生成 | `README.md:97` vs `run-cli.ps1:26-44` |
| 9 | `inject/README` 记 `GP_replace_agx_neutral.txt` 内容为"—" | 实际指向 `GP_tonemap_agx_neutral.dxbc` | `inject/README.md:22` |
| 10 | `tools/build_tonemap.ps1` 把 `tonemap_agx_neutral.hlsl` 列为构建目标 | 该源文件不存在，脚本静默 skip；注释仍写"all four shipped payloads" | `build_tonemap.ps1:10-12,45` |
| 11 | `README` 说"四个产物统一用 ps_4_0" | 实际 5 个 job（多了 `GP_fsr1.dxbc`），且两份 README 都没记 FSR1 载荷 | `README.md:39` vs `build_tonemap.ps1:38-44` |
| 12 | `demo/README` 写"约 200 MB 截图" | 实测 1,204 MB / 212 个文件 | `demo/README.md:5` |
| 13 | `RESULTS.md` 里 2026-10-23/24 的"出货：mode 0 / `1696 0 1.10` / `0.35 -0.75 0 8`" | 现值 mode 2 / `1.35` / `0 10`，且同文件 `:326` 已裁决搁置 —— 未标 superseded | `RESULTS.md:223/229/230` |
| 14 | `toggle.ps1` 的 `-On` | 无条件用 `.off` 覆盖 `d3d11.dll`：`-Off → deploy(新) → -On` 会把旧 DLL 盖回去；且缺 `-Game` 参数（deploy/remove 都有） | `toggle.ps1:9` |
| 15 | `remove.ps1` 说"恢复原生渲染" | 不删 `d3d11.dll.off`（再 `-On` 会复活）；`GP_*` 通配会连日志/dump 一起删；路径错也报成功 | `remove.ps1:4-6` |
| 16 | `deploy.ps1` 说"只部署 polished defaults" | 不做过期清理：游戏目录里既有的 `GP_adapt.txt` / `GP_light_bind.txt` / `GP_cb_dump.txt` 不会被移除，"默认关"无法恢复 | `deploy.ps1:15-25` |

**为什么值得单独列**：这个项目的可信度建立在"文档 = 实测"上。第 1、2、3、5 条不是笔误，而是描述了一个不存在的实现或一个矛盾的量级——它们会让下一个接手的人（包括三个月后的你）在错误的前提上继续推理。

**正面核对（不必改）**：`GP_ssao.dxbc` / `GP_tonemap.dxbc` 的 sha256 前缀 `5A2370A56BA8` / `8BD7FDE4571B` 与 README 一致；AgX `E0.55/K1.40/S1.20`、ACES `0.45/1.12/1.08`、`smoothstep(0.15,1.0)`、present 缺省 `alpha 0.35 / luma 0.05/0.18` 全部与源码一致；6 个配置文件的字段顺序全对；`git ls-files -ci --exclude-standard` 为空（没有 ignore 漏网文件）。

---

## 6. 工具链与仓库卫生

| 项 | 现状 | 影响 |
|---|---|---|
| 依赖声明 | **没有** `requirements.txt` / `pyproject.toml`；实际用到 numpy(66 文件)、Pillow(51)、capstone(20)、opencv(4)、pefile(2)、imageio-ffmpeg(2) | 换机/换人不可复现；本机 Python 3.14.6 + numpy 2.5.3，部分老脚本大概率已跑不通 |
| 硬编码路径 | 实测 134 个脚本中 **121 个**写死 `<USERPROFILE>` 或 `<STEAM>`；`inject/counter/*.ps1` 是 10/11 | 所有工具都只能在你这台机器上跑 |
| 重复/死脚本 | `ao_offline/2/3`+`ao_preview` 四次重写同一 AO 循环（相似度 0.58–0.70）；`cmp_ssao` vs `cmp_ssao2` 0.96；`ratio`/`ratio3`、`exe_scan`/`exe_scan2`、`list_mat_ps`/`list_mat_ps2` 成对 | 读者无法判断哪个是"当前正确实现" |
| 已确认的坏脚本 | `make_ab_contact.py:15` `import contact_shadow`（函数实际叫 `contact_occlusion`）→ **每次运行都 ImportError**（已复现） | demo 里那张对照图的生成链是断的 |
| 构建脚本 | `proxy/build.bat` 写死 VS 路径与项目绝对路径；`build_present.ps1` 写死 fxc 版本 `10.0.26100.0` 且用 `/O3`，与 README"不要 /O3"的约定相反；`build_tonemap.ps1` 反而是自动探测 fxc 的好写法 | 构建不可移植，且两条 shader 构建链的约定不一致 |
| 仓库体积 | `.git` 4.1 MB，但工作区 1.3 GB（`demo/` 1.2 GB + `extract/` 83 MB） | 每次备份/同步都很重；`demo/README` 自己写的 200 MB 也已过时 |
| 提交的生成物 | `extract/shader-inventory.csv`(425 KB)、`extract/rtti_names.txt`(209 KB)、`fullscreen_shaders.h`(42 KB)、`gpmat.pbo`、个人 `Arma3Profile` 备份(130 KB) | 噪声；`.gitignore` 缺 `*.csv` / `*.pbo` / `config/backup-*/` |
| 文档导航 | 22 篇文档、无索引；README 只链 `10`、`16`，**13 篇（01–08、11、14、15、18、19）是孤儿** | 新读者找不到入口 |
| 测试 | 仅 `tools/smoke_test.py`（覆盖 CreatePixelShader） | 回归全靠人肉跑游戏 |

---

## 7. 证据质量

**强的地方（比多数同类项目好）**

- 负面结果**保留并归档**（N1/N2 双 NO-GO、GFSDK 崩溃回滚、镜面负收益），这是最省后人时间的东西；
- **自我纠错**：2026-10-28 用 30 万行历史日志推翻了自己"曝光钳制在压暗"的叙事，并给出验证方法（临时 `1.05` 看 `CLAMPED` 比例）；
- 测量口径明确区分 **`diag_fps`**（被封顶）与 **`exe_fn`**（采样命中），并在 `ai_wp_cost_model.json` 里留下完整原始行 + `R²`/`RMSE`——我核对了系数，与 `docs/17` 一致；
- 离线可复现：`contact_shadow_smoke.py` 在本机仍可 import 并生成场景（numpy 2.5.3 下正常）。

**弱的地方**

- **单机、单场景、n 小**：`exe_fn` 在低负载下只有 3–17 次命中，相对噪声很大；同一配置两次运行差 9%（48 组：522 vs 570）。
- **"已验证"与"有收益"混用**：SSAO 替换、ambient 注入除色调定稿外没有独立对照。
- **测量 rig 与出货配置不一致**：`mission/init.sqf` 强制 `setViewDistance 4000` / `setTerrainGrid 6.25`（`:25-28`），而出货 profile 是 3800 / 3.125。demo 图并不代表默认配置下的画面。
- **第 5 节的量级矛盾（2% vs 23%）直接支撑了"GPU 不是瓶颈"这一战略判断**，进而支撑了"超分只是画质工具"的结论。这条必须先修正再谈超分。

---

## 8. 风险登记

| 风险 | 触发条件 | 现状 |
|---|---|---|
| BattlEye / 封号 | 带 `d3d11.dll` 连官方或有 BE 的服 | 文档反复警告，但**代码没有任何环境检测或醒目提示**；`deploy.ps1` 也不问"你确定只玩单人？" |
| A3 更新全链路失效 | 游戏更新 → `size/crc`、`expo size`、RVA 全变 | 无版本自检；只会在日志里表现为 `REPLACE ps` 消失（静默不生效） |
| 崩溃 / 黑屏 | 接触阴影（已搁置）、`InstallCandHooks`（改游戏代码，曾崩客户端）、GFSDK 代理（已回滚） | 都保留了"默认关"的路径，这点做对了 |
| 不可分发 | DLL 被 `.gitignore` 掉（`*.dll`），仓库里只有源码 | 别人 clone 下来跑不了 `deploy.ps1`，必须先装 VS2022 + SDK |
| 维护者依赖 | 121/134 脚本写死本机路径、构建脚本写死 VS 安装路径 | 只有你能维护 |
| 合规 | 不分发原版 DXBC / 反编译源码 | 已遵守（`docs/02:168`） |

---

## 9. 建议（按 ROI 排序）

**立即（半天，全是缺陷修复）**

1. 把 `LoadConfig()` 从 `DllMain` 挪到首个 `CreateDevice`（P0-1）。
2. `EnsurePresentResources` 改为按 `mode != 2` 懒创建；`ResizeBuffers` 时释放重建（P0-2/P0-4）。
3. `g_maps` 加锁或改每线程表（P0-3）。
4. `OMSetRenderTargets` 钩加门控（P1-5）——这是唯一一个"每帧几千次"的热路径开销。
5. 删掉时域死代码（P1-7），或把 MRT 写回 shader 真正接上；不要留半截。
6. 修文档四连：`RESULTS.md:361`（不存在的缓存）、`GP_probe_scale.txt.example:22`（不存在的 gating）、`inject/README.md:117`（不存在的时域）、`deploy.ps1:32`（永远不生效的 debug 提示）。

**一周（可验证的收敛）**

7. **先跑一次 `GP_probe_scale`**，把真实 `psLen/psCrc` 写进 `GP_replace_fsr1.txt`。现在文件里的 `5596 B682EAC0` 没有对应的 `GP_upscale.txt` 证据，属于"按推测出货"。
8. 修正 `2% vs 23%` 的量级矛盾，并在 `docs/10 §2.13.6` 明确它是哪一个分母。这条会改变超分方向的结论强度。
9. 给 `GP_spec` / `GP_amb` / `GP_adapt` 补上和 `expo` 一样的"缺文件即关闭"语义，并把字段阈值写进 README（现在 `got>=1` 与 `got>=2` 不一致）。
10. 加 `requirements.txt`；把 121 个脚本的绝对路径收敛成一个 `ROOT = Path(__file__).resolve().parents[1]` 常量（机械替换，可脚本化）。
11. 修 `toggle.ps1` 的旧 DLL 覆盖、`remove.ps1` 漏删 `.off`、`deploy.ps1` 不清过期配置——这三个直接决定"我部署的到底是不是新 DLL"。

**一个月（把它变成能给别人的东西）**

12. **交付线打包**：一个 `install.ps1` + 版本自检（读 `arma3_x64.exe` 的 size/version，与已知 shader 表比对，不匹配就明确告知"本版未适配"而不是静默不生效）+ 崩溃回滚 + 一份"只玩单人"的醒目声明。
13. **回归**：把 `smoke_test.py` 扩成 `Map/Unmap` + `Present` 的最小验证（用假设备或真设备都行），进 CI（Windows runner 至少跑构建 + 静态检查）。
14. **文档做单一事实源**：预设表、`README` 的能力表由脚本从 `presets/` + 代码常量生成，杜绝手抄漂移；加 `docs/README.md` 索引，把 13 篇孤儿文档归并成"历史裁决"区。

**战略（需要你决定）**

15. 现在同时挂着三条研究线：**超分**、**接触阴影**、**光照 CB**。接触阴影已经证明"只有深度做不出稳定结果"（黑天 + 需要干净深度，而 N2 已判 NO-GO），继续投入的期望值很低；建议**正式结案**，只在 README 保留一句结论。
16. 超分线的前置条件（放大环节能否接管）已经有探测器，**先花半天跑出数据**再决定要不要投 3–5 人日。若 `GP_upscale.txt` 为空，这个方向当天就该封档。
17. 真正还有画质空间的是文档自己反复指出的那条：**rvmat / 材质响应**（`docs/01:168-169`、`docs/02:117`、`docs/15:105` 都写着"这是唯一能改材质如何响应光的官方路径"）。它不需要注入、不违反 BE、可分发给别人——但它也意味着离开当前"注入 + 后处理"的舒适区。**这是本项目最值得做的一次方向选择，而不是又一个 shader 参数。**

---

## 10. 复现清单

```powershell
# 1. 文档/代码漂移（第 5 节 #1/#2/#3）
Select-String inject\proxy\d3d11_proxy.cpp -Pattern 'ByteWidth|Unconditional|Single RT'
git log --oneline -S 'ByteWidth' -- inject/proxy/d3d11_proxy.cpp   # 空输出 = 从未实现

# 2. 工具链断点（第 6 节）
python -c "import sys; sys.path.insert(0,'tools'); import make_ab_contact"   # ImportError

# 3. 仓库卫生
git ls-files | Measure-Object            # 369
git ls-files -ci --exclude-standard      # 空 = 无 ignore 漏网

# 4. 构建后自检（现有能力）
powershell -File tools\build_tonemap.ps1
powershell -File tools\build_present.ps1
```

---

## 11. 修复记录（2026-10-28 晚）

本节记录评审之后**实际改了什么、怎么验的、还留着什么**。上面 §4/§5 保留原样，作为修复前的证据。

### 11.1 代码（`inject/proxy/d3d11_proxy.cpp`，全部已重新编译）

| 原编号 | 修复 | 验证 |
|---|---|---|
| P0-1 | `LoadConfig()` 移出 `DllMain`，改为首个 `D3D11CreateDevice*` 里的 `EnsureInit()`（`InterlockedCompareExchange` 守门）；`DllMain` 只存 `hModule` | 冒烟测试日志里配置在设备创建后加载，`proxy attached` 出现在其后 |
| P0-2 | 不再保存 backbuffer 的 `Texture2D*`；新增 `ReleasePresentResources()` + 挂 `IDXGISwapChain::ResizeBuffers`（slot 13），改分辨率前释放 RTV/拷贝纹理 | 冒烟测试 `ResizeBuffers hr=0x00000000`（修复前会因占着 buffer 0 而失败） |
| P0-3 | `g_maps` / `g_psSizes` 加 `SRWLOCK`；`Unmap` 先在锁内取走表项、再在锁外做浮点处理；`g_psSizes` 加 8192 条上限，超限整体释放重建 | 编译通过；日志格式不变 |
| P0-4 | `EnsurePresentResources` 改为按需：只有 `presentMode != 2`（或自适应曝光要读帧）才建；`mode==2` 时释放 | 冒烟测试确认 mode 2 下日志**没有** `present ready` |
| P1-5 | `OMSetRenderTargets` 钩加 `(presentMode!=2 \|\| probeMrt)` 门控 + DSV 未变则跳过 COM 往返 | 编译通过；几何路径不再每 draw 做 QI |
| P1-6 | 着色器表条目数设上限，超限 `PsMapReset()` 释放引用后重建（只影响探针命名） | 无 |
| P1-7 | 删除时域死代码：`g_histTex/RTV/SRV`、`CreateHistResources`、`ReleaseHistResources` 全部移除（省 ~16 MB 与一套无用绑定） | 编译通过 |
| P1-9/10 | `GP_spec.txt` / `GP_amb.txt` 删除后回落；两者共用 `ParseAmbFile()`，首载与热载阈值一致（≥2 字段才改 amb/ae，≥4 才改色温） | 冒烟测试日志 `ambient 0.00 ae 0.00`（缺文件→关闭） |
| P1-11 | FSR1 的 `keepAlive`（会整体压暗）改为永不命中的 `discard` 守卫，保持绑定形状但零影响；重编 `GP_fsr1.dxbc`（2132 B，`4C13AC4DB1C2`） | `build_tonemap.ps1` 重跑，其余四个载荷哈希不变 |
| P1-13 | `OnDemandDump` 注释不再承诺写 `.dep` 深度 | — |
| P1-14 | `deploy.ps1` 删除"红 debug"提示（mode 4 永远被强制回 2） | — |
| P2 | `build.bat` 不再写死项目路径，加 `/utf-8`（源码是 UTF-8，之前按 GBK 解码会mangle 4 行注释/1 条日志）；`ParsePresentLine` 相关陈旧注释更正 | 编译零警告 |
| 探针容量 | `g_scaleSeen` 32 → **128**，加 `prio` 字段（2 = 读内部渲染尺寸或写 backbuffer）与**按优先级淘汰**；报告打印 `distinct=N/128` 与 `prio` 列。修的是"真·拉伸每帧 1 次，进不去被 UI pass 占满的表" | `probe_smoke_test` 断言 prio-2 行存在 |
| 探针颜色空间 | 新增 `ProbeUpscaleInput()`：对 prio-2 pass 把输入 SRV 拷到 staging，网格采样后打印 `min/max/mean >1% >4%` 与 verdict（HDR / display-referred）；`GP_upscale_dump_input.txt` 存在时另存完整 raw | 用 8.0 色块验证 → 判为 HDR，半浮点解码精确到 0.25/0.5/0.75 |
| 探针启动 | `LoadConfig` 里补 `RefreshProbeScaleFlag()` / `LoadArmaCfgRenderSize()` —— 之前探针要等到第 60 个 Present 才生效，即使文件在启动前就放好了 | 冒烟测试第 1 帧就能记录 |
| 整帧抓取 | `GP_passseq.txt` 升级为"一帧全部 pass + 每 pass 采样源的颜色统计"，并新增 `GP_shaders.txt`（全部 PS 的 crc/长度）。抓帧两阶段：先由"输入<输出且写 backbuffer"的帧 arm，下一帧带统计落盘；资格判定不再依赖硬编码 crc | `probe_smoke_test` 12/12；`analyze_capture.py` 生成链路报告 |
| 抓帧回读时机 | 在 draw 内读一次（探针一直用的路径），并把 SRV 留到 Present 复读一次，兜住"帧内读到全零"的驱动行为 | 冒烟测试通过；真实数据见 14:29 会话 |
| 成像（2026-10-28 晚） | AgX 输出加 **IGN 抖动**（±0.5/255）消 8-bit 色带；新增 `GP_agx.txt`（E K S shoulder）经 `c[82]/c[83]` **实时调参**，删文件回内建默认；可选高光肩部（默认关，因为会把 1.0 压到 ~0.94） | 载荷重建（3752 B）；`GP_agx.txt` 出货 0.55 1.44 1.24 0，只把对比/饱和各推 3% 逼近项目自定目标 |

**新增** `tools/proxy_smoke_test.py`：不启动游戏，用隐藏窗口 + 真 D3D11 设备跑
"配置加载 → CreatePixelShader 替换 → Present ×2 → ResizeBuffers → Present"，退出码即结果。
本机实测 7/7 PASS。

### 11.2 脚本与工具

| 文件 | 修复 |
|---|---|
| `inject/deploy.ps1` | `-Game` 校验；拒绝部署比源码旧的 DLL；不再复制 4 个"备选"预设（ACES / AgX-neutral / FSR1 / stylized）；新增过期清理（`GP_adapt.txt` / `GP_light_bind.txt` / `GP_cb_dump.txt` / 各种 probe/trigger），否则"默认关"无法恢复 |
| `inject/remove.ps1` | 同时删 `d3d11.dll.off`（否则下次 `toggle -On` 会把注入装回来）；路径不存在时明确报错而不是假成功；空目录提示 |
| `inject/toggle.ps1` | 补 `-Game`；`-On` 不再用较旧的 `.off` 覆盖较新的 `d3d11.dll` |
| `tools/make_ab_contact.py` | 修复 `import contact_shadow`（函数实际叫 `contact_occlusion`）——之前每次运行都 ImportError |
| `requirements.txt` | 新增：numpy / Pillow / capstone / pefile / opencv-python / imageio-ffmpeg，按本机实测版本钉住 |
| `*.ps1`（8 个） | 给含中文的脚本补 **UTF-8 BOM**。Windows PowerShell 5.1 按 ANSI 读无 BOM 文件，中文会变成乱码，严重的会直接解析失败（重写 deploy/remove/toggle 时踩到，8 个脚本统一修） |
| `tools/build_tonemap.ps1` | 注释改为"五个载荷"，并说明 neutral 无源文件、skip 是预期 |

### 11.3 文档

- **纠正了一条不存在的实现**：`RESULTS.md` 的"`Hook_Map` 加 ByteWidth 缓存"改为"未做缓存，同日晚些修的是并发安全"。
- **探针文档**：`GP_probe_scale.txt.example` 不再声称"着色器记录是 gated 的"（该分支早已删除）。
- **时域**：`inject/README` 与 README 都不再声称 RG16F 时域存在；明确接触阴影 mode 0/3/4 已被硬开关封死。
- **数量级矛盾**：`docs/10 §2.13.6` 与 `docs/20 §4.1` 统一为"全样本 0.68% / 去等待后 ~23%"，并加更正注记。
- **历史快照**：`RESULTS.md` 2026-10-23 的 v1 段落加了"不是当前出货状态"的横幅（mode 0 / 1.10 / `0 8` 都已被覆盖）。
- **ACES → AgX**：`docs/09` 的对比表已更正。
- 其余：`mission` 的 `GP_Shot2` 生成方式、`GP_amb` 字段语义、`GP_adapt` 不热重载、`demo/README` 的实际体积、`build_tonemap` 的五个产物。

### 11.4 修复过程中**新发现**的问题

1. **接触阴影的离线证据不成立**：`docs/12` 写 `mean_occlusion_ground ≈ 0.49`，用当前代码重跑是
   **0.023**（`contact_occlusion(make_scene()[1])`，ground = `d < 0.88`）。场景深度只有 0.28–0.75 m，
   1.2 m 半径在 `projK=600` 下被裁到 ≤48 px，只有方块边缘一圈命中。已在 `docs/12`
   与 `demo/README` 标注更正；**这进一步支持"接触阴影结案"，而不是相反。**
2. `make_ab_contact.py` 此前**根本跑不起来**（`ImportError`），所以 `demo/ab-contact-*.png`
   不是当前代码的产物；修好导入后又发现它把 `contact_occlusion` 的结果取反成 "lit"、再在合成里取反回来，
   数学等价但极易读错，已在注释里写清方向。
3. **两个编码坑**：`build.bat` 之前按 CP936 读 UTF-8 源码，4 处 `—`/`≈` 会被 mangle（其中一条在
   `Log()` 字符串里，日志会出乱码）；`.ps1` 里中文若无 BOM，Windows PowerShell 5.1 会按 ANSI 解码，
   `toggle.ps1` 到 `remove.ps1` 直接解析失败。两者都已在构建/脚本层修掉（`/utf-8` + BOM）。

### 11.5 明确**没做**的（及原因）

| 事项 | 原因 |
|---|---|
| 重写 AgX 的 gamma 链 | `pow(2.2)` 被 `pow(c[1].w≈0.4545)` 抵消、输出实际是线性光——外观是靠 E/K/S 调出来的。改它等于重新标定整套色调，应作为独立实验，不该混在修复里 |
| 修复 `LooksLikeSSAOFinal` 的加载期反汇编开销 | 它是 SSAO 替换的**唯一**识别方式；改成 crc 白名单会让 A3 更新后更难适配。当前只影响一次加载，接受 |
| 给 FSR1 的 `5596 B682EAC0` 补证据 | **已有一半**：游戏目录里 2026-10-28 13:21 的探针产物已归档到 [extract/upscale_probe_20261028](../extract/upscale_probe_20261028/README.md)。它证明放大**是**单个 PS pass（`B682EAC0`，1600×900 HDR → 1920×1080），但该会话的 `psLen` 是 **6204** 而非配置里的 5596 ⇒ 替换从未命中；探针报告里没这一行，是因为 `g_scaleSeen[32]` 被高频 UI pass 占满。要真正落地仍需改探针容量 + 按目标分辨率重采 size |
| 合并/删除 ~40 个一次性脚本 | 机械但量大，且需要逐个确认是否还有人用；建议单独一次提交 |
| 版本自检 / CI | 属于"一个月"项，需要先定分发形态 |

---

**一句话收尾（更新）**：修复后，三个会导致真实故障的缺陷、一处不存在的实现记录、一处数量级错误都已清掉，
并且第一次有了不依赖游戏的回归入口（`proxy_smoke_test.py`）。剩下的问题不是"还有 bug"，而是
**"这条产品线要不要继续"**——接触阴影的证据在这次复核里又弱了一档，超分仍缺一次实测，rvmat 才是没有天花板的方向。

---

**2026-10-28 15:55 补记（公开整理时）**：同日 14:51 的 1440×810 复采已经把 FSR1 指纹对上：
`GP_upscale.txt` 里有 `5596 B682EAC0`（1440×810 → 1920×1080，hits=6579），原始文件归档在
[extract/upscale_probe_20261028/1440x810](../extract/upscale_probe_20261028/1440x810/README.md)。
所以本节的"超分仍缺一次实测"应改为"**指纹已对上，画质 A/B 未做**"；1600×900 的 6204 只适用于那个分辨率。
