"""P3: catalog all indirect calls inside simstep 0x1155340 (post-ParallelFor)."""
from __future__ import annotations

import collections
import os
import struct

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import (
    X86_OP_IMM,
    X86_OP_MEM,
    X86_OP_REG,
    X86_REG_RIP,
)

EXE = r"<ARMA3>\Arma3_x64.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "extract", "cpu_samples", "simstep_indirect.txt")
STEP, STEP_SZ = 0x1155340, 4604
PF = 0x10FCE10


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


def main():
    data, ib, secs = load_pe(EXE)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    oo = rva_off(secs, STEP)
    code = data[oo : oo + STEP_SZ]

    pf_site = None
    sites = []
    # also keep a sliding window of previous insns for context
    prev = []
    for ins in md.disasm(code, ib + STEP):
        rva = ins.address - ib
        if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
            if int(ins.op_str, 16) - ib == PF:
                pf_site = rva
        if ins.mnemonic == "call" and not ins.op_str.startswith("0x"):
            raw = bytes(ins.bytes)
            kind = "reg"
            slot = None
            base = None
            mem_str = ins.op_str
            if ins.operands and ins.operands[0].type == X86_OP_MEM:
                kind = "mem"
                m = ins.operands[0].mem
                slot = m.disp
                base = ins.reg_name(m.base) if m.base else None
                if m.base == X86_REG_RIP:
                    kind = "rip"
                    slot = (ins.address + ins.size + m.disp) - ib
            elif ins.operands and ins.operands[0].type == X86_OP_REG:
                kind = "reg"
                base = ins.reg_name(ins.operands[0].reg)
            sites.append(
                {
                    "rva": rva,
                    "size": ins.size,
                    "raw": raw.hex(),
                    "text": f"{ins.mnemonic} {ins.op_str}",
                    "kind": kind,
                    "base": base,
                    "slot": slot,
                    "prev": list(prev[-4:]),
                    "after_pf": pf_site is not None and rva > pf_site,
                }
            )
        prev.append(f"{rva:08X}: {ins.mnemonic} {ins.op_str}")
        if len(prev) > 8:
            prev.pop(0)

    lines = []
    lines.append(f"# simstep indirect calls  STEP=0x{STEP:X}  PF_site={pf_site:#x}")
    lines.append(f"# total={len(sites)} after_pf={sum(1 for s in sites if s['after_pf'])}")
    lines.append("")

    # group by (kind, base, slot)
    groups = collections.Counter()
    for s in sites:
        if not s["after_pf"]:
            continue
        key = (s["kind"], s["base"], s["slot"])
        groups[key] += 1

    lines.append("## groups (kind, base, slot/disp) after ParallelFor")
    for (kind, base, slot), n in groups.most_common():
        slot_s = f"0x{slot:X}" if isinstance(slot, int) and slot is not None else str(slot)
        lines.append(f"  {n:2d}x  {kind:4s} base={base} slot={slot_s}")
    lines.append("")

    lines.append("## sites (after ParallelFor only)")
    for i, s in enumerate(sites):
        if not s["after_pf"]:
            continue
        slot_s = (
            f"0x{s['slot']:X}" if isinstance(s["slot"], int) and s["slot"] is not None else "-"
        )
        lines.append(
            f"[{i:02d}] RVA=0x{s['rva']:X} sz={s['size']} raw={s['raw']}  "
            f"{s['text']}  kind={s['kind']} slot={slot_s}"
        )
        for p in s["prev"]:
            lines.append(f"      | {p}")
        lines.append("")

    # size histogram for patch feasibility
    lines.append("## size histogram (after PF)")
    sc = collections.Counter(s["size"] for s in sites if s["after_pf"])
    for sz, n in sorted(sc.items()):
        note = "E8-fit" if sz >= 5 else "need-steal"
        lines.append(f"  sz={sz}: {n}  ({note})")

    text = "\n".join(lines) + "\n"
    open(OUT, "w", encoding="utf-8").write(text)
    print(text)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
