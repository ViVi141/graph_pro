"""Disassemble arma3server Top hot functions (first ~40 insn + call summary)."""
from __future__ import annotations

import bisect
import struct
from capstone import CS_ARCH_X86, CS_MODE_64, Cs

EXE = r"<ARMA3>\arma3server_x64.exe"
TARGETS = [0x0140D288, 0x011DCE70, 0x01088D30, 0x00E32A82, 0x011C8D00]

data = open(EXE, "rb").read()
e = struct.unpack_from("<I", data, 0x3C)[0]
coff = e + 4
nsec = struct.unpack_from("<H", data, coff + 2)[0]
opt = coff + 20
ib = struct.unpack_from("<Q", data, opt + 24)[0]
sec_off = opt + struct.unpack_from("<H", data, coff + 16)[0]
secs = []
for i in range(nsec):
    o = sec_off + i * 40
    nm = data[o : o + 8].rstrip(b"\0").decode("latin-1", "ignore")
    vs, va, rs, ra = struct.unpack_from("<IIII", data, o + 8)
    secs.append((nm, va, vs, ra, rs))


def off(rva: int):
    for _n, va, vs, ra, _rs in secs:
        if va <= rva < va + vs:
            return ra + (rva - va)
    return None


pd = next(s for s in secs if s[0] == ".pdata")
funcs = []
for i in range(0, pd[4], 12):
    b, e2, _u = struct.unpack_from("<III", data, pd[3] + i)
    if b and e2 > b:
        funcs.append((b, e2))
funcs.sort()
starts = [f[0] for f in funcs]


def owner(rva: int):
    k = bisect.bisect_right(starts, rva) - 1
    if k < 0:
        return None
    b, e2 = funcs[k]
    return (b, e2) if b <= rva < e2 else None


md = Cs(CS_ARCH_X86, CS_MODE_64)
for rva in TARGETS:
    o = owner(rva)
    if not o:
        print("====", hex(rva), "NO OWNER")
        continue
    b, e2 = o
    size = e2 - b
    fo = off(b)
    print(f"==== {hex(rva)} owner={hex(b)} size={size}")
    body = data[fo : fo + size]
    for i, insn in enumerate(md.disasm(body, ib + b)):
        if i >= 36:
            print("  ...")
            break
        print(f"  {insn.address - ib:08X}: {insn.mnemonic:8s} {insn.op_str}")
    tgts: dict[int, int] = {}
    i = 0
    while i < len(body) - 5:
        if body[i] == 0xE8:
            rel = struct.unpack_from("<i", body, i + 1)[0]
            tgt = (b + i + 5 + rel) & 0xFFFFFFFF
            tgts[tgt] = tgts.get(tgt, 0) + 1
            i += 5
        else:
            i += 1
    top = sorted(tgts.items(), key=lambda x: -x[1])[:8]
    print(f"  E8 calls={sum(tgts.values())} unique={len(tgts)}")
    for t, c in top:
        ow = owner(t)
        print(f"    x{c} -> 0x{t:08X} (fn {hex(ow[0]) if ow else '?'} sz={ow[1]-ow[0] if ow else '?'})")
    print()
