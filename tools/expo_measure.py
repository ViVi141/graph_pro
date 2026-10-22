import numpy as np
from PIL import Image
A = r"C:\Users\74738\.dsh\attachments\v1\objects\cf\cf05fe264a6ab3e8740603c5165f0f8c8194cd095bc64bea9ed2d338572c1220"  # expo hi=1.10
B = r"C:\Users\74738\.dsh\attachments\v1\objects\8c\8c132e7eb402527ae5c3a05ecdbcd398ae13b47979507c33093f0c2aff303a85"  # expo hi=0.30
def lum(img): return 0.2126*img[:,:,0]+0.7152*img[:,:,1]+0.0722*img[:,:,2]
for name, p in [("hi=1.10", A), ("hi=0.30", B)]:
    im = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)/255.0
    L = lum(im)
    # regions inside the 3D viewport (x 220..1470, y 95..1010 in this 1924x1140 render)
    wall   = L[300:420, 700:900]
    floor  = L[820:900, 700:1000]
    win    = L[330:370, 545:640]
    print("%-9s wall %.4f  floor %.4f  window %.4f   frame_mean %.4f  frac>0.98 %.3f  frac<0.02 %.3f" %
          (name, wall.mean(), floor.mean(), win.mean(), L[100:1000, 230:1460].mean(),
           (L[100:1000, 230:1460] > 0.98).mean(), (L[100:1000, 230:1460] < 0.02).mean()))
    print("           wall RGB %s  window RGB %s" % (np.round(im[300:420,700:900].reshape(-1,3).mean(0),3),
                                                    np.round(im[330:370,545:640].reshape(-1,3).mean(0),3)))
