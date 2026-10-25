import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe, capstone
b = pe.Bin()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
TEXT_VA = b.sections[0][1]

def annot(ins):
    extra = ""
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            t = ins.address + ins.size + op.mem.disp
            d = b.data(t, 24)
            if d and all(32 <= c < 127 or c == 0 for c in d[:12]) and d[:1].isascii() and d[:1] not in (b'\0',):
                extra += "  ; %x %r" % (t, b.cstr(t, 60))
            else:
                extra += "  ; %x" % t
        if op.type == capstone.x86.X86_OP_IMM and ins.mnemonic in ("call", "jmp"):
            f = b.func_at(op.imm)
            if f:
                extra += "  ; func %x+%x sz%x" % (f[0], op.imm - f[0], f[1]-f[0])
    return extra

def dump(rva, size=None, limit=100000, start_off=0):
    f = b.func_at(rva) if size is None else (rva, rva + size)
    code = b.text[f[0]-TEXT_VA: f[1]-TEXT_VA]
    n = 0
    for ins in md.disasm(code, f[0]):
        if n < start_off:
            n += 1; continue
        print("%08x  %-28s %s" % (ins.address, ins.mnemonic + " " + ins.op_str, annot(ins)))
        n += 1
        if n >= limit: break

if __name__ == "__main__":
    dump(int(sys.argv[1], 16), limit=int(sys.argv[2]) if len(sys.argv) > 2 else 100000)
