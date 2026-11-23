# 22 · 着色器目录与重写（反汇编 9061 个 blob / 2585 个着色器）

日期：2026-11-23
工具：[tools/shader_catalog.py](../tools/shader_catalog.py)、[tools/dxbc_to_hlsl.py](../tools/dxbc_to_hlsl.py)
数据：`extract/shader-catalog.csv`（入库，189 KB）、`extract/shdc/catalog.jsonl`（本地，13 MB，含完整元数据）

---

## 1. 这批着色器从哪来

Arma 3 的九个着色器缓存全在 `Dta\bin.pbo` 里，合计约 83 MB：

```powershell
python tools\pbo_extract.py "<Arma 3>\Dta\bin.pbo" .shdc extract\shdc
python tools\shader_catalog.py --all                 # 解析 + 反汇编 + 骨架
python tools\shader_catalog.py --stats               # 目录统计
```

| 缓存 | blob | 唯一着色器（按 size+crc 去重） |
|---|---:|---:|
| Shaders_4_0_VS | 3632 | 511 |
| Shaders_5_0_VS | 3632 | 511 |
| Shaders_4_0_PS | 690 | 607 |
| Shaders_5_0_PS | 690 | 619 |
| Shaders_4_0_PP | 197 | 156 |
| Shaders_5_0_PP | 213 | 174 |
| Shaders_5_0_CS | 5 | 5 |
| Shaders_4_0/5_0_GS | 1+1 | 2 |
| **合计** | **9061** | **2585** |

一个"blob"是一个 DXBC 容器；同一份字节会在不同缓存/不同变体里重复出现（折叠 6476 次），
例如 `VSShaderPool` 在 5_0_VS 里有 3415 个命名条目、只有 511 份不同字节。

## 2. 目录里有什么

每个唯一着色器记录：名称、阶段、缓存、变体序号、字节偏移、**size / crc32**（与代理的
`GP_replace.txt` 同一把钥匙）、指令数、常量缓冲（名称/大小/每个变量的偏移）、
绑定资源（t/s 槽位与类型）、输入/输出签名。

```
extract/shdc/catalog.jsonl        每行一个着色器（全量元数据）
extract/shdc/catalog.csv          压缩表（已复制到 extract/shader-catalog.csv 入库）
extract/shdc/disasm/<cache>/*.asm  D3DDisassemble 原文（PS/PP/GS/CS 共 508 个文件）
extract/shdc/hlsl/<cache>/*.hlsl   ABI 骨架：能把引擎声明原样写出来的空壳
```

统计：指令数中位数 **228**、p90 **387**、最大 **2056**；2464 个着色器带常量缓冲，
604 个零资源。

## 3. 指纹审计：一个已经在"空转"的功能

拿目录对着 `dist/graph_pro_universal/files/graphics_*/GP_replace.txt` 逐行核对，
**9 把钥匙里有 3 把在当前游戏版本里不存在**：

| 钥匙（size/crc32） | 目录中的对应物 | 结论 |
|---|---|---|
| 5860 / 42670B06 | `PSPostProcessGlowNewFinalFilmic` | ✅ |
| 5732 / 92DDC7B8 | `PSPostProcessGlowNewFinalNightFilmic` | ✅ |
| 5724 / F6B44573 | `PSPostProcessGlowNewBloomInitDownsample4x` | ✅ |
| 10036 / C8390391 | `PSPostProcessSSSMVeryHigh` | ✅ |
| 9960 / 31F14A8E | `PSPostProcessSSSMHigh` | ✅ |
| 7396 / 3D897E19 | `PSPostProcessSSSMNormal` | ✅ |
| 16264 / 4AC9BAA2 | **无** | ❌ 旧版本指纹 |
| 17992 / D7B6AECA | **无** | ❌ 旧版本指纹 |
| 17960 / 13052781 | **无** | ❌ 旧版本指纹 |

那三把是 `GP_super_pbr.dxbc` 的钥匙，也就是说 **AgX / SSGI / Ultra 三档里宣传的
"3D GGX PBR 材质升级"在这台机器的游戏版本上从未命中过**——它一直静默地什么都没做。
代理不会报错，因为"没有命中"是合法状态。

正确的钥匙在目录里：`PSSSSMSuper` 的 5_0 变体是 **21144 / 0945039F** 与
**22872 / 3DAA0949**（4_0 是 19328/DB597CFB、21056/47C7D0E9）。已经核对过载荷与目标的
ABI：常量缓冲名、t0–t7/t15/t16 绑定、11 个输入寄存器全部一致，所以换了钥匙之后
替换链路是通的。三个包已改（见同日 RESULTS 记录）。

清单原本只存在于被 gitignore 的 `dist/`，所以这次把它们也入库了一份：
`inject/universal/graphics/<pack>/GP_replace.txt` 是唯一事实源，dist 里的包由它拼装。

## 4. 反汇编 → 重写

`tools/dxbc_to_hlsl.py` 把 D3DDisassemble 的文本逐条翻成 HLSL：

* 声明来自目录（真实 ABI）：常量缓冲按 **原始 float4 数组** 声明（`float4 cb0[98];`），
  这样偏移与引擎完全一致，变量名只作注释；纹理/采样器按 t/s 槽位；输入签名按寄存器；
* 指令一对一：`mov/add/mul/mad/dp2-4/min/max/frc/rsqrt/sqrt/exp/log/sin/cos/ddx/ddy`、
  整数运算、比较、`if_z/if_nz/else/endif/loop/break/continue`、`sample*/load`、
  `discard`、`movc`；修饰符 `_sat`、`-|x|` 保留；
* 不认识的指令保留成 `// TODO unsupported: <原指令>`，不会静默丢掉。

结果（fxc /O2 回编，比较指令条数）：

| 缓存 | 翻译 | 编译通过 | 指令数中位差 | 与原件差 ≤2 条 |
|---|---:|---:|---:|---:|
| Shaders_5_0_PP（后处理族） | 143 | **119（83%）** | 0 | 61% |
| Shaders_5_0_PS（材质族） | 619 | 111（18%） | −17 | 29% |

后处理族已经足够好：它们就是能被代理安全替换的那一族（113→174 个唯一变体）。
材质族的缺口清晰可见：`icb`（indexable constant buffer）、`gather4`、`f16tof32`、
UAV 写入、`bfi/ubfe` 这些指令还没有映射，而且 545 条指令的 `PSSSSMSuper` 这类着色器
本来就该手写而不是机械翻译。

## 5. 改写一个着色器的完整流程

```powershell
# 1. 找到它（名字 / 阶段 / 指纹）
Select-String extract\shader-catalog.csv -Pattern 'PSSSSMSuper'

# 2. 读反汇编与骨架
notepad extract\shdc\disasm\Shaders_5_0_PS\PSSSSMSuper_0.asm
notepad extract\shdc\hlsl\Shaders_5_0_PS\PSSSSMSuper_0.hlsl

# 3. 写新 shader（骨架里已经声明好常量缓冲/资源/签名）
fxc /T ps_5_0 /E main /O2 /Fo GP_xxx.dxbc my_shader.hlsl

# 4. 用目录里的 (size, crc32) 登记，装机后看日志 REPLACED PS
#    21144 0945039F GP_xxx.dxbc
```

自动翻译的产物可以直接作为起点：`extract/shdc/rewrite/<cache>/*.hlsl`。

## 6. 边界（必须说清）

- **没有像素级验证**。回编得到的指令条数一致只能说明"翻译没漏指令"，不能说明画面一致；
  真正的验收仍然是进游戏 A/B 截图，而这一步按仓库约定由使用者执行。
- 反汇编文本来自 `d3dcompiler_47`；BIS 的 RDEF 名称表比 MS 反射的预期偏 1 字节
  （`D3DReflect` 读出来是 `OSITION`），所以元数据统一从反汇编文本解析，而不是 D3DReflect。
- VS/GS/CS 只做了目录与骨架：代理只钩 `CreatePixelShader`，替换它们没有意义。
- 着色器缓存属于游戏资源，**不随仓库分发**（`extract/shdc/` 已在 .gitignore 中）。
