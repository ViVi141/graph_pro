# demo

A/B 对比截图与分析图放在本目录（及 `_live/`）。

PNG / NPY / MP4 已由根目录 `.gitignore` 排除，避免把媒体文件推进 Git。
当前工作区实测约 **1.2 GB / 212 个文件**（2026-10-28；旧版本文写的是 200 MB，已过时）。
需要对比图时在本地用 `mission/` + `tools/` 流程重新生成：

    python tools\contact_shadow_smoke.py        # 接触阴影离线冒烟
    python tools\make_ab_contact.py             # 由同一场景生成 ab-contact-*.png
    python tools\proxy_smoke_test.py            # 代理本身的无头验证（不产图）

注意：`contact_shadow_smoke.py` 的当前遮挡率是 `mean_occ_ground ≈ 0.023`
（不是早期文档写的 0.49），详见 [../docs/12](../docs/12-pipeline-feasibility.md) 与
[../docs/21](../docs/21-project-review.md) §11。
