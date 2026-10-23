#!/usr/bin/env python3
"""Minimal Arma 3 PBO reader / extractor.

Facts this encodes (verified on 2.22 addons):
  * header: "prefix" property, then "product", "version" properties,
    then file entries [name\\0][mime,orig,offset,ts,size : 5x u32],
    terminated by an empty name.
  * offset field is 0 for all entries: data is stored sequentially in
    entry order, starting right after the header.  (This is why the old
    pbo_rvmat_scan saw "all offsets zero" and concluded the container was
    non-standard.)
  * file data sums to file_size - header_size - trailer (~41 B: a hash).
  * rvmats inside official addons are binarized; strings (PSID, .paa paths)
    are still readable with `strings`, which is enough to author a text
    replacement without decoding the binary.

Usage:
  python tools/pbo_extract.py <pbo> <virtual-path-or-substring> [outdir]
  python tools/pbo_extract.py <pbo> --list [substring]
"""
import os
import struct
import sys

DATA_PAD = 20


def read_entries(path):
    with open(path, "rb") as f:
        head = f.read(8 * 1024 * 1024)
    i = head.index(b"prefix\x00")
    props = {}
    first = None
    while True:
        j = head.index(b"\x00", i)
        name = head[i:j].decode("latin-1")
        i = j + 1
        if name in ("prefix", "product", "version"):
            j = head.index(b"\x00", i)
            props[name] = head[i:j].decode("latin-1")
            i = j + 1
            continue
        if name == "":
            continue
        first = name
        break
    entries = []
    while True:
        if first is not None:
            name, first = first, None
        else:
            j = head.index(b"\x00", i)
            name = head[i:j].decode("latin-1")
            i = j + 1
        if name == "":
            break
        mime, orig, off, ts, size = struct.unpack_from("<IIIII", head, i)
        i += 20
        entries.append({"name": name, "size": size, "mime": mime,
                        "original": orig, "offset": off})
    prefix = props.get("prefix", "")
    # 20-byte pad between the header and the first file's data.  Missing it
    # shifts every extraction 20 bytes early (you get the tail of the previous
    # file prepended, e.g. an SQF starting mid-line or an rvmat starting with
    # half a texture name).
    return prefix, i + DATA_PAD, entries


def extract(pbo, match, outdir=None):
    prefix, header_end, entries = read_entries(pbo)
    out = []
    pos = header_end
    with open(pbo, "rb") as f:
        for e in entries:
            if match in e["name"]:
                f.seek(pos)
                data = f.read(e["size"])
                dest = None
                if outdir:
                    dest = os.path.join(outdir, e["name"].replace("\\", "_"))
                    os.makedirs(outdir, exist_ok=True)
                    with open(dest, "wb") as g:
                        g.write(data)
                out.append((e["name"], data, dest))
            pos += e["size"]
    return prefix, out


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    pbo, target = argv[1], argv[2]
    if target == "--list":
        substr = argv[3] if len(argv) > 3 else ""
        prefix, header_end, entries = read_entries(pbo)
        print(f"prefix={prefix}  header={header_end}  entries={len(entries)}")
        for e in entries:
            if substr in e["name"]:
                print(f'{e["size"]:9d}  {e["name"]}')
        return 0
    outdir = argv[3] if len(argv) > 3 else None
    prefix, got = extract(pbo, target, outdir)
    print(f"prefix={prefix}  matches={len(got)}")
    for name, data, dest in got:
        print(f"  {name}  {len(data)} B -> {dest or '(memory)'}")
        if not dest:
            sys.stdout.buffer.write(data[:400])
    return 0 if got else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
