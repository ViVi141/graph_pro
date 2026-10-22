import struct, os, sys
EXE = r"D:\SteamLibrary\steamapps\common\Arma 3\arma3server_x64.exe"
OUT = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\inject\counter\funcs.bin"
data = open(EXE, "rb").read()
e = struct.unpack_from("<I", data, 0x3C)[0]; coff = e + 4
nsec = struct.unpack_from("<H", data, coff + 2)[0]; opt = coff + 20
sec_off = opt + struct.unpack_from("<H", data, coff + 16)[0]
secs = []
for i in range(nsec):
    o = sec_off + i * 40
    nm = data[o:o+8].rstrip(b"\0").decode("latin-1","ignore")
    vs, va, rs, ra = struct.unpack_from("<IIII", data, o + 8)
    secs.append((nm, va, vs, ra, rs))
pd = [s for s in secs if s[0] == ".pdata"][0]
_, pv, pvs, pra, prs = pd
pairs = []
for i in range(0, prs, 12):
    b, e2, u = struct.unpack_from("<III", data, pra + i)
    if b and e2 > b: pairs.append((b, e2))
pairs.sort()
with open(OUT, "wb") as f:
    f.write(struct.pack("<I", len(pairs)))
    for b, e2 in pairs:
        f.write(struct.pack("<II", b, e2))
print("wrote", OUT, len(pairs), "functions,", os.path.getsize(OUT), "bytes")
