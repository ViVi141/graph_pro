
import struct
p = r"D:\SteamLibrary\steamapps\common\Arma 3\arma3_x64.exe"
d = open(p,'rb').read()
e_lfanew = struct.unpack_from('<I', d, 0x3C)[0]
assert d[e_lfanew:e_lfanew+4] == b'PE\x00\x00'
coff = e_lfanew + 4
nsec = struct.unpack_from('<H', d, coff+2)[0]
sizeopt = struct.unpack_from('<H', d, coff+16)[0]
opt = coff + 20
magic = struct.unpack_from('<H', d, opt)[0]
dd = opt + (112 if magic == 0x20b else 96)
imp_rva, imp_size = struct.unpack_from('<II', d, dd + 8)
secs = []
sec0 = opt + sizeopt
for i in range(nsec):
    o = sec0 + i*40
    name = d[o:o+8].rstrip(b'\x00').decode('latin-1')
    vsize, vaddr, rsize, raddr = struct.unpack_from('<IIII', d, o+8)
    secs.append((name, vaddr, vsize, raddr, rsize))
def rva2off(rva):
    for n,v,vs,ra,rs in secs:
        if v <= rva < v + max(vs, rs):
            return ra + (rva - v)
    return None
off = rva2off(imp_rva)
res = {}
while True:
    oft, tds, fc, name_rva, ft = struct.unpack_from('<IIIII', d, off)
    if name_rva == 0: break
    no = rva2off(name_rva)
    dll = d[no:d.index(b'\x00', no)].decode('latin-1')
    funcs = []
    t = rva2off(oft if oft else ft)
    while True:
        v = struct.unpack_from('<Q', d, t)[0]
        if v == 0: break
        if not (v & (1<<63)):
            fo = rva2off(v & 0x7fffffff)
            fn = d[fo+2:d.index(b'\x00', fo+2)].decode('latin-1')
            funcs.append(fn)
        t += 8
    res[dll] = funcs
    off += 20
for dll, fns in res.items():
    if 'd3d11' in dll.lower() or 'dxgi' in dll.lower() or 'd3dcompiler' in dll.lower():
        print(dll, len(fns))
        for f in fns: print("   ", f)
