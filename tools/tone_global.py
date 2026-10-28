
from PIL import Image
import numpy as np
for tag,p in [("current(0.93/1.10)", r"<ARMA3_DOCS>\Screenshots\gp_r_baseline.png"),
              ("ref maxed", r"<REPO>\demo\_live\maxed.png")]:
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)/255
    l = 0.2126*a[...,0]+0.7152*a[...,1]+0.0722*a[...,2]
    rb = a[...,0]-a[...,2]
    dark = l < 0.35
    mid  = (l >= 0.35) & (l < 0.55)
    lit  = l >= 0.55
    print(f"== {tag}")
    for name,m in [("dark(<0.35)",dark),("mid(0.35-0.55)",mid),("lit(>0.55)",lit)]:
        if m.sum() < 100: continue
        print(f"   {name:16s} share=%.1f%%  luma=%.3f  R-B=%+.4f" % (m.mean()*100, l[m].mean(), rb[m].mean()))
