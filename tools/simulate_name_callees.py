"""Name large World::Simulate callees via RTTI/vtable/strings/xrefs."""
from __future__ import annotations

import bisect
import os
import re
import struct
from collections import defaultdict

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

EXE = r"<ARMA3>\Arma3_x64.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "extract", "cpu_samples", "simulate_callee_names.txt")

TARGETS = [
    0x11456D0,  # ~5433
    0x1155340,  # ~4604
    0x11566C0,  # ~2104
    0x1260C00,  # ~2595
    0x1263C50,  # ~1255
    0x1A249F0,  # dispatcher
    0x110AD20,  # tiny clear
    0x3859C0,   # 10x helper
]


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


def demangle(name: str) -> str:
    parts = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,40}", name)
    skip = {
        "AU", "AV", "XI", "XZ", "QEAA", "QEBA", "AEAV", "PEAV", "AEAH",
        "InvokerLambda", "ParamsFunctor", "JobFuture", "enf", "AutoArray",
        "Span", "Link", "RStringCT", "basic_string", "char",
    }
    keep = [p for p in parts if p not in skip and not p.startswith("lambda")]
    return "::".join(keep[:6]) if keep else name[:80]


def main() -> int:
    data, ib, secs = load_pe(EXE)
    starts, ends = pdata(data, secs)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    # index all RTTI name RVAs
    rtti = []
    for m in re.finditer(rb"\.\?A[VU][A-Za-z0-9_@?$<>.-]{3,220}@@", data):
        r = fo_rva(secs, m.start())
        if r is not None:
            rtti.append((r, m.group(0).decode("latin-1", "ignore")))
    rtti.sort()
    rtti_rvas = [r for r, _ in rtti]
    rtti_map = dict(rtti)

    # Build: for each RTTI name RVA, find .rdata qwords that equal ib+name_rva
    # (TypeDescriptor pointer patterns vary; also scan for name_rva-16 as TD)
    text = [s for s in secs if s[0] == ".text"][0]
    rdata = [s for s in secs if s[0] == ".rdata"][0]
    _, tva, tvs, traw, _ = text
    _, rva0, rvs, rraw, rrs = rdata

    # Map function -> set of RTTI names referenced via rip-rel in first 2KB
    def refs_in_fn(fn: int, size: int):
        oo = rva_off(secs, fn)
        if oo is None:
            return [], []
        blob = data[oo : oo + min(size, 4096)]
        names, strs = [], []
        seen_n, seen_s = set(), set()
        for ins in md.disasm(blob, ib + fn):
            for op in ins.operands:
                if op.type != X86_OP_MEM or op.mem.base != X86_REG_RIP:
                    continue
                abs_a = ins.address + ins.size + op.mem.disp
                rr = abs_a - ib
                oo2 = rva_off(secs, rr)
                if oo2 is None:
                    continue
                chunk = data[oo2 : oo2 + 96]
                if chunk.startswith(b".?A"):
                    s = chunk.split(b"\0", 1)[0].decode("latin-1", "ignore")
                    if s not in seen_n:
                        seen_n.add(s)
                        names.append(s)
                    continue
                # try TypeDescriptor: name at +16
                if len(chunk) >= 24:
                    # sometimes pointer to name
                    pass
                try:
                    s = chunk.split(b"\0", 1)[0].decode("ascii")
                except Exception:
                    continue
                if 4 <= len(s) <= 80 and s.isprintable() and s not in seen_s:
                    # filter noise
                    if re.search(r"[A-Za-z]{3}", s):
                        seen_s.add(s)
                        strs.append(s)
        return names, strs

    # Who calls each target from whole .text? (expensive but capped)
    # Vectorised scan for E8 rel32 to target
    import numpy as np

    tbytes = data[traw : traw + tvs]
    callers = defaultdict(list)
    for tgt in TARGETS:
        # E8 rel32 where next = ib+site+5, rel = tgt_va - next
        # site_rva = tva + pos, next = ib + site_rva + 5, rel32 = (ib+tgt) - next
        # rel32 = tgt - site_rva - 5
        arr = np.frombuffer(tbytes, dtype=np.uint8)
        # find E8
        e8 = np.where(arr[:-4] == 0xE8)[0]
        for pos in e8:
            rel = struct.unpack_from("<i", tbytes, pos + 1)[0]
            site = tva + int(pos)
            dest = site + 5 + rel
            if dest == tgt:
                own, _ = owner(starts, ends, site)
                callers[tgt].append((site, own))
                if len(callers[tgt]) >= 30:
                    break

    lines = ["# Simulate large-callee naming", f"# ImageBase 0x{ib:X}", ""]

    for tgt in TARGETS:
        own, sz = owner(starts, ends, tgt)
        if own is None:
            own, sz = tgt, 64
        lines.append(f"## 0x{tgt:08X}  pdata_size={sz}  owner=0x{own:X}")
        names, strs = refs_in_fn(own, sz or 256)
        if names:
            lines.append("  RTTI refs:")
            for n in names[:15]:
                lines.append(f"    - {demangle(n)}")
                lines.append(f"      {n[:110]}")
        else:
            lines.append("  RTTI refs: (none in first 4KB rip-rel)")
        if strs:
            lines.append("  strings:")
            for s in strs[:20]:
                lines.append(f"    - {s!r}")
        else:
            lines.append("  strings: (none)")
        cs = callers.get(tgt, [])
        lines.append(f"  .text callers found: {len(cs)} (capped)")
        # summarize unique owning funcs
        owns = sorted({c[1] for c in cs if c[1]})
        for o in owns[:12]:
            _, osz = owner(starts, ends, o)
            n2, s2 = refs_in_fn(o, min(osz or 256, 1024))
            tag = demangle(n2[0]) if n2 else (s2[0] if s2 else "")
            lines.append(f"    from fn 0x{o:X} size={osz}  {tag}")
        lines.append("")

    # Extra: find methods whose RTTI name contains interesting keywords and
    # whose function body is one of our large callees (via xref to RTTI near fn)
    # Scan rdata for pointers to complete object locators — lighter approach:
    # search which RTTI strings appear within ±0x200 of any qword pointing at our fns
    lines.append("## Heuristic: RTTI names near absolute address of callee")
    for tgt in TARGETS[:5]:
        abs_bytes = struct.pack("<Q", ib + tgt)
        hits = []
        pos = 0
        while True:
            i = data.find(abs_bytes, pos)
            if i < 0:
                break
            rr = fo_rva(secs, i)
            hits.append(rr)
            pos = i + 1
            if len(hits) >= 20:
                break
        lines.append(f"  ptrs to 0x{tgt:X}: {len(hits)}  rvas={hits[:8]}")
        # look for RTTI strings in ±0x100 of each pointer site in rdata
        for hr in hits[:8]:
            if hr is None:
                continue
            oo = rva_off(secs, hr)
            if oo is None:
                continue
            window = data[max(0, oo - 0x80) : oo + 0x80]
            for m in re.finditer(rb"\.\?A[VU][A-Za-z0-9_@?$<>.-]{3,120}@@", window):
                lines.append(
                    f"    near-ptr RTTI: "
                    f"{m.group(0).decode('latin-1', 'ignore')[:100]}"
                )

    # Keyword inventory: World member-like names
    lines.append("")
    lines.append("## RTTI keywords near engine (sample)")
    keys = (
        b"Simulate", b"PerformAI", b"Landscape", b"Visib", b"Occlusion",
        b"Phys", b"Anim", b"Entity", b"Scene", b"Sound", b"Network",
        b"Clutter", b"Shadow", b"PrepareDraw", b"Flush", b"SUPER",
    )
    for k in keys:
        cnt = sum(1 for _r, n in rtti if k.decode() in n)
        lines.append(f"  {k.decode():15s}  {cnt}")

    text_out = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(text_out)
    print(text_out)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
