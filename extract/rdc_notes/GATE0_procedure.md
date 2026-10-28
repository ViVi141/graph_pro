# Gate 0 — RenderDoc 干净抓帧（操作单）

## 环境

- RenderDoc 1.46：`C:\Program Files\RenderDoc\qrenderdoc.exe`
- 游戏：`<ARMA3>`
- **必须先移走代理**：把游戏目录下的 `d3d11.dll` 改名为 `d3d11.dll.gp_off`（否则与 RenderDoc 抢 hook）

## 步骤（优先：先正常进游戏再注入）

RenderDoc **Launch Application** 在本机容易直接触发  
`DX11 error : Error creating shader : DXGI_ERROR_DEVICE_REMOVED`。  
单独开游戏正常、一开 RenderDoc 就炸 = 工具注入问题，不是完整性损坏。

**推荐顺序：**

1. 确认游戏目录**没有**我们的 `d3d11.dll` 代理（可用 `inject\remove.ps1`；备份文件不要叫 `d3d11*.dll`）
2. Steam / 启动器加参数：`-window`（窗口模式，降低全屏独占 DEVICE_REMOVED）
3. **先正常启动** Arma，进到主菜单或任务（3D 已起来）
4. 打开 qrenderdoc → File → **Inject into Process** → 选 `arma3_x64.exe`
5. 等状态变成捕获就绪后，前台按 F12 抓一帧 → 另存 `extract/rdc_notes/arma3_clean.rdc`

**若仍 DEVICE_REMOVED：**

- Tools → Options → Replay：关掉过严校验（Verify Buffer Access 等）
- 不要用「经 Steam 启动 + Capture Child」双注入
- 核显上 RenderDoc 抓 A3 本身就不稳；抓不到就停，用 `GATE0_proxy_substitute.md`（Gate 0 屏幕空间路线已够用）

**不要用：** Launch Application 直接拉 `arma3_x64`（本机已复现 CreateShader 掉设备）。

## 要在 RDC 里记录的字段

填入同目录 `GATE0_results.md`：

| 项 | 填空 |
|---|---|
| Draw 总数 | |
| Unique IB | |
| 三角形量级 | |
| 场景几何 API（Draw / DrawIndexed / Instanced / ExecuteCommandList） | |
| 某物体 VS cb 是否含 world（offset） | |
| 是否存在法线/MRT | |
| PP 顺序（SSAO→…→tonemap） | |

## 本仓库已完成的替代证据（无 RDC 时）

见 `GATE0_proxy_substitute.md`：代理 drawlog + `GP_cb_*.raw` 矩阵扫描 + docs/10 实测。
在交互式 RDC 尚未落盘前，Gate 0 以「替代证据」裁决屏幕空间路线，几何/BVH 路线保持未证实。
