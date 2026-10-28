
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

old = r"<REPO>\demo\before2\gp_r_baseline.png"
new = r"<ARMA3_DOCS>\Screenshots\gp_r_baseline.png"

def sharp(p):
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32).mean(axis=2)
    k = np.array([[0,1,0],[1,-4,1],[0,1,0]], np.float32)
    w = sliding_window_view(a,(3,3)); lap=(w*k).sum(axis=(2,3))
    return float(lap.var())/1000

im1 = Image.open(old).convert("RGB").resize((900,506), Image.LANCZOS)
im2 = Image.open(new).convert("RGB").resize((900,506), Image.LANCZOS)
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 22)
small = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 18)
sheet = Image.new("RGB",(1840,600),(16,16,18))
sheet.paste(im1,(10,60)); sheet.paste(im2,(930,60))
d=ImageDraw.Draw(sheet)
d.text((10,14),"旧设置（texture=1, AF=4, SSAO=0, AA=0）",font=font,fill=(240,240,240))
d.text((930,14),"新设置（texture=3, AF=16, SSAO=1, SMAA）",font=font,fill=(240,240,240))
d.text((10,570),f"锐度指标 {sharp(old):.2f}",font=small,fill=(150,190,230))
d.text((930,570),f"锐度指标 {sharp(new):.2f}   (≈2× )",font=small,fill=(150,190,230))
out=r"<REPO>\demo\config-ab.png"
sheet.save(out); print(out, sheet.size)
