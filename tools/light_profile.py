import numpy as np
from PIL import Image
A = r"<USERPROFILE>\.dsh\attachments\v1\objects\cf\cf05fe264a6ab3e8740603c5165f0f8c8194cd095bc64bea9ed2d338572c1220"
im = np.asarray(Image.open(A).convert("RGB")).astype(np.float32)/255.0
L = 0.2126*im[:,:,0]+0.7152*im[:,:,1]+0.0722*im[:,:,2]
print("floor luminance vs row (row -> distance from camera increases upward)")
for y in range(620, 1010, 60):
    print("  y=%4d  floor centre %.4f    left wall %.4f" % (y, L[y:y+40, 760:1160].mean(), L[y:y+40, 460:520].mean()))
print()
print("back wall bands (x 520..1240) at the window height and below:")
for x in range(520, 1240, 120):
    print("  x=%4d  %.4f" % (x, L[400:520, x:x+110].mean()))
print()
print("windows:", np.round(im[330:360, 550:1240].reshape(-1,3).mean(0), 3))
print("wall near window (y 380..430):", np.round(im[380:430, 600:1200].reshape(-1,3).mean(0), 3))
print("ceiling:", np.round(im[110:260, 600:1200].reshape(-1,3).mean(0), 3))
