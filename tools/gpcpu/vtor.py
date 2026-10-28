import os
import sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe
SRV = r"<ARMA3>\arma3server_x64.exe"
b = pe.Bin(SRV)
IB = b.base
data = b.pe.__data__
# section map
secs = b.sections

def off_of(rva):
    for n, va, vs, pr, sr in secs:
        if va <= rva < va + max(vs, sr):
            return pr + (rva - va)
    return None

def read_rva(rva, n):
    o = off_of(rva)
    return data[o:o+n] if o is not None else b''

def find_vtable(rva):
    # look for absolute pointer IB+rva in .rdata
    target = struct.pack('<Q', IB + rva)
    rd = [s for s in secs if s[0] == '.rdata'][0]
    nm, va, vs, pr, sr = rd
    blob = data[pr:pr+sr]
    out = []
    start = 0
    while True:
        i = blob.find(target, start)
        if i < 0: break
        start = i + 1
        entry_rva = va + i
        # vtable[-1] should be a COL pointer (absolute)
        if i >= 8:
            col = struct.unpack_from('<Q', blob, i - 8)[0]
            if IB <= col < IB + 0x4000000:
                col_rva = col - IB
                hdr = read_rva(col_rva, 20)
                if len(hdr) == 20:
                    sig, off, cd, td, cd2 = struct.unpack('<IIIII', hdr)
                    if sig == 1 and 0 < td < 0x4000000:
                        tdn = read_rva(td, 300)
                        if tdn[:1] == b'.':
                            z = tdn.find(b'\0')
                            out.append((entry_rva, tdn[:z].decode('latin-1', 'replace')))
    return out

for rva in [0x646FC0, 0x1072032, 0x1071489, 0x13792BA, 0x1400FEB, 0x139B7A5, 0x10747E0, 0x137A1FA, 0x10ABC85, 0x1088D30, 0xE32A82]:
    vt = find_vtable(rva)
    print("%08x -> %s" % (rva, vt[:3] if vt else "not in vtable"))
