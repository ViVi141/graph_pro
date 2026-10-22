import numpy as np
from PIL import Image, ImageDraw
D = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo"
A = Image.open(D + r"\ab-vanilla-baseline.png").convert("RGB")
B = Image.open(D + r"\ab-injected-baseline.png").convert("RGB")
a = np.asarray(A).astype(np.float32); b = np.asarray(B).astype(np.float32)
def lum(x): return (0.2126*x[:,:,0] + 0.7152*x[:,:,1] + 0.0722*x[:,:,2])/255.0
La, Lb = lum(a), lum(b)
for name, L in (("vanilla", La), ("injected", Lb)):
    print("%-9s clip_black %.4f  clip_white %.4f  p05 %.3f  p50 %.3f  p95 %.3f" %
          (name, (L < 0.004).mean(), (L > 0.996).mean(), np.percentile(L,5), np.percentile(L,50), np.percentile(L,95)))
# 1:1 crop of the facade + road edge
crop = (slice(120, 520), slice(620, 1220))
ca = A.crop((crop[1].start, crop[0].start, crop[1].stop, crop[0].stop))
cb = B.crop((crop[1].start, crop[0].start, crop[1].stop, crop[0].stop))
w, h = ca.size
out = Image.new("RGB", (w*2 + 12, h + 26), (18,18,18))
out.paste(ca, (0, 26)); out.paste(cb, (w + 12, 26))
dr = ImageDraw.Draw(out)
dr.text((6, 7), "VANILLA  1:1 crop", fill=(255,255,255))
dr.text((w + 18, 7), "INJECTED  1:1 crop", fill=(255,255,255))
out.save(D + r"\ab-crop-facade.png")
print("wrote ab-crop-facade.png", out.size)
