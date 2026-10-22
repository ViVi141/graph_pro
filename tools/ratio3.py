
from PIL import Image
import numpy as np
shots = {
 "1.00 (原值)": r"C:\Users\74738\.dsh\attachments\v1\objects\6a\6a7fb4f0b30eefca60dc4dfb2f0047bda42194a78b36d82c0fb5ed18ecca1683",
 "0.60/0.80":    r"C:\Users\74738\.dsh\attachments\v1\objects\9c\9cda81ac89d36daa4f2ef9d15aef2310eaa8b24367a6c2e980dcf7a7e34b1edd",
 "0.45/0.70":    r"C:\Users\74738\.dsh\attachments\v1\objects\d0\d028f1c6dbf2e1738c7d18d41da4a8a4ad477c9f6d46ac45716fc79c9f47eb67",
}
def lum(p, box):
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)/255
    x0,y0,x1,y1 = box
    z = a[y0:y1, x0:x1]
    l = 0.2126*z[...,0]+0.7152*z[...,1]+0.0722*z[...,2]
    return float(l.mean()), float(np.percentile(l,95)), float(l.std()*255)
for tag,p in shots.items():
    door = lum(p,(945,235,995,275))
    wall = lum(p,(380,330,600,430))
    floor = lum(p,(500,850,800,1000))
    print(f"{tag:12s} door={door[0]:.3f}/{door[1]:.3f}  wall={wall[0]:.3f} (σ{wall[2]:.0f})  floor={floor[0]:.3f} (σ{floor[2]:.0f})  ratio={door[0]/max(wall[0],1e-3):.2f}")
