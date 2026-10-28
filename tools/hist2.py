
from PIL import Image
import numpy as np
for tag,p in [("v5 tonemap", r"<ARMA3_DOCS>\Screenshots\gp_r_baseline.png"),
              ("before",     r"<REPO>\demo\_live\maxed.png")]:
    im = Image.open(p).convert("RGB")
    a = np.asarray(im).astype(np.float32)/255
    l = 0.2126*a[...,0]+0.7152*a[...,1]+0.0722*a[...,2]
    mx=a.max(axis=2); mn=a.min(axis=2); s=np.where(mx>1e-5,(mx-mn)/np.maximum(mx,1e-5),0)
    print(f"{tag:12s} p1=%.3f p99=%.3f mean=%.3f std=%.3f sat=%.3f dark%%=%.1f light%%=%.1f" % (
        np.percentile(l,1), np.percentile(l,99), l.mean(), l.std(), s.mean(),
        (l<0.15).mean()*100, (l>0.85).mean()*100))
