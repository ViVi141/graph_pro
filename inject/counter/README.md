# CPU 采样器（gpsample）

不改游戏代码：注入后按 RIP 采样，写入 `GP_sample.log` / `GP_sample_top.txt`。  
完整门禁见 `docs/13-cpu-hotspot.md`。

本机若遇「禁止运行脚本」，一律加 `-ExecutionPolicy Bypass`（不要改系统策略）。

## 一键流程

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File prepare_funcs.ps1
.\build_sample.bat
powershell -NoProfile -ExecutionPolicy Bypass -File deploy_sample.ps1
# 启动 Arma3_x64 / YAAB 后：
powershell -NoProfile -ExecutionPolicy Bypass -File attach_sample.ps1
# 跑完：
powershell -NoProfile -ExecutionPolicy Bypass -File dump_sample.ps1
# 结束后：
powershell -NoProfile -ExecutionPolicy Bypass -File remove_sample.ps1
```

## 文件

| 文件 | 作用 |
|---|---|
| `gpsample.dll` | 采样 DLL |
| `funcs.bin` | 客户端 `.pdata` 函数表（默认 = client） |
| `funcs_client.bin` / `funcs_server.bin` | 双端备份 |
| `injector.exe` | `LoadLibrary` 注入 |
| `GP_sample.txt` | `interval_ms auto_dump_sec max_min`（YAAB 建议 `50 60 5`） |
| `GP_sample_modules.txt` | C1b：按模块命中占比 |
| `GP_sample_top.txt` | 主 exe 函数 Top（`pct_total` + `pct_exe`） |

覆盖 `gpsample.dll` 前须**完全退出** Arma。  
## 计时器（gptimer · ParallelFor / simstep）

崩溃修复：v1 wrapper 栈错位；v2 stub 分在 >2GB 外导致 `E9` 跳飞（AV at `A8350000`）；v3 prologue/ret-swap 约 1min 后 mimalloc AV；v4 只改两处 E8 call-site；**v4.1 修好 disp8：`[rsp+0x80]` 实为 `rsp-128`，导致 ms 膨胀到百万级——QPC 槽改用 disp32**。

```powershell
.\build_timer.bat
# 须先完全退出 Arma 再 deploy
powershell -NoProfile -ExecutionPolicy Bypass -File deploy_timer.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File attach_timer.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File dump_timer.ps1
```

产出 `GP_timer.txt`。注入后约 2.5s 才打补丁。勿与 `gpsample` / `d3d11` 同时挂。

## 间接调用计时（gpindirect · P3）

simstep 在 ParallelFor 后有 30 个间接 call。  
- v1.1：11×6B 站点合计 ~4ms（`vcall_2a0` 单目标 `0x2033A0`，可忽略）→ 热点不在那儿。  
- **v1.2**：只钩 `call r12`×8（偷 6）+ `call r15`×6（偷 9，勿再偷 5）。

```powershell
.\build_indirect.bat
powershell -NoProfile -ExecutionPolicy Bypass -File deploy_indirect.ps1
# YAAB 后：
powershell -NoProfile -ExecutionPolicy Bypass -File attach_indirect.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File dump_indirect.ps1
```

产出 `GP_indirect.txt`。勿与 gptimer / gpsample / d3d11 同时挂。

**不要**与 `d3d11.dll` 画面代理同时部署。

