import struct
EXE = r"D:\SteamLibrary\steamapps\common\Arma 3\Arma3_x64.exe"
data = open(EXE, "rb").read()
e = struct.unpack_from("<I", data, 0x3C)[0]
coff = e + 4
nsec = struct.unpack_from("<H", data, coff + 2)[0]
opt = coff + 20
sec_off = opt + struct.unpack_from("<H", data, coff + 16)[0]
secs = []
for i in range(nsec):
    o = sec_off + i * 40
    name = data[o:o+8].rstrip(b"\0").decode("latin-1","ignore")
    vs, va, rs, ra = struct.unpack_from("<IIII", data, o + 8)
    secs.append((name, va, vs, ra, rs))
def off_of(rva):
    for name, va, vs, ra, rs in secs:
        if va <= rva < va + vs: return ra + (rva - va)
    return None
def sec_of(rva):
    for name, va, vs, ra, rs in secs:
        if va <= rva < va + vs: return name
    return None

# --- .pdata -> function table ---
pd = [s for s in secs if s[0] == ".pdata"][0]
_, va, vs, ra, rs = pd
funcs = []
for i in range(0, rs, 12):
    b, e2, u = struct.unpack_from("<III", data, ra + i)
    if b == 0: continue
    funcs.append((b, e2))
funcs.sort()
print("functions in .pdata:", len(funcs))

target = 0x18D423
import bisect
starts = [f[0] for f in funcs]
k = bisect.bisect_right(starts, target) - 1
while k >= 0:
    b, e2 = funcs[k]
    if b <= target < e2:
        print("DrawIndexedInstanced call site RVA 0x%X is inside function 0x%X .. 0x%X (size %d)" % (target, b, e2, e2-b))
        fo = off_of(b)
        print("function prologue bytes:")
        print("  " + " ".join("%02x" % x for x in data[fo:fo+40]))
        break
    k -= 1
else:
    print("not found in .pdata")

# bytes around the call site
co = off_of(target)
print("\naround call site:")
print("  " + " ".join("%02x" % x for x in data[co-16:co+16]))
