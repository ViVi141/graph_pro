import os
import sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe, capstone, numpy as np
SRV = r"<ARMA3>\arma3server_x64.exe"
b = pe.Bin(SRV)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
TEXT = b.sections[0][1]
t = np.frombuffer(b.text, dtype=np.uint8).astype(np.int64)
N = len(t)
E8 = np.nonzero(t[:N-5] == 0xE8)[0]
DISP = (t[E8+1] | (t[E8+2] << 8) | (t[E8+3] << 16) | (t[E8+4] << 24))
DISP = np.where(DISP >= 0x80000000, DISP - 0x100000000, DISP)
TGT = TEXT + E8 + 5 + DISP

def real_callers(target, limit=8):
    idx = E8[TGT == target]
    out = []
    for p in idx:
        rva = int(TEXT + p)
        f = b.func_at(rva)
        if not f: continue
        code = b.text[f[0]-TEXT: f[1]-TEXT]
        ok = False
        for ins in md.disasm(code, f[0]):
            if ins.address == rva:
                ok = ins.mnemonic == 'call'
                break
            if ins.address > rva: break
        if ok:
            out.append((rva, f))
            if len(out) >= limit: break
    return out

def strings_of(f, n=6):
    code = b.text[f[0]-TEXT: f[1]-TEXT]
    ss = []
    for ins in md.disasm(code, f[0]):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                tt = ins.address + ins.size + op.mem.disp
                try: s = b.cstr(tt, 60)
                except Exception: continue
                if s and 4 <= len(s) and all(32 <= ord(c) < 127 for c in s) and s not in ss:
                    ss.append(s)
    return ss[:n]

def callees_of(f):
    code = b.text[f[0]-TEXT: f[1]-TEXT]
    cs = {}
    for ins in md.disasm(code, f[0]):
        if ins.mnemonic == 'call' and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            cs[ins.operands[0].imm] = cs.get(ins.operands[0].imm, 0) + 1
    return sorted(cs.items(), key=lambda kv: -kv[1])

targets = [0x646FC0, 0x1072032, 0x1071489, 0x13792BA, 0x1400FEB, 0x139B7A5, 0x10747E0, 0x137A1FA, 0x10ABC85]
for tv in targets:
    f = b.func_at(tv)
    print("\n===== %x (size %d) =====" % (tv, f[1]-f[0]))
    cs, strs = callctx = None, None
    cl = callees_of(f)
    print("  callees:", ", ".join("%x x%d" % (a, n) for a, n in cl[:6]))
    cals = real_callers(tv)
    if not cals:
        print("  no direct callers (virtual/inline)")
    for site, cf in cals[:4]:
        print("  caller %x size=%d strings=%s" % (cf[0], cf[1]-cf[0], strings_of(cf)[:4]))
