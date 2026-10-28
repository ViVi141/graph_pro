# -*- coding: utf-8 -*-
"""Align YAAB inject vs vanilla using user time-anchor; export sheet + side-by-side."""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

INJECT = Path(r"<USERPROFILE>\Videos\2026-10-23 23-41-19.mp4")
VANILLA = Path(r"<USERPROFILE>\Videos\2026-10-23 23-45-17.mp4")
OUT_DIR = Path(r"c:\Users\user\Desktop\Projects\Arma3\graph_pro\demo")


def grab(cap: cv2.VideoCapture, fi: int) -> np.ndarray | None:
  cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(fi)))
  ok, fr = cap.read()
  return fr if ok else None


def sig(bgr: np.ndarray) -> np.ndarray:
  g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
  g = cv2.resize(g, (128, 72), interpolation=cv2.INTER_AREA).astype(np.float32)
  return g - g.mean()


def mad_pair(a: np.ndarray, b: np.ndarray) -> float:
  return float(np.mean(np.abs(sig(a) - sig(b))))


def refine_delta(
    path_i: Path,
    path_v: Path,
    i_anchor: int,
    delta0: int,
    coarse_radius: int = 60,
    coarse_step: int = 4,
    fine_radius: int = 6,
) -> tuple[int, float]:
  """Search delta around delta0 with coarse then fine; few probe frames only."""
  cap_i = cv2.VideoCapture(str(path_i))
  cap_v = cv2.VideoCapture(str(path_v))
  n_i = int(cap_i.get(cv2.CAP_PROP_FRAME_COUNT))
  n_v = int(cap_v.get(cv2.CAP_PROP_FRAME_COUNT))
  probes = [i_anchor + d for d in (-900, -300, 0, 300, 900, 1500)]
  probes = [p for p in probes if 0 <= p < n_i]

  def score(delta: int) -> float:
    errs = []
    for pi in probes:
      pv = pi + delta
      if pv < 0 or pv >= n_v:
        continue
      a = grab(cap_i, pi)
      b = grab(cap_v, pv)
      if a is None or b is None:
        continue
      errs.append(mad_pair(a, b))
    return float(np.mean(errs)) if errs else 1e9

  best_d, best_e = delta0, score(delta0)
  print(f"  seed delta={delta0} err={best_e:.5f}")
  for d in range(delta0 - coarse_radius, delta0 + coarse_radius + 1, coarse_step):
    e = score(d)
    if e < best_e:
      best_d, best_e = d, e
  print(f"  coarse best delta={best_d} err={best_e:.5f}")
  center = best_d
  for d in range(center - fine_radius, center + fine_radius + 1):
    e = score(d)
    if e < best_e:
      best_d, best_e = d, e
  print(f"  fine best delta={best_d} err={best_e:.5f}")
  cap_i.release()
  cap_v.release()
  return best_d, best_e


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("--inject", type=Path, default=INJECT)
  ap.add_argument("--vanilla", type=Path, default=VANILLA)
  ap.add_argument("--out", type=Path, default=OUT_DIR)
  ap.add_argument("--inj-s", type=float, default=31.0)
  ap.add_argument("--van-s", type=float, default=35.0)
  args = ap.parse_args()
  out = args.out
  out.mkdir(parents=True, exist_ok=True)

  ci = cv2.VideoCapture(str(args.inject))
  cv_ = cv2.VideoCapture(str(args.vanilla))
  fps_i = float(ci.get(cv2.CAP_PROP_FPS) or 60.0)
  fps_v = float(cv_.get(cv2.CAP_PROP_FPS) or 60.0)
  n_i = int(ci.get(cv2.CAP_PROP_FRAME_COUNT))
  n_v = int(cv_.get(cv2.CAP_PROP_FRAME_COUNT))
  ci.release()
  cv_.release()

  i_anchor = int(round(args.inj_s * fps_i))
  v_anchor = int(round(args.van_s * fps_v))
  delta0 = v_anchor - i_anchor
  print(f"user anchor: inject {args.inj_s}s(f{i_anchor}) ≈ vanilla {args.van_s}s(f{v_anchor})")
  print(f"delta0={delta0}f ({delta0 / fps_i:.3f}s)")

  delta, err = refine_delta(args.inject, args.vanilla, i_anchor, delta0)
  i0 = max(0, -delta)
  i1 = min(n_i, n_v - delta)
  overlap = i1 - i0
  print(f"final delta={delta}  overlap={overlap}f ({overlap / fps_i:.1f}s)")

  try:
    font_t = ImageFont.truetype("msyh.ttc", 22)
    font = ImageFont.truetype("msyh.ttc", 16)
  except OSError:
    font_t = font = ImageFont.load_default()

  cap_i = cv2.VideoCapture(str(args.inject))
  cap_v = cv2.VideoCapture(str(args.vanilla))
  tw, th = 640, 360
  picks = [i0 + int(overlap * p) for p in (0.05, 0.20, 0.35, 0.50, 0.65, 0.82)]
  pad, bar, head = 10, 34, 60
  canvas = Image.new("RGB", (pad * 3 + tw * 2, head + len(picks) * (th + bar + pad) + pad), (16, 16, 18))
  dr = ImageDraw.Draw(canvas)
  dr.text((pad, 8), "YAAB 对齐对比：注入 vs 原版", fill=(245, 245, 248), font=font_t)
  dr.text(
      (pad, 34),
      f"锚点 注入{args.inj_s:.0f}s≈原版{args.van_s:.0f}s → Δ={delta}f ({delta / fps_i:.3f}s)  重叠 {overlap / fps_i:.1f}s  align_err={err:.4f}",
      fill=(160, 165, 175),
      font=font,
  )

  mad_list = []
  for row, fi in enumerate(picks):
    fv = fi + delta
    a = grab(cap_i, fi)
    b = grab(cap_v, fv)
    if a is None or b is None:
      continue
    ar = cv2.cvtColor(a, cv2.COLOR_BGR2RGB)
    br = cv2.cvtColor(b, cv2.COLOR_BGR2RGB)
    mad = float(np.mean(np.abs(ar.astype(np.float32) - br.astype(np.float32))))
    mad_list.append(mad)
    y = head + row * (th + bar + pad)
    canvas.paste(Image.fromarray(cv2.resize(ar, (tw, th))), (pad, y))
    canvas.paste(Image.fromarray(cv2.resize(br, (tw, th))), (pad * 2 + tw, y))
    dr.rectangle([pad, y + th, pad + tw, y + th + bar], fill=(28, 28, 32))
    dr.rectangle([pad * 2 + tw, y + th, pad * 2 + tw * 2, y + th + bar], fill=(28, 28, 32))
    dr.text((pad + 8, y + th + 8), f"注入  t={fi / fps_i:.1f}s  f={fi}", fill=(255, 210, 110), font=font)
    dr.text(
        (pad * 2 + tw + 8, y + th + 8),
        f"原版  t={fv / fps_v:.1f}s  f={fv}  MAD={mad:.1f}",
        fill=(200, 200, 210),
        font=font,
    )

  sheet = out / "yaab-align-compare.png"
  canvas.save(sheet)
  print("wrote", sheet, "mean MAD", float(np.mean(mad_list)) if mad_list else None)

  # Sequential decode for video (fast): seek once each, then read forward
  out_vid = out / "yaab-align-sidebyside.mp4"
  out_w, out_h = tw * 2, th + 40
  writer = cv2.VideoWriter(str(out_vid), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (out_w, out_h))
  max_src = min(overlap, int(50 * fps_i))
  cap_i.set(cv2.CAP_PROP_POS_FRAMES, i0)
  cap_v.set(cv2.CAP_PROP_POS_FRAMES, i0 + delta)
  written = 0
  src_off = 0
  while src_off < max_src:
    ok_i, a = cap_i.read()
    ok_v, b = cap_v.read()
    if not ok_i or not ok_v:
      break
    if src_off % 2 == 0:
      a_s = cv2.resize(a, (tw, th), interpolation=cv2.INTER_AREA)
      b_s = cv2.resize(b, (tw, th), interpolation=cv2.INTER_AREA)
      panel = np.zeros((out_h, out_w, 3), np.uint8)
      panel[:th, :tw] = a_s
      panel[:th, tw:] = b_s
      cv2.rectangle(panel, (0, th), (out_w, out_h), (28, 28, 32), -1)
      cv2.putText(panel, "INJECT", (12, th + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 200, 255), 2, cv2.LINE_AA)
      cv2.putText(panel, "VANILLA", (tw + 12, th + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2, cv2.LINE_AA)
      cv2.putText(
          panel,
          f"t_inj={(i0 + src_off) / fps_i:.1f}s",
          (out_w // 2 - 70, th + 28),
          cv2.FONT_HERSHEY_SIMPLEX,
          0.55,
          (180, 180, 180),
          1,
          cv2.LINE_AA,
      )
      writer.write(panel)
      written += 1
      if written % 200 == 0:
        print(f"  video frames {written}")
    src_off += 1
  writer.release()
  cap_i.release()
  cap_v.release()
  print("wrote", out_vid, "frames", written)

  (out / "yaab-align-meta.txt").write_text(
      "\n".join(
          [
              f"inject={args.inject}",
              f"vanilla={args.vanilla}",
              f"user_anchor_inject_s={args.inj_s}",
              f"user_anchor_vanilla_s={args.van_s}",
              f"delta_frames={delta}",
              f"delta_s={delta / fps_i:.4f}",
              f"overlap_start_inject={i0}",
              f"overlap_frames={overlap}",
              f"overlap_s={overlap / fps_i:.3f}",
              f"align_err={err:.6f}",
              f"sheet_mean_mad={float(np.mean(mad_list)) if mad_list else -1:.3f}",
          ]
      ),
      encoding="utf-8",
  )
  print("wrote", out / "yaab-align-meta.txt")


if __name__ == "__main__":
  main()
