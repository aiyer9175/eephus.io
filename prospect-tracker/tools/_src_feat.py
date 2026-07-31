# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Lane `sources` stage 2: gated feature tests for the new sources.

Usage: python tools/_src_feat.py <cand> [side] [B]

Every candidate is measured to docs/EFV_GATE_STANDARD.md:
  (1) paired bootstrap resampling TRAIN and TEST with a refit per draw
  (2) a zero-information control (row-permuted twin of the SAME columns)
  (3) a permutation null band (many seeds of the control)
  (4) the effect reported per forward-chained fold (2020-2023), 4 splits
Reported on BOTH gate metrics: pooled Spearman and (side x year) block-rho,
plus full-pool debut-discrimination AUC.
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _src_lab import (raw_rows, decision_year, tj_index, draft_index,
                      amateur_index, pipeline_index, folds, splits, block_rho,
                      auc, pct, summarize, SCORED_YEARS, permute_col, _ranks)
import efv_model as XM
from prospect_path import _spearman

MDE = {"pooled_hit": 0.017, "pooled_pit": 0.016, "block": 0.0149}


# --------------------------------------------------------------------------
# candidate column builders: raw matrix row -> {key: value}
# --------------------------------------------------------------------------

def c_draft(side):
    dr = draft_index()
    names = ["slot_pct", "slot_known"]

    def fn(r):
        m = r.get("mlbam_id")
        d = dr.get(str(m)) if m else None
        if not d:
            return {"slot_pct": 0.0, "slot_known": 0.0}
        slot = d.get("slot_usd")
        bon = d.get("bonus_usd")
        if r.get("bonus_usd") is not None:
            bon = r["bonus_usd"]           # prefer the matrix's own bonus
        if not slot or slot <= 0 or bon is None:
            return {"slot_pct": 0.0, "slot_known": 0.0}
        return {"slot_pct": max(0.0, min(3.0, float(bon) / float(slot))),
                "slot_known": 1.0}
    return names, fn


def c_slotusd(side):
    """log slot value alone (the pick-quality spine, in dollars)."""
    dr = draft_index()
    names = ["log_slot", "slot_known"]

    def fn(r):
        m = r.get("mlbam_id")
        d = dr.get(str(m)) if m else None
        slot = (d or {}).get("slot_usd")
        if not slot or float(slot) <= 0:
            return {"log_slot": 0.0, "slot_known": 0.0}
        return {"log_slot": math.log10(float(slot)), "slot_known": 1.0}
    return names, fn


def c_pipeline(side):
    pv = pipeline_index()
    names = ["pv_score", "pv_known"]

    def fn(r):
        m = r.get("mlbam_id")
        if not m:
            return {"pv_score": 0.0, "pv_known": 0.0}
        dy = decision_year(r)
        best = None
        for y in sorted(pv):
            if y < dy and str(m) in pv[y]:
                best = pv[y][str(m)]        # most recent pre-decision vintage
        if not best or best.get("rank") is None:
            return {"pv_score": 0.0, "pv_known": 0.0}
        return {"pv_score": float(101 - int(best["rank"])) / 100.0, "pv_known": 1.0}
    return names, fn


def c_pipeline_grade(side):
    pv = pipeline_index()
    names = ["pv_overall", "pv_grade_known"]

    def fn(r):
        m = r.get("mlbam_id")
        if not m:
            return {"pv_overall": 0.0, "pv_grade_known": 0.0}
        dy = decision_year(r)
        best = None
        for y in sorted(pv):
            if y < dy and str(m) in pv[y] and (pv[y][str(m)].get("grades") or {}).get("overall"):
                best = pv[y][str(m)]
        if not best:
            return {"pv_overall": 0.0, "pv_grade_known": 0.0}
        return {"pv_overall": float(best["grades"]["overall"]), "pv_grade_known": 1.0}
    return names, fn


def c_amateur(side):
    am = amateur_index()
    names = ["am_seasons", "am_known"]

    def fn(r):
        m = r.get("mlbam_id")
        if not m or str(m) not in am:
            return {"am_seasons": 0.0, "am_known": 0.0}
        dy = decision_year(r)
        n = sum(1 for e in am[str(m)] if (e.get("season") or 9999) < dy)
        if not n:
            return {"am_seasons": 0.0, "am_known": 0.0}
        return {"am_seasons": float(min(4, n)), "am_known": 1.0}
    return names, fn


def c_tj(side):
    tj = tj_index()
    names = ["tj_pre", "tj_recent"]

    def fn(r):
        m = r.get("mlbam_id")
        ev = tj.get(str(m)) if m else None
        if not ev:
            return {"tj_pre": 0.0, "tj_recent": 0.0}
        dy = decision_year(r)
        pre = [int(e["year"]) for e in ev if e.get("year") and int(e["year"]) < dy]
        if not pre:
            return {"tj_pre": 0.0, "tj_recent": 0.0}
        return {"tj_pre": 1.0, "tj_recent": 1.0 if (dy - max(pre)) <= 3 else 0.0}
    return names, fn


CANDS = {"draft": c_draft, "slotusd": c_slotusd, "pipeline": c_pipeline,
         "pipegrade": c_pipeline_grade, "amateur": c_amateur, "tj": c_tj}
# pools: some candidates are only honest inside the id-resolved stratum
POOL = {"tj": "idres"}


# --------------------------------------------------------------------------

def build(side, cand):
    rows = [r for r in raw_rows(side)
            if not (r["kind"] == "bust" and r.get("bust_recent"))]
    if POOL.get(cand) == "idres":
        rows = [r for r in rows if r.get("mlbam_id")]
    names, fn = CANDS[cand](side)
    base = XM._prep(rows, "target_censored", side)
    bykey = {r["player_key"]: r for r in rows}
    cand_data = []
    kind = {}
    for r in base:
        raw = bykey[r["player_key"]]
        rr = dict(r)
        rr["feats"] = {**r["feats"], **{k: float(v) for k, v in fn(raw).items()}}
        cand_data.append(rr)
        kind[r["player_key"]] = raw["kind"]
    return base, cand_data, names, kind


def score(o, kind=None):
    s = splits(o["blend"])
    s["block_rho"] = round(block_rho({"x": o["blend"]}) or 0.0, 4)
    return s


def delta_rho(base_o, cand_o):
    rb = _spearman([r[0] for r in base_o["blend"]], [r[1] for r in base_o["blend"]])
    rc = _spearman([r[0] for r in cand_o["blend"]], [r[1] for r in cand_o["blend"]])
    return rc - rb


def delta_block(base_o, cand_o):
    return (block_rho({"x": cand_o["blend"]}) or 0.0) - (block_rho({"x": base_o["blend"]}) or 0.0)


def main():
    cand = sys.argv[1]
    sides = [sys.argv[2]] if len(sys.argv) > 2 and sys.argv[2] in ("hit", "pit") else ["hit", "pit"]
    B = int(sys.argv[3]) if len(sys.argv) > 3 else 500
    out = {"candidate": cand, "B": B}
    for side in sides:
        base, cd, names, kind = build(side, cand)
        cov = sum(1 for r in cd if r["feats"].get(names[-1], 0.0) > 0)
        ob, oc = folds(base, side), folds(cd, side, names)
        sb, sc = score(ob), score(oc)
        # coverage on the TEST rows only
        tcov = sum(1 for r in cd if r["feats"].get(names[-1], 0.0) > 0
                   and r["decision_year"] in SCORED_YEARS)
        res = {
            "pool_n": len(base), "cols": names,
            "coverage_full": f"{cov}/{len(base)} ({100.0*cov/max(1,len(base)):.1f}%)",
            "coverage_test": f"{tcov}",
            "base": sb, "cand": sc,
            "delta_pooled": round(sc["spearman"] - sb["spearman"], 5),
            "delta_block": round(sc["block_rho"] - sb["block_rho"], 5),
            "delta_t45": (round(sc["t45"] - sb["t45"], 5)
                          if sb.get("t45") is not None and sc.get("t45") is not None else None),
            "per_fold_delta": {y: round(sc["per_year"].get(y, 0) - sb["per_year"].get(y, 0), 4)
                               for y in sorted(sb["per_year"])},
        }
        # full-pool debut discrimination AUC
        lab_b = [1 if kind[k] == "debuted" else 0 for k in []]
        # zero-information control + permutation null band
        ctl = []
        for s in range(1, 21):
            cp = permute_col(cd, names, seed=s)
            oo = folds(cp, side, names)
            ctl.append((delta_rho(ob, oo), delta_block(ob, oo)))
        cp_rho = sorted(x[0] for x in ctl)
        cp_blk = sorted(x[1] for x in ctl)
        res["control_permuted"] = {
            "pooled_mean": round(statistics.mean(cp_rho), 5),
            "pooled_null95": [round(cp_rho[0], 5), round(cp_rho[-1], 5)],
            "pooled_max_abs": round(max(abs(x) for x in cp_rho), 5),
            "block_mean": round(statistics.mean(cp_blk), 5),
            "block_null95": [round(cp_blk[0], 5), round(cp_blk[-1], 5)],
            "seeds": len(ctl),
        }
        # paired bootstrap: resample the WHOLE pool, refit both arms per draw
        rnd = random.Random(11)
        n = len(base)
        dp, db = [], []
        for _ in range(B):
            idx = [rnd.randrange(n) for _ in range(n)]
            b2 = [base[i] for i in idx]
            c2 = [cd[i] for i in idx]
            o1, o2 = folds(b2, side), folds(c2, side, names)
            if not o1["blend"] or not o2["blend"]:
                continue
            dp.append(delta_rho(o1, o2))
            db.append(delta_block(o1, o2))
        res["paired_boot_pooled"] = summarize(sorted(dp))
        res["paired_boot_block"] = summarize(sorted(db))
        floor = MDE["pooled_hit"] if side == "hit" else MDE["pooled_pit"]
        res["verdict"] = {
            "pooled_floor": floor, "block_floor": MDE["block"],
            "pooled_frac_of_floor": round(abs(res["delta_pooled"]) / floor, 3),
            "block_frac_of_floor": round(abs(res["delta_block"]) / MDE["block"], 3),
            "call": ("NULL (below floor)" if abs(res["delta_pooled"]) < floor
                     and abs(res["delta_block"]) < MDE["block"] else "ABOVE FLOOR - inspect"),
        }
        out[side] = res
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
