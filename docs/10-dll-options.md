# 10 · 还能用哪些 DLL / 框架（Arma 3 DX11 注入扩展调研）

日期：2026-10-22　状态：桌面调研；本文没有【实测】条目，全部结论都需要在本机复现一次

**证据标记**

- **【事实】**：有官方文档 / 源码 / README 可查，文末给链接。
- **【实测】**：本项目已经验证过（见 docs/05、docs/08、RESULTS.md）。
- **【推测】**：没有直接证据，按机制推断，必须实测才能采信。
- **【未知】**：查不到可靠信息，或只在很老的资料里出现过。

**本机前提（会改变结论，务必先看）**

- 游戏：Arma 3 2.22 / Real Virtuality 4 / 只导入 d3d11.dll + DXGI.dll。
- 现有代理：d3d11.dll，vtable patch `Present(8)`、`Map(14)/Unmap(15)`、`OMSetRenderTargets(33)`、`CreatePixelShader(15)`。
- 测试机是 **Intel 核显**（RESULTS.md 第 1 节）。这一条直接判死 DLSS（需 RTX）和 Nsight（需 NVIDIA 卡），也让 DXR/BVH 路线性价比极低。
- 私有服、无 BattlEye，允许注入；但**联机状态**会影响 ReShade 的深度可用性（见 2.1）。

---

## 0. 先说结论

1. **能立刻加能力、且不和现有代理打架的只有两类**：离线抓帧工具（RenderDoc，半天内回答"世界矩阵/BVH 到底可不可行"）和地址级 hook 库（MinHook/Detours，用来补 `DrawIndexed` / `VSSetConstantBuffers` / `PSSetConstantBuffers`）。
2. **后处理框架里唯一值得认真评估的是 ReShade**：它和我们的 d3d11.dll 代理不是"二选一"——ReShade 可以装成 dxgi.dll，理论上能分层；但联机时 ReShade 会主动解绑深度语义（源码级证据），依赖它内置深度的效果在私有服会直接失效。
3. **明确不要碰**：ENB（闭源、无 Arma 版、同为 d3d11.dll）、dgVoodoo2（输入不是 D3D11）、Geo-11（立体 3D 驱动，不提供我们要的能力）、DXVK（换掉整个 D3D11，代理全废）、PIX（只支持 D3D12）、DLSS（无运动矢量 + 核显）。
4. **D3D11On12 → D3D12 → DXR 理论可行，但官方原话是"不建议用于复杂 3D 场景"**（CPU 中等开销、显存显著开销），再加上核显没有 RT 硬件，现阶段不值得投入。

---

## 1. 总表

工作量是**估算**（含调试和回滚），不是承诺。

| 方案 | 类型 | 能否用于 Arma3 DX11 | 与现有 d3d11 代理是否冲突 | 能带来什么 | 工作量 |
|---|---|---|---|---|---|
| ReShade 本体 | 后处理注入框架（dxgi.dll 或 d3d11.dll 代理） | 能（社区长期有 Arma3 预设；2.22 需实测） | dxgi 模式：可分层【推测】；d3d11 模式：硬冲突 | 成熟后处理栈、深度检测、ReShade FX、addon 生态（MXAO/RTGI 等） | 0.5 人日 |
| ReShade Add-on（自写） | 插件 API（宿主内运行） | 能（必须挂 ReShade） | 同 ReShade；等于在别人的 hook 上再挂一层 | draw/DSV/pipeline 事件、换 shader、加 pass、跳过 draw | 5–10 人日 |
| ENB | 后处理注入（d3d11/d3d9 代理，闭源） | 未知，成功率低【推测】 | 硬冲突（同名 d3d11.dll） | SSAO/SSIL/DOF/HDR/ToneMapping（如果它能认出深度） | 1 人日试 |
| Special K | 注入/显示层框架 | 能注入（D3D11 Enhanced） | dxgi 模式：可分层；d3d11 模式：硬冲突 | HDR retrofit、flip model、限帧、纹理替换、shader dump | 1 人日 |
| Geo-11 | 立体 3D 驱动（d3d11 代理） | 能加载，但没有我们要的能力 | 硬冲突 | 无（只有 stereo 和 shader fix 基建） | 0.5 人日 |
| dgVoodoo2 | 旧 API → D3D11 翻译层 | 不适用（输入不是 D3D11） | 无（根本不会加载） | 无 | 0 |
| DXVK | D3D11 → Vulkan 翻译层 | 能跑，但代价大【推测】 | 硬冲突（同时替换 d3d11 + dxgi） | Vulkan 后端、部分卡上的性能 | 1 人日试 |
| D3D11On12 | D3D11 → D3D12 桥 | 理论可行 | 不冲突（但要重写设备创建 + 加 dxgi 代理） | 进 D3D12：DXR、DLSS/FG 的 D3D12 后端 | 20–40 人日 |
| MinHook | inline hook 库 | 能 | 无 | 按地址挂钩（导出函数、任意函数） | 0.5–1 人日 |
| Detours | inline hook 库（微软） | 能 | 无 | 同上，事务式挂接/卸载 | 1 人日 |
| EasyHook | 注入 + hook（.NET 为主） | 能，但久未维护 | 无 | 托管侧钩子/注入 | 不推荐 |
| Frida | 动态插桩 | 能（研究用） | 无 | 脚本化 hook / trace，改完即走 | 0.5 人日 |
| RenderDoc | 离线抓帧 | 能（官方支持 D3D11） | 抓帧工具也 hook 同一套 API，建议先在干净目录抓 | 一帧全量：draw、VB/IB、cbuffer、shader、pipeline | 0.5–1 人日 |
| Nsight Graphics | 离线抓帧/分析 | 需 NVIDIA GPU | 未测 | 同 RenderDoc + GPU 计数器 | 0（本机不可用） |
| PIX | 离线抓帧 | 不能（D3D12 only） | — | — | 0 |
| 3Dmigoto | DX11 注入/dump 框架（d3d11.dll） | 未知（2014 年记录为不可用） | 硬冲突（d3d11.dll） | 逐 draw dump VB/IB/CB/depth、shader hunting | 1–2 人日 |
| DLSS | 超分 | 不能（无 MV + 需 RTX） | 可共存，但要改渲染管线 | 画质/帧率 | 30+ 人日 |
| FSR 1 / NVIDIA NIS | 空间超分 | 能 | 无（塞进 Present pass 即可） | 低采样率下救画质/提帧 | 2–4 人日 |
| FSR 2/3 | 时序超分/插帧 | 不能（缺 MV 和抖动） | 需改管线 | 更好的超分/插帧 | 10–20 人日 |
| XeSS | 超分 | 不能（DX11 要求 Arc；且缺 MV） | 需改管线 | 超分 | 5–10 人日 |

---

## 2. 逐个方案

### 2.1 ReShade 本体

- **【事实】** ReShade 是通用后处理注入器，支持 D3D9/10/11/12、OpenGL、Vulkan；安装器把代理 DLL 放到游戏目录（dxgi.dll 或 d3d11.dll，安装时可选）。add-on API 自 5.0 起提供（`include/reshade_api.hpp`、`include/reshade_events.hpp` 可查，二手说明见 reshade.dev）。
- **【事实】** Arma 3 社区长期在用 ReShade 预设（Nexus 有 Arma3 分类），所以"能不能跑"基本不是问题；2.22 需要实测一次。
- **和我们的冲突**：如果 ReShade 装 **dxgi.dll**，我们的 d3d11.dll 继续负责设备创建，ReShade 在 dxgi 层截 `CreateSwapChain` 并 patch 它自己那份 Present vtable；我们随后在 `CreateDeviceAndSwapChain` 返回后 patch 同一张 vtable，谁后 patch 谁在外层，能形成调用链。**【推测】可共存，但要实测"外层是谁"**——如果我们的 pass 在外层，ReShade 的效果会作用在我们的输出之后；反之我们的调色会被 ReShade 再处理一遍。如果 ReShade 装 d3d11.dll，则只能二选一。
- **额外能力**：现成的深度缓冲检测（Generic Depth）、成熟的后处理栈、ReShade FX 脚本、大量现成 shader（MXAO、RTGI 之类）。
- **风险（重要）**：ReShade 在检测到持续高网络流量时，会把 add-on/效果的纹理语义（包括深度）解绑。源码 `source/runtime.cpp` L952–981：`addon_enabled = traffic < 10;` 然后 `update_texture_bindings(... addon_enabled ? ... : 0)`。私有服也是联机，**依赖 ReShade 内置深度的效果会失效**；add-on 事件本身还会触发，自己跟踪 DSV 的 addon 可以绕开。

### 2.2 ReShade Add-on API（自己写 addon，或把现有逻辑迁进去）

- **【事实】** 事件表覆盖得很全：`draw` / `draw_indexed`（返回值 `true` 可以**阻止该 draw 执行**）、`bind_render_targets_and_depth_stencil`（拿 DSV）、`bind_pipeline_states`、`create_pipeline`（可改管线子对象，等于通用版"换 shader"）、`map_buffer_region` / `unmap_buffer_region`、`present`。共 84 个事件（`reshade_events.hpp`）。
- **能读深度吗**：能。两条路：用 ReShade 的深度语义（联机被解绑），或者在自己的 addon 里跟踪 `bind_render_targets_and_depth_stencil` 拿 DSV、自己 `copy_resource` 出来——后者不受网络检测影响。
- **能读法线吗**：不能。Arma 没有 G-buffer 法线，ReShade 也变不出来；只能从深度重建（项目已证明这条路在远场不可靠，见 RESULTS.md）。
- **能替换 DX11 管线状态吗**：**创建时能改，绑定时只能看**。`create_pipeline` 允许改子对象（可以换 shader 字节码）；`bind_pipeline_states` 是 `void` 回调、没有"拦截"语义；想任意时刻改状态，还是自己代理更自由。
- **代价**：ReShade 的 `api::` 抽象层只暴露它愿意暴露的东西；把现有 Present pass、shader 替换、材质常量注入迁过去，等于重写一遍（5–10 人日），而且以后 ReShade 升级可能破 API。收益是不用自己维护 vtable 表和设备生命周期。**【推测】短期不划算，除非打算长期做通用工具。**

### 2.3 ENB

- **【事实】** enbdev 自述：分"通用版"和"游戏专属版"；专属版按游戏定制，闭源；效果包括 SSAO、SSIL、DOF、Bloom、HDR、ToneMapping 等。
- **Arma 3**：enbdev 的游戏列表里没有 Arma 3，也没有专属版；通用 DX11 版能不能认出 Arma 的深度和 shader 是 **【未知】**，按 ENB 一贯的"按游戏调"风格，**【推测】成功率很低**。
- **冲突**：ENB 是 d3d11.dll / d3d9.dll 代理，硬冲突。
- **结论**：不值得试。它有的东西（HDR、tonemap、SSAO）我们要么已经有，要么 ReShade 能给。

### 2.4 Special K

- **【事实】** 官方兼容表：D3D11 = "Enhanced support including DXGI flip model override, HDR retrofit, texture modding, and shader debugging"；D3D12 = basic；D3D10 = unsupported（flip model override 有时能 work）；D3D9 = basic。
- **能带来**：HDR retrofit（SDR 游戏输出 HDR）、flip model（降延迟）、帧率限制、纹理替换、shader dump。**没有 mesh dump**——文档功能表里没有这一项，别指望它给几何/BVH。
- **冲突**：dxgi.dll 模式可分层；d3d11.dll 模式硬冲突；它也 hook Present，和 ReShade 一样有"谁在外层"的问题。
- **结论**：如果目标是 HDR 或延迟，值得试 1 人日；对"GI/接触阴影/BVH"没有帮助。

### 2.5 Geo-11

- **【事实】** helixmod / 3D Vision 社区的 DX11 立体 3D 驱动（SBS / 3D Vision 输出），以 d3d11.dll 代理形式工作，按游戏做 shader fix。
- **对我们**：它解决的是"把一帧变成左右眼两帧"，不提供深度、法线、几何或后处理能力。唯一可借鉴的是它的 d3d11 代理 + shader hunting 结构。
- **冲突**：d3d11.dll 硬冲突。
- **结论**：不用。

### 2.6 dgVoodoo2

- **【事实】** 它是旧 API（Glide / DirectDraw / D3D8/9）→ D3D11 的翻译层；Special K 官方兼容表也明确写 "DirectDraw / Direct3D 2-8 requires dgVoodoo 2 to translate the calls to Direct3D 11"。
- **Arma 3**：输入本来就是 D3D11，dgVoodoo2 没有可翻译的东西，**用不上**；也不会和我们的代理冲突（根本不会加载）。
- **结论**：跳过。

### 2.7 DXVK

- **【事实】** README 定位：Vulkan-based translation layer for Direct3D 8/9/10/11，主要面向 Linux/Wine；Windows 上有社区构建，但不是主目标。
- **Arma 3**：能跑（**【推测】**，需要试），但它同时替换 d3d11.dll 和 dxgi.dll——我们的代理彻底失效，所有 D3D11 钩子归零；拿到的是 Vulkan，接不了 DXR，也接不了任何 D3D11 生态工具。
- **唯一价值**：如果哪天想验证"Vulkan 后端下 Arma 是否更快"，可以单独试，和本项目目标无关。
- **结论**：不建议。

### 2.8 D3D11On12（→ D3D12 → DXR 的唯一现实路径）

- **【事实】** `D3D11On12CreateDevice(pDevice, Flags, pFeatureLevels, FeatureLevels, ppCommandQueues, NumQueues, NodeMask, ...)`：用一个已存在的 D3D12 device + 3D command queue 创建 `ID3D11Device`；每个 D3D11 调用会被 11on12 驱动翻译成 D3D12 命令。Windows 10 1803 起支持在 11on12 设备上建 swapchain。
- **官方限制（原文要点）**：D3D11On12 **没有为性能优化**，相比原生 D3D11 有 "moderate CPU overhead、minimal GPU overhead、significant memory overhead"，因此 **"not recommended ... for complicated 3D scenes"**，建议用于简单场景或 2D。
- **怎么接**：我们的 d3d11.dll 代理改成先 `D3D12CreateDevice` + 建 queue，再 `D3D11On12CreateDevice` 把 `ID3D11Device` 交给游戏；同时还要代理 dxgi（游戏的 swapchain 是走 `IDXGIFactory` 建的，不经过 D3D11 设备），把 backbuffer 用 `CreateWrappedResource` 包成 D3D11 资源。
- **收益**：几何进了 D3D12，可以建 BLAS/TLAS → DXR 光追、DLSS/DLSS-FG 的 D3D12 后端。
- **风险**：Arma 正是"复杂 3D 场景"，官方不推荐；11on12 有功能缺口（历史版本对 shader interface、swapchain 的支持都是后来补的）；本机 Intel 核显没有 RT 硬件，DXR tier 未必可用。**20–40 人日，不建议现在做。**

### 2.9 Hook 库：MinHook / Detours / EasyHook / Frida

- **【事实】** MinHook：x86/x64 inline hook，BSD-2，v1.3.4（2025-03-28）仍在维护；启用 hook 时会挂起/恢复线程，`MH_CreateHookApi` 可直接按导出名挂钩。
- **【事实】** Detours：微软维护，4.0.1，MIT；`DetourTransactionBegin / DetourUpdateThread / DetourAttach / DetourTransactionCommit` 事务式挂接，x64 支持。
- **【事实】** EasyHook：最后的 release 是 v2.7.7097.0（2020-02-04），以 .NET 托管注入为主，也支持 native DLL；x64 可用但基本停更。
- **【事实】** Frida：`Interceptor.attach` 跨平台，x64 可用，脚本化，适合"先搞清楚再写 C++"的研究阶段。
- **和手写 vtable patch 的取舍**：
  - vtable patch 优点：不改代码字节、只换指针、易回滚、天然支持多层链式；缺点：只能钩 COM 方法、必须在对象创建后、拿不到内部直接调用、接口版本一变槽位就变。
  - **MinHook 的价值在于"按地址钩"**：从 vtable 里取出函数地址再用 MinHook 挂，天然兼容 `ID3D11DeviceContext` / `1` / `2` / `3` / `4`，也能安全调用原函数；`D3D11CreateDevice` 这种导出函数则必须用 MinHook/Detours。
  - **建议**：Present / Map 保留现有 vtable patch；新增 `DrawIndexed`、`VSSetConstantBuffers`、`PSSetConstantBuffers` 用"vtable 取地址 + MinHook"，不要硬编码槽位。`DrawIndexed` 每帧上万次，钩子体里不要加锁、不要分配内存。
- **槽位参考**（和你们已用的 `Map=14 / Unmap=15 / OMSetRenderTargets=33` 同一套基准，建议用 d3d11.h 顺序再核一遍）：`VSSetConstantBuffers=7`、`DrawIndexed=12`、`Draw=13`、`PSSetConstantBuffers=16`、`IASetVertexBuffers=18`、`IASetIndexBuffer=19`。
- **EasyHook / Frida**：研究阶段 Frida 半天能出结果；正式注入不要用 EasyHook（停更 + .NET 依赖）。

### 2.10 RenderDoc（离线抓帧，第一优先）

- **【事实】** 官方支持 D3D11；能看完整 pipeline state、**mesh buffer 检查（VS 前后、可反投影到世界空间）**、buffer 导出 CSV 或 raw binary、shader 反汇编、pipeline 导出 HTML。
- **怎么用**：RenderDoc 启动 `arma3_x64.exe`（或注入），F12 抓一帧；在 Mesh 视图选中某个 draw，导出它的 VB/IB；在 Pipeline State 里看 VS/PS 的 cbuffer 原始字节；`Save resource` 把 buffer 存盘。
- **能直接回答三个问题**：① world matrix 在不在 VS cbuffer（在哪个 bind、哪个 offset）；② 一帧多少个 draw、多少个 unique IB（建 BVH 的 mesh 数量级）；③ 顶点格式和索引格式（能不能直接喂 BLAS）。
- **冲突**：RenderDoc 也 hook d3d11/dxgi，和我们的代理可能互相干扰。**建议先在"移走我们代理"的干净目录抓一帧**，确认能抓，再试带代理。
- **风险**：Arma 一帧几千 draw，捕获文件几百 MB、抓帧瞬间卡死几秒；无 BattlEye 所以不会被拦。
- **工作量**：0.5–1 人日。

### 2.11 NVIDIA Nsight Graphics / PIX

- **【事实】** PIX 的官方定位是 "Performance tuning and debugging for DirectX 12 games on Windows"；GPU capture 只支持 D3D12 → **Arma 的 D3D11 用不了**（除非先走 D3D11On12）。
- **Nsight Graphics**：支持 D3D11/12/Vulkan，但要求 NVIDIA GPU → **本机 Intel 核显不可用**（换 N 卡机器可以，但捕获文件可以在本机看）。
- **结论**：本机都不适用，不要在这上面花时间。

### 2.12 3Dmigoto

- **【事实】** DX11 modding wrapper（d3d11.dll + nvapi64.dll），提供 ShaderFixes / ShaderOverride / shader hunting / frame analysis；`d3dx.ini` 的 `analyse_options` 支持 `dump_rt`、`dump_depth`、`dump_tex`、`dump_cb`、`dump_vb`、`dump_ib`，按 draw call 分目录 dump。
- **对 Arma 3**：老 wiki（2014 年，0.53）记录是 "loads and runs，但 HLSL 反编译报错，不可用"；2.22 是 **【未知】**，**【推测】** 现代版本可能改善，必须实测。最新 release 是 1.3.16（2018-01-30），但 master 分支 2022 年还在更新（VS2022 工程）。
- **冲突**：它自己就是 d3d11.dll → **和我们硬冲突**。只能做"研究构建"：把我们的代理移走，单独用 3Dmigoto 跑一帧。
- **能带来**：运行时逐 draw 的 VB/IB/CB/depth dump、shader hash 表、常量缓冲可视化——正好补上 RenderDoc"只能看一帧"的短板，用来确认"world matrix 是每帧变的还是每物体变的"。
- **工作量**：1–2 人日（含折腾 ini 和兼容性）。

### 2.13 DLSS

- **【事实】** DLSS 2+ 的输入是 color + depth + motion vectors + jitter，必须在 UI 合成之前、按内部渲染分辨率执行；DLSS 3 帧生成要求 D3D12。
- **Arma**：没有运动矢量；可以用"深度 + 上一帧 view-projection"生成相机 MV（社区 mod 的常见做法），但需要矩阵，而且动态物体/植被会拖影。
- **硬件**：需要 NVIDIA RTX；**本机 Intel 核显直接排除**。
- **结论**：30+ 人日，收益不确定，不做。

### 2.14 FSR 1 / NVIDIA NIS（唯一现实可用的超分）

- **【事实】** FSR 1 = EASU（空间上采样）+ RCAS（锐化），**只需要颜色**，不依赖深度/MV/抖动；NVIDIA Image Scaling SDK 提供 DX11/DX12/Vulkan 的 compute shader（NVIDIA 官方 README 明确写了 DX11 可集成）。
- **怎么接**：塞进我们的 Present pass；前提是游戏以 **Sampling < 100%** 渲染（Arma 3 的 Sampling 就是渲染分辨率百分比），再上采样到窗口分辨率。
- **收益**：核显上帧率提升明显，代价是清晰度；**不解决光照问题**。
- **冲突**：无（同一 pass 里多一个 draw）。**工作量 2–4 人日**，风险低。

### 2.15 FSR 2/3

- **【事实】** FSR 2 需要 color + depth + motion vectors + jitter + 反应掩码/透明度掩码；官方示例后端是 D3D12/Vulkan（DX11 要自己移植后端）。
- **Arma**：缺 MV、缺 jitter → 不改造引擎接不进去；改造量约等于自己写一套 TAA。
- **结论**：10–20 人日，不建议。

### 2.16 XeSS

- **【事实】** XeSS-SR 需要 jitter + 运动矢量 + 深度；官方 Requirements 写得很清楚：**DirectX11 需要 Intel Arc 或更新**；DirectX12 才支持 Iris Xe 及其他 SM 6.4 + DP4a 的 GPU。
- **本机**：DX11 + 核显 → **不支持**；而且同样缺 MV。
- **结论**：5–10 人日，硬件不允许，不做。

---

## 3. 世界矩阵 / 几何到底能不能拿到

这是整个扩展方向的瓶颈，分四条路，按"证据强度"排序。

### 3.1 运行时读 VS 常量缓冲（最直接，但没验证过）

- 现状：我们只 hook 了 `Map/Unmap` 并抓了 `PSCB_Object1`（224 B），**VS 侧的 cbuffer 从来没抓过**。
- 做法：hook `VSSetConstantBuffers(7)` 记录每个 draw 绑定的 cb；在 `DrawIndexed(12)` 里把当前 VS cb 的内容 dump 出来，扫描 4×4 / 3×4 矩阵，和相机矩阵相乘验证。
- 风险 **【推测】**：Arma 可能把 world 变换烘进顶点、或放在 StructuredBuffer/instance data 里；不先 dump 无法判断。
- 成本：MinHook 接入 + 一天调试。

### 3.2 离线抓帧（最稳，先做这个）

- RenderDoc / 3Dmigoto 二选一（见 2.10、2.12）：直接看某个 draw 的 VS cbuffer 原始字节和 VB 位置，**一个下午就能回答"矩阵在不在、在哪个 offset"**。
- 顺带能统计：draw 数量、unique IB 数量、三角形总数、顶点格式——这是判断 BVH 可行性的原始数据。

### 3.3 解析游戏资源（另一条路，但缺实例变换）

- Arma 的模型是 P3D（ODOL）、地形是 WRP，社区有解析工具；离线能拿到静态几何和材质。
- 但每个物体的**实例变换**仍要运行时读（引擎对象链表/场景图），这条路比 3.1 更脆（版本一换就崩）。**【推测】不推荐作为主线。**

### 3.4 只有深度时能做什么

- 法线：邻域深度叉积重建，远场精度崩（RESULTS.md 已量化：24 位深度在 d>0.999 时失真）。
- 接触阴影：屏幕空间朝光源 ray march，只需要深度 + 光源方向，**不需要 G-buffer 法线**，是深度路线里唯一还值得试的。
- SSGI：需要 color + normal，Arma 没有 normal，只能重建，效果和稳定性都差；项目已经证伪过一版 AO。

### 3.5 BVH 可行性判断

- 数据量 **【推测】**：一帧几千 draw，unique mesh 可能几百到几千，三角形总量百万到千万级；地形是分块的。
- 显存/带宽：BLAS 按 unique mesh 缓存，TLAS 每帧重建；核显的显存和带宽是硬瓶颈。
- 结论：**先用 RenderDoc 把 draw 数、unique IB 数、三角形总数统计出来再决定**。如果目标只是接触阴影，屏幕空间方案比 BVH 便宜一个数量级；BVH 只在"真光追阴影/反射"时才值得。

---

## 4. 冲突矩阵（谁能和谁一起跑）

| 组合 | 结果 |
|---|---|
| 我们（d3d11.dll）+ ReShade（dxgi.dll） | 理论可分层，两个 Present 钩子；【推测】可行，需实测外层顺序 |
| 我们 + ReShade（d3d11.dll） | 不可能（同名文件） |
| 我们 + 3Dmigoto | 不可能（都要 d3d11.dll） |
| 我们 + Special K（dxgi.dll） | 理论可分层 |
| 我们 + ENB / Geo-11 / DXVK | 不可能（都替换 d3d11.dll） |
| 我们 + RenderDoc | 抓帧工具也 hook 同一 API；建议干净环境先抓一帧 |
| 我们 + MinHook / Detours / Frida | 可以；注意 hook 顺序和线程挂起时机 |

**通用规则**：`d3d11.dll` 在进程里只能有一个；`dxgi.dll` 可以分层，但每层都会 patch swapchain vtable，**谁最后 patch 谁在最外层**，调试时先打印一层"Present 链"确认顺序，否则会出现"我的 pass 不生效"的假象。

---

## 5. 最值得先试的三个

### ① RenderDoc 离线抓一帧（0.5–1 人日）

理由：它是唯一能在半天内回答"world matrix 在不在 cbuffer、一帧多少 unique mesh、BVH 值不值得做"的工具，零集成风险，不改一行注入代码。抓完这一帧，3.1 和 3.5 的争论就有数据了。

### ② MinHook 补 `DrawIndexed` / `VSSetConstantBuffers` / `PSSetConstantBuffers`（0.5–1 人日）

理由：现在缺的不是"想法"，是"每个 draw 的上下文"。vtable patch 只能覆盖我们手动列出的槽位，而且接口版本一变就错位；用"vtable 取地址 + MinHook"能一次覆盖 `ID3D11DeviceContext1-4`，并且能安全调用原函数。这两个钩子一上，逐物体材质、逐物体矩阵、draw 统计全都通了。

### ③ 3Dmigoto 单独跑一个"研究构建"（1–2 人日）

理由：RenderDoc 只能看一帧，3Dmigoto 能逐 draw dump `dump_cb / dump_vb / dump_ib / dump_depth`，还能做 shader hunting——用来确认"矩阵是每帧变还是每物体变""shader 变体到底有多少"。代价是它占 d3d11.dll，必须把我们的代理临时移走，所以放在第三位、当一次性研究工具用。

> 备选：如果目标不是 BVH 而是"立刻好看/更流畅"，跳过上面三条，直接在 Present pass 里接 **FSR 1 / NIS**（2–4 人日）——这是唯一在 Intel 核显 + 无 MV 条件下确定能落地的画质/性能方案。

---

## 6. 参考来源

- D3D11On12 概述（含"不适合复杂 3D 场景"原文）：https://learn.microsoft.com/en-us/windows/win32/direct3d12/direct3d-11-on-12
- D3D11On12CreateDevice：https://learn.microsoft.com/en-us/windows/win32/api/d3d11on12/nf-d3d11on12-d3d11on12createdevice
- ReShade 联机解绑深度的源码：https://raw.githubusercontent.com/crosire/reshade/main/source/runtime.cpp （L952–981）
- ReShade add-on 事件表：https://raw.githubusercontent.com/crosire/reshade/main/include/reshade_events.hpp
- ReShade add-on 接口：https://raw.githubusercontent.com/crosire/reshade/main/include/reshade_api.hpp
- ReShade 功能说明（二手）：https://reshade.dev/features.html
- Special K 兼容表（D3D11 Enhanced 原文）：https://wiki.special-k.info/en/Compatibility/List
- 3Dmigoto 仓库：https://github.com/bo3b/3Dmigoto
- 3Dmigoto d3dx.ini（analyse_options 的 dump_cb/dump_vb/dump_ib）：https://raw.githubusercontent.com/bo3b/3Dmigoto/master/Dependencies/d3dx.ini
- 3Dmigoto 游戏兼容笔记（Arma 3 旧记录）：https://github-wiki-see.page/m/bo3b/3Dmigoto/wiki/Game-notes
- RenderDoc 功能表（D3D11、mesh 检查、buffer 导出）：https://renderdoc.org/docs/getting_started/features.html
- PIX 官方定位（DirectX 12）：https://devblogs.microsoft.com/pix/
- MinHook README（v1.3.4）：https://github.com/TsudaKageyu/minhook
- Detours README（4.0.1 / MIT）：https://github.com/microsoft/Detours
- EasyHook README（v2.7.7097.0）：https://github.com/EasyHook/EasyHook
- Frida JavaScript API（Interceptor）：https://frida.re/docs/javascript-api/
- XeSS-SR 开发者指南（DX11 需 Arc；jitter/MV/depth）：https://github.com/intel/xess/blob/main/doc/xess_sr_developer_guide_english.md
- DLSS SDK 仓库：https://github.com/NVIDIA/DLSS
- FSR 2.2.1 README（输入资源/运动矢量）：https://github.com/GPUOpen-Effects/FidelityFX-FSR2
- DXVK README（D3D8/9/10/11 → Vulkan）：https://github.com/doitsujin/dxvk
- ENB 官网自述（通用版/专属版、闭源、效果列表）：https://www.enbdev.com/

---

## 7. 待实测清单（按优先级）

1. RenderDoc 在干净目录抓一帧 Arma 3：确认能抓、导出 1 个 draw 的 VS cbuffer 和 VB/IB。
2. 带我们的 d3d11.dll 代理再抓一次：确认 RenderDoc 与代理是否互相干扰。
3. ReShade 装 dxgi.dll + 我们的代理：打印 Present 调用链，确认谁在外层；进私有服看深度是否被解绑。
4. 3Dmigoto 单独构建：确认 2.22 能否加载、shader 反编译是否还报错、`analyse_options = dump_cb dump_vb dump_ib` 能否出文件。
5. MinHook 挂 `DrawIndexed`：统计每帧 draw 数、unique IB 数、VS cb 绑定分布。
6. FSR 1 / NIS 在 Present pass 的原型：Sampling 70% + 上采样，测帧率和清晰度。
---

## 实测补充（2026-10-22 05:00，本机现场数据，非检索）

### 1. 这个引擎会还原 vtable 补丁

安装后立刻回读：vt12=1 vt13=1 vt19=1 vt20=1 vt21=1（全部是我们的钩子）。
运行一段时间后复查：vt12=0 vt19=1 vt20=0 —— DrawIndexed(12) 与 DrawIndexedInstanced(20) 被改回原函数，而 IASetIndexBuffer(19) 存活。

- 进程中没有任何覆盖层 DLL 会做这种事（模块表里只有 Steam overlay、GFSDK_SSAO、PhysX、Tobii 等）。
- 后果：只打一次 vtable 补丁的绘制钩子会静默失效，表现为“钩子装上了但一次都没被调用”。
- 解法：每帧重断言。加入 ReassertPatches() 后，Draw 立刻从 0 变成每帧约 420 次调用。
- 这条对任何基于 vtable 的思路都适用，包括 ReShade add-on 的 draw 拦截。

### 2. 场景几何不在我们抓到的绘制里

300 帧窗口内只抓到 34 个 Draw，全部是 count=4 的全屏四边形（后处理 pass），vs0 常量缓冲固定 240 字节。
真实的场景几何（地形/物体）没有出现。

### 3. Arma 失焦时停止 Present

45 秒内只有约 300 次 Present（应为 2700 次）。窗口不在前台时引擎暂停渲染，
任何依赖 Present 的触发机制（本项目的 GP_dump.txt / GP_drawlog.txt）都会挂起等待。
触发时机必须在游戏处于前台且 3D 画面可见时。
### 4. 抓到的常量缓冲里没有世界矩阵（最终判定）

300 帧连续窗口内共 34 个 Draw，全部 count=4（全屏四边形，后处理 pass），每帧 2~3 个。
导出的 40 个 VS 常量缓冲（各 240 字节）扫描结果：

- 含 4x4 仿射矩阵（末行≈(0,0,0,1)、基向量长度 0.5~2、正交性误差<0.25）的文件数：**0 / 40**
- 单个缓冲非零浮点数：20 / 60，首个 float4 为 (1,0,0,0) —— 典型的后处理参数块，不是几何常量

**结论：通过 D3D11 vtable 钩子无法获得世界矩阵或场景几何。** 场景几何既不经过我们钩到的 draw 入口，
也不产生任何可见的几何常量。要拿到几何只能改用独立工具（RenderDoc / 3Dmigoto 研究构建），
而那只解决“知道能不能”，不解决“做完要多久”。

按 20–40 人日的估算与半分辨率低采样 GI 的收益上限，本线判定为**投入产出不成立，终止**。
