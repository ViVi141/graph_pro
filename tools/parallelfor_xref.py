"""Find ParallelFor submit/enqueue relative to sync @ 0x10FCE10 / simstep."""
from __future__ import annotations

import bisect
import collections
import os
import re
import struct

import numpy as np
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

EXE = r"<ARMA3>\Arma3_x64.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "extract", "cpu_samples", "parallelfor_xref.txt")

SYNC = 0x10FCE10
STEP = 0x1155340
STEP_SZ = 4604
SIM = 0x11527E0


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


def fo_rva(secs, fo):
    for _n, va, _vs, ra, rs in secs:
        if ra <= fo < ra + rs:
            return va + (fo - ra)
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
    c = data[oo : oo + 80]
    z = c.find(b"\0")
    if z < 3:
        return None
    try:
        s = c[:z].decode("ascii")
    except Exception:
        return None
    return s if s.isprintable() else None


def find_calls_to(tbytes, tva, target, limit=40):
    hits = []
    arr = np.frombuffer(tbytes, dtype=np.uint8)
    for pos in np.where(arr == 0xE8)[0]:
        pos = int(pos)
        rel = struct.unpack_from("<i", tbytes, pos + 1)[0]
        site = tva + pos
        if site + 5 + rel == target:
            hits.append(site)
            if len(hits) >= limit:
                break
    return hits


def main():
    data, ib, secs = load_pe(EXE)
    starts, ends = pdata(data, secs)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    text = [s for s in secs if s[0] == ".text"][0]
    _n, tva, tvs, traw, _ = text
    tbytes = data[traw : traw + tvs]
    lines = ["# ParallelFor xref", ""]

    # All Parallel* / pFor / subSync strings
    lines.append("## strings")
    for nd in (
        b"ParallelFor sync",
        b"ParallelFor Subdivide",
        b"ParallelFor",
        b"pFor",
        b"subSync",
        b"ParallelForEach",
    ):
        pos = 0
        found = []
        while True:
            i = data.find(nd, pos)
            if i < 0:
                break
            r = fo_rva(secs, i)
            found.append(r)
            pos = i + 1
            if len(found) >= 8:
                break
        lines.append(f"  {nd!r} -> {[hex(x) for x in found if x]}")

    # Who calls SYNC
    sync_callers = find_calls_to(tbytes, tva, SYNC, 50)
    lines.append("")
    lines.append(f"## callers of sync 0x{SYNC:X}: {len(sync_callers)}")
    own_counts = collections.Counter()
    for site in sync_callers:
        o, sz = owner(starts, ends, site)
        own_counts[o] += 1
        in_step = STEP <= site < STEP + STEP_SZ
        in_sim = SIM <= site < SIM + 11093
        lines.append(
            f"  @{site:X} own=0x{(o or 0):X} sz={sz} "
            f"in_simstep={in_step} in_Simulate={in_sim}"
        )
    lines.append("  unique owners:")
    for o, c in own_counts.most_common(15):
        if o is None:
            continue
        _, sz = owner(starts, ends, o)
        # strings in owner
        oo = rva_off(secs, o)
        strs = []
        if oo is not None:
            seen = set()
            for ins in md.disasm(data[oo : oo + min(sz or 256, 1200)], ib + o):
                for op in ins.operands:
                    if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                        s = read_cstr(
                            data, secs,
                            (ins.address + ins.size + op.mem.disp) - ib,
                        )
                        if s and s not in seen:
                            seen.add(s)
                            strs.append(s)
        lines.append(f"    {c}x from 0x{o:X} sz={sz} strs={strs[:5]}")

    # Code BEFORE sync inside simstep — all calls
    lines.append("")
    lines.append("## simstep calls BEFORE ParallelFor sync")
    oo = rva_off(secs, STEP)
    code = data[oo : oo + STEP_SZ]
    sync_site = None
    pre_calls = []
    for ins in md.disasm(code, ib + STEP):
        site = ins.address - ib
        if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
            tgt = int(ins.op_str, 16) - ib
            if tgt == SYNC:
                sync_site = site
                break
            pre_calls.append((site, tgt))
        elif ins.mnemonic == "call":
            if sync_site is None:
                pre_calls.append((site, None))  # indirect
    lines.append(f"  sync_site={sync_site:#x}" if sync_site else "  sync not found")
    for site, tgt in pre_calls:
        if tgt is None:
            lines.append(f"  @{site:X} indirect")
            continue
        o, sz = owner(starts, ends, tgt)
        strs = []
        if o is not None:
            o2 = rva_off(secs, o)
            seen = set()
            for ins in md.disasm(data[o2 : o2 + min(sz or 64, 800)], ib + o):
                for op in ins.operands:
                    if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                        s = read_cstr(
                            data, secs,
                            (ins.address + ins.size + op.mem.disp) - ib,
                        )
                        if s and s not in seen:
                            seen.add(s)
                            strs.append(s)
        lines.append(
            f"  @{site:X} -> 0x{tgt:X} sz={sz} strs={strs[:4]}"
        )

    # Find functions that reference "ParallelFor Subdivide" or "pFor" — likely submit path
    lines.append("")
    lines.append("## functions referencing ParallelFor-related strings")
    for nd in (b"ParallelFor Subdivide", b"ParallelFor sync", b"pFor"):
        i = data.find(nd)
        if i < 0:
            continue
        sr = fo_rva(secs, i)
        lines.append(f"  string {nd!r} @ {sr:#x}")
        # find lea to this string via 0x8D filter
        arr = np.frombuffer(tbytes, dtype=np.uint8)
        hits = []
        for idx in np.where(arr == 0x8D)[0]:
            idx = int(idx)
            for start, ilen in ((idx, 6), (idx - 1, 7) if idx >= 1 else (idx, 6)):
                if start < 0 or start + ilen > len(tbytes):
                    continue
                if idx >= 1 and start == idx - 1 and tbytes[start] not in (
                    0x48, 0x4C, 0x49, 0x4D, 0x41, 0x44, 0x45, 0x47,
                ):
                    continue
                d = struct.unpack_from("<i", tbytes, start + ilen - 4)[0]
                if tva + start + ilen + d == sr:
                    hits.append(tva + start)
        for site in hits[:12]:
            o, sz = owner(starts, ends, site)
            lines.append(f"    xref @{site:X} own=0x{(o or 0):X} sz={sz}")

    # Disasm SYNC function outline — look for wait loops / job pop
    lines.append("")
    lines.append("## sync fn 0x10FCE10 outline (first 40 ins + string sites)")
    o2 = rva_off(secs, SYNC)
    _b, ssz = owner(starts, ends, SYNC)
    for i, ins in enumerate(md.disasm(data[o2 : o2 + min(ssz, 400)], ib + SYNC)):
        extra = ""
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                s = read_cstr(
                    data, secs, (ins.address + ins.size + op.mem.disp) - ib
                )
                if s:
                    extra = f"  ; {s!r}"
        lines.append(
            f"  {ins.address - ib:08X}: {ins.mnemonic} {ins.op_str}{extra}"
        )
        if i >= 45:
            break

    text_out = "\n".join(lines) + "\n"
    open(OUT, "w", encoding="utf-8").write(text_out)
    print(text_out)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
