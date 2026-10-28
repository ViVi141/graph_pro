
from PIL import Image
import numpy as np
p = r"<USERPROFILE>\.dsh\attachments\v1\objects\6a\6a7fb4f0b30eefca60dc4dfb2f0047bda42194a78b36d82c0fb5ed18ecca1683"
im = Image.open(p).convert("RGB")
a = np.asarray(im).astype(np.float32)/255
print("size", im.size)
def zone(name, x0,y0,x1,y1):
    z = a[y0:y1, x0:x1]
    l = 0.2126*z[...,0]+0.7152*z[...,1]+0.0722*z[...,2]
    print(f"{name:14s} luma={l.mean():.3f} p95={np.percentile(l,95):.3f} rgb=%.3f %.3f %.3f" % tuple(z.mean(axis=(0,1))))
# coordinates based on 1924x1140 image
zone("inside wall", 400, 350, 700, 500)
zone("inside floor", 400, 900, 700, 1050)
zone("outside floor", 940, 430, 1010, 470)
zone("outside wall", 900, 300, 960, 360)
zone("ceiling", 500, 130, 800, 190)
