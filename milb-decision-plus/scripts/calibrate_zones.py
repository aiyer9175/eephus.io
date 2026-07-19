# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Calibrate the stringer-pixel -> plate-feet transform and zone geometry.

Fit on dual-system pitches (both x/y pixels and pX/pZ feet present):
MLB + AAA. Validate:
  1. coordinate R2 / RMSE on a held-out season
  2. geometry: in/out boundary fit on TRUE coords vs official zone labels
  3. full pipeline: zone from predicted coords vs official labels, including
     an OUT-OF-DOMAIN test on tracked A-ball/CPX parks (minor-league
     stringers), which is the honest proxy for AA/A+ stringer quality.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA_PROCESSED, DATA_RAW, OUTPUTS, log_run
from zone_lib import CALIB_PATH, assign_zone

V2 = DATA_RAW / "pitches_v2"
SEED = 42


def load_dual(dirs: list[str], max_rows_per_dir: int = 400_000) -> pd.DataFrame:
    frames = []
    rng = np.random.default_rng(SEED)
    for name in dirs:
        files = glob.glob(str(V2 / name / "pitches_*.parquet"))
        if not files:
            continue
        df = pd.concat([pd.read_parquet(
            f, columns=["px", "pz", "sx", "sy", "sz_top", "sz_bot", "zone",
                        "season", "level", "bat_side"]) for f in files],
            ignore_index=True)
        df = df[df.px.notna() & df.sx.notna() & df.sy.notna()]
        if len(df) > max_rows_per_dir:
            df = df.iloc[rng.choice(len(df), max_rows_per_dir, replace=False)]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def fit_transform(train: pd.DataFrame) -> dict:
    fx = LinearRegression().fit(train[["sx"]], train.px)
    h = (train.sz_top - train.sz_bot)
    Z = pd.DataFrame({"sy": train.sy, "sz_top": train.sz_top,
                      "sz_bot": train.sz_bot, "sy_height": train.sy * h})
    fz = LinearRegression().fit(Z, train.pz)
    return {
        "px": {"intercept": float(fx.intercept_), "sx": float(fx.coef_[0])},
        "pz": {"intercept": float(fz.intercept_),
               **{k: float(c) for k, c in zip(Z.columns, fz.coef_)}},
    }


def apply_transform(df: pd.DataFrame, calib: dict):
    cx, cz = calib["px"], calib["pz"]
    h = df.sz_top - df.sz_bot
    px = cx["intercept"] + cx["sx"] * df.sx
    pz = (cz["intercept"] + cz["sy"] * df.sy + cz["sz_top"] * df.sz_top
          + cz["sz_bot"] * df.sz_bot + cz["sy_height"] * df.sy * h)
    return px, pz


def fit_geometry(df: pd.DataFrame) -> dict:
    """Grid-search in/out boundary against official labels using TRUE coords."""
    z = pd.to_numeric(df.zone, errors="coerce")
    truth_in = z.between(1, 9)
    best = None
    for xlim in np.arange(0.70, 0.96, 0.01):
        for zbuf in np.arange(-0.05, 0.16, 0.01):
            pred = assign_zone(df.px, df.pz, df.sz_top, df.sz_bot, xlim, zbuf)
            agree = ((pred <= 9) == truth_in).mean()
            if best is None or agree > best[0]:
                best = (agree, round(float(xlim), 3), round(float(zbuf), 3))
    return {"inout_agreement_true_coords": round(float(best[0]), 4),
            "xlim": best[1], "zbuf": best[2]}


def main() -> None:
    train = load_dual(["2025_MLB", "2025_AAA"])
    test = load_dual(["2026_MLB", "2026_AAA"])
    print(f"dual-system pitches: train {len(train):,}, holdout {len(test):,}")

    calib = fit_transform(train)
    geo = fit_geometry(train.sample(min(len(train), 200_000), random_state=SEED))
    calib["geometry"] = {"xlim": geo["xlim"], "zbuf": geo["zbuf"]}
    print("transform:", json.dumps(calib, indent=None))
    print("geometry fit:", geo)

    rows = []
    for name, df in [("holdout_MLB_AAA_2026", test)]:
        px, pz = apply_transform(df, calib)
        r2x = 1 - ((px - df.px) ** 2).sum() / ((df.px - df.px.mean()) ** 2).sum()
        r2z = 1 - ((pz - df.pz) ** 2).sum() / ((df.pz - df.pz.mean()) ** 2).sum()
        z = pd.to_numeric(df.zone, errors="coerce")
        pred = assign_zone(px, pz, df.sz_top, df.sz_bot, geo["xlim"], geo["zbuf"])
        valid = z.notna()
        inout = ((pred <= 9) == z.between(1, 9))[valid].mean()
        exact = (pred[valid.to_numpy()] == z[valid].to_numpy()).mean()
        rows.append({"set": name, "n": len(df),
                     "px_r2": round(float(r2x), 4), "pz_r2": round(float(r2z), 4),
                     "px_rmse_ft": round(float(np.sqrt(((px - df.px) ** 2).mean())), 3),
                     "pz_rmse_ft": round(float(np.sqrt(((pz - df.pz) ** 2).mean())), 3),
                     "inout_agree": round(float(inout), 4),
                     "zone_exact_agree": round(float(exact), 4)})

    # out-of-domain: tracked minor-league parks (minors stringers)
    for name, dirs in [("ood_A_tracked", ["2025_A", "2026_A"]),
                       ("ood_CPX_tracked", ["2025_CPX", "2026_CPX"])]:
        df = load_dual(dirs)
        if len(df) < 5000:
            continue
        px, pz = apply_transform(df, calib)
        z = pd.to_numeric(df.zone, errors="coerce")
        pred = assign_zone(px, pz, df.sz_top, df.sz_bot, geo["xlim"], geo["zbuf"])
        valid = z.notna()
        inout = ((pred <= 9) == z.between(1, 9))[valid].mean()
        exact = (pred[valid.to_numpy()] == z[valid].to_numpy()).mean()
        rows.append({"set": name, "n": len(df),
                     "px_r2": round(float(1 - ((px - df.px) ** 2).sum()
                                          / ((df.px - df.px.mean()) ** 2).sum()), 4),
                     "pz_r2": round(float(1 - ((pz - df.pz) ** 2).sum()
                                          / ((df.pz - df.pz.mean()) ** 2).sum()), 4),
                     "px_rmse_ft": round(float(np.sqrt(((px - df.px) ** 2).mean())), 3),
                     "pz_rmse_ft": round(float(np.sqrt(((pz - df.pz) ** 2).mean())), 3),
                     "inout_agree": round(float(inout), 4),
                     "zone_exact_agree": round(float(exact), 4)})

    rep = pd.DataFrame(rows)
    out = OUTPUTS / "zone_calibration"
    out.mkdir(parents=True, exist_ok=True)
    rep.to_csv(out / "zone_calibration_validation.csv", index=False)
    print(rep.to_string(index=False))

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    CALIB_PATH.write_text(json.dumps(calib, indent=2))
    print(f"\ncalibration -> {CALIB_PATH}")
    log_run("zone_calibration_v1", **{r["set"]: r["inout_agree"] for r in rows},
            geometry=calib["geometry"])


if __name__ == "__main__":
    main()
