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

## 3. 指纹审计：目录不是运行时全集（一次自我纠错）

拿目录对着 `GP_replace.txt` 逐行核对，第一遍得出的结论是"9 把钥匙里有 3 把不存在，
PBR 从未生效"。**这个结论是错的**，核对过程反而证明了另一件事——用
[tools/verify_shaders.py](../tools/verify_shaders.py) 读一次真实运行日志：

```
key              shader                            hits
5860/42670B06    PSPostProcessGlowNewFinalFilmic    1
5732/92DDC7B8    PSPostProcessGlowNewFinalNightFilmic 1
5724/F6B44573    PSPostProcessGlowNewBloomInitDownsample4x 1
10036/C8390391   PSPostProcessSSSMVeryHigh          1
9960/31F14A8E    PSPostProcessSSSMHigh              1
7396/3D897E19    PSPostProcessSSSMNormal            1
16264/4AC9BAA2   (not in catalog)                   1
17992/D7B6AECA   (not in catalog)                   1
17960/13052781   (not in catalog)                   1
PBR (PSSSSMSuper) hits: 3
```

三把"不存在"的钥匙**每次运行都命中**，日志里是
`REPLACED PS len=16264 crc=4AC9BAA2 -> 16052 bytes`。

所以正确的结论是：

- **`Dta\bin.pbo` 里的 .shdc 缓存不是引擎运行时的全集**。这台机器上 `PSSSSMSuper`
  的实际变体是 16264 / 17992 / 17960 三份，而缓存里只有 21144 / 22872；
  再往外扫 1943 个 PBO（本体 + Workshop）也只有 bin.pbo 带 `.shdc`，
  所以这三份要么是引擎按材质特性在运行时拼出来的，要么来自缓存之外的路径。
- **目录能证明"这把钥匙对应哪个着色器"，不能证明"这把钥匙一定被创建"**。
  反过来，**没命中才可疑**：只要跑过一次、日志里没有 `REPLACED PS`，那才是死钥匙。
- 所以审计的正确做法是 `verify_shaders.py` 这种"清单 × 真实日志"的交叉核对，
  而不是拿清单对着缓存的静态列表。

这三份运行时 blob 已经抓到过一次：开发时给代理临时加过 `GP_dump_bytes.txt`
开关（置入后每次 `CreatePixelShader` 把 blob 落到 `GP_psdump\<size>_<crc>.dxbc`），
一次运行得到 **234 个运行时 PS**，其中就有 16264/17992/17960。它们只有 3 个 chunk、
没有 RDEF，所以只能反汇编、拿不到变量名。

> 该开关随后与整个代理修复批次一起**回滚**了（见 RESULTS 2026-11-23 收敛条目）：
> 出问题的不是它，但"能在真实进程里改渲染"的改动在验证不充分时不应留在交付线上。
> 需要补全运行时目录时，把这段代码加回去跑一次即可，逻辑只有十几行。

**顺带查出的真问题**：部署在游戏目录里的 `GP_super_pbr.dxbc` 是 **16052 B**，
而 `dist\` 里的是 **16124 B**——也就是说现网跑的是更早一次编译的 PBR 载荷。
`verify_shaders.py` 会把这种漂移直接打出来（"payload drift"），重新安装前不要相信
任何一次 A/B。

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