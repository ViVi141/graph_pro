#!/usr/bin/env python3
r"""Check a real run against the shader catalog: did every GP_replace key hit?

This is the offline half of "did the pack actually do something". It needs no
game process and no shader cache:

    python tools\verify_shaders.py --game "<Arma 3>"            # deployed pack + log
    python tools\verify_shaders.py --game "<Arma 3>" --expect-pbr

Reads <game>\GP_replace.txt (what the proxy was told to replace) and
<game>\GP_universal.log (what it actually replaced), resolves each key through
extract/shader-catalog.csv (name, stage) and prints one row per key.

Exit code 0 only if every key has at least one hit; --expect-pbr additionally
requires the two PSSSSMSuper keys (21144/0945039F, 22872/3DAA0949) to hit.
"""
from __future__ import annotations

import argparse
import collections
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "extract", "shader-catalog.csv")
# The three GP_super_pbr keys. They are deliberately NOT in extract/shader-catalog.csv:
# the shipped .shdc caches are not the complete runtime set, and only a real log can
# decide whether a key is live (these are - see docs/22 section 3).
PBR_KEYS = {(16264, 0x4AC9BAA2), (17992, 0xD7B6AECA), (17960, 0x13052781)}
HIT_RE = re.compile(r"REPLACED PS len=(\d+) crc=([0-9A-Fa-f]{8})")
SSAO_RE = re.compile(r"REPLACED SSAOFinal len=(\d+)")
WARN_RE = re.compile(r"no replacement matched")


def load_catalog():
    if not os.path.exists(CATALOG):
        return {}
    names = {}
    with open(CATALOG, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                key = (int(row["size"]), int(row["crc32"], 16))
            except (KeyError, ValueError):
                continue
            names.setdefault(key, (row["name"], row["stage"]))
    return names


def load_manifest(path):
    keys = []
    if not os.path.exists(path):
        return keys
    for line in open(path, encoding="utf-8", errors="replace"):
        parts = line.split()
        if len(parts) != 3:
            continue
        try:
            keys.append((int(parts[0]), int(parts[1], 16), parts[2]))
        except ValueError:
            continue
    return keys


def parse_log(path):
    hits = collections.Counter()
    ssao = 0
    lines = warned = 0
    if not os.path.exists(path):
        return hits, ssao, 0, False
    for line in open(path, encoding="utf-8", errors="replace"):
        lines += 1
        m = HIT_RE.search(line)
        if m:
            hits[(int(m.group(1)), int(m.group(2), 16))] += 1
        if SSAO_RE.search(line):
            ssao += 1
        if WARN_RE.search(line):
            warned = True
    return hits, ssao, lines, warned


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=os.environ.get("ARMA3_DIR", ""))
    ap.add_argument("--log", default="GP_universal.log")
    ap.add_argument("--expect-pbr", action="store_true")
    ap.add_argument("--allow-empty", action="store_true",
                    help="accept a log with no hits yet (pack deployed, game not run)")
    args = ap.parse_args()
    if not args.game or not os.path.isdir(args.game):
        print("pass --game <Arma 3> or set ARMA3_DIR")
        return 2

    catalog = load_catalog()
    manifest = load_manifest(os.path.join(args.game, "GP_replace.txt"))
    log_path = os.path.join(args.game, args.log)
    hits, ssao, lines, warned = parse_log(log_path)

    print("manifest: %d keys   log: %s (%d lines, %d replacement hits, %d SSAO)"
          % (len(manifest), args.log, lines, sum(hits.values()), ssao))
    if not manifest:
        print("  no GP_replace.txt in the game dir -> pure DXVK or nothing deployed")
        return 0
    if warned:
        print("  WARNING: the proxy logged 'no replacement matched' - fingerprints are stale")

    print("\n%-16s %-32s %-9s %s" % ("key", "shader", "stage", "hits"))
    missing = 0
    for size, crc, payload in manifest:
        name, stage = catalog.get((size, crc), ("(not in catalog)", "?"))
        n = hits.get((size, crc), 0)
        flag = "" if n else "   <-- MISS"
        marked = "*" if (size, crc) in PBR_KEYS else " "
        # a key is only expected to hit if the game actually draws that pass
        print("%s%-16s %-32s %-9s %d%s" % (marked, "%d/%08X" % (size, crc),
                                          name, stage, n, flag))

    # payload drift: the file deployed in the game dir vs the one in dist/,
    # which is what a reinstall would copy. A mismatch means the deployment is
    # older (or newer) than the pack, and every hit above used the wrong bytes.
    dist = os.path.join(ROOT, "dist", "graph_pro_universal", "files")
    drifted = []
    for _size, _crc, payload in manifest:
        got = os.path.join(args.game, payload)
        if not os.path.exists(got):
            drifted.append((payload, "missing in game dir"))
            continue
        sizes = set()
        for d in (os.path.join(dist, "graphics_agx"), os.path.join(dist, "graphics_agx_lite"),
                  os.path.join(dist, "graphics_ssgi"), os.path.join(dist, "graphics_ultra"),
                  os.path.join(dist, "graphics_legacy"), dist):
            cand = os.path.join(d, payload)
            if os.path.exists(cand):
                sizes.add(os.path.getsize(cand))
        # a payload name can differ per pack (tonemap 6672 agx vs 8080 ultra); only
        # flag it when the deployed bytes are in no pack at all.
        if sizes and os.path.getsize(got) not in sizes:
            drifted.append((payload, "deployed %d B, dist has %s" % (
                os.path.getsize(got), "/".join(str(s) for s in sorted(sizes)))))
    if drifted:
        print("\npayload drift (deployment != dist, reinstall before trusting these hits):")
        for name, why in drifted:
            print("  %-24s %s" % (name, why))

    unknown = set(catalog) & set(hits) - {(s, c) for s, c, _ in manifest}
    if unknown:
        print("\nhits with no manifest entry (SSAO-resolve heuristic or stale files):")
        for key in sorted(unknown):
            print("  %d/%08X  %s  x%d" % (key[0], key[1], catalog[key][0], hits[key]))

    pbr_hits = sum(hits.get(k, 0) for k in PBR_KEYS)
    print("\nPBR (PSSSSMSuper) hits: %d" % pbr_hits)

    if args.allow_empty and not hits:
        print("log has no hits yet - run the game once with this pack deployed")
        return 0
    if args.expect_pbr and pbr_hits == 0:
        print("FAIL: --expect-pbr but neither 21144/0945039F nor 22872/3DAA0949 was replaced")
        return 1
    zero = [k for k in manifest if hits.get((k[0], k[1]), 0) == 0]
    if zero and hits:
        print("%d of %d keys never hit - that is normal for passes a scene does not"
              " draw (night tonemap, DOF in clear weather), and fatal only if it is the"
              " pass you care about." % (len(zero), len(manifest)))
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main())
