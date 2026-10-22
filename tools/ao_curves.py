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
radM=1.5; dirs=12; steps=5
pixR=np.clip(radM*K/z,0.0,64.0)
active=(z<=3000.0)&(pixR>=1.0)&(d<0.999999)
rot=np.random.default_rng(3).random((H,W),dtype=np.float32)*6.2831853
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
ao=np.where(active,np.clip(1.0-total/dirs,0,1),1.0)
np.save(r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\ao1200.npy",ao)

def box(a,r):
    k=np.ones((2*r+1,2*r+1),np.float32); k/=k.sum()
    from numpy.lib.stride_tricks import sliding_window_view
    pad=np.pad(a,r,mode="edge")
    return sliding_window_view(pad,(2*r+1,2*r+1)).__mul__(k).sum(axis=(2,3))
aob=box(ao,2)
crop=(slice(560,860), slice(700,1300))
rows=[]
for name,a,s in [("original",None,0),("blur, ^1, s=1.0",aob,1.0),("blur, ^2, s=1.0",aob,2.0),("blur, ^3, s=1.0",aob,3.0)]:
    img  = c if a is None else np.clip(c*(1.0-(1.0-a[...,None]**s)),0,1)
    row  = (img*255).astype(np.uint8)[crop]
    rows.append(row)
Image.fromarray(np.concatenate(rows,axis=0)).save(OUT+r"\ao-curve-compare.png")
print("rows: original / ^1 / ^2 / ^3 ; crop 600x300 each")
