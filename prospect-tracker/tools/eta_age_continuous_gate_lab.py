# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""C3-ETA gate lab (E1.2 arm b, run 2026-08-03) -- the OWED gate for
eta.AGE_ADJ_CONTINUOUS (implemented 2026-07-30, DEFAULT OFF, registered as
"GATE OWED, not passed" in docs/efv-2026-07-30/EFV_LANE_GATES.md).

THE ARBITER IS eta_backtest.py's PROTOCOL, not a Spearman lab. ETA is a
forecast with censored outcomes, so this lab runs the censoring-aware harness
that file already implements:

  cohort      eta_backtest.build_cohort() -- one row per (player, vintage
              2018-2023) with an FV snapshot and no prior debut; inputs
              reconstructed as of the vintage (level/stats from season Y-1,
              decimal age at the snapshot date, static norm tables).
  scored      debuted rows only, error in calendar years (MAE / bias /
              within-1y / exact) -- the same selection the shipped ship
              decision was made on, shared identically by both arms.
  censored    censored_active rows carry the unconditional signal via the
              OVERDUE count (predicted year already past LAST_FULL_SEASON);
              washed-out rows are permanent risk-set members and are reported
              as a due-date count, never scored in years.
  bases       TWO arms, both forward-chained-clean:
                live  = eta.BASE_YEARS as shipped (the champion table)
                kmfc  = the censoring-aware Kaplan-Meier bases refitted
                        FORWARD-CHAINED per vintage on vintages < Y
                        (eta_backtest._km_table), the protocol the v39 ship
                        was decided on.
              Both arms in a pair use the SAME table; the ONLY difference is
              the AGE_ADJ_CONTINUOUS flag, so nothing else can move.

  control     zero-information: the decimal age column PERMUTED across cohort
              rows (row link broken), 20 draws, both flag settings rescored on
              each draw. A staircase-to-ramp delta that a meaningless age
              column reproduces is not age information.
  bootstrap   paired, B=2000 over the debuted rows, delta = treatment minus
              champion on the SAME resampled rows (MAE and within-1y).

Champion = the shipped staircase (flag False). Treatment = the interpolated
ramp (flag True). The flag is set on the imported module inside this process
only; no source file is edited and no served artifact is written.

Artifact: data/eta_age_continuous_eval.json
Run: python tools/eta_age_continuous_gate_lab.py
"""
from __future__ import annotations

import json
import pickle
import random
import statistics
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os  # noqa: E402
os.chdir(ROOT)

import eta as ETA                       # noqa: E402
import eta_backtest as ETB              # noqa: E402

OUT_PATH = ROOT / "data" / "eta_age_continuous_eval.json"
# Cohort rebuild is the expensive step (StatsAPI ladder reads from the local
# cache). Memoized under the gitignored .cache tree so a rerun is instant.
CACHE = Path(os.environ.get("ETA_COHORT_CACHE",
                            ROOT / ".cache" / "eta_cohort_c3gate.pkl"))
REGISTRATION = "docs/efv-2026-07-30/EFV_LANE_GATES.md, arm C3-ETA (gate OWED)"

CTRL_DRAWS = 20
BOOT_B = 2000


def _cohort():
    if CACHE.exists():
        with CACHE.open("rb") as fh:
            return pickle.load(fh)
    t = time.time()
    rows, acct = ETB.build_cohort()
    print(f"build_cohort: {len(rows)} rows in {time.time() - t:.1f}s")
    with CACHE.open("wb") as fh:
        pickle.dump((rows, acct), fh)
    return rows, acct


def _rescore(rows, tables, today_year, flag):
    prev = ETA.AGE_ADJ_CONTINUOUS
    ETA.AGE_ADJ_CONTINUOUS = flag
    try:
        return ETB._heuristic_rescore(rows, tables, today_year)
    finally:
        ETA.AGE_ADJ_CONTINUOUS = prev


def _pairs(rows, preds, idx):
    return [(preds[i], rows[i]["actual"]) for i in idx]


def _overdue(rows, preds):
    return sum(1 for i, r in enumerate(rows)
               if r["outcome"] == "censored_active"
               and preds.get(i, r["pred"]) <= ETB.LAST_FULL_SEASON)


def _washed_due(rows, preds):
    return sum(1 for i, r in enumerate(rows)
               if r["outcome"] == "washed_out"
               and preds.get(i, r["pred"]) <= ETB.LAST_FULL_SEASON)


def _boot(rows, idx, pb, pt, b=BOOT_B, seed=13):
    """Paired bootstrap over debuted rows: treatment minus champion."""
    rng = random.Random(seed)
    eb = [pb[i] - rows[i]["actual"] for i in idx]
    et = [pt[i] - rows[i]["actual"] for i in idx]
    n = len(idx)
    d_mae, d_w1 = [], []
    for _ in range(b):
        s = [rng.randrange(n) for _ in range(n)]
        mb = sum(abs(eb[j]) for j in s) / n
        mt = sum(abs(et[j]) for j in s) / n
        wb = sum(1 for j in s if abs(eb[j]) <= 1) / n
        wt = sum(1 for j in s if abs(et[j]) <= 1) / n
        d_mae.append(mt - mb)
        d_w1.append(wt - wb)

    def ci(v):
        v = sorted(v)
        return [round(v[int(0.025 * len(v))], 5), round(v[int(0.975 * len(v)) - 1], 5)]

    return {
        "n": n, "B": b,
        "d_mae": {"point": round(sum(abs(e) for e in et) / n - sum(abs(e) for e in eb) / n, 5),
                  "mean": round(statistics.mean(d_mae), 5), "ci95": ci(d_mae),
                  "p_improves": round(sum(1 for d in d_mae if d < 0) / len(d_mae), 3)},
        "d_within_1y": {"point": round(sum(1 for e in et if abs(e) <= 1) / n
                                       - sum(1 for e in eb if abs(e) <= 1) / n, 5),
                        "mean": round(statistics.mean(d_w1), 5), "ci95": ci(d_w1),
                        "p_improves": round(sum(1 for d in d_w1 if d > 0) / len(d_w1), 3)},
    }


def _arm(rows, tables, today_year, label):
    pb = _rescore(rows, tables, today_year, False)
    pt = _rescore(rows, tables, today_year, True)
    idx = [i for i, r in enumerate(rows)
           if r["outcome"] == "debuted" and i in pb and i in pt]
    champ = ETB._score(_pairs(rows, pb, idx))
    treat = ETB._score(_pairs(rows, pt, idx))
    changed = [i for i in pb if i in pt and pb[i] != pt[i]]
    earlier = sum(1 for i in changed if pt[i] < pb[i])
    by_level = {}
    for lv in sorted({rows[i]["level"] for i in idx if rows[i]["level"]}):
        li = [i for i in idx if rows[i]["level"] == lv]
        if len(li) < 25:
            continue
        by_level[lv] = {"n": len(li),
                        "champion_mae": ETB._score(_pairs(rows, pb, li))["mae"],
                        "continuous_mae": ETB._score(_pairs(rows, pt, li))["mae"]}
    return {
        "label": label,
        "scored_rows": len(idx),
        "champion_staircase": champ,
        "continuous_ramp": treat,
        "delta": {"mae": round(treat["mae"] - champ["mae"], 4),
                  "within_1y": round(treat["within_1y"] - champ["within_1y"], 4),
                  "bias": round(treat["bias"] - champ["bias"], 4),
                  "exact": round(treat["exact"] - champ["exact"], 4)},
        "footprint": {"rows_with_a_prediction": len(pb),
                      "predictions_changed": len(changed),
                      "changed_earlier": earlier,
                      "changed_later": len(changed) - earlier},
        "censoring": {"overdue_champion": _overdue(rows, pb),
                      "overdue_continuous": _overdue(rows, pt),
                      "washed_out_already_due_champion": _washed_due(rows, pb),
                      "washed_out_already_due_continuous": _washed_due(rows, pt)},
        "by_level_mae": by_level,
        "paired_bootstrap": _boot(rows, idx, pb, pt),
    }


def _control(rows, tables, today_year, draws=CTRL_DRAWS):
    """Zero-information control: permute the decimal age across cohort rows."""
    ages = [r["age"] for r in rows]
    out = []
    for s in range(draws):
        rng = random.Random(5000 + s)
        perm = ages[:]
        rng.shuffle(perm)
        for r, a in zip(rows, perm):
            r["age"] = a
        pb = _rescore(rows, tables, today_year, False)
        pt = _rescore(rows, tables, today_year, True)
        idx = [i for i, r in enumerate(rows)
               if r["outcome"] == "debuted" and i in pb and i in pt]
        cb = ETB._score(_pairs(rows, pb, idx))
        ct = ETB._score(_pairs(rows, pt, idx))
        out.append({"d_mae": round(ct["mae"] - cb["mae"], 4),
                    "d_within_1y": round(ct["within_1y"] - cb["within_1y"], 4)})
    for r, a in zip(rows, ages):      # restore
        r["age"] = a
    return out


def main():
    rows, acct = _cohort()
    today_year = date.today().year

    live_tables = {vy: dict(ETA.BASE_YEARS) for vy in ETB.VINTAGE_YEARS}
    km_by_vintage = {}
    for vy in ETB.VINTAGE_YEARS:
        km = ETB._km_table([r for r in rows if r["vintage"] < vy])
        if km:
            km_by_vintage[vy] = km

    arms = {"live_base_years": _arm(rows, live_tables, today_year, "live BASE_YEARS (shipped v39)"),
            "km_forward_chained": _arm(rows, km_by_vintage, today_year,
                                       "KM bases refit forward-chained per vintage")}
    ctrl = _control(rows, live_tables, today_year)
    real = arms["live_base_years"]["delta"]
    ctrl_mae = [c["d_mae"] for c in ctrl]
    out = {
        "generated_at": date.today().isoformat(),
        "experiment": "C3-ETA: eta.AGE_ADJ_CONTINUOUS (staircase -> knot interpolation)",
        "registration": REGISTRATION,
        "regen_cmd": "python tools/eta_age_continuous_gate_lab.py",
        "protocol": ("eta_backtest.py censoring-aware harness: vintages 2018-2023, MAE "
                     "scored on debuted rows only (shared selection), overdue + washed-out "
                     "due counts carry the censored signal; both arms rescored through "
                     "estimate_eta with identical base tables, the flag the only difference"),
        "accounting": acct,
        "arms": arms,
        "zero_information_control": {
            "design": "decimal age permuted across cohort rows, 20 draws, live bases",
            "draws": ctrl,
            "d_mae_mean": round(statistics.mean(ctrl_mae), 4),
            "d_mae_sd": round(statistics.pstdev(ctrl_mae), 4),
            "d_mae_min": round(min(ctrl_mae), 4), "d_mae_max": round(max(ctrl_mae), 4),
            "real_d_mae": real["mae"],
            "real_better_than_all_controls": all(real["mae"] < c for c in ctrl_mae),
        },
        "ship_criterion": ("the criterion the v39 ETA ship was decided on: forward-chained "
                           "debuted MAE and within-1y must BOTH beat the incumbent on "
                           "identical rows, with the overdue shift disclosed; a delta whose "
                           "paired-bootstrap CI95 covers 0 is unresolved, not a win"),
    }
    OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k, a in arms.items():
        print(f"[{k}] n={a['scored_rows']} mae {a['champion_staircase']['mae']} -> "
              f"{a['continuous_ramp']['mae']} (d={a['delta']['mae']}) "
              f"w1y {a['champion_staircase']['within_1y']} -> {a['continuous_ramp']['within_1y']} "
              f"(d={a['delta']['within_1y']}) changed={a['footprint']['predictions_changed']} "
              f"overdue {a['censoring']['overdue_champion']} -> {a['censoring']['overdue_continuous']}")
    print("control d_mae mean", out["zero_information_control"]["d_mae_mean"],
          "range", out["zero_information_control"]["d_mae_min"],
          out["zero_information_control"]["d_mae_max"])
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
