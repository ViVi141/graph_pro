import numpy as np
from PIL import Image
p = r"D:\SteamLibrary\steamapps\common\Arma 3\GP_depth.raw"
OUT = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo"
W, H = 1920, 1080
raw = np.fromfile(p, dtype=np.uint32).reshape(H, W)
d = (raw & 0xFFFFFF).astype(np.float32) / 16777216.0
NEAR = 0.1; K = 600.0
z = NEAR / np.maximum(1.0 - d, 1e-7)
ux = ((np.arange(W)+0.5)/W*2-1).astype(np.float32)
uy = (1.0-(np.arange(H)+0.5)/H*2).astype(np.float32)
PX = ux[None,:]*z*(W/2.0)/K; PY = uy[:,None]*z*(H/2.0)/K; PZ = z
dPx = np.dstack([np.gradient(PX,axis=1), np.gradient(PY,axis=1), np.gradient(PZ,axis=1)])
dPy = np.dstack([np.gradient(PX,axis=0), np.gradient(PY,axis=0), np.gradient(PZ,axis=0)])
N = np.cross(dPx,dPy); N /= np.maximum(np.linalg.norm(N,axis=2,keepdims=True),1e-9)
N[(N[:,:,0]*PX+N[:,:,1]*PY+N[:,:,2]*PZ)>0] *= -1.0
ys, xs = np.mgrid[0:H,0:W]
rng = np.random.default_rng(1); rot = rng.random((H,W),dtype=np.float32)*6.2831853

def ao_map(radM, dirs=6, steps=4):
    pixR = np.clip(radM*K/z, 0.0, 64.0)
    active = (z<=3000.0)&(pixR>=1.0)&(d<0.999999)
    total = np.zeros((H,W),np.float32)
    for a in range(dirs):
        ang = rot + a*(6.2831853/dirs); ca,sa = np.cos(ang), np.sin(ang)
        best = np.zeros((H,W),np.float32)
        for s in range(1,steps+1):
            t = s*0.25
            xi = np.clip(xs+np.rint(ca*pixR*t).astype(np.int32),0,W-1)
            yi = np.clip(ys+np.rint(sa*pixR*t).astype(np.int32),0,H-1)
            VX = PX[yi,xi]-PX; VY = PY[yi,xi]-PY; VZ = z[yi,xi]-PZ
            L = np.sqrt(VX*VX+VY*VY+VZ*VZ)
            ok = (L>1e-5)&(L<radM)
            inv = np.where(ok,1.0/np.maximum(L,1e-9),0.0)
            cosA = (N[:,:,0]*VX+N[:,:,1]*VY+N[:,:,2]*VZ)*inv
            best = np.maximum(best, np.where(ok, np.clip(cosA,0,1)*(1.0-t), 0))
        total += best
    return np.where(active, np.clip(1.0-total/dirs,0,1), 1.0)

for rad in [1.5, 3.0, 6.0]:
    ao = ao_map(rad)
    Image.fromarray((ao*255).astype(np.uint8)).save(OUT + r"\ao-n-%.1f.png" % rad)
    print("rad %.1f mean %.4f p5 %.3f frac<0.95 %.3f frac<0.8 %.3f" %
          (rad, ao.mean(), np.percentile(ao,5), (ao<0.95).mean(), (ao<0.8).mean()))
