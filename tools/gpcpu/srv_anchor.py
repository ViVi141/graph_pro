import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe, xrefs

SRV = r"<ARMA3>\arma3server_x64.exe"
b = pe.Bin(SRV)
print("funcs", len(b.funcs), "base", hex(b.base))
ss = b.strings(8, 160)
for s in ["simulation started twice in a frame?", "ParallelFor sync", "mtVehS", "Error: Cannot create micro jobs thread: %s"]:
    hit = [a for a, t in ss if t == s]
    print("\nstring", s, "->", [hex(x) for x in hit])
    for a in hit[:1]:
        xr = b.xrefs(a)
        print("  xrefs", len(xr))
        for x in xr[:5]:
            f = b.func_at(x)
            print("   site %x func %s size %s" % (x, hex(f[0]) if f else None, f[1]-f[0] if f else 0))
            if f:
                cs = xrefs.callers(b, f[0])
                print("     callers:", [(hex(c), hex(cf[0]) if cf else None, cf[1]-cf[0] if cf else 0) for c, cf in cs[:6]])
