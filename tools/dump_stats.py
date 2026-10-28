import numpy as np, struct
p = r"<ARMA3>\GP_depth.raw"
W, H = 1920, 1080
raw = np.fromfile(p, dtype=np.uint32).reshape(H, W)
d = (raw & 0xFFFFFF).astype(np.float32) / 16777216.0
print("shape", d.shape, "min %.6f max %.6f mean %.6f" % (d.min(), d.max(), d.mean()))
for name, sl in [("top 10%", slice(0, 108)), ("top 25%", slice(0, 270)), ("mid", slice(400, 700)), ("bottom 20%", slice(864, 1080))]:
    s = d[sl]
    print("%-10s min %.6f  max %.6f  mean %.6f  frac==1 %.3f" % (name, s.min(), s.max(), s.mean(), (s >= 0.999999).mean()))
NEAR = 0.1
z = NEAR / np.maximum(1.0 - d, 1e-7)
for name, sl in [("top 10%", slice(0, 108)), ("mid", slice(400, 700)), ("bottom 20%", slice(864, 1080))]:
    s = z[sl]
    print("%-10s z(m) p5 %.1f  p50 %.1f  p95 %.1f" % (name, np.percentile(s,5), np.percentile(s,50), np.percentile(s,95)))
