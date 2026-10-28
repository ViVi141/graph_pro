import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe, capstone
b = pe.Bin(r"<ARMA3>\Arma3_x64.exe")
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
TEXT = b.sections[0][1]

def info(rva):
    f = b.func_at(rva)
    if not f:
        print("%08x not in pdata" % rva); return
    code = b.text[f[0]-TEXT: f[1]-TEXT]
    strs, calls = [], {}
    for ins in md.disasm(code, f[0]):
        if ins.mnemonic == 'call' and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            calls[ins.operands[0].imm] = calls.get(ins.operands[0].imm, 0) + 1
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                t = ins.address + ins.size + op.mem.disp
                try: s = b.cstr(t, 80)
                except Exception: continue
                if s and 4 <= len(s) and all(32 <= ord(c) < 127 for c in s) and s not in strs:
                    strs.append(s)
    print("%08x size=%d" % (f[0], f[1]-f[0]))
    print("   strings:", strs[:6])
    top = sorted(calls.items(), key=lambda kv: -kv[1])[:6]
    print("   calls:", ["%x x%d" % (a, n) for a, n in top])

for r in (0x169B288, 0x1698F85, 0x1A25430, 0x16CCB80, 0x1700920, 0x1638618):
    info(r)
