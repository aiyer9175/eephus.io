# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Universal zone assignment from best-available coordinates.

Tracked pitches use true plate coordinates (pX/pZ). Untracked pitches use
stringer pixel coordinates (x/y) mapped to feet via a transform calibrated on
the millions of pitches that carry BOTH systems. Geometry constants for the
in/out boundary are themselves fit to maximize agreement with the official
zone labels, and the whole pipeline is validated out-of-domain on tracked
minor-league parks (minors stringers ≈ MLB stringers check).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

CALIB_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "zone_calibration.json"

DEFAULT_SZ_TOP = 3.40
DEFAULT_SZ_BOT = 1.57


def load_calibration() -> dict:
    return json.loads(CALIB_PATH.read_text())


def pixels_to_feet(sx, sy, sz_top, sz_bot, calib) -> tuple[np.ndarray, np.ndarray]:
    """Apply the calibrated linear transform. Inputs are array-like."""
    sx = np.asarray(sx, dtype=float)
    sy = np.asarray(sy, dtype=float)
    sz_top = np.where(pd.isna(sz_top), DEFAULT_SZ_TOP, np.asarray(sz_top, dtype=float))
    sz_bot = np.where(pd.isna(sz_bot), DEFAULT_SZ_BOT, np.asarray(sz_bot, dtype=float))
    cx = calib["px"]
    px = cx["intercept"] + cx["sx"] * sx
    cz = calib["pz"]
    height = sz_top - sz_bot
    pz = (cz["intercept"] + cz["sy"] * sy + cz["sz_top"] * sz_top
          + cz["sz_bot"] * sz_bot + cz["sy_height"] * sy * height)
    return px, pz


def assign_zone(px, pz, sz_top, sz_bot, xlim: float, zbuf: float) -> np.ndarray:
    """Gameday-style zone: 1-9 = 3x3 in-zone grid (catcher's view,
    1 = up-and-left/glove-side-high for RHB frame: top row 1,2,3 left->right),
    11-14 = out-of-zone quadrants (11 up-left, 12 up-right, 13 down-left,
    14 down-right)."""
    px = np.asarray(px, dtype=float)
    pz = np.asarray(pz, dtype=float)
    top = np.where(pd.isna(sz_top), DEFAULT_SZ_TOP, np.asarray(sz_top, dtype=float)) + zbuf
    bot = np.where(pd.isna(sz_bot), DEFAULT_SZ_BOT, np.asarray(sz_bot, dtype=float)) - zbuf

    in_x = np.abs(px) <= xlim
    in_z = (pz >= bot) & (pz <= top)
    in_zone = in_x & in_z

    col = np.clip(np.floor((px + xlim) / (2 * xlim / 3)), 0, 2)        # 0=left
    h = np.maximum(top - bot, 0.1)
    row = np.clip(np.floor((top - pz) / (h / 3)), 0, 2)                # 0=top
    zone_in = (1 + col + 3 * row).astype(int)

    up = pz > (top + bot) / 2
    left = px < 0
    zone_out = np.where(up, np.where(left, 11, 12), np.where(left, 13, 14))

    out = np.where(in_zone, zone_in, zone_out)
    out = np.where(np.isnan(px) | np.isnan(pz), -1, out)
    return out.astype(int)


def best_zone_frame(p: pd.DataFrame, calib: dict) -> pd.DataFrame:
    """Add zone_final (1-9/11-14), px_final/pz_final, zone_source to a pitch
    frame with columns px,pz,sx,sy,sz_top,sz_bot,zone."""
    have_track = p.px.notna() & p.pz.notna()
    have_str = p.sx.notna() & p.sy.notna()

    px_f = p.px.to_numpy(dtype=float).copy()
    pz_f = p.pz.to_numpy(dtype=float).copy()
    src = np.where(have_track, "tracked", "none")

    idx = (~have_track) & have_str
    if idx.any():
        spx, spz = pixels_to_feet(p.loc[idx, "sx"], p.loc[idx, "sy"],
                                  p.loc[idx, "sz_top"], p.loc[idx, "sz_bot"], calib)
        px_f[idx.to_numpy()] = spx
        pz_f[idx.to_numpy()] = spz
        src[idx.to_numpy()] = "stringer"

    p = p.copy()
    p["px_final"], p["pz_final"], p["zone_source"] = px_f, pz_f, src
    geo = calib["geometry"]
    derived = assign_zone(px_f, pz_f, p.sz_top, p.sz_bot, geo["xlim"], geo["zbuf"])
    # tracked pitches keep the official zone label where present
    official = pd.to_numeric(p.zone, errors="coerce")
    p["zone_final"] = np.where(official.notna(), official.fillna(-1), derived).astype(int)
    p.loc[(p.zone_final == -1) | (p.zone_source == "none"), "zone_final"] = np.nan
    return p
