# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Section 3 of docs/PROJ_PATH_SHAPE_GATE.md: the power artifact,
data/proj_shape_mde.json.

THE FRAME THIS LAB MAY TOUCH (3.1): DEV (label seasons 2008-2011) and simulation,
nothing else. Every bundle here is fitted at a base <= 2011 (labels <= 2010) and
every prediction call carries `ceiling = 2011`, so no cell whose label season is
2012 or later is ever predicted, let alone scored, in this process. The artifact
records the bases and label seasons it read; test_proj_shape_gate.py pins that the
SCORED set is a subset of DEV and that no label season at or above 2012 was read
for any purpose.

What it publishes:
  * per lambda on the registered grid, the paired test-only cluster-bootstrap sd
    (B = 1000, clustered on player, seed 20260918) of every statistic class 3.2
    names, candidate minus S on the DEV cells; the point deltas are NOT published
    here (they are the dev frontier, which the gate artifact publishes);
  * the calibration bootstrap: B = 200 full-refit draws on DEV, the player pool
    resampled and BOTH arms refitted per draw with their point-in-time blends,
    giving ratio = sd_full / sd_test; vif_applied = max(1.8, ratio) (3.2);
  * transport to GATE: sd_GATE = sd_DEV * sqrt(n_players_DEV / n_players_GATE),
    with the GATE player count a structural count of rows (no label, no
    prediction);
  * MDE95 = 1.645 * sd_GATE * vif_applied for every class, one floor per class;
  * the detection checks of 3.3: ARM A at a planted +0.0065 WAR MAE degradation
    with the real paired-difference structure; each ARM B lever at the nearer-zero
    end of its published prior CI, against its Holm k = 3 step-one floor.

Run: python tools/proj_shape_mde_lab.py --work <dir> [--procs 10]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import proj_shape_gate as G  # noqa: E402

OUT = ROOT / "data" / "proj_shape_mde.json"
CEILING = max(G.DEV_LABELS)                      # 2011
DEV_BASES = tuple(range(G.EVAL_FIRST_BASE, CEILING + 1))
OOF_BASES = tuple(range(G.FIRST_BASE + 1, CEILING + 1))   # 2004..2011
CAL_LAMBDA = 0.20                                # default named in the artifact
CLASSES = ("pooled_mae", "per_h_mae", "pooled_bias", "star_mae", "star_bias",
           "coverage", "pinball_q10", "pinball_q90")


def _z_holm_step1() -> float:
    from efv_power_lab import _z_one_sided
    return _z_one_sided(G.HOLM_ALPHA / G.HOLM_K)


def compose_arm(F, oof, arm_bases, weights=None):
    """{B: {side: (idx, composed)}} for the DEV scoring bases, blends refit point in
    time from this arm's own out-of-fold predictions."""
    preds, lams = {}, {}
    for B in arm_bases:
        bl = G.fit_blends(F, oof, B, weights)
        lams[B] = bl
        preds[B] = {}
        for side in ("hit", "pit"):
            idx, Q = oof[B][side]
            preds[B][side] = (idx, G.compose(Q, G.star_flag(F[side], idx), bl["mean"], bl["star"]))
    return preds, lams


def class_sd(S: dict, cand: str, base: str = "S") -> dict:
    out = {}
    num, den = G.paired_delta(S, cand, base, "mae")
    out["pooled_mae"] = G.boot_sd(S, num, den)
    out["per_h_mae"] = {}
    for h in range(1, 5):
        num, den = G.paired_delta(S, cand, base, "mae", h=h)
        out["per_h_mae"][str(h)] = G.boot_sd(S, num, den) if den.sum() else None
    num, den = G.paired_delta(S, cand, base, "bias")
    out["pooled_bias"] = G.boot_sd(S, num, den)
    num, den = G.paired_delta(S, cand, base, "mae", star=True)
    out["star_mae"] = G.boot_sd(S, num, den)
    num, den = G.paired_delta(S, cand, base, "bias", star=True)
    out["star_bias"] = G.boot_sd(S, num, den)
    for k in ("coverage", "pinball_q10", "pinball_q90"):
        num, den = G.paired_delta(S, cand, base, k)
        out[k] = G.boot_sd(S, num, den)
    return out


def gate_player_count(F: dict, sel_fn=None) -> int:
    """Players in the GATE frame's cells: a STRUCTURAL count (which (player, base,
    horizon) cells exist and are not two-sided). It reads the base and the label
    SEASON of a cell, never its label value or any prediction."""
    ids = set()
    for side in ("hit", "pit"):
        f = F[side]
        ls = G.label_seasons(f)
        cm = (np.isin(ls, G.GATE_LABELS) & (f["base"][:, None] >= G.EVAL_FIRST_BASE)
              & (~f["excl_cell"]) & (~f["excl_row"][:, None]))
        if sel_fn is not None:
            cm &= sel_fn(side, f)
        ids |= set(f["mlbam"][cm.any(axis=1)].tolist())
    return len(ids)


def lever_cells():
    """The B0 cell definitions (tools/proj_calibration_lab.py's convention) as
    predicates over a scored dict and over the frame (for structural counts)."""
    def band(a):
        return np.where(a <= 24, "<=24", np.where(a <= 27, "25-27", np.where(
            a <= 30, "28-30", np.where(a <= 33, "31-33", "34+"))))

    def S_age(S, cell):
        _, ab, side = cell.split(":")
        return (band(S["age_t"]) == ab) & (S["side"] == side)
    return band, S_age


def _cal_draw(args):
    """One full-refit draw: resample players with replacement, refit S and the
    calibration candidate at every base 2004-2011 on the resampled frame (labels
    <= B - 1), refit both arms' blends point in time, score the resampled DEV cells."""
    work, d = args
    G.setup(Path(work))
    F = G.load_frame(Path(work))
    assert F["meta"].get("label_ceiling") == CEILING, "3.1: labels above 2011 are present"
    rng = np.random.default_rng(G.SEED_BOOT + 1000 + d)
    ids = np.unique(np.concatenate([F[s]["mlbam"][F[s]["base"] <= CEILING] for s in ("hit", "pit")]))
    pick = rng.integers(0, len(ids), len(ids))
    cnt = np.bincount(pick, minlength=len(ids))
    lookup = dict(zip(ids.tolist(), cnt.tolist()))
    weights = {s: np.array([lookup.get(int(m), 0) for m in F[s]["mlbam"]], dtype=int)
               for s in ("hit", "pit")}
    arms = {"S": None, "J%.2f" % CAL_LAMBDA: CAL_LAMBDA}
    preds = {}
    for arm, lam in arms.items():
        oof = {}
        for B in OOF_BASES:
            hmax = CEILING - B + 1
            if lam is None:
                b = G.fit_s(F, B, weights=weights,
                            horizons=tuple(range(1, min(G.HORIZONS, hmax) + 1)))
            else:
                b = G.fit_joint(F, B, lam, weights=weights)
            oof[B] = {}
            for side in ("hit", "pit"):
                idx = np.flatnonzero((F[side]["base"] == B) & (weights[side] > 0))
                oof[B][side] = (idx, G.predict_raw(b, F, side, idx, CEILING))
        preds[arm], _ = compose_arm(F, oof, DEV_BASES, weights)
    # weighted delta pooled MAE over DEV cells
    num = den = 0.0
    a = "J%.2f" % CAL_LAMBDA
    for side in ("hit", "pit"):
        f = F[side]
        cm = G.cell_mask(f, "DEV")
        for B in DEV_BASES:
            idxS, cS = preds["S"][B][side]
            idxJ, cJ = preds[a][B][side]
            assert np.array_equal(idxS, idxJ)
            m = cm[idxS]
            w = weights[side][idxS][:, None] * m
            y = np.nan_to_num(f["Y"][idxS])
            diff = np.abs(np.nan_to_num(cJ["c"]) - y) - np.abs(np.nan_to_num(cS["c"]) - y)
            num += float((w * diff).sum())
            den += float(w.sum())
    return d, num / den


def run(work: Path, procs: int, b_full: int) -> dict:
    t0 = time.time()
    # 3.1, mechanically: every process of this lab (this one and every pool worker it
    # spawns, which inherit the environment) blanks each label above 2011 on load
    os.environ["PROJ_SHAPE_LABEL_CEILING"] = str(CEILING)
    G.setup(work)
    F = G.load_frame(work)
    assert F["meta"].get("label_ceiling") == CEILING, "3.1: labels above 2011 are present"
    arms = ["S"] + [G.arm_name(l) for l in G.LAMBDA_GRID]
    jobs = [(a, B) for a in arms for B in OOF_BASES]
    G.ensure_bundles(work, jobs, procs)
    oof, preds, lams = {}, {}, {}
    for a in arms:
        oof[a] = G.oof_for(work, F, a, OOF_BASES, CEILING)
        preds[a], lams[a] = compose_arm(F, oof[a], DEV_BASES)
    S = G.scored(F, preds, "DEV", CEILING)
    read_labels = sorted({int(x) for x in (S["base"] + S["h"] - 1)})
    assert set(read_labels) <= set(G.DEV_LABELS), read_labels
    np_dev = G.n_players(S)
    np_gate = gate_player_count(F)
    transport = math.sqrt(np_dev / np_gate)

    # --- calibration bootstrap (full refit) ---
    from multiprocessing import Pool
    tc = time.time()
    with Pool(procs) as pool:
        full = sorted(pool.map(_cal_draw, [(str(work), d) for d in range(b_full)]))
    full_vals = np.array([v for _, v in full])
    cal_arm = "J%.2f" % CAL_LAMBDA
    num, den = G.paired_delta(S, cal_arm, "S", "mae")
    sd_test_cal = G.boot_sd(S, num, den)
    sd_full = float(np.nanstd(full_vals, ddof=1))
    ratio = sd_full / sd_test_cal if sd_test_cal else None
    vif_applied = max(G.VIF_REGISTERED, ratio or 0.0)
    cal_wall = round(time.time() - tc, 1)

    # --- per-lambda floors ---
    per_lam = {}
    for lam in G.LAMBDA_GRID:
        a = G.arm_name(lam)
        sd = class_sd(S, a)

        def mde(v):
            return None if v is None else round(G.Z95_ONE * v * transport * vif_applied, 5)
        per_lam["%.2f" % lam] = {
            "sd_dev_test_only": {k: (round(v, 6) if not isinstance(v, dict) else
                                     {h: (round(x, 6) if x is not None else None) for h, x in v.items()})
                                 for k, v in sd.items()},
            "mde95_gate": {k: (mde(v) if not isinstance(v, dict) else
                               {h: mde(x) for h, x in v.items()}) for k, v in sd.items()},
        }
    mde_pooled = {k: v["mde95_gate"]["pooled_mae"] for k, v in per_lam.items()}

    # --- ARM A detection check (3.3), design-matched ---
    det_a = {}
    for k, v in per_lam.items():
        a = G.arm_name(float(k))
        num, den = G.paired_delta(S, a, "S", "mae")
        sel = den > 0
        diff = num[sel] - num[sel].mean() + G.M          # real structure, mean planted at M
        planted = np.zeros(len(num)); planted[sel] = diff
        boots = G.cluster_boot(S, planted, den, G.B_TEST, G.SEED_BOOT)
        sd_g = float(np.nanstd(boots, ddof=1)) * transport * vif_applied
        lb = G.M - G.Z95_ONE * sd_g
        det_a[k] = {"planted_delta_mae": G.M, "sd_gate_vif": round(sd_g, 6),
                    "one_sided_lower_bound": round(lb, 6), "detected": bool(lb > 0)}

    # --- ARM B floors and detection (3.3, 5.5) on the S composition ---
    band, S_age = lever_cells()
    z1 = _z_holm_step1()
    e = S["S:c"] - S["y"]
    lev = {}
    sign = {c: (1.0 if G.PLANTED[c] > 0 else -1.0) for c in G.PLANTED}

    def cell_sel(c):
        if c == "role:C":
            return S["role"] == "C"
        if c == "star":
            return S["star"].astype(bool)
        return S_age(S, c)

    def gate_count(c):
        def fn(side, f):
            ls = G.label_seasons(f)
            if c == "role:C":
                return np.repeat((f["role"] == "C")[:, None], G.HORIZONS, axis=1)
            if c == "star":
                return np.repeat(f["star"][:, None], G.HORIZONS, axis=1)
            _, ab, sd_ = c.split(":")
            at = f["X"][:, 0][:, None] + np.arange(G.HORIZONS)[None, :]
            return (band(at) == ab) & (side == sd_) & np.ones_like(ls, dtype=bool)
        return gate_player_count(F, fn)

    cells = {}
    for c in G.PLANTED:
        sel = cell_sel(c)
        boots = G.cluster_boot(S, np.where(sel, e, 0.0), sel.astype(float), G.B_TEST, G.SEED_BOOT)
        npd = G.n_players(S, sel)
        npg = gate_count(c)
        sd_g = float(np.nanstd(boots, ddof=1)) * math.sqrt(npd / npg) * vif_applied if npg else None
        cells[c] = {"n_dev": int(sel.sum()), "n_players_dev": npd, "n_players_gate": npg,
                    "sd_gate_vif": round(sd_g, 6) if sd_g else None}
    # B-AGE as a unit: n-weighted, prior-signed mean bias over its four cells
    age_sel = np.zeros(len(e)); age_den = np.zeros(len(e))
    for c in G.AGE_CELLS:
        sel = cell_sel(c)
        age_sel += np.where(sel, sign[c] * e, 0.0); age_den += sel
    boots = G.cluster_boot(S, age_sel, age_den, G.B_TEST, G.SEED_BOOT)
    npd_age = G.n_players(S, age_den > 0)

    def age_union(side, f):
        at = f["X"][:, 0][:, None] + np.arange(G.HORIZONS)[None, :]
        out = np.zeros(at.shape, dtype=bool)
        for c in G.AGE_CELLS:
            _, ab, sd_ = c.split(":")
            out |= (band(at) == ab) & (side == sd_)
        return out
    npg_age = gate_player_count(F, age_union)
    sd_age = float(np.nanstd(boots, ddof=1)) * math.sqrt(npd_age / npg_age) * vif_applied
    planted_age = (sum(cells[c]["n_dev"] * abs(G.PLANTED[c]) for c in G.AGE_CELLS)
                   / sum(cells[c]["n_dev"] for c in G.AGE_CELLS))
    lev["B-AGE"] = {"cells": list(G.AGE_CELLS), "statistic": (
        "n-weighted mean over the four registered age cells of the bias signed by its "
        "published prior's direction"), "sd": round(sd_age, 6),
        "mde95_holm_k3": round(z1 * sd_age, 6), "planted": round(planted_age, 6),
        "n_players_dev": npd_age, "n_players_gate": npg_age}
    for name, c in (("B-C", "role:C"), ("B-STAR", "star")):
        sd = cells[c]["sd_gate_vif"]
        lev[name] = {"cells": [c], "statistic": "the cell's signed bias", "sd": round(sd, 6),
                     "mde95_holm_k3": round(z1 * sd, 6), "planted": abs(G.PLANTED[c])}
    for name, v in lev.items():
        v["detected"] = bool(v["planted"] >= v["mde95_holm_k3"])
        v["verdict_if_not_detected"] = "UNDERPOWERED"
    lev_cells = cells

    res = {
        "generated_at": G.utc_now(),
        "gate": G.GATE_DOC + " section 3, under amendment A-2 (fwar corpus, after step Z)",
        "read": G.EARLY_READ + ": registered 2026-10-02 (moved after step Z by A-2), "
                "produced 2026-10-14 after the blast artifact",
        "producer": "tools/proj_shape_mde_lab.py",
        "fixture": G.FIXTURE,
        "corpus": G.corpus_stamp(work),
        "frame_read": {
            "scored_bases": list(DEV_BASES),
            "scored_label_seasons": read_labels,
            "training_label_seasons_max": CEILING - 1,
            "blend_fit_label_seasons_max": CEILING - 1,
            "prediction_ceiling_label_season": CEILING,
            "labels_blanked_above": CEILING,
            "frames": ["DEV", "simulation"],
            "note": ("every label above season 2011 was blanked on load in every process "
                     "of this lab; every bundle fitted at a base <= 2011 on labels <= 2010; "
                     "every prediction capped at label season 2011; no GATE, CONFIRM or "
                     "Tier-2 label or prediction exists in this process. The GATE player "
                     "counts the transport formula needs are STRUCTURAL: which (player, "
                     "base, horizon) cells exist and are not two-sided, read off the base "
                     "and the label SEASON, never a label value"),
        },
        "n_cells_dev": int(len(S["y"])),
        "n_players_dev": np_dev,
        "n_players_gate_structural": np_gate,
        "transport": {"formula": "sd_GATE = sd_DEV * sqrt(n_players_DEV / n_players_GATE)",
                      "factor": round(transport, 6)},
        "bootstrap": {
            "B": G.B_TEST, "refits_per_draw": 0, "train_resampled": False,
            "seed": G.SEED_BOOT, "clustered_on": "player",
            "vif_registered": G.VIF_REGISTERED,
            "calibration": {"B": b_full, "refits_per_draw": 2 * len(OOF_BASES),
                            "train_resampled": True, "arms": ["S", cal_arm],
                            "calibration_candidate_default": (
                                "lambda 0.20, the middle of the non-zero grid; the measured "
                                "ratio is applied to every lambda's sd"),
                            "blends_refit_per_draw": True,
                            "sd_full": round(sd_full, 6), "sd_test": round(sd_test_cal, 6),
                            "wall_s": cal_wall, "seed_base": G.SEED_BOOT + 1000},
            "vif_measured": round(ratio, 4) if ratio else None,
            "vif_applied": round(vif_applied, 4),
        },
        "z_one_sided": G.Z95_ONE,
        "per_lambda": per_lam,
        "mde95_pooled_mae_by_lambda": mde_pooled,
        "margin_M": G.M,
        "margin_guard": {k: ("UNDERPOWERED_NO_MARGIN" if v >= G.M else "clears")
                         for k, v in mde_pooled.items()},
        "arm_a_detection": det_a,
        "arm_b": {"holm_k": G.HOLM_K, "z_step1": round(z1, 4), "levers": lev,
                  "cells": lev_cells,
                  "floor_key": "mde95_holm_k3",
                  "planted_source": "the nearer-zero end of each cell's published CI in "
                                    "data/proj_calibration_eval.json (3.3)"},
        "reading": [
            "Floors are per statistic class and not transferable between classes (3.2).",
            "MDE95 is one-sided (1.645 sd) with the VIF applied after transport.",
            UNCONDITIONAL_BASIS_REF,
        ],
        "wall_time_s": round(time.time() - t0, 1),
    }
    return res


UNCONDITIONAL_BASIS_REF = G.UNCONDITIONAL_BASIS


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--procs", type=int, default=10)
    ap.add_argument("--b-full", type=int, default=G.B_FULL)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    r = run(Path(a.work), a.procs, a.b_full)
    Path(a.out).write_text(json.dumps(r, indent=1, default=G._jsonable) + "\n", encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("bootstrap", "mde95_pooled_mae_by_lambda",
                                        "margin_guard", "arm_b")}, indent=1, default=G._jsonable))
