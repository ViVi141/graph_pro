# 经典画面旁路线（legacy proxy）— 已归档

> **归档日期：2026-11-23。只读保存，不再维护、不再随仓库更新。**
> 当前在维护的注入交付线是 [`inject/universal/`](../../inject/universal/README.txt)。

## 为什么归档

Universal 线在产品能力上已经覆盖经典线：DXVK 3.1.1 链式代理、四档画质包
（agx / agx_lite / ssgi / ultra）、一键安装 / 卸载 / 回滚、只读自检。
经典线剩下的能力全部是研究探针，且状态为「已判负 / 已搁置 / 未量化」：

| 经典线独有能力 | 状态 | 证据 |
|---|---|---|
| Present 钩 + 接触阴影 | 已搁置（`kContactShelved`） | `docs/12-pipeline-feasibility.md` |
| FSR1 放大 pass 指纹探针（`GP_upscale*`） | 指纹已对上，画质收益未量化 | `extract/upscale_probe_20261028/`、`docs/21-project-review.md` |
| passseq / candhooks / shader dump（`GP_*`） | 研究用途，未量化 | `docs/15-*.md`、`docs/21-project-review.md` |
| 经典热调参（`GP_present` / `GP_light` / `GP_adapt`） | 部分已判负 | `inject/presets/` |

保留归档而不是删除，是为了让上述证据链仍有可复现的入口。

## 目录映射

归档保持原来的 `inject/`、`tools/` 相对结构，因此多数脚本不用改路径就能离线运行。

| 原路径 | 归档路径 |
|---|---|
| `inject/proxy/` | `archive/legacy-proxy/inject/proxy/` |
| `inject/presets/` | `archive/legacy-proxy/inject/presets/` |
| `inject/present/` | `archive/legacy-proxy/inject/present/` |
| `inject/deploy.ps1` / `remove.ps1` / `toggle.ps1` / `set-spec.ps1` | `archive/legacy-proxy/inject/` |
| `inject/*.hlsl`、`ssao_natural.dxbc`、`tonemap_agx.dxbc`（冻结副本） | `archive/legacy-proxy/inject/` |
| `tools/proxy_smoke_test.py` / `probe_smoke_test.py` / `analyze_capture.py` | `archive/legacy-proxy/tools/` |
| `tools/capture_3way_graphics.ps1` | `archive/legacy-proxy/tools/`（仓库根改为上两级计算） |
| `tools/build_tonemap.ps1` / `build_present.ps1` | `archive/legacy-proxy/tools/` |
| `tools/gen_cand_header.py` / `gen_cands_generic.py` | `archive/legacy-proxy/tools/` |

`inject/vcvars64_locate.bat` 在活跃树与归档中各有一份，保证两边 `build*.bat` 都能独立运行。
`inject/tonemap_agx.dxbc` 留在活跃树（它是 Universal 构建产物，由 `inject/universal/build.bat` 生成）；
归档里那一份是冻结副本。

## 离线复现（不碰游戏进程）

```powershell
# 编译经典代理（需要 VS C++ 工具）
cd archive\legacy-proxy\inject\proxy; .\build.bat; cd ..\..\..\..

# 无头回归：配置加载 -> 替换 -> Present -> ResizeBuffers / 放大探针
python archive\legacy-proxy\tools\proxy_smoke_test.py
python archive\legacy-proxy\tools\probe_smoke_test.py

# 重新编译经典载荷（输出到归档内 presets\）
powershell -File archive\legacy-proxy\tools\build_tonemap.ps1
powershell -File archive\legacy-proxy\tools\build_present.ps1
```

三个 `capture_*.ps1` 只做「写文件 / 等你自己跑游戏 / 收集」，不会启动、关闭、
注入或截图游戏客户端。归档中的 `deploy.ps1` 仍能按原结构工作，但**不建议再部署**；
若游戏目录里还有经典代理，请先运行：

```powershell
powershell -File archive\legacy-proxy\inject\remove.ps1
```

再切换到 Universal：`inject\universal\install.ps1`。

## 边界

- 归档内的脚本按 2026-11-23 的状态冻结，不保证随游戏版本更新。
- CI 的 Python compileall 只覆盖活跃 `tools/`；归档脚本的语法检查靠人工/PS Parser 全量扫描。
- 文档（`docs/12`、`docs/15`、`docs/21`、`docs/RESULTS`）保留历史正文，路径引用按当时的
  `inject/...` 记录；本文档是这些路径的跳转索引。
