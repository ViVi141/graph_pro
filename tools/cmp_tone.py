
from PIL import Image, ImageDraw, ImageFont
a = Image.open(r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\_live\maxed.png").convert("RGB")
b = Image.open(r"C:\Users\74738\Documents\Arma 3\Screenshots\gp_r_baseline.png").convert("RGB")
w,h = 880, 495
a = a.resize((w,h), Image.LANCZOS); b = b.resize((w,h), Image.LANCZOS)
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 20)
sheet = Image.new("RGB",(w*2+30,h+50),(18,18,20))
sheet.paste(a,(10,40)); sheet.paste(b,(w+20,40))
d=ImageDraw.Draw(sheet)
d.text((10,10),"改前：阴影偏暖、占比 3.3%",font=font,fill=(235,235,235))
d.text((w+20,10),"改后：阴影偏冷 -0.05、占比 14%",font=font,fill=(235,235,235))
out=r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\tone-compare.png"
sheet.save(out); print(out)
