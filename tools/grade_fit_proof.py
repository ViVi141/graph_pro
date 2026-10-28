# -*- coding: utf-8 -*-
"""Fit global brightness/contrast/saturation/gamma on vanilla-max to match inject-max.

Proves injection is not reproducible by global grade alone.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

DEMO = Path(r"c:\Users\user\Desktop\Projects\Arma3\graph_pro\demo")
VANILLA = DEMO / "_live" / "vanilla-maxcfg-latest" / "gp_r_baseline.png"
INJECT = DEMO / "_live" / "with-dll-maxcfg-20261023-223515" / "gp_r_baseline.png"


def best_shift(ref: np.ndarray, mov: np.ndarray, rng: int = 6) -> tuple[int, int]:
  h, w, _ = ref.shape
  best = (1e18, 0, 0)
  y0, y1, x0, x1 = 200, h - 200, 300, w - 300
  r = ref[y0:y1, x0:x1]
  for dy in range(-rng, rng + 1):
    for dx in range(-rng, rng + 1):
      m = mov[y0 + dy : y1 + dy, x0 + dx : x1 + dx]
      if m.shape != r.shape:
        continue
      d = np.abs(r - m).mean()
      if d < best[0]:
        best = (d, dx, dy)
  return best[1], best[2]


def crop_align(a: np.ndarray, b: np.ndarray, dx: int, dy: int) -> tuple[np.ndarray, np.ndarray]:
  h, w, _ = a.shape
  y0a, y1a = max(0, -dy), min(h, h - dy)
  x0a, x1a = max(0, -dx), min(w, w - dx)
  return a[y0a:y1a, x0a:x1a], b[y0a + dy : y1a + dy, x0a + dx : x1a + dx]


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


def rmse_flat(samples_a: np.ndarray, samples_b: np.ndarray, params: tuple[float, ...]) -> float:
  br, co, sa, ga = params
  x = np.clip(samples_a, 0.0, 1.0)
  x = np.power(np.maximum(x, 1e-6), ga)
  x = (x - 0.5) * co + 0.5 + br
  x = np.clip(x, 0.0, 1.0)
  g = (0.2126 * x[:, 0] + 0.7152 * x[:, 1] + 0.0722 * x[:, 2])[:, None]
  x = np.clip(g + (x - g) * sa, 0.0, 1.0)
  return float(np.sqrt(((x - samples_b) ** 2).mean()))


def heat(a: np.ndarray, b: np.ndarray, gain: float = 5.0) -> np.ndarray:
  d = np.clip(np.abs(a - b).mean(2) * 255.0 * gain, 0, 255)
  h = np.zeros((*d.shape, 3), np.float32)
  h[:, :, 0] = np.clip(d * 1.2, 0, 255)
  h[:, :, 1] = np.clip(d * 0.5, 0, 255)
  h[:, :, 2] = np.clip(d * 0.1, 0, 255)
  return h.astype(np.uint8)


def u8(x: np.ndarray) -> np.ndarray:
  return (np.clip(x, 0.0, 1.0) * 255.0).astype(np.uint8)


def main() -> None:
  a = np.asarray(Image.open(VANILLA).convert("RGB"), dtype=np.float64) / 255.0
  b = np.asarray(Image.open(INJECT).convert("RGB"), dtype=np.float64) / 255.0
  print("loaded", a.shape, b.shape)

  dx, dy = best_shift(a, b)
  print("align", dx, dy)
  if dx or dy:
    a, b = crop_align(a, b, dx, dy)
    print("cropped", a.shape)

  # Fit on heavily downsampled pixels (fast, stable for global grade).
  fit_a = a[40:-40:8, 40:-40:8].reshape(-1, 3)
  fit_b = b[40:-40:8, 40:-40:8].reshape(-1, 3)
  print("fit samples", fit_a.shape[0])

  best: tuple[float, tuple[float, float, float, float] | None] = (1e9, None)
  for br in np.linspace(-0.12, 0.05, 9):
    for co in np.linspace(0.9, 1.55, 10):
      for sa in np.linspace(0.9, 1.45, 9):
        for ga in np.linspace(0.85, 1.25, 7):
          e = rmse_flat(fit_a, fit_b, (br, co, sa, ga))
          if e < best[0]:
            best = (e, (float(br), float(co), float(sa), float(ga)))
  assert best[1] is not None
  print("coarse best rmse", best[0], "params", best[1])

  br, co, sa, ga = best[1]
  for step in (0.02, 0.01, 0.005):
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
              if not (-0.2 < p[0] < 0.15 and 0.7 < p[1] < 1.8 and 0.7 < p[2] < 1.8 and 0.7 < p[3] < 1.4):
                continue
              e = rmse_flat(fit_a, fit_b, p)
              if e + 1e-6 < best[0]:
                best = (e, p)
                br, co, sa, ga = p
                improved = True
  print("refined rmse", best[0], "params", [round(x, 4) for x in best[1]])

  br, co, sa, ga = best[1]
  fitted = apply_grade(a, br, co, sa, ga)

  rmse_raw = float(np.sqrt(((a - b) ** 2).mean()))
  rmse_fit = float(np.sqrt(((fitted - b) ** 2).mean()))
  mad_raw = float(np.abs(a - b).mean() * 255.0)
  mad_fit = float(np.abs(fitted - b).mean() * 255.0)
  frac_raw = float((np.abs(a - b).mean(2) * 255.0 > 8).mean())
  frac_fit = float((np.abs(fitted - b).mean(2) * 255.0 > 8).mean())
  closed = (mad_raw - mad_fit) / mad_raw * 100.0
  print("RMSE raw %.5f  fit %.5f" % (rmse_raw, rmse_fit))
  print("MAD  raw %.2f   fit %.2f  /255" % (mad_raw, mad_fit))
  print("frac>8 raw %.1f%% fit %.1f%%" % (100 * frac_raw, 100 * frac_fit))
  print("MAD closed by grade fit: %.1f%%" % closed)

  lb = 0.2126 * b[:, :, 0] + 0.7152 * b[:, :, 1] + 0.0722 * b[:, :, 2]
  for name, lo, hi in (("shadows", 0.0, 0.35), ("mids", 0.35, 0.7), ("highs", 0.7, 1.01)):
    m = (lb >= lo) & (lb < hi)
    if m.sum() < 500:
      continue
    r = float(np.abs(a[m] - b[m]).mean() * 255.0)
    f = float(np.abs(fitted[m] - b[m]).mean() * 255.0)
    print("region %-8s MAD raw %.2f fit %.2f residual%% %.0f" % (name, r, f, 100 * f / max(r, 1e-6)))

  h, w, _ = a.shape
  cw, ch = 640, 400
  cx, cy = w // 2, h // 2 + 40
  x0, y0 = cx - cw // 2, cy - ch // 2

  def crop(im: np.ndarray) -> np.ndarray:
    return im[y0 : y0 + ch, x0 : x0 + cw]

  try:
    font_t = ImageFont.truetype("msyh.ttc", 24)
    font = ImageFont.truetype("msyh.ttc", 16)
    font_s = ImageFont.truetype("msyh.ttc", 14)
  except OSError:
    font_t = font = font_s = ImageFont.load_default()

  panels = [
      (crop(u8(a)), "原版拉满"),
      (crop(u8(fitted)), "原版拉满 + 最佳亮度/对比/饱和/gamma"),
      (crop(u8(b)), "注入拉满（目标）"),
      (crop(heat(fitted, b, gain=5)), "拟合后残差（越亮=仍不像）"),
  ]

  pad, bar = 12, 48
  canvas_w = cw * 2 + pad * 3
  canvas_h = bar + (ch + bar) * 2 + pad * 3 + 70
  canvas = Image.new("RGB", (canvas_w, canvas_h), (20, 20, 22))
  d = ImageDraw.Draw(canvas)
  d.text((pad, 10), "证明：只调亮度/对比/饱和/gamma 无法复现注入", fill=(245, 245, 245), font=font_t)
  for i, (arr, lab) in enumerate(panels):
    r, c = divmod(i, 2)
    x = pad + c * (cw + pad)
    y = bar + pad + r * (ch + bar + pad)
    canvas.paste(Image.fromarray(arr), (x, y))
    d.rectangle([x, y + ch, x + cw, y + ch + bar], fill=(32, 32, 36))
    d.text((x + 8, y + ch + 8), lab, fill=(255, 220, 120) if i == 2 else (230, 230, 235), font=font)
    if i == 1:
      d.text(
          (x + 8, y + ch + 28),
          "br%+.3f con%.2f sat%.2f gam%.2f" % (br, co, sa, ga),
          fill=(160, 160, 170),
          font=font_s,
      )
    if i == 3:
      d.text(
          (x + 8, y + ch + 28),
          "残差 MAD %.1f/255（仍剩 %.0f%%）" % (mad_fit, 100 * mad_fit / mad_raw),
          fill=(255, 160, 140),
          font=font_s,
      )

  fy = canvas_h - 60
  d.rectangle([0, fy, canvas_w, canvas_h], fill=(28, 28, 32))
  verdict = (
      "拟合后 MAD %.1f→%.1f/255，只消除约 %.0f%% 差异；剩余 %.0f%% 无法用全局对比/饱和解释（阴影结构/色调分离/ACES）。"
      % (mad_raw, mad_fit, closed, 100 - closed)
  )
  d.text((pad, fy + 12), verdict, fill=(220, 220, 230), font=font_s)
  d.text(
      (pad, fy + 34),
      "参数搜索：brightness / contrast / saturation / gamma → 对齐注入拉满",
      fill=(150, 150, 160),
      font=font_s,
  )
  out = DEMO / "ab-grade-fit-proof.png"
  canvas.save(out)
  print("wrote", out)

  strip_h, strip_w = h // 3, w // 3
  strip = Image.new("RGB", (strip_w * 3 + pad * 4, strip_h + bar + pad * 2), (20, 20, 22))
  sd = ImageDraw.Draw(strip)
  for i, (im, lab) in enumerate(
      ((u8(a), "原版拉满"), (u8(fitted), "全局调色最佳拟合"), (u8(b), "注入拉满"))
  ):
    x = pad + i * (strip_w + pad)
    strip.paste(Image.fromarray(im).resize((strip_w, strip_h), Image.LANCZOS), (x, pad + bar))
    sd.text((x, pad + 8), lab, fill=(240, 240, 240), font=font)
  strip_path = DEMO / "ab-grade-fit-strip.png"
  strip.save(strip_path)
  print("wrote", strip_path)


if __name__ == "__main__":
  main()
