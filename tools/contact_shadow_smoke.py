#!/usr/bin/env python3
"""Offline contact-shadow smoke: soft dual-radius + luma protect.

Produces demo/contact-shadow-smoke.png
  panels: colour | occ gray | red debug | composite(protect) | composite(no protect)
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
GROUND_D_MAX = 0.88


def z_of(d: np.ndarray) -> np.ndarray:
    return NEAR / np.maximum(1.0 - d, 1e-7)


def pack_depth(z: np.ndarray) -> np.ndarray:
    return 1.0 - NEAR / np.maximum(z, NEAR + 1e-3)


def make_scene(h: int = 540, w: int = 960):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    uv = np.stack([xx / (w - 1), yy / (h - 1)], axis=-1)
    # Keep packed d under GROUND_D_MAX (0.88 → z ≲ 0.83 m with NEAR=0.1)
    # so the offline scene exercises the same reject path as the HLSL.
    z = 0.35 + uv[..., 1] * 0.40
    box = (uv[..., 0] > 0.42) & (uv[..., 0] < 0.58) & (uv[..., 1] > 0.35) & (uv[..., 1] < 0.72)
    z = np.where(box, 0.28, z)
    sky = uv[..., 1] < 0.18
    d = pack_depth(z)
    d = np.where(sky, 1.0, d)
    col = np.zeros((h, w, 3), dtype=np.float32)
    col[..., 0] = 0.45 + 0.15 * uv[..., 0]
    col[..., 1] = 0.50 + 0.10 * uv[..., 1]
    col[..., 2] = 0.40
    col = np.where(box[..., None], np.array([0.75, 0.55, 0.35], dtype=np.float32), col)
    col = np.where(sky[..., None], np.array([0.55, 0.65, 0.85], dtype=np.float32), col)
    # Dark vegetation strip to exercise luma protect.
    veg = (uv[..., 1] > 0.75) & (uv[..., 0] < 0.35) & (~sky)
    col = np.where(veg[..., None], np.array([0.08, 0.12, 0.06], dtype=np.float32), col)
    return col, d, uv


def contact_occ_radius(d, light_xy, radius_m, proj_k, steps, rad_scale):
    h, w = d.shape
    L = np.array(light_xy, dtype=np.float32)
    L = L / max(float(np.linalg.norm(L)), 1e-6)
    z0 = z_of(d)
    occ = np.zeros_like(d)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rad_m = max(radius_m * rad_scale, 0.05)
    for s in range(1, steps + 1):
        t = s / float(steps)
        pix_r = np.clip(rad_m * proj_k / np.maximum(z0, 1.0), 2.0, 48.0)
        ouv_x = xx + L[0] * pix_r * t
        ouv_y = yy + L[1] * pix_r * t
        xi = np.clip(np.floor(ouv_x), 0, w - 1).astype(np.int32)
        yi = np.clip(np.floor(ouv_y), 0, h - 1).astype(np.int32)
        d1 = d[yi, xi]
        z1 = z_of(d1)
        dz = z0 - z1
        max_dz = rad_m * (0.35 + 0.65 * t)
        wgt = (1.0 - t) * (1.0 - t)
        cand = wgt * np.clip(dz / np.maximum(max_dz, 1e-3), 0, 1)
        valid = (
            (dz > 0.02)
            & (dz <= max_dz)
            & (d < GROUND_D_MAX)
            & (d1 < GROUND_D_MAX)
            & (z0 < 25.0)
        )
        occ = np.where(valid, occ + cand * (1.0 - occ), occ)
    return np.clip(occ, 0, 1)


def contact_occlusion(d, light_xy=(0.35, -0.75), radius_m=1.2, proj_k=600.0, steps=10):
    fine = contact_occ_radius(d, light_xy, radius_m, proj_k, steps, 0.40)
    coarse = contact_occ_radius(d, light_xy, radius_m, proj_k, steps, 1.00)
    return np.maximum(fine, coarse)


def composite(col, occ, strength=0.45, luma0=0.05, luma1=0.18, protect=True):
    luma = 0.2126 * col[..., 0] + 0.7152 * col[..., 1] + 0.0722 * col[..., 2]
    if protect:
        prot = np.clip((luma - luma0) / max(luma1 - luma0, 1e-3), 0, 1)
    else:
        prot = np.ones_like(luma)
    k = 1.0 - occ * strength * prot
    return col * k[..., None]


def main() -> None:
    col, d, _ = make_scene()
    occ = contact_occlusion(d)
    ground = d < GROUND_D_MAX
    occ = np.where(ground, occ, 0.0)
    sh = 1.0 - occ
    dbg = np.stack([sh, sh, sh], axis=-1)
    red = col * (1.0 - 0.85 * occ[..., None]) + np.array([1.0, 0.15, 0.1]) * (0.85 * occ[..., None])
    comp_p = composite(col, occ, protect=True)
    comp_n = composite(col, occ, protect=False)
    panel = np.concatenate([col, dbg, red, comp_p, comp_n], axis=1)
    panel = np.clip(panel * 255.0, 0, 255).astype(np.uint8)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if Image is not None:
        Image.fromarray(panel, mode="RGB").save(OUT)
    else:
        ppm = OUT.with_suffix(".ppm")
        h, w, _ = panel.shape
        with open(ppm, "wb") as f:
            f.write(f"P6\n{w} {h}\n255\n".encode("ascii"))
            f.write(panel.tobytes())
    mean_occ = float(occ[ground].mean()) if np.any(ground) else 0.0
    veg = (col[..., 1] < 0.15) & ground
    if np.any(veg):
        d_prot = float(np.abs(comp_p[veg] - col[veg]).mean())
        d_raw = float(np.abs(comp_n[veg] - col[veg]).mean())
        print(f"wrote {OUT} mean_occ_ground={mean_occ:.3f} veg_delta protect={d_prot:.4f} raw={d_raw:.4f}")
    else:
        print(f"wrote {OUT} mean_occ_ground={mean_occ:.3f}")


if __name__ == "__main__":
    main()
