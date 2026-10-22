
from PIL import Image
p = r"C:\Users\74738\Documents\Arma 3\Screenshots\gp_r_baseline.png"
im = Image.open(p).convert("RGB")
im.thumbnail((1200,1200))
im.save(r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\_live\latest_full.png")
print(im.size)
