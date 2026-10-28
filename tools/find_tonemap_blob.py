
import struct, zlib, glob, os
target = (5860, 0x42670B06)
for fn in sorted(glob.glob(r"<REPO>\extract\shdc\*.shdc")):
    b = open(fn,'rb').read()
    i = 0
    found = 0
    while True:
        i = b.find(b"DXBC", i)
        if i < 0: break
        try: size = struct.unpack_from('<I', b, i+24)[0]
        except: break
        if 100 < size < 300000 and i + size <= len(b):
            blob = b[i:i+size]
            if (size, zlib.crc32(blob)&0xffffffff) == target:
                print("FOUND in", os.path.basename(fn), "at", i, "size", size)
                found = 1
            i += size
        else:
            i += 4
    if found: break
else:
    print("not found in shdc; checking all sizes near 5860")
