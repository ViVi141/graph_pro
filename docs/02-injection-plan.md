# 注入路线与 shader 替换方案（任务 2）

> 前提已确认：**私有服务器 / 允许注入 / 无 BattlEye**。
> 这改变了结论：不必停在 ReShade，可以直接**替换引擎自己的后处理着色器**。

---

## 0. 判定

**只叠 ReShade 是次优解。** 它工作在 Present 之后，改的是"已经调完色、已经 tonemap 完"的最终图像：你能再压一层 LUT，但改不了 A3 自己的曝光、filmic 曲线、AO 半径和 AA 逻辑，叠加只会双重调色。

**A3 的后处理链本身是可以替换的**——它是一批预编译 DXBC，名字、哈希、常量缓冲布局都能拿到。这是本项目的真正抓手。

---

## 1. 证据（本机实测，非推测）

`Dta\bin.pbo`（82 MB）头部直接列出 9 个着色器缓存：

```
Shaders_4_0_GS.shdc  Shaders_4_0_PP.shdc  Shaders_4_0_PS.shdc  Shaders_4_0_VS.shdc
Shaders_5_0_CS.shdc  Shaders_5_0_GS.shdc  Shaders_5_0_PP.shdc  Shaders_5_0_PS.shdc  Shaders_5_0_VS.shdc
```

提取结果（脚本：`tools/pbo_shdc_probe.py`，产物：`extract/shdc/`）：

| 缓存 | DXBC 块数 | 命名字符串条目 |
|---|---|---|
| Shaders_4_0_PP | 85 | 43 |
| Shaders_5_0_PP | 293 | 144 |
| Shaders_4_0_PS | 1524 | 759 |
| Shaders_5_0_PS | 1666 | 830 |
| Shaders_4_0_VS | 6193 | 2967 |
| Shaders_5_0_VS | 6901 | 3301 |
| **合计** | **18,122** | **7,853**（去重，见 `extract/shader-inventory.csv`） |

- 编译器指纹：`Microsoft (R) HLSL Shader Compiler 9.29.952.3111`（June 2010 SDK），目标 `ps_4_0 / vs_4_0`；5_0 缓存同构。
- 每个条目结构：`名称\0 阶段\0 8位哈希\0`，后可反汇编出 `RDEF` 常量缓冲布局（如 `PSCB_PostProcess`、`PSC_BloomPars`、`PSC_ssaoPixelOffset`）。
- 常量缓冲命名直接暴露用途：`PSC_BlurKernel`、`PSC_BicubicTexelSize`、`PSC_ShadowmapMatrix`、`PSC_TempRangeMax01`…

**结论：A3 的整条后处理、AA、材质 shader 都在你手上，可读、可反汇编、可替换。**

---

## 2. 后处理链的实际构成（可直接替换的 pass）

从 `Shaders_5_0_PP.shdc` 解析出的命名条目，按功能分组：

| 功能 | shader 名 | 说明 |
|---|---|---|
| **Tonemap** | `PSPostProcessGlowNewFinalFilmic` / `…Reinhard` / `…None` | 三条曲线对应"Glow/HDR"档位——**拟真感第一目标** |
| 曝光/亮度统计 | `PSPostProcessDownSampleAvgLuminance`、`…AssumedLuminance` | 自动曝光来源 |
| Bloom | `PSPostProcessGlow`、`GlowNight`、`GlowNewBloomInitDownsample`、`…Compose`、`…Kawase` | 光晕层次 |
| 环境光遮蔽 | `PSPostProcessSSAO`、`SSAOFinal`、`SSAOBlurVert/Horz`、`…Depth` | AO 强度/半径/降噪 |
| 抗锯齿 | `A3_SMAA*`（5 段）、`PsFxaa3_11` | 在 PS 缓存，可换更强 AA |
| 调色 | `PsPpColors`、`PsPpColorsRadial`、`PsPpChromAber` | 全局 LUT/色差 |
| 电影感 | `PSPostProcessFilmGrainColor/Mono`、`PsPpDynamicBlur`、`PsPpRotBlur`、`PsPpRadialBlur` | 颗粒/动态模糊 |
| 景深 | `PSPostProcessDOF`、`DistanceDOF` | |
| HDR 裁剪 | `PSPostProcessHDRColorLimit`（+NVG 版） | 高光滚降 |
| 天气/水 | `PSPostProcessRain3D`、`PSRainRefractAdjust`、`PSPostProcessCaustics`、`PSPostProcessWetDistort` | |
| 热像/NVG | `PSPostProcessThermal*`、`PSPostProcessNVG` | |
| 次表面散射 | `PSPostProcessSSSM*`（4 档） | 植被/皮肤透光 |
| 云 | `GSSimulWeatherClouds`（GS） | |

---

## 3. 三条注入路线对比

| | A. ReShade | **B. DXBC 替换（推荐）** | C. 重打包 bin.pbo |
|---|---|---|---|
| 作用点 | Present 之后 | `CreatePixelShader` 等创建点 | 直接改 `.shdc` 内容 |
| 能改 | 最终图像再加工 | **引擎原本的 tonemap/AO/bloom/AA** | 同 B，但静态 |
| 改不了 | 曝光、AO 半径、AA 逻辑 | 几何/光照模型本身 | 同 B |
| 工程量 | 半天（装+调参） | 中（hook + 重编译 + 热重载） | 低（解包/替换/重打包） |
| 稳定性 | 高 | 中（签名不匹配会崩） | 高 |
| A3 更新后 | 不影响 | 哈希变，需重跑 dump | **全部失效，需重做** |
| 多人 | 官方服高危 | 私有服可用 | 仅本地，且每人一份游戏 |
| 性能成本 | +1~N 个全屏 pass | **≈0**（替换已有 pass） | ≈0 |

**结论：B 为主，A 作为兜底/快速验证，C 用于"永久固化"或对比实验。**

C 的价值被低估：私有服场景下，把改好的 `.shdc` 重打包进 `bin.pbo`（去掉 `.bisign`、服务器 `verifySignatures=0`），**完全不需要注入**，效果与 B 等价且没有崩溃风险——代价是每次 A3 更新要重做，且每个客户端都要换文件。

---

## 4. 路线 B 的工作流（可执行）

1. **代理注入**：游戏目录放 `d3d11.dll`（或 `dxgi.dll`），转发导出，在 `D3D11CreateDevice` 后拿到 `ID3D11Device`。
2. **挂创建点**：hook `CreatePixelShader / CreateVertexShader / CreateGeometryShader / CreateComputeShader`。
3. **指纹匹配**：对传入 bytecode 取 hash（CRC/SHA1 均可），与"目标表"比对；命中则替换，否则原样透传。
4. **编译替换件**：`fxc /T ps_5_0 /E main` 编译你的 HLSL → DXBC。约束：
   - 输入/输出签名必须与原件一致（`SV_Target` 数量、MRT 顺序）
   - 常量缓冲布局必须一致（从原件 `RDEF` 反汇编读出，或用同结构 `cbuffer`）
   - SRV/Sampler 槽位一致
5. **热重载**：监视 `.hlsl` 改动 → 重编译 → 清 `VSShaderPool`/PS 池（或重启场景）。
6. **安全模式**：按住某键启动则不注入。

**已知坑**：
- A3 同时存在 D3DX11（SM4.0 源码编译）与预编译 `.shdc`（SM5.0）两条路径，实际命中哪个以运行时 dump 为准。
- 部分 PP pass 用 MRT（HDR + 深度/速度），输出数量和格式写错会直接黑屏。
- 全屏 pass 的顶点着色器是共享的（`VSPostProcessCustomEdge4T`），不要动它。

---

## 5. 替换优先级（拟真感收益 / 风险）

| 优先级 | 目标 | 期望效果 | 风险 |
|---|---|---|---|
| ★★★ | `PSPostProcessGlowNewFinalFilmic` | 换成 ACES/AgX 类曲线：高光滚降自然、暗部不死黑 → **"照片感"主要来源** | 低（全屏 quad，参数简单） |
| ★★★ | `PSPostProcessSSAOFinal` | AO 半径/强度/降噪重写，接触阴影扎实 | 中（多 pass 联动） |
| ★★☆ | `PSPostProcessGlowNewBloom*` | bloom 阈值/扩散，光源有"呼吸" | 中 |
| ★★☆ | `PsPpColors` | 换成 3D LUT，统一色调 | 低 |
| ★★☆ | `A3_SMAANeighborhoodBlendingPS` | 换更强 AA 或改混合权重 | 中 |
| ★☆☆ | `PSPostProcessHDRColorLimit` | 高光裁剪更柔 | 低 |
| ★☆☆ | `PSPostProcessFilmGrainMono/Color` | 关掉或换真实胶片颗粒 | 极低（最好的练手目标） |

> 注意：真正决定"材质像不像真的"仍是 `.rvmat`（specular/fresnel/PSID），shader 替换解决的是"成像"而不是"材质响应"。两者要一起做。

---

## 6. 私有服落地清单

**服务器端**（`server.cfg`）：
```
BattlEye = 0;
verifySignatures = 0;      // 或给你的 addon 签名
```

**客户端**：
- 渲染是纯本地行为，**服务器不渲染**；想让所有人看到一致画面，每个客户端都要装同一套。
- 分两包管理：
  - **addon 包**（`.rvmat`、贴图、粒子）→ 正常 mod，走 `-mod=@graphpro`，可签名、可分发给队友
  - **注入包**（`.dll` + `.hlsl`）→ 不进 mod 列表、不参与签名检查，纯本地
- **隔离**：单独复制一份游戏目录做实验（~90 GB 太大时，至少单独 profile + 快捷方式），避免误连官方服。

**更新维护**：A3 每次更新 `.shdc` 会重编，hash 全变。缓解办法：
- 用"结构指纹"（stage + cbuffer 名集合 + 指令数）而非纯 hash 匹配
- 保留 `dump → 映射表` 的一键脚本，更新后 5 分钟重跑

---

## 7. 性能预算（Intel 核显 / 1080p / 120 Hz）

- **替换已有 pass ≈ 免费**：同样的全屏 draw，指令数相当，帧率基本不变。
- **新增 pass 才收费**：ReShade 的 MXAO/RTGI 是"额外"的全屏计算，核显上代价 20~50%。
- 因此路线 B 在你这台机器上**比 ReShade 更划算**：画质提升来自"改算法"，而不是"加算法"。
- 需要监控：`diag_fps`、PresentMon 帧时间；目标 ≥ 60 fps 稳定。

---

## 8. PoC 计划（5 步，含验收）

| 步骤 | 内容 | 验收标准 | 预估 |
|---|---|---|---|
| 1 | 写 dumper：注入 + dump 全部 (stage, hash, size, 反汇编头) | 能列出"当前画质档实际使用了哪些 PS" | 1 天 |
| 2 | 原样回填（bytecode 不变） | 连续 10 分钟不崩、帧率不变 | 0.5 天 |
| 3 | 替换 `FilmGrainMono` 为直通 | 画面颗粒消失，其余无变化 | 0.5 天 |
| 4 | 替换 tonemap 为 ACES 近似 | A/B 截图高光明显更自然，fps 不降 | 1~2 天 |
| 5 | 打包启动器（注入开关/配置/日志/安全模式） | 一键启停，可回滚 | 1 天 |

---

## 9. 风险与红线

- **崩溃/黑屏**：始终保留"不注入"启动方式；先在窗口模式 + 低画质验证。
- **官方服**：带注入进官方/BE 服务器 = 封号风险，用独立副本。
- **分发**：不要分发原版 `.shdc`/反编译源码（版权）；分发你自己的 HLSL 与工具即可。
- **更新失效**：把它当"每次大版本都要维护"的项目，而不是一次性补丁。

---

## 附：本地产物

- `tools/pbo_shdc_probe.py` —— 解析 bin.pbo、导出 9 个 .shdc
- `tools/shdc_inspect.py` —— .shdc 结构/DXBC/字符串探测
- `tools/shdc_inventory.py` / `shdc_csv.py` —— 名单与 CSV 导出
- `extract/shdc/*.shdc` —— 9 个缓存（~81 MB）
- `extract/shader-inventory.csv` —— 7,853 条（cache, name, stage, hash）
