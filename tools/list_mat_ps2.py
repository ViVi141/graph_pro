
import re, os
d = r"<REPO>\extract\shdc"
b = open(os.path.join(d,"Shaders_5_0_PS.shdc"),'rb').read()
pat = re.compile(rb'([A-Za-z][A-Za-z0-9_]{2,60})\x00(ps_4_0)\x00([0-9A-F]{8})\x00')
names = sorted(set(m.group(1).decode() for m in pat.finditer(b)))
print("entries:", len(names))
cands = [n for n in names if ('NormalMap' in n or 'Specular' in n)]
print("material candidates:", len(cands))
for n in cands[:30]: print("   ", n)
