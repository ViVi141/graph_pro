import numpy as np
g = r"D:\SteamLibrary\steamapps\common\Arma 3"
W, H = 1920, 1080
a = np.fromfile(g + r"\GP_shot_1.rgb", dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.float32)
b = np.fromfile(g + r"\GP_shot_2.rgb", dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.float32)
d = np.abs(b - a).mean(axis=2)
regions = {
    "sky (top)":        (slice(150, 200), slice(600, 1400)),
    "containers":       (slice(430, 660), slice(560, 1080)),
    "road / open dirt": (slice(330, 400), slice(900, 1400)),
    "grass foliage":    (slice(880, 1040), slice(600, 1500)),
    "stone wall":       (slice(700, 760), slice(500, 900)),
}
for name, (sy, sx) in regions.items():
    r = d[sy, sx]
    print("%-18s mean %.3f  p99 %.1f  max %.0f  frac>3: %.3f" % (name, r.mean(), np.percentile(r, 99), r.max(), (r > 3).mean()))
