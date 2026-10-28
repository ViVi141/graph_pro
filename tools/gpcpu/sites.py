import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe, capstone
b = pe.Bin(r"<ARMA3>\arma3server_x64.exe")
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
TEXT = b.sections[0][1]
TARGET = 0x646FC0
for fs in (0x62BAB0, 0x62BE7D, 0x62BF2E):
    f = b.func_at(fs)
    code = b.text[f[0]-TEXT: f[1]-TEXT]
    print("func %x size %d" % (f[0], f[1]-f[0]))
    for ins in md.disasm(code, f[0]):
        if ins.mnemonic == 'call' and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM and ins.operands[0].imm == TARGET:
            print("   call site %x bytes %s" % (ins.address, b.data(ins.address, 5).hex()))
