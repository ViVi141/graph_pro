# 无头 DS 任务 GP_ServerTest

用于 **arma3server_x64** CPU 采样（无渲染、无客户端 UI）。

## 部署 / 采样

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File server\run-cpu-sample.ps1 -SampleMinutes 3
powershell -NoProfile -ExecutionPolicy Bypass -File server\ab-soft-levers.ps1 -Variant wp_none
```

- 任务目录：`mission/GP_ServerTest.Altis/` → 复制到游戏 `MPMissions\`
- Profile：`%LOCALAPPDATA%\GP_arma_server`（路径须无空格）
- **勿**与 `d3d11.dll` 画面代理同时使用
- 指标用 `GP_sample_modules.txt` 的 exe_fn，不要用 `diag_fps`

结论：[docs/16-cpu-server-soft-levers.md](../docs/16-cpu-server-soft-levers.md)
