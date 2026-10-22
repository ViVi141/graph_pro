import struct, collections
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
fmap = {}
for i in range(0, prs, 12):
    b, e2, u = struct.unpack_from("<III", data, pra + i)
    if b: fmap[b] = e2

START, SIZE = 0x11527E0, 11093
md = Cs(CS_ARCH_X86, CS_MODE_64)
o = off(START)
code = data[o:o + SIZE]
calls = collections.Counter()
for ins in md.disasm(code, ib + START):
    m = ins.mnemonic
    if m != "call": continue
    op = ins.op_str
    if op.startswith("0x"):
        tgt = int(op, 16)
        rva = tgt - ib
        if rva in fmap:
            calls[rva] += 1
print("direct calls inside World::Simulate:", sum(calls.values()), " to", len(calls), "distinct functions")
rows = sorted(calls.items(), key=lambda kv: -fmap[kv[0]] if kv[0] in fmap else 0)
print("\ntop callees by function SIZE (big callee = usually heavy):")
for rva, cnt in rows[:18]:
    print("   0x%08X  size %6d  called %2dx" % (rva, fmap[rva] - rva, cnt))
print("\ntop callees by CALL COUNT:")
for rva, cnt in calls.most_common(12):
    print("   0x%08X  size %6d  called %2dx" % (rva, fmap[rva] - rva, cnt))
