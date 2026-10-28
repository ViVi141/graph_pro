import struct
EXE = r"<ARMA3>\Arma3_x64.exe"
data = open(EXE, "rb").read()
e = struct.unpack_from("<I", data, 0x3C)[0]
coff = e + 4
nsec = struct.unpack_from("<H", data, coff + 2)[0]
opt = coff + 20
sec_off = opt + struct.unpack_from("<H", data, coff + 16)[0]
secs = []
for i in range(nsec):
    o = sec_off + i * 40
    name = data[o:o+8].rstrip(b"\0").decode("latin-1","ignore")
    vs, va, rs, ra = struct.unpack_from("<IIII", data, o + 8)
    secs.append((name, va, vs, ra, rs))
text = [s for s in secs if s[0] == ".text"][0]
_, tva, tvs, tra, trs = text
def rva_of(off):
    for name, va, vs, ra, rs in secs:
        if ra <= off < ra + rs: return va + (off - ra)
    return None

def scan(slot, label):
    disp = slot * 8
    hits = []
    if disp < 0x80:
        for rm in range(8):
            pat = bytes([0xFF, 0x50 | rm, disp])
            s = tra
            while True:
                i = data.find(pat, s, tra + trs)
                if i < 0: break
                hits.append(rva_of(i)); s = i + 1
    for rm in range(8):
        pat = bytes([0xFF, 0x90 | rm]) + struct.pack("<i", disp)
        s = tra
        while True:
            i = data.find(pat, s, tra + trs)
            if i < 0: break
            hits.append(rva_of(i)); s = i + 1
    # SIB form: mod=10, rm=100 -> FF 94 <sib> <disp32>
    for sib in range(256):
        pat = bytes([0xFF, 0x94, sib]) + struct.pack("<i", disp)
        s = tra
        while True:
            i = data.find(pat, s, tra + trs)
            if i < 0: break
            hits.append(rva_of(i)); s = i + 1
    hits = sorted(set(hits))
    print("%-30s slot %2d disp 0x%03X  sites: %4d  %s" %
          (label, slot, disp, len(hits), " ".join("0x%X" % h for h in hits[:5])))
    return hits

for slot, name in [(12,"DrawIndexed"), (13,"Draw"), (20,"DrawIndexedInstanced"),
                   (21,"DrawInstanced"), (38,"DrawAuto"), (39,"DrawIndexedInstancedIndirect"),
                   (40,"DrawInstancedIndirect"), (58,"ExecuteCommandList")]:
    scan(slot, name)
