
import re, os, struct
d = r"<REPO>\extract\shdc"
b = open(os.path.join(d,"Shaders_5_0_PS.shdc"),'rb').read()
pat = re.compile(rb'([A-Za-z][A-Za-z0-9_]{2,60})\x00(ps_4_0)\x00([0-9A-F]{8})\x00')
names = [m.group(1).decode() for m in pat.finditer(b)]
uniq = sorted(set(names))
print("ALL:", ", ".join(n for n in uniq if n.startswith("PSNormalMap") or n.startswith("PSDetail") or n.startswith("PSSuper")))
out = r"<REPO>\extract\dxbc_mat"
os.makedirs(out, exist_ok=True)
targets = ["PSNormalMapDetailMacroASSpecularMap","PSNormalMapMacroASSpecularMap"]
for t in targets:
    i = b.find(t.encode())
    if i < 0: print("miss", t); continue
    j = b.find(b"DXBC", i)
    size = struct.unpack_from('<I', b, j+24)[0]
    open(os.path.join(out, t + ".dxbc"), "wb").write(b[j:j+size])
    print("saved", t, size)
