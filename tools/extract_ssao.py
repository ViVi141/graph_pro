
import re, struct, os
d = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\extract\shdc"
b = open(os.path.join(d,"Shaders_5_0_PP.shdc"),'rb').read()
pat = re.compile(rb'([A-Za-z][A-Za-z0-9_]{2,60})\x00(ps_4_0)\x00([0-9A-F]{8})\x00')
names = sorted(set(m.group(1).decode() for m in pat.finditer(b)))
print([n for n in names if 'SSAO' in n])
out = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\extract\dxbc_ssao"
os.makedirs(out, exist_ok=True)
for t in ["PSPostProcessSSAOFinal","PSPostProcessSSAO","PSPostProcessSSAOBlurHorz"]:
    i = b.find(t.encode())
    if i < 0: print("miss", t); continue
    j = b.find(b"DXBC", i)
    size = struct.unpack_from('<I', b, j+24)[0]
    open(os.path.join(out, t + ".dxbc"), "wb").write(b[j:j+size])
    print(t, size)
