"""Annotate GP_sample_top.txt with known RVAs + Capstone peek."""
from __future__ import annotations

import bisect
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = r"<ARMA3>\Arma3_x64.exe"
KNOWN = os.path.join(ROOT, "extract", "cpu_samples", "known_rva.txt")
OUT = os.path.join(ROOT, "extract", "cpu_samples", "c1_yaab_annotated.txt")


def load_pe(path: str):
    data = open(path, "rb").read()
    e = struct.unpack_from("<I", data, 0x3C)[0]
    coff = e + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    opt = coff + 20
    ib = struct.unpack_from("<Q", data, opt + 24)[0]
    sec_off = opt + struct.unpack_from("<H", data, coff + 16)[0]
    secs = []
    for i in range(nsec):
        o = sec_off + i * 40
        nm = data[o : o + 8].split(b"\0", 1)[0].decode("latin-1", "ignore")
        vs, va, rs, ra = struct.unpack_from("<IIII", data, o + 8)
        secs.append((nm, va, vs, ra, rs))
    return data, ib, secs


def sec_off(secs, rva: int):
    for _nm, va, vs, ra, _rs in secs:
        if va <= rva < va + vs:
            return ra + (rva - va)
    return None


def load_known(path: str) -> dict[int, str]:
    out: dict[int, str] = {}
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            a, b = line.split(None, 1)
            out[int(a, 16)] = b
    return out


def parse_top(path: str):
    rows = []
    meta = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# total_samples"):
                parts = line.split()
                meta["samples"] = int(parts[2])
                meta["misses"] = int(parts[4])
                continue
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            rows.append(
                (int(parts[0]), float(parts[1]), int(parts[2], 16), int(parts[3]))
            )
    return rows, meta


def tag(rva: int, size: int, known: dict[int, str]) -> str:
    if rva in known:
        return known[rva]
    for kr, name in known.items():
        if rva <= kr < rva + size:
            return name
    if rva == 0x1A249F0:
        return "Simulate_16way_dispatch"
    if abs(rva - 0x1A249F0) < 0x800:
        return "near_16way_dispatch"
    if 0x11527E0 <= rva < 0x11527E0 + 11093:
        return "inside_World::Simulate"
    if size <= 128:
        return "tiny_leaf?"
    if size >= 3000:
        return "large_fn"
    return "unlabeled"


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else (
        r"<ARMA3>\GP_sample_top.txt"
    )
    if not os.path.isfile(src):
        print("missing", src)
        return 1

    data, ib, secs = load_pe(EXE)
    known = load_known(KNOWN)
    rows, meta = parse_top(src)

    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64

        md = Cs(CS_ARCH_X86, CS_MODE_64)
        have_cs = True
    except Exception:
        have_cs = False
        md = None

    samples = meta.get("samples", 0)
    misses = meta.get("misses", 0)
    attributed = samples / max(1, samples + misses)

    lines = [
        f"# source {src}",
        f"# samples={samples} misses={misses} "
        f"exe_hit_rate={100.0 * attributed:.2f}%",
        "# hits  pct     rva         size   tag",
    ]

    print(lines[1])
    print("hits   pct      rva         size   tag")
    for hits, pct, rva, size in rows:
        t = tag(rva, size, known)
        extra = ""
        if have_cs:
            o = sec_off(secs, rva)
            if o is not None:
                code = data[o : o + min(size, 80)]
                ins = list(md.disasm(code, ib + rva))
                calls = sum(1 for i in ins if i.mnemonic == "call")
                mnems = ",".join(i.mnemonic for i in ins[:5])
                extra = f"  peek_calls~{calls} [{mnems}]"
        line = f"{hits:5d}  {pct:6.2f}%  0x{rva:08X}  {size:5d}  {t}{extra}"
        print(line)
        lines.append(line)

    # Class buckets by size
    leafish = [r for r in rows if r[3] <= 200]
    big = [r for r in rows if r[3] >= 1500]
    lines.append(
        f"# leafish(size<=200) in top: {len(leafish)}  "
        f"large(size>=1500): {len(big)}"
    )
    lines.append(
        "# verdict: high miss rate => much time in other modules "
        "(ntdll/d3d/driver/mimalloc) or waits; exe top is flat."
    )

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
