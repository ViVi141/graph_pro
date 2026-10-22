import struct, os, re, collections
ADDONS = r"D:\SteamLibrary\steamapps\common\Arma 3\addons"

def lzss_decompress(data, expected):
    out = bytearray()
    i = 0
    while i < len(data) and len(out) < expected:
        flags = data[i]; i += 1
        for bit in range(8):
            if i >= len(data) or len(out) >= expected:
                break
            if flags & (1 << bit):
                out.append(data[i]); i += 1
            else:
                if i + 1 >= len(data):
                    break
                b1, b2 = data[i], data[i+1]; i += 2
                pos = b1 | ((b2 & 0xF0) << 4)
                length = (b2 & 0x0F) + 3
                start = len(out) - pos - 1
                for k in range(length):
                    out.append(out[start + k] if 0 <= start + k < len(out) else 0)
    return bytes(out[:expected])

def read_pbo(path, want):
    with open(path, "rb") as f:
        head = f.read(4 * 1024 * 1024)
        pos = head.find(b"version\x00")
        if pos < 0:
            return {}
        entries = []
        while True:
            end = head.index(b"\x00", pos)
            name = head[pos:end].decode("latin-1"); pos = end + 1
            if name == "":
                break
            mime, orig, off, ts, size = struct.unpack_from("<IIIII", head, pos); pos += 20
            entries.append((name, mime, orig, off, size))
        header_end = pos
        result = {}
        for name, mime, orig, off, size in entries:
            if not name.lower().endswith(want):
                continue
            f.seek(header_end + off)
            blob = f.read(size)
            if mime == 0x43707273:  # Cprs
                blob = lzss_decompress(blob, orig)
            result[name] = blob
        return result

pat_spec = re.compile(r"specular(?:Color)?\s*(?:\[\])?\s*=\s*\{([^}]*)\}", re.I)
pat_pow  = re.compile(r"specularPower\s*=\s*([0-9.]+)", re.I)

for pbo in ["plants_f.pbo", "structures_f_mil.pbo", "rocks_f.pbo", "data_f.pbo"]:
    p = os.path.join(ADDONS, pbo)
    try:
        mats = read_pbo(p, ".rvmat")
    except Exception as e:
        print(pbo, "ERR", e); continue
    zero = tot = 0
    pows = collections.Counter()
    for name, blob in mats.items():
        text = blob.decode("latin-1", "ignore")
        m = pat_spec.search(text)
        pw = pat_pow.search(text)
        tot += 1
        val = 0.0
        if m:
            try:
                parts = [float(x) for x in m.group(1).split(",") if x.strip()]
                val = max(parts) if parts else 0.0
            except Exception:
                val = -1.0
        if pw:
            pows[round(float(pw.group(1)))] += 1
        if val <= 1e-6:
            zero += 1
    print("%-26s materials=%3d  specular==0: %3d (%.0f%%)  top specularPower: %s" %
          (pbo, tot, zero, 100.0*zero/max(tot,1), pows.most_common(4)))
