# 14 · World::Simulate 在做什么（静态逆向）

日期：2026-10-22 · 目标：`Arma3_x64.exe` 2.22 · RVA **`0x11527E0`** · 大小 **11093 B**

原始反汇编摘要：`extract/cpu_samples/simulate_deep.txt`  
续挖（定名/时间线）：`extract/cpu_samples/simulate_p0_p1.txt`

## 1. 函数角色（结论先行）

`World::Simulate(float dt, bool&, bool&)` 是**主线程帧模拟编排器**，不是重计算核：

- 约 **2498** 条指令，**265** 次直接 `call` → **147** 个不同目标
- 另有 **107** 次间接调用；函数体内向后跳转约 **17**（局部循环/重试）
- 栈帧很大（`sub rsp, 0x6d8` 量级）：本地状态机 + 多个作业/future 句柄
- RTTI 显示其内部嵌套了 **InvokerLambda 作业**（含 Entity 遍历 lambda、SoundMainTask）

与 C1/C1b 一致：**主线程把门闩串起来**；工人线程跑被投递的作业，采样里大量 `ntdll` 等待。

## 2. 与 Simulate 绑定的 RTTI（引擎自己贴的标签）

| 含义 | 说明 |
|---|---|
| `SoundMainTask (from Simulate)` | `.?AVSoundMainTask@?1??Simulate@World@@QEAAXMAEA_N0@Z@` |
| `job: Simulate InvokerLambda` | `.?AU?$InvokerLambda@V<lambda_1>@?HA@??Simulate@World@@QEAAXMAEA_N0@Z@XI@@` |
| `job: Simulate InvokerLambda` | `.?AU?$InvokerLambda@V<lambda_2>@?1??Simulate@World@@QEAAXMAEA_N0@Z@XI@@` |
| `job: Simulate/Entity lambda` | `.?AU?$InvokerLambda@V<lambda_1>@?1???R1?HA@??Simulate@World@@QEAAXMAEA_N0@Z@QEBA@I@Z@_NPEA…` |
| `SimulateCloudletsAndSound → JobFuture` | 云团+声音异步，返回 `enf::JobFuture` |
| `PrepareDrawPrepareCloudlets → JobFuture` | 绘制准备侧云团作业 |

解读：Simulate **主动投递并行作业**（lambda / Sound / Cloudlets），自己留下编排与汇合。

## 3. 调用画像

### 按调用次数（编排痕迹）

| 次数 | RVA | 标签 |
|---|---|---|
| 17 | `0x0110AD20` | tiny counter/clear ([rcx+8]) |
| 10 | `0x003859C0` | helper (called 10x) |
| 8 | `0x00BA53C0` | outside_pdata? |
| 6 | `0x01127F80` | helper (6x) |
| 6 | `0x00145D80` | helper (6x) |
| 6 | `0x0013DB60` | helper (6x) |
| 5 | `0x0112FC20` | fn size=350 |
| 5 | `0x011272A0` | fn size=280 |
| 4 | `0x001271B0` | outside_pdata? |
| 4 | `0x0012A940` | fn size=57 |
| 4 | `0x01A249F0` | 16-way jump dispatcher (job/type switch) |
| 4 | `0x00140B70` | fn size=236 |
| 4 | `0x0112F8B0` | fn size=151 |
| 4 | `0x01260C00` | large subsystem @ World+0xac8 path |
| 4 | `0x00398960` | fn size=59 |

### 大块被调（更可能是真子系统）

| 次数 | RVA | size | 标签 |
|---|---|---|---|
| 2 | `0x011456D0` | 5433 | large fn size=5433 |
| 1 | `0x01155340` | 4604 | large fn size=4604 |
| 4 | `0x01260C00` | 2595 | large subsystem @ World+0xac8 path |
| 1 | `0x011566C0` | 2104 | large fn size=2104 |
| 4 | `0x01A249F0` | 1645 | 16-way jump dispatcher (job/type switch) |
| 2 | `0x00384D00` | 1304 | fn size=1304 |
| 1 | `0x01263C50` | 1255 | fn size=1255 |
| 1 | `0x00145250` | 1233 | fn size=1233 |
| 1 | `0x0027A460` | 1069 | fn size=1069 |
| 1 | `0x01156F00` | 995 | fn size=995 |
| 2 | `0x0162CFA0` | 773 | fn size=773 |
| 1 | `0x0014C770` | 751 | fn size=751 |

## 4. 阶段草图（按函数体偏移均分 8 段）

静态分段，不是运行时 timer；用于看「前/中/后段在调谁」。

- **phase0** `0x11527E0`–`0x1152D4A` （38 calls）：`0x1271B0`×2, `0x6C98C0`×2, `0x1BA9A0`×2
- **phase1** `0x1152D4A`–`0x11532B5` （42 calls）：`0x140B70`×3, `0x11272A0`×3, `0xBA53C0`×3
- **phase2** `0x11532B5`–`0x115381F` （29 calls）：`0x112FC20`×2, `0x112F8B0`×2, `0x3859C0`×2
- **phase3** `0x115381F`–`0x1153D8A` （35 calls）：`0x3859C0`×3, `0x398960`×3, `0x112F8B0`×2
- **phase4** `0x1153D8A`–`0x11542F5` （39 calls）：`0x1127F80`×4, `0x1143F60`×3, `0x141040`×3
- **phase5** `0x11542F5`–`0x115485F` （25 calls）：`0x10FB420`×4, `0x3859C0`×3, `0xBA53C0`×3
- **phase6** `0x115485F`–`0x1154DCA` （26 calls）：`0x110AD20`×17, `0x1BC2F0`×3, `0x1011AD0`×2
- **phase7** `0x1154DCA`–`0x1155335` （31 calls）：`0x145D80`×3, `0x13DB60`×3, `0x36DD40`×2

## 5. 关键被调者在干什么

### `0x1A249F0` — 16 路跳转分发（调用 4 次）

```
cmp r8, 0xF
ja  default
mov r9d, [table + r8*4]
jmp r9
```

是**类型/消息/作业码分发器**，不是数值内核。Simulate 多次进入不同 case。

### `0x110AD20` — 10B，调用 17 次

访问并清理 `[rcx+8]` 一类计数/链表头，典型 **容器复位 / 遍历哨兵**。出现次数多说明 Simulate 在多个阶段反复「清空本帧结构」。

### `0x1260C00` — ~2.5KB，调用 4 次

大栈帧子系统，开场即读 `World+0xAC8`；在 Simulate 中段与其它大块穿插调用 4 次。  
更像挂在 World 上的**真模拟子模块**（定名需再跟虚表），不是叶子。

### 大块定名（P0 续）

| RVA | size | 置信度 | 工作名 | 证据 |
|---|---|---|---|---|
| **`0x1155340`** | ~4604 | **高** | **本帧实体/载具仿真步进** | 仅 Simulate 调用；`mtVehS`；**`{error} Strange - simulation started twice in a frame?`**；`World+0xC10` 本帧已仿真旗 |
| `0x1260C00` | ~2595 | 中 | 环境/天气相关（`World+0xAC8`） | 调用者带 `startWeather` / `CfgWorlds` |
| `0x11456D0` | ~5433 | 中 | 世界/任务状态维护 | 调用者带 `worldName` / mission* / `Landscape` |
| `0x11566C0` | ~2104 | 中高 | 加载/内存过渡 | 紧挨 `SUPERFLUSH` + `Loading screen closed` |
| `0x1263C50` | ~1255 | 低 | 环境辅助？ | 字符串 `sligt`；紧跟 `0x1260C00` |

### Simulate 内调用时间线（节选）

```
early:  16-way dispatch x2
        -> 0x1155340   [本帧 simulation step / 防双跑]
mid:    0x1260C00
        -> 0x11566C0 + SUPERFLUSH / Loading screen closed
        -> 0x1260C00 xN + 0x11456D0 x2 + 0x1263C50
late:   0x110AD20 x17  [批量清本帧容器]
        16-way dispatch x2
全程:   间接 call ~107（vtable/job），各 phase 都有
```

汇合点分散在间接调用里，不是单一 `Wait` 大闸。另有 RTTI：`SimulateCloudletsAndSound` / `PrepareDrawPrepareCloudlets` → `JobFuture`。

### 字符串泄露出的阶段语义

| 字符串 | 含义 |
|---|---|
| `simulation started twice in a frame?` | 本帧仿真重入保护（钉死 `0x1155340`） |
| `SUPERFLUSH Pre/Post-Report` / `freed %s` | 内存/流资源强刷 |
| `Loading screen closed` | 加载界面关闭路径 |
| `Array index out of range` | 容器断言 |
| `Warning: Hash of %s is wrong.` | 资源校验警告 |

## 6. `0x1155340` 内部（P0′ · 已拆）

全文：`extract/cpu_samples/simstep_0x1155340.txt` · `simstep_deep.txt`

| 项 | 值 |
|---|---|
| 大小 | 4604 B · ~1053 insn |
| 直接 call | 76 → 43 目标 |
| 间接 call | **30**（全部在 ParallelFor **之后**） |

### 结构

```
[准备 / 旗位]
    │
    ▼
call 0x10FCE10   「ParallelFor sync / pFor / subSync / Subdivide」
    │              ← 主线程在此等待工人（明确等待边）
    ▼
大量 tiny helper + 间接 call×30   ← 更像逐对象 vtable 仿真
    │
    ▼
mtVehS / 「simulation started twice」检查（World+0xC10）
```

### 要点

- **`0x10FCE10`**：引擎自带的 **ParallelFor 汇合**；字符串钉死。这是目前找到的、最干净的「主线程等工人」边。
- 高频 `0x1133850`（8×）→ 再调小函数；`0x1108700` 内又进 **16 路分发器**。
- 直接被调者大多是小函数；**重活在 ParallelFor 工人侧 + 间接虚调用**，不在这 43 个直接 call 的函数体本身。

## 7. 对「CPU 吃不饱 / 帧被拖住」的含义

1. Simulate 编排 → 进入 **`0x1155340` 本帧仿真**。
2. 仿真步进里很早 **`ParallelFor sync`**：工人在算时主线程阻塞 → 采样见 `ntdll`（YAAB 实测约占 simstep **15.6%**）。
3. sync 之后主线程还要跑 **30 次间接调用**（串行虚调用尾）——约占 simstep **84%**，是更大头。
4. 优化叶子几乎摸不到这条链；减实体/载具数量 → 减轻 ParallelFor **和** 后面的虚调用尾。

## 8. ParallelFor 提交/汇合（P2 静态结论）

全文：`extract/cpu_samples/parallelfor_xref.txt`

| 事实 | 含义 |
|---|---|
| **`0x10FCE10` 的唯一调用者是 `0x1155340`** | 这条 ParallelFor 专属于本帧仿真步进 |
| sync 前只有准备型小 call | **不是**「别处先 enqueue、此处只 wait」 |
| 函数序言：`count < 2` 则主线程串行跑 functor | 少实体时根本不进工人 |
| 字符串另有多份模板实例（`0x14E680` 等） | 引擎通用 ParallelFor 家族；仿真步进用的是这一份 |
| 调用点构造 functor 后直接 `call sync` | **划分 + 执行 + 汇合一体** |

## 9. 运行时计时（P1′ · gptimer）

`inject/counter/gptimer.dll` **v4.1**：只改两处 E8（`0x1153052`→simstep、`0x1155624`→ParallelFor），近距 stub + QPC。

### YAAB 实测（2026-10-23 · v4.1）

| | calls | total_ms | avg_ms | max_ms |
|---|---:|---:|---:|---:|
| **simstep** `0x1155340` | 12093 | 43508 | **3.60** | 23.4 |
| **ParallelFor** `0x10FCE10` | 12093 | 6771 | **0.56** | 2.71 |
| **parfor / simstep** | | | **15.6%** | |

- 调用 1:1，与静态「唯一点 ParallelFor」一致。
- 汇合约占 simstep **1/6**；约 **84%** 在 sync **之后**的串行/间接链。
- 只优化工人侧上限约 15%；主杠杆是 **P3（sync 后 30 个间接 call）**。

勿与 `gpsample` / `d3d11` 同时挂。

## 10. P3 · sync 后间接 call 画像

静态：`extract/cpu_samples/simstep_indirect.txt`

| 组 | 次数 | YAAB 实测 |
|---|---:|---|
| `vcall [rax+0x2A0]` | 8 | v1.1：~1ms / 18986 calls，唯一目标 RVA `0x2033A0`（空壳） |
| IAT rip x2 | 2 | v1.1：~3ms |
| `vcall+0x210` | 1 | YAAB **0 calls** |
| **`call r12`** | 8 | **v1.2 待测**（与 2a0 配对，疑似真活） |
| **`call r15`** | 6 | **v1.2 待测** |

结论（v1.1）：已测 6B 站点不是那 84%；墙钟应在 **r12/r15**。

## 11. 下一步

| 优先级 | 目标 |
|---|---|
| **YAAB + gpindirect v1.2** | 实测 call_r12 / call_r15 ms |
| 定名 r12/r15 目标 RVA | pdata / 字符串 |
| P4 | 少实体 `count < 2` |


---

脚本：`simulate_*.py` · `simstep_*.py` · `parallelfor_xref.py` · `gptimer.cpp`
