import struct, re, bisect, sys, json
import numpy as np
from capstone import *
from capstone.x86 import *

EXE = sys.argv[1]
OUT = sys.argv[2]
data = open(EXE, "rb").read()
e = struct.unpack_from("<I", data, 0x3C)[0]; coff = e + 4
nsec = struct.unpack_from("<H", data, coff + 2)[0]; opt = coff + 20
ib = struct.unpack_from("<Q", data, opt + 24)[0]
sec_off = opt + struct.unpack_from("<H", data, coff + 16)[0]
secs = []
for i in range(nsec):
    o = sec_off + i * 40
    nm = data[o:o+8].rstrip(b"\0").decode("latin-1","ignore")
    vs, va, rs, ra = struct.unpack_from("<IIII", data, o + 8)
    secs.append((nm, va, vs, ra, rs))
def off(rva):
    for nm, va, vs, ra, rs in secs:
        if va <= rva < va + vs: return ra + (rva - va)
def sec_of(rva):
    for nm, va, vs, ra, rs in secs:
        if va <= rva < va + vs: return nm
    return None
pd = [s for s in secs if s[0] == ".pdata"][0]
_, pv, pvs, pra, prs = pd
fmap = {}
for i in range(0, prs, 12):
    b, e2, u = struct.unpack_from("<III", data, pra + i)
    if b: fmap[b] = e2

# RTTI -> vtable map
types = {}
for m in re.finditer(rb"\.\?A[VU][A-Za-z0-9_@?$<>.-]{3,200}@@", data):
    o = m.start()
    for nm, va, vs, ra, rs in secs:
        if ra <= o < ra + rs:
            types[va + (o - ra)] = m.group(0).decode("latin-1"); break
td = {r - 16: n for r, n in types.items()}
rd = [s for s in secs if s[0] == ".rdata"][0]
_, rrva, rvsz, rraw, rrsz = rd
cols = {}
for i in range(rraw, rraw + rrsz - 24, 4):
    sig, off_, cd, ptd, pcd = struct.unpack_from("<IIIII", data, i)
    if sig == 1 and ptd in td:
        cols[rrva + (i - rraw)] = td[ptd]
vt = {}
for i in range(rraw, rraw + rrsz - 8, 8):
    v = struct.unpack_from("<Q", data, i)[0]
    if v >= ib and (v - ib) in cols:
        vt[cols[v - ib]] = (rrva + (i - rraw)) + 8

sim_vt = [va for n, va in vt.items() if "Simulate@World" in n]
T = [s for s in secs if s[0] == ".text"][0]
_, trva, tvsz, traw, trsz = T
body = np.frombuffer(data[traw:traw+trsz], dtype=np.uint8)
def refs_to(target):
    out = []
    n = len(body) - 8
    pos = range(0, n)
    pos = np.arange(0, n, dtype=np.int64)
    for ilen in (5,6,7):
        o2 = pos + ilen - 4
        d = (body[o2].astype(np.int64) | (body[o2+1].astype(np.int64)<<8) |
             (body[o2+2].astype(np.int64)<<16) | (body[o2+3].astype(np.int64)<<24))
        d = np.where(d >= 2**31, d - 2**32, d)
        want = target - (trva + pos + ilen)
        out.extend(int(trva + k) for k in np.nonzero(d == want)[0][:200])
    return out

cand_funcs = set()
for va in sim_vt:
    for r in refs_to(va):
        k = bisect.bisect_right(list(sorted(fmap.keys())), r) - 1
        if k >= 0:
            starts = sorted(fmap.keys()); b = starts[k]
            if b <= r < fmap[b]: cand_funcs.add(b)
print("Simulate candidate addresses:", ["0x%X" % x for x in sorted(cand_funcs)])

md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
best = None
for f in sorted(cand_funcs):
    size = fmap[f] - f
    if size < 2000: continue
    code = data[off(f):off(f)+size]
    insns = list(md.disasm(code, ib + f))
    calls = [int(i.op_str,16) - ib for i in insns if i.mnemonic == "call" and i.op_str.startswith("0x")]
    callees = sorted({c for c in calls if c in fmap})
    if best is None or len(callees) > len(best[1]): best = (f, callees, size)
f, callees, size = best
print("World::Simulate @ 0x%X  size %d  callees %d" % (f, size, len(callees)))

def analyse(rva):
    sz = fmap[rva] - rva
    if sz < 32 or sz > 600: return None
    insns = list(md.disasm(data[off(rva):off(rva)+sz], ib + rva))
    if not insns: return None
    if sum(1 for i in insns if i.mnemonic == "call") > 1: return None
    simd = sum(1 for i in insns if i.mnemonic.endswith(("ss","ps","sd","pd")))
    total = 0; cl = 0
    for i in insns:
        if i.mnemonic in ("jmp","call","ret","je","jne","jg","jl","jae","jbe","js","jns","loop","jle","jge"):
            return None
        for op in i.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP: return None
        total += i.size
        if total >= 5: cl = total; break
    if not cl or cl > 16: return None
    return dict(rva=rva, copy_len=cl, size=sz, simd=simd)

cands = [a for a in (analyse(c) for c in callees) if a]
cands.sort(key=lambda c: -c["simd"])
print("hookable candidates:", len(cands))
lines = ["// auto-generated for " + EXE.split("\\")[-1],
         "#pragma once",
         "struct CandHook { unsigned rva; unsigned copyLen; unsigned size; volatile long count; };",
         "static CandHook g_cands[] = {"]
for c in cands:
    lines.append("    { 0x%08X, %d, %d, 0 },   // simd %d" % (c["rva"], c["copy_len"], c["size"], c["simd"]))
lines.append("};")
lines.append("static const int g_nCand = sizeof(g_cands)/sizeof(g_cands[0]);")
open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("wrote", OUT, "with", len(cands), "entries")