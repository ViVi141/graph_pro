### `0x1155340` 内部调用图（P0′）

- 大小 **4604 B**，直接 call **76** → **43** 目标，间接 **30**
- 自带串：`mtVehS`、`simulation started twice in a frame?`

#### 决定性发现

| RVA | 角色 |
|---|---|
| **`0x10FCE10`** | **ParallelFor sync**（`ParallelFor sync` / `pFor` / `subSync` / `Subdivide`） |
| 调用点 | `0x1155624`（simstep 前段） |
| 间接 call | **0 个在 sync 前，30 个在 sync 后** |

结构：准备 → **ParallelFor 汇合（主线程等待）** → 虚调用尾 / tiny helpers → 防双跑检查。

#### 其它高频

| 次 | RVA | 备注 |
|---|---|---|
| 8 | `0x1133850` | 中转，再调小函数 |
| 4 | `0x115B980` | 再调 `0x1133850` |
| 2 | `0x1108700` | 内部进 16 路分发器 |

全文：`simstep_0x1155340.txt` · `simstep_deep.txt`
