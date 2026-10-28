
from PIL import Image, ImageDraw, ImageFont
import numpy as np
after = r"<ARMA3_DOCS>\Screenshots\gp_r_baseline.png"
before = r"<REPO>\demo\_live\maxed.png"
a = Image.open(after).convert("RGB")
b = Image.open(before).convert("RGB").resize(a.size, Image.LANCZOS)
d = np.abs(np.asarray(a,np.float32)-np.asarray(b,np.float32))
print("mean abs diff vs maxed:", round(float(d.mean()),2))
regions = [("wall base", 300, 430, 160), ("barrels base", 330, 470, 120)]
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 20)
tw, th = 440, 440
sheet = Image.new("RGB", (tw*2+60, (th+30)*len(regions)+20), (18,18,20))
dr = ImageDraw.Draw(sheet)
for i,(name,cx,cy,half) in enumerate(regions):
    for j,im in enumerate([b, a]):
        c = im.crop((cx-half,cy-half,cx+half,cy+half)).resize((tw,th), Image.LANCZOS)
        x=20+j*(tw+20); y=10+i*(th+30)
        sheet.paste(c,(x,y+30))
        dr.text((x+2,y+4), f"{name} {'原样' if j==0 else 'smoothstep'}", font=font, fill=(235,235,240))
out=r"<REPO>\demo\ssao-smoothstep.png"
sheet.save(out); print(out, sheet.size)
