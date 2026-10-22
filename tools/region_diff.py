
from PIL import Image
import numpy as np
before = Image.open(r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\_live\maxed.png").convert("RGB").resize((1920,1080), Image.LANCZOS)
after = Image.open(r"C:\Users\74738\Documents\Arma 3\Screenshots\gp_r_baseline.png").convert("RGB")
regions = {"barrels":(200,180,560,520), "road":(900,300,1500,700), "roof":(1600,200,1900,500)}
for name,(x0,y0,x1,y1) in regions.items():
    a = np.asarray(before.crop((x0,y0,x1,y1)), np.float32)
    b = np.asarray(after.crop((x0,y0,x1,y1)), np.float32)
    d = np.abs(a-b)
    print(f"{name:9s} mean={d.mean():.2f} p95={np.percentile(d,95):.1f} max={d.max():.0f}")
