# 1440×810 探针会话（2026-10-28 14:47–14:51）

同一份 `GP_probe_scale.txt`，在 Sampling 75%（内部 1440×810 → backbuffer
1920×1080）下复采。四个文件都是从游戏目录直接拷出的原始产物：

| File | Contents |
|---|---|
| `GP_upscale.txt` | 整局放大候选（`prio` / 输入输出 / `psLen` / `psCrc` / hits） |
| `GP_bindseq.txt` | 一帧的 PSSetShader 顺序（含 tonemap / stretch） |
| `GP_passseq.txt` | 一帧的 fullscreen pass + 采样源颜色统计 |
| `GP_shaders.txt` | 本局创建过的全部 pixel shader（crc / len） |

## 关键行

`GP_upscale.txt`：

```
2  1440x810  1920x1080  10/28  5596  B682EAC0  Draw  hits=6579
2  64x768    1920x1080  28/28   816  9576A9FE  Draw  hits=206057
```

`GP_bindseq.txt`：

```
232  42670B06  2956    <- tonemap (our AgX payload; original is 5860)
235  B682EAC0  5596    <- final stretch
```

## 结论

- 放大**是**一个全屏 PS pass：`1440x810 (RGBA16F) → 1920x1080 (RGBA8)`。
- `tonemap` 在拉伸**之前**，所以拉伸读到的是已经 tonemap 过的 LDR 图。
- `psLen` 随内部渲染尺寸变化：**1600×900 时 6204，1440×810 时 5596**。
  `inject/presets/GP_replace_fsr1.txt` 写的是 `5596 B682EAC0`，因此只在这个
  分辨率下命中；换 Sampling 必须重采。
- 本帧 `GP_passseq.txt` 只有 2 个 pass（很可能是菜单/加载帧），不能用于判断
  完整后处理链；`analyze_capture.py` 现在会对此标低置信度。

## 未做的事

- 没有把 `GP_fsr1.dxbc` 真正挂上去做 A/B；这仍是一个待验证的替换件。
- 没有在 1600×900 下复验 6204 的失效；预期是 `REPLACE ps` 不出现。
