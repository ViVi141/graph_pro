"""Name arma3server_x64 Top RVAs via .pdata + near-string + RTTI method xref.

Usage:
  python tools/server_top_name.py [GP_sample_top.txt]
"""
from __future__ import annotations

import bisect
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = r"D:\SteamLibrary\steamapps\common\Arma 3\arma3server_x64.exe"
DEFAULT_TOP = os.path.join(
    ROOT, "extract", "cpu_samples", "top_20261024_023135.txt"
)
OUT = os.path.join(ROOT, "extract", "cpu_samples", "server_top_named.txt")

# Client-known string fingerprints we also expect on server.
FINGERPRINTS = [
    (b"ParallelFor sync", "ParallelFor_sync"),
    (b"simulation started twice", "simstep_guard"),
    (b"mtVehS", "mtVehS"),
    (b"World::Simulate", "World_Simulate_str"),
    (b"PerformAI", "PerformAI_str"),
    (b"ProcessSearching", "ProcessSearching_str"),
    (b"PrepareGroundClutter", "PrepareGroundClutter_str"),
]


def pe_map(data: bytes):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    coff = e + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    opt = coff + 20
    ib = struct.unpack_from("<Q", data, opt + 24)[0]
    sec_off = opt + struct.unpack_from("<H", data, coff + 16)[0]
    secs = []
    for i in range(nsec):
        o = sec_off + i * 40
        nm = data[o : o + 8].rstrip(b"\0").decode("latin-1", "ignore")
        vs, va, rs, ra = struct.unpack_from("<IIII", data, o + 8)
        secs.append((nm, va, vs, ra, rs))
    return ib, secs


def off_of(secs, rva: int) -> int | None:
    for _nm, va, vs, ra, _rs in secs:
        if va <= rva < va + vs:
            return ra + (rva - va)
    return None


def load_funcs(data: bytes, secs):
    pd = [s for s in secs if s[0] == ".pdata"][0]
    _nm, _va, _vs, ra, rs = pd
    funcs = []
    for i in range(0, rs, 12):
        b, e2, _u = struct.unpack_from("<III", data, ra + i)
        if b and e2 > b:
            funcs.append((b, e2))
    funcs.sort()
    return funcs


def owner(funcs, rva: int):
    starts = [f[0] for f in funcs]
    k = bisect.bisect_right(starts, rva) - 1
    if k < 0:
        return None
    b, e2 = funcs[k]
    if b <= rva < e2:
        return b, e2
    return None


def parse_top(path: str):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(
                r"(\d+)\s+([\d.]+)(?:\s+([\d.]+))?\s+0x([0-9A-Fa-f]+)\s+(\d+)",
                line,
            )
            if not m:
                continue
            hits = int(m.group(1))
            pct_tot = float(m.group(2))
            pct_exe = float(m.group(3) or m.group(2))
            rva = int(m.group(4), 16)
            size = int(m.group(5))
            rows.append((hits, pct_tot, pct_exe, rva, size))
    return rows


def build_string_index(data: bytes, secs, ib: int):
    """Map absolute string VA -> printable snippet; then rip-relative users in .text."""
    rd = [s for s in secs if s[0] == ".rdata"][0]
    _nm, rva, _vs, ra, rs = rd
    # Collect interesting C strings in .rdata
    interesting = {}
    blob = data[ra : ra + rs]
    for needle, tag in FINGERPRINTS:
        start = 0
        while True:
            i = blob.find(needle, start)
            if i < 0:
                break
            # expand to full C string
            s0 = i
            while s0 > 0 and 32 <= blob[s0 - 1] < 127:
                s0 -= 1
            s1 = i
            while s1 < len(blob) and blob[s1] != 0 and 32 <= blob[s1] < 127:
                s1 += 1
            snip = blob[s0:s1][:80].decode("latin-1", "replace")
            str_rva = rva + s0
            interesting[str_rva] = (tag, snip)
            start = i + 1

    # Also harvest RTTI mangled names containing key tokens
    rtti = {}
    for m in re.finditer(rb"\.\?A[VU][A-Za-z0-9_@?$<>.-]{3,200}@@", data):
        name = m.group(0).decode("latin-1")
        if any(
            k in name
            for k in (
                "Simulate@World",
                "PerformAI@World",
                "ProcessSearching",
                "PrepareGroundClutter",
                "ParallelFor",
            )
        ):
            o = m.start()
            for _nm, va, vs, ra2, rs2 in secs:
                if ra2 <= o < ra2 + rs2:
                    rtti[va + (o - ra2)] = name
                    break
    return interesting, rtti


def find_lea_users(data: bytes, secs, funcs, str_rvas: set[int], ib: int):
    """Scan .text for RIP-relative LEA/MOV that land on str_rva; map to owner func."""
    T = [s for s in secs if s[0] == ".text"][0]
    _nm, trva, _tvs, traw, trsz = T
    text = data[traw : traw + trsz]
    # pattern: 48 8D 0D/15/05/1D/2D/35 xx xx xx xx  (LEA r?, [rip+disp32])
    # also 48 8B 0D ... MOV
    hits = {r: [] for r in str_rvas}
    for i in range(len(text) - 7):
        if text[i] != 0x48:
            continue
        op = text[i + 1]
        modrm = text[i + 2]
        if op not in (0x8D, 0x8B):
            continue
        if (modrm & 0xC7) != 0x05:  # mod=00 reg=? rm=101 rip-rel
            continue
        disp = struct.unpack_from("<i", text, i + 3)[0]
        insn_rva = trva + i
        next_rva = insn_rva + 7
        target = (next_rva + disp) & 0xFFFFFFFF
        if target in hits:
            own = owner(funcs, insn_rva)
            if own:
                hits[target].append(own[0])
    return hits


def strings_near_func(data: bytes, secs, ib: int, fb: int, fe: int, limit=6):
    """Pull ASCII literals referenced by RIP-rel LEA inside [fb,fe)."""
    fo = off_of(secs, fb)
    if fo is None:
        return []
    body = data[fo : fo + (fe - fb)]
    out = []
    for i in range(len(body) - 7):
        if body[i] != 0x48 or body[i + 1] not in (0x8D, 0x8B):
            continue
        if (body[i + 2] & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", body, i + 3)[0]
        next_rva = fb + i + 7
        target = (next_rva + disp) & 0xFFFFFFFF
        to = off_of(secs, target)
        if to is None:
            continue
        # read C string
        chunk = data[to : to + 96]
        if not chunk or chunk[0] == 0:
            continue
        if not (32 <= chunk[0] < 127):
            continue
        end = chunk.find(b"\0")
        if end < 4:
            continue
        s = chunk[:end].decode("latin-1", "replace")
        if not re.search(r"[A-Za-z]{4}", s):
            continue
        out.append(s[:70])
        if len(out) >= limit:
            break
    return out


def main() -> int:
    top_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TOP
    if not os.path.isfile(top_path):
        print("missing", top_path)
        return 1
    data = open(EXE, "rb").read()
    ib, secs = pe_map(data)
    funcs = load_funcs(data, secs)
    interesting, rtti = build_string_index(data, secs, ib)
    print(
        "server size=%d funcs=%d fp_strings=%d key_rtti=%d"
        % (len(data), len(funcs), len(interesting), len(rtti))
    )

    # Map fingerprint strings -> owning functions
    users = find_lea_users(data, secs, funcs, set(interesting), ib)
    fp_owners: dict[str, set[int]] = {}
    for srva, (tag, _snip) in interesting.items():
        for fb in users.get(srva, []):
            fp_owners.setdefault(tag, set()).add(fb)

    # RTTI type names present (not method bodies) — list for notes
    for r, n in sorted(rtti.items(), key=lambda x: x[1])[:20]:
        print("RTTI", hex(r), n[:100])

    rows = parse_top(top_path)[:25]
    lines = [
        f"# named from {top_path}",
        f"# exe={os.path.basename(EXE)} imagebase=0x{ib:X}",
        "# hits pct_exe rva size owner tag strings",
    ]
    for hits, _pt, pe, rva, size in rows:
        own = owner(funcs, rva)
        if not own:
            tag = "NO_PDATA"
            fb, fe = rva, rva + size
        else:
            fb, fe = own
            tags = []
            for t, owners in fp_owners.items():
                if fb in owners:
                    tags.append(t)
            tag = ",".join(tags) if tags else "unlabeled"
        near = strings_near_func(data, secs, ib, fb, fe)
        near_s = " | ".join(near) if near else "-"
        line = (
            f"{hits:5d} {pe:7.3f}%  0x{rva:08X}  {size:5d}  "
            f"owner=0x{fb:08X}..{fe:08X}  {tag}  :: {near_s}"
        )
        print(line)
        lines.append(line)

    lines.append("")
    lines.append("# fingerprint string -> owner function RVAs")
    for tag, owners in sorted(fp_owners.items()):
        lines.append(
            f"#   {tag}: " + ", ".join(f"0x{o:X}" for o in sorted(owners)[:12])
        )
        print(tag, [hex(o) for o in sorted(owners)[:8]])

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
