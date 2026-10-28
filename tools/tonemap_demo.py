
# -*- coding: utf-8 -*-
import numpy as np, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, SW, PH = 940, 400, 150          # tile width, scene height, plot height
H = SW + PH
yy, xx = np.mgrid[0:SW, 0:W].astype(np.float32)
u, v = xx / W, yy / SW

img = np.zeros((SW, W, 3), np.float32)
# interior: warm wall, mid tones so curves diverge
img += np.array([0.95, 0.80, 0.62], np.float32) * (0.10 + 0.22 * (1 - v))[..., None]
# floor
fl = v > 0.78
img[fl] = (np.array([0.42, 0.34, 0.26], np.float32) * (0.35 + 0.35 * (1 - v[fl]))[..., None])
# window / sky
win = (u > 0.50) & (u < 0.92) & (v > 0.12) & (v < 0.72)
sky = np.stack([0.55 + 0.25 * v, 0.68 + 0.2 * v, 0.95 + 0.0 * v], -1) * (2.0 + 7.0 * (1 - (v - 0.12) / 0.60))[..., None]
img[win] = sky[win]
# sun
d = np.sqrt(((u - 0.80) ** 2 + ((v - 0.26) * 1.8) ** 2))
img += (np.clip(1.0 - d / 0.03, 0, 1) ** 2)[..., None] * np.array([260.0, 230.0, 180.0], np.float32)
# lamp (left, near wall)
dl = np.sqrt((u - 0.15) ** 2 + ((v - 0.55) * 1.8) ** 2)
img += (np.clip(1.0 - dl / 0.045, 0, 1) ** 2)[..., None] * np.array([45.0, 26.0, 9.0], np.float32)
# glowing panel on wall (mid highlight 3..6)
pan = (u > 0.56) & (u < 0.70) & (v > 0.76) & (v < 0.86)
img[pan] = np.array([3.2, 3.0, 2.6], np.float32)

def srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)

def bloomp(hdr, thresh=1.0, strength=0.22):
    b = np.clip(hdr - thresh, 0, None)
    im = Image.fromarray(np.clip(srgb(b / 6.0) * 255, 0, 255).astype(np.uint8))
    im = im.resize((W // 4, SW // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(7))
    im = im.resize((W, SW), Image.BILINEAR)
    return np.asarray(im, np.float32) / 255.0 * strength

def aces(x):
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)
def reinhard(x): return x / (1.0 + x)
def clamp(x):    return np.clip(x, 0, 1)
curves = [("Clamp（无 tonemap）", clamp, False), ("Reinhard", reinhard, False),
          ("ACES filmic", aces, False), ("ACES + bloom", aces, True)]

pad, lab = 16, 52
grid = Image.new("RGB", (W * 2 + pad * 3, H * 2 + pad * 3 + lab * 2), (16, 16, 18))
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 27)
small = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 18)

for i, (title, fn, useb) in enumerate(curves):
    base = fn(img)
    if useb: base = np.clip(base + bloomp(img), 0, 1)
    tile = Image.new("RGB", (W, H), (0, 0, 0))
    tile.paste(Image.fromarray((srgb(base) * 255).astype(np.uint8)), (0, 0))
    d = ImageDraw.Draw(tile)
    # curve plot
    plot_y0, plot_h = SW, PH - 26
    d.rectangle([0, SW, W, SW + PH], fill=(26, 26, 30))
    ins_left, ins_right = 70, W - 20
    d.line([ins_left, SW + plot_h, ins_right, SW + plot_h], fill=(90, 90, 96))
    d.line([ins_left, SW + 14, ins_left, SW + plot_h], fill=(90, 90, 96))
    d.text((ins_left - 62, SW + 10), "输出", font=small, fill=(170, 170, 175))

    for xv, lb in [(1, "1"), (2, "2"), (4, "4"), (8, "8")]:
        px = ins_left + (xv / 8.0) * (ins_right - ins_left)
        d.line([px, SW + 14, px, SW + plot_h], fill=(52, 52, 58))
        d.text((px - 5, SW + plot_h + 4), lb, font=small, fill=(150, 150, 155))
    py_ = [ins_left + (k / 80.0) * (ins_right - ins_left) for k in range(81)]
    in_vals = np.linspace(0, 8, 81)
    out_vals = fn(in_vals.astype(np.float32))
    pts = [(p, SW + plot_h - o * (plot_h - 14)) for p, o in zip(py_, out_vals)]
    d.line(pts, fill=(240, 240, 240), width=3)
    px = pad + (i % 2) * (W + pad)
    py = pad + (i // 2) * (H + lab + pad)
    grid.paste(tile, (px, py + lab))
    dd = ImageDraw.Draw(grid)
    dd.text((px + 2, py + 10), title + "    横轴 = HDR 输入 0–8   纵轴 = 显示亮度", font=small, fill=(238, 238, 240))

outp = r"<REPO>\demo\tonemap-demo.png"
grid.save(outp)
print("saved", outp, grid.size)
