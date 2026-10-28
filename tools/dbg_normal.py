import numpy as np
p = r"<ARMA3>\GP_depth.raw"
W,H = 1920,1080
raw = np.fromfile(p, dtype=np.uint32).reshape(H,W)
d = (raw & 0xFFFFFF).astype(np.float32)/16777216.0
NEAR=0.1; K=600.0
z = NEAR/np.maximum(1.0-d,1e-7)
ux=((np.arange(W)+0.5)/W*2-1).astype(np.float32)
uy=(1.0-(np.arange(H)+0.5)/H*2).astype(np.float32)
PX=ux[None,:]*z*(W/2.0)/K; PY=uy[:,None]*z*(H/2.0)/K; PZ=z
dPx=np.dstack([np.gradient(PX,axis=1),np.gradient(PY,axis=1),np.gradient(PZ,axis=1)])
dPy=np.dstack([np.gradient(PX,axis=0),np.gradient(PY,axis=0),np.gradient(PZ,axis=0)])
N=np.cross(dPx,dPy); N/=np.maximum(np.linalg.norm(N,axis=2,keepdims=True),1e-9)
N[(N[:,:,0]*PX+N[:,:,1]*PY+N[:,:,2]*PZ)>0]*=-1.0
for (yy,xx) in [(1000,960),(700,960),(560,960)]:
    print("pixel row=%d col=%d  z=%.1f  N=(%.3f,%.3f,%.3f)"%(yy,xx,z[yy,xx],N[yy,xx,0],N[yy,xx,1],N[yy,xx,2]))
    for name,dy,dx in [("down",40,0),("up",-40,0),("right",0,40),("left",0,-40)]:
        y1=min(max(yy+dy,0),H-1); x1=min(max(xx+dx,0),W-1)
        VX=PX[y1,x1]-PX[yy,xx]; VY=PY[y1,x1]-PY[yy,xx]; VZ=z[y1,x1]-z[yy,xx]
        L=(VX*VX+VY*VY+VZ*VZ)**0.5
        cosA=(N[yy,xx,0]*VX+N[yy,xx,1]*VY+N[yy,xx,2]*VZ)/max(L,1e-9)
        print("   %-5s L=%7.3f  cosA=%+.3f  VZ=%7.3f"%(name,L,cosA,VZ))
