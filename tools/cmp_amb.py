
from PIL import Image
import numpy as np
old = r"C:\Users\74738\.dsh\attachments\v1\objects\6a\6a7fb4f0b30eefca60dc4dfb2f0047bda42194a78b36d82c0fb5ed18ecca1683"
new = r"C:\Users\74738\.dsh\attachments\v1\objects\9c\9cda81ac89d36daa4f2ef9d15aef2310eaa8b24367a6c2e980dcf7a7e34b1edd"
regions = {"inside wall":(400,350,700,500), "inside floor":(400,900,700,1050),
           "outside floor":(940,430,1010,470), "outside wall":(900,300,960,360), "ceiling":(500,130,800,190)}
for tag,p in [("before(旧)",old),("after(新)",new)]:
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)/255
    print("==", tag)
    for name,(x0,y0,x1,y1) in regions.items():
        z = a[y0:y1, x0:x1]
        l = 0.2126*z[...,0]+0.7152*z[...,1]+0.0722*z[...,2]
        print(f"  {name:14s} mean=%.3f p95=%.3f" % (l.mean(), np.percentile(l,95)))
