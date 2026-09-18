# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""RE-GATE 1: the SHIPPED xHEM+ / fwdHEM+ construction, pre-registered in
docs/HEM_RIV_REGATE_GATE.md (frozen 2026-09-18, before any number here was
computed).

The defect this lab exists to measure: `xhem_plus` and `fwdhem_plus` were gated
on constructions NORMALIZED OVER THE EVAL SET (tools/xhem_plus_lab.py X-H3 /
X-H5), while the columns that ship re-standardize over the SERVED POOL
(hitter_export._join_xhem_plus / ._join_fwdhem_plus, Savant PA >= 100 over the
whole season). The construction that passed the gate is not the construction on
the board. This lab gates what ships.

  A1 (xhem_plus)    delta = rho(xHEM+_served(Y), wOBA(Y+1))
                          - rho(actual wOBA(Y), wOBA(Y+1))
  A2 (fwdhem_plus)  delta = rho(fwdHEM+_served(Y), wOBA(Y+1))
                          - rho(Savant xwOBA(Y), wOBA(Y+1))

Both arms run the pre-registered decomposition ladder D0..D4; ONLY D4 (the
served column, integers as served) carries a verdict. Both bootstrap
conventions are reported for every cell, always: v1 (raw pooled target, iid
paired resample) and v2 (within-outcome-season z target, player-clustered
season-stratified resample). Every gap carries an MDE95 derived in run
(1.645 * bootstrap sd), never a stored constant. Multiplicity: Holm over the
two primary arms, k = 2, applied separately within each convention
(tools/efv_power_lab.holm_family).

The pair set is the frozen X-H3 pair set and is NOT extended here; it may not
be extended before 2026-11-15 (see the gate document).

  -> data/xhem_served_regate_eval.json

Run: python tools/xhem_served_regate_lab.py [--no-write]
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("EEPHUS_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import hem_plus  # noqa: E402
import plus_lab_harness as plh  # noqa: E402
import xhem_plus_lab as xhl  # noqa: E402
from efv_power_lab import holm_family  # noqa: E402

DATA = ROOT / "data"
OUT_PATH = DATA / "xhem_served_regate_eval.json"
GATE_DOC = "docs/HEM_RIV_REGATE_GATE.md"

# ---- frozen by the gate document; changing any of these is a new gate ------ #
SEASONS = list(xhl.SEASONS)          # 2016-2025 ex-2020
MIN_PA = xhl.MIN_PA                  # 200.0, the eval pair-set floor
SERVED_MIN_PA = 100.0                # hitter_export._XHEM_MIN_PA / _FWDHEM_MIN_PA
W_XWOBA, W_HEM = xhl.BLEND_W_XWOBA, xhl.BLEND_W_HEM   # 0.7 / 0.3
GAIN = hem_plus.HEM_SPREAD_GAIN      # 2.28
BOOT = 2000
SEED_R1 = 20260918
ORIG_SEED_XH3 = xhl.SEED             # 20260705, for the D0 reproduction draw
ORIG_SEED_XH5 = xhl.BLEND_SEED       # 20260706
MDE_Z = 1.645                        # one-sided 95%, docs/EFV_GATE_STANDARD.md

TARGET_V1 = "actual wOBA in Y+1 (raw, pooled across seasons)"
TARGET_V2 = "actual wOBA in Y+1"


def _r4(v):
    return None if v is None else round(v, 4)


def _mu_sd(vals):
    """hitter_export._join_fwdhem_plus._mu_sd, reproduced exactly."""
    k = len(vals)
    mu = sum(vals) / k
    sd = (sum((v - mu) ** 2 for v in vals) / (k - 1)) ** 0.5
    return mu, sd


def _sd(xs):
    if len(xs) < 2:
        return None
    mu = sum(xs) / len(xs)
    return (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


# --------------------------------------------------------------------------- #
# bootstrap with the DRAWS kept. plh.iid_boot_gaps / plh.cluster_boot_gaps emit
# only the summary; Holm and the in-run MDE95 need the gap distribution sd. The
# draw construction is identical to the harness, and run() asserts that the
# summaries agree exactly with the harness on the D0 cells.
# --------------------------------------------------------------------------- #
def iid_gaps_full(primary, baselines: dict, tgt, boot: int, seed: int) -> dict:
    n = len(tgt)
    rng = random.Random(seed)
    gaps = {k: [] for k in baselines}
    for _ in range(boot):
        samp = [rng.randrange(n) for _ in range(n)]
        st = [tgt[i] for i in samp]
        rp = plh.spearman([primary[i] for i in samp], st)
        if rp is None:
            continue
        for k, series in baselines.items():
            rb = plh.spearman([series[i] for i in samp], st)
            if rb is not None:
                gaps[k].append(rp - rb)
    return gaps


def cluster_gaps_full(primary, baselines: dict, tgt, players, strata_key,
                      boot: int, seed: int) -> dict:
    if not (len(primary) == len(tgt) == len(players) == len(strata_key)):
        raise ValueError("parallel array length mismatch")
    by_player: dict = {}
    first: dict = {}
    for i, p in enumerate(players):
        by_player.setdefault(p, []).append(i)
        s = strata_key[i]
        if p not in first or s < first[p]:
            first[p] = s
    strata: dict = {}
    for p, s in first.items():
        strata.setdefault(s, []).append(p)
    strata = {s: sorted(strata[s], key=str) for s in sorted(strata)}
    rng = random.Random(seed)
    gaps = {k: [] for k in baselines}
    for _ in range(boot):
        idx: list = []
        for s in strata:
            pl = strata[s]
            m = len(pl)
            for _ in range(m):
                idx.extend(by_player[pl[rng.randrange(m)]])
        st = [tgt[i] for i in idx]
        rp = plh.spearman([primary[i] for i in idx], st)
        if rp is None:
            continue
        for k, series in baselines.items():
            rb = plh.spearman([series[i] for i in idx], st)
            if rb is not None:
                gaps[k].append(rp - rb)
    return gaps


def cell(primary, baseline, tgt, draws) -> dict:
    """One comparison cell: rhos, the gap CI, the in-run MDE95 and its sign."""
    c = plh.ci(draws)
    sd = _sd(draws)
    return {
        "rho_primary": _r4(plh.spearman(primary, tgt)),
        "rho_baseline": _r4(plh.spearman(baseline, tgt)),
        "gap_ci": c,
        "gap_sd_bootstrap": _r4(sd),
        "mde95_in_run": _r4(MDE_Z * sd) if sd else None,
        "n_boot_draws": len(draws),
        "lo95_gt_0": bool(c and c["lo95"] > 0),
        "hi95_lt_0": bool(c and c["hi95"] < 0),
    }


# --------------------------------------------------------------------------- #
# served constructions, reproduced from hitter_export
# --------------------------------------------------------------------------- #
def served_xhem_pool(savant_year: dict) -> tuple:
    """(PA-weighted pool mean xwOBA, pool size) over the served PA >= 100 pool.
    hitter_export._join_xhem_plus."""
    xw = {m: (x, pa) for m, (_w, x, pa) in savant_year.items()
          if pa >= SERVED_MIN_PA and x > 0}
    if not xw:
        return (None, 0)
    dtot = sum(pa for _x, pa in xw.values())
    pool = (sum(x * pa for x, pa in xw.values()) / dtot) if dtot else None
    return (pool, len(xw))


def served_xhem_unrounded(xwoba: float, pool_mean: float) -> float:
    return 100.0 + GAIN * (100.0 * xwoba / pool_mean - 100.0)


def eval_pool_anchor(xs, pas, weighted: bool):
    """The same ratio anchor arithmetic fitted on the EVAL pool (the pair-set
    rows of one predictor season). Ladder rung D1 only."""
    if not xs:
        return None
    if weighted:
        d = sum(pas)
        return (sum(x * p for x, p in zip(xs, pas)) / d) if d else None
    return sum(xs) / len(xs)


def served_fwdhem_pool(savant_year: dict, hem_year: dict):
    """The served fwdHEM+ normalizer for one season: the PA >= 100 Savant pool
    that ALSO carries a HEM core. hitter_export._join_fwdhem_plus."""
    xw = {m: x for m, (_w, x, pa) in savant_year.items()
          if pa >= SERVED_MIN_PA and x > 0}
    pool = {m: (x, hem_year[m]) for m, x in xw.items() if hem_year.get(m) is not None}
    if len(pool) < 2:
        return None
    mu_x, sd_x = _mu_sd([v[0] for v in pool.values()])
    mu_h, sd_h = _mu_sd([v[1] for v in pool.values()])
    if not sd_x or not sd_h:
        return None
    blend = {m: W_XWOBA * (x - mu_x) / sd_x + W_HEM * (h - mu_h) / sd_h
             for m, (x, h) in pool.items()}
    _mu_b, sd_b = _mu_sd(list(blend.values()))
    if not sd_b:
        return None
    return {"mu_x": mu_x, "sd_x": sd_x, "mu_h": mu_h, "sd_h": sd_h,
            "sd_b": sd_b, "n_pool": len(pool)}


def served_fwdhem_unrounded(xwoba: float, hem_raw: float, p: dict) -> float:
    z = (W_XWOBA * (xwoba - p["mu_x"]) / p["sd_x"]
         + W_HEM * (hem_raw - p["mu_h"]) / p["sd_h"])
    return p["mu_h"] + p["sd_h"] * (z / p["sd_b"])


def _ties(vals) -> int:
    return len(vals) - len(set(vals))


def build_pair_set(data: dict) -> dict:
    """The frozen X-H3 pair set, built exactly as tools/xhem_plus_lab.run does."""
    woba, xwoba, tgt, pa_y = [], [], [], []
    mids, pys, oys = [], [], []
    dropped_partial = 0
    for y in SEASONS:
        cur, nxt = data.get(y), data.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, (w, x, pa) in cur.items():
            nn = nxt.get(mid)
            if nn and pa >= MIN_PA and nn[2] >= MIN_PA:
                if not plh.season_complete(y + 1):
                    dropped_partial += 1
                    continue
                woba.append(w)
                xwoba.append(x)
                tgt.append(nn[0])
                pa_y.append(pa)
                mids.append(mid)
                pys.append(y)
                oys.append(y + 1)
    return {"woba": woba, "xwoba": xwoba, "tgt": tgt, "pa_y": pa_y,
            "mids": mids, "pys": pys, "oys": oys,
            "n": len(woba), "dropped_partial": dropped_partial}


def _holm_rows(h: dict) -> list:
    for v in h.values():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "key" in v[0]:
            return v
    return []


def run(write: bool = True) -> dict:
    t0 = time.time()
    data = {}
    for y in SEASONS + [max(SEASONS) + 1]:
        d = xhl.load_savant_woba(y)
        if d:
            data[y] = d
    ps = build_pair_set(data)
    n = ps["n"]
    print(f"  X-H3 pair set: {n} pairs (dropped {ps['dropped_partial']} partial-outcome)")

    hem_by_year = {y: xhl.load_hem_core(y) for y in sorted(set(ps["pys"]))}
    xpool = {y: served_xhem_pool(data[y]) for y in sorted(set(ps["pys"]))}
    fpool = {y: served_fwdhem_pool(data[y], hem_by_year.get(y, {}))
             for y in sorted(set(ps["pys"]))}

    tgt = ps["tgt"]
    tgt_v2 = plh.zscore_within(ps["oys"], tgt)
    mids, pys = ps["mids"], ps["pys"]

    by_season_rows: dict = {}
    for i in range(n):
        by_season_rows.setdefault(pys[i], []).append(i)

    # ---- ARM A1: xhem_plus, baseline raw actual wOBA(Y), unchanged ---------- #
    base_a1 = ps["woba"]
    eval_anchor = {y: eval_pool_anchor([ps["xwoba"][i] for i in idx],
                                       [ps["pa_y"][i] for i in idx], False)
                   for y, idx in by_season_rows.items()}
    a1 = {}
    a1["D0"] = list(ps["xwoba"])
    a1["D1"] = [served_xhem_unrounded(ps["xwoba"][i], eval_anchor[pys[i]])
                for i in range(n)]
    a1["D2"] = [served_xhem_unrounded(ps["xwoba"][i], xpool[pys[i]][0])
                for i in range(n)]
    a1["D3"] = list(a1["D2"])
    a1["D4"] = [float(int(round(v))) for v in a1["D3"]]

    # ---- ARM A2: fwdhem_plus, baseline raw Savant xwOBA(Y), unchanged ------- #
    keep = [i for i in range(n)
            if hem_by_year.get(pys[i], {}).get(mids[i]) is not None
            and fpool.get(pys[i]) is not None]
    dropped_no_hem = n - len(keep)
    xw5 = [ps["xwoba"][i] for i in keep]
    hem5 = [hem_by_year[pys[i]][mids[i]] for i in keep]
    tgt5 = [tgt[i] for i in keep]
    mids5 = [mids[i] for i in keep]
    pys5 = [pys[i] for i in keep]
    oys5 = [ps["oys"][i] for i in keep]
    n5 = len(keep)
    tgt5_v2 = plh.zscore_within(oys5, tgt5)
    print(f"  X-H5 pair set: {n5} pairs (dropped {dropped_no_hem} with no HEM core)")

    zx5 = plh.zscore_within(pys5, xw5)
    zh5 = plh.zscore_within(pys5, hem5)
    a2 = {}
    a2["D0"] = [W_XWOBA * a + W_HEM * b for a, b in zip(zx5, zh5)]
    a2["D1"] = [W_XWOBA * (xw5[i] - fpool[pys5[i]]["mu_x"]) / fpool[pys5[i]]["sd_x"]
                + W_HEM * (hem5[i] - fpool[pys5[i]]["mu_h"]) / fpool[pys5[i]]["sd_h"]
                for i in range(n5)]
    a2["D2"] = [served_fwdhem_unrounded(xw5[i], hem5[i], fpool[pys5[i]])
                for i in range(n5)]
    a2["D3"] = list(a2["D2"])
    a2["D4"] = [float(int(round(v))) for v in a2["D3"]]
    base_a2 = xw5

    def ladder(arm_vals, baseline, base_name, tgt_raw, tgt_z, players, pred,
               orig_seed):
        out = {}
        for rung in ("D0", "D1", "D2", "D3", "D4"):
            seeds = [(SEED_R1, "regate")]
            if rung == "D0":
                seeds.append((orig_seed, "original"))
            for seed, tag in seeds:
                v1d = iid_gaps_full(arm_vals[rung], {base_name: baseline},
                                    tgt_raw, BOOT, seed)[base_name]
                v2d = cluster_gaps_full(arm_vals[rung], {base_name: baseline},
                                        tgt_z, players, pred, BOOT, seed)[base_name]
                key = rung if tag == "regate" else rung + "_original_seed"
                out[key] = {
                    "seed": seed,
                    "v1": cell(arm_vals[rung], baseline, tgt_raw, v1d),
                    "v2": cell(arm_vals[rung], baseline, tgt_z, v2d),
                    "_v1_draws": v1d, "_v2_draws": v2d,
                    "n_distinct_values": len(set(arm_vals[rung])),
                    "n_tied_rows": _ties(arm_vals[rung]),
                }
        return out

    lad_a1 = ladder(a1, base_a1, "vs_actual_woba", tgt, tgt_v2, mids, pys,
                    ORIG_SEED_XH3)
    lad_a2 = ladder(a2, base_a2, "vs_xwoba_alone", tgt5, tgt5_v2, mids5, pys5,
                    ORIG_SEED_XH5)

    # ---- D0 reproduction check, against the harness itself ----------------- #
    h1 = plh.iid_boot_gaps(a1["D0"], {"vs_actual_woba": base_a1}, tgt, BOOT,
                           ORIG_SEED_XH3)["vs_actual_woba"]
    h2 = plh.cluster_boot_gaps(a1["D0"], {"vs_actual_woba": base_a1}, tgt_v2,
                               mids, pys, BOOT, ORIG_SEED_XH3)["vs_actual_woba"]
    b1 = plh.iid_boot_gaps(a2["D0"], {"vs_xwoba_alone": base_a2,
                                      "vs_hem_core_alone": hem5},
                           tgt5, BOOT, ORIG_SEED_XH5)["vs_xwoba_alone"]
    b2 = plh.cluster_boot_gaps(a2["D0"], {"vs_xwoba_alone": base_a2,
                                          "vs_hem_core_alone": hem5},
                               tgt5_v2, mids5, pys5, BOOT,
                               ORIG_SEED_XH5)["vs_xwoba_alone"]
    repro = {
        "A1": {"harness_v1": h1, "harness_v2": h2,
               "lab_v1": lad_a1["D0_original_seed"]["v1"]["gap_ci"],
               "lab_v2": lad_a1["D0_original_seed"]["v2"]["gap_ci"],
               "published_v1_gap_lo95": 0.0173,
               "published_rho_xwoba": 0.4543, "published_rho_woba": 0.4108,
               "published_n_pairs": 1871},
        "A2": {"harness_v1": b1, "harness_v2": b2,
               "lab_v1": lad_a2["D0_original_seed"]["v1"]["gap_ci"],
               "lab_v2": lad_a2["D0_original_seed"]["v2"]["gap_ci"],
               "published_v1_gap": {"mean": 0.0114, "lo95": 0.0038},
               "published_v2_gap": {"mean": 0.0015, "lo95": -0.0069},
               "published_rho_blend": 0.4658, "published_rho_xwoba": 0.4543},
    }
    repro["A1"]["identical_to_harness"] = bool(
        h1 == repro["A1"]["lab_v1"] and h2 == repro["A1"]["lab_v2"])
    repro["A2"]["identical_to_harness"] = bool(
        b1 == repro["A2"]["lab_v1"] and b2 == repro["A2"]["lab_v2"])
    repro["A1"]["reproduces_published"] = bool(
        lad_a1["D0_original_seed"]["v1"]["rho_primary"] == 0.4543
        and lad_a1["D0_original_seed"]["v1"]["rho_baseline"] == 0.4108
        and repro["A1"]["lab_v1"]["lo95"] == 0.0173 and n == 1871)
    repro["A2"]["reproduces_published"] = bool(
        lad_a2["D0_original_seed"]["v1"]["rho_primary"] == 0.4658
        and lad_a2["D0_original_seed"]["v1"]["rho_baseline"] == 0.4543
        and repro["A2"]["lab_v1"]["lo95"] == 0.0038
        and repro["A2"]["lab_v2"]["lo95"] == -0.0069)

    # ---- A1s: labelled sensitivity, zero verdict weight -------------------- #
    s_hem = [float(int(round(v))) for v in hem5]
    s_xhem = [float(int(round(served_xhem_unrounded(xw5[i], xpool[pys5[i]][0]))))
              for i in range(n5)]
    s1 = iid_gaps_full(s_xhem, {"vs_served_hem_plus": s_hem}, tgt5, BOOT,
                       SEED_R1)["vs_served_hem_plus"]
    s2 = cluster_gaps_full(s_xhem, {"vs_served_hem_plus": s_hem}, tgt5_v2,
                           mids5, pys5, BOOT, SEED_R1)["vs_served_hem_plus"]
    a1s = {"note": ("labelled SENSITIVITY, zero verdict weight (gate R1-3): the "
                    "served xHEM+ integer against the served HEM+ integer on the "
                    "A2 row subset. It informs the display lane only."),
           "v1": cell(s_xhem, s_hem, tgt5, s1),
           "v2": cell(s_xhem, s_hem, tgt5_v2, s2)}

    # ---- multiplicity: Holm k = 2 within each convention -------------------- #
    holm = {}
    for conv in ("v1", "v2"):
        cells = []
        for key, lad in (("A1_xhem_plus", lad_a1), ("A2_fwdhem_plus", lad_a2)):
            dr = lad["D4"]["_%s_draws" % conv]
            cells.append({"key": key, "delta": sum(dr) / len(dr), "sd": _sd(dr)})
        holm[conv] = holm_family(cells, alpha=0.05)

    def holm_reject(conv, key):
        for row in _holm_rows(holm[conv]):
            if row.get("key") == key:
                return bool(row.get("reject_holm"))
        return False

    # ---- the pre-registered decision rule (gate R1-6) ---------------------- #
    def decide(lad, key):
        d4 = lad["D4"]
        p1 = d4["v1"]["lo95_gt_0"] and holm_reject("v1", key)
        p2 = d4["v2"]["lo95_gt_0"] and holm_reject("v2", key)
        if d4["v1"]["hi95_lt_0"] or d4["v2"]["hi95_lt_0"]:
            return ("deprecated",
                    "REFUTED: the D4 gap hi95 is below zero under at least one "
                    "convention, so the claim is contradicted, not merely "
                    "unestablished.", p1, p2)
        if p1 and p2:
            return ("validated",
                    "The SERVED construction clears its baseline under BOTH "
                    "conventions after Holm (k=2).", p1, p2)
        if p1:
            return ("provisional",
                    "DEMOTED: the served construction clears only the legacy v1 "
                    "convention. The one-cycle v1 grandfather clause is spent by "
                    "this re-gate (gate R1-6, rule 3).", p1, p2)
        if p2:
            return ("provisional",
                    "DEMOTED: the served construction clears only v2, which was "
                    "not the pre-declared convention; an undeclared convention "
                    "cannot promote a row.", p1, p2)
        return ("provisional",
                "DEMOTED: not separable from its baseline on the SERVED "
                "construction at this n under either convention.", p1, p2)

    v_a1 = decide(lad_a1, "A1_xhem_plus")
    v_a2 = decide(lad_a2, "A2_fwdhem_plus")

    coverage = {
        "note": ("Coverage is reported separately and is NEVER used to explain a "
                 "gap. The gate speaks only about the PA >= 200 subset while the "
                 "board stamps every tracked hitter at PA >= 100, and that "
                 "sentence travels with the verdict."),
        "pair_set_n_by_predictor_season": {str(y): len(idx) for y, idx
                                           in sorted(by_season_rows.items())},
        "served_normalizer_pool_by_season": {
            str(y): {"xhem_pool_pa_ge_100": xpool[y][1],
                     "fwdhem_pool_pa_ge_100_with_hem_core":
                         (fpool[y]["n_pool"] if fpool.get(y) else 0)}
            for y in sorted(xpool)},
        "board_stamped_never_eligible_by_season": {
            str(y): xpool[y][1] - len(by_season_rows.get(y, []))
            for y in sorted(xpool)},
        "n_pairs_dropped_partial_outcome_season": ps["dropped_partial"],
        "n_pairs_dropped_no_hem_core": dropped_no_hem,
    }

    def clean(lad):
        return {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                for k, v in lad.items()}

    payload = {
        "generated_at": date.today().isoformat(),
        "experiment": "RE-GATE 1 (arms A1, A2)",
        "gate_document": GATE_DOC,
        "pre_registered": "2026-09-18, frozen before any number in this artifact was computed",
        "models": ["xhem_plus", "fwdhem_plus"],
        "seasons": SEASONS,
        "seed": SEED_R1,
        "boot": BOOT,
        "defect_under_test": (
            "xhem_plus and fwdhem_plus were gated on constructions normalized over "
            "the EVAL SET; the shipped columns re-standardize over the SERVED POOL "
            "(hitter_export._join_xhem_plus / ._join_fwdhem_plus, Savant PA >= 100 "
            "over the full season). The normalizer pool and the evaluation pool are "
            "different objects, and the ladder measures what the difference costs."),
        "conventions": {
            "pair_set": ("the frozen X-H3 pair set (Savant PA >= %d in Y and in Y+1, "
                         "complete outcome season)" % int(MIN_PA)),
            "served_normalizer_pool": ("full-season Savant pool at PA >= %d; fwdHEM+ "
                                       "additionally requires a HEM core"
                                       % int(SERVED_MIN_PA)),
            "verdict_rung": "D4, the served column exactly, integers as served",
            "mde95": ("derived in run as 1.645 * bootstrap sd of the gap; no stored "
                      "constant anywhere in this artifact"),
            "approximation_disclosed_in_advance": (
                "the served normalizer is built at pipeline time from whatever Savant "
                "rows exist THEN; this re-gate reconstructs it on COMPLETE season "
                "pools, which is the best available proxy and is biased in one "
                "direction (complete pools are larger and wider). Declared in the "
                "gate document before the run, so it cannot be produced afterwards "
                "to explain away a loss."),
        },
        "harness": plh.convention_meta(TARGET_V1, TARGET_V2),
        "n_forward_pairs": {"A1": n, "A2": n5},
        "d0_reproduction_check": repro,
        "ladder_note": (
            "PRE-REGISTRATION UNDER-SPECIFICATION, disclosed rather than papered "
            "over: the gate R1-5 table introduces the normalizer POOL at D1 and the "
            "normalizer RECIPE at D2, but the A1 D0 construction (raw xwOBA) carries "
            "no normalizer at all, so D1 needs a recipe to change a pool on. "
            "Realisation: A1 D1 applies the ratio recipe fitted on the EVAL pool (the "
            "pair-set rows of that predictor season, unweighted anchor); A1 D2 moves "
            "to the served PA-weighted anchor on the served pool. A2 D1 z-scores the "
            "legs over the SERVED pool under the eval plain 0.7/0.3 blend; A2 D2 adds "
            "the served re-standardize and affine map. D3 is the unrounded served "
            "float and is IDENTICAL to D2 by construction for both arms; it is "
            "emitted anyway so the D3 -> D4 rounding cost is read off a stated rung. "
            "Rungs carry zero verdict weight (R1-5, R1-7); only D4 decides."),
        "arms": {
            "A1_xhem_plus": {
                "estimand": ("rho(xHEM+_served(Y), wOBA(Y+1)) - rho(actual wOBA(Y), "
                             "wOBA(Y+1))"),
                "baseline": "raw actual wOBA(Y), the X-H3 baseline, unchanged",
                "pre_registered_expectation": (
                    "EXPECTED TO SURVIVE: xHEM+ is a monotone map of xwOBA within a "
                    "season, so only cross-season pooling and rounding are exposed."),
                "ladder": clean(lad_a1),
                "passes_v1_after_holm": v_a1[2],
                "passes_v2_after_holm": v_a1[3],
                "verdict": v_a1[0],
                "verdict_reason": v_a1[1],
            },
            "A2_fwdhem_plus": {
                "estimand": ("rho(fwdHEM+_served(Y), wOBA(Y+1)) - rho(Savant "
                             "xwOBA(Y), wOBA(Y+1))"),
                "baseline": "raw Savant xwOBA(Y) alone, the X-H5 baseline, unchanged",
                "pre_registered_expectation": (
                    "EXPECTED TO FAIL: pass_under_v2 is already FALSE in the "
                    "published artifact and this re-gate retires the v1 grandfather "
                    "clause. Recorded up front so the demotion cannot be read "
                    "afterwards as a surprise."),
                "named_exposure": (
                    "the blend ranking depends on the ratio sd_h/sd_x, so a different "
                    "normalizer pool is a different effective weight pair and "
                    "therefore a different ordering. The shipped comment claiming full "
                    "monotonicity covers only the final re-standardize and affine "
                    "map, not the leg normalizers."),
                "ladder": clean(lad_a2),
                "passes_v1_after_holm": v_a2[2],
                "passes_v2_after_holm": v_a2[3],
                "verdict": v_a2[0],
                "verdict_reason": v_a2[1],
            },
        },
        "sensitivity_A1s_served_xhem_vs_served_hem": a1s,
        "multiplicity": {
            "family": ("the two primary arms A1 and A2, Holm k = 2, applied "
                       "SEPARATELY within each convention (gate R1-7)"),
            "total_primary_tests_in_the_gate_document": 3,
            "outside_the_family_by_declaration": ["D0", "D1", "D2", "D3", "A1s",
                                                  "every coverage figure"],
            "v1": holm["v1"], "v2": holm["v2"],
        },
        "coverage": coverage,
        "standing_consequence": (
            "The headline number on a served column is the SERVED construction "
            "number. The eval-normalized figure may appear only as a labelled "
            "reproduction. This binds the whole +index family from 2026-09-18 "
            "forward."),
        "runtime_seconds": round(time.time() - t0, 1),
    }
    payload["verdict"] = {
        "xhem_plus": v_a1[0],
        "fwdhem_plus": v_a2[0],
        "summary": _summary(payload),
    }

    print(json.dumps({"A1_D4_v1": lad_a1["D4"]["v1"]["gap_ci"],
                      "A1_D4_v2": lad_a1["D4"]["v2"]["gap_ci"],
                      "A2_D4_v1": lad_a2["D4"]["v1"]["gap_ci"],
                      "A2_D4_v2": lad_a2["D4"]["v2"]["gap_ci"],
                      "repro": {k: repro[k]["reproduces_published"] for k in repro},
                      "verdicts": {"xhem_plus": v_a1[0], "fwdhem_plus": v_a2[0]}},
                     indent=1))
    if write:
        tmp = OUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        tmp.replace(OUT_PATH)
        print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    return {OUT_PATH: payload}


def _summary(p: dict) -> str:
    a1 = p["arms"]["A1_xhem_plus"]["ladder"]["D4"]
    a2 = p["arms"]["A2_fwdhem_plus"]["ladder"]["D4"]
    e1 = p["arms"]["A1_xhem_plus"]["ladder"]["D0_original_seed"]
    e2 = p["arms"]["A2_fwdhem_plus"]["ladder"]["D0_original_seed"]
    return (
        "RE-GATE 1 on the SERVED construction (D4, integers as served), "
        f"{p['n_forward_pairs']['A1']} / {p['n_forward_pairs']['A2']} pairs. "
        f"A1 served xHEM+ vs actual wOBA: rho {a1['v1']['rho_primary']} vs "
        f"{a1['v1']['rho_baseline']}, v1 gap {a1['v1']['gap_ci']}, v2 gap "
        f"{a1['v2']['gap_ci']}; eval-normalized D0 reproduction v1 gap "
        f"{e1['v1']['gap_ci']}. "
        f"A2 served fwdHEM+ vs xwOBA alone: rho {a2['v1']['rho_primary']} vs "
        f"{a2['v1']['rho_baseline']}, v1 gap {a2['v1']['gap_ci']}, v2 gap "
        f"{a2['v2']['gap_ci']}; eval-normalized D0 reproduction v1 gap "
        f"{e2['v1']['gap_ci']}. "
        f"Verdicts: xhem_plus {p['arms']['A1_xhem_plus']['verdict']}, "
        f"fwdhem_plus {p['arms']['A2_fwdhem_plus']['verdict']}.")


if __name__ == "__main__":
    run(write="--no-write" not in sys.argv[1:])
