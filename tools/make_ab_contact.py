#!/usr/bin/env python3
"""Build demo/ab-contact-*.png from the offline contact-shadow smoke scene.

Panels:
  ab-contact-off-vs-on.png  — colour | composite (strength 0.45, ship default)
  ab-contact-debug.png      — colour | red occlusion (mode-4 equivalent)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from contact_shadow_smoke import contact_shadow, make_scene

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


def panel_row(*imgs: np.ndarray, labels: list[str]) -> Image.Image:
    h, w, _ = imgs[0].shape
    row = Image.new("RGB", (w * len(imgs), h + 28), (18, 18, 18))
    draw = ImageDraw.Draw(row)
    for i, arr in enumerate(imgs):
        rgb = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
        row.paste(Image.fromarray(rgb, mode="RGB"), (i * w, 28))
        draw.text((i * w + 8, 8), labels[i], fill=(255, 255, 255))
    return row


def main() -> None:
    col, d, _ = make_scene()
    sh = contact_shadow(d, light_xy=(0.35, -0.75), radius_m=1.20, proj_k=600.0, steps=8)
    strength = 0.45
    comp = col * (1.0 - (1.0 - sh[..., None]) * strength)
    o = 1.0 - sh
    red = col * (1.0 - 0.85 * o[..., None]) + np.array([1.0, 0.15, 0.1]) * (0.85 * o[..., None])
    DEMO.mkdir(parents=True, exist_ok=True)
    off_on = panel_row(col, comp, labels=["CONTACT OFF (passthrough)", "CONTACT ON mode0 strength=0.45"])
    off_on.save(DEMO / "ab-contact-off-vs-on.png")
    dbg = panel_row(col, red, labels=["colour", "mode4 red occlusion debug"])
    dbg.save(DEMO / "ab-contact-debug.png")
    mean_occ = float((1.0 - sh)[d < 0.999].mean())
    print(f"wrote ab-contact-off-vs-on.png / ab-contact-debug.png mean_occ={mean_occ:.3f}")


if __name__ == "__main__":
    main()
