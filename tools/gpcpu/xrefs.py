import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pe

def callers(b, target):
    t = np.frombuffer(b.text, dtype=np.uint8).astype(np.int64)
    n = len(t)
    va = b.sections[0][1]
    idx = np.nonzero(t[:n-5] == 0xE8)[0]
    disp = (t[idx+1] | (t[idx+2] << 8) | (t[idx+3] << 16) | (t[idx+4] << 24))
    disp = np.where(disp >= 0x80000000, disp - 0x100000000, disp)
    tgt = va + idx + 5 + disp
    sel = idx[tgt == target]
    return [(va + int(i), b.func_at(va + int(i))) for i in sel]

if __name__ == "__main__":
    b = pe.Bin()
    for a in sys.argv[1:]:
        tgt = int(a, 16)
        cs = callers(b, tgt)
        print("\n### callers of %x : %d" % (tgt, len(cs)))
        for site, f in cs[:20]:
            print("   site %x  in func %s size %s" % (site, hex(f[0]) if f else None, f[1]-f[0] if f else 0))
