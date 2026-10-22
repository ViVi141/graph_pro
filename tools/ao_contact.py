import numpy as np
from PIL import Image
GAME = r"D:\SteamLibrary\steamapps\common\Arma 3"
OUT = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo"
W,H = 1920,1080
d = (np.fromfile(GAME+r"\GP_depth_1200.raw",dtype=np.uint32).reshape(H,W)&0xFFFFFF).astype(np.float32)/16777216.0
c = np.fromfile(GAME+r"\GP_color_1200.raw",dtype=np.uint8).reshape(H,W,4)[:,:,:3].astype(np.float32)/255.0
NEAR=0.1; K=600.0
z = NEAR/np.maximum(1.0-d,1e-7)
ux=((np.arange(W)+0.5)/W*2-1).astype(np.float32)
uy=(1.0-(np.arange(H)+0.5)/H*2).astype(np.float32)
PX=ux[None,:]*z*(W/2.0)/K; PY=uy[:,None]*z*(H/2.0)/K; PZ=z
dPx=np.dstack([np.gradient(PX,axis=1),np.gradient(PY,axis=1),np.gradient(PZ,axis=1)])
dPy=np.dstack([np.gradient(PX,axis=0),np.gradient(PY,axis=0),np.gradient(PZ,axis=0)])
N=np.cross(dPx,dPy); N/=np.maximum(np.linalg.norm(N,axis=2,keepdims=True),1e-9)
N[(N[:,:,0]*PX+N[:,:,1]*PY+N[:,:,2]*PZ)>0]*=-1.0
ys,xs=np.mgrid[0:H,0:W]
rot=np.random.default_rng(3).random((H,W),dtype=np.float32)*6.2831853
def occ(radM, dirs=10, steps=5):
    pixR=np.clip(radM*K/z,0.0,80.0)
    active=(z<=3000.0)&(pixR>=1.0)&(d<0.999999)
    total=np.zeros((H,W),np.float32)
    for a in range(dirs):
        ang=rot+a*(6.2831853/dirs); ca,sa=np.cos(ang),np.sin(ang)
        best=np.zeros((H,W),np.float32)
        for s in range(1,steps+1):
            t=s/float(steps)
            xi=np.clip(xs+np.rint(ca*pixR*t).astype(np.int32),0,W-1)
            yi=np.clip(ys+np.rint(sa*pixR*t).astype(np.int32),0,H-1)
            VX=PX[yi,xi]-PX; VY=PY[yi,xi]-PY; VZ=z[yi,xi]-PZ
            L=np.sqrt(VX*VX+VY*VY+VZ*VZ)
            ok=(L>1e-5)&(L<radM)
            inv=np.where(ok,1.0/np.maximum(L,1e-9),0.0)
            cosA=(N[:,:,0]*VX+N[:,:,1]*VY+N[:,:,2]*VZ)*inv
            best=np.maximum(best,np.where(ok,np.clip(cosA,0,1)*(1.0-t),0))
        total+=best
    o=np.clip(total/dirs,0,1)
    return np.where(active,o,0.0)
o_small=occ(0.8); o_large=occ(4.0)
contact=np.clip(o_small-o_large*0.9,0,1)
print("o_small mean %.3f  o_large mean %.3f  contact mean %.4f  frac>0.05 %.3f"%(o_small.mean(),o_large.mean(),contact.mean(),(contact>0.05).mean()))
crop=(slice(560,860), slice(700,1300))
rows=[(c*255).astype(np.uint8)[crop]]
for gain in [1.5, 2.5, 4.0]:
    img=np.clip(c*(1.0-np.clip(contact*gain,0,0.75)[...,None]),0,1)
    rows.append((img*255).astype(np.uint8)[crop])
Image.fromarray(np.concatenate(rows,axis=0)).save(OUT+r"\ao-contact.png")
Image.fromarray((np.clip(contact*8,0,1)*255).astype(np.uint8)).save(OUT+r"\ao-contact-map.png")
print("wrote ao-contact.png rows: orig / gain1.5 / gain2.5 / gain4.0")
