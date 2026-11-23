"""Annotate GP_prof_report.txt RVAs using Arma3_x64.exe RTTI vtables + string xrefs.

Maps any RVA in the profiler report to:
  1. Exact C++ class name(s) if the RVA appears in an MSVC RTTI vtable
  2. Nearby/referenced ASCII strings inside the function body (RIP-relative LEA)
  3. Known RVA tags from extract/cpu_samples/known_rva.txt
"""
from __future__ import annotations

import bisect
import os
import re
import struct
import sys

EXE_DEFAULT = os.path.join(os.environ.get("ARMA3_DIR", r"<ARMA3>"), "Arma3_x64.exe")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWN = os.path.join(ROOT, "extract", "cpu_samples", "known_rva.txt")


class PEImage:
    def __init__(self, path: str):
        self.data = open(path, "rb").read()
        e = struct.unpack_from("<I", self.data, 0x3C)[0]
        coff = e + 4
        nsec = struct.unpack_from("<H", self.data, coff + 2)[0]
        opt = coff + 20
        self.image_base = struct.unpack_from("<Q", self.data, opt + 24)[0]
        sec_off = opt + struct.unpack_from("<H", self.data, coff + 16)[0]
        self.secs = []
        for i in range(nsec):
            o = sec_off + i * 40
            nm = self.data[o : o + 8].rstrip(b"\0").decode("latin-1", "ignore")
            vs, va, rs, ra = struct.unpack_from("<IIII", self.data, o + 8)
            self.secs.append((nm, va, vs, ra, rs))

    def rva_to_off(self, rva: int) -> int | None:
        for _, va, vs, ra, rs in self.secs:
            if va <= rva < va + max(vs, rs):
                off = ra + (rva - va)
                if off < ra + rs:
                    return off
        return None

    def get_sec(self, name: str):
        for s in self.secs:
            if s[0] == name:
                return s
        return None

    def read_cstr(self, rva: int, maxlen: int = 120) -> str | None:
        off = self.rva_to_off(rva)
        if off is None:
            return None
        chunk = self.data[off : off + maxlen]
        nul = chunk.find(b"\x00")
        if nul < 3:
            return None
        raw = chunk[:nul]
        if all(32 <= b < 127 for b in raw):
            return raw.decode("ascii")
        return None


def build_vtable_map(pe: PEImage) -> dict[int, list[str]]:
    """Scan .rdata for MSVC x64 RTTI CompleteObjectLocator -> vtable -> method RVAs."""
    rdata = pe.get_sec(".rdata")
    data_sec = pe.get_sec(".data")
    text = pe.get_sec(".text")
    if not rdata or not text:
        return {}

    _, rva_r, _, off_r, sz_r = rdata
    _, rva_t, vs_t, _, _ = text
    t_lo = pe.image_base + rva_t
    t_hi = t_lo + vs_t

    # Map TypeDescriptor RVA -> demangled-ish name
    td_names: dict[int, str] = {}
    for m in re.finditer(rb"\.\?AV([A-Za-z0-9_@?$<>]+?)@@\x00", pe.data):
        str_off = m.start()
        # TypeDescriptor starts 16 bytes before name (vftable ptr + spare ptr)
        td_off = str_off - 16
        # Convert file off to RVA
        td_rva = None
        for _, va, vs, ra, rs in pe.secs:
            if ra <= td_off < ra + rs:
                td_rva = va + (td_off - ra)
                break
        if td_rva is not None:
            raw = m.group(1).decode("ascii", "ignore")
            parts = [p for p in raw.split("@") if p]
            cls = "::".join(reversed(parts)) if parts else raw
            td_names[td_rva] = cls

    # Find COLs in .rdata: signature == 1, pTypeDescriptor in td_names, pSelf == col_rva
    col_va_to_cls: dict[int, str] = {}
    blob = pe.data[off_r : off_r + sz_r]
    for rel in range(0, len(blob) - 24, 4):
        sig = struct.unpack_from("<I", blob, rel)[0]
        if sig != 1:
            continue
        p_td = struct.unpack_from("<I", blob, rel + 12)[0]
        if p_td not in td_names:
            continue
        col_rva = rva_r + rel
        p_self = struct.unpack_from("<I", blob, rel + 20)[0]
        if p_self == col_rva:
            col_va_to_cls[pe.image_base + col_rva] = td_names[p_td]

    # Scan .rdata qwords for pointers to COL -> immediately followed by vtable slots!
    method_map: dict[int, list[str]] = {}
    for rel in range(0, len(blob) - 16, 8):
        q = struct.unpack_from("<Q", blob, rel)[0]
        cls = col_va_to_cls.get(q)
        if not cls:
            continue
        # Vtable starts at rel + 8
        for slot in range(128):
            s_off = rel + 8 + slot * 8
            if s_off + 8 > len(blob):
                break
            fn_va = struct.unpack_from("<Q", blob, s_off)[0]
            if not (t_lo <= fn_va < t_hi):
                break
            fn_rva = fn_va - pe.image_base
            tag = f"{cls}::vslot[{slot}]"
            lst = method_map.setdefault(fn_rva, [])
            if len(lst) < 3 and tag not in lst:
                lst.append(tag)
    return method_map


def scan_fn_strings(pe: PEImage, rva: int, size: int) -> list[str]:
    """Find RIP-relative LEA (48/4C 8D xx disp32) pointing to readable strings."""
    off = pe.rva_to_off(rva)
    if off is None:
        return []
    code = pe.data[off : off + min(size, 16384)]
    found: list[str] = []
    seen = set()
    i = 0
    n = len(code)
    while i + 7 <= n:
        b0 = code[i]
        if (b0 == 0x48 or b0 == 0x4C) and code[i + 1] == 0x8D:
            modrm = code[i + 2]
            if (modrm & 0xC7) == 0x05:  # RIP-relative
                disp = struct.unpack_from("<i", code, i + 3)[0]
                target_rva = rva + i + 7 + disp
                s = pe.read_cstr(target_rva)
                if s and s not in seen:
                    seen.add(s)
                    found.append(s[:48])
                    if len(found) >= 4:
                        break
                i += 7
                continue
        i += 1
    return found


def load_known() -> dict[int, str]:
    out: dict[int, str] = {}
    if not os.path.isfile(KNOWN):
        return out
    with open(KNOWN, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"\s+", line, maxsplit=1)
            if len(parts) == 2:
                out[int(parts[0], 16)] = parts[1]
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: annotate_prof.py <GP_prof_report.txt> [Arma3_x64.exe]")
        return 2
    rep_path = sys.argv[1]
    exe_path = sys.argv[2] if len(sys.argv) > 2 else EXE_DEFAULT
    print(f"Loading PE + RTTI vtables from {exe_path}...")
    pe = PEImage(exe_path)
    vmap = build_vtable_map(pe)
    known = load_known()
    print(f"Mapped {len(vmap)} virtual methods across RTTI vtables.")

    lines = open(rep_path, encoding="utf-8", errors="replace").read().splitlines()
    out_lines = []
    for line in lines:
        m = re.search(r"0x([0-9A-Fa-f]{8})\s+(\d+)", line)
        if m:
            rva = int(m.group(1), 16)
            sz = int(m.group(2))
            tags = []
            if rva in known:
                tags.append(f"KNOWN:{known[rva]}")
            if rva in vmap:
                tags.append("VTABLE:" + ",".join(vmap[rva]))
            strs = scan_fn_strings(pe, rva, sz)
            if strs:
                tags.append("STR:" + " | ".join(strs[:3]))
            if tags:
                line = f"{line}   ;; {' ; '.join(tags)}"
        else:
            m2 = re.search(r"0x([0-9A-Fa-f]{8})\s*->\s*0x([0-9A-Fa-f]{8})", line)
            if m2:
                r1, r2 = int(m2.group(1), 16), int(m2.group(2), 16)
                t1 = known.get(r1) or (vmap[r1][0] if r1 in vmap else "")
                t2 = known.get(r2) or (vmap[r2][0] if r2 in vmap else "")
                if t1 or t2:
                    line = f"{line}   ;; {t1 or '?'} -> {t2 or '?'}"
        out_lines.append(line)

    out_path = rep_path.replace(".txt", "_annotated.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")
    print(f"Wrote {out_path}")
    # Print key sections
    for l in out_lines[:115]:
        print(l)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

