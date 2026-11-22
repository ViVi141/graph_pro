"""Quantitative + visual 3-way comparison: Vanilla vs Legacy ACES v5 vs New AgX."""
from __future__ import annotations

import os
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_DIR = os.path.join(ROOT, "extract", "ab_graphics")
OUT_PNG = os.path.join(ROOT, "demo", "ab_vanilla_vs_aces_vs_agx.png")


def metrics(arr: np.ndarray) -> dict:
    # arr: float32 [H,W,3] in [0,1]
    luma = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    mx = arr.max(axis=-1)
    mn = arr.min(axis=-1)
    sat = np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0.0)
    # Sky region (top 30%)
    sky = luma[: int(luma.shape[0] * 0.30), :]
    # Ground/town region (bottom 65%)
    gnd = luma[int(luma.shape[0] * 0.35) :, :]
    return {
        "mean_luma": float(luma.mean()),
        "contrast_std": float(luma.std()),
        "overexp_98_pct": float((mx >= 0.98).mean() * 100.0),
        "overexp_99_pct": float((mx >= 0.995).mean() * 100.0),
        "crush_02_pct": float((luma <= 0.02).mean() * 100.0),
        "p05_luma": float(np.percentile(luma, 5)),
        "p95_luma": float(np.percentile(luma, 95)),
        "mean_sat": float(sat.mean()),
        "sky_std": float(sky.std()),
        "gnd_std": float(gnd.std()),
    }


def main() -> int:
    names = [("vanilla", "1. Vanilla (Stock DXVK)"),
             ("legacy_aces", "2. Legacy ACES v5 (Old Repo)"),
             ("new_agx", "3. New AgX Filmic (Zero-Clip)")]
    imgs = []
    print(f"{'Mode':<14} {'Luma':>6} {'Std':>6} {'Over98%':>8} {'Over99%':>8} {'Crush%':>7} {'P05':>5} {'P95':>5} {'Sat':>6} {'SkyStd':>7} {'GndStd':>7}")
    print("-" * 96)
    for key, label in names:
        p = os.path.join(IN_DIR, f"{key}.png")
        im = Image.open(p).convert("RGB")
        arr = np.asarray(im, dtype=np.float32) / 255.0
        m = metrics(arr)
        print(
            f"{key:<14} {m['mean_luma']:6.3f} {m['contrast_std']:6.3f} "
            f"{m['overexp_98_pct']:7.2f}% {m['overexp_99_pct']:7.2f}% "
            f"{m['crush_02_pct']:6.2f}% {m['p05_luma']:5.3f} {m['p95_luma']:5.3f} "
            f"{m['mean_sat']:6.3f} {m['sky_std']:7.4f} {m['gnd_std']:7.4f}"
        )
        imgs.append((label, im, m))

    # Build 3-column side-by-side (resized to 854x480 each) + bottom row center 1:1 crop (854x480)
    pw, ph = 854, 480
    hdr = 36
    canvas = Image.new("RGB", (pw * 3, (ph + hdr) * 2), (18, 18, 22))
    draw = ImageDraw.Draw(canvas)

    for idx, (label, im, m) in enumerate(imgs):
        w, h = im.size
        # Top row: full frame scaled
        full = im.resize((pw, ph), Image.Resampling.LANCZOS)
        canvas.paste(full, (idx * pw, hdr))
        txt = f"{label} | Over98={m['overexp_98_pct']:.1f}% Crush={m['crush_02_pct']:.1f}% Std={m['contrast_std']:.3f}"
        draw.text((idx * pw + 10, 10), txt, fill=(240, 240, 240))

        # Bottom row: 1:1 crop centered on horizon/town/sky boundary
        cx0 = max(0, (w - pw) // 2)
        cy0 = max(0, int(h * 0.22))
        crop = im.crop((cx0, cy0, cx0 + pw, cy0 + ph))
        canvas.paste(crop, (idx * pw, ph + hdr * 2))
        draw.text((idx * pw + 10, ph + hdr + 10), f"1:1 Crop (Sky + Town) - {label}", fill=(200, 220, 255))

    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    canvas.save(OUT_PNG)
    print(f"\nSaved visual comparison -> {OUT_PNG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
