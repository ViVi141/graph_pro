#!/usr/bin/env python3
"""Hunt sun-like float3 slots across day / dusk / indoor CB dumps.

Usage:
  python tools/cb_sun_hunt.py <day_dir> <dusk_dir> <indoor_dir> [--out inject/presets/GP_light_bind.txt]

Each dir should contain GP_cb_<size>_<n>.f32 dumps (from GP_cb_dump.txt) and
optionally GP_cb_index.txt. Ranking prefers:
  - near-unit length in day & dusk
  - large angular change day→dusk
  - near-zero or collapsed length indoors (or stable fake fill-light)
"""
from __future__ import annotations

import argparse
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np


def load_dumps(folder: Path) -> dict[int, list[np.ndarray]]:
    by_size: dict[int, list[np.ndarray]] = defaultdict(list)
    for p in sorted(folder.glob("GP_cb_*.f32")):
        # GP_cb_<size>_<n>.f32
        parts = p.stem.split("_")
        if len(parts) < 3:
            continue
        try:
            size = int(parts[2])
        except ValueError:
            continue
        raw = p.read_bytes()
        n = len(raw) // 4
        arr = np.frombuffer(raw, dtype=np.float32, count=n)
        by_size[size].append(arr)
    return by_size


def mean_buf(bufs: list[np.ndarray]) -> np.ndarray | None:
    if not bufs:
        return None
    n = min(b.size for b in bufs)
    stacked = np.stack([b[:n] for b in bufs], axis=0)
    return stacked.mean(axis=0)


def candidates(day: np.ndarray, dusk: np.ndarray, indoor: np.ndarray | None, size: int):
    n = min(day.size, dusk.size)
    if indoor is not None:
        n = min(n, indoor.size)
    rows = []
    for i in range(0, n - 2):
        d = day[i : i + 3]
        u = dusk[i : i + 3]
        ld = float(np.linalg.norm(d))
        lu = float(np.linalg.norm(u))
        if not (0.85 <= ld <= 1.15 and 0.85 <= lu <= 1.15):
            continue
        dn = d / ld
        un = u / lu
        ang = float(np.degrees(np.arccos(np.clip(np.dot(dn, un), -1, 1))))
        indoor_len = 0.0
        indoor_score = 0.0
        if indoor is not None:
            inn = indoor[i : i + 3]
            indoor_len = float(np.linalg.norm(inn))
            # Prefer slots that collapse indoors or stay a weak fill.
            if indoor_len < 0.25:
                indoor_score = 1.0
            elif indoor_len < 0.85:
                indoor_score = 0.4
            else:
                indoor_score = 0.0
        else:
            indoor_score = 0.5
        # Day→dusk should move (sun arc); reject identical dirs.
        if ang < 5.0:
            continue
        score = ang + 40.0 * indoor_score
        rows.append(
            {
                "size": size,
                "idx": i,
                "score": score,
                "ang_deg": ang,
                "day": dn,
                "dusk": un,
                "indoor_len": indoor_len,
            }
        )
    rows.sort(key=lambda r: -r["score"])
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("day_dir", type=Path)
    ap.add_argument("dusk_dir", type=Path)
    ap.add_argument("indoor_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    day_m = load_dumps(args.day_dir)
    dusk_m = load_dumps(args.dusk_dir)
    indoor_m = load_dumps(args.indoor_dir)
    sizes = sorted(set(day_m) & set(dusk_m))
    if not sizes:
        print("no overlapping CB sizes between day and dusk")
        return

    all_rows = []
    for size in sizes:
        d = mean_buf(day_m[size])
        u = mean_buf(dusk_m[size])
        inn = mean_buf(indoor_m[size]) if size in indoor_m else None
        if d is None or u is None:
            continue
        all_rows.extend(candidates(d, u, inn, size))

    all_rows.sort(key=lambda r: -r["score"])
    if not all_rows:
        print("no unit-float3 candidates with day/dusk angle > 5 deg")
        return

    print(f"{'rank':>4} {'size':>6} {'idx':>5} {'score':>8} {'ang':>7} {'inLen':>6}  day                    dusk")
    for rank, r in enumerate(all_rows[: args.top], 1):
        d = r["day"]
        u = r["dusk"]
        print(
            f"{rank:4d} {r['size']:6d} {r['idx']:5d} {r['score']:8.2f} {r['ang_deg']:7.2f} "
            f"{r['indoor_len']:6.3f}  "
            f"({d[0]:+.3f},{d[1]:+.3f},{d[2]:+.3f})  "
            f"({u[0]:+.3f},{u[1]:+.3f},{u[2]:+.3f})"
        )

    best = all_rows[0]
    line = f"{best['size']} {best['idx']}\n"
    print(f"\nbest bind: {line.strip()}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(line, encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
