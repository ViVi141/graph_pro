
import re, os, csv
d = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\extract\shdc"
out = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\extract\shader-inventory.csv"
pat = re.compile(rb'([A-Za-z][A-Za-z0-9_]{2,40})\x00((?:ps|vs|gs|cs)_[45]_[01])\x00([0-9A-F]{8})\x00')
rows=[]
for fn in sorted(os.listdir(d)):
    if not fn.endswith('.shdc'): continue
    b=open(os.path.join(d,fn),'rb').read()
    seen=set()
    for name,stage,h in pat.findall(b):
        key=(name,stage,h)
        if key in seen: continue
        seen.add(key)
        rows.append([fn, name.decode(), stage.decode(), h.decode()])
with open(out,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['cache','name','stage','hash']); w.writerows(rows)
print("rows", len(rows), "->", out)
