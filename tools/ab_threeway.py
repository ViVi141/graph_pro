import numpy as np
from PIL import Image, ImageDraw
from numpy.lib.stride_tricks import sliding_window_view
D = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo"
names = [("原版", "ab-cc-baseline.png"),
         ("原版+游戏调色", "ab-cc-cold_highContrast.png"),
         ("我们的注入", "ab-injected-baseline.png")]
imgs = {n: Image.open(D + "\\" + f).convert("RGB") for n, f in names}
base = np.asarray(imgs["原版"]).astype(np.float32)

def L(x): return (0.2126*x[:,:,0] + 0.7152*x[:,:,1] + 0.0722*x[:,:,2]) / 255.0
def sharp(g):
    k = np.array([[0,1,0],[1,-4,1],[0,1,0]], np.float32)
    w = sliding_window_view(g, (3,3)); return float((w*k).sum(axis=(2,3)).var())
def sat(x):
    mx = x.max(axis=2); mn = x.min(axis=2)
    return float(((mx-mn) / np.maximum(mx, 1)).mean())

print("%-14s %7s %7s %8s %7s %7s %7s %7s %7s" % ("", "mean", "std", "sharp", "dark%", "p05", "p95", "sat", "blown%"))
rows = {}
for n, f in names:
    x = np.asarray(imgs[n]).astype(np.float32); l = L(x)
    d = dict(mean=l.mean(), std=l.std(), sharp=sharp(l), dark=100*(l<0.10).mean(),
             p05=np.percentile(l,5), p95=np.percentile(l,95), sat=sat(x/255.0),
             blown=100*(x.max(axis=2)>=254).mean())
    rows[n] = d
    print("%-14s %7.4f %7.4f %8.4f %6.1f%% %7.3f %7.3f %7.3f %6.2f%%" %
          (n, d["mean"], d["std"], d["sharp"], d["dark"], d["p05"], d["p95"], d["sat"], d["blown"]))

# distance from each to our injected frame, restricted to fit of mean/std
tgt = np.asarray(imgs["我们的注入"]).astype(np.float32)
print("\n与“我们的注入”的差距（整帧平均绝对差 / 255）:")
for n, f in names[:2]:
    x = np.asarray(imgs[n]).astype(np.float32)
    print("  %-14s %.2f" % (n, np.abs(x - tgt).mean()))

# 3-panel image
w, h = imgs["原版"].size
scale = 2
panel = Image.new("RGB", (w//scale*3 + 24, h//scale + 26), (18,18,18))
dr = ImageDraw.Draw(panel)
for i, (n, f) in enumerate(names):
    panel.paste(imgs[n].resize((w//scale, h//scale), Image.LANCZOS), (i*(w//scale+12), 26))
    dr.text((i*(w//scale+12) + 6, 7), n, fill=(255,255,255))
panel.save(D + r"\ab-three-way.png")
print("\nwrote ab-three-way.png", panel.size)
