import struct, os
ADDONS = r"D:\SteamLibrary\steamapps\common\Arma 3\addons"
def lzss(data, expected):
    out = bytearray(); i = 0
    while i < len(data) and len(out) < expected:
        flags = data[i]; i += 1
        for bit in range(8):
            if i >= len(data) or len(out) >= expected: break
            if flags & (1 << bit):
                out.append(data[i]); i += 1
            else:
                if i + 1 >= len(data): break
                b1, b2 = data[i], data[i+1]; i += 2
                pos = b1 | ((b2 & 0xF0) << 4); length = (b2 & 0x0F) + 3
                start = len(out) - pos - 1
                for k in range(length):
                    out.append(out[start+k] if 0 <= start+k < len(out) else 0)
    return bytes(out[:expected])
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
    rv = [e for e in entries if e[0].lower().endswith(".rvmat")]
    print("rvmat entries:", len(rv))
    print("mime distribution:", {hex(m): sum(1 for e in rv if e[1]==m) for m in set(e[1] for e in rv)})
    name, mime, orig, off, size = rv[0]
    f.seek(header_end + off); blob = f.read(size)
    print("first:", name, "mime", hex(mime), "stored", size, "orig", orig)
    if mime == 0x43707273:
        blob = lzss(blob, orig)
    print("--- text ---")
    print(blob[:600].decode("latin-1", "ignore"))
