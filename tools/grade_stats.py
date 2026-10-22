
# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont
import numpy as np, os, json

d = r"C:\Users\74738\Documents\Arma 3\Screenshots"
names = [("gp_q_baseline.png","原样 baseline"),
         ("gp_q_film_lowContrast.png","低对比胶片 film_lowContrast"),
         ("gp_q_cold_highContrast.png","冷调高对比 cold_highContrast"),
         ("gp_q_warm_sunset.png","暖调日落 warm_sunset")]

stats = []
for fn, label in names:
    im = Image.open(os.path.join(d, fn)).convert("RGB")
    a = np.asarray(im).astype(np.float32) / 255.0
    lum = 0.2126*a[...,0] + 0.7152*a[...,1] + 0.0722*a[...,2]
    mx = a.max(axis=2); mn = a.min(axis=2)
    sat = np.where(mx > 1e-5, (mx-mn)/np.maximum(mx,1e-5), 0)
    stats.append(dict(file=fn, label=label,
        luma=float(lum.mean()*255),
        clip=float((lum > 0.98).mean()*100),
        crush=float((lum < 0.02).mean()*100),
        sat=float(sat.mean()*100),
        contrast=float(lum.std()*255)))

for s in stats:
    print(f"{s['label']:34s} luma={s['luma']:6.1f} clip={s['clip']:5.2f}% crush={s['crush']:5.2f}% sat={s['sat']:5.1f}% sd={s['contrast']:5.1f}")
json.dump(stats, open(r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\_live\stats.json","w"), ensure_ascii=False, indent=1)
