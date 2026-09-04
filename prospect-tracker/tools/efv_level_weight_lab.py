# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""LEVEL AND LEAGUE WEIGHTS for MiLB performance as an eFV driver (owner ask, 2026-09-04).

The question: "what is the weight of a DSL performance compared to a Double A performance?
My instinct says AA > A+ > A > AAA > CPX > DSL. Find and derive weights for the correlation
strength of each league level, and maybe weight by specific conferences too, because the
PCL is friendly to hitters so hitting well there should count less."

Two different quantities are hiding in that ask and this lab keeps them apart, because
conflating them is how a level weight becomes a scouting-grade proxy.

  RAW STRENGTH   rho(level-relative performance at level L, first-6yr WAR) among the
                 players who posted a qualifying season at L. This is the question as
                 asked. It is also heavily SELECTED: a player only reaches AAA if someone
                 already believed in him, and AA/AAA seasons sit closer to the majors, so
                 raw strength partly measures who gets there rather than what the level says.

  INCREMENTAL    the same correlation after the consensus FV and age-relative-to-level are
  STRENGTH       partialled out. This is the quantity an eFV DRIVER needs, because eFV
                 already carries the scouting grade and the age read. A level whose raw
                 strength is high and whose incremental strength is zero tells the model
                 nothing it did not already know.

The environment question (PCL) is handled by the norms, not by a hand penalty: every rate
here is already level-relative to CONTEMPORANEOUS season-and-level norms via
efv_dataset._resolved_norms, so a hitter-friendly league is normalised by its own league's
median before anything is compared. Part 3 then asks whether a residual LEAGUE effect
survives that normalisation, which is the honest form of the PCL question: if the norms
already absorb it, a second penalty would double-count.

Leakage: seasons are restricted by the same rule efv_dataset._milb_features uses, cutoff
repair included. Exposure gate is the model's own, 50 PA / 60 BF.

Run:
    python tools/efv_level_weight_lab.py
    python tools/efv_level_weight_lab.py --side hit
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_dataset as ds                    # noqa: E402  READ ONLY
import efv_model as E                       # noqa: E402  READ ONLY
import milb_history as mh                   # noqa: E402  READ ONLY

sys.path.insert(0, str(ROOT / "tools"))
import efv_mde_lab as M                     # noqa: E402
import efv_volume_driver_lab as V           # noqa: E402  reuses the eligibility rule

OUT_PATH = ROOT / "data" / "xfv_level_weight_eval.json"
SEED = 20260807
LEVELS = ("DSL", "CPX", "A", "A+", "AA", "AAA")
MIN_CELL = 40            # do not report a level or league cell thinner than this
MIN_LEAGUE_CELL = 40
BOOT = 2000

HIT_KEYS = ("ops_rel", "obp_rel", "iso_rel", "k_rel", "bb_rel")
PIT_KEYS = ("k_rel", "bb_rel", "era_rel")


def _resid(y: np.ndarray, Z: np.ndarray) -> np.ndarray:
    """y with the columns of Z projected out (least squares, intercept included)."""
    A = np.column_stack([np.ones(len(y)), Z]) if Z.size else np.ones((len(y), 1))
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    return y - A @ beta


def collect(side: str) -> dict:
    """One record per (row, level) with a qualifying season at that level."""
    from efv_dataset import matrix_path
    group = "pitching" if side == "pit" else "hitting"
    minexp = 60 if side == "pit" else 50
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in raw if r["kind"] == "debuted"]
    prep = E._prep(deb, "target_censored", side)
    by_key = {r["player_key"]: r for r in raw}
    recs = []
    for r in prep:
        src = by_key.get(r.get("player_key")) or {}
        mlbam = src.get("mlbam_id")
        seasons = V.eligible_seasons(mlbam, int(r["decision_year"]), src.get("cutoff"), group)
        birth = str(src.get("birth_date") or "")[:4]
        byear = int(birth) if birth.isdigit() else None
        # the most-exposed qualifying season at each level = the player's home there
        best: dict[str, tuple[float, dict, int]] = {}
        for s in seasons:
            for row in s["rows"]:
                lv = row.get("level")
                if lv not in LEVELS:
                    continue
                exp = ds._f(row.get("bf") if side == "pit" else row.get("pa")) or 0.0
                if exp < minexp:
                    continue
                if lv not in best or exp > best[lv][0]:
                    best[lv] = (exp, row, s["season"])
        for lv, (exp, row, season) in best.items():
            norms = ds._resolved_norms(season, lv, group)
            rates = ds._season_rates(row, norms, side, shrink=True)
            recs.append({
                "player_key": r.get("player_key"), "level": lv, "season": season,
                "league": row.get("league") or "?", "exposure": exp,
                "age": (season - byear) if byear else None,
                "y": float(r["target"]), "w": float(r.get("weight", 1.0) or 1.0),
                "fv": float(r["fv"]), "dy": int(r["decision_year"]),
                "rates": {k: float(rates.get(k, 0.0)) for k in
                          (PIT_KEYS if side == "pit" else HIT_KEYS)},
            })
    return {"side": side, "recs": recs, "n_rows": len(prep)}


def _boot_ci(x: np.ndarray, y: np.ndarray, w: np.ndarray, rng) -> list[float]:
    vals = []
    n = len(y)
    for _ in range(BOOT):
        s = rng.integers(0, n, n)
        v = M.wrho(x[s], y[s], w[s])
        if np.isfinite(v):
            vals.append(float(v))
    if not vals:
        return None
    a = np.array(vals)
    return [round(float(np.percentile(a, 2.5)), 4), round(float(np.percentile(a, 97.5)), 4)]


def strengths(coll: dict) -> dict:
    side = coll["side"]
    keys = PIT_KEYS if side == "pit" else HIT_KEYS
    rng = np.random.default_rng(SEED)
    by_level = defaultdict(list)
    for r in coll["recs"]:
        by_level[r["level"]].append(r)
    out = {}
    for lv in LEVELS:
        rs = by_level.get(lv) or []
        if len(rs) < MIN_CELL:
            out[lv] = {"n": len(rs), "reported": False,
                       "why": f"cell under MIN_CELL {MIN_CELL}; a weight here would be noise"}
            continue
        y = np.array([r["y"] for r in rs])
        w = np.array([r["w"] for r in rs])
        fv = np.array([r["fv"] for r in rs])
        age = np.array([r["age"] if r["age"] is not None else np.nan for r in rs])
        age = np.where(np.isfinite(age), age, np.nanmedian(age) if np.isfinite(np.nanmedian(age)) else 0.0)
        Z = np.column_stack([fv, age])
        y_res = _resid(y, Z)
        block = {"n": len(rs), "reported": True,
                 "mean_age": round(float(np.mean(age)), 2),
                 "mean_fv": round(float(np.mean(fv)), 2), "keys": {}}
        for k in keys:
            x = np.array([r["rates"][k] for r in rs])
            if np.allclose(x, x[0]):
                continue
            x_res = _resid(x, Z)
            block["keys"][k] = {
                "raw_rho": round(float(M.wrho(x, y, w)), 4),
                "raw_ci95": _boot_ci(x, y, w, rng),
                "incremental_rho": round(float(M.wrho(x_res, y_res, w)), 4),
                "incremental_ci95": _boot_ci(x_res, y_res, w, rng),
            }
        # the level's headline = the best-performing key by |incremental rho|. SELECTION
        # BIAS is declared rather than hidden: picking the best of five keys per level
        # inflates the reported value, so the headline is a description, not a test.
        if block["keys"]:
            bk = max(block["keys"], key=lambda k: abs(block["keys"][k]["incremental_rho"]))
            block["headline_key"] = bk
            block["headline_incremental_rho"] = block["keys"][bk]["incremental_rho"]
            block["headline_raw_rho"] = block["keys"][bk]["raw_rho"]
            block["headline_key_is_max_of"] = len(block["keys"])
            for leg in ("raw", "incremental"):
                ci = block["keys"][bk][f"{leg}_ci95"]
                block[f"headline_{leg}_excludes_zero"] = bool(
                    ci and (ci[0] > 0 or ci[1] < 0))
        out[lv] = block
    # Normalised weights on the incremental leg, which is the one a driver would use.
    # SIGNED, and a cell whose interval spans zero is given weight 0.0 rather than a
    # rank: an unsigned |rho| normalisation made the thinnest and noisiest cell (DSL,
    # n=71, a NEGATIVE point estimate) come out as the heaviest level, which is the
    # opposite of what a weight is for.
    live = {lv: b for lv, b in out.items()
            if b.get("reported") and "headline_incremental_rho" in b}
    for leg in ("incremental", "raw"):
        sig = {lv: b[f"headline_{leg}_rho"] for lv, b in live.items()
               if b.get(f"headline_{leg}_excludes_zero") and b[f"headline_{leg}_rho"] > 0}
        mx = max(sig.values()) if sig else 0.0
        for lv, b in live.items():
            r = b[f"headline_{leg}_rho"]
            b[f"derived_weight_{leg}"] = (
                round(r / mx, 3) if (mx > 0 and b.get(f"headline_{leg}_excludes_zero")
                                     and r > 0) else 0.0)
        for lv, b in live.items():
            b[f"weight_note_{leg}"] = (
                "0.0 means the interval spans zero or the point estimate is negative, "
                "so this level buys nothing on this leg. It does NOT mean the level is "
                "worthless, only that this pool cannot resolve it.")
    return out


def leagues(coll: dict) -> dict:
    """Residual LEAGUE effect after the level norms have already normalised the rates."""
    side = coll["side"]
    keys = PIT_KEYS if side == "pit" else HIT_KEYS
    rng = np.random.default_rng(SEED + 5)
    by = defaultdict(list)
    for r in coll["recs"]:
        by[(r["level"], r["league"])].append(r)
    out = {}
    for (lv, lg), rs in sorted(by.items()):
        if len(rs) < MIN_LEAGUE_CELL:
            continue
        y = np.array([r["y"] for r in rs])
        w = np.array([r["w"] for r in rs])
        fv = np.array([r["fv"] for r in rs])
        Z = fv.reshape(-1, 1)
        y_res = _resid(y, Z)
        blk = {"n": len(rs), "mean_label": round(float(y.mean()), 3),
               "mean_fv": round(float(fv.mean()), 2), "keys": {}}
        for k in keys:
            x = np.array([r["rates"][k] for r in rs])
            if np.allclose(x, x[0]):
                continue
            ci = _boot_ci(_resid(x, Z), y_res, w, rng)
            blk["keys"][k] = {
                "incremental_rho": round(float(M.wrho(_resid(x, Z), y_res, w)), 4),
                "incremental_ci95": ci,
                "excludes_zero": bool(ci and (ci[0] > 0 or ci[1] < 0)),
            }
        out[f"{lv}|{lg}"] = blk
    # THE FAMILY IS LARGE AND THE READ IS SELECTED. Roughly 18 league cells per side times
    # five keys, and any table that reports the best key per cell is reading a maximum.
    # Recorded here so no cell in it can be quoted as a finding on its own interval.
    n_cells = sum(len(b["keys"]) for b in out.values())
    n_excl = sum(1 for b in out.values() for kk in b["keys"].values() if kk["excludes_zero"])
    out["_family"] = {
        "league_cells": len(out), "key_tests": n_cells,
        "intervals_excluding_zero": n_excl,
        "expected_by_chance_at_95pct": round(0.05 * n_cells, 1),
        "reading": ("compare intervals_excluding_zero against expected_by_chance. These "
                    "intervals are UNCORRECTED and the per-cell headline is a max over "
                    "five keys, so a count near the chance line is a null, not a set of "
                    "league effects. No cell here is a finding on its own."),
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--side", choices=["hit", "pit", "both"], default="both")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    sides = ("hit", "pit") if a.side == "both" else (a.side,)
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_level_weight_lab.py",
        "asked_by": "owner, 2026-09-04: per-level and per-league weights for MiLB performance",
        "label_basis": "eWAR v2 (the 2026-09-04 label epoch)",
        "owner_expectation": "AA > A+ > A > AAA > CPX > DSL",
        "two_quantities": {
            "raw": "rho(level-relative performance at L, first-6yr WAR), selected pool",
            "incremental": "the same with consensus FV and age partialled out; this is the "
                           "quantity an eFV driver needs, because eFV already has the grade",
        },
        "environment_note": ("every rate is already level-relative to CONTEMPORANEOUS "
                             "season-and-level norms, so a hitter-friendly league such as "
                             "the PCL is normalised by its own league median before "
                             "anything is compared. Part 3 asks whether a RESIDUAL league "
                             "effect survives that; a second hand penalty on top would "
                             "double-count."),
        "min_cell": MIN_CELL, "bootstrap_B": BOOT, "seed": SEED,
        "sides": {},
    }
    for side in sides:
        t0 = time.time()
        coll = collect(side)
        print(f"=== {side}: {coll['n_rows']} rows -> {len(coll['recs'])} (row, level) "
              f"records ({time.time()-t0:.0f}s)", flush=True)
        out["sides"][side] = {
            "n_rows": coll["n_rows"], "n_records": len(coll["recs"]),
            "by_level": strengths(coll),
            "by_league": leagues(coll),
        }
        lv = out["sides"][side]["by_level"]
        order = sorted((l for l in lv if lv[l].get("reported")),
                       key=lambda l: -abs(lv[l].get("headline_incremental_rho", 0)))
        print(f"  incremental order: {' > '.join(order)}", flush=True)
    if not a.no_write:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
