import struct, os
ADDONS = r"D:\SteamLibrary\steamapps\common\Arma 3\addons"
p = os.path.join(ADDONS, "plants_f.pbo")
with open(p, "rb") as f:
    head = f.read(4*1024*1024)
    pos = head.find(b"version\x00"); entries = []
    while True:
        end = head.index(b"\x00", pos); name = head[pos:end].decode("latin-1"); pos = end+1
        if name == "": break
        mime, orig, off, ts, size = struct.unpack_from("<IIIII", head, pos); pos += 20
        entries.append((name, mime, orig, off, size))
    header_end = pos
    print("header_end", header_end)
    name, mime, orig, off, size = [e for e in entries if e[0].lower().endswith(".rvmat")][0]
    for label, start in [("header_end+off", header_end + off), ("off", off)]:
        f.seek(start); blob = f.read(64)
        print("%-16s %s" % (label, " ".join("%02x" % b for b in blob[:32])))
    # try the next entry's offset to see spacing
    idx = [e[0] for e in entries].index(name)
    n2 = entries[idx+1]
    print("first entry:", name, "off", off, "size", size)
    print("second entry:", n2[0], "off", n2[2], "size", n2[4], "delta", n2[2] - off)
