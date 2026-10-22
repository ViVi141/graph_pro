
from PIL import Image
import numpy as np
p = r"C:\Users\74738\Documents\Arma 3\Screenshots\gp_r_baseline.png"
a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)/255
def stat(name, x0,y0,x1,y1):
    z = a[y0:y1, x0:x1]
    l = 0.2126*z[...,0]+0.7152*z[...,1]+0.0722*z[...,2]
    print(f"{name:14s} luma=%.3f  R-B=%+.4f  std=%.3f  sat=%.3f" % (l.mean(), (z[...,0]-z[...,2]).mean(), l.std(),
          ((z.max(axis=2)-z.min(axis=2))/np.maximum(z.max(axis=2),1e-5)).mean()))
stat("sun road",    700, 700, 900, 800)
stat("shadow road", 250, 380, 450, 430)
stat("sun dirt",    980, 760, 1120, 860)
stat("wall sun",    300, 150, 450, 220)
stat("wall shade",  120, 260, 200, 320)
