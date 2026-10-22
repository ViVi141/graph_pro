import struct
from capstone import *
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
def off(rva):
    for nm, va, vs, ra, rs in secs:
        if va <= rva < va + vs: return ra + (rva - va)
    return None
pd = [s for s in secs if s[0] == ".pdata"][0]
_, pv, pvs, pra, prs = pd
funcs = {}
for i in range(0, prs, 12):
    b, e2, u = struct.unpack_from("<III", data, pra + i)
    if b: funcs[b] = e2

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
targets = [("World::Simulate", 0x11527E0), ("World::PerformAI", 0x1106B30),
           ("AIPathPlanner::ProcessSearching", 0x1369C60),
           ("Landscape::PrepareGroundClutter", 0x15E8220)]
for name, rva in targets:
    end = funcs.get(rva)
    o = off(rva)
    code = data[o:o + 96]
    print("\n=== %s  RVA 0x%X  size %s ===" % (name, rva, ("%d" % (end - rva)) if end else "?"))
    n = 0
    for ins in md.disasm(code, ib + rva):
        print("  0x%08X  %-8s %s" % (ins.address - ib, ins.mnemonic, ins.op_str))
        n += 1
        if n >= 14: break
