# Arma 3 渲染交互面地图（任务 1）

> 环境基线（本机实测，非通用推断）
> - 游戏：`D:\SteamLibrary\steamapps\common\Arma 3`，arma3_x64.exe **2.22.154089**
> - 图形 API：**DirectX 11**（exe 导入 `d3d11.dll`/`DXGI.dll`、`D3DCOMPILER`；**无** `d3d9.dll`、**无** `dxcompiler` → 不存在 DX9/DX12 路径）
> - GPU：Intel 核显（Arc/Xe，驱动 32.0.101.9150），原生屏 2880×1800@120，游戏内 1920×1080 窗口
> - 反作弊：BattlEye 已随游戏安装（`arma3battleye.exe`）
> - 基线备份：`baseline/Arma3.cfg`、`baseline/74738.Arma3Profile`、`baseline/rpt-head.txt`

---

## 0. 结论先行

Arma 3（Real Virtuality 4）**没有公开的渲染插件 API**，也**没有暴露可替换的 shader 源码**：`Dta\bin.pbo` 里没有任何 `.hlsl`；着色器以**预编译 DXBC 缓存**（`.shdc`）形式存在——18,122 个 DXBC 块、7,853 个命名条目，可反汇编、可替换（详见 [02-injection-plan.md](02-injection-plan.md)）。所以"和渲染交互"只有三条真实通路：

| 通路 | 本质 | 能否改变"像不像真的" | 风险 |
|---|---|---|---|
| **A. 配置 + 脚本（SQF）** | 调引擎已有参数、加后处理、改相机与天气 | 中（观感/气氛大，材质与光照模型不变） | 无，官方支持 |
| **B. 资源级 addon** | rvmat / p3d / 贴图 / 地形 / 模板配置 | **高**（这是唯一能改"材质如何响应光"的官方途径） | 低，需签名与服务器允许 |
| **C. 进程外注入** | ReShade / ENB / SpecialK / DXVK / shader replace | 高（但只能"后期"，改不了几何与光照计算） | **BattlEye 风险**，多人慎用 |

一句话：**想改"引擎怎么算"，只能走 B；想改"算完长什么样"，走 A 和 C。** A 最便宜、B 最有效、C 最快见效也最容易翻车。

---

## 1. 为什么交互面这么窄（引擎事实）

1. **RV4 是前向渲染 + 多 pass**，材质由 `.rvmat` 选择引擎内置的 shader 变体（`PixelShaderID`/`VertexShaderID`），你**只能选变体、不能写 shader**。
2. **没有 C++ 渲染插件接口**。唯一的官方原生入口是 `callExtension`（DLL 扩展），但它拿不到 D3D11 设备/交换链，只能做 CPU 侧计算与文件 IO（可用来"离线生成贴图 → 运行时喂给 setObjectTexture"，属于曲线救国）。
3. **多人大面积受签名约束**：官方 PBO 带 `.bisign`，服务器 `verifySignatures` 会拒绝改过的核心资源；BattlEye 会拒绝注入型 DLL。
4. 因此，**所有"画面提升"最终都落在"数据 + 参数 + 后期"上**，这也决定了投入产出比：材质/光照模板 > 后处理 > 屏幕空间滤镜。

---

## 2. L1 配置层（零成本，先榨干）

### 2.1 `Documents\Arma 3\Arma3.cfg`（本机实测键，已被我备份）

| 键 | 当前值 | 作用 | 备注 |
|---|---|---|---|
| `renderWidth/renderHeight` | 1920×1080 | 内部渲染分辨率（≠ 窗口分辨率） | 可低于窗口做"渲染缩放" |
| `multiSampleCount` | 1 | MSAA 采样数（1 = 关） | 开 2/4 对细线/植被收益大，代价高 |
| `AToC` | 0 | Alpha-To-Coverage，配合 MSAA 修草木边缘 | 开 MSAA 后才有意义 |
| `PPAA` | 0 | 后处理抗锯齿（FXAA/SMAA 档） | 0=关；低档几乎免费 |
| `ppSSAO` | 0 | 屏幕空间环境光遮蔽 | **拟真感性价比最高的一项** |
| `ppHaze` | 2 | 大气雾/空气透视 | 2 已是较高级 |
| `ppBloom` / `ppDOF` / `ppRadialBlur` | 1/1/1 | 泛光 / 景深 / 径向模糊 | 拟真感建议：DOF 低、RadialBlur 关 |
| `ppSharpen` | 0 | 锐化 | 与 PPAA 叠加补偿软边 |
| `waterSSReflectionsQuality` | 0 | 水面屏幕空间反射 | 关=水面"死"，开=明显提升 |
| `cloudsQuality` | 1 | 云层质量 | 天空观感主要来源 |
| `dynamicLightsQuality` | 1 | 动态光源质量 | 夜间/车灯观感 |
| `pipQuality` | 2 | PiP（镜面/热成像/屏幕）质量 | 与 L2 的 r2t 联动 |
| `HDRPrecision` | 16 | HDR 精度（16/32） | 高光滚降更自然 |
| `GPU_MaxFramesAhead` | 1000 | 预渲染帧数上限 | ⚠️ 1000 为"自动"语义；设 1 降延迟、可能掉帧 |
| `vsync` / `tripleBuffering` | 1 / 0 | 垂直同步 / 三缓冲 | 120 Hz 屏可试 vsync=0 + 限帧 |

调整方式：启动器 UI 或直接改文件（**改前退出游戏**，游戏退出时会覆写该文件）。

### 2.2 `<profile>.Arma3Profile`（本机实测）

| 键 | 当前值 | 含义 |
|---|---|---|
| `viewDistance` | 1600 | 视距（米） |
| `preferredObjectViewDistance` | 1300 | 物体视距 |
| `pipViewDistance` | 800 | PiP 视距 |
| `shadowZDistance` | 100 | 阴影覆盖距离（米）——**阴影观感第一开关** |
| `terrainGrid` | 25 | 地表细节网格（数值越小越细：25 → 12.5 → 6.25） |
| `sceneComplexity` | 600000 | 场景复杂度预算（物体 LOD 切换阈值） |
| `textureQuality` | 1 | 贴图档位（偏低，说明现在画面偏"糊"） |
| `shadowQuality` | 3 | 阴影档位 |
| `anisoFilter` | 4 | 各向异性过滤（4 ≈ 低档，16 对地面/道路提升巨大） |
| `gamma/ppBrightness/ppContrast/ppSaturation` | 1 / 1.01 / 1.06 / 1.08 | 显示端色调，等价于"免费 LUT" |

> ⚠️ 档位数值与 UI 名称的对应关系（如 textureQuality 1 到底对应"低"还是"标准"）建议在启动器里逐档对照一次再写死，避免误判。

### 2.3 启动参数（本机实际使用）

从 RPT 头部可见当前启动行：
`-skipIntro -noSplash -window -enableHT -malloc=mimalloc_v250_20260820 -hugePages -showScriptErrors -debug "-mod=..."`

与画面/性能相关的还有：`-maxMem=`、`-maxVRAM=`（限制显存，影响贴图流送）、`-cpuCount=`、`-exThreads=`、`-profiles=`。⚠️ `-malloc`/`-hugePages` 影响帧生成稳定性（卡顿）而非画质，属于"帧时间"优化。

---

## 3. L2 脚本层（SQF：官方支持的"运行时渲染控制"）

这是唯一能在**游戏运行中**改渲染参数的通路。分六类：

### 3.1 几何/细节预算
```sqf
setViewDistance 3000;
setObjectViewDistance [2500, 2000];   // [物体视距, 阴影视距]
setTerrainGrid 6.25;                  // 地表细节
setShadowDistance 200;                // 阴影覆盖
setDetailMapBlendPars [0.3, 0.6];     // 细节贴图混合
```
> 只在本地客户端生效，多人下不改变服务器逻辑。

### 3.2 大气 / 光照 / 天气（"拟真感"的主战场）
```sqf
setOvercast 0.75; setFog [0.15, 0.02, 40]; setRain 0.2;
setWaves 0.4; setHumidity 0.6;
setDate [2035, 7, 12, 17, 40]; setTimeMultiplier 1;
```
配合 `setLightAmbient/setLightColor/setLightBrightness` 可做局部光源塑形；`setAperture`/`setApertureNew` 控制曝光（HDR 感的关键）。

### 3.3 后处理（ppEffect 家族）
```sqf
private _cc = ppEffectCreate ["ColorCorrections", 1500];
_cc ppEffectEnable true;
_cc ppEffectAdjust [1, 1, 0, [0,0,0,0], [1,1,1,0.9], [0.9,0.9,0.95,0.5]];
_cc ppEffectCommit 0;

private _grain = ppEffectCreate ["FilmGrain", 1501];
_grain ppEffectEnable true; _grain ppEffectAdjust [0.15, 1, 0.5]; _grain ppEffectCommit 0;
```
可创建的类型（常见）：`ColorCorrections`、`ColorInversion`、`DynamicBlur`、`FilmGrain`、`RadialBlur`、`WetDistortion`、`ChromAberration`。
参数含义与可用类型随版本变化，**以 BIKI 的 Post Process Effects 页为准**（我这边直连 BIKI 被 Cloudflare 拦了，需你本地或换网络核对）。

模板化做法（推荐，可复用、可切换）：
- `CfgPostprocessTemplates` 定义模板（`colorCorrections[]`、`filmGrain[]` 等）
- `[ "模板名" ] call BIS_fnc_setPPeffectTemplate` 应用，`BIS_fnc_setPPeffectTemplate` 也支持淡入时间
- `setPiPEffect [类型, ...]`：设置 PiP（镜面/屏幕/热像）通道的后处理，索引语义随版本变动 ⚠️

### 3.4 相机 / 镜头语言
```sqf
private _cam = "camera" camCreate (player modelToWorld [0,3,1.6]);
_cam camSetFov 0.5; _cam cameraEffect ["Internal", "Back"];
_cam camSetTarget player; _cam camCommit 0;
```
相关：`camSetFovRange`、`camUseNVG`、`setCamUseTi`（热成像）、`setAperture`、`cameraView`。**"电影感"很大程度来自 FOV/景深/曝光，而不是滤镜。**

### 3.5 渲染到纹理 + 自绘（唯一接近"自定义渲染"的官方能力）
```sqf
// 渲染目标当贴图用：模型表面 / UI 控件都能拿到实时画面
ctrlSetText [1000, "#(argb,512,512,1)r2t(rt1,1.0)"];
player setObjectTexture [0, "#(argb,512,512,1)r2t(rt1,1.0)"];
```
- `r2t(name, scale)` 是引擎内建的渲染目标语法，配合 `cameraEffect` 的 "RenderTarget" 模式可做监控屏、瞄准镜、镜面反射。
- 全屏叠加绘制：`addMissionEventHandler ["Draw3D", {...}]` + `drawIcon3D`/`drawLine3D`（每帧回调，可做世界空间标注、测距线、准星）；UI 层用 `displayAddEventHandler ["Draw", ...]`。
- 局限：**只能叠加与复用已有渲染结果，不能新增光照/材质通道**。

### 3.6 材质热替换
```sqf
player setObjectMaterial [0, "myMod\data\new_skin.rvmat"];      // 本地
player setObjectMaterialGlobal [0, "..."];                        // 广播（多人）
```
配合模型 `hiddenSelections`，可在不改 p3d 的前提下整体换材质——**做"材质包"最省事的路径**。

### 3.7 测量
`diag_fps`、`diag_fpsMin`、`diag_frameNo`、`diag_deltaTime`、`diag_captureFrame`（逐帧耗时快照）、`diag_captureSlowFrame`（只抓慢帧）。改任何画质前先量基线。

---

## 4. L3 资源层（addon：真正改"引擎算出来什么"）

### 4.1 `.rvmat` —— 材质是画面拟真度的根
```cpp
class Stage1 {
    texture = "myMod\data\wall_nohq.paa";
    uvSource = "tex";
    class uvTransform { aside[] = {1,0,0}; up[] = {0,1,0}; dir[] = {0,0,1}; };
};
PixelShaderID = "NormalMapDiffuse";
VertexShaderID = "NormalMap";
```
- `PixelShaderID/VertexShaderID`：**选择引擎内置 shader 变体**（NormalMap / NormalMapDiffuse / NormalMapMacroAS / Terrain / Water / Multi / Detail …）
- `StageTI`（细节/宏观混合）、`RenderFlags`（NoZWrite/NoZTest 等）、`ambient[]/diffuse[]/forcedDiffuse[]/emmisive[]/specular[]/fresnelN`：**决定材质如何响应光**，这是 ReShade 永远做不到的部分。
- 现实收益：同一张 albedo，换 rvmat 的 specular/fresnel/PSID，金属/湿滑/哑光的分裂感完全不同 → **"塑料感 → 真实感"的关键开关**。

### 4.2 `.p3d` 模型
LOD 体系（Visual / Geometry / FireGeometry / Shadow / ViewPilot…）、`hiddenSelections`、法线/切线、顶点色。改 LOD 与法线是"物体看起来扎实"的来源。

### 4.3 贴图管线
TGA/PNG → `.paa`（TexView 2），法线（_nohq）、宏观（_mc）、细节（_dt）、`_as`（环境光遮蔽/高光）。**PAA 的压缩质量直接影响"糊不糊"**。

### 4.4 配置类
- `CfgPatches`：addon 入口，`requiredAddons` 决定加载顺序（做补丁覆盖的关键）
- `description.ext` / `CfgPostprocessTemplates`：后处理模板库
- `CfgCloudlets`（+ `setParticleParams/ParticleArray`）：爆炸、烟尘、火花——**VFX 拟真感的大头**
- `hiddenSelectionsTextures/Materials`：换皮不换模型
- `CfgWorlds` + `.wrp` 地形：Terrain Builder 编辑卫星图/细节层/材质索引/地表网格

### 4.5 签名与分发
官方 pbo 带 `.bisign`；自建 addon 用 `DSSignFile` 签名，服务器 `verifySignatures=2` 才收。改官方核心 pbo（如 `bin.pbo`）= 多人直接被踢。

---

## 5. L4 进程外注入层（改"已经算完的像素"）

| 工具 | 机制 | 能得到什么 | 代价/风险 |
|---|---|---|---|
| **ReShade** | `dxgi.dll`/`d3d11.dll` 代理，劫持 Present | SMAA/FXAA、MXAO、RTGI、DOF、LUT、锐化、色差、颗粒；可读深度缓冲 | 需要深度缓冲可用性调试；**BattlEye 环境下有被踢/封风险** |
| **ENB** | 同类代理，DX11 通用注入 | 高质量 bloom/SSAO/色调 | 对 A3 无官方适配，稳定性差 |
| **SpecialK** | 全局注入 / 本地 dll | flip model、HDR retrofit、帧生成、延迟控制 | 注入型，多人高风险 |
| **DXVK** | DX11 → Vulkan 转译 | 部分场景降 CPU 开销、提帧稳定 | 兼容性/反作弊风险，收益不确定 |
| **Lossless Scaling** | 外置窗口捕获 + 缩放/插帧 | 低分辨率渲染 + 放大、帧生成 | **不改游戏进程**，对 BE 相对安全；但引入额外延迟与伪影 |
| **驱动层** | Intel 控制中心：AF/CMAA/锐化/电源 | 免费 AF 16×、锐化 | 你这台是 Intel 核显：**没有 DSR/VSR、没有 DLSS**，只有驱动级 AF/锐化 |
| **shader replace** | D3D11 hook（3Dmigoto 类），按 shader hash 换 DXBC | **可重写像素着色器**（色调映射、降噪、SSR 替换） | 能力最强、工程量最大、BE 必杀；仅建议单机实验 |

**BattlEye 现实**：注入型工具在 BE 保护的多人服务器上属于高危区，且多数服务器还有 `verifySignatures`。结论：**C 类只在单人/编辑器/本地无 BE 会话里玩**，别带进多人。

---

## 6. L5 测量与工具链

- **日志**：`%LOCALAPPDATA%\Arma 3\*.rpt`（启动参数、GPU、脚本错误、加载耗时——本机最新一份 4.1 MB）
- **帧分析**：`diag_captureFrame`；外部用 PresentMon / CapFrameX / NVIDIA 无 → Intel 用 PresentMon 即可
- **官方工具**（Steam 上 Arma 3 Tools）：Object Builder、TexView 2、Terrain Builder、Arma 3 Launcher、DSSignFile
- **社区工具**：Mikero（DePbo/MakePbo/PboProject/Rapify/DeRap）、Eliteness（PBO 浏览）、`Arma3\Dta\bin.pbo` 解包查看字体/UI 资源
- **调试**：`-showScriptErrors`、`diag_log`、Eden 编辑器实时改参数（最快的参数试错环境）

---

## 7. 三条路线的 ROI（针对"更拟真 + 更有画面感"）

| 路线 | 典型工作量 | 观感提升 | 适配你的环境（Intel 核显 1080p） |
|---|---|---|---|
| A：配置 + SQF | 1–3 天 | ★★★☆ | **首选**。先补 SSAO/水面反射/各向异性/贴图档位，再上后处理模板 |
| B：rvmat + 贴图 + 粒子 | 1–4 周 | ★★★★★ | 收益最高，但吃显存/带宽，核显上要控制贴图分辨率 |
| C：ReShade 预设 | 半天 | ★★★☆ | 单人可用；MXAO/RTGI 在核显上代价大，优先用轻量 LUT + 锐化 + 轻 AO |

**建议顺序**：先做 A 的"基线测量 + 参数矩阵"，用同一场景截图对比，确定哪几项真的提升拟真感；再把结论固化进 B 的材质/模板；C 只做最后 10% 的"胶片感"。

---

## 8. 拟真感到底由什么决定（后续任务的判据）

1. **光照一致性**：阴影方向/软硬、AO、接触阴影是否与太阳一致 → 主要靠 `shadowZDistance`、`ppSSAO`、rvmat 的 specular/fresnel
2. **材质响应**：粗糙度差异、湿滑、金属反射 → **只能靠 rvmat**，后处理无解
3. **大气透视**：远景去饱和/发蓝 → `ppHaze`/`setFog`/`setOvercast`
4. **镜头语言**：FOV、景深、曝光、轻微色差/颗粒 → 相机命令 + ppEffect
5. **帧稳定性**：卡顿比低画质更毁沉浸 → `-malloc`、帧上限、`GPU_MaxFramesAhead`

---

## 9. 下一步（任务 2 候选）

1. **基线采集**：固定场景（Eden 同一位置/时间/天气），拍 6 组对照图（当前 / +SSAO / +水面反射 / +AF16 / +贴图档 / +后处理），量化观感差异
2. **参数矩阵**：把 `Arma3.cfg` 与 profile 的每个键做成"可回滚的开关表"
3. **材质试点**：选 1 个物体（车/墙/地面），只改 rvmat，验证"塑料 → 真实"的收益
4. **决策点**：确认目标场景是**单人/编辑器**还是**多人服务器**——这直接决定 C 类工具能否进入方案
