"""Deepen 0x1155340: ParallelFor sync site + hot callee labels."""
from __future__ import annotations

import bisect
import collections
import os
import struct

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

EXE = r"<ARMA3>\Arma3_x64.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "extract", "cpu_samples", "simstep_deep.txt")
STEP, STEP_SZ = 0x1155340, 4604
HOT = [0x10FCE10, 0x1133850, 0x1108700, 0x115B980, 0x110BA80, 0x11258E0, 0xE777A0, 0xE77000]


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


def read_cstr(data, secs, rva):
    oo = rva_off(secs, rva)
    if oo is None:
        return None
    c = data[oo : oo + 96]
    z = c.find(b"\0")
    if z < 4:
        return None
    try:
        s = c[:z].decode("ascii")
    except Exception:
        return None
    return s if s.isprintable() else None


def main():
    data, ib, secs = load_pe(EXE)
    starts, ends = pdata(data, secs)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    lines = []

    oo = rva_off(secs, STEP)
    code = data[oo : oo + STEP_SZ]
    # ParallelFor neighborhood
    lines.append("## ParallelFor sync call site in simstep")
    for ins in md.disasm(code, ib + STEP):
        if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
            if int(ins.op_str, 16) - ib == 0x10FCE10:
                site = ins.address - ib
                start = max(STEP, site - 0x40)
                o2 = rva_off(secs, start)
                for ins2 in md.disasm(data[o2 : o2 + 0xA0], ib + start):
                    mark = " <<<" if ins2.address - ib == site else ""
                    lines.append(
                        f"  {ins2.address - ib:08X}: "
                        f"{ins2.mnemonic} {ins2.op_str}{mark}"
                    )
                    if ins2.address - ib > site + 0x28:
                        break

    lines.append("")
    lines.append("## Hot callee profiles")
    for rva in HOT:
        b, sz = owner(starts, ends, rva)
        if b is None:
            lines.append(f"### 0x{rva:X} (no pdata)")
            continue
        lines.append(f"### 0x{b:X} size={sz}")
        o2 = rva_off(secs, b)
        strs, seen = [], set()
        calls = collections.Counter()
        for ins in md.disasm(data[o2 : o2 + min(sz, 2500)], ib + b):
            if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
                calls[int(ins.op_str, 16) - ib] += 1
            for op in ins.operands:
                if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                    s = read_cstr(data, secs, (ins.address + ins.size + op.mem.disp) - ib)
                    if s and s not in seen:
                        seen.add(s)
                        strs.append(s)
        lines.append(f"  strings: {strs[:15]}")
        lines.append("  top callees:")
        for t, c in calls.most_common(8):
            tb, tsz = owner(starts, ends, t)
            # one-hop strings
            hs = []
            if tb is not None:
                o3 = rva_off(secs, tb)
                for ins in md.disasm(data[o3 : o3 + min(tsz, 800)], ib + tb):
                    for op in ins.operands:
                        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                            s = read_cstr(
                                data, secs,
                                (ins.address + ins.size + op.mem.disp) - ib,
                            )
                            if s and s not in hs:
                                hs.append(s)
            lines.append(
                f"    {c}x 0x{t:X} sz={tsz}  {hs[:3]}"
            )
        lines.append("")

    # count indirect in simstep phases relative to ParallelFor site
    lines.append("## indirect calls vs ParallelFor position")
    pf_site = None
    indir = []
    for ins in md.disasm(code, ib + STEP):
        site = ins.address - ib
        if ins.mnemonic == "call":
            if ins.op_str.startswith("0x") and int(ins.op_str, 16) - ib == 0x10FCE10:
                pf_site = site
            elif not ins.op_str.startswith("0x"):
                indir.append(site)
    lines.append(f"  ParallelFor @ {pf_site:#x}" if pf_site else "  ParallelFor not found")
    if pf_site:
        before = sum(1 for s in indir if s < pf_site)
        after = sum(1 for s in indir if s > pf_site)
        lines.append(f"  indirect before={before} after={after} total={len(indir)}")

    text = "\n".join(lines) + "\n"
    open(OUT, "w", encoding="utf-8").write(text)
    print(text)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
