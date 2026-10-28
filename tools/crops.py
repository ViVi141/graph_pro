
from PIL import Image, ImageDraw, ImageFont
import os
src = r"<REPO>\demo\before3\gp_r_baseline.png"
im = Image.open(src).convert("RGB")
W,H = im.size
print("size", W, H)
regions = [
    ("soldier", 1056, 640, 160),
    ("wall",    380, 330, 200),
    ("road",   1100, 470, 200),
    ("roof",   1690, 300, 200),
    ("bg",      160,  60, 200),
]
tiles = []
for name, cx, cy, half in regions:
    box = (max(0,cx-half), max(0,cy-half), min(W,cx+half), min(H,cy+half))
    c = im.crop(box).resize(((box[2]-box[0])*2, (box[3]-box[1])*2), Image.LANCZOS)
    tiles.append((name, c))
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 20)
tw = max(t[1].width for t in tiles); th = max(t[1].height for t in tiles)
cols = 3; rows = 2
sheet = Image.new("RGB", (tw*cols+20*(cols+1), (th+30)*rows+20*(rows+1)), (18,18,20))
for i,(name,t) in enumerate(tiles):
    x = 20 + (i%cols)*(tw+20); y = 20 + (i//cols)*(th+30+20)
    sheet.paste(t,(x,y+30))
    ImageDraw.Draw(sheet).text((x+2,y+4), name, font=font, fill=(240,240,240))
out = r"<REPO>\demo\analysis-crops.png"
sheet.save(out); print(out, sheet.size)
