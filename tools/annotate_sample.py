"""Annotate GP_sample_top.txt with known RVAs and coarse size-class tags."""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWN = os.path.join(ROOT, "extract", "cpu_samples", "known_rva.txt")
OUT_DIR = os.path.join(ROOT, "extract", "cpu_samples")


def load_known(path: str) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"\s+", line, maxsplit=1)
            if len(parts) < 2:
                continue
            rows.append((int(parts[0], 16), parts[1]))
    rows.sort()
    return rows


def label_for(rva: int, known: list[tuple[int, str]], size: int) -> str:
    # Exact or containing known symbol start within this function span is unknown;
    # match if known RVA falls inside [rva, rva+size) or equals start.
    for kr, name in known:
        if kr == rva or (rva <= kr < rva + size):
            return name
    if size >= 8000:
        return "large_orchestrator?"
    if size <= 128:
        return "tiny_leaf?"
    if size <= 600:
        return "small_fn"
    return "mid_fn"


def parse_top(path: str) -> list[tuple[int, float, int, int]]:
    rows: list[tuple[int, float, int, int]] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # hits pct rva size
            m = re.match(
                r"(\d+)\s+([\d.]+)\s+0x([0-9A-Fa-f]+)\s+(\d+)", line
            )
            if not m:
                continue
            hits = int(m.group(1))
            pct = float(m.group(2))
            rva = int(m.group(3), 16)
            size = int(m.group(4))
            rows.append((hits, pct, rva, size))
    return rows


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: annotate_sample.py <GP_sample_top.txt>")
        return 2
    src = sys.argv[1]
    if not os.path.isfile(src):
        print("missing", src)
        return 1
    known = load_known(KNOWN)
    rows = parse_top(src)
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "annotated_latest.txt")
    lines = [
        f"# annotated from {src}",
        "# hits  pct     rva         size   tag",
    ]
    for hits, pct, rva, size in rows:
        tag = label_for(rva, known, size)
        line = f"{hits:6d}  {pct:6.2f}%  0x{rva:08X}  {size:6d}  {tag}"
        lines.append(line)
        print(line)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
