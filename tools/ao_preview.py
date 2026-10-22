import sys, numpy as np
from PIL import Image

GAME = r"D:\SteamLibrary\steamapps\common\Arma 3"
OUT = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo"
W, H = 1920, 1080
NEAR = 0.1

def load(frame):
    d = (np.fromfile(GAME + r"\GP_depth_%d.raw" % frame, dtype=np.uint32).reshape(H, W) & 0xFFFFFF).astype(np.float32) / 16777216.0
    c = np.fromfile(GAME + r"\GP_color_%d.raw" % frame, dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.float32) / 255.0
    return d, c

def geometry(d, K):
    z = NEAR / np.maximum(1.0 - d, 1e-7)
    ux = ((np.arange(W) + 0.5) / W * 2 - 1).astype(np.float32)
    uy = (1.0 - (np.arange(H) + 0.5) / H * 2).astype(np.float32)
    PX = ux[None, :] * z * (W / 2.0) / K
    PY = uy[:, None] * z * (H / 2.0) / K
    dPx = np.dstack([np.gradient(PX, axis=1), np.gradient(PY, axis=1), np.gradient(z, axis=1)])
    dPy = np.dstack([np.gradient(PX, axis=0), np.gradient(PY, axis=0), np.gradient(z, axis=0)])
    N = np.cross(dPx, dPy)
    N /= np.maximum(np.linalg.norm(N, axis=2, keepdims=True), 1e-9)
    N[(N[:, :, 0] * PX + N[:, :, 1] * PY + N[:, :, 2] * z) > 0] *= -1.0
    return z, PX, PY, N

def ao_map(d, z, PX, PY, N, radM, K, dirs=8, steps=4, seed=1):
    pixR = np.clip(radM * K / z, 0.0, 64.0)
    active = (z <= 3000.0) & (pixR >= 1.0) & (d < 0.999999)
    ys, xs = np.mgrid[0:H, 0:W]
    rot = np.random.default_rng(seed).random((H, W), dtype=np.float32) * 6.2831853
    total = np.zeros((H, W), np.float32)
    for a in range(dirs):
        ang = rot + a * (6.2831853 / dirs)
        ca, sa = np.cos(ang), np.sin(ang)
        best = np.zeros((H, W), np.float32)
        for s in range(1, steps + 1):
            t = s * 0.25
            xi = np.clip(xs + np.rint(ca * pixR * t).astype(np.int32), 0, W - 1)
            yi = np.clip(ys + np.rint(sa * pixR * t).astype(np.int32), 0, H - 1)
            VX = PX[yi, xi] - PX; VY = PY[yi, xi] - PY; VZ = z[yi, xi] - z
            L = np.sqrt(VX * VX + VY * VY + VZ * VZ)
            ok = (L > 1e-5) & (L < radM)
            inv = np.where(ok, 1.0 / np.maximum(L, 1e-9), 0.0)
            cosA = (N[:, :, 0] * VX + N[:, :, 1] * VY + N[:, :, 2] * VZ) * inv
            best = np.maximum(best, np.where(ok, np.clip(cosA, 0, 1) * (1.0 - t), 0))
        total += best
    return np.where(active, np.clip(1.0 - total / dirs, 0, 1), 1.0)

if __name__ == "__main__":
    frame = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    K = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0
    d, c = load(frame)
    z, PX, PY, N = geometry(d, K)
    tiles = []
    for rad in [0.5, 1.5, 4.0]:
        ao = ao_map(d, z, PX, PY, N, rad, K)
        aov = (ao * 255).astype(np.uint8)
        comp = np.clip(c * (1.0 - (1.0 - ao[..., None]) * 0.75), 0, 1)
        tiles.append(np.concatenate([np.repeat(aov[..., None], 3, axis=2), (comp * 255).astype(np.uint8)], axis=1))
        print("rad %.1f: mean %.4f  frac<0.95 %.3f  frac<0.8 %.3f" % (rad, ao.mean(), (ao < 0.95).mean(), (ao < 0.8).mean()))
    row = np.concatenate(tiles, axis=0)
    Image.fromarray(row).resize((row.shape[1] // 3, row.shape[0] // 3)).save(OUT + r"\ao-preview-%d.png" % frame)
    print("wrote ao-preview-%d.png" % frame)
