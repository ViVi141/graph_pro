
import struct, os, re, collections
p = r"<REPO>\extract\shdc\Shaders_5_0_PP.shdc"
b = open(p,'rb').read()
print("size", len(b))
print("head 160:", b[:160].hex(' '))
first = b.find(b'DXBC')
print("first DXBC at", first)
print("around first:", b[max(0,first-64):first].hex(' '))
# DXBC total size at +24
sz = struct.unpack_from('<I', b, first+24)[0]
print("declared size", sz)
# collect offsets
offs=[]
i=0
while True:
    i = b.find(b'DXBC', i)
    if i<0: break
    try: s = struct.unpack_from('<I', b, i+24)[0]
    except: break
    if 100 < s < 200000 and i+s <= len(b):
        offs.append((i,s))
        i += s
    else:
        i += 4
print("blobs:", len(offs), "total bytes:", sum(s for _,s in offs))
# ascii strings inside blobs
def strings(x, n=6):
    return [m.decode('latin-1') for m in re.findall(rb'[\x20-\x7e]{%d,}'%n, x)]
cnt = collections.Counter()
for o,s in offs:
    for st in strings(b[o:o+s], 5):
        cnt[st]+=1
for st,c in cnt.most_common(40):
    print(f"{c:5d}  {st[:90]}")
