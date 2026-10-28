
from PIL import Image
import numpy as np
old = r"<USERPROFILE>\.dsh\attachments\v1\objects\6a\6a7fb4f0b30eefca60dc4dfb2f0047bda42194a78b36d82c0fb5ed18ecca1683"
new = r"<USERPROFILE>\.dsh\attachments\v1\objects\9c\9cda81ac89d36daa4f2ef9d15aef2310eaa8b24367a6c2e980dcf7a7e34b1edd"
def lum(p, box):
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)/255
    x0,y0,x1,y1 = box
    z = a[y0:y1, x0:x1]
    l = 0.2126*z[...,0]+0.7152*z[...,1]+0.0722*z[...,2]
    return float(l.mean()), float(np.percentile(l,95))
# doorway bright patch (approx same in both)
for tag,p in [("before",old),("after",new)]:
    win_b, win_p = lum(p,(945,235,995,275))   # 门外亮地面
    wall_b, wall_p = lum(p,(380,330,600,430)) # 室内墙
    print(f"{tag}: door mean={win_b:.3f} p95={win_p:.3f} | wall mean={wall_b:.3f} p95={wall_p:.3f} | ratio={win_b/max(wall_b,1e-3):.2f}")
