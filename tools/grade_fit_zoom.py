# -*- coding: utf-8 -*-
"""Multi-focus A/B: global grade best-fit vs inject-max (structural residual)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

DEMO = Path(r"c:\Users\user\Desktop\Projects\Arma3\graph_pro\demo")
VANILLA = DEMO / "_live" / "vanilla-maxcfg-latest" / "gp_r_baseline.png"
INJECT = DEMO / "_live" / "with-dll-maxcfg-20261023-223515" / "gp_r_baseline.png"

BR, CO, SA, GA = -0.0775, 1.2461, 0.865, 1.1117

# Seed list: (cx, cy, label). Each seed snaps to the strongest residual nearby.
SEEDS = [
    (980, 700, "人物轮廓与脚下阴影"),
    (480, 320, "石墙缝隙 / 接触暗部"),
    (1550, 260, "屋顶瓦片高光压暗"),
    (280, 560, "远树体积与层次"),
    (1250, 520, "绿篱 / 阴面局部对比"),
    (720, 860, "沥青颗粒与车辙"),
    (1600, 700, "右侧建筑墙面"),
    (900, 400, "中景石墙顶边"),
]


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


def u8(x: np.ndarray) -> np.ndarray:
  return (np.clip(x, 0.0, 1.0) * 255.0).astype(np.uint8)


def residual_map(a: np.ndarray, b: np.ndarray) -> np.ndarray:
  return np.abs(a - b).mean(axis=2)


def box_mean(m: np.ndarray, k: int = 24) -> np.ndarray:
  """Integral-image box filter (odd-ish via cumsum)."""
  pad = k // 2
  p = np.pad(m, pad, mode="edge")
  c = np.cumsum(np.cumsum(p, 0), 1)
  # sum of window ending at (i+k, j+k)
  h, w = m.shape
  out = np.empty_like(m)
  for y in range(h):
    y1 = y + k
    y0 = y
    for x in range(w):
      x1 = x + k
      x0 = x
      s = c[y1, x1] - c[y0, x1] - c[y1, x0] + c[y0, x0]
      out[y, x] = s / (k * k)
  return out


def box_mean_fast(m: np.ndarray, k: int = 32) -> np.ndarray:
  from numpy.lib.stride_tricks import sliding_window_view

  pad = k // 2
  p = np.pad(m, pad, mode="edge")
  win = sliding_window_view(p, (k, k))
  return win.mean(axis=(-1, -2))


def refine_near(
    smooth: np.ndarray, cx: int, cy: int, half: int, search: int = 140
) -> tuple[int, int, float]:
  h, w = smooth.shape
  y0 = max(half, cy - search)
  y1 = min(h - half, cy + search + 1)
  x0 = max(half, cx - search)
  x1 = min(w - half, cx + search + 1)
  patch = smooth[y0:y1, x0:x1]
  if patch.size == 0:
    return cx, cy, float(smooth[cy, cx])
  iy, ix = np.unravel_index(int(np.argmax(patch)), patch.shape)
  nx, ny = x0 + ix, y0 + iy
  return nx, ny, float(smooth[ny, nx])


def nms_pick(
    candidates: list[tuple[int, int, float, str]], min_dist: int, n: int
) -> list[tuple[int, int, float, str]]:
  picked: list[tuple[int, int, float, str]] = []
  for cx, cy, score, lab in sorted(candidates, key=lambda t: -t[2]):
    if any((cx - px) ** 2 + (cy - py) ** 2 < min_dist**2 for px, py, _, _ in picked):
      continue
    picked.append((cx, cy, score, lab))
    if len(picked) >= n:
      break
  return picked


def crop(im: np.ndarray, cx: int, cy: int, cw: int, ch: int) -> np.ndarray:
  h, w = im.shape[:2]
  x0 = int(np.clip(cx - cw // 2, 0, w - cw))
  y0 = int(np.clip(cy - ch // 2, 0, h - ch))
  return im[y0 : y0 + ch, x0 : x0 + cw]


def amplify_diff(fit: np.ndarray, inj: np.ndarray, amount: float = 1.55) -> np.ndarray:
  """Push fitted toward residual so side-by-side reads clearer (display only)."""
  # Keep fitted as-is; build a "difference enhanced" view of inject-fit gap on fit
  # Better: return fit unchanged — visual clarity comes from picking hard regions.
  return fit


def heat_on_fit(fit_u8: np.ndarray, res: np.ndarray, gain: float = 10.0) -> np.ndarray:
  d = np.clip(res * 255.0 * gain, 0, 255)
  out = fit_u8.astype(np.float32)
  out[:, :, 0] = np.clip(out[:, :, 0] * 0.40 + d * 1.15, 0, 255)
  out[:, :, 1] = np.clip(out[:, :, 1] * 0.40 + d * 0.30, 0, 255)
  out[:, :, 2] = np.clip(out[:, :, 2] * 0.40, 0, 255)
  return out.astype(np.uint8)


def main() -> None:
  a = np.asarray(Image.open(VANILLA).convert("RGB"), dtype=np.float64) / 255.0
  b = np.asarray(Image.open(INJECT).convert("RGB"), dtype=np.float64) / 255.0
  fitted = apply_grade(a, BR, CO, SA, GA)
  res = residual_map(fitted, b)
  mad = float(res.mean() * 255.0)
  print("MAD fitted vs inject %.2f/255" % mad)

  cw, ch = 560, 320
  half = min(cw, ch) // 2
  smooth = box_mean_fast(res, k=28)
  # mask edges
  smooth[:half, :] = 0
  smooth[-half:, :] = 0
  smooth[:, :half] = 0
  smooth[:, -half:] = 0

  def label_at(cx: int, cy: int) -> str:
    # nearest seed label within 220px, else quadrant heuristic
    best = None
    for sx, sy, lab in SEEDS:
      dist2 = (cx - sx) ** 2 + (cy - sy) ** 2
      if best is None or dist2 < best[0]:
        best = (dist2, lab)
    if best and best[0] < 220**2:
      return best[1]
    h, w = smooth.shape
    if cy < h * 0.35 and cx > w * 0.55:
      return "亮部屋顶 / 高光层次"
    if cy < h * 0.45 and cx < w * 0.45:
      return "远景树丛体积"
    if cy > h * 0.65:
      return "地面阴影与微对比"
    if cx > w * 0.55:
      return "建筑墙面局部结构"
    return "中景阴影结构"

  # Global residual peaks (strongest first) — this drives “尽量明显”
  cands = []
  flat = smooth.copy()
  for _ in range(24):
    iy, ix = np.unravel_index(int(np.argmax(flat)), flat.shape)
    sc = float(flat[iy, ix])
    if sc < 0.02:
      break
    cands.append((int(ix), int(iy), sc, label_at(int(ix), int(iy))))
    y0, y1 = max(0, iy - 100), min(flat.shape[0], iy + 100)
    x0, x1 = max(0, ix - 100), min(flat.shape[1], ix + 100)
    flat[y0:y1, x0:x1] = 0

  foci = nms_pick(cands, min_dist=240, n=6)
  print("picked foci:")
  for cx, cy, sc, lab in foci:
    print(
        "  %-18s (%d,%d) smooth=%.4f localMAD=%.1f"
        % (lab, cx, cy, sc, float(crop(res, cx, cy, cw, ch).mean() * 255))
    )

  try:
    font_t = ImageFont.truetype("msyh.ttc", 26)
    font = ImageFont.truetype("msyh.ttc", 17)
    font_s = ImageFont.truetype("msyh.ttc", 14)
  except OSError:
    font_t = font = font_s = ImageFont.load_default()

  pad, gap, bar, head = 14, 10, 40, 78
  row_w = cw * 3 + gap * 2
  canvas_w = pad * 2 + row_w
  canvas_h = head + len(foci) * (ch + bar + gap) + pad + 44
  canvas = Image.new("RGB", (canvas_w, canvas_h), (14, 14, 16))
  d = ImageDraw.Draw(canvas)
  d.text(
      (pad, 10),
      "多聚焦对比：全局调色最佳拟合  vs  注入拉满",
      fill=(250, 250, 252),
      font=font_t,
  )
  d.text(
      (pad, 42),
      "左=已用亮度/对比/饱和/gamma 尽力贴右 | 中=注入 | 右=残差热力（越红越抹不平）  MAD %.1f/255  br%+.3f con%.2f sat%.2f gam%.2f"
      % (mad, BR, CO, SA, GA),
      fill=(150, 155, 165),
      font=font_s,
  )

  fit_u8 = u8(fitted)
  inj_u8 = u8(b)
  heat_full = heat_on_fit(fit_u8, res, gain=11.0)

  for i, (cx, cy, sc, lab) in enumerate(foci):
    local = float(crop(res, cx, cy, cw, ch).mean() * 255.0)
    # mild local contrast stretch on both for readability (same LUT) — keep fair
    f_crop = crop(fit_u8, cx, cy, cw, ch).astype(np.float32)
    i_crop = crop(inj_u8, cx, cy, cw, ch).astype(np.float32)
    # per-row shared stretch based on combined percentiles
    stack = np.concatenate([f_crop.reshape(-1, 3), i_crop.reshape(-1, 3)], 0)
    lo = np.percentile(stack, 2, axis=0)
    hi = np.percentile(stack, 98, axis=0)
    span = np.maximum(hi - lo, 8.0)

    def stretch(x: np.ndarray) -> np.ndarray:
      y = (x - lo) / span * 255.0
      return np.clip(y, 0, 255).astype(np.uint8)

    panels = [
        (stretch(f_crop), "调色最佳拟合", (210, 210, 220)),
        (stretch(i_crop), "注入拉满", (255, 215, 100)),
        (crop(heat_full, cx, cy, cw, ch), "残差（红=仍差）", (255, 130, 110)),
    ]
    y = head + i * (ch + bar + gap)
    for j, (arr, title, col) in enumerate(panels):
      x = pad + j * (cw + gap)
      canvas.paste(Image.fromarray(arr), (x, y))
      d.rectangle([x, y + ch, x + cw, y + ch + bar], fill=(26, 26, 30))
      if j == 0:
        d.text((x + 8, y + ch + 6), "%d. %s" % (i + 1, lab), fill=(240, 240, 245), font=font)
        d.text((x + 8, y + ch + 24), title, fill=col, font=font_s)
      elif j == 1:
        d.text((x + 8, y + ch + 10), title, fill=col, font=font)
      else:
        d.text((x + 8, y + ch + 6), title, fill=col, font=font)
        d.text((x + 8, y + ch + 24), "本区 MAD %.1f/255" % local, fill=(200, 140, 130), font=font_s)

  fy = canvas_h - 36
  d.rectangle([0, fy, canvas_w, canvas_h], fill=(22, 22, 26))
  d.text(
      (pad, fy + 10),
      "说明：左右列用同一拉伸便于看结构差；全局调色已尽力对齐整体明度/饱和，红区仍在 = 局部阴影与色调分离，不是滑条问题。",
      fill=(185, 185, 195),
      font=font_s,
  )

  out = DEMO / "ab-grade-fit-zoom.png"
  canvas.save(out)
  print("wrote", out)


if __name__ == "__main__":
  main()
