# 注入器说明

> 公开研究仓库：仅限单人 / 编辑器 / 无 BattlEye 的私有服。仓库不包含游戏资源；
> `proxy/d3d11.dll` 需要自己编译，构建产物不入库。

## 组成

| 文件 | 说明 |
|---|---|
| proxy/d3d11.dll | 代理 DLL（静态链接，仅依赖 KERNEL32） |
| proxy/d3d11_proxy.cpp / build.bat | 源码与 MSVC 构建脚本 |
| present/ | Present 接触阴影 HLSL + 嵌入头（`tools/build_present.ps1`） |
| presets/ | 当前生效配置 |
| tonemap_aces.hlsl / ssao_final.hlsl | 两个替换着色器的源码 |
| deploy.ps1 / remove.ps1 | 一键部署 / 一键移除 |
| toggle.ps1 | 开/关 d3d11.dll |
| set-spec.ps1 | 调材质镜面参数 |

## 默认预设（presets/）

| 文件 | 内容 | 作用 |
|---|---|---|
| GP_replace.txt | 5860 42670B06 GP_tonemap_agx.dxbc | tonemap → **AgX**（当前出货） |
| GP_replace_aces.txt | 5860 42670B06 GP_tonemap.dxbc | tonemap → ACES v5（**不随 deploy**） |
| GP_replace_agx_neutral.txt | 5860 42670B06 GP_tonemap_agx_neutral.dxbc | AgX neutral 变体（**无 .hlsl 源**，仅载荷；**不随 deploy**） |
| GP_replace_fsr1.txt | 5596 B682EAC0 GP_fsr1.dxbc | 替换游戏自己的 stretch pass（**不随 deploy**；见下） |
| GP_tonemap_agx.dxbc | AgX，内建 E 0.55 / K 1.40 / S 1.20 | 全局成像；`c[82]` 有 GP_agx.txt 时可实时覆盖；输出带抖动 |
| GP_agx.txt | `0.55 1.44 1.24 0` | **出货的 AgX 调参**（E K S shoulder），热重载，删文件回内建默认 |
| GP_agx.txt.example | 注释 + 调参建议 | 调参说明；`GP_agx.txt` 是实际生效的 4 个数 |
| GP_tonemap.dxbc | ACES v5（曝光 0.45 / 对比 1.12 / 饱和 1.08） | 备选成像 |
| GP_ssao.dxbc | smoothstep(0.15, 1.0) | AO 对比增强；已接线，无 A/B 对照 |
| GP_fsr1.dxbc | 双线性 + 邻域钳制锐化 | `GP_replace_fsr1.txt` 的载荷；1440×810 下指纹已命中，**未做画质 A/B** |
| GP_spec.txt | `0 0.15 0` | 镜面 **mode 0 关**（`1 boost power` = 只 boost 已有 spec） |
| GP_spec_boost.txt | `1 0.15 0` | 选择性镜面实验（不随 deploy） |
| GP_amb.txt | `0.80 0.90 1.00 1.00` | 环境光折中（不冷偏） |
| GP_amb_stylized.txt | `0.60 0.80 0.93 1.10` | 旧风格化档（发暗发蓝） |
| GP_expo.txt | `1696 0 1.35` | 曝光上限折中（指纹钳制） |
| GP_expo_adapt.txt | `1696 0 1.10 1 0.55 0.55 1.10` | 自适应 hi（不随 deploy） |
| GP_expo_tight.txt | `1696 0 0.55` | 紧曝光实验（不随 deploy） |
| GP_present.txt | mode **2** | **接触阴影已搁置**（`kContactShelved`，改文件无效） |
| GP_present_on.txt | mode 0 | ⛔ 已失效（会被强制回 mode 2）；仅作代码路径保留 |
| GP_present_off.txt | mode 2 | 关 Present |
| GP_present_contact.txt | mode 4 | ⛔ 已失效（同上） |
| GP_light.txt | `0.35 -0.75 0 10` | 手调屏幕空间光向 + 步数 |
| GP_light_auto.txt | `auto 10` | 用 CB 绑定光向（需 `GP_light_bind.txt`） |
| GP_light_bind.txt.example | `1696 12`（示例占位值） | 改名为 `GP_light_bind.txt` 前先跑 `cb_sun_hunt.py` |
| GP_cb_dump.txt.example | `1 512 4096 120 64` | 改名为 `GP_cb_dump.txt` 开 CB dump |
| GP_probe*.example | — | 探针（`GP_probe_mrt` / `GP_probe_scale`） |
| GP_probe_scale.txt.example | — | **放大环节探测器**：找"输入 SRV < 输出 RTV"的全屏 pass，输出 `GP_upscale.txt`（含 psLen/psCrc） |
| GP_adapt.txt.example | `1 0.02 0.50 0.25` | 自适应 AgX 控制器（**默认关，且只在启动时读一次**） |

### GP_adapt.txt 格式

`enable blownTarget topTarget rate`

- **默认关**（`g_adaptOn = 0`）。开启后每 15 帧做一次全幅 `CopyResource` + STAGING 回读，
  在 CPU-bound 引擎里是实打实的开销，因此不随 deploy 出货。
- 开启时，代理把 `g_adapt` 写入 `PSCB_PostProcess` 的 `c[80].x`，并把哨兵 `1.0` 写入 `c[80].w`；
  AgX shader 仅在 `c[80].w == 1.0`（精确浮点比较）时用它插值 E/K/S，其余情况走固定 tune。
- 关闭时 `c[80].w` 写 0，shader 立即回到固定曲线，不会读到残值。
- 实测：`blown` 长期 ≈0.004（阈值 0.02），所以这个控制器在常规场景几乎不会触发。

### GP_expo.txt 格式

`size lo hi [adapt] [target] [hiLo] [hiHi]`

- 出货：`1696 0 1.35`
- adapt=1：按帧平均亮度在 `[hiLo, hiHi]` 间插值有效上限
- **实测（2026-10-28）**：指纹通过的 `f150` 99.9% 恒为 1.0，`hi=1.35` 绝大多数帧是空操作；
  `CLAMPED` 只在 AE 短时冲高（约 1.64）时出现。想验证机制：临时改 `1696 0 1.05` 跑一局。
- **指纹**（防共享 size 误伤）：`c1.w≈0.4545`、`c0≈0`、`AE∈[0.05,4]`，且 `c37` 为 `(1, 0.30, AE, 1.00)` 或 `(1, 0.09, AE, 0.75)`
- 删/改名文件会热禁用（不必重启）
- 日志：`expo hit ... fp=1` / `CLAMPED ... fp-ok` / `expo skip fingerprint`

### GP_agx.txt 格式

`E K S [shoulder]` —— AgX 的曝光 / 对比 / 饱和度 / 高光肩部，**60 帧热重载**，删文件即回落到
shader 内建默认（0.55 / 1.40 / 1.20 / 关）。

- 肩部（shoulder）默认**关**：它把 1.0 映射到约 0.94，会让爆掉的天空发灰；只有在"要高光层次
  胜过要纯白"时才开。
- 为什么给这几个数：项目自己的 A/B 目标是 σ 0.16–0.22、暗部 10–20%、饱和 15–25%、少过曝；
  实测是 σ 0.142、饱和 ~15%、过曝 15.4%。出货的 `0.55 1.44 1.24 0` 只把对比和饱和各推 3%。
- 输出还加了 **±0.5/255 的 IGN 抖动**：8-bit 输出在天空/雾/暗角上的色带会消失，其余不可见。

### GP_present.txt 格式

`mode strength radius_m projK frac [alpha] [luma0] [luma1]`

| mode | 含义 |
|---|---|
| 0 | 接触阴影合成（软双半径 + 明度保护） |
| 1 | 遮挡灰度 debug |
| 2 | 关闭 |
| 3 | 合成 + 深度缩略图 |
| 4 | 红色遮挡 debug |

> ⚠️ 当前版本 `kContactShelved = true`：**任何 ≠2 的 mode 都会被强制改回 2**，
> 上面 0/1/3/4 只是保留的代码路径，写进 `GP_present.txt` 不会生效（`deploy.ps1` 也不再提示开它）。

缺省：`alpha=0.35`、`luma0=0.05` / `luma1=0.18`（明度保护）。热重读。
时域滤波（RG16F ping-pong）**已删除**：它与单 RT 合成不兼容，历史纹理从未被采样。

### GP_probe_scale.txt / 放大环节探测器

超分（FSR1/NIS）只能插在游戏的「放大环节」，而 `Present` 拿到的已是放大后的图。
本探针用来定位那个环节，并顺手回答"那个 pass 的输入是不是已经 tonemap 过"：

1. 复制 `presets\GP_probe_scale.txt.example` → 游戏目录 `GP_probe_scale.txt`
2. **进游戏把 Sampling 调到 70% 或 50%**（100% 时输入=输出，永不命中）
3. 玩几分钟后读游戏目录 `GP_upscale.txt`（建 `GP_upscale_dump.txt` 可立刻刷一次）

判据：全屏 draw 中**输入 SRV 尺寸 < 输出 RTV 尺寸**即命中；报告给出 `psLen` + `psCrc`，
可直接写进 `GP_replace.txt` 替换该 pass。纯观察，不修改任何状态。

报告要点（2026-10-28 起）：

- `prio`：**2 = 读内部渲染尺寸或写 backbuffer**。要替换的就是"prio 2 且输出是 backbuffer"那一行；
  原先 32 槽先到先得，会被高频 UI pass 占满（实测 `distinct=32` 就是这个上限），
  现在 128 槽 + 按优先级淘汰。
- **颜色空间回读**：对被选中的 prio-2 pass，代理把它当帧的输入拷到 staging 读一遍，
  在 `GP_shader.log` 里打 `upscale input ... min/max/mean >1% >4%` 和一句 verdict
  （`HDR / scene-linear -> tonemap before EASU` 或 `display-referred [0,1] -> EASU can be used directly`）。
  FSR1 的 EASU 要求后者；前者必须在替换件里先做 tonemap。
- **整帧抓取（一次拿全）**：~240 帧后写一次 `GP_passseq.txt`（这一帧**每一个**全屏 pass 的
  执行顺序 + 输入/输出尺寸 + 格式 + psLen/crc + **采样源的颜色统计**）、`GP_shaders.txt`
  （游戏创建过的全部 PS）、`GP_upscale.txt`（整局候选）。
  再用 `python tools\analyze_capture.py "<游戏目录>"` 生成一份报告：链路、最终拉伸、
  每个阶段的 HDR/LDR、可替换 shader 清单。
- 想拿到那张纹理本体（1600×900 RGBA16F ≈ 12 MB），在 draw 之前建 `GP_upscale_dump_input.txt`，
  会写出 `GP_up_in_<crc>_<w>x<h>.raw`（打包行，8 bpp）。

若报告为空：要么 Sampling 还是 100%，要么放大不由单个 PS pass 完成（VS-only blit / DXGI 缩放）。
后者本身是有价值的负面结论。现有实测见 [extract/upscale_probe_20261028](../extract/upscale_probe_20261028/README.md)。
注意 `psLen` 随内部渲染尺寸变化：1600×900 时是 6204，1440×810 时是 **5596**（`B682EAC0`）。
不要把一个分辨率下的 size 当成通用值。

### GP_light.txt / 自动光向
- 手调：`lx ly lz steps`
- 自动：文件内容 `auto [steps]`，并从 `GP_light_bind.txt` 读 `size floatIndex`
- 流程：复制 `GP_cb_dump.txt.example` → dump 白天/黄昏/室内 → `python tools/cb_sun_hunt.py ... --out GP_light_bind.txt` → 复制 `GP_light_auto.txt` → `GP_light.txt`

### GP_spec.txt 格式

`mode boost [power]` — mode 0=关；mode 1=仅当已有 specular 时 `×(1+boost)`（跳过草/云）。

## 工作方式

1. 代理 d3d11.dll，接管 D3D11CreateDevice（配置在**首次创建设备时**读取，不在 DllMain 里做文件 IO）
2. 挂钩 CreatePixelShader：按 (size, crc) 或反汇编指纹替换指定 pass
3. 挂钩 Map/Unmap：环境光 / 曝光钳制 / 可选镜面 boost / CB dump / 光向绑定
4. Present：颜色拷贝 +（搁置的）全屏接触阴影；`ResizeBuffers` 时释放并重建自有资源
5. 只有 `presentMode != 2`（或自适应曝光开启）时才创建 Present 资源；默认配置下不占显存

## 已验证生效

- tonemap / SSAO resolve / 环境光（见 docs/RESULTS）
- 曝光钳制：**机制**成立（`fp=1` / `CLAMPED ... fp-ok` 可验），但 30 万行日志里 99.9% 的帧是空操作
- 接触阴影：仅离线冒烟；引擎内强制 mode 2，且**离线重跑的可复现遮挡率只有 ~0.02**（见 docs/21 §11）
- 天空保护：近地 `d<0.88` / `z≤25m`；云层不采样为遮挡物

## 已放弃

- 代理 GFSDK_SSAO；`specular==0` 覆写；仅深度二次 AO；G-buffer 法线 / 云前干净深度（N1/N2）

## 已知限制

- 材质着色器代码不可改；A3 更新后 size/crc / expo size 需重采
- 自动光向依赖 CB hunt 命中；未绑定时请用手调 `GP_light.txt`
- 接触阴影**已结案**：Present 侧合成需要干净深度，而 N2 已判 NO-GO；`kContactShelved`
  是无条件硬开关，不再有"通过 A/B 后打开"的路径
- 没有版本自检：A3 更新后如果 `GP_replace.txt` 的 size/crc 不再命中，只会表现为日志里
  不再出现 `REPLACE ps`（静默不生效）
- 部署 / 移除脚本读 `ARMA3_DIR`（或 `-Game <路径>`）；不要依赖旧的绝对路径。
