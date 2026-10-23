"""Locate World::Simulate / ParallelFor sync bodies on arma3server_x64."""
from __future__ import annotations

import bisect
import re
import struct

EXE = r"D:\SteamLibrary\steamapps\common\Arma 3\arma3server_x64.exe"
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


def off_of(rva: int):
    for _n, va, vs, ra, _rs in secs:
        if va <= rva < va + vs:
            return ra + (rva - va)
    return None


pd = [s for s in secs if s[0] == ".pdata"][0]
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


# Find "Simulate@World@@QEAAXMAEA_N0@Z" in RTTI / mangled — walk back to CO / vtable is hard;
# instead find large functions that LEA the simstep_guard string.
needle = b"simulation started twice"
idx = data.find(needle)
print("simstep_guard file_off", hex(idx) if idx >= 0 else None)
# rva of string
str_rva = None
for _n, va, vs, ra, rs in secs:
    if ra <= idx < ra + rs:
        str_rva = va + (idx - ra)
        break
print("str_rva", hex(str_rva) if str_rva else None)

T = [s for s in secs if s[0] == ".text"][0]
trva, traw, trsz = T[1], T[3], T[4]
text = data[traw : traw + trsz]
owners = set()
for i in range(len(text) - 7):
    if text[i] != 0x48 or text[i + 1] not in (0x8D, 0x8B):
        continue
    if (text[i + 2] & 0xC7) != 0x05:
        continue
    disp = struct.unpack_from("<i", text, i + 3)[0]
    insn = trva + i
    tgt = (insn + 7 + disp) & 0xFFFFFFFF
    if tgt == str_rva:
        own = owner(insn)
        if own:
            owners.add(own)

print("functions referencing simstep_guard:")
for b, e2 in sorted(owners):
    print(f"  0x{b:08X}..{e2:08X} size={e2-b}")

# ParallelFor sync string
needle2 = b"ParallelFor sync"
idx2 = data.find(needle2)
str2 = None
for _n, va, vs, ra, rs in secs:
    if ra <= idx2 < ra + rs:
        str2 = va + (idx2 - ra)
        break
owners2 = set()
for i in range(len(text) - 7):
    if text[i] != 0x48 or text[i + 1] not in (0x8D, 0x8B):
        continue
    if (text[i + 2] & 0xC7) != 0x05:
        continue
    disp = struct.unpack_from("<i", text, i + 3)[0]
    insn = trva + i
    tgt = (insn + 7 + disp) & 0xFFFFFFFF
    if tgt == str2:
        own = owner(insn)
        if own:
            owners2.add(own)
print("functions referencing ParallelFor sync:")
for b, e2 in sorted(owners2):
    print(f"  0x{b:08X}..{e2:08X} size={e2-b}")

# Heuristic: World::Simulate on client was ~11093 B. Find large .pdata funcs that call
# any simstep_guard owner (E8 rel32).
sim_owners = {b for b, _ in owners}
callers = {}
for b, e2 in funcs:
    if e2 - b < 4000:
        continue
    fo = off_of(b)
    body = data[fo : fo + (e2 - b)]
    for i in range(len(body) - 5):
        if body[i] != 0xE8:
            continue
        rel = struct.unpack_from("<i", body, i + 1)[0]
        tgt = (b + i + 5 + rel) & 0xFFFFFFFF
        if tgt in sim_owners:
            callers.setdefault((b, e2), set()).add(tgt)

print("large funcs calling simstep_guard owners (Simulate candidates):")
for (b, e2), tgts in sorted(callers.items(), key=lambda x: -(x[0][1] - x[0][0]))[:15]:
    print(
        f"  0x{b:08X} size={e2-b} -> "
        + ", ".join(f"0x{t:X}" for t in sorted(tgts))
    )

# Compare with sample top
TOP = [
    0x0140D288,
    0x011DCE70,
    0x01088D30,
    0x00E32A82,
    0x011E601A,
    0x01400FEB,
    0x0166F9B4,
    0x01072032,
    0x011C8D00,
]
print("sample Top vs simstep/PFor owners:")
all_hot = {b for b, _ in owners} | {b for b, _ in owners2}
for r in TOP:
    o = owner(r)
    mark = "HIT_FP" if o and o[0] in all_hot else "other"
    print(f"  0x{r:08X} owner={hex(o[0]) if o else None} {mark}")
