# 注入器说明

## 组成

| 文件 | 说明 |
|---|---|
| proxy/d3d11.dll | 代理 DLL（静态链接，仅依赖 KERNEL32） |
| proxy/d3d11_proxy.cpp / build.bat | 源码与 MSVC 构建脚本 |
| presets/ | 当前生效的 5 个配置文件 |
| tonemap_aces.hlsl / ssao_final.hlsl | 两个替换着色器的源码 |
| deploy.ps1 / remove.ps1 | 一键部署 / 一键移除 |
| toggle.ps1 | 开/关 d3d11.dll |
| set-spec.ps1 | 调材质镜面参数 |

## 当前预设（presets/）

| 文件 | 内容 | 作用 |
|---|---|---|
| GP_replace.txt | 5860 42670B06 GP_tonemap.dxbc | 启用 tonemap 替换 |
| GP_tonemap.dxbc | ACES v5（曝光 0.45 / 对比 1.12 / 饱和 1.08） | 全局成像 |
| GP_ssao.dxbc | smoothstep(0.15, 1.0) | AO 对比增强 |
| GP_spec.txt | 0.12 12 | 材质镜面 F0 与幂 |
| GP_amb.txt | 0.60 0.80 0.93 1.10 | 环境光强度与色温 |
| GP_light.txt | 0.35 -0.75 0 8 | 屏幕空间光方向 + 接触阴影步数 |
| GP_present_contact.txt | mode 4 … | 接触阴影红色 debug（复制为 GP_present.txt） |
| GP_probe.txt.example | 1 | 复制为游戏目录 GP_probe.txt 开启绘制分类探针 |

## 工作方式

1. 代理 d3d11.dll，接管 D3D11CreateDevice
2. 挂钩 CreatePixelShader：按 (size, crc) 或反汇编指纹替换指定 pass
3. 挂钩 Map/Unmap：修改材质常量（镜面、环境光）
4. 挂钩 D3DCompile / D3DX11CompileFromMemory：仅记录（当前零调用）

## 已验证生效

- tonemap 替换：REPLACE ps size=5860 crc=42670B06
- SSAO resolve 替换：SSAO FINAL REPLACED len=692 crc=850EE87F
- 材质镜面注入：spec added ...
- 环境光缩放：ambient scaled amb=0.60 ae=0.80

## 已放弃

- 代理 GFSDK_SSAO：DLL 加载成功但游戏在 CreateContext 前崩溃，已回滚

## 已知限制

- 材质着色器代码不可改（编译器在 exe 内）
- 每次 A3 更新后 size/crc 变化，需重新采样
