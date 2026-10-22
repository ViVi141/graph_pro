
import re, os, collections
d = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\extract\shdc"
pat = re.compile(rb'([A-Za-z][A-Za-z0-9_]{2,40})\x00((?:ps|vs|gs|cs)_[45]_[01])\x00([0-9A-F]{8})\x00')
for fn in ["Shaders_4_0_PP.shdc","Shaders_5_0_PP.shdc"]:
    b = open(os.path.join(d,fn),'rb').read()
    ms = pat.findall(b)
    print(f"=== {fn}: {len(ms)} named entries")
    names = [m[0].decode() for m in ms]
    print(", ".join(names[:130]))
    print()
    print("stages:", collections.Counter(m[1].decode() for m in ms))
