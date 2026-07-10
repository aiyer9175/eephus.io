# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tjStuff+-style scoring for MLB Stats API pitch feed rows.

The model artifact and feature construction come from Thomas Nestico's
MIT-licensed tjstuff_plus project:
https://github.com/tnestico/tjstuff_plus
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path
from typing import Iterable


MODEL_PATH = Path(__file__).parent / "model" / "tjstuff_plus" / "lgbm_model_2020_2023.joblib"
FEATURES = [
    "start_speed",
    "spin_rate",
    "extension",
    "az",
    "ax",
    "x0",
    "z0",
    "speed_diff",
    "az_diff",
    "ax_diff",
]

# Notebook cell 30 prints the 2024 prediction distribution as xRV/100:
# mean 0.35, stdev 0.68. The model target itself is per-pitch run value.
TJSTUFF_TARGET_MEAN = 0.0035
TJSTUFF_TARGET_STD = 0.0068
FASTBALL_TYPES = {"FF", "SI", "FC", "FT"}


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _load_model():
    if not MODEL_PATH.exists():
        return None
    try:
        import joblib
    except Exception:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return joblib.load(MODEL_PATH)
    except Exception:
        return None


def _mean(values: Iterable) -> float | None:
    nums = [_num(v) for v in values]
    nums = [v for v in nums if v is not None]
    return sum(nums) / len(nums) if nums else None


def _primary_fastball(rows: list[dict]) -> dict | None:
    by_type: dict[str, list[dict]] = {}
    for row in rows:
        code = row.get("pitch_type")
        if code in FASTBALL_TYPES:
            by_type.setdefault(code, []).append(row)
    candidates = by_type or {}
    if not candidates:
        for row in rows:
            if row.get("pitch_type"):
                candidates.setdefault(row["pitch_type"], []).append(row)
    if not candidates:
        return None

    def key(item: tuple[str, list[dict]]) -> tuple[int, float]:
        _code, pitch_rows = item
        return (len(pitch_rows), _mean(r.get("velo") for r in pitch_rows) or 0.0)

    _code, pitch_rows = max(candidates.items(), key=key)
    return {
        "velo": _mean(r.get("velo") for r in pitch_rows),
        "az": _mean(r.get("az") for r in pitch_rows),
        "ax": _mean(r.get("ax_mirrored") for r in pitch_rows),
    }


def _feature_row(row: dict, primary: dict) -> list[float] | None:
    velo = _num(row.get("velo"))
    spin = _num(row.get("spin"))
    extension = _num(row.get("extension"))
    az = _num(row.get("az"))
    ax = _num(row.get("ax_mirrored"))
    x0 = _num(row.get("x0_mirrored"))
    z0 = _num(row.get("release_height"))
    fb_velo = _num(primary.get("velo"))
    fb_az = _num(primary.get("az"))
    fb_ax = _num(primary.get("ax"))
    if None in (velo, spin, extension, az, ax, x0, z0, fb_velo, fb_az, fb_ax):
        return None
    return [
        velo,
        spin,
        extension,
        az,
        ax,
        x0,
        z0,
        velo - fb_velo,
        az - fb_az,
        abs(ax - fb_ax),
    ]


def score_pitch_points(points: list[dict]) -> list[dict]:
    """Return copies of pitch rows with `tj_stuff_plus` when scoreable."""

    model = _load_model()
    if model is None:
        return [dict(p) for p in points]

    rows: list[dict] = []
    for point in points:
        row = dict(point)
        ax = _num(row.get("ax"))
        x0 = _num(row.get("x0"))
        hand = str(row.get("pitcher_hand") or "R").upper()
        row["ax_mirrored"] = -ax if hand == "L" and ax is not None else ax
        if x0 is None:
            row["x0_mirrored"] = None
        elif hand == "L":
            row["x0_mirrored"] = x0
        else:
            row["x0_mirrored"] = -x0
        rows.append(row)

    primary = _primary_fastball(rows)
    if not primary:
        return rows

    feature_rows: list[list[float]] = []
    feature_indexes: list[int] = []
    for idx, row in enumerate(rows):
        feats = _feature_row(row, primary)
        if feats is None:
            continue
        feature_rows.append(feats)
        feature_indexes.append(idx)
    if not feature_rows:
        return rows

    # Predict with the feature NAMES the model was fitted with. A bare
    # list/array triggers sklearn's "X does not have valid feature names"
    # UserWarning — and the old catch_warnings() suppression mutates global
    # filter state, which is not thread-safe under run_monthly's parallel
    # pipelines, so the warning still leaked intermittently.
    try:
        import pandas as pd
        names = getattr(model, "feature_names_in_", None)   # ndarray on sklearn Pipelines
        cols = list(names) if names is not None and len(names) else FEATURES
        x = pd.DataFrame(feature_rows, columns=cols)
    except Exception:                                    # noqa: BLE001 — names are an optimization
        x = feature_rows
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        preds = model.predict(x)
    for idx, pred in zip(feature_indexes, preds):
        z = (float(pred) - TJSTUFF_TARGET_MEAN) / TJSTUFF_TARGET_STD
        rows[idx]["tj_stuff_plus"] = round(max(20.0, min(180.0, 100.0 - (z * 10.0))), 1)
        rows[idx]["tj_stuff_plus_model"] = "tjstuff_plus_2020_2023_lgbm"
    return rows
