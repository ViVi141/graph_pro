# 18 · 跨 CPU 任务流畅度估算

## 有没有？

**有相对估算，没有免校准的绝对 FPS 预言。**

| 已有 | 不能直接当的 |
|---|---|
| 本机 DS 上 AI/移动的线性开销（[docs/17](17-ai-wp-cost-table.md)） | `diag_fps`≈28 当流畅标准 |
| 用 **PassMark 单线程分** 把预算缩放到别的 CPU | 忽略 GPU/内存/模组后的精确帧率 |
| YAAB Average FPS（社区常用客户端对比） | 与「任意任务」一一对应 |

Arma 模拟偏 **单线程编排 + 作业线程**；跨机一阶近似用 **Single Thread Rating** 缩放站岗当量预算。

---

## 核心量：SEU（Standing-Equivalent Units）

来自本机拟合（移动/站岗斜率比 ≈ **2.63**）：

```
SEU = U_stand + 2.63 × U_move
```

路点条数可忽略（已移动后 1/2/5 条几乎同开销）；只区分 **站岗（禁 PATH）** vs **移动**。

目标机预算：

```
budget_target = budget_ref × (ST_target / ST_ref)
```

判定：`SEU / budget_target` → SMOOTH (≤0.85) / OK (≤1) / MARGINAL (≤1.25) / HEAVY。

---

## 用法

```powershell
# 看有哪些 CPU 预设
python tools\estimate_mission_cpu.py --list-cpus

# 校准说明
python tools\estimate_mission_cpu.py --calibrate-help

# 估算：96 巡逻 + 32 站岗，在 Ryzen 5 5600 上客户端能否流畅
python tools\estimate_mission_cpu.py --move 96 --stand 32 --cpu r5_5600 --role client
```

编辑 [`config/cpu_catalog.json`](../config/cpu_catalog.json)：

1. `reference.passmark_st` = 本机单线程分  
2. `budgets.client_smooth_seu` = 本机仍流畅时的最大 SEU（用实机或 YAAB 标定）  
3. 可选 `client_playable_seu` / `server_ok_seu`  
4. 在 `cpus[]` 增加朋友的 CPU

**未填预算前**，工具会报 `UNCALIBRATED`——避免假装精确。

---

## 建议标定流程（客户端）

1. 固定画质档（与发任务时一致）。  
2. 用 `GP_ServerTest` 同类负载或真实任务，逐步加移动 AI。  
3. 主观/PresentMon：目标 60 或 45 FPS 的最大 `U_move`（站岗另测）。  
4. `SEU = U_stand + 2.63*U_move` 写入 `client_smooth_seu`。  
5. 可选再跑一局 YAAB，记下 Average FPS，作为对外「这台机器档位」的公开锚点。

专用服：用 `server/sweep-ai-wp.ps1` + 实战 tick，填 `server_ok_seu`（服无渲染，预算通常高于同 CPU 客户端）。

---

## 局限

- ST 缩放误差在游戏负载上常见 **±15–30%**。  
- 模组、脚本 `nearEntities`、载具、视距会另开销——SEU 只覆盖 **步兵 AI 移动/站岗** 主项。  
- 核显/双显卡切换会毁客户端标定（与 CPU 估算无关）。
