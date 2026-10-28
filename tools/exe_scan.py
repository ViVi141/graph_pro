import struct, re, collections
EXE = r"<ARMA3>\Arma3_x64.exe"
data = open(EXE, "rb").read()
print("size", len(data))

# --- PE sections ---
e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
assert data[e_lfanew:e_lfanew+4] == b"PE\0\0"
coff = e_lfanew + 4
nsec = struct.unpack_from("<H", data, coff + 2)[0]
opt = coff + 20
magic = struct.unpack_from("<H", data, opt)[0]
image_base = struct.unpack_from("<Q", data, opt + 24)[0]
sec_off = opt + struct.unpack_from("<H", data, coff + 16)[0]
secs = []
for i in range(nsec):
    o = sec_off + i * 40
    name = data[o:o+8].rstrip(b"\0").decode("latin-1", "ignore")
    vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, o + 8)
    chars = struct.unpack_from("<I", data, o + 36)[0]
    secs.append((name, vaddr, vsize, raddr, rsize, chars))
print("image_base 0x%X" % image_base)
for s in secs:
    print("  %-8s rva=0x%08X vsz=0x%08X raw=0x%08X rsz=0x%08X" % (s[0], s[1], s[2], s[3], s[4]))

def rva_of(off):
    for name, vaddr, vsize, raddr, rsize, chars in secs:
        if raddr <= off < raddr + rsize:
            return vaddr + (off - raddr), name
    return None, None

# --- scan for call [reg+disp] through vtable slots ---
def scan_disp(disp, label):
    hits = []
    pats = []
    for rm in range(8):
        modrm8 = 0x50 | rm      # mod=01 reg=010
        pats.append((bytes([0xFF, modrm8, disp & 0xFF]), 8))
        if disp > 0xFF:
            modrm32 = 0x90 | rm
            pats.append((bytes([0xFF, modrm32]) + struct.pack("<I", disp), -1))
    for pat, _ in pats:
        start = 0
        while True:
            i = data.find(pat, start)
            if i < 0: break
            rva, sec = rva_of(i)
            if sec and sec == ".text":
                hits.append(rva)
            start = i + 1
    print("%-28s disp=0x%X  call sites in .text: %d" % (label, disp, len(hits)))
    return hits

for slot, name in [(12, "DrawIndexed"), (13, "Draw"), (20, "DrawIndexedInstanced"),
                   (21, "DrawInstanced"), (38, "DrawAuto"), (39, "DrawIndexedInstancedIndirect"),
                   (40, "DrawInstancedIndirect"), (58, "ExecuteCommandList")]:
    h = scan_disp(slot * 8, name)
    if h:
        print("     first few RVAs:", " ".join("0x%X" % x for x in h[:6]))
