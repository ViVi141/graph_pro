# 13 · CPU 热点可行性门禁（C0–C4）

日期：2026-10-22  
前提：画面旁路（docs/12）已结案；本路线目标是**帧时间**，不是画质。  
已知硬约束见 [11-re-findings.md](11-re-findings.md)：不可替换 `World::Simulate`；AI/寻路/clutter 已是作业线程。

---

## 总览

| Gate | 内容 | 通过条件 | 工具 |
|---|---|---|---|
| **C0** | 确认 CPU 瓶颈 | 半分辨率 FPS 相对全分辨率涨幅 **&lt; 15%** | 目测 / PresentMon / `diag_fps` |
| **C1** | RIP 采样 Top 函数 | ≥5 分钟有效样本；Top20 可复现 | `gpsample` + `funcs.bin` |
| **C2** | 热点叶子调用计数 | 选出 1–3 个可 hook 叶子 | `gpcount` + cand hooks |
| **C3** | Rust/SIMD 替换 A/B | 同场景帧时间降 ≥5%，稳定 | 自定义替换 DLL |
| **C4** | 版本指纹 + 回退 | 补丁失败走原路径 | 部署脚本 |

当前交付：**C0 清单 + C1 采样链路**（不含 C2+ 替换实现）。

---

## C0 · 分辨率对照（固定场景 = YAAB）

**标准场景：Yet Another Arma Benchmark（YAAB）**。C0 / C1 / C3 的 A/B **必须同一任务、同一 View/Object 距离**。

**已测通过（2026-10-22，见 `extract/cpu_samples/c0_notes.txt`）**：

| 项 | 全采样 | 半采样率（窗仍 1080p） |
|---|---|---|
| YAAB Avg FPS | **64.8** | **68.6** |
| View / Object | 1600 / 1300 | 同左 |
| 叠加层 | CPU~143% GPU~76% | CPU~106% GPU~82% |
| 比值 | — | **1.06（+6%）** |

**裁决：CPU-bound（GO → C1）**。半采样几乎不涨帧，GPU 占用略升也救不了帧率。

等价测法：改窗到 960×540，或只把渲染/采样率减半（窗保持 1080p）——以 YAAB Average FPS 对比为准。  
**不要**部署 `d3d11.dll` 代理。

---

## C1 · RIP 采样（在 YAAB 一轮内完成）

**原理**：周期性挂起线程读 RIP，按 `.pdata` 函数区间计命中。**不改代码**，比 cand hook 更安全。

### 准备（一次性）

```powershell
cd inject\counter
powershell -NoProfile -ExecutionPolicy Bypass -File prepare_funcs.ps1
.\build_sample.bat
powershell -NoProfile -ExecutionPolicy Bypass -File deploy_sample.ps1
```

`GP_sample.txt` 格式：`interval_ms auto_dump_sec max_min`  
**YAAB 推荐：`50 60 5`**（50ms 间隔，降低挂起开销；每 60s / 结束时 dump；最多 5 分钟）。  
1ms 间隔样本更多，但会明显拉低 FPS，只适合短测定位。

### 运行

1. 启动 **Arma3_x64**（可保留你的 `-enableHT` / `-malloc=mimalloc`），进入 YAAB。  
2. **Benchmark 一开始**就另开终端注入：

```powershell
cd inject\counter
powershell -NoProfile -ExecutionPolicy Bypass -File attach_sample.ps1
```

3. 让 YAAB 完整跑完（约 2 分钟；需要更多样本可连跑 2–3 轮）。  
4. 结果弹窗出来后立刻：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File dump_sample.ps1
```


在结果里同时记下本次 YAAB Average FPS（采样本身会轻微拉低 FPS，C3 对比时用**不采样**的干净轮作基线）。

产物：

| 文件 | 位置 |
|---|---|
| `GP_sample.log` | 游戏目录（追加） |
| `GP_sample_top.txt` | 游戏目录（覆盖为最新 Top） |
| `extract/cpu_samples/top_*.txt` | dump 脚本自动备份 |

### 标注（可选）

```powershell
python tools\annotate_sample.py D:\SteamLibrary\steamapps\common\Arma 3\GP_sample_top.txt
```

会把已知 RVA（如 `World::Simulate`）和粗粒度标签打到 stdout / `extract/cpu_samples/`。

### C1 通过标准

- `total samples` 建议 **≥ 5×10⁴**（视线程数与时长）。  
- Top 表稳定：两次 dump 的前 10 名 RVA 重叠过半。  
- 标出每个 Top 项：`编排器 / 作业体 / 叶子候选 / 系统(DXGI/驱动)`。  
- **编排器**（如 `Simulate`）只作上下文，不做替换目标。

### C1 实测（YAAB · 2026-10-22）

| 指标 | 值 |
|---|---|
| 间隔 | 50 ms（`GP_sample.txt` = `50 60 5`） |
| exe 内命中 | ~2.5k |
| exe 外 miss | ~132k（**命中率 ~1.8%**） |
| Top1 | `0x01A249F0` 16 路跳转分发（docs/11），仅 ~1.8% of exe hits |
| 形态 | **极平坦**；含 memcmp 风格小函数、若干 SIMD 中段 |

**裁决：单叶子替换 NO-GO**（没有占支配地位的可替换热点）。  
优先：**C1b 按模块归因**（ntdll / d3d11 / dxgi / mimalloc），以及复杂度/AI 等软加速。详见 `extract/cpu_samples/c1_yaab_notes.txt`。

### C1b · 模块归因（已实现）

同一次采样额外写 `GP_sample_modules.txt`（按模块命中占比）。`gpsample` 需用 C1b 版重新 `build_sample.bat` + `deploy_sample.ps1`（**须先退出游戏**才能覆盖 DLL）。

```powershell
.\build_sample.bat
powershell -NoProfile -ExecutionPolicy Bypass -File deploy_sample.ps1
# YAAB 开始后 attach；结束后 dump —— 先看 modules 再看 top
```

解读：`ntdll`/`kernel*` 高 → **多半是线程阻塞**（挂起采样偏差），不要当成计算热点。  
应看去掉 `ntdll`+`win32u` 后的重归一化占比。

### C1b 实测（YAAB · 2026-10-22）

| 模块 | 原始% | 去等待后% |
|---|---|---|
| ntdll.dll | 92.6 | （排除） |
| win32u.dll | 3.4 | （排除） |
| **Arma3_x64.exe** | 2.5 | **~63** |
| **igd10umt64xe**（Intel UMD） | 0.9 | **~23** |
| PhysX* | 0.3 | **~8** |
| d3d11.dll | 0.1 | ~2 |
| mimalloc | 0.02 | ~0.5 |

**裁决**：叶子 SIMD 仍 NO-GO；有效杠杆是 **减引擎工作量（复杂度/AI）** + **减 iGPU 驱动负载（画质/draw）** + 按需减 PhysX。详见 `extract/cpu_samples/c1b_yaab_notes.txt`。

### 清理

```powershell
powershell -File inject\counter\remove_sample.ps1
```

完全退出游戏后再删，避免 DLL 占用。

---

## C2–C4（后续，未实现）

- **C2**：对 C1 标为叶子的 RVA 生成 `cand_hooks`，用 `gpcount` 记调用次数。  
- **C3**：无状态叶子 → Rust/SIMD；同场景 A/B 帧时间。  
- **C4**：exe 版本/大小指纹；hook 失败不崩溃。

预期：单叶子常见 **数个百分点** 帧时间改善；若 C1 Top 全是提交/驱动/编排，则 **NO-GO**，改走复杂度/视距软加速。

---

## 与画面路线的关系

| | 画面旁路 (docs/12) | CPU 热点 (本文) |
|---|---|---|
| 依赖 RenderDoc | 否 | 否 |
| 部署物 | `d3d11.dll` 代理 | 仅 `gpsample.dll` 注入 |
| 同时开 | **不要**与代理混用采样 | 干净目录 |

---

## 风险

- 采样会短暂挂起线程，可能引入轻微卡顿；不要在正式对局里用。  
- 部分环境反作弊/BattlEye 可能拒绝注入 → 仅单人/离线/关 BE 私服。  
- `misses` 偏高通常是 RIP 落在模块外（驱动/系统）；可忽略。
