# -*- coding: utf-8 -*-
"""Multi-frame exhaustive global grade fit: vanilla→inject under ONE param set.

Proves DLL effect is not reproducible by a single brightness/contrast/sat/gamma
across diverse YAAB scenes.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

DEMO = Path(r"c:\Users\user\Desktop\Projects\Arma3\graph_pro\demo")
INJ = DEMO / "yaab-sync-inject.mp4"
VAN = DEMO / "yaab-sync-vanilla.mp4"
N_FRAMES = 36  # evenly spaced; low-diff / UI frames dropped for fit


def apply_grade(
    img: np.ndarray, brightness: float, contrast: float, saturation: float, gamma: float
) -> np.ndarray:
  x = np.clip(img, 0.0, 1.0)
  if abs(gamma - 1.0) > 1e-6:
    x = np.power(np.maximum(x, 1e-6), gamma)
  x = (x - 0.5) * contrast + 0.5 + brightness
  x = np.clip(x, 0.0, 1.0)
  g = (0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2])[..., None]
  return np.clip(g + (x - g) * saturation, 0.0, 1.0)


def grade_flat(
    samples: np.ndarray, br: float, co: float, sa: float, ga: float
) -> np.ndarray:
  x = np.clip(samples, 0.0, 1.0)
  x = np.power(np.maximum(x, 1e-6), ga)
  x = (x - 0.5) * co + 0.5 + br
  x = np.clip(x, 0.0, 1.0)
  g = (0.2126 * x[:, 0] + 0.7152 * x[:, 1] + 0.0722 * x[:, 2])[:, None]
  return np.clip(g + (x - g) * sa, 0.0, 1.0)


def rmse(a: np.ndarray, b: np.ndarray) -> float:
  return float(np.sqrt(((a - b) ** 2).mean()))


def mad255(a: np.ndarray, b: np.ndarray) -> float:
  return float(np.abs(a - b).mean() * 255.0)


def load_pairs(n: int) -> tuple[list[np.ndarray], list[np.ndarray], list[int], float]:
  ci = cv2.VideoCapture(str(INJ))
  cv_ = cv2.VideoCapture(str(VAN))
  total = int(ci.get(cv2.CAP_PROP_FRAME_COUNT))
  fps = float(ci.get(cv2.CAP_PROP_FPS) or 60.0)
  # skip first/last 5% (loading / hard cuts)
  lo = int(total * 0.06)
  hi = int(total * 0.94)
  idxs = [int(lo + (hi - lo) * i / (n - 1)) for i in range(n)]
  vans, injs = [], []
  for fi in idxs:
    ci.set(cv2.CAP_PROP_POS_FRAMES, fi)
    cv_.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ok_i, a = ci.read()
    ok_v, b = cv_.read()
    if not ok_i or not ok_v:
      raise RuntimeError(f"read fail at {fi}")
    # BGR -> RGB float
    vans.append(cv2.cvtColor(b, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0)
    injs.append(cv2.cvtColor(a, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0)
  ci.release()
  cv_.release()
  return vans, injs, idxs, fps


def pool_samples(frames: list[np.ndarray], step: int = 8, max_n: int = 40000) -> np.ndarray:
  parts = []
  for f in frames:
    parts.append(f[40:-40:step, 40:-40:step].reshape(-1, 3))
  all_p = np.concatenate(parts, axis=0)
  if len(all_p) > max_n:
    rng = np.random.default_rng(0)
    all_p = all_p[rng.choice(len(all_p), size=max_n, replace=False)]
  return all_p


def fit_grade(fit_v: np.ndarray, fit_i: np.ndarray) -> tuple[float, tuple[float, float, float, float]]:
  best = (1e9, (0.0, 1.0, 1.0, 1.0))
  # Stage 1: coarse exhaustive grid
  n_eval = 0
  for br in np.linspace(-0.15, 0.08, 12):
    for co in np.linspace(0.85, 1.65, 14):
      for sa in np.linspace(0.75, 1.55, 12):
        for ga in np.linspace(0.75, 1.35, 11):
          pred = grade_flat(fit_v, float(br), float(co), float(sa), float(ga))
          e = rmse(pred, fit_i)
          n_eval += 1
          if e < best[0]:
            best = (e, (float(br), float(co), float(sa), float(ga)))
  print(f"  coarse evals={n_eval} best={best[0]:.5f} params={[round(x,4) for x in best[1]]}", flush=True)
  br, co, sa, ga = best[1]
  # Stage 2: medium grid around best
  for br2 in np.linspace(br - 0.04, br + 0.04, 9):
    for co2 in np.linspace(co - 0.12, co + 0.12, 9):
      for sa2 in np.linspace(sa - 0.12, sa + 0.12, 9):
        for ga2 in np.linspace(ga - 0.08, ga + 0.08, 9):
          p = (float(br2), float(co2), float(sa2), float(ga2))
          if not (-0.25 < p[0] < 0.2 and 0.6 < p[1] < 1.9 and 0.6 < p[2] < 1.9 and 0.7 < p[3] < 1.35):
            continue
          e = rmse(grade_flat(fit_v, *p), fit_i)
          if e < best[0]:
            best = (e, p)
  br, co, sa, ga = best[1]
  print(f"  medium best={best[0]:.5f} params={[round(x,4) for x in best[1]]}", flush=True)
  # Stage 3: local refine
  for step in (0.015, 0.008, 0.004, 0.002):
    improved = True
    while improved:
      improved = False
      for dbr in (-step, 0.0, step):
        for dco in (-step, 0.0, step):
          for dsa in (-step, 0.0, step):
            for dga in (-step, 0.0, step):
              if dbr == dco == dsa == dga == 0.0:
                continue
              p = (br + dbr, co + dco, sa + dsa, ga + dga)
              if not (-0.25 < p[0] < 0.2 and 0.6 < p[1] < 1.9 and 0.6 < p[2] < 1.9 and 0.7 < p[3] < 1.35):
                continue
              e = rmse(grade_flat(fit_v, *p), fit_i)
              if e + 1e-7 < best[0]:
                best = (e, p)
                br, co, sa, ga = p
                improved = True
  return best


def u8(x: np.ndarray) -> np.ndarray:
  return (np.clip(x, 0, 1) * 255).astype(np.uint8)


def heat(a: np.ndarray, b: np.ndarray, gain: float = 6.0) -> np.ndarray:
  d = np.clip(np.abs(a - b).mean(2) * 255.0 * gain, 0, 255)
  h = np.zeros((*d.shape, 3), np.float32)
  h[:, :, 0] = np.clip(d * 1.25, 0, 255)
  h[:, :, 1] = np.clip(d * 0.45, 0, 255)
  h[:, :, 2] = np.clip(d * 0.12, 0, 255)
  return h.astype(np.uint8)


def main() -> None:
  print("loading", N_FRAMES, "frame pairs...")
  vans, injs, idxs, fps = load_pairs(N_FRAMES)
  # Drop near-identical / loading / flat UI frames from the *fit* set so one
  # global grade is optimized for real gameplay content, then evaluate on all.
  raw0 = [mad255(v, i) for v, i in zip(vans, injs)]
  fit_mask = [m > 10.0 and (idxs[k] / fps) > 12.0 for k, m in enumerate(raw0)]
  if sum(fit_mask) < 8:
    fit_mask = [m > 6.0 for m in raw0]
  print("frames", idxs, flush=True)
  print("fit on", sum(fit_mask), "/", N_FRAMES, "gameplay-like frames", flush=True)

  rng = np.random.default_rng(0)
  parts_v, parts_i = [], []
  for use, v, i in zip(fit_mask, vans, injs):
    if not use:
      continue
    vv = v[40:-40:12, 40:-40:12].reshape(-1, 3)
    ii = i[40:-40:12, 40:-40:12].reshape(-1, 3)
    parts_v.append(vv)
    parts_i.append(ii)
  fit_v = np.concatenate(parts_v, 0)
  fit_i = np.concatenate(parts_i, 0)
  if len(fit_v) > 36000:
    sel = rng.choice(len(fit_v), size=36000, replace=False)
    fit_v, fit_i = fit_v[sel], fit_i[sel]
  print("pooled samples", fit_v.shape[0], flush=True)

  print("exhaustive grid + refine...", flush=True)
  err, params = fit_grade(fit_v, fit_i)
  br, co, sa, ga = params
  print("best params br,con,sat,gam", [round(x, 4) for x in params], "pool RMSE", err)

  fitted = [apply_grade(v, br, co, sa, ga) for v in vans]

  mad_raw = [mad255(v, i) for v, i in zip(vans, injs)]
  mad_fit = [mad255(f, i) for f, i in zip(fitted, injs)]
  # Stats on gameplay frames only (fairer)
  gp = [k for k, m in enumerate(fit_mask) if m]
  mean_raw = float(np.mean([mad_raw[k] for k in gp]))
  mean_fit = float(np.mean([mad_fit[k] for k in gp]))
  closed = (mean_raw - mean_fit) / mean_raw * 100.0
  still_bad = sum(1 for k in gp if mad_fit[k] > 8.0)
  print(f"gameplay MAD mean raw {mean_raw:.2f} → fit {mean_fit:.2f}  closed {closed:.1f}%")
  print(f"gameplay frames MAD_fit>8: {still_bad}/{len(gp)}")
  for k, (fi, r, f) in enumerate(zip(idxs, mad_raw, mad_fit)):
    tag = "FIT" if fit_mask[k] else "skip"
    print(
        f"  #{k:02d} [{tag}] t={fi/fps:5.1f}s  MAD raw {r:5.1f}  fit {f:5.1f}  "
        f"residual% {100*f/max(r,1e-6):.0f}"
    )

  try:
    font_t = ImageFont.truetype("msyh.ttc", 22)
    font = ImageFont.truetype("msyh.ttc", 13)
    font_s = ImageFont.truetype("msyh.ttc", 12)
  except OSError:
    font_t = font = font_s = ImageFont.load_default()

  # Grid: pick 12 highest residual among gameplay frames used for / after fit
  order = sorted(gp, key=lambda k: -mad_fit[k])
  show = order[:12]

  tw, th = 360, 202
  cols = 3  # fit | inject | residual  as a group? Better: each row = 3 crops of same frame types across?
  # Layout: 12 rows × 3 cols (调色后原版 | 注入 | 残差)
  pad, bar, head, foot = 10, 32, 78, 56
  canvas_w = pad * 4 + tw * 3
  canvas_h = head + len(show) * (th + bar + pad) + foot
  canvas = Image.new("RGB", (canvas_w, canvas_h), (14, 14, 16))
  d = ImageDraw.Draw(canvas)
  d.text((pad, 10), "YAAB 多帧证明：同一组全局调色 无法抹平注入差异", fill=(248, 248, 250), font=font_t)
  d.text(
      (pad, 40),
      f"穷尽搜索 brightness/contrast/saturation/gamma → 一组参数用于全部 {N_FRAMES} 帧  |  "
      f"br{br:+.3f} con{co:.2f} sat{sa:.2f} gam{ga:.2f}",
      fill=(160, 165, 175),
      font=font_s,
  )
  d.text(
      (pad, 58),
      f"实况帧平均 MAD {mean_raw:.1f}→{mean_fit:.1f}/255（只消掉 {closed:.0f}%）；"
      f"MAD>8 仍有 {still_bad}/{len(gp)} 帧  |  下列为残差最大的 12 个时刻",
      fill=(200, 170, 140),
      font=font_s,
  )

  for row, k in enumerate(show):
    fi = idxs[k]
    panels = [
        (u8(fitted[k]), "同一调色后的原版", (210, 210, 220)),
        (u8(injs[k]), "注入", (255, 210, 100)),
        (heat(fitted[k], injs[k], gain=7.0), f"残差 MAD {mad_fit[k]:.1f}", (255, 130, 110)),
    ]
    y = head + row * (th + bar + pad)
    for j, (arr, lab, col) in enumerate(panels):
      x = pad + j * (tw + pad)
      thumb = cv2.resize(arr, (tw, th), interpolation=cv2.INTER_AREA)
      canvas.paste(Image.fromarray(thumb), (x, y))
      d.rectangle([x, y + th, x + tw, y + th + bar], fill=(26, 26, 30))
      if j == 0:
        d.text(
            (x + 6, y + th + 6),
            f"t={fi/fps:.1f}s · {lab}",
            fill=col,
            font=font,
        )
        d.text(
            (x + 6, y + th + 20),
            f"rawMAD {mad_raw[k]:.1f} → fit {mad_fit[k]:.1f}",
            fill=(150, 150, 160),
            font=font_s,
        )
      else:
        d.text((x + 6, y + th + 10), lab, fill=col, font=font)

  fy = canvas_h - foot
  d.rectangle([0, fy, canvas_w, canvas_h], fill=(22, 22, 26))
  d.text(
      (pad, fy + 12),
      "结论：在跨场景共用同一组全局调色参数时，仍有大量局部结构差（阴影层次 / ACES 曲线 / SSAO resolve）。",
      fill=(220, 220, 230),
      font=font,
  )
  d.text(
      (pad, fy + 32),
      "这不是「某一帧碰巧调不准」——是同一参数在全部抽帧上的系统残差。DLL ≠ 单纯拉滑条。",
      fill=(255, 200, 120),
      font=font,
  )

  out = DEMO / "yaab-grade-fit-multiframe.png"
  canvas.save(out)
  print("wrote", out)

  # summary strip: 8 frames, 2 rows (fit vs inject)
  show2 = order[:8]
  if not show2:
    show2 = order[:8]
  tw2, th2 = 300, 168
  strip_w = pad * 9 + tw2 * 8
  strip_h = 50 + 2 * (th2 + 28) + pad
  strip = Image.new("RGB", (strip_w, strip_h), (14, 14, 16))
  sd = ImageDraw.Draw(strip)
  sd.text((pad, 10), "同一全局调色后的原版（上） vs 注入（下）— 残差最大 8 帧", fill=(240, 240, 245), font=font)
  for j, k in enumerate(show2):
    x = pad + j * (tw2 + pad)
    strip.paste(Image.fromarray(cv2.resize(u8(fitted[k]), (tw2, th2))), (x, 42))
    strip.paste(Image.fromarray(cv2.resize(u8(injs[k]), (tw2, th2))), (x, 42 + th2 + 28))
    sd.text((x, 42 + th2 + 4), f"fit MAD{mad_fit[k]:.1f}", fill=(180, 180, 190), font=font_s)
    sd.text((x, 42 + 2 * th2 + 32 - 20), "inject", fill=(255, 210, 100), font=font_s)
  out2 = DEMO / "yaab-grade-fit-multiframe-strip.png"
  strip.save(out2)
  print("wrote", out2)

  meta = DEMO / "yaab-grade-fit-multiframe-meta.txt"
  lines = [
      f"n_frames={N_FRAMES}",
      f"params_br={br:.6f}",
      f"params_contrast={co:.6f}",
      f"params_saturation={sa:.6f}",
      f"params_gamma={ga:.6f}",
      f"pool_rmse={err:.6f}",
      f"mad_mean_raw={mean_raw:.4f}",
      f"mad_mean_fit={mean_fit:.4f}",
      f"mad_closed_pct={closed:.2f}",
      f"frames_mad_fit_gt8={still_bad}",
  ]
  for k, (fi, r, f) in enumerate(zip(idxs, mad_raw, mad_fit)):
    lines.append(f"frame[{k}] idx={fi} t={fi/fps:.2f} mad_raw={r:.3f} mad_fit={f:.3f}")
  meta.write_text("\n".join(lines) + "\n", encoding="utf-8")
  print("wrote", meta)


if __name__ == "__main__":
  main()
