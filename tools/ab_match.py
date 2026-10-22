import numpy as np
from PIL import Image, ImageDraw
from numpy.lib.stride_tricks import sliding_window_view
D = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo"
sets = [("VANILLA", "ab-match-baseline.png"),
        ("VANILLA+CC(match)", "ab-cc-match.png"),
        ("OURS(injection)", "ab-injected-baseline.png")]
def L(x): return (0.2126*x[:,:,0] + 0.7152*x[:,:,1] + 0.0722*x[:,:,2]) / 255.0
def sharp(g):
    k = np.array([[0,1,0],[1,-4,1],[0,1,0]], np.float32)
    w = sliding_window_view(g, (3,3)); return float((w*k).sum(axis=(2,3)).var())
def sat(x):
    mx = x.max(axis=2); mn = x.min(axis=2); return float(((mx-mn)/np.maximum(mx,1)).mean())
rows = []
print("%-18s %7s %7s %8s %6s %7s %7s %8s" % ("", "mean", "std", "sharp", "dark%", "p05", "sat", "blown%"))
for name, f in sets:
    x = np.asarray(Image.open(D + "\\" + f).convert("RGB")).astype(np.float32)
    l = L(x); s = sat(x/255.0)
    d = dict(name=name, mean=l.mean(), std=l.std(), sharp=sharp(l), dark=100*(l<0.10).mean(),
             p05=np.percentile(l,5), sat=s, blown=100*(x.max(axis=2)>=254).mean())
    rows.append(d)
    print("%-18s %7.4f %7.4f %8.4f %5.1f%% %7.3f %7.3f %7.2f%%" %
          (name, d["mean"], d["std"], d["sharp"], d["dark"], d["p05"], d["sat"], d["blown"]))
tgt = rows[-1]
print("\n距离目标（我们）:")
for r in rows[:-1]:
    err = [abs(r[k]-tgt[k])/max(abs(tgt[k]),1e-6)*100 for k in ("mean","std","sharp","sat")]
    print("  %-18s mean %+5.1f%%  std %+5.1f%%  sharp %+5.1f%%  sat %+5.1f%%  综合 %.1f%%" %
          (r["name"], *[ (r[k]-tgt[k])/max(abs(tgt[k]),1e-6)*100 for k in ("mean","std","sharp","sat")],
           np.mean(err)))
# 3-panel
ims = [Image.open(D + "\\" + f).convert("RGB") for _, f in sets]
w, h = ims[0].size; sc = 2
panel = Image.new("RGB", (w//sc*3 + 24, h//sc + 26), (18,18,18)); dr = ImageDraw.Draw(panel)
for i, (n, _) in enumerate(sets):
    panel.paste(ims[i].resize((w//sc, h//sc), Image.LANCZOS), (i*(w//sc+12), 26))
    dr.text((i*(w//sc+12)+6, 7), n, fill=(255,255,255))
panel.save(D + r"\ab-match-compare.png")
print("\nwrote ab-match-compare.png")
