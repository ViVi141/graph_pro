
import glob, os, re
d = r"<ARMA3>\GP_cand"
files = glob.glob(os.path.join(d, "small_*.txt"))
print("files", len(files))
for f in sorted(files):
    t = open(f, encoding="utf-8", errors="replace").read()
    tex = t.count("dcl_resource_texture2d")
    has_movx = "mov o0.xyzw, r0.xxxx" in t
    if tex == 1 and has_movx:
        print("CANDIDATE", os.path.basename(f))
        print(t[t.find("ps_"):][:600])
        print("---")
