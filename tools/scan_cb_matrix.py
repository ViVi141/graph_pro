#!/usr/bin/env python3
"""Scan GP_cb_*.raw dumps for 4x4 affine matrices (Gate 2 helper)."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np


def looks_affine(m: np.ndarray) -> bool:
    """m is 4x4 row-major float32."""
    if m.shape != (4, 4):
        return False
    # last row ~ (0,0,0,1) or last col
    if abs(m[3, 3] - 1.0) > 0.15:
        return False
    baselen = np.linalg.norm(m[:3, :3], axis=0)
    if np.any(baselen < 0.2) or np.any(baselen > 8.0):
        return False
    # rough orthogonality of basis
    b = m[:3, :3]
    dots = abs(np.dot(b[:, 0], b[:, 1])) + abs(np.dot(b[:, 0], b[:, 2])) + abs(
        np.dot(b[:, 1], b[:, 2])
    )
    return dots < 0.75


def scan_file(path: Path) -> list[int]:
    raw = path.read_bytes()
    if len(raw) < 64:
        return []
    floats = np.frombuffer(raw[: len(raw) - (len(raw) % 4)], dtype="<f4")
    hits = []
    for i in range(0, len(floats) - 15):
        m = floats[i : i + 16].reshape(4, 4)
        if looks_affine(m):
            hits.append(i * 4)
    return hits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", type=Path, nargs="?", default=Path(r"<ARMA3>"))
    args = ap.parse_args()
    files = sorted(args.dir.glob("GP_cb_*.raw"))
    if not files:
        print(f"no GP_cb_*.raw under {args.dir}")
        return
    n_hit = 0
    for f in files:
        offs = scan_file(f)
        if offs:
            n_hit += 1
            print(f"{f.name}: matrix@ {offs[:8]}")
        else:
            print(f"{f.name}: none")
    print(f"summary: {n_hit}/{len(files)} files contain affine 4x4")


if __name__ == "__main__":
    main()
