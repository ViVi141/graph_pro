#!/usr/bin/env python3
"""Patch a binary Arma 3 rvmat in place (same length, no re-encoding).

Why this exists: official addon rvmats are *binarized* (`\\0raP` container).
CfgConvert refuses them ("Unknown entry type"), and Binarize only goes
text -> binary.  But the specular block is a simple tagged array:

    "specular\\0" 0x04 [tag][f32] [tag][f32] [tag][f32] [tag][u32]

tag 0x01 = float literal, tag 0x02 = int literal.  Vanilla "matte" materials
store 0.0 as tag 0x02 + int 0, which is why a naive float write is ignored.
This tool flips the tag to 0x01 and writes the float, leaving everything else
byte-identical.

Only specular RGB is touched.  specularPower is left alone on purpose: in some
materials it is stored as int (e.g. 10) and in others as float (e.g. 99.2);
flipping its type without re-encoding the container is not safe.

Usage:
  python tools/rvmat_patch.py in.rvmat out.rvmat --specular 0.10,0.10,0.10
Prints a byte-diff summary so the edit can be audited.
"""
import argparse
import struct
import sys


def patch_specular(data: bytearray, rgb):
    key = b"specular\x00"
    k = data.find(key)
    if k < 0:
        raise SystemExit("no 'specular' property")
    k += len(key)
    if data[k] != 0x04:
        raise SystemExit(f"unexpected specular array type 0x{data[k]:02x}")
    k += 1
    spans = []
    for i in range(3):
        tag = data[k]
        old = struct.unpack_from("<f", data, k + 1)[0]
        if tag not in (0x01, 0x02):
            raise SystemExit(f"unexpected tag 0x{tag:02x} at offset {k}")
        data[k] = 0x01                      # force float literal
        struct.pack_into("<f", data, k + 1, float(rgb[i]))
        spans.append((k, k + 5, tag, old, float(rgb[i])))
        k += 5
    return spans


def patch_power(data: bytearray, power):
    """specularPower is stored either as a raw float (e.g. 29.2) or as an int
    (e.g. 10).  Only patch when the existing bytes look like a plausible float,
    otherwise leave the field alone - flipping its type would corrupt the file.
    """
    key = b"specularPower\x00"
    k = data.find(key)
    if k < 0:
        return None
    k += len(key)
    old = struct.unpack_from("<f", data, k)[0]
    if not (0.0 < old < 1000.0):
        return ("skip", old, None)
    struct.pack_into("<f", data, k, float(power))
    return ("ok", old, float(power))



def diff_spans(before: bytes, after: bytes):
    out, start = [], None
    for i, (a, b) in enumerate(zip(before, after)):
        if a != b and start is None:
            start = i
        elif a == b and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(after)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--specular", required=True, help="r,g,b")
    ap.add_argument("--power", type=float, default=None, help="specularPower (float form only)")
    a = ap.parse_args()
    rgb = [float(x) for x in a.specular.split(",")]
    if len(rgb) != 3:
        raise SystemExit("--specular needs r,g,b")

    raw = open(a.src, "rb").read()
    data = bytearray(raw)
    spans = patch_specular(data, rgb)
    pw = patch_power(data, a.power) if a.power is not None else None
    if len(data) != len(raw):
        raise SystemExit("length changed - refusing to write")
    open(a.dst, "wb").write(data)

    print(f"in {len(raw)} B -> out {len(data)} B")
    for k, end, tag, old, new in spans:
        print(f"  offset {k:5d}: tag 0x{tag:02x} val {old:+.4f} -> {new:+.4f}")
    if pw:
        print(f"  power: {pw[0]} {pw[1]:+.3f} -> {pw[2]}")
    changed = diff_spans(raw, bytes(data))
    total = sum(b - s for s, b in changed)
    print(f"  changed spans: {changed}  ({total} bytes)")
    # structural sanity: all known property names must still be present
    for key in (b"PixelShaderID\x00", b"VertexShaderID\x00", b"specular\x00",
                b"ambient\x00", b"diffuse\x00"):
        if key not in data:
            raise SystemExit(f"structure damaged: missing {key}")
    print("  structure check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
