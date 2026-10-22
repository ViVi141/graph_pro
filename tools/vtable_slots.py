import re, glob, os
root = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\Include\*\um"))[-1]
def vtbls(path):
    txt = open(os.path.join(root, path), encoding="utf-8", errors="ignore").read()
    out = {}
    for m in re.finditer(r"typedef struct (\w+?)Vtbl\s*\{(.*?)\}\s*\1Vtbl;", txt, re.S):
        name, body = m.group(1), m.group(2)
        methods = re.findall(r"STDMETHODCALLTYPE\s*\*\s*(\w+)\s*\)", body)
        out[name] = methods
    return out
all_v = {}
for h in ["d3d11.h", "d3d11_1.h", "d3d11_2.h", "d3d11_3.h"]:
    p = os.path.join(root, h)
    if os.path.exists(p):
        all_v.update(vtbls(h))
for iface in ["ID3D11Device", "ID3D11Device1", "ID3D11Device2", "ID3D11Device3"]:
    ms = all_v.get(iface)
    if not ms:
        print(iface, "NOT FOUND"); continue
    print(iface + "  (" + str(len(ms)) + " slots)")
    for i, n in enumerate(ms):
        if "Deferred" in n:
            print("   slot %-3d %s" % (i, n))
ms = all_v.get("ID3D11DeviceContext") or []
print("\nID3D11DeviceContext (" + str(len(ms)) + " slots)")
want = {"DrawIndexed","Draw","DrawIndexedInstanced","DrawInstanced","IASetIndexBuffer",
        "VSSetConstantBuffers","Map","Unmap","OMSetRenderTargets","ExecuteCommandList",
        "DrawAuto","DrawIndexedInstancedIndirect","DrawInstancedIndirect","PSSetConstantBuffers"}
for i, n in enumerate(ms):
    if n in want:
        print("   slot %-3d %s" % (i, n))
