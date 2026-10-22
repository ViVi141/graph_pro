import numpy as np
p = r"D:\SteamLibrary\steamapps\common\Arma 3\GP_depth.raw"
W,H=1920,1080
raw=np.fromfile(p,dtype=np.uint32).reshape(H,W)
d=(raw&0xFFFFFF).astype(np.float32)/16777216.0
NEAR=0.1;K=600.0
z=NEAR/np.maximum(1.0-d,1e-7)
ux=((np.arange(W)+0.5)/W*2-1).astype(np.float32)
uy=(1.0-(np.arange(H)+0.5)/H*2).astype(np.float32)
PX=ux[None,:]*z*(W/2.0)/K; PY=uy[:,None]*z*(H/2.0)/K; PZ=z
dPx=np.dstack([np.gradient(PX,axis=1),np.gradient(PY,axis=1),np.gradient(PZ,axis=1)])
dPy=np.dstack([np.gradient(PX,axis=0),np.gradient(PY,axis=0),np.gradient(PZ,axis=0)])
N=np.cross(dPx,dPy); N/=np.maximum(np.linalg.norm(N,axis=2,keepdims=True),1e-9)
N[(N[:,:,0]*PX+N[:,:,1]*PY+N[:,:,2]*PZ)>0]*=-1.0
ys,xs=np.mgrid[0:H,0:W]
radM=6.0
pixR=np.clip(radM*K/z,0.0,64.0)
best_all=np.zeros((H,W),np.float32); okc=np.zeros((H,W),np.int32)
for a in range(12):
    ang=a*(6.2831853/12); ca,sa=np.cos(ang),np.sin(ang)
    for s in range(1,5):
        t=s*0.25
        xi=np.clip(xs+np.rint(ca*pixR*t).astype(np.int32),0,W-1)
        yi=np.clip(ys+np.rint(sa*pixR*t).astype(np.int32),0,H-1)
        VX=PX[yi,xi]-PX; VY=PY[yi,xi]-PY; VZ=z[yi,xi]-PZ
        L=np.sqrt(VX*VX+VY*VY+VZ*VZ)
        ok=(L>1e-5)&(L<radM)
        inv=np.where(ok,1.0/np.maximum(L,1e-9),0.0)
        cosA=(N[:,:,0]*VX+N[:,:,1]*VY+N[:,:,2]*VZ)*inv
        best_all=np.maximum(best_all,np.where(ok,cosA,-9))
        okc+=ok
print("valid samples per pixel: mean %.1f" % okc.mean())
print("max cosA over image: %.4f" % best_all.max())
print("frac pixels with cosA>0.1: %.4f   >0.3: %.4f" % ((best_all>0.1).mean(),(best_all>0.3).mean()))
print("N components mean abs: %.3f %.3f %.3f"% (np.abs(N[:,:,0]).mean(),np.abs(N[:,:,1]).mean(),np.abs(N[:,:,2]).mean()))
