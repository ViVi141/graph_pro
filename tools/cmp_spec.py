
from PIL import Image, ImageDraw, ImageFont
import numpy as np
before = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\_live\maxed.png"   # 1100 wide preview
after_src = r"C:\Users\74738\Documents\Arma 3\Screenshots\gp_r_baseline.png"
a = Image.open(after_src).convert("RGB")
a_small = a.resize((1100, 619), Image.LANCZOS)
b = Image.open(before).convert("RGB")
arr1 = np.asarray(b, np.float32); arr2 = np.asarray(a_small, np.float32)
d = np.abs(arr1-arr2)
print("mean abs diff:", round(float(d.mean()),2), "pct>8:", round(float((d.mean(axis=2)>8).mean()*100),2))

# crops at full res: wall+barrels region, road
regions = [("wall/barrels", 380, 330, 200), ("road", 1100, 470, 200), ("roof", 1690, 300, 180)]
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 20)
tw, th = 400, 400
sheet = Image.new("RGB", (tw*2+60, (th+30)*len(regions)+20), (18,18,20))
d2 = ImageDraw.Draw(sheet)
for i,(name,cx,cy,half) in enumerate(regions):
    for j,src in enumerate([before, after_src]):
        im = Image.open(src).convert("RGB")
        if im.size[0] != 1920:
            im = im.resize((1920,1080), Image.LANCZOS)
        box=(cx-half,cy-half,cx+half,cy+half)
        c=im.crop(box).resize((tw,th), Image.LANCZOS)
        x=20+j*(tw+20); y=10+i*(th+30)
        sheet.paste(c,(x,y+30))
        d2.text((x+2,y+4), f"{name} {'无镜面' if j==0 else '加镜面'}", font=font, fill=(235,235,240))
out=r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\spec-compare.png"
sheet.save(out); print(out, sheet.size)
