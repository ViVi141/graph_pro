# inject — 注入线总览

## Universal 产品线（唯一在维护的注入交付线）

| 入口 | 说明 |
|---|---|
| [universal/README.txt](universal/README.txt) | 安装、卸载、切换、画质包、故障排查 |
| `universal/build.bat` | 编译代理与载荷（需要 VS C++ 工具 + Windows SDK fxc） |
| `universal/install.ps1` / `GraphPro_Manager.bat` | 一键安装 / 管理菜单 |
| `universal/uninstall.ps1` | 完全卸载并恢复备份 |
| [../tools/verify_universal.ps1](../tools/verify_universal.ps1) | 只读自检：部署完整性 + 后端 / 画质包状态 |
| [../tools/universal_smoke_test.py](../tools/universal_smoke_test.py) | 无头离线回归（不需要游戏） |

`vcvars64_locate.bat` 是各 `build*.bat` 共用的 VS 路径探测器。

## 经典画面旁路线（已归档）

2026-11-23 起，原 `inject/proxy`、`inject/presets`、`inject/present`、
`deploy.ps1` / `remove.ps1` / `toggle.ps1` / `set-spec.ps1` 与经典 HLSL 已整体移到
[`archive/legacy-proxy/`](../archive/legacy-proxy/ARCHIVED.md)，只读保存。

- 产品能力已由 Universal 覆盖；经典线剩余的是已搁置 / 未量化的研究探针。
- 归档保留原 `inject/`、`tools/` 相对结构，离线 smoke test 与载荷编译仍可运行。
- 如果你的游戏目录里还部署着经典代理，先运行
  `archive\legacy-proxy\inject\remove.ps1`，再用 `universal\install.ps1` 切换到 Universal。
- 归档内容不要再部署到游戏目录。

## 其它

`counter/` 是 CPU 采样 / 符号归因载荷，与画面线无关，保持活跃。
