
import re, os, glob, difflib

REF = r"<REPO>\extract\dxbc\tonemap.asm"
CAND = r"<ARMA3>\GP_cand"

def mnemonics(path):
    out = []
    for ln in open(path, encoding="utf-8", errors="replace").read().splitlines():
        s = ln.strip()
        if not s or s.startswith("//"): continue
        m = re.match(r'^([a-z][a-z0-9_]*)\b', s)
        if m: out.append(m.group(1))
    return out

ref = mnemonics(REF)
print("reference instr:", len(ref))
print(" ".join(ref))
print()

best = []
for p in sorted(glob.glob(os.path.join(CAND, "*.txt"))):
    cur = mnemonics(p)
    sm = difflib.SequenceMatcher(None, ref, cur)
    ratio = sm.ratio()
    name = os.path.basename(p)
    best.append((ratio, name, len(cur), cur))
    print(f"{name:22s} instr={len(cur):3d} ratio={ratio:.3f}")
print()
best.sort(reverse=True)
for ratio, name, n, cur in best[:2]:
    print("== best:", name, f"ratio={ratio:.3f}")
    print("   ", " ".join(cur))
