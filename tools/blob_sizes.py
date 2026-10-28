
import struct, zlib, glob, os
sizes = {}
for fn in sorted(glob.glob(r"<REPO>\extract\shdc\*.shdc")):
    b = open(fn,'rb').read()
    i = 0
    while True:
        i = b.find(b"DXBC", i)
        if i < 0: break
        try: size = struct.unpack_from('<I', b, i+24)[0]
        except: break
        if 100 < size < 300000 and i + size <= len(b):
            blob = b[i:i+size]
            sizes.setdefault(size, []).append((os.path.basename(fn), zlib.crc32(blob)&0xffffffff))
            i += size
        else:
            i += 4
for s in (5860, 692, 224, 13596, 11132):
    if s in sizes:
        print(s, "->", sizes[s][:3])
    else:
        print(s, "-> none")
