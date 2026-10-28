
import re, struct, os
d = r"<REPO>\extract\shdc"
b = open(os.path.join(d,"Shaders_5_0_PP.shdc"),'rb').read()
out = r"<REPO>\extract\dxbc"
os.makedirs(out, exist_ok=True)
targets = ["PSPostProcessGlowNewFinalFilmic","PSPostProcessGlowNewFinalReinhard","PSPostProcessSSAOFinal"]
for t in targets:
    i = b.find(t.encode())
    if i < 0: print(t, "not found"); continue
    j = b.find(b"DXBC", i)
    size = struct.unpack_from('<I', b, j+24)[0]
    blob = b[j:j+size]
    fn = os.path.join(out, t + ".dxbc")
    open(fn,'wb').write(blob)
    print(t, "blob", size, "->", fn)
