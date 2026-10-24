# 无头 DS · CPU 效率探索（续）

日期：2026-10-24  
工具：`server\run-cpu-sample.ps1` / `server\ab-ai-load.ps1` / `gpsample` / `tools/server_top_name.py`  
Profile：`%LOCALAPPDATA%\GP_arma_server`（路径必须无空格）

---

## 1. 测量陷阱（重要）

| 指标 | idle (0 AI) | AI×48 (~193 units) | script nearestObjects 压力 |
|---|---|---|---|
| `diag_fps` | ~28 | ~28 | ~28 |
| `gpsample` exe_fn | **17** | **570** | 27 |
| exe 模块占比 | 0.07% | **2.20%** | 0.09% |

**`diag_fps` 在本机 DS 上接近常数，不能用来评判 CPU 效率。**  
有效指标：`GP_sample_modules.txt` 里的 **exe_fn / arma3server 占比**（或固定工作的 `workMs`）。

原始 JSON：`ab_sample_metric.json` · `ab_ai_extreme.json`

### gpsample 组数梯度（~70s / 50ms 间隔）

| nGroups | 约单位数 | exe_fn | exe 模块 % |
|---|---|---|---|
| 0 | 1 | 17 | 0.07 |
| 16 | ~64 | 196 | 0.73 |
| 48 | ~193 | 570 | 2.20 |

近似线性：减半 AI ≈ 减半 exe 热度。软加速曲线 **GO**。

---

## 2. 软杠杆矩阵（gpsample · 同协议 ~65s）

脚本：`server\ab-soft-levers.ps1` · 汇总 JSON：`ab_soft_levers_all.json` + `ab_physx_on.json`

| 杠杆 | 对比 | exe_fn | exe% | 裁决 |
|---|---|---|---|---|
| **AI 数量** | 0 / 16 / 48 组 | 17 / 196 / 570 | 0.07 / 0.73 / 2.20 | **GO**（近似线性） |
| **setSkill** | 0.1 vs 1.0（48 组+巡逻） | 548 vs 536 | 2.09 vs 2.10 | **NO-GO**（本负载下无差） |
| **Waypoint/移动** | 禁 PATH/MOVE vs CYCLE 巡逻 | **152 vs 557** | **0.65 vs 2.15** | **GO**（~3.7×，最强软杠杆） |
| **PhysX 载具** | 0 vs 24 MRAP+crew（各组 24） | 276 vs 312 | 1.09 vs 1.20 | **弱 / 近 NO-GO**（PhysX 模块仍 &lt;0.02%） |

解读：
- 无头侧真正吃 CPU 的是 **AI 寻路/移动模拟**，不是 skill 档位，也不是轻量载具 PhysX。
- 任务优化优先级：**少单位 &gt; 禁无意义移动/站岗用 disableAI PATH &gt; 减载具**；`setSkill` 不必当性能旋钮。
- `diag_fps` 全程 ~28，会误判上述全部杠杆。

---

## 3. 叶子替换 —— 仍 NO-GO

AI48 下 Top（`top_ai48_*.txt`）：

| pct_exe | RVA | size | 备注 |
|---|---|---|---|
| 10.5% | `0x0140D288` | 785 | unlabeled mid_fn |
| 10.0% | `0x011DCE70` | 1698 | unlabeled |
| 6.1% | `0x01088D30` | 690 | unlabeled |
| … | flat | | Top1 仅 ~10% of exe |

- `ParallelFor sync` / `simstep_guard` / `mtVehS` 的 owner **不在** sample Top
- RTTI 仍有 `Simulate@World` / `PerformAI` / `ProcessSearching` 的 InvokerLambda（作业线程），与客户端 docs/11 一致
- **单叶子 SIMD/Rust 替换：NO-GO**（与 YAAB C1 同构）

命名产物：`server_top_named.txt` · `server_top_disasm.txt`  
工具：`tools/server_top_name.py` · `tools/server_disasm_tops.py`

### Top 反汇编标签（server）

| RVA | 粗标签 | 含义 |
|---|---|---|
| `0x0140D288` | **terrain/grid index** | 对 `[r13+0xbd4/bd8]` 做边界检查 + 位移，像地形格采样 |
| `0x011DCE70` | **field/net iter** | 清 `[rcx+0x148]`；多次调用 `0x11C8D00`（带 Unexpected field type） |
| `0x01088D30` | **float3 距离叶子** | 纯 SSE `subss/mulss/addss`；仅 1 个 E8 —— **唯一像样的叶子**，但仅 ~6% exe |
| `0x00E32A82` | **max-scan 叶子** | 循环 `maxss` 扫 `[obj+0xa8]` |
| `0x011C8D00` | **field 解析器** | 6 KB，76 次 call；字符串 Unexpected field type |

叶子 `0x1088D30` 可作 C2 计数候选，但占比太低，单独替换预期 &lt;1% 总 CPU。

---

## 4. Patch / 优化候选总表

| 候选 | 类型 | 裁决 | 证据 |
|---|---|---|---|
| 减少 AI 数量 | 任务设计 | **GO** | 组数梯度 exe_fn |
| `disableAI "PATH"` / 少 waypoint | 任务设计 | **GO** | wp_none vs wp_cycle |
| 降低 `setSkill` | 任务设计 | **NO-GO**（性能） | skill_low≈skill_high |
| 少轻型载具 | 任务设计 | **弱** | physx_on +13% exe，PhysX% 仍极低 |
| 替换 `0x1088D30` 距离叶 | 二进制补丁 | **NO-GO** | 仅 ~6% exe，平坦 profile |
| 替换 `World::Simulate` / PFor | 二进制补丁 | **NO-GO** | docs/11 + 不在 sample Top |
| d3d11 画面代理 | — | **无关/冲突** | 勿与 gpsample 同挂 |

---

## 5. 定量开销表（续）

AI 人数 × 路点模式的网格采样与线性拟合见 **[17-ai-wp-cost-table.md](17-ai-wp-cost-table.md)**  
（`exe_fn ≈ a·U + b`；移动约 **2.6×** 站岗；路点条数几乎无关）。

---

## 6. 一键命令

```powershell
# 完整采样
powershell -NoProfile -ExecutionPolicy Bypass -File server\run-cpu-sample.ps1 -SampleMinutes 3

# 软杠杆（skill / wp / physx）
powershell -NoProfile -ExecutionPolicy Bypass -File server\ab-soft-levers.ps1 -Variant wp_none
powershell -NoProfile -ExecutionPolicy Bypass -File server\ab-soft-levers.ps1 -Variant wp_cycle

# 命名 / 反汇编 Top
python tools\server_top_name.py
python tools\server_disasm_tops.py
```
