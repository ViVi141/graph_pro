import re, collections, os, json
EXE = r"D:\SteamLibrary\steamapps\common\Arma 3\Arma3_x64.exe"
data = open(EXE, "rb").read()
names = sorted(set(m.group(0).decode("latin-1") for m in
                   re.finditer(rb"\.\?A[VU][A-Za-z0-9_@?$<>.-]{3,200}@@", data)))
print("unique RTTI names:", len(names))

def undecorate(n):
    # crude: pull identifiers separated by @, keep those not starting with ?/$
    parts = [p for p in n.split("@") if p and not p.startswith("?")]
    return parts

classes = collections.Counter()
for n in names:
    parts = undecorate(n)
    if parts:
        classes[parts[0]] += 1
print("\ntop-level symbols (first @-field), by count:")
for k, v in classes.most_common(40):
    print("  %-28s %4d" % (k, v))

keywords = ["AI", "Path", "Visib", "Cull", "Landscape", "Terrain", "Phys", "Anim",
            "Render", "DX11", "Sound", "Network", "Script", "Matrix", "Vector",
            "Spatial", "Occlusion", "LOD", "Clutter", "Shadow"]
print("\nkeyword hits across all RTTI names:")
for k in keywords:
    hits = [n for n in names if k in n]
    print("  %-12s %4d" % (k, len(hits)))

out = r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\extract\rtti_names.txt"
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "w", encoding="utf-8").write("\n".join(names))
print("\nfull list ->", out)
