
from PIL import Image
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
def sharp(p):
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32).mean(axis=2)
    k = np.array([[0,1,0],[1,-4,1],[0,1,0]], np.float32)
    w = sliding_window_view(a,(3,3)); lap=(w*k).sum(axis=(2,3))
    return float(lap.var())/1000
import os
paths = {
 "02:00 原版": r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\before\gp_r_baseline.png",
 "02:13 原版": r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\before2\gp_r_baseline.png",
 "02:27 原版": r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\before3\gp_r_baseline.png",
 "02:36 新设置": r"C:\Users\74738\Documents\Arma 3\Screenshots\gp_r_baseline.png",
}
for k,p in paths.items():
    print(f"{k:14s} sharpness={sharp(p):.2f}  exists={os.path.exists(p)}")
