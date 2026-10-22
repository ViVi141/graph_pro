"""Deep static RE of World::Simulate @ 0x11527E0 (Arma3_x64 2.22)."""
from __future__ import annotations

import collections
import os
import re
import struct
import bisect

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

EXE = r"D:\SteamLibrary\steamapps\common\Arma 3\Arma3_x64.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "extract", "cpu_samples")
OUT_MD = os.path.join(ROOT, "docs", "14-world-simulate.md")
OUT_TXT = os.path.join(OUT_DIR, "simulate_deep.txt")

START, SIZE = 0x11527E0, 11093


def load_pe(path: str):
    data = open(path, "rb").read()
    e = struct.unpack_from("<I", data, 0x3C)[0]
    coff = e + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    opt = coff + 20
    ib = struct.unpack_from("<Q", data, opt + 24)[0]
    sec_off = opt + struct.unpack_from("<H", data, coff + 16)[0]
    secs = []
    for i in range(nsec):
        o = sec_off + i * 40
        nm = data[o : o + 8].split(b"\0", 1)[0].decode("latin-1", "ignore")
        vs, va, rs, ra = struct.unpack_from("<IIII", data, o + 8)
        secs.append((nm, va, vs, ra, rs))
    return data, ib, secs


def rva_to_off(secs, rva: int):
    for _nm, va, vs, ra, _rs in secs:
        if va <= rva < va + vs:
            return ra + (rva - va)
    return None


def fo_to_rva(secs, fo: int):
    for _nm, va, _vs, ra, rs in secs:
        if ra <= fo < ra + rs:
            return va + (fo - ra)
    return None


def load_pdata(data, secs):
    pd = [s for s in secs if s[0] == ".pdata"][0]
    _nm, _va, _vs, pra, prs = pd
    starts, ends = [], {}
    for i in range(0, prs, 12):
        b, e2, _u = struct.unpack_from("<III", data, pra + i)
        if b and e2 > b:
            starts.append(b)
            ends[b] = e2
    starts.sort()
    return starts, ends


def owner_fn(starts, ends, rva: int):
    i = bisect.bisect_right(starts, rva) - 1
    if i < 0:
        return None, None
    b = starts[i]
    if b <= rva < ends[b]:
        return b, ends[b] - b
    return None, None


def demangle_hint(name: str) -> str:
    """Pull readable tokens from MSVC RTTI / lambda type names."""
    # Keep key identifiers
    parts = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,40}", name)
    skip = {
        "AU", "AV", "XI", "XZ", "QEAA", "QEBA", "AEAV", "PEAV", "AEAH",
        "InvokerLambda", "ParamsFunctor", "lambda", "JobFuture", "enf",
        "AutoArray", "Span", "Link", "RStringCT",
    }
    keep = [p for p in parts if p not in skip and not p.startswith("lambda")]
    # Prefer Class::Method style if Simulate@World present
    if "Simulate" in name and "World" in name:
        if "SoundMainTask" in name:
            return "SoundMainTask (from Simulate)"
        if "InvokerLambda" in name:
            # try extract nested context
            if "Entity" in name:
                return "job: Simulate/Entity lambda"
            return "job: Simulate InvokerLambda"
    if "PrepareDraw" in name:
        return "PrepareDraw* job"
    if len(keep) >= 2:
        return "::".join(keep[:4])
    return keep[0] if keep else name[:60]


def main() -> int:
    data, ib, secs = load_pe(EXE)
    starts, ends = load_pdata(data, secs)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    o0 = rva_to_off(secs, START)
    code = data[o0 : o0 + SIZE]
    insns = list(md.disasm(code, ib + START))

    # --- RTTI names mentioning Simulate@World ---
    sim_names = []
    for m in re.finditer(rb"\.\?A[VU][\w@?$<>.-]{3,240}Simulate@World@@[\w@?$<>.-]*", data):
        fo = m.start()
        r = fo_to_rva(secs, fo)
        raw = m.group(0).decode("latin-1", "ignore")
        if r is not None:
            sim_names.append((r, raw, demangle_hint(raw)))

    # All RTTI for labeling callees via rip-relative lea in callee bodies
    all_rtti = []
    for m in re.finditer(rb"\.\?A[VU][A-Za-z0-9_@?$<>.-]{3,200}@@", data):
        r = fo_to_rva(secs, m.start())
        if r is not None:
            all_rtti.append((r, m.group(0).decode("latin-1", "ignore")))
    all_rtti.sort()
    rtti_rvas = [r for r, _ in all_rtti]
    rtti_map = {r: n for r, n in all_rtti}

    def nearest_rtti_in_fn(fn_start: int, fn_size: int) -> str | None:
        """Scan callee for lea rip → absolute pointing near an RTTI name string."""
        oo = rva_to_off(secs, fn_start)
        if oo is None:
            return None
        blob = data[oo : oo + min(fn_size, 512)]
        hits = []
        for ins in md.disasm(blob, ib + fn_start):
            if ins.mnemonic not in ("lea", "mov"):
                continue
            for op in ins.operands:
                if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                    abs_addr = ins.address + ins.size + op.mem.disp
                    rva = abs_addr - ib
                    # TypeDescriptor often 16 bytes before name
                    for cand in (rva, rva + 16, rva - 16, rva + 8):
                        if cand in rtti_map:
                            hits.append(rtti_map[cand])
                    # or exact string
                    i = bisect.bisect_left(rtti_rvas, rva)
                    for j in (i - 1, i, i + 1):
                        if 0 <= j < len(rtti_rvas) and abs(rtti_rvas[j] - rva) < 0x40:
                            hits.append(rtti_map[rtti_rvas[j]])
        if not hits:
            return None
        # prefer Simulate-related
        for h in hits:
            if "Simulate" in h or "World" in h:
                return demangle_hint(h)
        return demangle_hint(hits[0])

    # --- walk Simulate: calls + control ---
    calls = []  # (site_rva, target_rva, count later)
    call_counter = collections.Counter()
    indirect = 0
    loops_like = 0
    for ins in insns:
        site = ins.address - ib
        if ins.mnemonic == "call":
            if ins.op_str.startswith("0x"):
                tgt = int(ins.op_str, 16) - ib
                calls.append((site, tgt))
                call_counter[tgt] += 1
            else:
                indirect += 1
        if ins.mnemonic.startswith("j") and ins.op_str.startswith("0x"):
            dest = int(ins.op_str, 16) - ib
            if dest < site and START <= dest < START + SIZE:
                loops_like += 1

    # Phase buckets by offset in function (8 equal parts)
    n_phases = 8
    phase_w = SIZE / n_phases
    phase_calls = [collections.Counter() for _ in range(n_phases)]
    for site, tgt in calls:
        off_in = site - START
        pi = min(n_phases - 1, int(off_in / phase_w))
        phase_calls[pi][tgt] += 1

    known = {
        0x1A249F0: "16-way jump dispatcher (job/type switch)",
        0x110AD20: "tiny counter/clear ([rcx+8])",
        0x1260C00: "large subsystem @ World+0xac8 path",
        0x3859C0: "helper (called 10x)",
        0x1127F80: "helper (6x)",
        0x145D80: "helper (6x)",
        0x13DB60: "helper (6x)",
    }

    def label_callee(rva: int) -> str:
        if rva in known:
            return known[rva]
        b, sz = owner_fn(starts, ends, rva)
        if b is None:
            return "outside_pdata?"
        hint = nearest_rtti_in_fn(b, sz or 64)
        if hint:
            return hint
        sz = ends[b] - b
        if sz <= 32:
            return f"tiny leaf size={sz}"
        if sz >= 2000:
            return f"large fn size={sz}"
        return f"fn size={sz}"

    # Analyze notable callees briefly
    def peek(rva: int, n: int = 8) -> list[str]:
        b, sz = owner_fn(starts, ends, rva)
        if b is None:
            b, sz = rva, 64
        oo = rva_to_off(secs, b)
        if oo is None:
            return []
        out = []
        for i, ins in enumerate(md.disasm(data[oo : oo + 96], ib + b)):
            out.append(f"  {ins.address - ib:08X}: {ins.mnemonic} {ins.op_str}")
            if i + 1 >= n:
                break
        return out

    # Prologue / stack
    prologue = []
    for ins in insns[:25]:
        prologue.append(f"  {ins.address - ib:08X}: {ins.mnemonic} {ins.op_str}")

    # String literals referenced from Simulate (rip-rel)
    str_hits = []
    for ins in insns:
        if not ins.operands:
            continue
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                abs_a = ins.address + ins.size + op.mem.disp
                rva = abs_a - ib
                oo = rva_to_off(secs, rva)
                if oo is None:
                    continue
                chunk = data[oo : oo + 64]
                if b"\0" in chunk[:48]:
                    try:
                        s = chunk.split(b"\0", 1)[0].decode("ascii")
                    except Exception:
                        continue
                    if len(s) >= 4 and s.isprintable():
                        str_hits.append((ins.address - ib, s))

    # Build report
    lines = []
    lines.append(f"World::Simulate deep RE")
    lines.append(f"RVA 0x{START:X} size {SIZE}  ImageBase 0x{ib:X}")
    lines.append(f"instructions={len(insns)} direct_calls={len(calls)} "
                 f"distinct={len(call_counter)} indirect_calls={indirect} "
                 f"backward_jumps~{loops_like}")
    lines.append("")
    lines.append("== RTTI tied to Simulate@World ==")
    for r, raw, hint in sorted(sim_names, key=lambda x: x[0]):
        lines.append(f"  0x{r:X}  {hint}")
        lines.append(f"           {raw[:120]}")
    lines.append("")
    lines.append("== Prologue ==")
    lines.extend(prologue)
    lines.append("")
    lines.append("== Top callees by call count ==")
    for rva, cnt in call_counter.most_common(25):
        b, sz = owner_fn(starts, ends, rva)
        sz = (ends[b] - b) if b is not None else -1
        lines.append(f"  {cnt:2d}x  0x{rva:08X}  size={sz:5d}  {label_callee(rva)}")
    lines.append("")
    lines.append("== Top callees by size (among those called) ==")
    by_size = sorted(call_counter.keys(),
                     key=lambda r: (ends.get(owner_fn(starts, ends, r)[0] or 0, 0) -
                                    (owner_fn(starts, ends, r)[0] or 0)),
                     reverse=True)
    for rva in by_size[:20]:
        b, _ = owner_fn(starts, ends, rva)
        sz = ends[b] - b if b is not None else -1
        lines.append(f"  {call_counter[rva]:2d}x  0x{rva:08X}  size={sz:5d}  {label_callee(rva)}")
    lines.append("")
    lines.append("== Phase map (8 slices of function body) ==")
    for pi in range(n_phases):
        a = int(START + pi * phase_w)
        b = int(START + (pi + 1) * phase_w)
        top = phase_calls[pi].most_common(5)
        lines.append(f"  phase{pi}  0x{a:X}-0x{b:X}  calls={sum(phase_calls[pi].values())}")
        for rva, cnt in top:
            lines.append(f"      {cnt}x 0x{rva:08X}  {label_callee(rva)}")
    lines.append("")
    lines.append("== String-ish rip refs from Simulate ==")
    seen = set()
    for site, s in str_hits:
        if s in seen:
            continue
        seen.add(s)
        lines.append(f"  @0x{site:X}  \"{s[:80]}\"")
        if len(seen) >= 40:
            break
    lines.append("")
    lines.append("== Peek: 16-way dispatcher ==")
    lines.extend(peek(0x1A249F0, 12))
    lines.append("== Peek: 0x1260C00 large subsystem ==")
    lines.extend(peek(0x1260C00, 14))
    lines.append("== Peek: 0x110AD20 tiny clear ==")
    lines.extend(peek(0x110AD20, 6))
    lines.append("== Peek: 0x3859C0 (10x) ==")
    lines.extend(peek(0x3859C0, 10))

    text = "\n".join(lines) + "\n"
    os.makedirs(OUT_DIR, exist_ok=True)
    open(OUT_TXT, "w", encoding="utf-8").write(text)
    print(text)

    # Markdown summary for docs/14
    md_lines = [
        "# 14 · World::Simulate 在做什么（静态逆向）",
        "",
        "日期：2026-10-22 · 目标：`Arma3_x64.exe` 2.22 · RVA **`0x11527E0`** · 大小 **11093 B**",
        "",
        "原始反汇编摘要：`extract/cpu_samples/simulate_deep.txt`",
        "",
        "## 1. 函数角色（结论先行）",
        "",
        "`World::Simulate(float dt, bool&, bool&)` 是**主线程帧模拟编排器**，不是重计算核：",
        "",
        f"- 约 **{len(insns)}** 条指令，**{len(calls)}** 次直接 `call` → **{len(call_counter)}** 个不同目标",
        f"- 另有 **{indirect}** 次间接调用；函数体内向后跳转约 **{loops_like}**（局部循环/重试）",
        "- 栈帧很大（`sub rsp, 0x6d8` 量级）：本地状态机 + 多个作业/future 句柄",
        "- RTTI 显示其内部嵌套了 **InvokerLambda 作业**（含 Entity 遍历 lambda、SoundMainTask）",
        "",
        "与 C1/C1b 一致：**主线程把门闩串起来**；工人线程跑被投递的作业，采样里大量 `ntdll` 等待。",
        "",
        "## 2. 与 Simulate 绑定的 RTTI（引擎自己贴的标签）",
        "",
        "| 含义 | 说明 |",
        "|---|---|",
    ]
    for r, raw, hint in sorted(sim_names, key=lambda x: x[0])[:12]:
        md_lines.append(f"| `{hint}` | `{raw[:90]}…` |" if len(raw) > 90
                        else f"| `{hint}` | `{raw}` |")
    md_lines += [
        "",
        "解读：Simulate **主动投递并行作业**（lambda / Sound 任务），自己留下编排与汇合。",
        "",
        "## 3. 调用画像",
        "",
        "### 按调用次数（编排痕迹）",
        "",
        "| 次数 | RVA | 标签 |",
        "|---|---|---|",
    ]
    for rva, cnt in call_counter.most_common(15):
        md_lines.append(f"| {cnt} | `0x{rva:08X}` | {label_callee(rva)} |")
    md_lines += [
        "",
        "### 大块被调（更可能是真子系统）",
        "",
        "| 次数 | RVA | size | 标签 |",
        "|---|---|---|---|",
    ]
    for rva in by_size[:12]:
        b, _ = owner_fn(starts, ends, rva)
        sz = ends[b] - b if b is not None else -1
        if sz < 200:
            continue
        md_lines.append(
            f"| {call_counter[rva]} | `0x{rva:08X}` | {sz} | {label_callee(rva)} |"
        )
    md_lines += [
        "",
        "## 4. 阶段草图（按函数体偏移均分 8 段）",
        "",
        "静态分段，不是运行时 timer；用于看「前/中/后段在调谁」。",
        "",
    ]
    for pi in range(n_phases):
        a = int(START + pi * phase_w)
        b = int(START + (pi + 1) * phase_w)
        top = phase_calls[pi].most_common(3)
        tops = ", ".join(f"`0x{r:X}`×{c}" for r, c in top) if top else "(no direct call)"
        md_lines.append(f"- **phase{pi}** `0x{a:X}`–`0x{b:X}` "
                        f"（{sum(phase_calls[pi].values())} calls）：{tops}")

    md_lines += [
        "",
        "## 5. 关键被调者在干什么",
        "",
        "### `0x1A249F0` — 16 路跳转分发（调用 4 次）",
        "",
        "```",
        "cmp r8, 0xF",
        "ja  default",
        "mov r9d, [table + r8*4]",
        "jmp r9",
        "```",
        "",
        "是**类型/消息/作业码分发器**，不是数值内核。Simulate 多次进入不同 case。",
        "",
        "### `0x110AD20` — 10B，调用 17 次",
        "",
        "访问并清理 `[rcx+8]` 一类计数/链表头，典型 **容器复位 / 遍历哨兵**。"
        "出现次数多说明 Simulate 在多个阶段反复「清空本帧结构」。",
        "",
        "### `0x1260C00` — ~2.5KB，调用 4 次",
        "",
        "大栈帧子系统，访问 `this+0xAC8` 一带对象；更像 **挂在 World 上的真实模拟子模块**"
        "（需再跟虚表/成员才能定名）。是少数「值得继续挖」的块，但仍是子系统级，不是叶子。",
        "",
        "## 6. 对「CPU 吃不饱 / 帧被拖住」的含义",
        "",
        "1. **Simulate 本身几乎不做重 SIMD 计算**；时间花在「按顺序调用 100+ 个子系统 + 投递/汇合作业」。",
        "2. 并行度来自内部 **InvokerLambda**，但 **帧结束仍要回到主线程汇合** → 工人在 `ntdll` 等待，主线程仍是门闩。",
        "3. 因此：替换 Simulate **不可行**；加速单个叶子对 YAAB **ROI 极低**；"
        "有效手段是 **减少它必须编排的对象/AI/物理/可见集规模**（软参数），"
        "或减少其后的渲染提交（iGPU UMD）。",
        "",
        "## 7. 建议的下一步逆向（若继续）",
        "",
        "| 优先级 | 目标 | 目的 |",
        "|---|---|---|",
        "| P0 | 给 `0x1260C00` 定名（RTTI/虚表/字符串） | 确认最大子模块身份 |",
        "| P1 | 标出 Simulate 内 Job 投递与 `JobFuture` 等待点 | 画「主线程等待边」 |",
        "| P2 | 动态：仅主线程采样 / ETW | 验证静态阶段与真实耗时 |",
        "",
        "---",
        "",
        f"生成脚本：`tools/simulate_deep.py` · 全文：`extract/cpu_samples/simulate_deep.txt`",
        "",
    ]
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(md_lines))
    print("wrote", OUT_MD)
    print("wrote", OUT_TXT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
