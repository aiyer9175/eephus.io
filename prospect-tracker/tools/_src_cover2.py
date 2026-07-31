"""Stage 1b: decompose WHY each source's coverage is what it is."""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _src_lab import (raw_rows, decision_year, tj_index, draft_index,
                      amateur_index, pipeline_index, SCORED_YEARS, src)

dr = draft_index(); am = amateur_index(); pv = pipeline_index(); tj = tj_index()
out = {}

# ---- 2. DRAFT: why does the official spine backfill ~0 rows? --------------
d2 = {}
for side in ("hit", "pit"):
    rows = [r for r in raw_rows(side)
            if not (r["kind"] == "bust" and r.get("bust_recent"))
            and r.get("target_censored") is not None
            and r.get("consensus_fv_raw") is not None]
    miss = [r for r in rows if r.get("pick_overall") is None]
    miss_id = [r for r in miss if r.get("mlbam_id")]
    miss_id_indraft = [r for r in miss_id if str(r["mlbam_id"]) in dr]
    # of the rows the source DOES cover, how many already had a pick?
    covered = [r for r in rows if r.get("mlbam_id") and str(r["mlbam_id"]) in dr]
    d2[side] = {
        "rows": len(rows),
        "missing_pick_overall": len(miss),
        "  of those, have mlbam_id": len(miss_id),
        "  of those, present in draft source": len(miss_id_indraft),
        "source-covered rows": len(covered),
        "  already had pick_overall": sum(1 for r in covered if r.get("pick_overall") is not None),
        "  already had bonus_usd": sum(1 for r in covered if r.get("bonus_usd") is not None),
        "missing-pick rows that are IFA": sum(1 for r in miss if r.get("is_ifa")),
        "missing-pick decision-year hist": dict(sorted(Counter(decision_year(r) for r in miss).items())),
    }
    # conflicts detail
    cf = []
    for r in covered:
        d = dr[str(r["mlbam_id"])]
        if r.get("pick_overall") is not None and d.get("pick_overall") is not None \
           and int(r["pick_overall"]) != int(d["pick_overall"]):
            cf.append({"player_key": r["player_key"], "matrix": r["pick_overall"],
                       "statsapi": d["pick_overall"], "yr": d.get("year")})
        if r.get("bonus_usd") is not None and d.get("bonus_usd") is not None:
            a, b = float(r["bonus_usd"]), float(d["bonus_usd"])
            if a > 0 and abs(a - b) / max(a, b) > 0.02:
                cf.append({"player_key": r["player_key"], "bonus_matrix": a,
                           "bonus_statsapi": b, "yr": d.get("year")})
    d2[side]["conflicts"] = cf[:20]
    d2[side]["n_conflicts"] = len(cf)
    # NEW columns the source offers that the matrix has NO analogue for
    have_slot = sum(1 for r in covered if dr[str(r["mlbam_id"])].get("slot_usd") is not None)
    have_pool = sum(1 for r in covered if dr[str(r["mlbam_id"])].get("pool_pct") is not None)
    d2[side]["NEW slot_usd on covered"] = have_slot
    d2[side]["NEW pool_pct (bonus/slot) on covered"] = have_pool
out["draft"] = d2

# ---- 4. AMATEUR: as-of usability -----------------------------------------
a2 = {}
for side in ("hit", "pit"):
    rows = [r for r in raw_rows(side)
            if not (r["kind"] == "bust" and r.get("bust_recent"))
            and r.get("target_censored") is not None
            and r.get("consensus_fv_raw") is not None]
    asof = post = 0
    for r in rows:
        m = r.get("mlbam_id")
        if not m or str(m) not in am:
            continue
        dy = decision_year(r)
        ev = am[str(m)]
        if any((e.get("season") or 9999) < dy for e in ev):
            asof += 1
        else:
            post += 1
    a2[side] = {"rows": len(rows), "as_of_usable(season<decision_yr)": asof,
                "covered_but_all_post_decision": post}
    # test-fold only
    tf = [r for r in rows if decision_year(r) in SCORED_YEARS]
    a = 0
    for r in tf:
        m = r.get("mlbam_id")
        if m and str(m) in am and any((e.get("season") or 9999) < decision_year(r) for e in am[str(m)]):
            a += 1
    a2[side]["test_fold_as_of_usable"] = f"{a}/{len(tf)}"
    # which sport labels supply the as-of rows
    lab = Counter()
    for r in rows:
        m = r.get("mlbam_id")
        if not m or str(m) not in am:
            continue
        for e in am[str(m)]:
            if (e.get("season") or 9999) < decision_year(r):
                lab[e.get("sport_label")] += 1
    a2[side]["as_of_row_sport_labels"] = dict(lab)
out["amateur"] = a2

# ---- 5. PIPELINE: usable as-of overlap, rank AND grades -------------------
p2 = {}
vint = src("pipeline_vintages")["vintages"]
sample = None
for yr, recs in sorted(vint.items()):
    if recs:
        sample = {"year": yr, "rec": recs[0]}
        break
p2["_sample_record"] = sample
gk = set()
for yr, recs in vint.items():
    for rec in recs:
        g = rec.get("grades") or {}
        gk |= set(g.keys())
p2["_grade_subfields"] = sorted(gk)
for side in ("hit", "pit"):
    rows = [r for r in raw_rows(side)
            if not (r["kind"] == "bust" and r.get("bust_recent"))
            and r.get("target_censored") is not None
            and r.get("consensus_fv_raw") is not None]
    rank_asof = grade_asof = 0
    yrs = Counter()
    for r in rows:
        m = r.get("mlbam_id")
        if not m:
            continue
        dy = decision_year(r)
        best = None
        bestg = None
        for y in sorted(pv):
            if y >= dy:
                continue
            rec = pv[y].get(str(m))
            if rec:
                best = rec
                if rec.get("grades"):
                    bestg = rec
        if best:
            rank_asof += 1
            yrs[decision_year(r)] += 1
        if bestg:
            grade_asof += 1
    p2[side] = {"rows": len(rows), "as_of_rank_rows": rank_asof,
                "as_of_GRADE_rows": grade_asof,
                "as_of_rank_by_decision_year": dict(sorted(yrs.items())),
                "test_fold_rank_rows": sum(v for k, v in yrs.items() if k in SCORED_YEARS)}
out["pipeline"] = p2

# ---- 1. TJ: missingness confound check -----------------------------------
t2 = {}
rows = [r for r in raw_rows("pit")
        if not (r["kind"] == "bust" and r.get("bust_recent"))
        and r.get("target_censored") is not None
        and r.get("consensus_fv_raw") is not None]
withid = [r for r in rows if r.get("mlbam_id")]
noid = [r for r in rows if not r.get("mlbam_id")]
def dbrate(p):
    return round(sum(1 for r in p if r["kind"] == "debuted") / max(1, len(p)), 3)
def meanwar(p):
    v = [float(r["target_censored"]) for r in p]
    return round(sum(v) / max(1, len(v)), 3)
t2["id_resolved"] = {"n": len(withid), "debut_rate": dbrate(withid), "mean_target": meanwar(withid)}
t2["id_missing"] = {"n": len(noid), "debut_rate": dbrate(noid), "mean_target": meanwar(noid)}
fires = [r for r in withid if tj.get(str(r["mlbam_id"]))
         and any(int(e["year"]) < decision_year(r) for e in tj[str(r["mlbam_id"])] if e.get("year"))]
nofire = [r for r in withid if r not in fires]
t2["tj_pre_1 (within id-resolved)"] = {"n": len(fires), "debut_rate": dbrate(fires), "mean_target": meanwar(fires)}
t2["tj_pre_0 (within id-resolved)"] = {"n": len(nofire), "debut_rate": dbrate(nofire), "mean_target": meanwar(nofire)}
out["tj_confound"] = t2

print(json.dumps(out, indent=1, default=str))
