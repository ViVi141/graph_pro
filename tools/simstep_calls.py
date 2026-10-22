"""Dissect World per-frame sim step @ 0x1155340 (called from Simulate)."""
from __future__ import annotations

import bisect
import collections
import os
import re
import struct

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

EXE = r"D:\SteamLibrary\steamapps\common\Arma 3\Arma3_x64.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_TXT = os.path.join(ROOT, "extract", "cpu_samples", "simstep_0x1155340.txt")
OUT_MD_SECTION = os.path.join(ROOT, "extract", "cpu_samples", "simstep_summary.md")

STEP = 0x1155340


def load_pe(path):
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


def rva_off(secs, rva):
    for _n, va, vs, ra, _rs in secs:
        if va <= rva < va + vs:
            return ra + (rva - va)
    return None


def pdata(data, secs):
    pd = [s for s in secs if s[0] == ".pdata"][0]
    _n, _va, _vs, pra, prs = pd
    starts, ends = [], {}
    for i in range(0, prs, 12):
        b, e2, _u = struct.unpack_from("<III", data, pra + i)
        if b and e2 > b:
            starts.append(b)
            ends[b] = e2
    starts.sort()
    return starts, ends


def owner(starts, ends, rva):
    i = bisect.bisect_right(starts, rva) - 1
    if i < 0:
        return None, None
    b = starts[i]
    if b <= rva < ends[b]:
        return b, ends[b] - b
    return None, None


def read_cstr(data, secs, rva, maxlen=100):
    oo = rva_off(secs, rva)
    if oo is None:
        return None
    chunk = data[oo : oo + maxlen]
    end = chunk.find(b"\0")
    if end < 4:
        return None
    try:
        s = chunk[:end].decode("ascii")
    except Exception:
        return None
    return s if s.isprintable() else None


def rip_strings(md, data, secs, ib, fn, size):
    oo = rva_off(secs, fn)
    if oo is None:
        return []
    out, seen = [], set()
    for ins in md.disasm(data[oo : oo + size], ib + fn):
        for op in ins.operands:
            if op.type != X86_OP_MEM or op.mem.base != X86_REG_RIP:
                continue
            rr = (ins.address + ins.size + op.mem.disp) - ib
            s = read_cstr(data, secs, rr)
            if s and s not in seen:
                seen.add(s)
                out.append(s)
            chunk_off = rva_off(secs, rr)
            if chunk_off is not None:
                chunk = data[chunk_off : chunk_off + 8]
                if chunk.startswith(b".?A"):
                    raw = data[chunk_off : chunk_off + 120].split(b"\0", 1)[0]
                    try:
                        name = raw.decode("latin-1")
                    except Exception:
                        continue
                    if name not in seen:
                        seen.add(name)
                        out.append("RTTI:" + name[:100])
    return out


def demangle_hint(s: str) -> str:
    if s.startswith("RTTI:"):
        s = s[5:]
    parts = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,40}", s)
    skip = {
        "AU", "AV", "XI", "XZ", "QEAA", "QEBA", "AEAV", "PEAV", "InvokerLambda",
        "ParamsFunctor", "JobFuture", "enf", "AutoArray", "RStringCT",
    }
    keep = [p for p in parts if p not in skip and not p.startswith("lambda")]
    return "::".join(keep[:5]) if keep else s[:60]


def classify(strs: list[str], size: int, rva: int) -> str:
    blob = " ".join(strs).lower()
    rules = [
        (("vehicle", "veh", "mtvehs", "car", "tank", "heli", "plane"), "vehicle"),
        (("phys", "physx", "rigid", "collision", "contact"), "physics"),
        (("ai", "path", "brain", "fsm", "combat"), "ai"),
        (("anim", "bone", "skeleton", "ragdoll"), "anim"),
        (("entity", "object", "person", "unit"), "entity"),
        (("network", "remote", "jip", "mp"), "network"),
        (("sound", "audio", "voice"), "sound"),
        (("weapon", "ammo", "magazine", "muzzle", "fire"), "weapon"),
        (("visib", "occlus", "lod", "render", "draw"), "visibility/render"),
        (("weather", "fog", "wind", "rain", "cloud"), "weather"),
        (("simul", "twice", "frame"), "sim-guard"),
    ]
    for keys, label in rules:
        if any(k in blob for k in keys):
            return label
    if size >= 2000:
        return "large-unknown"
    if size <= 64:
        return "tiny"
    return "unlabeled"


def main() -> int:
    data, ib, secs = load_pe(EXE)
    starts, ends = pdata(data, secs)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    own, size = owner(starts, ends, STEP)
    assert own == STEP, (own, STEP)
    oo = rva_off(secs, STEP)
    code = data[oo : oo + size]
    insns = list(md.disasm(code, ib + STEP))

    calls = []
    call_cnt = collections.Counter()
    indir = 0
    for ins in insns:
        if ins.mnemonic != "call":
            continue
        site = ins.address - ib
        if ins.op_str.startswith("0x"):
            tgt = int(ins.op_str, 16) - ib
            calls.append((site, tgt))
            call_cnt[tgt] += 1
        else:
            indir += 1

    # phase by offset in step
    nph = 6
    pw = size / nph
    phases = [collections.Counter() for _ in range(nph)]
    for site, tgt in calls:
        pi = min(nph - 1, int((site - STEP) / pw))
        phases[pi][tgt] += 1

    # label each distinct callee
    rows = []
    for tgt, cnt in call_cnt.most_common():
        b, sz = owner(starts, ends, tgt)
        if b is None:
            b, sz = tgt, -1
        strs = rip_strings(md, data, secs, ib, b, min(sz if sz > 0 else 256, 2500))
        hints = [demangle_hint(s) for s in strs[:8]]
        kind = classify(strs, sz if sz > 0 else 0, tgt)
        rows.append((cnt, tgt, sz, kind, hints, strs[:6]))

    lines = [
        f"# sim step 0x{STEP:X} size={size}",
        f"# insns={len(insns)} direct_calls={len(calls)} distinct={len(call_cnt)} "
        f"indirect={indir}",
        "",
        "## own strings",
    ]
    for s in rip_strings(md, data, secs, ib, STEP, size):
        lines.append(f"  - {s}")

    lines.append("")
    lines.append("## callees by count")
    for cnt, tgt, sz, kind, hints, strs in rows:
        h = ", ".join(hints[:3]) if hints else ""
        lines.append(f"  {cnt:2d}x  0x{tgt:08X}  sz={sz:5d}  [{kind}]  {h}")
        for s in strs[:3]:
            if not s.startswith("RTTI:"):
                lines.append(f"       str {s!r}")

    lines.append("")
    lines.append("## callees by size (among called)")
    by_sz = sorted(rows, key=lambda r: r[2] if r[2] > 0 else 0, reverse=True)
    for cnt, tgt, sz, kind, hints, strs in by_sz[:20]:
        h = ", ".join(hints[:3]) if hints else ""
        lines.append(f"  {cnt:2d}x  0x{tgt:08X}  sz={sz:5d}  [{kind}]  {h}")

    lines.append("")
    lines.append("## phase map")
    for pi in range(nph):
        a = int(STEP + pi * pw)
        b = int(STEP + (pi + 1) * pw)
        lines.append(f"  phase{pi} 0x{a:X}-0x{b:X} calls={sum(phases[pi].values())}")
        for tgt, cnt in phases[pi].most_common(5):
            kind = next((k for c, t, s, k, h, st in rows if t == tgt), "?")
            lines.append(f"      {cnt}x 0x{tgt:08X} [{kind}]")

    # kind histogram
    kind_hits = collections.Counter()
    kind_bytes = collections.Counter()
    for cnt, tgt, sz, kind, hints, strs in rows:
        kind_hits[kind] += cnt
        if sz > 0:
            kind_bytes[kind] += sz * cnt  # crude weight
    lines.append("")
    lines.append("## kind histogram (by call count)")
    for k, v in kind_hits.most_common():
        lines.append(f"  {k:20s}  calls={v}")

    text = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    open(OUT_TXT, "w", encoding="utf-8").write(text)
    print(text)

    # markdown summary snippet
    md_lines = [
        f"### `0x{STEP:X}` 内部调用图（P0′）",
        "",
        f"- 大小 **{size} B**，直接 call **{len(calls)}** → **{len(call_cnt)}** 目标，间接 **{indir}**",
        f"- 自带关键串：`mtVehS`、`simulation started twice in a frame?`",
        "",
        "#### 按调用次数 Top",
        "",
        "| 次 | RVA | size | 分类 | 线索 |",
        "|---|---|---|---|---|",
    ]
    for cnt, tgt, sz, kind, hints, strs in rows[:18]:
        clue = hints[0] if hints else (strs[0][:40] if strs else "")
        md_lines.append(
            f"| {cnt} | `0x{tgt:08X}` | {sz} | {kind} | {clue} |"
        )
    md_lines += [
        "",
        "#### 分类汇总",
        "",
        "| 类 | call 次数 |",
        "|---|---|",
    ]
    for k, v in kind_hits.most_common():
        md_lines.append(f"| {k} | {v} |")
    md_lines += [
        "",
        "全文：`extract/cpu_samples/simstep_0x1155340.txt`",
        "",
    ]
    open(OUT_MD_SECTION, "w", encoding="utf-8").write("\n".join(md_lines))
    print("wrote", OUT_TXT)
    print("wrote", OUT_MD_SECTION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
