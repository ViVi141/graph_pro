
from PIL import Image
p = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\_live\sp.png"
im = Image.open(p)
box = (470, 95, 740, 250)
c = im.crop(box).resize(((box[2]-box[0])*4, (box[3]-box[1])*4), Image.LANCZOS)
c.save(r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo\_live\sp_zoom.png")
print(c.size)
