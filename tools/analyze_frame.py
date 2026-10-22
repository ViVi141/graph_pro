
from PIL import Image
import numpy as np
p = r"C:\Users\74738\Documents\Arma 3\Screenshots\gp_r_baseline.png"
a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)/255.0
lum = 0.2126*a[...,0]+0.7152*a[...,1]+0.0722*a[...,2]
mx = a.max(axis=2); mn = a.min(axis=2)
sat = np.where(mx>1e-5,(mx-mn)/np.maximum(mx,1e-5),0)
print("luma  p1=%.3f p5=%.3f p50=%.3f p95=%.3f p99=%.3f" % tuple(np.percentile(lum,[1,5,50,95,99])))
print("luma  mean=%.3f std=%.3f" % (lum.mean(), lum.std()))
print("sat   mean=%.3f p95=%.3f" % (sat.mean(), np.percentile(sat,95)))
print("shadow(<0.15) share=%.1f%%  highlight(>0.85) share=%.1f%%" % ((lum<0.15).mean()*100,(lum>0.85).mean()*100))
print("mean RGB: %.3f %.3f %.3f" % tuple(a.mean(axis=(0,1))))
# 分区域色温 (R-B)
h,w = lum.shape
zones = {"top":(0,h//3),"mid":(h//3,2*h//3),"bottom":(2*h//3,h)}
for name,(y0,y1) in zones.items():
    print(f"{name:6s} luma=%.3f  R-B=%.4f  sat=%.3f" % (lum[y0:y1].mean(), (a[y0:y1,:,0]-a[y0:y1,:,2]).mean(), sat[y0:y1].mean()))
