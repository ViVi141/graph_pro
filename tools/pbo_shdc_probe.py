
import struct, os, collections

PBO = r"<ARMA3>\Dta\bin.pbo"
OUT = r"<REPO>\extract\shdc"
os.makedirs(OUT, exist_ok=True)
data = open(PBO,'rb').read()

pos = data.index(b'version\x00')
entries = []
while True:
    end = data.index(b'\x00', pos)
    name = data[pos:end].decode('latin-1')
    pos = end + 1
    if name == '':
        break
    mime, orig, off, ts, size = struct.unpack_from('<IIIII', data, pos)
    pos += 20
    entries.append((name, mime, orig, off, size))
header_end = pos
print("entries", len(entries), "header_end", header_end)
print("mimes", collections.Counter(hex(m) for _,m,_,_,_ in entries).most_common(6))
print("sample:", [e[0] for e in entries[:8]])

for name, mime, orig, off, size in entries:
    if not name.lower().endswith('.shdc'): continue
    start = header_end + off
    blob = data[start:start+size]
    open(os.path.join(OUT, name), 'wb').write(blob)
    print(f"{name:26s} mime={hex(mime):10s} stored={size:9d} orig={orig:9d} dxbc={blob.count(b'DXBC'):5d} first16={blob[:16].hex()}")
