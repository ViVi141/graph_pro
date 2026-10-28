
# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont
import numpy as np, os

d = r"<ARMA3_DOCS>\Screenshots"
items = [("gp_r_baseline.png","A 原样（引擎默认成像）"),
         ("gp_r_film_lowContrast.png","B 低对比胶片"),
         ("gp_r_cold_highContrast.png","C 冷调高对比"),
         ("gp_r_warm_sunset.png","D 暖调日落")]

TW, TH, LAB = 940, 529, 62
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 23)
small = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 17)
sheet = Image.new("RGB", (TW*2 + 36, (TH+LAB)*2 + 36), (16,16,18))
rows = []
for i,(fn,label) in enumerate(items):
    im = Image.open(os.path.join(d,fn)).convert("RGB")
    a = np.asarray(im).astype(np.float32)/255.0
    lum = 0.2126*a[...,0]+0.7152*a[...,1]+0.0722*a[...,2]
    mx=a.max(axis=2); mn=a.min(axis=2)
    sat=np.where(mx>1e-5,(mx-mn)/np.maximum(mx,1e-5),0)
    rows.append((label, lum.mean()*255, (lum>0.98).mean()*100, (lum<0.02).mean()*100, sat.mean()*100, lum.std()*255))
    tile = im.resize((TW,TH), Image.LANCZOS)
    x = 12 + (i%2)*(TW+12); y = 12 + (i//2)*(TH+LAB)
    sheet.paste(tile,(x,y+LAB))
    dr = ImageDraw.Draw(sheet)
    dr.text((x+2,y+8), label, font=font, fill=(240,240,242))
    dr.text((x+2,y+36), "亮度 %.0f   高光溢出 %.1f%%   死黑 %.1f%%   饱和度 %.1f%%   对比σ %.0f" % rows[-1][1:], font=small, fill=(150,190,230))

out = r"<REPO>\demo\grade-compare-real.png"
sheet.save(out)
for r_ in rows: print("%-22s luma=%.0f clip=%.1f%% crush=%.1f%% sat=%.1f%% sd=%.0f" % r_)
print(out)
