"""Stage 1: coverage census for the five new sources against the eFV matrix."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _src_lab import (raw_rows, decision_year, tj_index, draft_index,
                      amateur_index, pipeline_index, venue_index, SCORED_YEARS)

rep = {}
for side in ("hit", "pit"):
    rows = raw_rows(side)
    keep = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    keep = [r for r in keep if r.get("target_censored") is not None
            and r.get("consensus_fv_raw") is not None]
    test = [r for r in keep if decision_year(r) in SCORED_YEARS]
    train = [r for r in keep if decision_year(r) < min(SCORED_YEARS)]
    deb = [r for r in keep if r["kind"] == "debuted"]

    def cov(pool, fn):
        n = sum(1 for r in pool if fn(r))
        return f"{n}/{len(pool)} ({100.0*n/max(1,len(pool)):.1f}%)"

    mid = lambda r: r.get("mlbam_id")
    tj = tj_index()
    dr = draft_index()
    am = amateur_index()
    pv = pipeline_index()

    def has_tj(r):
        m = r.get("mlbam_id")
        return bool(m) and str(m) in tj

    def has_draft(r):
        m = r.get("mlbam_id")
        return bool(m) and str(m) in dr

    def has_am(r):
        m = r.get("mlbam_id")
        return bool(m) and str(m) in am

    def has_pv(r):
        m = r.get("mlbam_id")
        if not m:
            return False
        dy = decision_year(r)
        return any(str(m) in pv.get(y, {}) for y in pv if y < dy)

    rep[side] = {
        "pool": {"full": len(keep), "train_pre2020": len(train),
                 "test_2020_23": len(test), "debuted": len(deb)},
        "mlbam_id": {"full": cov(keep, mid), "test": cov(test, mid),
                     "train": cov(train, mid), "debuted": cov(deb, mid)},
        "tj_known_player": {"full": cov(keep, has_tj), "test": cov(test, has_tj)},
        "draft_slot_row": {"full": cov(keep, has_draft), "test": cov(test, has_draft)},
        "amateur_row": {"full": cov(keep, has_am), "test": cov(test, has_am)},
        "pipeline_asof_row": {"full": cov(keep, has_pv), "test": cov(test, has_pv)},
        "existing_pick_overall": {"full": cov(keep, lambda r: r.get("pick_overall") is not None),
                                  "test": cov(test, lambda r: r.get("pick_overall") is not None)},
        "existing_bonus_usd": {"full": cov(keep, lambda r: r.get("bonus_usd") is not None),
                               "test": cov(test, lambda r: r.get("bonus_usd") is not None)},
    }

    # what the draft source ADDS on top of what the matrix already has
    add_pick = add_bonus = confl = 0
    for r in keep:
        m = r.get("mlbam_id")
        d = dr.get(str(m)) if m else None
        if not d:
            continue
        if r.get("pick_overall") is None and d.get("pick_overall") is not None:
            add_pick += 1
        if r.get("bonus_usd") is None and d.get("bonus_usd") is not None:
            add_bonus += 1
        if (r.get("pick_overall") is not None and d.get("pick_overall") is not None
                and int(r["pick_overall"]) != int(d["pick_overall"])):
            confl += 1
    rep[side]["draft_fill_delta"] = {
        "rows_backfilled_pick": add_pick, "rows_backfilled_bonus": add_bonus,
        "pick_conflicts_with_existing": confl}

    # TJ, pitchers: pre-decision surgeries actually present
    if side == "pit":
        pre = 0
        for r in keep:
            m = r.get("mlbam_id")
            if not m:
                continue
            ev = tj.get(str(m))
            if ev and any(int(e["year"]) < decision_year(r) for e in ev if e.get("year")):
                pre += 1
        rep[side]["tj_pre_decision_fires"] = f"{pre}/{len(keep)}"

    # amateur league season span vs decision year
    if side == "hit":
        yrs = Counter()
        for recs in list(am.values())[:99999]:
            for e in recs:
                yrs[e.get("season")] += 1
        rep["_amateur_season_hist"] = dict(sorted(yrs.items()))
        sp = Counter()
        for recs in am.values():
            for e in recs:
                sp[e.get("sport_label")] += 1
        rep["_amateur_sport_hist"] = dict(sp)

pvm = json.loads(Path("data/pipeline_vintages.json").read_text(encoding="utf-8"))["_meta"]
rep["_pipeline_meta"] = pvm["per_year"]
rep["_venue"] = {"n": len(venue_index()),
                 "levels": dict(Counter(v.get("level") for v in venue_index().values())),
                 "with_elev": sum(1 for v in venue_index().values() if v.get("elevation_ft") is not None),
                 "with_dims": sum(1 for v in venue_index().values() if v.get("dims"))}

print(json.dumps(rep, indent=1))
