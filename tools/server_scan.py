import struct, re, bisect
EXE = r"D:\SteamLibrary\steamapps\common\Arma 3\arma3server_x64.exe"
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
print("size", len(data), " imagebase 0x%X" % ib)
names = sorted(set(m.group(0).decode("latin-1") for m in re.finditer(rb"\.\?A[VU][A-Za-z0-9_@?$<>.-]{3,200}@@", data)))
print("RTTI names:", len(names))
pd = [s for s in secs if s[0] == ".pdata"][0]
_, pv, pvs, pra, prs = pd
funcs = []
for i in range(0, prs, 12):
    b, e2, u = struct.unpack_from("<III", data, pra + i)
    if b: funcs.append((b, e2))
funcs.sort()
print(".pdata functions:", len(funcs))
hits = [n for n in names if ("Simulate@World" in n or "PerformAI@World" in n or "ProcessSearching" in n)]
print("\nkey methods present:")
for h in hits[:8]:
    print("   ", h[:110])
