import struct, os
ADDONS = r"<ARMA3>\addons"
READ = 2 * 1024 * 1024
rows = []
for fn in sorted(os.listdir(ADDONS)):
    if not fn.lower().endswith(".pbo"):
        continue
    p = os.path.join(ADDONS, fn)
    try:
        with open(p, "rb") as f:
            head = f.read(READ)
    except Exception:
        continue
    pos = head.find(b"version\x00")
    if pos < 0:
        rows.append((fn, -1, 0, os.path.getsize(p)))
        continue
    try:
        entries = []
        while True:
            end = head.index(b"\x00", pos)
            name = head[pos:end].decode("latin-1")
            pos = end + 1
            if name == "":
                break
            mime, orig, off, ts, size = struct.unpack_from("<IIIII", head, pos)
            pos += 20
            entries.append((name, off, size, mime))
    except Exception:
        rows.append((fn, -2, 0, os.path.getsize(p)))
        continue
    rv = [e for e in entries if e[0].lower().endswith(".rvmat")]
    rows.append((fn, len(entries), len(rv), os.path.getsize(p)))
rows.sort(key=lambda r: -r[2])
print("%-42s %8s %7s %10s" % ("pbo", "entries", "rvmat", "size"))
for fn, ne, nr, sz in rows[:18]:
    print("%-42s %8d %7d %10d" % (fn, ne, nr, sz))
print("\ntotal rvmat:", sum(r[2] for r in rows if r[2] > 0))
print("pbos scanned:", len(rows))
