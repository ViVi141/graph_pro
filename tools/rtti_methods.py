import re, collections, os
EXE = r"<ARMA3>\Arma3_x64.exe"
data = open(EXE, "rb").read()
names = sorted(set(m.group(0).decode("latin-1") for m in
                   re.finditer(rb"\.\?A[VU][A-Za-z0-9_@?$<>.-]{3,200}@@", data)))

# decorated member functions look like: ??Name@Class@@...  (possibly nested namespaces Class@Ns@@)
pairs = set()
for n in names:
    for m in re.finditer(r"\?\?([A-Za-z_][A-Za-z0-9_]{2,40})@((?:[A-Za-z_][A-Za-z0-9_]*@){1,3})", n):
        fn = m.group(1)
        scopes = [s for s in m.group(2).split("@") if s]
        pairs.add((scopes[0], "::".join(reversed(scopes)), fn))
print("named member functions found:", len(pairs))

by_class = collections.defaultdict(list)
for cls, scope, fn in pairs:
    by_class[scope].append(fn)

interesting = ("Landscape", "World", "Scene", "AI", "Path", "Visib", "Occlusion", "Clutter",
               "Shadow", "Render", "DX11", "Animation", "Anim", "Phys", "Terrain", "LOD")
print("\nclasses with >=3 named methods (filtered to engine subsystems):")
rows = []
for scope, fns in by_class.items():
    if any(k.lower() in scope.lower() for k in interesting):
        rows.append((len(set(fns)), scope, sorted(set(fns))))
rows.sort(reverse=True)
for n, scope, fns in rows[:20]:
    print("  %-34s %3d  %s" % (scope, n, ", ".join(fns[:6])))

out = r"<REPO>\extract\engine_methods.txt"
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    for n, scope, fns in rows:
        f.write("%s\t%d\t%s\n" % (scope, n, ",".join(fns)))
print("\nwrote", out)
