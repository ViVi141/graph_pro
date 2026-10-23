# 注入器说明

## 组成

| 文件 | 说明 |
|---|---|
| proxy/d3d11.dll | 代理 DLL（静态链接，仅依赖 KERNEL32） |
| proxy/d3d11_proxy.cpp / build.bat | 源码与 MSVC 构建脚本 |
| present/ | Present 接触阴影 HLSL + 嵌入头（`tools/build_present.ps1`） |
| presets/ | 当前生效配置 |
| tonemap_aces.hlsl / ssao_final.hlsl | 两个替换着色器的源码 |
| deploy.ps1 / remove.ps1 | 一键部署 / 一键移除 |
| toggle.ps1 | 开/关 d3d11.dll |
| set-spec.ps1 | 调材质镜面参数 |

## 默认预设（presets/）

| 文件 | 内容 | 作用 |
|---|---|---|
| GP_replace.txt | 5860 42670B06 GP_tonemap.dxbc | tonemap → ACES |
| GP_tonemap.dxbc | ACES v5（曝光 0.45 / 对比 1.12 / 饱和 1.08） | 全局成像 |
| GP_ssao.dxbc | smoothstep(0.15, 1.0) | AO 对比增强 |
| GP_spec.txt | `0 0.15 0` | 镜面 **mode 0 关**（`1 boost power` = 只 boost 已有 spec） |
| GP_spec_boost.txt | `1 0.15 0` | 选择性镜面实验（不随 deploy） |
| GP_amb.txt | `0.80 0.90 1.00 1.00` | 环境光折中（不冷偏） |
| GP_amb_stylized.txt | `0.60 0.80 0.93 1.10` | 旧风格化档（发暗发蓝） |
| GP_expo.txt | `1696 0 1.35` | 曝光上限折中（指纹钳制） |
| GP_expo_adapt.txt | `1696 0 1.10 1 0.55 0.55 1.10` | 自适应 hi（不随 deploy） |
| GP_expo_tight.txt | `1696 0 0.55` | 紧曝光实验（不随 deploy） |
| GP_present.txt | mode **2** | **接触阴影已搁置**（`kContactShelved`，改文件无效） |
| GP_present_on.txt | mode 0 | 保留作日后试验；当前会被强制回 mode 2 |
| GP_present_off.txt | mode 2 | 关 Present |
| GP_present_contact.txt | mode 4 | 红色遮挡 debug |
| GP_light.txt | `0.35 -0.75 0 10` | 手调屏幕空间光向 + 步数 |
| GP_light_auto.txt | `auto 10` | 用 CB 绑定光向（需 `GP_light_bind.txt`） |
| GP_light_bind.txt.example | `size idx` | 改名为 `GP_light_bind.txt` |
| GP_cb_dump.txt.example | `1 512 4096 120 64` | 改名为 `GP_cb_dump.txt` 开 CB dump |
| GP_probe*.example | — | 探针 |

### GP_expo.txt 格式

`size lo hi [adapt] [target] [hiLo] [hiHi]`

- 出货：`1696 0 1.10`
- adapt=1：按帧平均亮度在 `[hiLo, hiHi]` 间插值有效上限
- **指纹**（防共享 size 误伤）：`c1.w≈0.4545`、`c0≈0`、`AE∈[0.05,4]`，且 `c37` 为 `(1, 0.30, AE, 1.00)` 或 `(1, 0.09, AE, 0.75)`
- 删/改名文件会热禁用（不必重启）
- 日志：`expo hit ... fp=1` / `CLAMPED ... fp-ok` / `expo skip fingerprint`

### GP_present.txt 格式

`mode strength radius_m projK frac [alpha] [luma0] [luma1]`

| mode | 含义 |
|---|---|
| 0 | 接触阴影合成（软双半径 + 明度保护 + 时域） |
| 1 | 遮挡灰度 debug |
| 2 | 关闭 |
| 3 | 合成 + 深度缩略图 |
| 4 | 红色遮挡 debug |

缺省：`alpha=0.35`（时域）、`luma0=0.05` / `luma1=0.18`（SSAO 明度保护）。热重读。

### GP_light.txt / 自动光向

- 手调：`lx ly lz steps`
- 自动：文件内容 `auto [steps]`，并从 `GP_light_bind.txt` 读 `size floatIndex`
- 流程：复制 `GP_cb_dump.txt.example` → dump 白天/黄昏/室内 → `python tools/cb_sun_hunt.py ... --out GP_light_bind.txt` → 复制 `GP_light_auto.txt` → `GP_light.txt`

### GP_spec.txt 格式

`mode boost [power]` — mode 0=关；mode 1=仅当已有 specular 时 `×(1+boost)`（跳过草/云）。

## 工作方式

1. 代理 d3d11.dll，接管 D3D11CreateDevice
2. 挂钩 CreatePixelShader：按 (size, crc) 或反汇编指纹替换指定 pass
3. 挂钩 Map/Unmap：环境光 / 曝光钳制 / 可选镜面 boost / CB dump / 光向绑定
4. Present：深度 SRV + 全屏接触阴影（MRT 写历史 occ/depth）

## 已验证生效

- tonemap / SSAO resolve / 环境光 / 曝光钳制（见 docs/RESULTS）
- 接触阴影：软笔触 + 明度保护离线冒烟 `demo/contact-shadow-smoke.png`；引擎内默认 mode 2，试验用 `GP_present_on.txt`
- 时域：RG16F ping-pong；深度突变时重置
- 天空保护：近地 `d<0.88` / `z≤25m`；云层不采样为遮挡物

## 已放弃

- 代理 GFSDK_SSAO；`specular==0` 覆写；仅深度二次 AO；G-buffer 法线 / 云前干净深度（N1/N2）

## 已知限制

- 材质着色器代码不可改；A3 更新后 size/crc / expo size 需重采
- 自动光向依赖 CB hunt 命中；未绑定时请用手调 `GP_light.txt`
- 默认 Present 仍 mode 2，待引擎内 A/B 通过后再改 `GP_present.txt` → mode 0
