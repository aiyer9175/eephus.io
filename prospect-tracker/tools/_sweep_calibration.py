# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE: calibration. LEVEL calibration audit of eFV.

SCRATCH LAB. Reads only; writes only under data/ (the eval artifact) and the
scratch out dir. Does NOT import-modify efv_model / efv_dataset.

Stage 1 (frame): forward-chained OOS reproduction of the SERVED scoring stack
(efv_score.run) per decision-year fold: OLS(FV) anchor + lean ridge + linear
output calibration -> xfv_war -> vf.realized_implied_fv -> board-scale affine
-> rank_war blend -> per-fold rank-preserving quantile display map. Metadata
(level / age / acquisition cohort / censoring) is carried through so every
calibration statistic can be sliced by population.

Run:  python tools/_sweep_calibration.py frame
      python tools/_sweep_calibration.py report
"""
from __future__ import annotations

import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import efv_model as M                      # noqa: E402  (read-only use)
import value_framework as vf               # noqa: E402
from efv_dataset import matrix_path        # noqa: E402
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration  # noqa: E402

OUT = HERE / "_sweep_calib_out"
OUT.mkdir(exist_ok=True)
FRAME = OUT / "frame.json"

TARGET_SEASONS = 6
# folds: 2016-2020 decision years are FULLY RESOLVED (6yr window ends <= 2025 for
# 2020 debuts); 2021-2024 carry KM-censored targets and are scored separately.
RESOLVED_FOLDS = (2016, 2017, 2018, 2019, 2020)
CENSORED_FOLDS = (2021, 2022, 2023, 2024)

# bucket bands are per-season AVG WAR over the 6yr window (value_framework_config
# buckets.*.band); the eFV label is the SUM, so multiply by 6.
BUCKETS = ("bust", "bench", "regular", "good", "star")
BUCKET_EDGES_SUM = (3.0, 9.0, 15.0, 24.0)     # <3 bust, 3-9 bench, 9-15 regular, 15-24 good, 24+ star
BUCKET_MID_SUM = (0.0, 6.0, 12.0, 19.2, 30.0)  # midpoint_war * 6
WITHIN_CV = (0.0, 0.30, 0.38, 0.48, 0.70)


def _live_lambdas():
    lam, src = M._sf_live_lambdas()
    return lam, src


def _board_scale():
    """The served W-SIDESCALE affine (xfv.json meta.board_scale)."""
    try:
        meta = json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))["meta"]
        bs = meta.get("board_scale") or {}
        if bs.get("enabled"):
            return {s: (float(bs["coeffs"][s]["a"]), float(bs["coeffs"][s]["b"]))
                    for s in ("hit", "pit")}, "data/xfv.json meta.board_scale"
    except Exception:
        pass
    return {"hit": (0.0, 1.0), "pit": (0.0, 1.0)}, "identity (board_scale unavailable)"


def _age_at(birth_date, year):
    if not birth_date:
        return None
    try:
        return round(int(year) - int(str(birth_date)[:4]), 1)
    except (TypeError, ValueError):
        return None


def _acq(r):
    if float(r.get("is_ifa") or 0) >= 0.5:
        return "IFA"
    if float(r.get("is_college") or 0) >= 0.5:
        return "college"
    if r.get("pick_overall") is not None:
        return "HS"
    return "unknown"


def _meta_of(rows):
    """player_key -> carried metadata from the raw matrix row."""
    out = {}
    for r in rows:
        milb = r.get("milb") or {}
        out[r["player_key"]] = {
            "kind": r["kind"],
            "censored": bool(r.get("censored")),
            "target_resolved": r.get("target_resolved"),
            "target_censored": r.get("target_censored"),
            "level": milb.get("milb_level"),
            "age": milb.get("age"),
            "age_rel_level": milb.get("age_rel_level"),
            "acq": _acq(r),
            "position": r.get("position"),
            "birth_date": r.get("birth_date"),
            "debut_year": r.get("debut_year"),
            "n_sources": r.get("n_sources"),
        }
    return out


def build_frame():
    lam, lam_src = _live_lambdas()
    bs, bs_src = _board_scale()
    frame = []
    for side in ("hit", "pit"):
        is_pit = side == "pit"
        raw_rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        raw = [r for r in raw_rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
        meta = _meta_of(raw)
        data = M._prep(raw, "target_censored", side)
        keys, _m = M._feature_spec(side)
        a_bs, b_bs = bs[side]
        for yr in (*RESOLVED_FOLDS, *CENSORED_FOLDS):
            tr = [r for r in data if r["decision_year"] < yr]
            te = [r for r in data if r["decision_year"] == yr]
            if len(te) < 15 or len(tr) < 60:
                continue
            ols = M._fit_ols_fv(tr)
            ridge = _fit_ridge(tr, keys)
            if not (ols and ridge):
                continue
            cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
            a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
            pool = []
            for r in te:
                pk = r["player_key"]
                mt = meta[pk]
                xfv_war = max(-2.0, a + b * _predict(ridge, r["feats"]))
                dy = mt.get("debut_year") or yr
                age = _age_at(mt.get("birth_date"), dy)
                gm_age = None if age is None else float(age) + TARGET_SEASONS
                g_raw = vf.realized_implied_fv(xfv_war, is_pit, age=gm_age,
                                               position=mt.get("position"),
                                               exposure_seasons=TARGET_SEASONS)
                if g_raw is None:
                    continue
                g_board = max(20.0, min(80.0, a_bs + b_bs * float(g_raw)))
                cons_war = max(0.0, M._pred_ols(ols, r["fv"]))
                rank_war = (1 - lam[side]) * cons_war + lam[side] * xfv_war
                pool.append({
                    "pk": pk, "side": side, "year": yr, "fv": r["fv"],
                    "war": r["target"],                       # KM-censored label (fit target)
                    "war_resolved": mt.get("target_resolved"),
                    "censored": mt["censored"], "kind": mt["kind"],
                    "xfv_war": xfv_war, "cons_war": cons_war, "rank_war": rank_war,
                    "grade_model_raw": round(float(g_raw), 3),
                    "grade_board": round(g_board, 3),
                    "level": mt["level"], "age": mt["age"],
                    "age_rel_level": mt["age_rel_level"], "acq": mt["acq"],
                    "position": mt.get("position"), "n_sources": mt.get("n_sources"),
                })
            # per-fold rank-preserving quantile display map onto that pool's
            # consensus-FV distribution (efv_score.run / run_live, replicated per fold)
            if pool:
                target = sorted(p["fv"] for p in pool)
                order = sorted(range(len(pool)), key=lambda i: (pool[i]["rank_war"], pool[i]["pk"]))
                m = len(pool)
                for rank_pos, i in enumerate(order):
                    pos = ((rank_pos / (m - 1)) if m > 1 else 0.0) * (m - 1)
                    lo = int(pos); hi = min(m - 1, lo + 1); frac = pos - lo
                    pool[i]["grade_quantile"] = round(target[lo] * (1 - frac) + target[hi] * frac, 3)
            frame.extend(pool)
    payload = {"lambda": lam, "lambda_source": lam_src,
               "board_scale": {k: list(v) for k, v in bs.items()}, "board_scale_source": bs_src,
               "resolved_folds": list(RESOLVED_FOLDS), "censored_folds": list(CENSORED_FOLDS),
               "n": len(frame), "rows": frame}
    FRAME.write_text(json.dumps(payload), encoding="utf-8")
    print(f"frame n={len(frame)}  lambda={lam} ({lam_src})  board_scale={bs} ({bs_src})")
    for side in ("hit", "pit"):
        rs = [r for r in frame if r["side"] == side and not r["censored"]]
        print(f"  {side}: resolved n={len(rs)}  folds={sorted({r['year'] for r in rs})}")
    return payload


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "frame"
    if cmd == "frame":
        build_frame()
