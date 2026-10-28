# 放大探针实测 · 2026-10-28 13:04–13:21

> 从游戏目录 (`<ARMA3>`) 归档的运行时产物。
> 代理版本：修复前（`kContactShelved` 时期，`GP_probe_scale.txt` 已开启）。
> 原始文件：`GP_upscale.txt` / `GP_passseq.txt` / `GP_bindseq.txt` / `GP_mrt_census.txt` / `GP_depth_timeline.txt`。

## 设置

| 项 | 值 |
|---|---|
| backbuffer | 1920×1080（fmt 28 = `R8G8B8A8_UNORM`） |
| 内部渲染 | **1600×900**（`Arma3.cfg` 的 renderWidth/Height，即 Sampling ≈ 83%） |
| `GP_replace.txt` | 两行：`5860 42670B06 GP_tonemap_agx.dxbc` + `5596 B682EAC0 GP_fsr1.dxbc` |
| 采样时长 | 约 17 分钟（fullscreen draws 累计 232 万次） |

## 结论一：放大环节**是**一个全屏 PS pass —— 但探针报告把它漏掉了

`GP_passseq.txt` 倒数第 6 行（单帧执行顺序，idx 247）：

```
247  B682EAC0   6204    1600  x900        1920  x1080       10/28
```

即 **`B682EAC0`，`psLen=6204`，1600×900（fmt 10 = `R16G16B16A16_FLOAT`，HDR）→ 1920×1080（LDR）**。
每帧一次，位置在 `CDC25F42`(4960, 400×225→1600×900) 之后、`5EB60161`(1168, UI) 之前。

**但 `GP_upscale.txt` 的候选表里没有这一行。** 报告自己写着 `distinct=32` —— 那是
`g_scaleSeen[32]` 的**硬上限**，先到先得。UI/调试用的高频 pass（如
`64x768 → 1920x1080`，hits=95,828）把表占满，每帧只出现 1 次的真·拉伸反而进不去。

> 所以此前"未命中 = 放大不在 PS 里"的判断**不成立**。这是探针的容量缺陷，不是引擎的结论。

## 结论二：`GP_replace_fsr1.txt` 的 size 字段已经过期，替换从未生效

- 配置里写的是 `5596 B682EAC0 GP_fsr1.dxbc`
- 本次会话实测该 shader 是 **`psLen=6204`**

`Hook_CreatePixelShader` 的匹配条件是 `size == len && crc == crc`，**6204 ≠ 5596 ⇒ 不命中**。
代理日志（`GP_shader.prev.log`，10-26 的旧会话）里 `REPLACE ps` 共 39 次，全部是
`len=5860 crc=42670B06`（tonemap），`B682EAC0` **一次都没有**。

> 这正是 2026-10-28 评审里说的"静默不生效"：不报错、不降级，只是什么也没发生。
> size 会随渲染分辨率/变体变化（早前一次是 5596，对应 852×480 的场景），所以这行配置
> 必须在目标分辨率下重新采样。

## 结论三：tonemap 在拉伸**之前**

`GP_bindseq.txt`（PSSetShader 的转换序列，含非四边形 pass）：

```
243  42670B06   2956     <- tonemap，psLen 2956 = 我们的 AgX 载荷（说明替换生效中）
246  B682EAC0   6204     <- stretch
```

tonemap 先于拉伸 ⇒ 若将来真接上 FSR1/时序放大器，它读到的是**已经 tonemap 过的 LDR 图**
（与 `fsr1_easu.hlsl` 头部注释一致）。但 `GP_passseq` 又显示拉伸的输入是 fmt 10（HDR），
两者需要下一次用 `GP_probe.txt` 复核——可能是同一 CRC 绑定了多个目标。

## 结论四（顺带）：MRT / 深度普查的旧数据

`GP_mrt_census.txt` / `GP_depth_timeline.txt` 是 2026-10-23 的 N1/N2 门禁产物，
与 `docs/RESULTS.md` 里的"双 NO-GO"一致，留作对照。

## 复现

```powershell
# 1) 部署（会顺便清理旧探针文件）
powershell -File inject\deploy.ps1
# 2) 复制探针开关
copy inject\presets\GP_probe_scale.txt.example "<游戏>\GP_probe_scale.txt"
# 3) 进游戏，Sampling 调到 70% 或 50%，玩几分钟
# 4) 读 <游戏>\GP_upscale.txt（或建 GP_upscale_dump.txt 立刻写一次）
```

## 待办（按这次数据改的）

1. ✅ **已修（2026-10-28）**：探针表 32 → **128 槽 + 按优先级淘汰**（`prio 2` = 读内部渲染尺寸
   或写 backbuffer）。报告多了一列 `prio`，`distinct=N/128` 直接暴露表是否满。
2. ✅ **已重采（2026-10-28 14:51）**：1440×810 下是 **5596 / B682EAC0**，正好等于
   `GP_replace_fsr1.txt`；1600×900 的 6204 只适用于那个分辨率。见
   [`1440x810/README.md`](1440x810/README.md)。
3. ✅ **已加工具（待跑一次）**：不必再用 MRT 普查。代理现在会挑出那个 prio-2 pass，
   把它的**输入**读回来，在 `GP_shader.log` 打一行：

   ```
   [GP] upscale input <crc> 1600x900 fmt=10: min=(..) max=(..) mean=(..) >1=..% >4=..% n=36864
   [GP] upscale input verdict: HDR / scene-linear -> tonemap before EASU
   ```

   `verdict` 若为 `display-referred [0,1]`，FSR1 EASU 可以直接换上去；
   若是 HDR，替换件里必须先 tonemap（AgX），否则画面会少一道色调映射。
   想在真实帧上复核：在 draw 前建 `GP_upscale_dump_input.txt`，会写出
   `GP_up_in_<crc>_<w>x<h>.raw`（打包行，8 bpp），用 numpy 看直方图。

> 无头验证：`python tools\probe_smoke_test.py`（8/8 PASS，覆盖 800×450 → 1600×900 的
> prio-2 记录、半浮点解码、HDR verdict、raw dump）。

## 后记：1440×810 复采（14:47–14:51）

同一套探针在 Sampling 75%（1440×810 → 1920×1080）下采到：

- `GP_upscale.txt`：`5596 B682EAC0`，`1440x810 → 1920x1080`，hits=6579；
- `GP_bindseq.txt`：tonemap `42670B06 / 2956` 在 idx 232，stretch `B682EAC0 / 5596` 在 idx 235；
- 结论：`psLen` 随分辨率变（1600×900 = 6204，1440×810 = 5596），配置里的
  size 只对目标分辨率有效。原始文件见 [`1440x810/`](1440x810/)。
- 仍未做：把 `GP_fsr1.dxbc` 真正挂上去的 A/B。
