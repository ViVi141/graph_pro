"""Print comparison table for extract/bench_7900x/*.json runs."""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "extract", "bench_7900x")


def main() -> int:
    files = sorted(glob.glob(os.path.join(DIR, "*.json")))
    if not files:
        print("No benchmark JSON files found in", DIR)
        return 0
    rows = []
    for p in files:
        with open(p, encoding="utf-8-sig") as f:
            rows.append(json.load(f))

    base_fps = None
    for r in rows:
        if r.get("yaabfps"):
            base_fps = r["yaabfps"]
            break

    print(
        f"{'Tag':<24} {'AvgFPS':>7} {'Delta':>7} {'1%Low':>7} {'0.1%Low':>8} "
        f"{'P50ms':>6} {'P95ms':>6} {'P99ms':>6} {'DXVK':>5} {'Aff':>8} {'Malloc'}"
    )
    print("-" * 112)
    for r in rows:
        fps = r.get("yaabfps")
        if fps is None:
            print(f"{r.get('tag','?'):<24}  (no result)")
            continue
        delta = f"{((fps / base_fps) - 1.0) * 100:+.1f}%" if base_fps else ""
        alloc = r.get("malloc") or "default"
        print(
            f"{r['tag']:<24} {fps:7.2f} {delta:>7} {r.get('low1_fps',0):7.2f} {r.get('low01_fps',0):8.2f} "
            f"{r.get('p50_ms',0):6.2f} {r.get('p95_ms',0):6.2f} {r.get('p99_ms',0):6.2f} "
            f"{'YES' if r.get('use_dxvk') else 'no':>5} {(r.get('affinity') or '-'):>8} {alloc}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

