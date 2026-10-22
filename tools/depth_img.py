import numpy as np
from PIL import Image
p = r"D:\SteamLibrary\steamapps\common\Arma 3\GP_depth.raw"
W,H=1920,1080
raw=np.fromfile(p,dtype=np.uint32).reshape(H,W)
d=(raw&0xFFFFFF).astype(np.float32)/16777216.0
z=0.1/np.maximum(1.0-d,1e-7)
zs=np.clip(z,0,3000)
img=(255.0*(1.0-np.log1p(zs)/np.log1p(3000.0))).astype(np.uint8)
Image.fromarray(img).save(r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\depth-linear.png")
print("z p1 %.1f p50 %.1f p99 %.1f max %.0f"%(np.percentile(z,1),np.percentile(z,50),np.percentile(z,99),z.max()))
# count pixels that differ sharply from their right neighbour (geometry edges)
diff=np.abs(np.diff(z,axis=1))
print("edge pixels (dz>0.3m): %.4f"%(diff>0.3).mean())
