
from PIL import Image, ImageDraw, ImageFont
import numpy as np, os

before = r"<REPO>\demo\before3\gp_r_baseline.png"
after  = r"<ARMA3_DOCS>\Screenshots\gp_r_baseline.png"

def arr(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.float32)

def sharp(a):
    g = a.mean(axis=2)
    k = np.array([[0,1,0],[1,-4,1],[0,1,0]], np.float32)
    from numpy.lib.stride_tricks import sliding_window_view
    w = sliding_window_view(g, (3,3))
    lap = (w * k).sum(axis=(2,3))
    return float(lap.var())

def reg(a, x, y, r=200):
    return a[max(0,y-r):y+r, max(0,x-r):x+r]

for tag,p in [("BEFORE(旧设置)", before), ("AFTER(新设置) ", after)]:
    a = arr(p)
    print(f"{tag} sharpness_all={sharp(a)/1000:.1f}  road={sharp(reg(a,1100,470))/1000:.1f}  wall={sharp(reg(a,380,330))/1000:.1f}")

# side by side crops
im1 = Image.open(before).convert("RGB"); im2 = Image.open(after).convert("RGB")
regions = [("soldier",1056,640,150),("wall",380,330,180),("road",1100,470,180),("roof",1690,300,180)]
tw = 360*2; th = 360*2
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 20)
sheet = Image.new("RGB", (tw*2+60, (th+34)*len(regions)+20), (18,18,20))
d = ImageDraw.Draw(sheet)
for i,(name,cx,cy,half) in enumerate(regions):
    for j,im in enumerate([im1, im2]):
        box=(max(0,cx-half),max(0,cy-half),cx+half,cy+half)
        c=im.crop(box).resize((tw,th), Image.LANCZOS)
        x=20+j*(tw+20); y=10+i*(th+34)
        sheet.paste(c,(x,y+34))
        d.text((x+2,y+6), f"{name} {'旧设置' if j==0 else '新设置'}", font=font, fill=(235,235,240))
out=r"<REPO>\demo\config-compare.png"
sheet.save(out); print(out, sheet.size)
