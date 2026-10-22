
import re, struct, os
d = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\extract\shdc"
b = open(os.path.join(d,"Shaders_5_0_PS.shdc"),'rb').read()
pat = re.compile(rb'([A-Za-z][A-Za-z0-9_]{2,60})\x00((?:ps|vs)_5_0)\x00([0-9A-F]{8})\x00')
names = [m.group(1).decode() for m in pat.finditer(b)]
uniq = sorted(set(names))
print("ps_5_0 entries:", len(uniq))
cands = [n for n in uniq if ('NormalMap' in n or 'Specular' in n) and ('Default' in n or 'Super' in n)]
print("material candidates:", len(cands))
for n in cands[:25]: print("   ", n)
