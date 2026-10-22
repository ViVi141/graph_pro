
from PIL import Image
import numpy as np
shots = {
 "原值": r"C:\Users\74738\.dsh\attachments\v1\objects\6a\6a7fb4f0b30eefca60dc4dfb2f0047bda42194a78b36d82c0fb5ed18ecca1683",
 "0.6 无冷色": r"C:\Users\74738\.dsh\attachments\v1\objects\9c\9cda81ac89d36daa4f2ef9d15aef2310eaa8b24367a6c2e980dcf7a7e34b1edd",
 "0.6 + 冷色": r"C:\Users\74738\.dsh\attachments\v1\objects\cc\cc06f1f421cb62a788c817d77990ea78e22c0da4b0bdeabe322937fd48d59395",
}
def stat(p, box):
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)/255
    x0,y0,x1,y1 = box
    z = a[y0:y1, x0:x1]
    l = 0.2126*z[...,0]+0.7152*z[...,1]+0.0722*z[...,2]
    return l.mean(), (z[...,0]-z[...,2]).mean(), (z.max(axis=2)-z.min(axis=2)).mean()
for tag,p in shots.items():
    w = stat(p,(380,330,600,430))   # 室内墙（阴影）
    d = stat(p,(790,240,850,280))   # 门外亮部
    print(f"{tag:10s} 墙 luma={w[0]:.3f} R-B={w[1]:+.4f} sat={w[2]:.3f} | 门外 luma={d[0]:.3f} R-B={d[1]:+.4f}")
