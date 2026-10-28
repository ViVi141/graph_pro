
import re, struct, zlib, os, glob

shdc_dir = r"<REPO>\extract\shdc"
name_pat = re.compile(rb'([A-Za-z][A-Za-z0-9_]{2,40})\x00((?:ps|vs|gs|cs)_[45]_[01])\x00([0-9A-F]{8})\x00')

table = {}
for fn in glob.glob(os.path.join(shdc_dir, "*.shdc")):
    b = open(fn,'rb').read()
    for m in name_pat.finditer(b):
        name = m.group(1).decode()
        stage = m.group(2).decode()
        if not stage.startswith('ps'): continue
        j = b.find(b'DXBC', m.end())
        if j < 0: continue
        size = struct.unpack_from('<I', b, j+24)[0]
        if not (100 < size < 200000): continue
        blob = b[j:j+size]
        key = (size, zlib.crc32(blob) & 0xffffffff)
        table.setdefault(key, name)

print("ps entries in table:", len(table))

log = open(r"<ARMA3>\GP_shader.log", encoding='utf-8', errors='replace').read().splitlines()
seen = {}
for line in log:
    m = re.search(r'ps size=(\d+) crc=([0-9A-F]{8})', line)
    if not m: continue
    key = (int(m.group(1)), int(m.group(2),16))
    seen[key] = seen.get(key,0)+1

hits = 0
for (size,crc),count in sorted(seen.items(), key=lambda kv:-kv[0][0]):
    nm = table.get((size,crc))
    if nm:
        hits += 1
        print(f"{size:7d} {crc:08X} x{count:<3d} {nm}")
print("matched", hits, "of", len(seen))
