# Gate 0 替代证据（代理侧，2026-10-22）

RenderDoc 已安装，但干净 `.rdc` 需交互进游戏；下列为已落盘的等价证据。

## 绘制入口

来源：`docs/10-dll-options.md` 实测 + 游戏目录现存 `GP_cb_*.raw`。

- 300 Present 窗口内：约 34 次 Draw，**全部 `count=4`**（全屏后处理四边形）
- 每帧 2–3 个此类 Draw；`vs0` 常量缓冲固定 **240 字节**
- 场景地形/物体 **未出现**在 immediate-context 的 Draw/DrawIndexed 钩子里
- 引擎会还原部分 vtable 补丁；需每帧 `ReassertPatches`（否则 Draw 静默为 0）
- 已挂钩：Draw / DrawIndexed / Instanced / Auto / Indirect / ExecuteCommandList + 全部 CreateDeferredContext 变体

## 矩阵 / MRT

```
tools/scan_cb_matrix.py  →  0/40 GP_cb_*.raw 含仿射 4x4
```

结论：通过当前钩到的 PP draw 的 VS cb **读不到 world 矩阵**；未见法线 G-buffer（与 RESULTS 深度重建失败一致）。

## PP 顺序（来自 shdc 名 + 已验证替换）

候选链（命名，非 RDC 时序）：

1. SSAO 生成 / BlurHorz / BlurVert / SSAOFinal（已替换 Final）
2. Bloom / Glow
3. Tonemap（`PSPostProcessGlowNewFinal*`，size=5860 crc=42670B06 已替换）
4. AA（SMAA/FXAA）

插入点候选：Present 前（已有深度+颜色捕获）或 tonemap 替换点。

## Gate 0 裁决（替代）

| 问题 | 结果 |
|---|---|
| 场景几何 API | **未在 immediate 钩子中观测到** → 几何线 NO-GO，待 RDC 确认是否 deferred CB |
| world 矩阵 | **PP cb 中无** |
| 法线 MRT | **无证据** → 锁定深度+光源屏幕空间 |
| PP 顺序 / 插入点 | Present 侧可行（已有 depth srv DIRECT） |

**状态：Gate 0 有条件通过（屏幕空间旁路） / 几何旁路未通过。**
