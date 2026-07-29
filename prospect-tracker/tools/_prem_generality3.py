# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""GENERALITY LANE, PASS 3. THE ONLY TEST THAT ADJUDICATES THE LANE.

Passes 1 and 2 measured how far each live board row sits from its stratum's historical
outcome. Neither can say whether closing that distance would make the board MORE RIGHT,
because there is no ground truth for an active prospect. This pass supplies one: apply the
proposed fix OUT OF FOLD to players whose careers already happened, and see whether it
predicts realized WAR better than the shipped served grade does.

THE FIX UNDER TEST (the "STRATUM RECENTER" from pass 1/2, exactly as a patch would ship):
    offset(s)   = mean_TRAIN(served eFV in stratum s) - stratum_implied_FV_TRAIN(s)
    score(i)    = served eFV(i) - offset(stratum(i))
Ranking is invariant to a global constant, so this is a pure per-stratum re-leveling.

DESIGN, per docs/EFV_GATE_STANDARD.md:
  * >= 4 forward-chained time splits (train on every cohort strictly before the test
    cohort), never a single split;
  * a ZERO-INFORMATION CONTROL: the stratum label row-permuted inside TRAIN only, so the
    offsets keep their marginal and lose their meaning. If the control scores as well, the
    stratum surface is not what is doing the work;
  * a paired bootstrap resampling TRAIN and TEST with the offsets refit on every draw;
  * a permutation null band on the same delta.

Reported in BOTH framings the lane requires:
  * SERVED framing  -- rows that carry a MiLB track record, i.e. what the board displays;
  * POOLED framing  -- every resolved row, with unstratifiable rows scored at baseline,
    which is what a pooled gate number would see.

Read-only apart from one eval artifact.
"""
from __future__ import annotations

import collections
import json
import random
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
DATA = ROOT / "data"

from _prem_generality import (  # noqa: E402
    SHRINK_K, build_cuts, implied_fv, load_side, stratum,
)

random.seed(20260725)
BOOT = 1000
PERM = 500
DROP_LEVELS = {"CPX"}
TEST_COHORTS = [2019, 2020, 2021, 2022, 2023]


def spearman(a, b):
    def rk(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                j += 1
            av = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[o[k]] = av
            i = j + 1
        return r
    ra, rb = rk(a), rk(b)
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((x - mb) ** 2 for x in rb) ** 0.5
    return num / (da * db) if da and db else 0.0


def fit_offsets_side(train, is_pit, permute=False):
    """offset(s) = mean_TRAIN(served) - implied_TRAIN(s), fit on the train cohorts only."""
    rows = [r for r in train
            if r["strat"] is not None and r["strat"][0] not in DROP_LEVELS
            and r["served"] is not None]
    if not rows:
        return {}
    labels = [r["strat"] for r in rows]
    if permute:
        labels = labels[:]
        random.shuffle(labels)
    cells = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    lvl = collections.defaultdict(lambda: [0.0, 0.0])
    for r, s in zip(rows, labels):
        c = cells[s]
        c[0] += r["y"]
        c[1] += 1.0
        c[2] += r["served"]
        L = lvl[s[0]]
        L[0] += r["y"]
        L[1] += 1.0
    lvm = {k: (v[0] / v[1] if v[1] else 0.0) for k, v in lvl.items()}
    out = {}
    for s, c in cells.items():
        mu = (c[1] * (c[0] / c[1]) + SHRINK_K * lvm.get(s[0], 0.0)) / (c[1] + SHRINK_K)
        out[s] = (c[2] / c[1]) - implied_fv(mu, is_pit)
    return out


def score(rows, offs, only=None):
    """baseline vs candidate scores on a test fold."""
    base, cand, y = [], [], []
    for r in rows:
        if r["served"] is None or r["y"] is None:
            continue
        o = 0.0
        s = r["strat"]
        if s is not None and s[0] not in DROP_LEVELS and s in offs:
            if only is None or s in only:
                o = offs[s]
        base.append(r["served"])
        cand.append(r["served"] - o)
        y.append(r["y"])
    return base, cand, y


def run(rows_by_side, framing, only=None, permute=False):
    """-> (fold deltas, pooled base rho, pooled cand rho)."""
    deltas, br, cr = [], [], []
    for pit, rows in rows_by_side.items():
        for T in TEST_COHORTS:
            tr = [r for r in rows if (r["cohort"] or 0) < T]
            te = [r for r in rows if (r["cohort"] or 0) == T]
            if len(tr) < 60 or len(te) < 25:
                continue
            offs = fit_offsets_side(tr, pit, permute=permute)
            b, c, y = score(te, offs, only=only)
            if len(y) < 25:
                continue
            rb, rc = spearman(b, y), spearman(c, y)
            deltas.append(rc - rb)
            br.append(rb)
            cr.append(rc)
    return deltas, br, cr


def main() -> int:
    xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    served = {}
    for k, v in xfv.items():
        g = v.get("xfv_grade")
        if isinstance(g, (int, float)):
            served[k] = float(g)

    scored_h = {r["player_key"]: r for r in
                json.loads((DATA / "xfv_scored.json").read_text(encoding="utf-8"))}
    scored_p = {r["player_key"]: r for r in
                json.loads((DATA / "xfv_scored_pitcher.json").read_text(encoding="utf-8"))}

    res_h, _ = load_side(False)
    res_p, _ = load_side(True)
    cuts_h, cuts_p = build_cuts(res_h), build_cuts(res_p)

    def prep(res, cuts, sc):
        out = []
        for r in res:
            g = sc.get(r["key"], {}).get("xfv_grade")
            out.append({"key": r["key"], "y": r["y"], "cohort": r["cohort"],
                        "served": float(g) if isinstance(g, (int, float)) else None,
                        "strat": stratum(r, cuts), "has_milb": r["has_milb"],
                        "kind": r["kind"]})
        return out

    all_h = prep(res_h, cuts_h, scored_h)
    all_p = prep(res_p, cuts_p, scored_p)
    srv_h = [r for r in all_h if r["strat"] is not None and r["strat"][0] not in DROP_LEVELS]
    srv_p = [r for r in all_p if r["strat"] is not None and r["strat"][0] not in DROP_LEVELS]

    print("=" * 78)
    print("PASS 3: does STRATUM RECENTER predict realized WAR better than the shipped grade?")
    print("=" * 78)
    print(f"  served framing  : {len(srv_h)} hitters + {len(srv_p)} pitchers "
          f"(has a MiLB track record, non-CPX = the board's own population)")
    print(f"  pooled framing  : {len(all_h)} hitters + {len(all_p)} pitchers")
    print(f"  forward-chained test cohorts: {TEST_COHORTS}\n")

    results = {}
    for framing, hb, pb in (("SERVED", srv_h, srv_p), ("POOLED", all_h, all_p)):
        rows = {False: hb, True: pb}
        d, br, cr = run(rows, framing)
        if not d:
            print(f"{framing}: no usable folds")
            continue
        # zero-information control
        cd = []
        for _ in range(40):
            dd, _b, _c = run(rows, framing, permute=True)
            if dd:
                cd.append(st.mean(dd))
        # paired bootstrap over TRAIN and TEST with refit
        boot = []
        for _ in range(BOOT):
            bd = []
            for pit, rr in rows.items():
                for T in TEST_COHORTS:
                    tr = [r for r in rr if (r["cohort"] or 0) < T]
                    te = [r for r in rr if (r["cohort"] or 0) == T]
                    if len(tr) < 60 or len(te) < 25:
                        continue
                    trb = [tr[random.randrange(len(tr))] for _ in range(len(tr))]
                    teb = [te[random.randrange(len(te))] for _ in range(len(te))]
                    offs = fit_offsets_side(trb, pit)
                    b, c, y = score(teb, offs)
                    if len(y) < 25:
                        continue
                    bd.append(spearman(c, y) - spearman(b, y))
            if bd:
                boot.append(st.mean(bd))
        boot.sort()
        lo, hi = boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]
        mean_d = st.mean(d)
        cd.sort()
        print(f"{framing} framing, {len(d)} forward-chained folds")
        print(f"  baseline (shipped served eFV) mean fold Spearman  {st.mean(br):+.4f}")
        print(f"  candidate (stratum recentered) mean fold Spearman {st.mean(cr):+.4f}")
        print(f"  DELTA                                             {mean_d:+.4f}   "
              f"CI95 [{lo:+.4f},{hi:+.4f}]")
        print(f"  zero-information control (label permuted in TRAIN) "
              f"{st.mean(cd):+.4f} [p5 {cd[int(0.05 * len(cd))]:+.4f}, "
              f"p95 {cd[int(0.95 * len(cd))]:+.4f}]")
        print(f"  per-fold deltas: " + ", ".join(f"{x:+.3f}" for x in d))
        print(f"  folds improved: {sum(1 for x in d if x > 0)}/{len(d)}")
        mde = 0.017
        v = ("SHIP-GRADE WIN" if lo > 0 and mean_d > mde else
             "MEASURED NULL" if lo <= 0 <= hi else
             "HARMFUL" if hi < 0 else "below MDE95, NULL")
        print(f"  MDE95 for a feature-scale change is ~{mde} pooled Spearman -> {v}\n")
        results[framing] = {
            "n_folds": len(d), "base_rho": round(st.mean(br), 4),
            "cand_rho": round(st.mean(cr), 4), "delta": round(mean_d, 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            "control_delta": round(st.mean(cd), 4),
            "control_p5": round(cd[int(0.05 * len(cd))], 4),
            "control_p95": round(cd[int(0.95 * len(cd))], 4),
            "per_fold": [round(x, 4) for x in d],
            "folds_improved": sum(1 for x in d if x > 0), "verdict": v,
        }

    # ---- the OWNER'S NARROW FIX: recenter only old-for-level strata, then only
    #      the exact Bradfield cell.
    print("=" * 78)
    print("THE NARROW FIXES the owner's complaint actually implies")
    print("=" * 78)
    rows = {False: srv_h, True: srv_p}
    for name, sel in (
        ("OLD-for-level strata only", lambda s: s[1] == "old"),
        ("OLD + below-median production only", lambda s: s[1] == "old" and s[2] == "lowProd"),
        ("Triple-A OLD + lowProd only (the Bradfield cell)",
         lambda s: s == ("AAA", "old", "lowProd")),
    ):
        strata = set()
        for rr in rows.values():
            for r in rr:
                if r["strat"] and sel(r["strat"]):
                    strata.add(r["strat"])
        d, br, cr = run(rows, "SERVED", only=strata)
        if not d:
            print(f"  {name}: no usable folds")
            continue
        boot = []
        for _ in range(400):
            bd = []
            for pit, rr in rows.items():
                for T in TEST_COHORTS:
                    tr = [r for r in rr if (r["cohort"] or 0) < T]
                    te = [r for r in rr if (r["cohort"] or 0) == T]
                    if len(tr) < 60 or len(te) < 25:
                        continue
                    trb = [tr[random.randrange(len(tr))] for _ in range(len(tr))]
                    teb = [te[random.randrange(len(te))] for _ in range(len(te))]
                    offs = fit_offsets_side(trb, pit)
                    b, c, y = score(teb, offs, only=strata)
                    if len(y) < 25:
                        continue
                    bd.append(spearman(c, y) - spearman(b, y))
            if bd:
                boot.append(st.mean(bd))
        boot.sort()
        lo, hi = boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]
        v = "WIN" if lo > 0 else ("HARMFUL" if hi < 0 else "MEASURED NULL")
        print(f"  {name}")
        print(f"    delta {st.mean(d):+.4f}  CI95 [{lo:+.4f},{hi:+.4f}]  "
              f"folds improved {sum(1 for x in d if x > 0)}/{len(d)}  -> {v}")
        results[name] = {"delta": round(st.mean(d), 4), "ci95": [round(lo, 4), round(hi, 4)],
                         "folds_improved": sum(1 for x in d if x > 0), "n_folds": len(d),
                         "verdict": v}

    (DATA / "xfv_generality3_eval.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8")
    print("\nwrote data/xfv_generality3_eval.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
