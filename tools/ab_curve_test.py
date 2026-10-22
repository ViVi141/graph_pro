import numpy as np
from PIL import Image
from numpy.lib.stride_tricks import sliding_window_view
D = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo"
a = np.asarray(Image.open(D + r"\ab-vanilla-baseline.png").convert("RGB")).astype(np.float32)
b = np.asarray(Image.open(D + r"\ab-injected-baseline.png").convert("RGB")).astype(np.float32)

print("=== per-channel transfer test (can one global curve explain it?) ===")
for ch, name in enumerate("RGB"):
    x = a[:,:,ch].ravel(); y = b[:,:,ch].ravel()
    idx = np.clip((x / 4.0).astype(np.int32), 0, 63)
    lut = np.zeros(64, np.float32); cnt = np.zeros(64, np.float32)
    np.add.at(lut, idx, y); np.add.at(cnt, idx, 1)
    lut = lut / np.maximum(cnt, 1)
    pred = lut[idx]
    resid = np.abs(pred - y)
    print("  %s: mean|resid| %.2f/255  p99 %.1f  frac>8: %.3f" %
          (name, resid.mean(), np.percentile(resid, 99), (resid > 8).mean()))

Lv = (0.2126*a[:,:,0] + 0.7152*a[:,:,1] + 0.0722*a[:,:,2]) / 255.0
Li = (0.2126*b[:,:,0] + 0.7152*b[:,:,1] + 0.0722*b[:,:,2]) / 255.0
v_clip = (a.max(axis=2) >= 254); i_clip = (b.max(axis=2) >= 254)
print("\n=== clipping ===")
print("  vanilla blown px %.4f   injected blown px %.4f" % (v_clip.mean(), i_clip.mean()))
print("  detail recovered where vanilla was blown (Li < Lv-0.02): %.4f" % (v_clip & ~i_clip & (Li < Lv - 0.02)).mean())
print("  newly blown by us: %.4f" % (i_clip & ~v_clip).mean())

def local_std(L, m):
    pad = np.pad(L, 7, mode="edge"); w = sliding_window_view(pad, (15,15))
    s = w.std(axis=(2,3))[m]; return float(s.mean()) if s.size else 0.0
m = Lv < 0.25
print("\n=== shadow local contrast (15x15 std, L<0.25) ===")
print("  vanilla %.4f   injected %.4f" % (local_std(Lv, m), local_std(Li, m)))
m2 = Lv > 0.75
print("=== highlight local contrast (L>0.75) ===")
print("  vanilla %.4f   injected %.4f" % (local_std(Lv, m2), local_std(Li, m2)))
