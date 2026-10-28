
from PIL import Image, ImageDraw, ImageFont
paths = [("0.60 / 0.80", r"<USERPROFILE>\.dsh\attachments\v1\objects\9c\9cda81ac89d36daa4f2ef9d15aef2310eaa8b24367a6c2e980dcf7a7e34b1edd"),
         ("0.45 / 0.70", r"<USERPROFILE>\.dsh\attachments\v1\objects\d0\d028f1c6dbf2e1738c7d18d41da4a8a4ad477c9f6d46ac45716fc79c9f47eb67")]
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 20)
w,h = 860, 510
sheet = Image.new("RGB",(w*2+30,h+50),(18,18,20))
for i,(tag,p) in enumerate(paths):
    im = Image.open(p).convert("RGB").resize((w,h), Image.LANCZOS)
    sheet.paste(im,(10+i*(w+10),40))
    ImageDraw.Draw(sheet).text((10+i*(w+10),10), tag, font=font, fill=(235,235,240))
out=r"<REPO>\demo\ambient-045-vs-06.png"
sheet.save(out); print(out)
