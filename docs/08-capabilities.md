# 目前可修改的画面参数（清单）

日期：2026-10-22　状态：按“已验证 / 已实现待验证 / 已定位未实现”标注

## 1. 配置文件（改完重启游戏生效）

### Arma3.cfg

| 键 | 取值 | 影响 |
|---|---|---|
| ppSSAO | 0–8 | 环境光遮蔽质量，接触阴影 |
| PPAA | 0–7 | 抗锯齿（0 关 / 低档 FXAA / 高档 SMAA） |
| multiSampleCount | 1/2/4/8 | MSAA，核显上最贵 |
| AToC | 位掩码 | alpha-to-coverage，修草木边缘 |
| HDRPrecision | 16/32 | 高光精度 |
| cloudsQuality | 0–4 | 云层 |
| waterSSReflectionsQuality | 0–3 | 水面屏幕空间反射 |
| dynamicLightsQuality | 0–4 | 动态光源 |
| ppHaze | 0–2 | 大气雾 |
| ppBloom / ppDOF / ppRadialBlur / ppSharpen | 数值 | 泛光/景深/径向模糊/锐化 |
| GPU_MaxFramesAhead | 1–N | 预渲染帧，影响延迟 |

### Arma3.Profile

| 键 | 取值 | 影响 |
|---|---|---|
| textureQuality | 0–4 | 贴图分辨率 |
| anisoFilter | 0/4/8/16 | 各向异性过滤 |
| shadowZDistance | 50–300 | 阴影覆盖距离 |
| terrainGrid | 25 / 12.5 / 6.25 / 3.125 | 地表细节网格 |
| viewDistance / preferredObjectViewDistance / pipViewDistance | 米 | 视距 |
| sceneComplexity | 200k–2M | 场景复杂度预算（卡顿相关） |
| gamma / ppBrightness / ppContrast / ppSaturation | 浮点 | 显示端色调 |

## 2. 材质常量（运行时注入，立即生效）

材质常量缓冲 PSCB_Object1（224 字节），每个 draw 上传一次：

| 偏移 | 字段 | 含义 | 状态 |
|---|---|---|---|
| 16 | PSC_AE | 环境/自发光系数 | 可改 |
| 32 | PSC_GE | 几何/边缘项 | 可改 |
| 48 | PSC_DForced | 强制漫反射 | 可改 |
| 64 | PSC_Diffuse | 漫反射颜色 | 可改 |
| 96 | PSC_Specular | 镜面 RGB + 幂（w） | ✅ 已实现 |
| 128 | PSC_Emissive | 自发光 | 可改 |
| 144 | PSC_AmbientMid | 环境光（阴影区颜色） | 可改（全局，无梯度） |

已实现：给 specular 为 0 的材质补电介质反射（diffuse × scale，power 可调），参数在 GP_spec.txt。

限制：这些常量是**每材质一个值**，不是每像素，所以做不出“朝天的面偏蓝、墙根更暗”的梯度。

## 3. 后处理着色器（DXBC 替换，全局生效）

| Pass | 状态 | 可改什么 |
|---|---|---|
| tonemap（PSPostProcessGlowNewFinal*） | ✅ 已验证替换 | 色调映射曲线、曝光、gamma |
| SSAO final（t1→r0.x 的 3 指令拷贝） | ✅ 已验证（len=692 crc=850EE87F） | AO 对比、AO 染色 |
| SSAO 生成 / 模糊 | 已定位，未匹配 | 采样半径、强度、降噪 |
| Bloom / AA（SMAA/FXAA） | 名称已定位，未匹配 | 阈值、扩散、边缘混合 |
| 调色 / 颗粒 / 色差 / 景深 | 名称已定位 | 各自参数 |

## 4. 任务脚本层（SQF，随任务生效）

日期时间、天气（overcast/fog/rain/waves/wind）、视距、地形网格、阴影距离、相机（FOV/位置/目标）、
ppEffect 模板（ColorCorrections / FilmGrain / ChromAberration / DynamicBlur / RadialBlur）。

## 5. 不能改的

| 项 | 原因 |
|---|---|
| 材质着色器代码（ambient 计算、BRDF 结构） | 编译器嵌在 exe 内，拿不到源码 |
| 阴影算法（PCSS、阴影分辨率） | 同上 |
| 模型 / 贴图 / 植被体积 / 地形平铺 | 需要改资源（P3D/PAA/WRP） |
| 渲染管线结构 | 引擎内部 |
