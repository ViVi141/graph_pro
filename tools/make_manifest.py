"""Write dist/graph_pro_universal/MANIFEST.json: git commit + sha256 of every file.

The Universal line ships as a local dist/ tree (binary artifacts are gitignored),
so nothing in git says which build a user actually received. This manifest
travels with the release and lets tools/verify_universal.ps1 answer
"is the deployed d3d11.dll the build we think it is?".

    python tools/make_manifest.py                 # dist/graph_pro_universal
    python tools/make_manifest.py --dist <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIST = os.path.join(ROOT, "dist", "graph_pro_universal")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=DEFAULT_DIST, help="release tree to index")
    ap.add_argument("--out", default="", help="manifest path (default: <dist>/MANIFEST.json)")
    args = ap.parse_args()

    dist = os.path.abspath(args.dist)
    if not os.path.isdir(dist):
        print("missing dist dir: %s" % dist)
        return 2
    out = args.out or os.path.join(dist, "MANIFEST.json")

    files = {}
    for dirpath, _dirnames, filenames in os.walk(dist):
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.abspath(full) == os.path.abspath(out):
                continue
            rel = os.path.relpath(full, dist).replace(os.sep, "/")
            files[rel] = {"sha256": sha256(full), "bytes": os.path.getsize(full)}

    manifest = {
        "product": "GraphPro Universal",
        "git_commit": git("rev-parse", "HEAD"),
        "git_commit_short": git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "git_describe": git("describe", "--always", "--dirty"),
        "files": dict(sorted(files.items())),
    }
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("wrote %s (%d files, commit %s%s)" % (
        out, len(files), manifest["git_commit_short"],
        " dirty" if manifest["git_dirty"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
