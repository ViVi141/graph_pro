
import re, os, collections
d = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\extract\shdc"
pat = re.compile(rb'([A-Za-z][A-Za-z0-9_]{2,40})\x00((?:ps|vs|gs|cs)_[45]_[01])\x00([0-9A-F]{8})\x00')
total = 0
rows = []
for fn in sorted(os.listdir(d)):
    b = open(os.path.join(d,fn),'rb').read()
    ms = pat.findall(b)
    total += len(ms)
    rows.append((fn, len(ms), len(b)))
    print(f"{fn:26s} named={len(ms):5d} size={len(b):10d}")
print("TOTAL named entries:", total)
b = open(os.path.join(d,'Shaders_5_0_PS.shdc'),'rb').read()
names = [m[0].decode() for m in pat.findall(b)]
hits = [n for n in names if re.search(r'(SMAA|FXAA|AA|Resolve|MSAA)', n, re.I)]
print("\nPS cache AA-related names:", sorted(set(hits))[:40])
print("\nPS cache sample:", sorted(set(names))[:40])
