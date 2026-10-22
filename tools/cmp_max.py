
from PIL import Image
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
def sharp(p):
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32).mean(axis=2)
    k = np.array([[0,1,0],[1,-4,1],[0,1,0]], np.float32)
    w = sliding_window_view(a,(3,3)); lap=(w*k).sum(axis=(2,3))
    return float(lap.var())/1000
p1 = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\before2\gp_r_baseline.png"
p2 = r"C:\Users\74738\Documents\Arma 3\Screenshots\gp_r_baseline.png"
for tag,p in [("原版",p1),("拉满",p2)]:
    a=np.asarray(Image.open(p).convert("RGB")).astype(np.float32)/255
    lum=0.2126*a[...,0]+0.7152*a[...,1]+0.0722*a[...,2]
    print(tag, "sharp=%.2f luma=%.0f p99=%.0f" % (sharp(p), lum.mean()*255, np.percentile(lum,99)*255))
im=Image.open(p2).convert("RGB"); im.thumbnail((1100,1100))
im.save(r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\_live\maxed.png")
print("preview ok")
