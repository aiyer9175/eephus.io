# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The HEM+ family re-baseline on the 2016 to 2026 pair set, and HEM+ against
xwOBA: the ONE run of docs/HEM_XWOBA_REGATE_GATE.md (pre-registered 2026-10-15,
committed alone before any number here was computed).

Three arms, each a paired difference of Spearman rank correlations with
next-year actual wOBA, at rung D4 (the served integer column):

  A1 (xhem_plus)   delta = rho(xHEM+_served(Y),  wOBA(Y+1)) - rho(wOBA(Y),  wOBA(Y+1))
  A2 (fwdhem_plus) delta = rho(fwdHEM+_served(Y), wOBA(Y+1)) - rho(xwOBA(Y), wOBA(Y+1))
  A3 (hem_plus)    delta = rho(HEM+_served(Y),   wOBA(Y+1)) - rho(xwOBA(Y), wOBA(Y+1))

A1 and A2 are the 2026-09-18 arms (tools/xhem_served_regate_lab.py) re-read on
the pair set extended by the 2025 to 2026 block; A3 is new and carries verdict
weight for the first time. HEM+_served is the column exactly as served:
hem_plus.score_pool's path on the season's StatsAPI statlines, int(round(
hem_plus_raw)), which is what tools/xhem_plus_lab.load_hem_core walks. Both
bootstrap conventions on every cell, an in-run MDE95 on every gap, Holm k = 3
within each convention, and a frozen-subset reproduction of the 2026-09-18 D4
cells as a stop rule. The served constructions and the bootstrap draw are
IMPORTED from the 2026-09-18 lab, not re-implemented, so the reproduction is
the same arithmetic on the same rows.

The 2025 to 2026 block is admitted only by the owner's logged season-complete
override (--season-complete-asof 2026:2026-10-01, owner 2026-10-14 EW3-6);
the read is an OWNER-WAIVED EARLY READ of the date R1-12 registered.

  -> data/hem_xwoba_regate_eval.json

Run:  python tools/hem_xwoba_regate_lab.py --season-complete-asof 2026:2026-10-01
      python tools/hem_xwoba_regate_lab.py --dry-run-fixtures   (reporting path on
                                            None-bearing fixtures; writes nothing)
      --no-write keeps the artifact off disk; --out <path> redirects it.
Exit codes: 0 ran, 3 the frozen-subset reproduction failed (STOP), 4 refused
(the 2025 block is under the floor, written under --out only).
"""
from __future__ import annotations

import hashlib
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

import plus_lab_harness as plh  # noqa: E402
import xhem_plus_lab as xhl  # noqa: E402
import xhem_served_regate_lab as xsr  # noqa: E402
from efv_power_lab import holm_family  # noqa: E402

DATA = ROOT / "data"
OUT_PATH = DATA / "hem_xwoba_regate_eval.json"
PRIOR_PATH = DATA / "xhem_served_regate_eval.json"
GATE_DOC = "docs/HEM_XWOBA_REGATE_GATE.md"
PRIOR_GATE_DOC = "docs/HEM_RIV_REGATE_GATE.md"

# ---- frozen by the gate document; changing any of these is a new gate ------ #
SEASONS = list(xsr.SEASONS)          # predictor seasons 2016-2025 ex-2020
NEW_BLOCK = 2025                     # the one predictor season R1-12 could not admit
NEW_BLOCK_FLOOR = 200                # fewer rows than this: REFUSED (gate section 10)
PRIOR_N = 1871                       # the 2026-09-18 pair set, a reproduction target
BOOT = 2000
SEED_R3 = 20261015
SEED_R1 = xsr.SEED_R1                # 20260918, the frozen-subset reproduction draw
REGISTERED_DATE = "2026-11-16 or later (docs/HEM_RIV_REGATE_GATE.md R1-12)"
WAIVER = ("owner 2026-10-14 (EW3-5): registered look days and dates are waived; "
          "EW3-6: the 2026 season is treated as complete as of 2026-10-01 through the "
          "logged PLUS_LAB_SEASON_COMPLETE_ASOF override; this read is an OWNER-WAIVED "
          "EARLY READ, never the registered date's read")

ARMS = ("A1_xhem_plus", "A2_fwdhem_plus", "A3_hem_plus")
ROW_OF = {"A1_xhem_plus": "xhem_plus", "A2_fwdhem_plus": "fwdhem_plus",
          "A3_hem_plus": "hem_plus"}

_r4 = xsr._r4
_sd = xsr._sd
_ties = xsr._ties
cell = xsr.cell


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #
def savant_file_receipt(year: int) -> dict:
    """sha256, row count, max PA and mtime of the Savant expected-statistics
    file the loader reads for `year` (gate section 2: the 2026 file is the
    current-season file, so the capture is written down)."""
    import mlb_player_export as mpe  # noqa: PLC0415
    p = mpe.CACHE_DIR / f"expected_batter_{year}.csv"
    if not p.exists():
        return {"file": p.name, "exists": False}
    b = p.read_bytes()
    rows = xhl.load_savant_woba(year)
    pas = [v[2] for v in rows.values()]
    return {"file": p.name, "exists": True, "sha256": hashlib.sha256(b).hexdigest(),
            "bytes": len(b), "rows_loaded": len(rows),
            "max_pa": max(pas) if pas else None,
            "n_600_plus_pa": sum(1 for v in pas if v >= 600),
            "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime))}


def load_inputs() -> dict:
    data = {}
    for y in SEASONS + [max(SEASONS) + 1]:
        d = xhl.load_savant_woba(y)
        if d:
            data[y] = d
    hem_by_year = {y: xhl.load_hem_core(y) for y in SEASONS if y in data}
    receipts = {str(y): savant_file_receipt(y) for y in SEASONS + [max(SEASONS) + 1]}
    prior = json.loads(PRIOR_PATH.read_text(encoding="utf-8")) if PRIOR_PATH.exists() else None
    return {"data": data, "hem_by_year": hem_by_year, "savant_files": receipts,
            "prior": prior}


# --------------------------------------------------------------------------- #
# fixtures for the dry run: None-bearing, small, deterministic; never written
# --------------------------------------------------------------------------- #
def fixtures(seed: int = 7) -> dict:
    rng = random.Random(seed)
    data: dict = {}
    hem: dict = {}
    players = list(range(1000, 1040))
    for y in SEASONS + [max(SEASONS) + 1]:
        row = {}
        for m in players:
            if rng.random() < 0.15:
                continue                                   # no Savant row that year
            w = 0.30 + rng.gauss(0, 0.035)
            x = w + rng.gauss(0, 0.02)
            pa = rng.choice([80.0, 150.0, 250.0, 420.0, 610.0])
            row[m] = (w, x, pa)
        data[y] = row
        if y in SEASONS:
            hem[y] = {m: 100.0 + rng.gauss(0, 12) for m in row if rng.random() < 0.85}
            # a None hem core must be dropped, not scored
            hem[y][players[0]] = None
    prior = {"n_forward_pairs": {"A1": None, "A2": None},
             "arms": {"A1_xhem_plus": {"ladder": {"D4": {"v1": {"rho_primary": None,
                                                                "rho_baseline": None,
                                                                "gap_ci": None},
                                                         "v2": {"rho_primary": None,
                                                                "rho_baseline": None,
                                                                "gap_ci": None}}}},
                      "A2_fwdhem_plus": {"ladder": {"D4": {"v1": {"rho_primary": None,
                                                                  "rho_baseline": None,
                                                                  "gap_ci": None},
                                                           "v2": {"rho_primary": None,
                                                                  "rho_baseline": None,
                                                                  "gap_ci": None}}}}}}
    receipts = {str(y): {"file": f"expected_batter_{y}.csv", "exists": False}
                for y in SEASONS + [max(SEASONS) + 1]}
    return {"data": data, "hem_by_year": hem, "savant_files": receipts, "prior": prior}


# --------------------------------------------------------------------------- #
# the pre-registered decision rule (gate section 6 = R1-6 verbatim)
# --------------------------------------------------------------------------- #
def decide(d4: dict, holm_v1: bool, holm_v2: bool) -> dict:
    """The R1-6 table row for one arm from its D4 cells and its Holm flags.
    `table_row` names the row; `verdict` is the registry verdict the row maps
    to for a row that starts validated (the mover applies the per-row text)."""
    v1, v2 = d4["v1"], d4["v2"]
    p1 = bool(v1.get("lo95_gt_0")) and bool(holm_v1)
    p2 = bool(v2.get("lo95_gt_0")) and bool(holm_v2)
    if v1.get("hi95_lt_0") or v2.get("hi95_lt_0"):
        return {"table_row": "refuted", "verdict": "deprecated",
                "reason": ("REFUTED: the D4 gap hi95 is below zero under at least one "
                           "convention, so the claim is contradicted, not merely "
                           "unestablished."), "passes_v1_after_holm": p1,
                "passes_v2_after_holm": p2}
    if p1 and p2:
        return {"table_row": "both", "verdict": "validated",
                "reason": ("The SERVED construction clears its baseline under BOTH "
                           "conventions after Holm (k=3)."),
                "passes_v1_after_holm": p1, "passes_v2_after_holm": p2}
    if p1:
        return {"table_row": "v1_only", "verdict": "provisional",
                "reason": ("DEMOTED: the served construction clears only the legacy v1 "
                           "convention; the one-cycle v1 grandfather clause is spent."),
                "passes_v1_after_holm": p1, "passes_v2_after_holm": p2}
    if p2:
        return {"table_row": "v2_only", "verdict": "provisional",
                "reason": ("DEMOTED: the served construction clears only v2, which was "
                           "not the pre-declared convention; an undeclared convention "
                           "cannot promote a row."),
                "passes_v1_after_holm": p1, "passes_v2_after_holm": p2}
    return {"table_row": "straddle", "verdict": "provisional",
            "reason": ("DEMOTED: not separable from its baseline on the SERVED "
                       "construction at this n under either convention."),
            "passes_v1_after_holm": p1, "passes_v2_after_holm": p2}


def _holm_reject(holm: dict, key: str) -> bool:
    for row in xsr._holm_rows(holm):
        if row.get("key") == key:
            return bool(row.get("reject_holm"))
    return False


# --------------------------------------------------------------------------- #
# scoring: pure given the inputs, so the dry run and the run share one path
# --------------------------------------------------------------------------- #
def _subset(arr, idx):
    return [arr[i] for i in idx]


def _rung_cells(vals, baseline, base_name, tgt_raw, tgt_z, players, pred, seed,
                boot) -> dict:
    v1d = xsr.iid_gaps_full(vals, {base_name: baseline}, tgt_raw, boot, seed)[base_name]
    v2d = xsr.cluster_gaps_full(vals, {base_name: baseline}, tgt_z, players, pred,
                                boot, seed)[base_name]
    return {"seed": seed,
            "v1": cell(vals, baseline, tgt_raw, v1d),
            "v2": cell(vals, baseline, tgt_z, v2d),
            "_v1_draws": v1d, "_v2_draws": v2d,
            "n_distinct_values": len(set(vals)),
            "n_tied_rows": _ties(vals)}


def _clean(lad: dict) -> dict:
    return {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
            for k, v in lad.items()}


def _same4(a, b) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same4(a[k], b[k]) for k in a)
    try:
        return round(float(a), 4) == round(float(b), 4)
    except (TypeError, ValueError):
        return False


def score(inputs: dict, boot: int = BOOT, seed: int = SEED_R3,
          seed_r1: int = SEED_R1, today: date | None = None,
          new_block_floor: int = NEW_BLOCK_FLOOR) -> dict:
    """The whole battery on `inputs`; pure given them. `new_block_floor` is
    lowered ONLY by the dry run on fixtures, so the refusal path and the full
    reporting path can both be exercised before the one run."""
    t0 = time.time()
    data, hem_by_year, prior = inputs["data"], inputs["hem_by_year"], inputs["prior"]
    ps = xsr.build_pair_set(data)
    n = ps["n"]
    mids, pys, oys, tgt = ps["mids"], ps["pys"], ps["oys"], ps["tgt"]
    tgt_v2 = plh.zscore_within(oys, tgt) if n else []
    by_season_rows: dict = {}
    for i in range(n):
        by_season_rows.setdefault(pys[i], []).append(i)
    n_new = len(by_season_rows.get(NEW_BLOCK, []))
    print(f"  extended pair set: {n} pairs ({ps['dropped_partial']} dropped partial-outcome; "
          f"{NEW_BLOCK} block {n_new})")

    pred_seasons = sorted(set(pys))
    xpool = {y: xsr.served_xhem_pool(data[y]) for y in pred_seasons}
    fpool = {y: xsr.served_fwdhem_pool(data[y], hem_by_year.get(y) or {})
             for y in pred_seasons}
    hem_clean = {y: {m: v for m, v in (hem_by_year.get(y) or {}).items() if v is not None}
                 for y in pred_seasons}

    coverage = {
        "note": ("Coverage is reported separately and is NEVER used to explain a gap. "
                 "The gate speaks only about the PA >= 200 subset while the board stamps "
                 "every tracked hitter at PA >= 100, and that sentence travels with the "
                 "verdict."),
        "pair_set_n_by_predictor_season": {str(y): len(by_season_rows[y])
                                           for y in pred_seasons},
        "new_block_predictor_season": NEW_BLOCK,
        "new_block_n": n_new,
        "new_block_floor": NEW_BLOCK_FLOOR,
        "served_normalizer_pool_by_season": {
            str(y): {"xhem_pool_pa_ge_100": xpool[y][1],
                     "fwdhem_pool_pa_ge_100_with_hem_core":
                         (fpool[y]["n_pool"] if fpool.get(y) else 0),
                     "hem_core_pool": len(hem_clean[y])}
            for y in pred_seasons},
        "board_stamped_never_eligible_by_season": {
            str(y): xpool[y][1] - len(by_season_rows.get(y, [])) for y in pred_seasons},
        "n_pairs_dropped_partial_outcome_season": ps["dropped_partial"],
    }
    meta = {
        "generated_at": (today or date.today()).isoformat(),
        "experiment": "RE-BASELINE of RE-GATE 1 (arms A1, A2) on the extended pair set, plus arm A3",
        "gate_document": GATE_DOC,
        "prior_gate_document": PRIOR_GATE_DOC,
        "pre_registered": "2026-10-15, frozen and committed alone before any number in this artifact was computed",
        "models": ["xhem_plus", "fwdhem_plus", "hem_plus"],
        "seasons": SEASONS,
        "seed": seed, "boot": boot,
        "owner_waived_early_read": {
            "registered_date": REGISTERED_DATE,
            "run_date": (today or date.today()).isoformat(),
            "authority": WAIVER,
            "season_complete_override": plh.season_complete_override_meta(),
        },
        "harness": plh.convention_meta(xsr.TARGET_V1, xsr.TARGET_V2),
        "savant_files": inputs.get("savant_files"),
        "coverage": coverage,
    }

    if n_new < new_block_floor:
        meta["refused"] = {
            "reason": (f"the {NEW_BLOCK} block carries {n_new} pairs, under the registered "
                       f"floor of {new_block_floor}: the 2026 capture is not a complete "
                       "season; nothing is scored and no row moves (gate section 10)"),
        }
        meta["verdict"] = {"status": "REFUSED"}
        meta["runtime_seconds"] = round(time.time() - t0, 1)
        return meta

    # ---- the three arms' predictor columns -------------------------------- #
    base_a1 = ps["woba"]
    eval_anchor = {y: xsr.eval_pool_anchor(_subset(ps["xwoba"], idx),
                                           _subset(ps["pa_y"], idx), False)
                   for y, idx in by_season_rows.items()}
    a1 = {"D0": list(ps["xwoba"]),
          "D1": [xsr.served_xhem_unrounded(ps["xwoba"][i], eval_anchor[pys[i]])
                 for i in range(n)],
          "D2": [xsr.served_xhem_unrounded(ps["xwoba"][i], xpool[pys[i]][0])
                 for i in range(n)]}
    a1["D3"] = list(a1["D2"])
    a1["D4"] = [float(int(round(v))) for v in a1["D3"]]

    keep = [i for i in range(n)
            if hem_clean.get(pys[i], {}).get(mids[i]) is not None
            and fpool.get(pys[i]) is not None]
    dropped_no_hem = n - len(keep)
    n5 = len(keep)
    xw5 = _subset(ps["xwoba"], keep)
    hem5 = [hem_clean[pys[i]][mids[i]] for i in keep]
    tgt5 = _subset(tgt, keep)
    mids5, pys5, oys5 = _subset(mids, keep), _subset(pys, keep), _subset(oys, keep)
    woba5 = _subset(ps["woba"], keep)
    tgt5_v2 = plh.zscore_within(oys5, tgt5) if n5 else []
    print(f"  HEM-core subset: {n5} pairs (dropped {dropped_no_hem} with no HEM core)")

    zx5 = plh.zscore_within(pys5, xw5) if n5 else []
    zh5 = plh.zscore_within(pys5, hem5) if n5 else []
    a2 = {"D0": [xsr.W_XWOBA * a + xsr.W_HEM * b for a, b in zip(zx5, zh5)],
          "D1": [xsr.W_XWOBA * (xw5[i] - fpool[pys5[i]]["mu_x"]) / fpool[pys5[i]]["sd_x"]
                 + xsr.W_HEM * (hem5[i] - fpool[pys5[i]]["mu_h"]) / fpool[pys5[i]]["sd_h"]
                 for i in range(n5)],
          "D2": [xsr.served_fwdhem_unrounded(xw5[i], hem5[i], fpool[pys5[i]])
                 for i in range(n5)]}
    a2["D3"] = list(a2["D2"])
    a2["D4"] = [float(int(round(v))) for v in a2["D3"]]

    a3 = {"D3": list(hem5)}
    a3["D4"] = [float(int(round(v))) for v in a3["D3"]]

    def ladder(arm_vals, baseline, base_name, tgt_raw, tgt_z, players, pred):
        return {rung: _rung_cells(arm_vals[rung], baseline, base_name, tgt_raw, tgt_z,
                                  players, pred, seed, boot)
                for rung in sorted(arm_vals)}

    lad_a1 = ladder(a1, base_a1, "vs_actual_woba", tgt, tgt_v2, mids, pys)
    lad_a2 = ladder(a2, xw5, "vs_xwoba_alone", tgt5, tgt5_v2, mids5, pys5)
    lad_a3 = ladder(a3, xw5, "vs_xwoba_alone", tgt5, tgt5_v2, mids5, pys5)

    # ---- frozen-subset reproduction of the 2026-09-18 D4 cells (stop rule) -- #
    old = [i for i in range(n) if pys[i] < NEW_BLOCK]
    old5 = [j for j, i in enumerate(keep) if pys[i] < NEW_BLOCK]
    rep = {"note": ("the rows whose predictor season is 2024 or earlier, in the same "
                    "construction and row order as data/xhem_served_regate_eval.json, "
                    "re-drawn under SEED_R1; zero verdict weight; a mismatch STOPS the run"),
           "seed": seed_r1, "n_old_rows": {"A1": len(old), "A2": len(old5)},
           "prior_n": {"A1": (prior or {}).get("n_forward_pairs", {}).get("A1"),
                       "A2": (prior or {}).get("n_forward_pairs", {}).get("A2")}}
    ok = True
    for key, lad_vals, base, idx, t_raw, players, pred, oy in (
            ("A1_xhem_plus", a1["D4"], base_a1, old, tgt, mids, pys, oys),
            ("A2_fwdhem_plus", a2["D4"], xw5, old5, tgt5, mids5, pys5, oys5)):
        vals, bl = _subset(lad_vals, idx), _subset(base, idx)
        tr = _subset(t_raw, idx)
        tz = plh.zscore_within(_subset(oy, idx), tr) if idx else []
        c = _rung_cells(vals, bl, "prior", tr, tz, _subset(players, idx),
                        _subset(pred, idx), seed_r1, boot)
        pri = ((((prior or {}).get("arms") or {}).get(key) or {}).get("ladder") or {}).get("D4") or {}
        match = {}
        for conv in ("v1", "v2"):
            pc = pri.get(conv) or {}
            match[conv] = {
                "rho_primary": _same4(c[conv]["rho_primary"], pc.get("rho_primary")),
                "rho_baseline": _same4(c[conv]["rho_baseline"], pc.get("rho_baseline")),
                "gap_ci": _same4(c[conv]["gap_ci"], pc.get("gap_ci")),
            }
        n_ok = (len(idx) == rep["prior_n"]["A1" if key.startswith("A1") else "A2"] == PRIOR_N)
        arm_ok = n_ok and all(all(m.values()) for m in match.values())
        ok = ok and arm_ok
        rep[key] = {"recomputed": {"v1": c["v1"], "v2": c["v2"]},
                    "prior": {"v1": pri.get("v1"), "v2": pri.get("v2")},
                    "match_to_4dp": match, "n_matches_prior": n_ok, "reproduces": arm_ok}
    rep["reproduces_all"] = ok

    # ---- sensitivities, zero verdict weight -------------------------------- #
    s_xhem = [float(int(round(xsr.served_xhem_unrounded(xw5[i], xpool[pys5[i]][0]))))
              for i in range(n5)]
    a1s = {"note": ("labelled SENSITIVITY, zero verdict weight: the served xHEM+ integer "
                    "against the served HEM+ integer on the HEM-core subset (gate section 3)"),
           **{k: v for k, v in _rung_cells(s_xhem, a3["D4"], "vs_served_hem_plus", tgt5,
                                          tgt5_v2, mids5, pys5, seed, boot).items()
              if not k.startswith("_") and k != "seed"}}
    a3s = {"note": ("labelled SENSITIVITY, zero verdict weight: the served HEM+ integer "
                    "against raw actual wOBA(Y), the parent comparison the hem_plus gate "
                    "names, on the HEM-core subset (gate section 3)"),
           **{k: v for k, v in _rung_cells(a3["D4"], woba5, "vs_actual_woba", tgt5,
                                          tgt5_v2, mids5, pys5, seed, boot).items()
              if not k.startswith("_") and k != "seed"}}

    # ---- multiplicity: Holm k = 3 within each convention -------------------- #
    holm = {}
    for conv in ("v1", "v2"):
        cells = []
        for key, lad in (("A1_xhem_plus", lad_a1), ("A2_fwdhem_plus", lad_a2),
                         ("A3_hem_plus", lad_a3)):
            dr = lad["D4"]["_%s_draws" % conv]
            cells.append({"key": key, "delta": (sum(dr) / len(dr)) if dr else 0.0,
                          "sd": _sd(dr) if len(dr) > 1 else 0.0})
        holm[conv] = holm_family(cells, alpha=0.05)

    arms = {}
    for key, lad, est, base_txt, expect in (
            ("A1_xhem_plus", lad_a1,
             "rho(xHEM+_served(Y), wOBA(Y+1)) - rho(actual wOBA(Y), wOBA(Y+1))",
             "raw actual wOBA(Y), the X-H3 baseline, unchanged",
             "EXPECTED TO SURVIVE (gate section 8, item 1)"),
            ("A2_fwdhem_plus", lad_a2,
             "rho(fwdHEM+_served(Y), wOBA(Y+1)) - rho(Savant xwOBA(Y), wOBA(Y+1))",
             "raw Savant xwOBA(Y) alone, the X-H5 baseline, unchanged",
             "EXPECTED TO STAY PROVISIONAL (gate section 8, item 2)"),
            ("A3_hem_plus", lad_a3,
             "rho(HEM+_served(Y), wOBA(Y+1)) - rho(Savant xwOBA(Y), wOBA(Y+1))",
             "raw Savant xwOBA(Y) alone, the same rows as A2",
             "EXPECTED TO BE REFUTED (gate section 8, item 3)")):
        d = decide(lad["D4"], _holm_reject(holm["v1"], key), _holm_reject(holm["v2"], key))
        arms[key] = {"row": ROW_OF[key], "estimand": est, "baseline": base_txt,
                     "pre_registered_expectation": expect,
                     "ladder": _clean(lad), "verdict_rung": "D4",
                     "passes_v1_after_holm": d["passes_v1_after_holm"],
                     "passes_v2_after_holm": d["passes_v2_after_holm"],
                     "table_row": d["table_row"], "verdict": d["verdict"],
                     "verdict_reason": d["reason"]}
    arms["A3_hem_plus"]["served_construction"] = (
        "hem_plus.score_pool's path on the season's StatsAPI hitting statlines "
        "(hitter_export.load_season_hitting -> build_hitters): every bat with a wOBA "
        "denominator above zero enters; the anchor is Pool.mean_woba over bats at "
        "POOL_MIN_PA; hem_plus_raw = 100 + HEM_SPREAD_GAIN * (100 * shrunk wOBA / anchor "
        "- 100); the served integer is int(round(hem_plus_raw)). Re-scored per predictor "
        "season on the complete statlines (tools/xhem_plus_lab.load_hem_core) and read on "
        "the pair-set rows.")

    meta.update({
        "n_forward_pairs": {"A1": n, "A2": n5, "A3": n5},
        "n_pairs_dropped_no_hem_core": dropped_no_hem,
        "frozen_subset_reproduction": rep,
        "arms": arms,
        "sensitivity_A1s_served_xhem_vs_served_hem": a1s,
        "sensitivity_A3s_served_hem_vs_actual_woba": a3s,
        "multiplicity": {
            "family": ("the three primary arms A1, A2 and A3, Holm k = 3, applied "
                       "SEPARATELY within each convention (gate section 7)"),
            "total_primary_tests_in_the_gate_document": 3,
            "outside_the_family_by_declaration": ["D0", "D1", "D2", "D3",
                                                  "frozen_subset_reproduction", "A1s",
                                                  "A3s", "every coverage figure"],
            "v1": holm["v1"], "v2": holm["v2"],
        },
        "standing_consequence": (
            "The headline number on a served column is the SERVED construction number; "
            "the eval-normalized figure may appear only as a labelled reproduction "
            "(docs/HEM_RIV_REGATE_GATE.md R1-6, inherited)."),
        "runtime_seconds": round(time.time() - t0, 1),
    })
    meta["verdict"] = {
        "status": "RAN" if ok else "STOPPED_REPRODUCTION_FAILED",
        "xhem_plus": arms["A1_xhem_plus"]["verdict"] if ok else None,
        "fwdhem_plus": arms["A2_fwdhem_plus"]["verdict"] if ok else None,
        "hem_plus": arms["A3_hem_plus"]["verdict"] if ok else None,
        "summary": (summary(meta) if ok else
                    "frozen-subset reproduction FAILED; no verdict. " + summary(meta)),
    }
    return meta


def summary(p: dict) -> str:
    parts = [f"RE-BASELINE on the extended pair set (D4, integers as served), "
             f"{p['n_forward_pairs']['A1']} / {p['n_forward_pairs']['A2']} pairs "
             f"({p['coverage']['new_block_predictor_season']} block "
             f"{p['coverage']['new_block_n']}); owner-waived early read."]
    for key, label in (("A1_xhem_plus", "A1 served xHEM+ vs actual wOBA"),
                       ("A2_fwdhem_plus", "A2 served fwdHEM+ vs xwOBA alone"),
                       ("A3_hem_plus", "A3 served HEM+ vs xwOBA alone")):
        d4 = p["arms"][key]["ladder"]["D4"]
        parts.append(f"{label}: rho {d4['v1']['rho_primary']} vs {d4['v1']['rho_baseline']}, "
                     f"v1 gap {d4['v1']['gap_ci']}, v2 gap {d4['v2']['gap_ci']}; "
                     f"{p['arms'][key]['table_row']} -> {p['arms'][key]['verdict']}.")
    return " ".join(parts)


def run(write: bool = True, out: Path | None = None, dry: bool = False) -> int:
    inputs = fixtures() if dry else load_inputs()
    if dry:
        # both paths before the one run: the refusal receipt at the registered
        # floor, then the whole reporting path with the floor lowered
        refused = score(inputs, boot=50)
        print(json.dumps({"dry_refusal_path": refused["verdict"]["status"],
                          "reason": (refused.get("refused") or {}).get("reason")}, indent=1))
        payload = score(inputs, boot=50, new_block_floor=0)
    else:
        payload = score(inputs, boot=BOOT)
    status = payload["verdict"]["status"]
    brief = {"status": status,
             "n": payload.get("n_forward_pairs"),
             "new_block_n": payload["coverage"]["new_block_n"]}
    if status == "RAN":
        brief["D4"] = {k: {"v1": payload["arms"][k]["ladder"]["D4"]["v1"]["gap_ci"],
                           "v2": payload["arms"][k]["ladder"]["D4"]["v2"]["gap_ci"],
                           "verdict": payload["arms"][k]["verdict"]} for k in ARMS}
        brief["reproduces"] = payload["frozen_subset_reproduction"]["reproduces_all"]
    print(json.dumps(brief, indent=1))
    if dry:
        if out:
            out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
            print(f"dry run on fixtures: fixture payload written to {out} (never data/)")
        else:
            print("dry run on fixtures: nothing written")
        return 0
    if status == "REFUSED":
        if out:
            out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
            print(f"REFUSED; coverage written to {out}")
        return 4
    if status != "RAN":
        print(json.dumps(payload["frozen_subset_reproduction"], indent=1, default=str))
        if out:
            out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print("STOP: the frozen-subset reproduction failed; nothing written to data/")
        return 3
    if write:
        target = out or OUT_PATH
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        tmp.replace(target)
        print(f"wrote {target}")
    return 0


def main(argv: list[str]) -> int:
    out = None
    dry = "--dry-run-fixtures" in argv
    if "--season-complete-asof" in argv:
        plh.set_season_complete_asof(argv[argv.index("--season-complete-asof") + 1])
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])
    return run(write="--no-write" not in argv, out=out, dry=dry)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
