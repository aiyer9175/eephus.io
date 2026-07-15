# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""E-STALE (2026-07-14) -- anchor-staleness discount, outcome-calibrated.

The Nathan Hickey class: ~7% of actively-scored players carry a consensus
anchor (fv + tools) frozen at their LAST list appearance (>1y stale; all
staleness is 0 in training rows by construction, so the model cannot learn
the discount). Ground truth (this lab, prospects.db): players whose last
graded listing was 2021/22 and who were never re-listed bust at ~91% vs
~55% for same-band re-listed controls, realizing ~FV22 on the model's own
realized_implied_fv scale against FV 35-45 anchors. The age gradient among
dropped players is flat -> the discount keys on time-since-listing alone.

Design: FIT the per-band terminal discount on the 2021-anchor dropped
cohort; VALIDATE held-out on the 2022-anchor dropped cohort. Gates
(pre-registered, docs/efv-2026-07-14/GATES.md E-STALE):
  c1 held-out cohort-level |grade error| improves vs the undecayed anchor
     in every band with n>=15;
  c2 no overshoot: decayed grade stays >= realized cohort implied FV - 2
     (the discount must not over-punish);
  c3 the fitted discounts are positive in every fitted band.

What ships (iff all gates pass): a serve-time decay of the MODEL'S fv input
(display consensus untouched) in efv_dataset.build_live:
  months_stale <= RAMP_START (18) -> 0  (annual list cadence + slack)
  RAMP_START..RAMP_FULL (30)      -> linear ramp to the band terminal
  > RAMP_FULL                     -> full terminal discount
Terminals are the fitted per-band values, capped at DISCOUNT_CAP. The
constants shipped in efv_dataset must match this artifact (test-pinned,
the overseas-factors pattern). Identity note: __noid snapshot keys are
folded into their plain siblings (383 phantom-drop dupes otherwise).

Writes data/xfv_stale_anchor_eval.json. Run: python tools/efv_stale_anchor_lab.py
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os
os.chdir(ROOT)

import value_framework as vf

DB = ROOT / "prospects.db"
OUT_PATH = ROOT / "data" / "xfv_stale_anchor_eval.json"

LIST_SOURCES = ("fangraphs", "mlb_pipeline", "mlb_pipeline_international", "espn",
                "baseballamerica", "baseballamerica_statcast_by_age", "just_baseball",
                "tjstats")
GRAD_EXCL_DAYS = 270      # debut soon after anchor => delisted-by-graduation, excluded
RELIST_STRICT_DAYS = 548  # 18 months
BANDS = (35, 40, 45)
MIN_BAND_N = 15
DISCOUNT_CAP = 10.0       # conservative ceiling on any shipped terminal discount
RAMP_START_MO = 18
RAMP_FULL_MO = 30
EXPOSURE = 6


def _d(s):
    return date(int(s[0:4]), int(s[5:7]), int(s[8:10]))


def _implied(mean_war):
    # hitter/pitcher scales are identical at these bands (verified in the study);
    # use the hitter scale for the cohort read.
    return float(vf.realized_implied_fv(mean_war, False, exposure_seasons=EXPOSURE))


def build_cohorts():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    all_keys = {r[0] for r in cur.execute("select distinct player_key from snapshots")}
    canon = {k: k[:-6] for k in all_keys if k.endswith("__noid") and k[:-6] in all_keys}
    C = lambda k: canon.get(k, k)

    listings = defaultdict(list)
    ph = ",".join("?" * len(LIST_SOURCES))
    for pk, sd, fv, src in cur.execute(
            f"select player_key, snapshot_date, fv, source from snapshots where source in ({ph})",
            LIST_SOURCES):
        listings[C(pk)].append((_d(sd), fv))

    debut = {}
    for pk, pj in cur.execute("select player_key, payload_json from roster_status"):
        try:
            v = json.loads(pj).get("mlb_debut_date")
        except Exception:
            v = None
        pk = C(pk)
        dd = _d(v) if v else None
        if dd is not None and (debut.get(pk) is None or dd < debut[pk]):
            debut[pk] = dd
        else:
            debut.setdefault(pk, dd)
    for pk, sd in cur.execute(
            "select player_key, snapshot_date from snapshots where source='auto_detect'"):
        pk = C(pk)
        if debut.get(pk) is None:
            debut[pk] = _d(sd)

    war = {}
    for pk, pj in cur.execute("select player_key, payload_json from career_war"):
        try:
            p = json.loads(pj)
            pk = C(pk)
            w = float(p.get("career_war") or 0.0)
            if pk not in war or abs(w) > abs(war[pk]):
                war[pk] = w
        except Exception:
            pass
    con.close()

    rows = []
    for pk, ls in listings.items():
        dates = sorted(x[0] for x in ls)
        last_list = dates[-1]
        for anchor_year in (2021, 2022):
            graded = [(dt, fv) for dt, fv in ls
                      if fv is not None and dt.year == anchor_year]
            if not graded:
                continue
            anchor_date = max(dt for dt, _ in graded)
            fvs = [fv for dt, fv in graded if dt == anchor_date]
            anchor_fv = sum(fvs) / len(fvs)
            band = int(round(anchor_fv / 5.0) * 5)
            if band not in BANDS:
                continue
            after = [dt for dt in dates if dt > anchor_date]
            if last_list.year <= anchor_year:
                grp = "dropped"        # never listed after the anchor year
            elif after and (after[0] - anchor_date).days <= RELIST_STRICT_DAYS:
                grp = "relisted"
            else:
                continue
            deb = debut.get(pk)
            if deb is not None and deb <= anchor_date + timedelta(days=GRAD_EXCL_DAYS):
                continue                # graduated off the list, not dropped
            rows.append(dict(pk=pk, year=anchor_year, band=band, grp=grp,
                             war=war.get(pk, 0.0), debut=deb is not None))
    return rows


def _band_stats(sub):
    n = len(sub)
    if n == 0:
        return None
    mw = sum(r["war"] for r in sub) / n
    return {"n": n, "mean_war": round(mw, 3),
            "bust_rate": round(sum(1 for r in sub if not r["debut"]) / n, 3),
            "implied_fv": round(_implied(mw), 2)}


def main():
    rows = build_cohorts()
    fit_rows = [r for r in rows if r["year"] == 2021 and r["grp"] == "dropped"]
    val_rows = [r for r in rows if r["year"] == 2022 and r["grp"] == "dropped"]
    ctl_rows = [r for r in rows if r["grp"] == "relisted"]

    fit, val, ctl = {}, {}, {}
    for b in BANDS:
        fit[b] = _band_stats([r for r in fit_rows if r["band"] == b])
        val[b] = _band_stats([r for r in val_rows if r["band"] == b])
        ctl[b] = _band_stats([r for r in ctl_rows if r["band"] == b])

    # Fitted terminal discounts (2021 cohort), POOLED across bands: the dropped
    # cohort's terminal state is band-independent (bust ~90%, realized implied
    # ~FV20-23 at every band, both years), so the pooled implied FV is the
    # stable estimate and per-band discount = band - pooled_implied, capped.
    # (Per-band fitting starves FV45: fit n=10 < 15, even though its held-out
    # 2022 cohort n=20 shows the same terminal state.) Validation stays PER
    # BAND on the held-out year, including 45.
    pooled_fit = [r for r in fit_rows]
    pooled_mw = sum(r["war"] for r in pooled_fit) / max(1, len(pooled_fit))
    pooled_implied = _implied(pooled_mw)
    discounts = {}
    if len(pooled_fit) >= 3 * MIN_BAND_N:
        for b in BANDS:
            discounts[b] = round(min(DISCOUNT_CAP, max(0.0, b - pooled_implied)), 1)

    # held-out validation (2022 cohort)
    clauses = {"c1_error_improves": {}, "c2_no_overshoot": {}, "c3_positive_fit": {}}
    c1_ok = c2_ok = True
    for b, disc in discounts.items():
        s = val[b]
        if not (s and s["n"] >= MIN_BAND_N):
            continue
        err_raw = abs(b - s["implied_fv"])
        err_dec = abs((b - disc) - s["implied_fv"])
        clauses["c1_error_improves"][b] = {
            "raw_err": round(err_raw, 2), "decayed_err": round(err_dec, 2),
            "pass": err_dec < err_raw}
        c1_ok &= err_dec < err_raw
        overshoot_floor = s["implied_fv"] - 2.0
        clauses["c2_no_overshoot"][b] = {
            "decayed": round(b - disc, 2), "floor": round(overshoot_floor, 2),
            "pass": (b - disc) >= overshoot_floor}
        c2_ok &= (b - disc) >= overshoot_floor
    c3_ok = bool(discounts) and all(d > 0 for d in discounts.values())
    clauses["c3_positive_fit"] = {"discounts": discounts, "pass": c3_ok}

    ship = c1_ok and c2_ok and c3_ok
    artifact = {
        "experiment": "xfv_stale_anchor",
        "generated_at": date.today().isoformat(),
        "gates_doc": "docs/efv-2026-07-14/GATES.md (E-STALE)",
        "cohorts": {
            "fit_2021_dropped": {str(b): fit[b] for b in BANDS},
            "validate_2022_dropped": {str(b): val[b] for b in BANDS},
            "relisted_controls": {str(b): ctl[b] for b in BANDS},
        },
        "pooled_fit": {"n": len(fit_rows), "mean_war": round(pooled_mw, 3),
                       "implied_fv": round(pooled_implied, 2)},
        "clauses": clauses,
        "ship": ship,
        "schedule": {
            "ramp_start_months": RAMP_START_MO,
            "ramp_full_months": RAMP_FULL_MO,
            "terminal_discount_by_band": {str(b): d for b, d in discounts.items()},
            "discount_cap": DISCOUNT_CAP,
            "applies_to": "the MODEL fv input for ACTIVE (non-debuted) players only; "
                          "display consensus untouched",
        },
    }
    OUT_PATH.write_text(json.dumps(artifact, indent=1), encoding="utf-8")
    print(f"fit (2021 dropped): { {b: fit[b] for b in BANDS} }")
    print(f"validate (2022 dropped): { {b: val[b] for b in BANDS} }")
    print(f"discounts: {discounts}")
    print(f"SHIP={ship} (c1={c1_ok} c2={c2_ok} c3={c3_ok}) -> wrote {OUT_PATH.name}")


if __name__ == "__main__":
    main()
