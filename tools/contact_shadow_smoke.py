#!/usr/bin/env python3
"""Offline Gate-4 contact-shadow smoke using a synthetic depth field.

Produces demo/contact-shadow-smoke.png (A/B: colour | occlusion | composite).
Does not require the game; validates the ray-march math before in-engine A/B.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    from PIL import Image
except ImportError:
    Image = None

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo" / "contact-shadow-smoke.png"
NEAR = 0.1


def z_of(d: np.ndarray) -> np.ndarray:
    return NEAR / np.maximum(1.0 - d, 1e-7)


def pack_depth(z: np.ndarray) -> np.ndarray:
    # Inverse of Zof for visualisation of Arma-like packing.
    return 1.0 - NEAR / np.maximum(z, NEAR + 1e-3)


def make_scene(h: int = 540, w: int = 960):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    uv = np.stack([xx / (w - 1), yy / (h - 1)], axis=-1)
    # Ground plane sloping away + a box occluder casting contact shadow.
    z = 8.0 + uv[..., 1] * 40.0
    box = (uv[..., 0] > 0.42) & (uv[..., 0] < 0.58) & (uv[..., 1] > 0.35) & (uv[..., 1] < 0.72)
    z = np.where(box, 6.5, z)
    # Sky strip
    sky = uv[..., 1] < 0.18
    d = pack_depth(z)
    d = np.where(sky, 1.0, d)
    # Fake albedo
    col = np.zeros((h, w, 3), dtype=np.float32)
    col[..., 0] = 0.45 + 0.15 * uv[..., 0]
    col[..., 1] = 0.50 + 0.10 * uv[..., 1]
    col[..., 2] = 0.40
    col = np.where(box[..., None], np.array([0.75, 0.55, 0.35], dtype=np.float32), col)
    col = np.where(sky[..., None], np.array([0.55, 0.65, 0.85], dtype=np.float32), col)
    return col, d, uv


def contact_shadow(d: np.ndarray, light_xy=(0.35, -0.75), radius_m=1.2, proj_k=600.0, steps=8):
    h, w = d.shape
    ts = np.array([1.0 / w, 1.0 / h], dtype=np.float32)
    L = np.array(light_xy, dtype=np.float32)
    L = L / max(float(np.linalg.norm(L)), 1e-6)
    z0 = z_of(d)
    occ = np.zeros_like(d)
    yy, xx = np.mgrid[0:h, 0:w]
    for s in range(1, steps + 1):
        t = s / float(steps)
        pix_r = np.clip(radius_m * proj_k / np.maximum(z0, 1.0), 2.0, 64.0)
        ouv_x = xx + L[0] * pix_r * t
        ouv_y = yy + L[1] * pix_r * t
        # bilinear sample of depth at ouv
        x0 = np.clip(ouv_x, 0, w - 1.001)
        y0 = np.clip(ouv_y, 0, h - 1.001)
        xi = np.floor(x0).astype(np.int32)
        yi = np.floor(y0).astype(np.int32)
        d1 = d[yi, xi]
        z1 = z_of(d1)
        dz = z0 - z1
        max_dz = radius_m * (0.35 + 0.65 * t)
        valid = (dz > 0.02) & (dz <= max_dz) & (d < 0.999999) & (z0 < 200.0)
        cand = (1.0 - t) * np.clip(dz / np.maximum(max_dz, 1e-3), 0, 1)
        occ = np.where(valid, np.maximum(occ, cand), occ)
    sh = np.clip(1.0 - occ, 0, 1)
    sh = np.where(d >= 0.999999, 1.0, sh)
    return sh


def main() -> None:
    col, d, _ = make_scene()
    sh = contact_shadow(d)
    strength = 0.70
    comp = col * (1.0 - (1.0 - sh[..., None]) * strength)
    dbg = np.stack([sh, sh, sh], axis=-1)
    # red occlusion overlay panel
    red = col.copy()
    o = 1.0 - sh
    red = red * (1.0 - 0.85 * o[..., None]) + np.array([1.0, 0.15, 0.1]) * (0.85 * o[..., None])
    panel = np.concatenate([col, dbg, red, comp], axis=1)
    panel = np.clip(panel * 255.0, 0, 255).astype(np.uint8)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if Image is not None:
        Image.fromarray(panel, mode="RGB").save(OUT)
    else:
        # PPM fallback
        ppm = OUT.with_suffix(".ppm")
        h, w, _ = panel.shape
        with open(ppm, "wb") as f:
            f.write(f"P6\n{w} {h}\n255\n".encode("ascii"))
            f.write(panel.tobytes())
        OUT.write_bytes(ppm.read_bytes())  # keep path stable if PIL missing
    mean_occ = float(1.0 - sh[d < 0.999].mean()) if np.any(d < 0.999) else 0.0
    print(f"wrote {OUT} mean_occlusion_ground={mean_occ:.3f}")


if __name__ == "__main__":
    main()
