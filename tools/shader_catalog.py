#!/usr/bin/env python3
r"""Inventory, disassembly and HLSL skeletons for every shader in Arma 3's caches.

Arma 3 ships nine shader caches inside Dta\bin.pbo:

    Shaders_{4_0,5_0}_{VS,PS,PP,GS,CS}.shdc      (~83 MB, ~9k DXBC blobs)

Extract them first (gitignored):

    python tools\pbo_extract.py "<Arma 3>\Dta\bin.pbo" .shdc extract\shdc

Then, for every DXBC blob in every cache, this tool records the name, stage,
cache, variant index and the (size, crc32) pair the Universal proxy matches on,
disassembles it with D3DDisassemble, parses the metadata that D3DDisassemble
prints (constant buffers, bound resources, input/output signatures) and writes:

    extract\shdc\catalog.jsonl     one line per unique blob
    extract\shdc\catalog.csv       compact table
    extract\shdc\disasm\<cache>\*.asm
    extract\shdc\hlsl\<cache>\*.hlsl   rewrite skeleton with the engine's ABI

Why the disassembly text and not D3DReflect: BiStudio's own RDEF name offsets
are off by one byte relative to what MS reflection expects (names come back as
"OSITION"), while D3DDisassemble resolves them correctly. The text is also what
a human verifying a rewrite wants anyway.
"""
from __future__ import annotations

import argparse
import collections
import ctypes
import csv
import json
import os
import re
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHDC_DIR = os.path.join(ROOT, "extract", "shdc")
OUT_DIR = SHDC_DIR

DXBC_CHUNKS = {"RDEF", "ISGN", "OSGN", "SHDR", "SHEX", "STAT", "SPDB",
               "IFCE", "RD11", "ISG1", "OSG1", "OSG5", "PSG1", "PCSG"}
STAGE_RE = re.compile(rb"([A-Za-z_][A-Za-z0-9_]{1,60})\x00((?:ps|vs|gs|hs|ds|cs)_[45]_[01])\x00([0-9A-F]{8})\x00")
MODEL_RE = re.compile(r"^(ps|vs|gs|hs|ds|cs)_([45]_[01])$", re.M)
CB_RE = re.compile(r"^cbuffer ([\w]+)\s*$")
VAR_RE = re.compile(r"^\s+([A-Za-z][\w\[\]]*)\s+([A-Za-z_]\w*)\s*;\s*(?://\s*Offset:\s*(\d+)\s+Size:\s*(\d+))?")
RES_ROW = re.compile(r"^(\S+)\s+(sampler|texture|cbuffer|buffer|tbuffer|structured|\w+)\s+(\S+)\s+(\S+)\s+([tsub]\d+)\s+(\d+)\s*$")
SIG_ROW = re.compile(r"^(\S+)\s+(\d+)\s+(\w+)\s+(\d+)\s+(\w+)\s+(\w+)\s+(\S*)\s*$")

HLSL_TEX = {"texture2d": "Texture2D", "texture3d": "Texture3D",
            "texturecube": "TextureCube", "texture1d": "Texture1D",
            "buffer": "Buffer", "structured": "StructuredBuffer"}


# --------------------------------------------------------------- .shdc scan
def scan_blobs(buf: bytes):
    """Every DXBC blob in the cache, validated through its own chunk table."""
    out, i = [], 0
    while True:
        pos = buf.find(b"DXBC", i)
        if pos < 0:
            break
        i = pos + 4
        if pos + 32 > len(buf):
            break
        size = struct.unpack_from("<I", buf, pos + 24)[0]
        nchunks = struct.unpack_from("<I", buf, pos + 28)[0]
        if not (64 <= size <= 4 << 20) or not (1 <= nchunks <= 20):
            continue
        if pos + size > len(buf) or 32 + nchunks * 4 > size:
            continue
        prev, ok = 0, True
        for c in range(nchunks):
            o = struct.unpack_from("<I", buf, pos + 32 + c * 4)[0]
            if o < 32 + nchunks * 4 or o + 8 > size or o <= prev:
                ok = False
                break
            fourcc = buf[pos + o:pos + o + 4].decode("latin1")
            csz = struct.unpack_from("<I", buf, pos + o + 4)[0]
            if fourcc not in DXBC_CHUNKS or o + 8 + csz > size:
                ok = False
                break
            prev = o
        if ok:
            out.append({"offset": pos, "size": size})
    return out


def scan_names(buf: bytes):
    return [{"pos": m.start(), "name": m.group(1).decode("latin1"),
             "stage": m.group(2).decode("latin1"), "hash": m.group(3).decode("latin1")}
            for m in STAGE_RE.finditer(buf)]


def scan_cache(path: str):
    name = os.path.basename(path)
    m = re.search(r"Shaders_(\d)_(\d)_(\w+)\.shdc", name)
    kind = m.group(3).lower() if m else "?"
    buf = open(path, "rb").read()
    blobs, heads = scan_blobs(buf), scan_names(buf)
    hi, last, anchor = 0, None, 0
    for bi, b in enumerate(blobs):
        while hi < len(heads) and heads[hi]["pos"] < b["offset"]:
            last = heads[hi]
            anchor = bi
            hi += 1
        b.update({"name": last["name"] if last else "(unnamed)",
                  "stage": last["stage"] if last else "?",
                  "header_hash": last["hash"] if last else "",
                  "variant": bi - anchor,
                  "cache": name, "cache_kind": kind})
    return buf, blobs


# --------------------------------------------------------------- disassembly
def make_disassembler():
    lib = None
    for name in ("d3dcompiler_47", "d3dcompiler_43"):
        try:
            lib = ctypes.WinDLL(name)
            break
        except OSError:
            continue
    if lib is None:
        return None
    fn = lib.D3DDisassemble
    fn.restype = ctypes.c_long
    fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint,
                   ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]

    def run(blob: bytes) -> str:
        out = ctypes.c_void_p()
        buf = ctypes.create_string_buffer(blob, len(blob))
        hr = fn(ctypes.cast(buf, ctypes.c_void_p), len(blob), 0, None, ctypes.byref(out))
        if hr < 0 or not out.value:
            return ""
        vt = ctypes.cast(out, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        get_ptr = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)(vt[3])
        get_len = ctypes.WINFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p)(vt[4])
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vt[2])
        p, n = get_ptr(out), get_len(out)
        text = ctypes.string_at(p, n).decode("latin1", "replace") if p and n else ""
        release(out)
        return text
    return run


def parse_disasm(text: str) -> dict:
    """Metadata out of the tables D3DDisassemble prints above the instructions."""
    meta = {"resources": [], "cbuffers": [], "input": [], "output": []}
    if not text:
        return meta
    lines = [l[3:] if l.startswith("// ") else ("" if l == "//" else l) for l in text.splitlines()]
    section, blank_run = None, 0
    cur_cb = None
    for raw in lines:
        s = raw.rstrip()
        low = s.strip()
        if not low:
            blank_run += 1
            continue
        blank_run = 0
        if low.endswith("Resource Bindings:"):
            section, cur_cb = "res", None
            continue
        if low.endswith("Buffer Definitions:"):
            section, cur_cb = "cb", None
            continue
        if low.endswith("Input signature:"):
            section, cur_cb = "in", None
            continue
        if low.endswith("Output signature:"):
            section, cur_cb = "out", None
            continue
        if set(low) <= set("- "):
            continue                      # table rule
        if low.startswith("Name ") and section in ("res", "in", "out"):
            continue                      # table header
        if section == "res":
            m = RES_ROW.match(low)
            if m:
                meta["resources"].append({"name": m.group(1), "type": m.group(2),
                                          "format": m.group(3), "dim": m.group(4),
                                          "bind": m.group(5), "count": int(m.group(6))})
        elif section in ("in", "out"):
            m = SIG_ROW.match(low)
            if m and not m.group(1).startswith("-"):
                meta["input" if section == "in" else "output"].append({"name": m.group(1), "index": int(m.group(2)),
                                      "mask": m.group(3), "register": int(m.group(4)),
                                      "system": m.group(5), "format": m.group(6),
                                      "used": m.group(7)})
        elif section == "cb":
            if low.startswith("cbuffer "):
                name = low[len("cbuffer "):].strip()
                cur_cb = {"name": name, "size": 0, "vars": []}
                meta["cbuffers"].append(cur_cb)
                continue
            if low == "}" or low.startswith("};"):
                cur_cb = None
                continue
            if cur_cb is not None:
                m = VAR_RE.match(s)
                if m:
                    off = int(m.group(3)) if m.group(3) else 0
                    sz = int(m.group(4)) if m.group(4) else 0
                    cur_cb["vars"].append({"hlsl": m.group(1), "name": m.group(2),
                                           "offset": off, "size": sz})
                    cur_cb["size"] = max(cur_cb["size"], off + sz)
        else:
            m = MODEL_RE.match(low)
            if m and "model" not in meta:
                meta["model"] = low
                section = "body"
    m = MODEL_RE.search(text)
    if m and "model" not in meta:
        meta["model"] = m.group(0)
    tail = re.search(r"Approximately (\d+) instruction slots", text)
    if tail:
        meta["instructions"] = int(tail.group(1))
    meta["asm_lines"] = text.count("\n")
    return meta


# --------------------------------------------------------------- HLSL skeleton
def hlsl_skeleton(rec: dict) -> str:
    meta = rec.get("meta", {})
    out = ["// %s   (%s, %d B, crc32 %08X)" % (rec["name"], rec["stage"], rec["size"], rec["crc"]),
           "// cache=%s variant=%d model=%s instructions=%s" % (
               rec["cache"], rec["variant"], meta.get("model", "?"),
               meta.get("instructions", "?")),
           "// Generated by tools/shader_catalog.py. The declarations are the engine ABI,",
           "// taken from D3DDisassemble; the body is what a rewrite has to fill in.",
           "// Replace it as (size=%d, crc=%08X) in GP_replace.txt." % (rec["size"], rec["crc"]),
           ""]
    for cb in meta.get("cbuffers", []):
        out.append("cbuffer %s : register(b0)   // %d B, %d vars" % (
            cb["name"], cb["size"], len(cb["vars"])))
        out.append("{")
        for v in cb["vars"]:
            out.append("    %s %s;   // +%d, %d B" % (v["hlsl"], v["name"], v["offset"], v["size"]))
        out.append("};")
        out.append("")
    for r in meta.get("resources", []):
        bind = r["bind"]
        if r["type"] == "sampler":
            out.append("SamplerState %s : register(%s);" % (r["name"], bind))
        elif bind.startswith("t"):
            decl = HLSL_TEX.get(r["type"], "Texture2D")
            out.append("%s %s : register(%s);   // %s %s" % (
                decl, r["name"], bind, r["format"], r["dim"]))
    out.append("")
    sig = meta.get("input") or []
    if sig:
        out.append("struct PSIn   // input signature")
        out.append("{")
        for e in sig:
            out.append("    float4 %s : %s%d;" % (e["name"].lower(), e["name"], e["index"]))
        out.append("};")
        out.append("")
        out.append("float4 main(PSIn i) : SV_Target")
    else:
        out.append("float4 main(float4 pos : SV_Position) : SV_Target")
    out += ["{", "    return 0;   // TODO: port the body from the .asm", "}", ""]
    return "\n".join(out)


# --------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shdc", default=SHDC_DIR)
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--scan", action="store_true", help="counts only, no output")
    ap.add_argument("--asm-stages", default="ps,pp,gs,cs",
                    help="cache kinds that get .asm files (default ps,pp,gs,cs; 'all' for every stage)")
    ap.add_argument("--no-asm", action="store_true")
    ap.add_argument("--no-hlsl", action="store_true")
    ap.add_argument("--only", default="", help="substring filter on the shader name")
    ap.add_argument("--stats", action="store_true", help="print the catalog summary")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.shdc) if f.endswith(".shdc"))
    if not files:
        print("no .shdc in %s - extract them from Dta\\bin.pbo first" % args.shdc)
        return 2

    if args.stats:
        path = os.path.join(args.out, "catalog.jsonl")
        recs = [json.loads(l) for l in open(path, encoding="utf-8")]
        return print_stats(recs)

    asm_stages = {x.strip() for x in args.asm_stages.split(",")}
    dis = None if args.scan or args.no_asm else make_disassembler()

    records, total = [], 0
    seen = {}
    for fn in files:
        buf, blobs = scan_cache(os.path.join(args.shdc, fn))
        total += len(blobs)
        for b in blobs:
            if args.only and args.only.lower() not in b["name"].lower():
                continue
            blob = buf[b["offset"]:b["offset"] + b["size"]]
            crc = zlib.crc32(blob) & 0xFFFFFFFF
            rec = {"name": b["name"], "stage": b["stage"], "cache": fn,
                   "variant": b["variant"], "offset": b["offset"], "size": b["size"],
                   "crc": crc, "cache_kind": b["cache_kind"]}
            if args.scan:
                records.append(rec)
                continue
            key = (b["size"], crc)
            if key in seen:
                seen[key]["aliases"].append("%s/%s" % (fn[:-5], b["name"]))
                continue
            rec["aliases"] = []
            if dis:
                text = dis(blob)
                rec["meta"] = parse_disasm(text)
                if text and not args.no_asm and (b["cache_kind"] in asm_stages or "all" in asm_stages):
                    d = os.path.join(args.out, "disasm", fn[:-5])
                    os.makedirs(d, exist_ok=True)
                    with open(os.path.join(d, "%s_%d.asm" % (b["name"], b["variant"])),
                              "w", encoding="utf-8", newline="\n") as g:
                        g.write(text)
            else:
                rec["meta"] = {}
            seen[key] = rec
            records.append(rec)

    if args.scan:
        print("%-24s %s" % ("cache", "blobs"))
        for fn in files:
            n = sum(1 for r in records if r["cache"] == fn)
            print("%-24s %5d" % (fn, n))
        print("total blobs: %d" % len(records))
        return 0

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "catalog.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(args.out, "catalog.csv"), "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(["name", "stage", "cache", "variant", "size", "crc32",
                    "instructions", "cbuffers", "resources", "asm_lines"])
        for r in records:
            m = r.get("meta", {})
            w.writerow([r["name"], r["stage"], r["cache"], r["variant"], r["size"],
                        "%08X" % r["crc"], m.get("instructions", ""),
                        len(m.get("cbuffers", [])), len(m.get("resources", [])),
                        m.get("asm_lines", "")])

    if not args.no_hlsl:
        for r in records:
            d = os.path.join(args.out, "hlsl", r["cache"][:-5])
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "%s_%d.hlsl" % (r["name"], r["variant"])),
                      "w", encoding="utf-8", newline="\n") as g:
                g.write(hlsl_skeleton(r))

    stages = collections.Counter(r["stage"] for r in records)
    print("unique shaders: %d   (blobs scanned %d, duplicates folded %d)" % (
        len(records), total, total - len(records)))
    for s, n in sorted(stages.items(), key=lambda kv: -kv[1]):
        print("  %-10s %4d" % (s, n))
    print("wrote", os.path.join(args.out, "catalog.jsonl"))
    return 0


def print_stats(recs) -> int:
    print("unique shaders:", len(recs))
    by_stage = collections.Counter(r["stage"] for r in recs)
    for s, n in sorted(by_stage.items(), key=lambda kv: -kv[1]):
        print("  %-10s %4d" % (s, n))
    print("\ncaches:")
    for c, n in sorted(collections.Counter(r["cache"] for r in recs).items()):
        print("  %-24s %5d" % (c, n))
    ins = [r["meta"].get("instructions", 0) for r in recs if r["meta"].get("instructions")]
    if ins:
        ins.sort()
        print("\ninstructions: median %d  p90 %d  max %d  (n=%d)" % (
            ins[len(ins) // 2], ins[int(len(ins) * 0.9)], ins[-1], len(ins)))
    cbs = [(len(r["meta"].get("cbuffers", [])), r) for r in recs]
    print("\nshaders with >=1 cbuffer: %d" % sum(1 for c, _ in cbs if c))
    print("shaders with 0 resources : %d" % sum(1 for r in recs if not r["meta"].get("resources")))
    big = sorted(cbs, key=lambda t: -t[0])[:5]
    for c, r in big:
        print("  %-40s %s cb=%d %d B" % (r["name"], r["stage"], c, r["size"]))
    pp = [r for r in recs if r["name"].startswith(("PSPostProcess", "VSPostProcess"))]
    print("\npost-process family: %d shaders" % len(pp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
