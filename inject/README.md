# 注入器说明

## 组成

| 文件 | 说明 |
|---|---|
| proxy/d3d11.dll | 代理 DLL（静态链接，仅依赖 KERNEL32） |
| proxy/d3d11_proxy.cpp / build.bat | 源码与 MSVC 构建脚本 |
| present/ | Present 接触阴影 HLSL + 嵌入头（`tools/build_present.ps1`） |
| presets/ | 当前生效配置（v1 默认） |
| tonemap_aces.hlsl / ssao_final.hlsl | 两个替换着色器的源码 |
| deploy.ps1 / remove.ps1 | 一键部署 / 一键移除 |
| toggle.ps1 | 开/关 d3d11.dll |
| set-spec.ps1 | 调材质镜面参数 |

## v1 默认预设（presets/）

| 文件 | 内容 | 作用 |
|---|---|---|
| GP_replace.txt | 5860 42670B06 GP_tonemap.dxbc | tonemap → ACES |
| GP_tonemap.dxbc | ACES v5（曝光 0.45 / 对比 1.12 / 饱和 1.08） | 全局成像 |
| GP_ssao.dxbc | smoothstep(0.15, 1.0) | AO 对比增强 |
| GP_spec.txt | `0 0` | 镜面关闭（实测负收益） |
| GP_amb.txt | `0.60 0.80 0.93 1.10` | 环境光强度与色温 |
| GP_expo.txt | `1696 0 1.10` | 钳制 PSCB_PostProcess `c[37].z`（size=1696，f150） |
| GP_expo_tight.txt | `1696 0 0.55` | 紧曝光实验（不随 deploy 覆盖） |
| GP_present.txt | `2 0.45 1.20 600 0.30` | **默认关闭**（mode 2）。mode 0 仅近地 d&lt;0.88，仍可能穿帮 |
| GP_present_off.txt | mode 2 | 关 Present（复制覆盖 GP_present.txt） |
| GP_present_contact.txt | mode 4 | 红色遮挡 debug |
| GP_light.txt | `0.35 -0.75 0 8` | 屏幕空间光方向 + 步数 |
| GP_probe.txt.example | 1 | 改名为 GP_probe.txt 开探针 |

### GP_expo.txt 格式

`size lo hi` — 仅当 Map 缓冲字节数 == size 时，把 float[150]（即 `c[37].z`）钳到 [lo, hi]。

- 出货：`1696 0 1.10`（已用 hi=1.10 vs 0.30 截图证明命中）
- 日志：`GP_shader.log` 应出现 `expo hit`；越界时还有 `exposure CLAMPED`

### GP_present.txt 格式

`mode strength radius_m projK frac`

| mode | 含义 |
|---|---|
| 0 | 接触阴影合成（出货） |
| 1 | 遮挡灰度 debug |
| 2 | 关闭 |
| 3 | 合成 + 深度缩略图 |
| 4 | 红色遮挡 debug |

热重读：改文件后下一帧生效，不必重启。

## 工作方式

1. 代理 d3d11.dll，接管 D3D11CreateDevice
2. 挂钩 CreatePixelShader：按 (size, crc) 或反汇编指纹替换指定 pass
3. 挂钩 Map/Unmap：环境光 / 曝光钳制（镜面默认关）
4. Present：深度 SRV + 全屏接触阴影 pass

## 已验证生效

- tonemap 替换：REPLACE ps size=5860 crc=42670B06
- SSAO resolve 替换：SSAO FINAL REPLACED len=692 crc=850EE87F
- 环境光缩放：ambient scaled amb=0.60 ae=0.80
- 曝光钳制：size=1696 / f150；A/B 见 `demo/expo-ab-compare.png`
- 接触阴影：离线冒烟 + mode0 默认；见 `demo/ab-contact-off-vs-on.png`
- 天空保护：深度探针 `max<0.99` 时跳过 Present；HLSL 对 `d≥0.995` / `z>80m` 早退；expo 只改 `0.02–8` 的 f150（避免误伤同 size 的其它 CB）

## 已放弃

- 代理 GFSDK_SSAO：CreateContext 前崩溃，已回滚
- 镜面补全：`specular==0` 是哑光意图，覆写伤害草/云
- 仅深度二次 AO：与原版 SSAO 冗余

## 已知限制

- 材质着色器代码不可改（编译器在 exe 内）
- 每次 A3 更新后 size/crc / expo size 可能变化，需重采
- 接触阴影光向短期手调（`GP_light.txt`）
