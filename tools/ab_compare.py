import numpy as np
from PIL import Image, ImageDraw

D = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo"
A = Image.open(D + r"\ab-vanilla-baseline.png").convert("RGB")
B = Image.open(D + r"\ab-injected-baseline.png").convert("RGB")
print("sizes:", A.size, B.size)
a = np.asarray(A).astype(np.float32)
b = np.asarray(B).astype(np.float32)
H, W = a.shape[:2]

def lum(x): return 0.2126*x[:,:,0] + 0.7152*x[:,:,1] + 0.0722*x[:,:,2]

# alignment check on a central crop
best = None
for dy in range(-6, 7, 1):
    for dx in range(-6, 7, 1):
        y0, y1, x0, x1 = 200, H-200, 300, W-300
        d = np.abs(a[y0:y1, x0:x1] - b[y0+dy:y1+dy, x0+dx:x1+dx]).mean()
        if best is None or d < best[0]: best = (d, dx, dy)
print("best alignment: mean-abs-diff %.3f at dx=%d dy=%d" % best)

def laplacian_var(g):
    k = np.array([[0,1,0],[1,-4,1],[0,1,0]], np.float32)
    from numpy.lib.stride_tricks import sliding_window_view
    w = sliding_window_view(g, (3,3))
    return float((w*k).sum(axis=(2,3)).var())

La, Lb = lum(a)/255.0, lum(b)/255.0
def stats(L, name):
    dark = L < 0.10
    print("%-10s mean %.4f  std %.4f  sharp %.4f  dark%% %.1f" %
          (name, L.mean(), L.std(), laplacian_var(L), 100*dark.mean()))
    return L.mean(), L.std(), 100*dark.mean()
stats(La, "vanilla")
stats(Lb, "injected")

def color_at(L, img, lo, hi, name):
    m = (L >= lo) & (L < hi)
    if m.sum() < 1000: print("  %-10s too few px" % name); return
    px = img[m]
    rb = px[:,0].mean() - px[:,2].mean()
    print("  %-10s px %7d  R %.1f G %.1f B %.1f  R-B %+.2f" %
          (name, m.sum(), px[:,0].mean(), px[:,1].mean(), px[:,2].mean(), rb/255.0))
print("vanilla tones:")
color_at(La, a, 0.0, 0.15, "shadows"); color_at(La, a, 0.3, 0.6, "midtones"); color_at(La, a, 0.75, 1.01, "high")
print("injected tones:")
color_at(Lb, b, 0.0, 0.15, "shadows"); color_at(Lb, b, 0.3, 0.6, "midtones"); color_at(Lb, b, 0.75, 1.01, "high")

# side by side, half size
small = lambda im: im.resize((W//2, H//2), Image.LANCZOS)
row = Image.new("RGB", (W, H//2 + 30), (20,20,20))
row.paste(small(A), (0, 30)); row.paste(small(B), (W//2, 30))
dr = ImageDraw.Draw(row)
dr.text((10, 8), "VANILLA (no injection)", fill=(255,255,255))
dr.text((W//2 + 10, 8), "CURRENT BEST (injection on)", fill=(255,255,255))
row.save(D + r"\ab-side-by-side.png")
print("wrote ab-side-by-side.png")

# difference map
d = np.abs(b - a).mean(axis=2)
Image.fromarray(np.clip(d*6, 0, 255).astype(np.uint8)).resize((W//2, H//2)).save(D + r"\ab-diff.png")
print("diff: mean %.3f  frac>3 %.4f  max %.0f" % (d.mean(), (d>3).mean(), d.max()))
