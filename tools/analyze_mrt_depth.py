# -*- coding: utf-8 -*-
"""Analyze GP_probe_mrt dumps: N1 RT census (normals?) + N2 depth timeline (clean depth?)."""
from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# DXGI_FORMAT enum values we care about
FMT_NAMES = {
    2: "R32G32B32A32_FLOAT",
    10: "R16G16B16A16_FLOAT",
    11: "R16G16B16A16_UNORM",
    24: "R10G10B10A2_UNORM",
    26: "R11G11B10_FLOAT",
    28: "R8G8B8A8_UNORM",
    29: "R8G8B8A8_UNORM_SRGB",
    34: "R16G16_FLOAT",
    41: "R32_FLOAT",
    44: "R24G8_TYPELESS",
    45: "D24_UNORM_S8_UINT",
    61: "R8_UNORM",
    87: "B8G8R8A8_UNORM",
    91: "B8G8R8A8_UNORM_SRGB",
}

NORMALISH = {2, 10, 11, 24, 28, 29, 87, 91}


def bpp_for(fmt: int) -> int:
  return {
      2: 16,
      10: 8,
      11: 8,
      24: 4,
      26: 4,
      28: 4,
      29: 4,
      34: 4,
      41: 4,
      44: 4,
      45: 4,
      61: 1,
      87: 4,
      91: 4,
  }.get(fmt, 4)


def half_to_float(h: int) -> float:
  sign = (h >> 15) & 1
  exp = (h >> 10) & 0x1F
  mant = h & 0x3FF
  if exp == 0:
    if mant == 0:
      return -0.0 if sign else 0.0
    val = (mant / 1024.0) * (2 ** -14)
  elif exp == 31:
    return float("nan")
  else:
    val = (1.0 + mant / 1024.0) * (2 ** (exp - 15))
  return -val if sign else val


def load_raw_rgb(path: Path, fmt: int, w: int, h: int) -> np.ndarray:
  data = path.read_bytes()
  bpp = bpp_for(fmt)
  expect = w * h * bpp
  if len(data) < expect:
    raise ValueError(f"{path.name}: size {len(data)} < {expect}")
  arr = np.frombuffer(data[:expect], dtype=np.uint8).reshape(h, w, bpp)

  if fmt in (28, 29):
    return arr[:, :, :3].astype(np.float32) / 255.0
  if fmt in (87, 91):
    bgr = arr[:, :, :3].astype(np.float32) / 255.0
    return bgr[:, :, ::-1].copy()
  if fmt == 24:
    u = arr.view(np.uint32)[:, :, 0]
    r = ((u >> 0) & 0x3FF).astype(np.float32) / 1023.0
    g = ((u >> 10) & 0x3FF).astype(np.float32) / 1023.0
    b = ((u >> 20) & 0x3FF).astype(np.float32) / 1023.0
    return np.stack([r, g, b], axis=-1)
  if fmt in (10, 11):
    u16 = arr.view(np.uint16).reshape(h, w, 4)
    if fmt == 10:
      rgb = np.empty((h, w, 3), np.float32)
      for c in range(3):
        flat = u16[:, :, c].reshape(-1)
        rgb[:, :, c] = np.array([half_to_float(int(v)) for v in flat], np.float32).reshape(h, w)
      return np.clip(rgb, 0, 1)
    return u16[:, :, :3].astype(np.float32) / 65535.0
  if fmt == 2:
    f = np.frombuffer(data[:expect], dtype=np.float32).reshape(h, w, 4)
    return np.clip(f[:, :, :3], 0, 1)
  # fallback: first 3 bytes as unorm
  if bpp >= 3:
    return arr[:, :, :3].astype(np.float32) / 255.0
  g = arr[:, :, 0].astype(np.float32) / 255.0
  return np.stack([g, g, g], axis=-1)


def normal_score(rgb: np.ndarray) -> dict:
  # assume encoded as n*0.5+0.5
  n = rgb * 2.0 - 1.0
  length = np.linalg.norm(n, axis=-1)
  mean_len = float(np.nanmean(length))
  near1 = float(np.mean(np.abs(length - 1.0) < 0.15))
  hemisphere = float(np.mean(n[:, :, 2] > 0))
  return {"mean_len": mean_len, "frac_unit": near1, "frac_hemi_z": hemisphere}


def parse_census(path: Path) -> list[dict]:
  rows = []
  if not path.exists():
    return rows
  for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
    line = line.strip()
    m = re.match(
        r"^([rsd])\s+fmt=(\d+)\s+(\d+)x(\d+)\s+samples=(\d+)\s+bind=(\d+)", line
    )
    if m:
      rows.append(
          {
              "kind": m.group(1),
              "fmt": int(m.group(2)),
              "w": int(m.group(3)),
              "h": int(m.group(4)),
              "samples": int(m.group(5)),
              "bind": int(m.group(6)),
          }
      )
      continue
    m = re.match(r"^dump\s+(GP_mrt_(\d+)_(\d+)x(\d+)\.raw)\s+fmt=(\d+)\s+bpp=(\d+)", line)
    if m:
      rows.append(
          {
              "kind": "dump",
              "file": m.group(1),
              "fmt": int(m.group(2)),
              "w": int(m.group(3)),
              "h": int(m.group(4)),
              "bpp": int(m.group(6)),
          }
      )
  return rows


def parse_timeline(path: Path) -> list[dict]:
  rows = []
  if not path.exists():
    return rows
  for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
    m = re.search(
        r"present=(\d+).*fmt=(\d+)\s+min=([\d.]+)\s+max=([\d.]+)\s+avg=([\d.]+)\s+"
        r"sky%=([\d.]+)\s+cloud%=([\d.]+)\s+stencil_nz%=([-\d.]+)",
        line,
    )
    if m:
      rows.append(
          {
              "present": int(m.group(1)),
              "fmt": int(m.group(2)),
              "min": float(m.group(3)),
              "max": float(m.group(4)),
              "avg": float(m.group(5)),
              "sky": float(m.group(6)),
              "cloud": float(m.group(7)),
              "stencil": float(m.group(8)),
          }
      )
  return rows


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument(
      "indir",
      nargs="?",
      default=r"D:\SteamLibrary\steamapps\common\Arma 3",
      help="directory with GP_mrt_census.txt / GP_depth_timeline.txt / raw dumps",
  )
  ap.add_argument(
      "--demo",
      default=r"c:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo",
      help="output demo dir",
  )
  args = ap.parse_args()
  indir = Path(args.indir)
  demo = Path(args.demo)
  demo.mkdir(parents=True, exist_ok=True)

  census = parse_census(indir / "GP_mrt_census.txt")
  timeline = parse_timeline(indir / "GP_depth_timeline.txt")
  dumps = [r for r in census if r.get("kind") == "dump"]
  rtv = [r for r in census if r.get("kind") == "r"]
  srv = [r for r in census if r.get("kind") == "s"]
  dsv = [r for r in census if r.get("kind") == "d"]

  print("=== N1 RT census ===")
  print(f"unique rtv={len(rtv)} srv={len(srv)} dsv={len(dsv)} dumps={len(dumps)}")
  for r in rtv + srv + dsv:
    name = FMT_NAMES.get(r["fmt"], "?")
    flag = " NORMALISH" if r["fmt"] in NORMALISH and r["kind"] in ("r", "s") else ""
    print(
        f"  {r['kind']} fmt={r['fmt']}({name}) {r['w']}x{r['h']} "
        f"samples={r['samples']} bind={r['bind']}{flag}"
    )

  tiles = []
  scores = []
  for d in dumps:
    path = indir / d["file"]
    if not path.exists():
      # also try without depending on dump line
      alt = list(indir.glob(f"GP_mrt_{d['fmt']}_*.raw"))
      path = alt[0] if alt else path
    if not path.exists():
      print(f"  missing {d['file']}")
      continue
    try:
      rgb = load_raw_rgb(path, d["fmt"], d["w"], d["h"])
    except Exception as e:
      print(f"  load fail {path.name}: {e}")
      continue
    sc = normal_score(rgb[::4, ::4])
    sc["file"] = path.name
    sc["fmt"] = d["fmt"]
    scores.append(sc)
    print(
        f"  dump {path.name} mean|n|={sc['mean_len']:.3f} "
        f"unit%={100*sc['frac_unit']:.1f} hemiZ%={100*sc['frac_hemi_z']:.1f}"
    )
    thumb = (np.clip(rgb[::3, ::3], 0, 1) * 255).astype(np.uint8)
    tiles.append((thumb, f"fmt{d['fmt']} |n|={sc['mean_len']:.2f}"))

  # also pick up any GP_mrt_*.raw not listed
  for path in sorted(indir.glob("GP_mrt_*.raw")):
    if any(path.name == d.get("file") for d in dumps):
      continue
    m = re.match(r"GP_mrt_(\d+)_(\d+)x(\d+)\.raw", path.name)
    if not m:
      continue
    fmt, w, h = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
      rgb = load_raw_rgb(path, fmt, w, h)
    except Exception as e:
      print(f"  load fail {path.name}: {e}")
      continue
    sc = normal_score(rgb[::4, ::4])
    sc["file"] = path.name
    sc["fmt"] = fmt
    scores.append(sc)
    print(
        f"  dump {path.name} mean|n|={sc['mean_len']:.3f} "
        f"unit%={100*sc['frac_unit']:.1f} hemiZ%={100*sc['frac_hemi_z']:.1f}"
    )
    thumb = (np.clip(rgb[::3, ::3], 0, 1) * 255).astype(np.uint8)
    tiles.append((thumb, f"fmt{fmt} |n|={sc['mean_len']:.2f}"))

  n1_go = False
  for sc in scores:
    if sc["fmt"] in NORMALISH and sc["frac_unit"] > 0.55 and 0.85 < sc["mean_len"] < 1.15:
      n1_go = True
      break

  print("=== N2 depth timeline ===")
  if not timeline:
    print("  (no GP_depth_timeline.txt)")
  best = None
  for row in timeline:
    print(
        f"  present={row['present']} fmt={row['fmt']} "
        f"sky={row['sky']:.1f}% cloud={row['cloud']:.1f}% st={row['stencil']:.1f}%"
    )
    if best is None or row["cloud"] < best["cloud"]:
      best = row

  n2_go = False
  if best is not None:
    # clean: low cloud band, still has sky marker
    n2_go = best["cloud"] < 5.0 and best["sky"] > 5.0
    print(
        f"  best cloud%={best['cloud']:.1f} sky%={best['sky']:.1f} "
        f"-> {'GO' if n2_go else 'NO-GO'}"
    )

  # depth-timeline chart
  try:
    font = ImageFont.truetype("msyh.ttc", 16)
  except OSError:
    font = ImageFont.load_default()

  if timeline:
    W, H = 900, 280
    chart = Image.new("RGB", (W, H), (22, 22, 24))
    dr = ImageDraw.Draw(chart)
    dr.text((12, 8), "Depth timeline: sky% (cyan) vs cloud-band% (orange)", fill=(230, 230, 235), font=font)
    xs = [r["present"] for r in timeline]
    if xs:
      xmin, xmax = min(xs), max(xs)
      span = max(1, xmax - xmin)

      def xmap(p: int) -> int:
        return 40 + int((p - xmin) / span * (W - 60))

      def ymap(v: float) -> int:
        return H - 30 - int(np.clip(v, 0, 100) / 100.0 * (H - 60))

      for i in range(len(timeline) - 1):
        a, b = timeline[i], timeline[i + 1]
        dr.line([(xmap(a["present"]), ymap(a["sky"])), (xmap(b["present"]), ymap(b["sky"]))], fill=(80, 200, 220), width=2)
        dr.line([(xmap(a["present"]), ymap(a["cloud"])), (xmap(b["present"]), ymap(b["cloud"]))], fill=(240, 140, 60), width=2)
    out_tl = demo / "depth-timeline.png"
    chart.save(out_tl)
    print("wrote", out_tl)

  if tiles:
    tw = min(480, tiles[0][0].shape[1])
    th = min(270, tiles[0][0].shape[0])
    cols = min(3, len(tiles))
    rows_n = (len(tiles) + cols - 1) // cols
    pad, bar = 8, 28
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows_n * (th + bar + pad) + pad + 36), (18, 18, 20))
    dr = ImageDraw.Draw(sheet)
    dr.text((pad, 8), "MRT candidates (N1) — look for unit-length normals", fill=(240, 240, 242), font=font)
    for i, (img, lab) in enumerate(tiles[:9]):
      r, c = divmod(i, cols)
      x = pad + c * (tw + pad)
      y = 36 + pad + r * (th + bar + pad)
      im = Image.fromarray(img).resize((tw, th), Image.LANCZOS)
      sheet.paste(im, (x, y))
      dr.text((x, y + th + 4), lab, fill=(200, 200, 210), font=font)
    out_m = demo / "mrt-candidates.png"
    sheet.save(out_m)
    print("wrote", out_m)

  print("=== VERDICT ===")
  print(f"N1 normals: {'GO' if n1_go else 'NO-GO'}")
  print(f"N2 clean depth: {'GO' if n2_go else 'NO-GO'}")
  if n2_go and not n1_go:
    print("SUGGEST: wire clean-depth to Present contact; keep AO off")
  elif n1_go and n2_go:
    print("SUGGEST: wire normals + clean depth; visualize before AO")
  elif n1_go:
    print("SUGGEST: wire normal SRV visualize; depth still dirty")
  else:
    print("SUGGEST: dual NO-GO — keep present mode 2; document RESULTS")


if __name__ == "__main__":
  main()
