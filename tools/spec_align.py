import numpy as np
g = r"D:\SteamLibrary\steamapps\common\Arma 3"
W, H = 1920, 1080
a = np.fromfile(g + r"\GP_shot_1.rgb", dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.float32)
b = np.fromfile(g + r"\GP_shot_2.rgb", dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.float32)
# central crop, away from the UI panels
y0, y1, x0, x1 = 200, 900, 400, 1700
best = None
for dy in range(-4, 5):
    for dx in range(-4, 5):
        A = a[y0:y1, x0:x1]
        B = b[y0+dy:y1+dy, x0+dx:x1+dx]
        d = np.abs(A - B).mean()
        if best is None or d < best[0]:
            best = (d, dx, dy)
print("best mean-abs-diff %.4f at shift dx=%d dy=%d" % best)
print("diff at zero shift %.4f" % np.abs(a[y0:y1, x0:x1] - b[y0:y1, x0:x1]).mean())
# how much of the diff is explained by a pure gain (exposure) change?
A = a[y0:y1, x0:x1]; B = b[y0:y1, x0:x1]
ratio = (B.mean() / max(A.mean(), 1e-6))
print("mean A %.3f  mean B %.3f  ratio %.4f" % (A.mean(), B.mean(), ratio))
print("diff after removing global gain: %.4f" % np.abs(A*ratio - B).mean())
