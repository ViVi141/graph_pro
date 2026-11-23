#!/usr/bin/env python3
r"""Transliterate Arma 3 pixel-shader DXBC assembly back into HLSL.

The catalog (tools/shader_catalog.py) disassembles every shader; this tool turns
that assembly into compilable HLSL whose declarations are the engine's real ABI
(raw float4 constant-buffer arrays, same registers, same input signature). The
body is a straight-line transliteration of the DXBC instructions - not a
refactor, not a optimisation - so the result can be recompiled and diffed
against the original asm.

    python tools\shader_catalog.py --all --asm-stages pp,ps,gs,cs
    python tools\dxbc_to_hlsl.py --cache Shaders_5_0_PP
    python tools\dxbc_to_hlsl.py --cache Shaders_5_0_PP --compile

--compile runs fxc on every generated file and reports instruction-count deltas,
which is the only cheap proof that the transliteration is instruction-complete.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHDC = os.path.join(ROOT, "extract", "shdc")

INSN_RE = re.compile(r"^\s*([a-z][a-z0-9_]*)\s*(.*)$")
DECL_RE = re.compile(r"^\s*(dcl_\w+)\s*(.*)$")
SWZ = set("xyzw")

# opcode -> (operand count, emitter)
SIMPLE = {
    "mov": "{d} = {a};",
    "add": "{d} = {a} + {b};",
    "mul": "{d} = {a} * {b};",
    "mad": "{d} = {a} * {b} + {c};",
    "min": "{d} = min({a}, {b});",
    "max": "{d} = max({a}, {b});",
    "frc": "{d} = frac({a});",
    "floor": "{d} = floor({a});",
    "round_ne": "{d} = round({a});",
    "round_ni": "{d} = floor({a});",
    "round_pi": "{d} = ceil({a});",
    "round_z": "{d} = trunc({a});",
    "rsq": "{d} = rsqrt({a});",
    "sqrt": "{d} = sqrt({a});",
    "exp": "{d} = exp2({a});",
    "log": "{d} = log2({a});",
    "sin": "{d} = sin({a});",
    "cos": "{d} = cos({a});",
    "deriv_rt_fine": "{d} = ddx_fine({a});",
    "deriv_rt_coarse": "{d} = ddx_coarse({a});",
    "deriv_rb_fine": "{d} = ddy_fine({a});",
    "deriv_rb_coarse": "{d} = ddy_coarse({a});",
    "saturate": "{d} = saturate({a});",
    "abs": "{d} = abs({a});",
    "div": "{d} = {a} / {b};",
    "iadd": "{d} = (int4)({a}) + (int4)({b});",
    "imad": "{d} = (int4)({a}) * (int4)({b}) + (int4)({c});",
    "ishl": "{d} = (int4)({a}) << (uint4)({b});",
    "ishr": "{d} = (int4)({a}) >> (uint4)({b});",
    "ushr": "{d} = (uint4)({a}) >> (uint4)({b});",
    "and": "{d} = (uint4)({a}) & (uint4)({b});",
    "or": "{d} = (uint4)({a}) | (uint4)({b});",
    "xor": "{d} = (uint4)({a}) ^ (uint4)({b});",
    "not": "{d} = ~(uint4)({a});",
    "imul": "{d} = (int4)({a}) * (int4)({b});",
    "ieq": "{d} = (int4)((int4)({a}) == (int4)({b}));",
    "ine": "{d} = (int4)((int4)({a}) != (int4)({b}));",
    "ige": "{d} = (int4)((int4)({a}) >= (int4)({b}));",
    "ilt": "{d} = (int4)((int4)({a}) < (int4)({b}));",
    "uge": "{d} = (int4)((uint4)({a}) >= (uint4)({b}));",
    "ult": "{d} = (int4)((uint4)({a}) < (uint4)({b}));",
}
DOT = {"dp2": 2, "dp3": 3, "dp4": 4}
SAMPLE = {"sample": "Sample", "sample_indexable": "SampleLevel",
          "sample_b": "SampleBias", "sample_b_indexable": "SampleBias",
          "sample_d": "SampleGrad", "sample_d_indexable": "SampleGrad",
          "sample_l": "SampleLevel", "sample_l_indexable": "SampleLevel",
          "sample_c": "SampleCmpLevelZero", "sample_c_indexable": "SampleCmpLevelZero"}
CMP = {"lt": "<", "ge": ">=", "eq": "==", "ne": "!="}
FLOW = {"if_nz": "if ({a}) {", "if_z": "if (!{a}) {", "else": "} else {",
        "endif": "}", "loop": "for (;;) {", "endloop": "}",
        "break": "break;", "continue": "continue;"}
CAST = {"ftoi": "asint", "ftou": "asuint", "itof": "(float)asfloat",
        "utof": "(float)asfloat"}
UNSUPPORTED = collections.Counter()


def strip_comment(line: str) -> str:
    i = line.find("//")
    return line[:i] if i >= 0 else line


def parse_asm(text: str) -> dict:
    """Split D3DDisassemble output into declarations and instructions."""
    decls, body, sig, model = {}, [], {}, None
    for raw in text.splitlines():
        line = strip_comment(raw).strip()
        if not line:
            continue
        m = DECL_RE.match(line)
        if m:
            decls.setdefault(m.group(1), []).append(m.group(2).strip())
            continue
        if re.match(r"^(ps|vs|gs|hs|ds|cs)_[45]_[01]$", line):
            model = line
            continue
        if re.match(r"^(ps|vs|gs|hs|ds|cs)_[45]_[01]\s", line):
            model = line.split()[0]
            rest = line[len(model):].strip()
            if rest:
                body.append(rest)
            continue
        if re.match(r"^(Name|Index|Mask|Register)\b", line) or set(line) <= set("- "):
            continue
        body.append(line)
    return {"decls": decls, "body": body, "model": model}


def parse_operand(tok: str):
    """(text, swizzle, neg, abs) of one asm operand."""
    tok = tok.strip()
    neg = absv = False
    while tok and tok[0] in "-|":
        if tok[0] == "-":
            neg = not neg
        else:
            absv = not absv
        tok = tok[1:]
    while tok and tok[-1] == "|":
        absv = not absv
        tok = tok[:-1]
    swz = ""
    m = re.search(r"\.([xyzw]{1,4})$", tok)
    if m and not tok.startswith("l("):
        swz = m.group(1)
        tok = tok[:m.start()]
    return tok, swz, neg, absv


def operand_to_hlsl(tok: str, vec: bool = True) -> str:
    base, swz, neg, absv = parse_operand(tok)
    mreg = re.match(r"^r(\d+)$", base)
    if mreg:
        base = "r[%s]" % mreg.group(1)
    text = base
    if base.startswith("l("):
        inner = base[2:-1]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) == 1:
            text = "((float4)(%s))" % parts[0]
        else:
            text = "float4(%s)" % ", ".join(parts)
    elif base.startswith("cb"):
        m = re.match(r"cb(\d+)\[(.+?)\]$", base)
        if m:
            idx = m.group(2)
            if re.search(r"[rv]\d", idx):
                inner = re.sub(r"\br(\d+)\b", r"r[\1]", idx)
                text = "cb%s[(int)(%s)]" % (m.group(1), inner.replace(" + ", "+").replace(" ", ""))
            else:
                text = "cb%s[%s]" % (m.group(1), idx)
        else:
            text = base
    if swz:
        if len(swz) == 1:
            text = "(%s).%s" % (text, swz)
        elif vec:
            text = "(%s).%s" % (text, swz)
        else:
            text = "(%s).%s" % (text, swz)
    if absv:
        text = "abs(%s)" % text
    if neg:
        text = "-(%s)" % text
    return text


def target_to_hlsl(tok: str) -> str:
    base, swz, _, _ = parse_operand(tok)
    mreg = re.match(r"^r(\d+)$", base)
    if mreg:
        base = "r[%s]" % mreg.group(1)
    name = base
    if swz and len(swz) < 4:
        return "%s.%s" % (name, swz)
    return name


def split_operands(s: str):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def translate(asm: dict, meta: dict, rec: dict) -> tuple:
    body, decls = asm["body"], asm["decls"]
    temps = 8
    m = re.search(r"(\d+)", " ".join(decls.get("dcl_temps", [])))
    if m:
        temps = max(int(m.group(1)), 1)
    used_cb, used_t, used_s, used_v, written_o = set(), set(), set(), set(), set()
    for line in body:
        for m2 in re.finditer(r"\bcb(\d+)\[", line):
            used_cb.add(int(m2.group(1)))
        for m2 in re.finditer(r"\bt(\d+)\b", line):
            used_t.add(int(m2.group(1)))
        for m2 in re.finditer(r"\bs(\d+)\b", line):
            used_s.add(int(m2.group(1)))
        for m2 in re.finditer(r"\bv(\d+)\b", line):
            used_v.add(int(m2.group(1)))
        for m2 in re.finditer(r"\bo(\d+)\b", line):
            written_o.add(int(m2.group(1)))

    # constant-buffer sizes: reflection when available, else highest index used
    cb_sizes = {}
    for cb in meta.get("cbuffers", []):
        pass
    cb_named = meta.get("cbuffers", [])
    for i, cb in enumerate(cb_named):
        cb_sizes.setdefault(i, max(1, (cb.get("size") or 0) // 16))
    for k in used_cb:
        need = 1
        for line in body:
            for m2 in re.finditer(r"\bcb%d\[(\d+)\]" % k, line):
                need = max(need, int(m2.group(1)) + 1)
        cb_sizes[k] = max(cb_sizes.get(k, 1), need)

    inputs = {e["register"]: e for e in meta.get("input", [])}
    # A few shaders read registers their reflected signature does not list; declare
    # them anyway so the transliteration compiles, and flag it.
    missing_inputs = sorted(set(used_v) - set(inputs))
    for reg in missing_inputs:
        inputs[reg] = {"name": "TEXCOORD", "index": max(0, reg - 1)}
    note_inputs = ("// NOTE: registers %s are read but absent from the reflected input\n"
                   "// signature; declared as TEXCOORD here so the file compiles.\n"
                   % ",".join("v%d" % r for r in missing_inputs)) if missing_inputs else ""
    out = []
    out.append("// %s (%s, %d B, crc32 %08X) - transliterated from DXBC" % (
        rec["name"], rec["stage"], rec["size"], rec["crc"]))
    out.append("// %s/%s, %d instructions" % (
        rec["cache"], rec.get("variant", 0), meta.get("instructions", 0)))
    out.append("// Generated by tools/dxbc_to_hlsl.py. Not hand-refactored: every asm")
    out.append("// instruction maps to one HLSL statement (or a TODO if unsupported).")
    if note_inputs:
        out.append(note_inputs.rstrip("\n"))
    if "todo_ops" in dir():
        pass
    out.append("")
    for k in sorted(cb_sizes):
        name = cb_named[k]["name"] if k < len(cb_named) and cb_named[k].get("name") else "CB%d" % k
        out.append("cbuffer %s_reg : register(b%d) { float4 cb%d[%d]; };   // %s, %d B" % (
            name, k, k, cb_sizes[k], name, cb_sizes[k] * 16))
    for t in sorted(used_t):
        out.append("Texture2D    t%d : register(t%d);" % (t, t))
    for s in sorted(used_s):
        out.append("SamplerState s%d : register(s%d);" % (s, s))
    out.append("")
    if inputs:
        out.append("struct PSIn")
        out.append("{")
        for reg in sorted(inputs):
            e = inputs[reg]
            out.append("    float4 iv%d : %s%d;" % (reg, e["name"], e["index"]))
        out.append("};")
        out.append("")
    outs = sorted(written_o) or [0]
    is_vs = rec["stage"].startswith("vs")
    if is_vs:
        out.append("struct VSOut")
        out.append("{")
        for o in outs:
            sem = "SV_Position" if o == 0 else "TEXCOORD%d" % (o - 1)
            out.append("    float4 o%d : %s;" % (o, sem))
        out.append("};")
        out.append("")
        out.append("VSOut main(%s)" % (("PSIn i") if inputs else "float4 pos : SV_Position"))
    elif len(outs) == 1:
        out.append("float4 main(%s) : SV_Target" % ("PSIn i" if inputs else "float4 pos : SV_Position"))
    else:
        out.append("struct PSOut")
        out.append("{")
        for o in outs:
            out.append("    float4 o%d : SV_Target%d;" % (o, o))
        out.append("};")
        out.append("")
        out.append("PSOut main(%s)" % ("PSIn i" if inputs else "float4 pos : SV_Position"))
    out.append("{")
    out.append("    float4 r[%d];" % temps)
    out.append("    for (int _i = 0; _i < %d; ++_i) r[_i] = 0;   // DXBC leaves temps undefined; the" % temps)
    out.append("    // original relies on every read being written first.")
    if inputs:
        for reg in sorted(inputs):
            out.append("    float4 v%d = i.iv%d;   // %s%d" % (
                reg, reg, inputs[reg]["name"], inputs[reg]["index"]))
    for o in outs:
        out.append("    float4 o%d = 0;" % o)
    out.append("")

    unsupported = 0
    todo_ops = collections.Counter()
    for line in body:
        m = INSN_RE.match(line)
        if not m:
            continue
        op, rest = m.group(1), m.group(2)
        # sample opcodes carry a "(texture2d)(float,float,float,float)" prefix
        while rest.startswith("("):
            depth, i2 = 0, 0
            for i2, ch in enumerate(rest):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
            rest = rest[i2 + 1:].lstrip()
        rest = rest.replace("_sat", "")  # modifier tracked separately below
        sat = "_sat" in m.group(1) or line.startswith(op + "_sat")
        opname = op.replace("_sat", "")
        operands = split_operands(rest)
        stmt = None
        try:
            if opname in SIMPLE:
                d = target_to_hlsl(operands[0])
                a = operand_to_hlsl(operands[1])
                b = operand_to_hlsl(operands[2]) if len(operands) > 2 else ""
                c = operand_to_hlsl(operands[3]) if len(operands) > 3 else ""
                stmt = SIMPLE[opname].format(d=d, a=a, b=b, c=c)
            elif opname in DOT:
                n = DOT[opname]
                d = target_to_hlsl(operands[0])
                a = operand_to_hlsl(operands[1])
                b = operand_to_hlsl(operands[2])
                stmt = "%s = dot((%s).xyzw, (%s).xyzw);" % (d, a, b) if n == 4 else \
                       "%s = dot((%s).%s, (%s).%s);" % (d, a, "xyz"[:n], b, "xyz"[:n])
            elif opname in CMP:
                d = target_to_hlsl(operands[0])
                a = operand_to_hlsl(operands[1])
                b = operand_to_hlsl(operands[2])
                stmt = "%s = (float4)((%s) %s (%s));" % (d, a, CMP[opname], b)
            elif opname in FLOW:
                if opname in ("if_nz", "if_z"):
                    stmt = FLOW[opname].replace("{a}", "any(%s)" % operand_to_hlsl(operands[0]))
                else:
                    stmt = FLOW[opname]
            elif opname == "breakc_nz":
                stmt = "if (any(%s)) break;" % operand_to_hlsl(operands[0])
            elif opname == "breakc_z":
                stmt = "if (!any(%s)) break;" % operand_to_hlsl(operands[0])
            elif opname in ("discard_nz", "discard"):
                stmt = "if (any(%s)) discard;" % operand_to_hlsl(operands[0]) if operands else "discard;"
            elif opname in ("discard_z",):
                stmt = "if (!any(%s)) discard;" % operand_to_hlsl(operands[0])
            elif opname == "ret":
                stmt = "// ret"
            elif opname == "movc":
                d = target_to_hlsl(operands[0])
                a = operand_to_hlsl(operands[1])
                b = operand_to_hlsl(operands[2])
                c = operand_to_hlsl(operands[3])
                stmt = "%s = (%s) ? (%s) : (%s);" % (d, a, b, c)
            elif opname in SAMPLE or opname.split("(")[0] in SAMPLE:
                base = opname.split("(")[0]
                d = target_to_hlsl(operands[0])
                coord = operand_to_hlsl(operands[1])
                tex = parse_operand(operands[2])[0]
                samp = parse_operand(operands[3])[0] if len(operands) > 3 else "s0"
                kind = SAMPLE.get(base, "SampleLevel")
                if kind == "SampleLevel":
                    lod = operand_to_hlsl(operands[4]) if len(operands) > 4 else "0"
                    stmt = "%s = %s.%s(%s, (%s).xy, %s);" % (d, tex, kind, samp, coord, lod)
                elif kind == "SampleGrad":
                    stmt = "%s = %s.%s(%s, (%s).xy, ddx((%s).xy), ddy((%s).xy));" % (
                        d, tex, kind, samp, coord, coord, coord)
                else:
                    stmt = "%s = %s.%s(%s, (%s).xy);" % (d, tex, kind, samp, coord)
            elif opname.startswith("ld") or opname.startswith("ld_indexable"):
                d = target_to_hlsl(operands[0])
                coord = operand_to_hlsl(operands[1])
                tex = parse_operand(operands[2])[0]
                stmt = "%s = %s.Load(int3((int2)((%s).xy), 0));" % (d, tex, coord)
            elif opname == "sincos":
                # sincos writes sin then cos into x/y of the destination mask; a
                # single-component destination (the common Arma case) keeps sin.
                d = target_to_hlsl(operands[0])
                a = operand_to_hlsl(operands[-1])
                swz = parse_operand(operands[0])[1]
                if len(swz) >= 2:
                    stmt = "{ float _s, _c; sincos((%s).x, _s, _c); %s.x = _s; %s.y = _c; }" % (a, d, d)
                else:
                    stmt = "%s = sin((%s).x);   // sincos: only sin survives a 1-component dst" % (d, a)
            elif opname == "rcp":
                d = target_to_hlsl(operands[0])
                a = operand_to_hlsl(operands[1])
                stmt = "%s = 1.0 / (%s);" % (d, a)
            elif opname in CAST:
                d = target_to_hlsl(operands[0])
                a = operand_to_hlsl(operands[1])
                cast = {"ftoi": "(int)", "ftou": "(uint)", "itof": "(float)",
                        "utof": "(float)"}[opname]
                stmt = "%s = %s(%s);" % (d, cast, a)
        except IndexError:
            stmt = None
        if sat and stmt and "=" in stmt:
            lhs, rhs = stmt.split("=", 1)
            stmt = "%s= saturate(%s);" % (lhs, rhs.rstrip(";"))
        if stmt is None:
            unsupported += 1
            UNSUPPORTED[opname] += 1
            todo_ops[opname] += 1
            out.append("    // TODO unsupported: %s" % line)
        else:
            out.append("    " + stmt)
    if is_vs:
        out.append("    VSOut result;")
        for o in outs:
            out.append("    result.o%d = o%d;" % (o, o))
        out.append("    return result;")
    elif len(outs) == 1:
        out.append("    return o%d;" % outs[0])
    else:
        out.append("    PSOut result;")
        for o in outs:
            out.append("    result.o%d = o%d;" % (o, o))
        out.append("    return result;")
    out.append("}")
    return "\n".join(out) + "\n", unsupported


def load_catalog(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=os.path.join(SHDC, "catalog.jsonl"))
    ap.add_argument("--disasm", default=os.path.join(SHDC, "disasm"))
    ap.add_argument("--out", default=os.path.join(SHDC, "rewrite"))
    ap.add_argument("--cache", default="Shaders_5_0_PP")
    ap.add_argument("--only", default="")
    ap.add_argument("--stage", default="ps", help="comma list of stages to translate (default ps)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--compile", action="store_true")
    args = ap.parse_args()

    stages = {s.strip() for s in args.stage.split(",")}
    recs = [r for r in load_catalog(args.catalog)
            if r["cache"][:-5] == args.cache and r["stage"].split("_")[0] in stages]
    if args.only:
        recs = [r for r in recs if args.only.lower() in r["name"].lower()]
    if args.limit:
        recs = recs[:args.limit]
    outdir = os.path.join(args.out, args.cache)
    os.makedirs(outdir, exist_ok=True)

    ok = fail = todo_files = 0
    total_todo = 0
    compiled = []
    for r in recs:
        asm_path = os.path.join(args.disasm, args.cache, "%s_%d.asm" % (r["name"], r["variant"]))
        if not os.path.exists(asm_path):
            continue
        asm = parse_asm(open(asm_path, encoding="utf-8", errors="replace").read())
        hlsl, todo = translate(asm, r.get("meta", {}), r)
        total_todo += todo
        if todo:
            todo_files += 1
        path = os.path.join(outdir, "%s_%d.hlsl" % (r["name"], r["variant"]))
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(hlsl)
        if args.compile:
            compiled.append((r, path))

    print("translated %d shaders -> %s" % (len(recs), outdir))
    print("  files with unsupported instructions: %d   total TODO statements: %d" % (
        todo_files, total_todo))
    if UNSUPPORTED:
        print("  top unsupported opcodes:")
        for op, n in UNSUPPORTED.most_common(12):
            print("    %-24s %d" % (op, n))

    if args.compile and compiled:
        fxc = find_fxc()
        if not fxc:
            print("fxc.exe not found; skipping compile check")
            return 0
        good = bad = 0
        deltas = []
        for r, path in compiled:
            d = os.path.join(args.out, "_bin")
            os.makedirs(d, exist_ok=True)
            obj = os.path.join(d, os.path.basename(path) + ".dxbc")
            proc = subprocess.run([fxc, "/nologo", "/T", r["stage"], "/E", "main", "/O2",
                                   "/Fo", obj, path], capture_output=True, text=True)
            if proc.returncode != 0:
                bad += 1
                if bad <= 5:
                    err = (proc.stdout + proc.stderr).strip().splitlines()
                    print("  COMPILE FAIL %s\n    %s" % (
                        os.path.basename(path), " | ".join(err[:3])))
                continue
            good += 1
            ours = instruction_count(obj)
            orig = r.get("meta", {}).get("instructions") or 0
            if orig:
                deltas.append(ours - orig)
        print("  fxc: %d compiled, %d failed" % (good, bad))
        if deltas:
            deltas.sort()
            same = sum(1 for d in deltas if abs(d) <= 2)
            print("  instruction delta vs original: median %d, |d|<=2 for %d/%d (%.0f%%)" % (
                deltas[len(deltas) // 2], same, len(deltas), 100.0 * same / len(deltas)))
    return 0


def find_fxc():
    import glob
    for pat in (r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\fxc.exe",
                r"C:\Program Files (x86)\Windows Kits\10\bin\x64\fxc.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def instruction_count(path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import shader_catalog as sc
    dis = sc.make_disassembler()
    if not dis:
        return 0
    text = dis(open(path, "rb").read())
    m = re.search(r"Approximately (\d+) instruction slots", text)
    return int(m.group(1)) if m else 0


if __name__ == "__main__":
    sys.exit(main())
