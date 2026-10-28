# 最小 rvmat 验证 v3（两次运行）

目标：同一个固定机位、同一帧里三个 H-Barrier，比较 `hbarrier.rvmat` 的 specular 改动是否有可测的视觉结果。

这次不再用 `setObjectMaterial`（H-Barrier 没有 hidden selections，运行时 API 对它无效），
改用 **mod 同路径覆盖** —— 这是实际生产会用的方式。

## 准备

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File mission\deploy-min.ps1
```

## 运行 A：基线（不带 mod）

1. 先正常启动 **Steam** 并保持登录
2. **你自己**启动 Arma 3（仓库不再提供启动脚本）
3. PLAY → SCENARIOS → **GP Min**
4. 场景出现后等约 **12 秒**，Esc → Abort

产物：`Documents\Arma 3\Screenshots\gp_mat_nomod.png`

## 运行 B：带 mod

1. 保持 Steam 运行
2. **你自己**用 `-mod=@gpmat` 启动（Steam 启动项里加，或在启动器里勾选 `mod\@gpmat`）
   —— PBO 不入库，先按 [mod/README.md](../mod/README.md) 自己打包。
3. 同样进 **GP Min**，等约 12 秒，Esc

产物：`Documents\Arma 3\Screenshots\gp_mat_mod.png`

## mod 里改了什么

| 项 | 原版 | mod |
|---|---|---|
| specular[] | 0.503 | **5.0** |
| specularPower | 29.2 | **4** |
| 其余字节/阶段/贴图 | — | 不变 |

5.0 是故意夸张的：如果覆盖生效，H-Barrier 会出现非常明显的高光；如果没有变化，说明覆盖机制没生效（而不是"材质不重要"）。

## 判定

| 观察 | 结论 |
|---|---|
| 两个 png 的障碍物区域差异明显 | 覆盖生效，材质常量有视觉权重 → 再调真实值 |
| 两个 png 完全一致，且 RPT 里 `[GP] modtag=mod` | 覆盖没生效（前缀/加载顺序），换 mod 方案 |
| RPT 里 `[GP] modtag=nomod` | mod 没加载，检查 `-mod=` 路径 |

## 备注

- 任务只生成 3 个 H-Barrier 并截图，不再读文件、不再调用 `setObjectMaterial`，不会再弹窗。
- 截图文件名自带 `nomod` / `mod`，不会互相覆盖。
