import re, glob, os
root = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\Include\*\um"))[-1]
txt = open(os.path.join(root, "d3d11.h"), encoding="utf-8", errors="ignore").read()
m = re.search(r"typedef struct ID3D11DeviceContextVtbl\s*\{(.*?)\}\s*ID3D11DeviceContextVtbl;", txt, re.S)
names = re.findall(r"STDMETHODCALLTYPE\s*\*\s*(\w+)\s*\)", m.group(1))
for i in range(54, 66):
    print("slot %-3d %s" % (i, names[i]))
