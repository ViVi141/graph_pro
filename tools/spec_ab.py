import numpy as np
from PIL import Image
g = r"<ARMA3>"
W, H = 1920, 1080
a = np.fromfile(g + r"\GP_shot_1.rgb", dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.int16)
b = np.fromfile(g + r"\GP_shot_2.rgb", dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.int16)
La = 0.2126*a[:,:,0] + 0.7152*a[:,:,1] + 0.0722*a[:,:,2]
Lb = 0.2126*b[:,:,0] + 0.7152*b[:,:,1] + 0.0722*b[:,:,2]
print("spec OFF : mean %.2f  max %.0f" % (La.mean(), La.max()))
print("spec ON  : mean %.2f  max %.0f" % (Lb.mean(), Lb.max()))
d = np.abs(b - a).max(axis=2)
dl = np.abs(Lb - La)
print("max channel diff: %d   mean abs diff: %.4f" % (d.max(), d.mean()))
print("pixels differing >1/255: %.4f   >3: %.4f   >8: %.4f" % ((d > 1).mean(), (d > 3).mean(), (d > 8).mean()))
print("luminance diff: mean %.4f  p99 %.1f  max %.0f" % (dl.mean(), np.percentile(dl, 99), dl.max()))
if d.max() > 2:
    ys, xs = np.where(d > 3)
    print("diff bbox: x %d..%d  y %d..%d  (%d px)" % (xs.min(), xs.max(), ys.min(), ys.max(), len(xs)))
    Image.fromarray(np.clip(d*8, 0, 255).astype(np.uint8)).resize((W//2, H//2)).save(r"<REPO>\demo\spec-diff.png")
    print("wrote demo/spec-diff.png (diff x8)")
