import struct, collections, json
from capstone import *
from capstone.x86 import *
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
pd = [s for s in secs if s[0] == ".pdata"][0]
_, pv, pvs, pra, prs = pd
fmap = {}
for i in range(0, prs, 12):
    b, e2, u = struct.unpack_from("<III", data, pra + i)
    if b: fmap[b] = e2

md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
# rebuild Simulate's callees
START, SIZE = 0x11527E0, 11093
code = data[off(START):off(START)+SIZE]
callees = set()
for ins in md.disasm(code, ib + START):
    if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
        rva = int(ins.op_str, 16) - ib
        if rva in fmap: callees.add(rva)
print("Simulate callees:", len(callees))

def analyse(rva):
    size = fmap[rva] - rva
    if size < 32 or size > 600: return None
    code = data[off(rva):off(rva)+size]
    insns = list(md.disasm(code, ib + rva))
    if not insns: return None
    calls = sum(1 for i in insns if i.mnemonic == "call")
    if calls > 1: return None
    simd = sum(1 for i in insns if i.mnemonic.startswith(("movap","movup","mul","add","sub","div","sqrt","rsqrt","comis","ucomis","pxor","max","min")) and i.mnemonic.endswith("ss") or (i.mnemonic.endswith("ps")))
    # prologue safety: first >=5 bytes with no rip-relative operand
    total = 0; copy_len = 0; safe = True
    for i in insns:
        for op in i.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                safe = False
        total += i.size
        if total >= 5:
            copy_len = total; break
        if total > 24: return None
    if not safe: return None
    return dict(rva=rva, size=size, copy_len=copy_len, calls=calls, simd=simd)

cands = []
for rva in sorted(callees):
    a = analyse(rva)
    if a: cands.append(a)
print("candidates (leaf-ish, hookable prologue, 32-600 B):", len(cands))
cands.sort(key=lambda c: -c["simd"])
print("\n%-12s %6s %5s %5s %5s" % ("rva", "size", "copy", "calls", "simd"))
for c in cands[:15]:
    print("0x%08X %6d %5d %5d %5d" % (c["rva"], c["size"], c["copy_len"], c["calls"], c["simd"]))
json.dump(cands, open(r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\extract\candidates.json","w"), indent=1)
print("\nwrote extract/candidates.json")
