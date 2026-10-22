import re
EXE = r"D:\SteamLibrary\steamapps\common\Arma 3\Arma3_x64.exe"
data = open(EXE, "rb").read()
names = re.findall(rb"\.\?A[VU][A-Za-z0-9_@?$<>.-]{3,120}@@", data)
print("RTTI type descriptors found:", len(names))
uniq = sorted(set(names))
print("unique:", len(uniq))
kw = [n.decode('latin-1') for n in uniq]
for pat in ("Render", "Draw", "Mesh", "Scene", "Material", "Texture", "Vertex", "Object", "World"):
    hits = [k for k in kw if pat in k]
    print("  %-9s %4d   e.g. %s" % (pat, len(hits), hits[:3] if hits else ""))
# also look for the module/class strings the engine stores
for s in (b".pdb", b"IL2CPP", b"Unity", b"armake"):
    print("contains", s, s in data)
