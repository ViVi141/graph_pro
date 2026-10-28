import numpy as np
from PIL import Image

p = r"<ARMA3>\GP_depth.raw"
OUT = r"<REPO>\demo"
W, H = 1920, 1080
raw = np.fromfile(p, dtype=np.uint32).reshape(H, W)
d = (raw & 0xFFFFFF).astype(np.float32) / 16777216.0
NEAR = 0.1

def ao_map(radM, K, dirs=6, steps=4, seed=0):
    z0 = NEAR / np.maximum(1.0 - d, 1e-7)
    pixR = radM * K / z0
    active = (z0 <= 3000.0) & (pixR >= 1.5)
    pixR = np.clip(pixR, 0.0, 48.0)
    mpp = z0 / K
    ys, xs = np.mgrid[0:H, 0:W]
    rng = np.random.default_rng(seed)
    rot = rng.random((H, W), dtype=np.float32) * 6.2831853
    total = np.zeros((H, W), np.float32)
    for a in range(dirs):
        ang = rot + a * (6.2831853 / dirs)
        ca, sa = np.cos(ang), np.sin(ang)
        best = np.zeros((H, W), np.float32)
        for s in range(1, steps + 1):
            t = s * 0.25
            dx = np.rint(ca * pixR * t).astype(np.int32)
            dy = np.rint(sa * pixR * t).astype(np.int32)
            xi = np.clip(xs + dx, 0, W - 1)
            yi = np.clip(ys + dy, 0, H - 1)
            d1 = d[yi, xi]
            z1 = NEAR / np.maximum(1.0 - d1, 1e-7)
            dz = z0 - z1
            horiz = np.maximum(pixR * t * mpp, 1e-4)
            ok = (dz > 0) & (dz * dz + horiz * horiz <= radM * radM * 4.0)
            v = np.where(ok, np.clip((dz / horiz) * 0.5, 0, 1), 0).astype(np.float32)
            best = np.maximum(best, v)
        total += best
    ao = np.clip(1.0 - total / dirs, 0, 1)
    ao = np.where(active, ao, 1.0)
    return ao

for rad, K in [(0.30, 600.0), (0.15, 600.0), (0.30, 300.0)]:
    ao = ao_map(rad, K)
    img = (np.clip(ao, 0, 1) * 255).astype(np.uint8)
    Image.fromarray(img).save(OUT + r"\ao-offline-%.2f-%.0f.png" % (rad, K))
    dark = (ao < 0.95).mean()
    print("rad %.2f K %.0f : mean %.4f  p1 %.3f  p50 %.3f  frac<0.95 %.4f  frac<0.5 %.4f" %
          (rad, K, ao.mean(), np.percentile(ao, 1), np.percentile(ao, 50), dark, (ao < 0.5).mean()))
