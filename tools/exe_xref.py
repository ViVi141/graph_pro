import struct, re, numpy as np
EXE = r"D:\SteamLibrary\steamapps\common\Arma 3\Arma3_x64.exe"
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
T = [s for s in secs if s[0] == ".text"][0]
_, trva, tvsz, traw, trsz = T
text = data[traw:traw+trsz]
body = np.frombuffer(text, dtype=np.uint8)

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

pd = [s for s in secs if s[0] == ".pdata"][0]
_, pv, pvs, pra, prs = pd
funcs = []
for i in range(0, prs, 12):
    b, e2, u = struct.unpack_from("<III", data, pra + i)
    if b: funcs.append((b, e2))
funcs.sort()
starts = np.array([f[0] for f in funcs], dtype=np.uint32)
import bisect
def owner(rva):
    k = bisect.bisect_right(starts, rva) - 1
    if k < 0: return None
    b, e2 = funcs[k]
    return b if b <= rva < e2 else None

def find_refs(target_rva, ilen=7):
    n = len(body) - 8
    pos = np.arange(0, n, dtype=np.int64)
    off = pos + ilen - 4
    d = (body[off].astype(np.int64)
         | (body[off+1].astype(np.int64) << 8)
         | (body[off+2].astype(np.int64) << 16)
         | (body[off+3].astype(np.int64) << 24))
    d = np.where(d >= 2**31, d - 2**32, d)
    want = target_rva - (trva + pos + ilen)
    idx = np.nonzero(d == want)[0]
    return [int(trva + k) for k in idx[:200]]

targets = {}
for name, va in vt.items():
    for kw in ("Simulate@World", "PrepareGroundClutter@Landscape", "ProcessSearching@AIPathPlanner",
               "PerformAI@World", "SelectActiveAggLights@Scene", "PrepareDrawPrepareCloudlets@World"):
        if kw in name:
            targets.setdefault(kw, (va, name))

print("targets found:", len(targets))
for kw, (va, name) in sorted(targets.items()):
    allrefs = set()
    for ilen in (5, 6, 7, 8):
        for r in find_refs(va, ilen):
            allrefs.add(r)
    owners = sorted({o for o in (owner(r) for r in allrefs) if o})
    print("%-34s vtable 0x%08X  refs %3d  funcs %2d  %s" %
          (kw, va, len(allrefs), len(owners), " ".join("0x%X" % x for x in owners[:4])))