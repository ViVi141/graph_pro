
# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont
import numpy as np, os, json

d = r"<ARMA3_DOCS>\Screenshots"
items = [("gp_q_baseline.png","baseline 原样"),
         ("gp_q_film_lowContrast.png","film_lowContrast 低对比"),
         ("gp_q_cold_highContrast.png","cold_highContrast 冷调高对比"),
         ("gp_q_warm_sunset.png","warm_sunset 暖调日落")]

TW, TH, LAB = 940, 529, 58
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 22)
small = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 17)
sheet = Image.new("RGB", (TW*2 + 36, (TH+LAB)*2 + 36), (16,16,18))

for i,(fn,label) in enumerate(items):
    im = Image.open(os.path.join(d,fn)).convert("RGB").resize((TW,TH), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32)/255.0
    lum = 0.2126*a[...,0]+0.7152*a[...,1]+0.0722*a[...,2]
    mx=a.max(axis=2); mn=a.min(axis=2)
    sat=np.where(mx>1e-5,(mx-mn)/np.maximum(mx,1e-5),0)
    txt = "亮度 %d   高光溢出 %.1f%%   饱和度 %.1f%%   对比(σ) %.0f" % (
        lum.mean()*255, (lum>0.98).mean()*100, sat.mean()*100, lum.std()*255)
    x = 12 + (i%2)*(TW+12); y = 12 + (i//2)*(TH+LAB)
    sheet.paste(im,(x,y+LAB))
    dr = ImageDraw.Draw(sheet)
    dr.text((x+2,y+6), label, font=font, fill=(240,240,242))
    dr.text((x+2,y+34), txt, font=small, fill=(150,190,230))

out = r"<REPO>\demo\grade-compare.png"
sheet.save(out)
print(out, sheet.size)
