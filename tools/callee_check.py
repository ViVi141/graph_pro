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
md = Cs(CS_ARCH_X86, CS_MODE_64)
for rva, label in [(0x01A249F0, "callee #1 (1645 B, 4x)"), (0x01260C00, "callee #2 (2595 B, 4x)"),
                   (0x0110AD20, "most-called (10 B, 17x)")]:
    o = off(rva)
    print("\n=== %s  RVA 0x%X ===" % (label, rva))
    n = 0
    for ins in md.disasm(data[o:o+80], ib + rva):
        print("   0x%08X  %-7s %s" % (ins.address - ib, ins.mnemonic, ins.op_str))
        n += 1
        if n >= 10: break
