#!/usr/bin/env python3
"""Fast static xref for a few DX11 render RTTI symbols (Gate 2)."""
from __future__ import annotations

import bisect
import re
import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EXE = Path(r"<ARMA3>\Arma3_x64.exe")
OUT = ROOT / "extract" / "rdc_notes" / "exe_render_xref.txt"

# Substrings inside demangled RTTI / lambda type names.
KW = (
    "Simulate@World@@",
    "PrepareDrawPrepareCloudlets@World@@",
    "SelectActiveAggLights@Scene@@",
    "GetDriverVersion@EngineDD11@DX11@@",
    "RenderCBToPlay@EngineDD11@DX11@@",
)


def main() -> None:
    data = EXE.read_bytes()
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
    text = [s for s in secs if s[0] == ".text"][0]
    _, trva, _, traw, trsz = text
    body = np.frombuffer(data[traw : traw + trsz], dtype=np.uint8)
    rd = [s for s in secs if s[0] == ".rdata"][0]
    _, rrva, _, rraw, rrsz = rd

    # Locate RTTI name strings that contain our keywords.
    name_hits = []
    for m in re.finditer(rb"\.\?A[VU][A-Za-z0-9_@?$<>.-]{3,220}@@", data):
        s = m.group(0).decode("latin-1")
        if any(k in s for k in KW):
            o = m.start()
            for nm, va, vs, ra, rs in secs:
                if ra <= o < ra + rs:
                    name_hits.append((va + (o - ra), s))
                    break
    # Dedup by RVA
    by_rva = {r: n for r, n in name_hits}

    # Map CompleteObjectLocator -> type; then find vtables pointing at COL.
    td = {r - 16: n for r, n in by_rva.items()}  # TypeDescriptor often 16B before name
    # Broader: search TypeDescriptor that references any matched name RVA.
    type_desc = {}
    for rva, name in by_rva.items():
        type_desc[rva] = name  # treat name RVA as key for string match below

    # Find .rdata QWORDs equal to ImageBase+nameRva (pointer to type name / TD)
    ptr_hits = {}
    for i in range(rraw, rraw + rrsz - 8, 8):
        v = struct.unpack_from("<Q", data, i)[0]
        if v < ib:
            continue
        r = v - ib
        if r in by_rva:
            ptr_hits.setdefault(by_rva[r], []).append(rrva + (i - rraw))

    pd = [s for s in secs if s[0] == ".pdata"][0]
    _, _pv, _pvs, pra, prs = pd
    funcs = []
    for i in range(0, prs, 12):
        b, e2, _u = struct.unpack_from("<III", data, pra + i)
        if b:
            funcs.append((b, e2))
    funcs.sort()
    starts = np.array([f[0] for f in funcs], dtype=np.uint32)

    def owner(rva: int):
        k = bisect.bisect_right(starts, rva) - 1
        if k < 0:
            return None
        b, e2 = funcs[k]
        return b if b <= rva < e2 else None

    def find_refs(target_rva: int, ilen: int = 7, limit: int = 40):
        # Vectorised scan for rel32 targeting target_rva.
        n = len(body) - 8
        # Stride sample every byte is heavy; use 1-byte but early-exit limit.
        pos = np.arange(0, n, dtype=np.int64)
        off = pos + ilen - 4
        d = (
            body[off].astype(np.int64)
            | (body[off + 1].astype(np.int64) << 8)
            | (body[off + 2].astype(np.int64) << 16)
            | (body[off + 3].astype(np.int64) << 24)
        )
        d = np.where(d >= 2**31, d - 2**32, d)
        want = target_rva - (trva + pos + ilen)
        idx = np.nonzero(d == want)[0][:limit]
        return [int(trva + k) for k in idx]

    lines = [
        f"# Render RTTI xref — {EXE.name}",
        f"# ImageBase 0x{ib:X}",
        "",
        "## RTTI name hits",
    ]
    for rva, name in sorted(by_rva.items()):
        lines.append(f"- 0x{rva:X}  {name[:140]}")
        ptrs = ptr_hits.get(name, [])[:6]
        if ptrs:
            lines.append(f"  rdata ptrs: " + ", ".join(f"0x{p:X}" for p in ptrs))

    # For PrepareDraw / Simulate / SelectActiveAggLights: xref to name RVA itself
    # (callers that load the type string / vtable via lea).
    lines.append("\n## .text refs to selected name RVAs (ilen=7, capped)")
    for rva, name in sorted(by_rva.items()):
        short = name
        if "PrepareDraw" not in name and "Simulate@World" not in name and "SelectActiveAggLights" not in name and "RenderCBToPlay" not in name:
            continue
        refs = find_refs(rva, 7, 30)
        owners = sorted({o for o in (owner(r) for r in refs) if o})
        lines.append(f"\n### {short[:100]}")
        lines.append(f"name_rva=0x{rva:X} refs={len(refs)} owning_funcs={len(owners)}")
        for o in owners[:8]:
            lines.append(f"  caller_func 0x{o:X}")

    lines += [
        "",
        "## Gate-2 interpretation",
        "- `DX11::EngineDD11` appears with PP/R2T parameter types and `RenderCBToPlay` worker —",
        "  render command buffers are played on a worker thread, not only on the Present thread.",
        "- `World::PrepareDrawPrepareCloudlets` is jobified (`JobFuture`) — draw prep is async.",
        "- `Scene::SelectActiveAggLights` is the CPU light-selection entry; sun direction for",
        "  contact shadows should be hunted from buffers it fills, not from PP VS cb (240 B quads).",
        "- Immediate-context Draw hooks seeing only count=4 quads is consistent with geometry",
        "  being recorded into deferred CBs / another context and replayed later.",
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} names={len(by_rva)}")


if __name__ == "__main__":
    main()
