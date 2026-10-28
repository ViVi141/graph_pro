"""P0: name large Simulate callees. P1: find job submit/wait edges."""
from __future__ import annotations

import bisect
import os
import re
import struct
from collections import Counter, defaultdict

import numpy as np
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

EXE = r"<ARMA3>\Arma3_x64.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "extract", "cpu_samples", "simulate_p0_p1.txt")
SIM, SIM_SZ = 0x11527E0, 11093

LARGE = {
    0x11456D0: "large_A",
    0x1155340: "large_B",
    0x11566C0: "large_C",
    0x1260C00: "subsys_ac8",
    0x1263C50: "subsys_near_ac8",
}


def load_pe(path):
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


def rva_off(secs, rva):
    for _n, va, vs, ra, _rs in secs:
        if va <= rva < va + vs:
            return ra + (rva - va)
    return None


def fo_rva(secs, fo):
    for _n, va, _vs, ra, rs in secs:
        if ra <= fo < ra + rs:
            return va + (fo - ra)
    return None


def pdata(data, secs):
    pd = [s for s in secs if s[0] == ".pdata"][0]
    _n, _va, _vs, pra, prs = pd
    starts, ends = [], {}
    for i in range(0, prs, 12):
        b, e2, _u = struct.unpack_from("<III", data, pra + i)
        if b and e2 > b:
            starts.append(b)
            ends[b] = e2
    starts.sort()
    return starts, ends


def owner(starts, ends, rva):
    i = bisect.bisect_right(starts, rva) - 1
    if i < 0:
        return None, None
    b = starts[i]
    if b <= rva < ends[b]:
        return b, ends[b] - b
    return None, None


def read_cstr(data, secs, rva, maxlen=96):
    oo = rva_off(secs, rva)
    if oo is None:
        return None
    chunk = data[oo : oo + maxlen]
    end = chunk.find(b"\0")
    if end < 4:
        return None
    try:
        s = chunk[:end].decode("ascii")
    except Exception:
        return None
    if not s.isprintable():
        return None
    return s


def rip_strings(md, data, secs, ib, fn, size):
    oo = rva_off(secs, fn)
    if oo is None:
        return []
    out = []
    seen = set()
    for ins in md.disasm(data[oo : oo + size], ib + fn):
        for op in ins.operands:
            if op.type != X86_OP_MEM or op.mem.base != X86_REG_RIP:
                continue
            rr = (ins.address + ins.size + op.mem.disp) - ib
            s = read_cstr(data, secs, rr)
            if s and s not in seen:
                seen.add(s)
                out.append((ins.address - ib, s))
    return out


def find_string_rvas(data, secs, needle: bytes):
    hits = []
    pos = 0
    while True:
        i = data.find(needle, pos)
        if i < 0:
            break
        r = fo_rva(secs, i)
        if r is not None:
            hits.append(r)
        pos = i + 1
        if len(hits) > 20:
            break
    return hits


def code_xrefs_to_rva(tbytes, tva, target_rva, limit=20):
    """Find lea/mov-style rip-rel sites ending at target_rva (filter on 0x8D)."""
    hits = []
    arr = np.frombuffer(tbytes, dtype=np.uint8)
    idxs = np.where(arr == 0x8D)[0]
    for i in idxs:
        i = int(i)
        # 8D xx disp32 → 6 bytes from 8D; or REX+8D → 7 bytes from REX
        cands = []
        if i + 5 < len(tbytes):
            cands.append((i, 6))  # start at 8D
        if i >= 1 and i + 5 < len(tbytes) and tbytes[i - 1] in (
            0x48, 0x4C, 0x49, 0x4D, 0x41, 0x44, 0x45, 0x47,
        ):
            cands.append((i - 1, 7))
        for start, ilen in cands:
            d = struct.unpack_from("<i", tbytes, start + ilen - 4)[0]
            if tva + start + ilen + d == target_rva:
                hits.append(tva + start)
                if len(hits) >= limit:
                    return hits
    return hits


def main():
    data, ib, secs = load_pe(EXE)
    starts, ends = pdata(data, secs)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    text_sec = [s for s in secs if s[0] == ".text"][0]

    lines = ["# Simulate P0/P1 continuation", ""]

    # --- P0: strings in large callees + callers ---
    lines.append("## P0 large callees — rip strings")
    for rva, tag in LARGE.items():
        _o, sz = owner(starts, ends, rva)
        sz = sz or 256
        strs = rip_strings(md, data, secs, ib, rva, sz)
        lines.append(f"### 0x{rva:X} ({tag}) size={sz}")
        if not strs:
            lines.append("  (no rip strings)")
        for site, s in strs[:30]:
            lines.append(f"  @{site:X} {s!r}")
        lines.append("")

    # Label callers of 0x1260C00 / 0x11456D0 that had config strings
    lines.append("## P0 caller functions — rip strings (context)")
    for rva in (0x112BA30, 0x112C780, 0x112C2B0, 0x114B0DA, 0x112410C, 0x16107C0):
        _o, sz = owner(starts, ends, rva)
        if _o is None:
            continue
        strs = rip_strings(md, data, secs, ib, _o, min(sz, 3000))
        lines.append(f"### caller/nearby 0x{_o:X} size={sz}")
        for site, s in strs[:25]:
            lines.append(f"  @{site:X} {s!r}")
        lines.append("")

    # Global string search for weather / mtVeh / SUPERFLUSH and who refs them
    lines.append("## P0 global string → code xref (selected)")
    needles = [
        b"startWeather",
        b"CfgWorlds",
        b"worldName",
        b"mtVehS",
        b"SUPERFLUSH",
        b"Loading screen closed",
        b"PerformAI",
        b"JobFuture",
        b"InvokerLambda",
    ]
    # Build quick xref: for each needle RVA, find rip-rel from .text via numpy
    _, tva, tvs, traw, _ = text_sec
    tbytes = data[traw : traw + tvs]

    def code_xrefs_to(target_rva, limit=15):
        return code_xrefs_to_rva(tbytes, tva, target_rva, limit)

    for nd in needles:
        rvas = find_string_rvas(data, secs, nd)
        lines.append(f"### string {nd!r}  rvas={ [hex(r) for r in rvas[:3]] }")
        for sr in rvas[:2]:
            x = code_xrefs_to(sr, 12)
            for site in x:
                own, osz = owner(starts, ends, site)
                in_sim = SIM <= site < SIM + SIM_SZ
                lines.append(
                    f"  xref code@0x{site:X} own=0x{(own or 0):X} "
                    f"in_Simulate={in_sim}"
                )
        lines.append("")

    # --- P1: job patterns inside Simulate ---
    lines.append("## P1 Simulate — call timeline of interest")
    oo = rva_off(secs, SIM)
    code = data[oo : oo + SIM_SZ]
    insns = list(md.disasm(code, ib + SIM))

    # Find calls to known large + dispatcher + clear
    interesting = set(LARGE) | {
        0x1A249F0, 0x110AD20, 0x3859C0, 0x1149B0, 0x112F8B0, 0x1139AA0
    }
    # Also find indirect calls (call qword ptr [..]) — job vtable
    lines.append("### direct calls to large/known")
    for ins in insns:
        if ins.mnemonic != "call":
            continue
        site = ins.address - ib
        if ins.op_str.startswith("0x"):
            tgt = int(ins.op_str, 16) - ib
            if tgt in interesting or tgt in LARGE:
                tag = LARGE.get(tgt, "")
                lines.append(f"  0x{site:X}: call 0x{tgt:X} {tag}")
        elif "[" in ins.op_str:
            # indirect
            pass

    lines.append("")
    lines.append("### indirect calls (vtable/job) count by proximity phase")
    phase = Counter()
    indir_sites = []
    for ins in insns:
        if ins.mnemonic == "call" and not ins.op_str.startswith("0x"):
            site = ins.address - ib
            pi = min(7, int((site - SIM) / (SIM_SZ / 8)))
            phase[pi] += 1
            indir_sites.append(site)
    for pi in range(8):
        lines.append(f"  phase{pi}: {phase[pi]} indirect calls")
    lines.append(f"  total indirect: {len(indir_sites)}")
    lines.append("  first/last few:")
    for site in indir_sites[:8] + indir_sites[-4:]:
        lines.append(f"    0x{site:X}")

    # Look for Wait-like: spin with call + test + je backward near JobFuture RTTI construction
    # Search Simulate for lea to InvokerLambda / SoundMainTask RTTI names
    lines.append("")
    lines.append("### Simulate refs to job-related RTTI/strings")
    job_needles = [
        b"SoundMainTask",
        b"InvokerLambda",
        b"JobFuture",
        b"PrepareDrawPrepareCloudlets",
    ]
    for nd in job_needles:
        for m in re.finditer(re.escape(nd), data):
            # only use as part of larger RTTI if possible
            pass
        rvas = []
        for m in re.finditer(rb".{0,40}" + re.escape(nd) + rb".{0,80}", data):
            # too broad
            break
        # find RTTI containing needle
        for m in re.finditer(
            rb"\.\?A[VU][\w@?$<>.-]{0,80}" + re.escape(nd) + rb"[\w@?$<>.-]{0,120}@@",
            data,
        ):
            r = fo_rva(secs, m.start())
            if r:
                rvas.append((r, m.group(0).decode("latin-1", "ignore")[:100]))
        lines.append(f"  RTTI with {nd!r}: {len(rvas)}")
        for r, name in rvas[:4]:
            x = code_xrefs_to(r, 8)
            sim_x = [s for s in x if SIM <= s < SIM + SIM_SZ]
            lines.append(f"    0x{r:X} sim_xrefs={len(sim_x)} all={len(x)}")
            lines.append(f"      {name}")
            for s in sim_x[:5]:
                lines.append(f"      Simulate@{s:X}")

    # SUPERFLUSH block already known — mark offsets
    lines.append("")
    lines.append("## P0/P1 working names (inferred)")
    lines.append(
        "- 0x1260C00: called from startWeather/CfgWorlds-bearing fns → "
        "**World weather / environment tick candidate** (World+0xAC8 object)"
    )
    lines.append(
        "- 0x11456D0: called from CfgWorlds/worldName-bearing fns → "
        "**World config / world-state maintenance candidate**"
    )
    lines.append(
        "- 0x1155340: unique to Simulate; string mtVehS nearby in earlier scan → "
        "**vehicle-related sim step candidate** (confirm)"
    )
    lines.append(
        "- 0x11566C0: sits next to SUPERFLUSH / Loading screen closed → "
        "**memory/stream flush / load-state transition**"
    )
    lines.append(
        "- Indirect calls spread across all phases → continuous vtable/job use; "
        "not a single wait site"
    )

    text = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(text)
    print(text)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
