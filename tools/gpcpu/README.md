# gpcpu · CPU 归因工具（DS + 客户端）

> 配套文档：[docs/20-client-cpu-forensics.md](../../docs/20-client-cpu-forensics.md)
> 本目录只放源码与脚本，不包含编译产物（DLL）。

## 组成

| 文件 | 类型 | 作用 |
|---|---|---|
| `gpmain.cpp` | DLL | 单线程（rvMain）RIP 采样，1 ms |
| `gpwatch.cpp` | DLL | 多线程采样 + 线程桶 + 模块 + 名字表 + 30 s 快照 |
| `gpmeasure.cpp` | DLL | 函数序言挂钩计数器（只计数，不改语义） |
| `gpgate2.cpp` / `gpgate3.cpp` | DLL | 目标获取调用点门控（时间相位 / 成对块）——实验用，已否决 |
| `build_*.bat` | 构建脚本 | 调用 VS2022 BuildTools 编译对应 DLL |
| `saturate2.ps1` | DS | AI 负载梯度 + 逐线程 CPU |
| `gaterun2/3.ps1`、`ab5.ps1`、`ab_beh.ps1` | DS | 门控 A/B、开火行为审计 |
| `watchtest.ps1`、`measuretest.ps1` | DS | 采样器 / 计数器的无头验证 |
| `threadcpu.ps1` | DS | 进程内逐线程 CPU 归属 |
| `pe.py`、`xrefs.py`、`dump.py` 等 | 分析 | PE/.pdata 解析、RVA→函数、反汇编、xref |

## 构建

需要 VS2022 BuildTools（含 VC++ x64）。

    build_watch.bat      -> gpwatch.dll
    build_measure.bat    -> gpmeasure.dll
    build_main.bat       -> gpmain.dll
    build_gate2.bat      -> gpgate2.dll
    build_gate3.bat      -> gpgate3.dll

## 使用要点

### gpwatch（采样器）

配置文件 `GP_watch.cfg`（与 DLL 同目录）：

    interval_ms  duration_s  threads_per_round  start_delay_s
    # 例：5 180 2 12   （5 ms 间隔、180 s、每轮主线程+1 个轮转线程、注入后延迟 12 s 开始）

- `GP_watch.names`：`RVA=标签`，输出里直接显示函数名
- 输出：`GP_watch.txt`（结束）+ `GP_watch_30s.txt`…（每 30 s 快照）
- 线程桶：`MainThrd / rvMain / rvRender / render / EngineDD11 / d3d11 / DXGI / Audio / Job# / enfWorkShort / enfWorkLong / PHYSSim / udpNet / IOCP`

### gpmeasure（序言计数）

`GP_measure.cfg`：

    rva=169B288
    back=169B290
    bytes=4889AC2490000000

`bytes` 是被覆盖的整条指令（必须与 `rva` 处字节一致，否则拒绝安装），`back` 是其后地址。
输出 `GP_submit.txt`：`calls` 与 `calls_per_s`。

## 注意

- **仅限单人/编辑器**，不要在有 BattlEye 的联机里用。
- 采样靠挂起线程，会带来 10–30% 开销；采样期间不要做性能对比。
- `funcs.bin` 必须与目标二进制一致（客户端 `funcs_client.bin` / 服务器 `funcs_server.bin`）。
- 客户端 `MainThrd` 桶为空是正常的：客户端主线程名是 `rvMain`。
- `.ps1` 里含本机绝对路径（仓库、游戏目录、profiles），换机器需要改。
- `gpmeasure` 会改写游戏代码序言，重启游戏即恢复。
- `GP_watch.names.example` 是 2.22 客户端的 RVA→名字表，`docs/20` 的结论靠它才可读；
  复制为 `GP_watch.names` 放进游戏目录即可（**必须**与目标版本一致，A3 更新后 RVA 会变）。
