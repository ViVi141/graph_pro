import struct, re
EXE = r"D:\SteamLibrary\steamapps\common\Arma 3\Arma3_x64.exe"
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
    nm = data[o:o+8].rstrip(b"\0").decode("latin-1","ignore")
    vs, va, rs, ra = struct.unpack_from("<IIII", data, o + 8)
    secs.append((nm, va, vs, ra, rs))
def sec_index(rva):
    for k, (nm, va, vs, ra, rs) in enumerate(secs):
        if va <= rva < va + vs: return k
    return -1
types = {}
for m in re.finditer(rb"\.\?A[VU][A-Za-z0-9_@?$<>.-]{3,160}@@", data):
    o = m.start()
    for nm, va, vs, ra, rs in secs:
        if ra <= o < ra + rs:
            types[va + (o - ra)] = m.group(0).decode("latin-1")
            break
print("type names:", len(types))
# type descriptor structure starts 16 bytes before the name
td_struct = {rva - 16: name for rva, name in types.items()}

rdata = [s for s in secs if s[0] == ".rdata"][0]
_, rva0, vsz0, ra0, rsz0 = rdata
cols = {}
for i in range(ra0, ra0 + rsz0 - 24, 4):
    sig, off_, cd, ptd, pcd = struct.unpack_from("<IIIII", data, i)
    if sig != 1: continue
    if ptd in td_struct:
        cols[rva0 + (i - ra0)] = td_struct[ptd]
print("COLs:", len(cols))
colset = set(cols)
vt = {}
for i in range(ra0, ra0 + rsz0 - 8, 8):
    v = struct.unpack_from("<Q", data, i)[0]
    if v < ib: continue
    r = v - ib
    if r in colset:
        vt[cols[r]] = (rva0 + (i - ra0)) + 8
print("vtables:", len(vt))
def show(pat, limit=5):
    ks = sorted(k for k in vt if pat in k)
    print("\n[%s] %d classes" % (pat, len(ks)))
    for k in ks[:limit]:
        print("   0x%08X  %s" % (vt[k], k[:100]))
for p in ("DX11::", "Scene", "World", "Landscape", "Render"):
    show(p)
