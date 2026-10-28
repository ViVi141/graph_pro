
from PIL import Image, ImageDraw, ImageFont
a = Image.open(r"<USERPROFILE>\.dsh\attachments\v1\objects\6a\6a7fb4f0b30eefca60dc4dfb2f0047bda42194a78b36d82c0fb5ed18ecca1683").convert("RGB")
b = Image.open(r"<USERPROFILE>\.dsh\attachments\v1\objects\9c\9cda81ac89d36daa4f2ef9d15aef2310eaa8b24367a6c2e980dcf7a7e34b1edd").convert("RGB")
w, h = 860, 510
a = a.resize((w,h), Image.LANCZOS); b = b.resize((w,h), Image.LANCZOS)
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 20)
sheet = Image.new("RGB",(w*2+30, h+50),(18,18,20))
sheet.paste(a,(10,40)); sheet.paste(b,(w+20,40))
d=ImageDraw.Draw(sheet)
d.text((10,10),"调整前（环境光原值）",font=font,fill=(235,235,240))
d.text((w+20,10),"调整后（ambient 0.6 / AE 0.8）",font=font,fill=(235,235,240))
out=r"<REPO>\demo\ambient-compare.png"
sheet.save(out); print(out, sheet.size)
