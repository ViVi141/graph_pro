import numpy as np
GAME = r"<ARMA3>"
W,H = 1920,1080
d = (np.fromfile(GAME+r"\GP_depth_600.raw",dtype=np.uint32).reshape(H,W)&0xFFFFFF).astype(np.float32)/16777216.0
c = np.fromfile(GAME+r"\GP_color_600.raw",dtype=np.uint8).reshape(H,W,4)
rgb = c[:,:,:3]
sky = d >= 0.999999
print("sky pixels: %.3f of frame" % sky.mean())
s = rgb[sky]
print("sky R: mean %.1f min %d max %d" % (s[:,0].mean(), s[:,0].min(), s[:,0].max()))
print("sky G: mean %.1f min %d max %d" % (s[:,1].mean(), s[:,1].min(), s[:,1].max()))
print("sky B: mean %.1f min %d max %d" % (s[:,2].mean(), s[:,2].min(), s[:,2].max()))
print("frac pure blue (0,0,255): %.3f" % ((s[:,0]==0)&(s[:,1]==0)&(s[:,2]==255)).mean())
print("frac black (0,0,0): %.3f" % ((s[:,0]==0)&(s[:,1]==0)&(s[:,2]==0)).mean())
print("alpha stats: min %d max %d mean %.1f" % (c[:,:,3].min(), c[:,:,3].max(), c[:,:,3].mean()))
# row profile through the sky
for row in [60, 90, 120, 150]:
    seg = rgb[row]
    print("row %3d: R %3d..%3d  G %3d..%3d  B %3d..%3d" % (row, seg[:,0].min(), seg[:,0].max(), seg[:,1].min(), seg[:,1].max(), seg[:,2].min(), seg[:,2].max()))
