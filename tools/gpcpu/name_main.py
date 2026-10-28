import os
import sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe, capstone
SRV = r"<ARMA3>\arma3server_x64.exe"
b = pe.Bin(SRV)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
TEXT = b.sections[0][1]
top = []
for line in open(r"<GP_WORK>\main_top_224.txt", encoding="utf-8", errors="replace"):
    m = re.match(r"(\d+)\s+([\d.]+)\s+([\d.]+)\s+0x([0-9A-Fa-f]+)\s+(\d+)", line.strip())
    if m: top.append((int(m.group(1)), float(m.group(3)), int(m.group(4), 16), int(m.group(5))))

def strings_in(f):
    out = []
    code = b.text[f[0]-TEXT: f[1]-TEXT]
    for ins in md.disasm(code, f[0]):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                t = ins.address + ins.size + op.mem.disp
                try:
                    s = b.cstr(t, 80)
                except Exception:
                    continue
                if s and len(s) >= 4 and all(32 <= ord(ch) < 127 for ch in s):
                    out.append(s)
    seen = []
    for s in out:
        if s not in seen: seen.append(s)
    return seen[:8]

for hits, pct, rva, size in top[:15]:
    f = b.func_at(rva)
    ss = strings_in(f) if f else []
    print("%2d %6.2f%%  %08x size=%d  %s" % (hits, pct, rva, size, " | ".join(ss)))
