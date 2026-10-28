
from PIL import Image
p = r"<ARMA3_DOCS>\Screenshots\gp_r_baseline.png"
im = Image.open(p).convert("RGB")
im.thumbnail((1200,1200))
im.save(r"<REPO>\demo\_live\latest_full.png")
print(im.size)
