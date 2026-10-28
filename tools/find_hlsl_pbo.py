
import glob, os, struct
ADD = r"<ARMA3>\Addons"
hits = []
for pbo in sorted(glob.glob(os.path.join(ADD, "*.pbo"))):
    try:
        data = open(pbo,'rb').read(400000)
    except Exception:
        continue
    if b'.hlsl' in data:
        hits.append(os.path.basename(pbo))
print("pbo with .hlsl in header area:", hits[:20], "count", len(hits))
# also bin.pbo
b = open(r"<ARMA3>\Dta\bin.pbo",'rb').read(400000)
print("bin.pbo .hlsl:", b.count(b'.hlsl'))
