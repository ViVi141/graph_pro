
from PIL import Image
import numpy as np
p = r"<ARMA3_DOCS>\Screenshots\gp_r_baseline.png"
a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)/255
def stat(name, x0,y0,x1,y1):
    z = a[y0:y1, x0:x1]
    l = 0.2126*z[...,0]+0.7152*z[...,1]+0.0722*z[...,2]
    rb = (z[...,0]-z[...,2]).mean()
    print(f"{name:16s} luma=%.3f  std=%.3f  R-B=%+.4f  sat=%.3f" % (l.mean(), l.std(), rb,
          ((z.max(axis=2)-z.min(axis=2))/np.maximum(z.max(axis=2),1e-5)).mean()))
# 阳光下路面 vs 墙影里的路面 (1920x1080)
stat("sun road",      700, 700, 900, 800)
stat("shadow road",   250, 380, 450, 430)
stat("wall sunlit",   300, 150, 450, 220)
stat("wall shaded",   120, 260, 200, 320)
stat("dirt",          980, 760, 1120, 860)
stat("roof",          1500, 560, 1650, 620)
stat("soldier",       1050, 830, 1090, 900)
