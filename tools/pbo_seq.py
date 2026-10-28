import struct, os
ADDONS = r"<ARMA3>\addons"
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
    f.seek(header_end)
    blob = f.read(700)
    print("first bytes after header:", " ".join("%02x" % b for b in blob[:24]))
    txt = blob.decode("latin-1", "ignore")
    print("as text:", repr(txt[:200]))
    # walk sequentially and see whether sizes/order line up
    f.seek(header_end); offset = header_end
    ok = 0
    for i, (name, mime, orig, off, ts, size) in enumerate(entries[:5]):
        f.seek(offset)
        b = f.read(size)
        looks = any(k in b[:400] for k in (b"ambient", b"diffuse", b"specular", b"class"))
        print("seq %-55s size=%5d looks_rvmat=%s" % (name, size, looks))
        if looks: ok += 1
        offset += size
    print("sequential hits:", ok, "/ 5")
