# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""GENERALITY LANE, PASS 2. Pass 1 (tools/_prem_generality.py) produced two lists that are
artifacts, and the artifacts are the finding.

PASS-1 DEFECTS THIS PASS REPAIRS.

 1. SCALE MISMATCH. Served eFV spans roughly 20-65. The stratum-implied surface is
    compressed into roughly 20-58 and its MASS sits near 40-48, because most resolved
    prospects produce little WAR. So `served - implied` is mechanically increasing in the
    served grade itself: pass 1 found +8.96 mean gap in the current top 100 and -14.96
    beyond slot 1000, and 94.5% vs 0.6% over-graded. That is one number (the board's own
    grade) reappearing as a "finding". The corrected statistic CENTERS the gap on the
    board-wide mean gap, which is rank-invariant and therefore honest.

 2. THE CPX STRATUM IS DEGENERATE. 104 of 105 resolved complex-level hitters are busts
    carrying exactly 0.0 realized WAR with observed_seasons=6, so every CPX cell inverts to
    the FV-20 floor with ZERO variance. That is why 38 of pass 1's "worst 50 over-graded"
    were complex-league teenagers with a zero-width bootstrap CI. Excluded here.

 3. THE SERVED FLOOR. Board rows served exactly 20.0 are the model's floor for players it
    declines to grade, not a claim that they are worthless. All 50 of pass 1's
    "under-graded" rows were floor rows. Excluded here.

 4. NO WITHIN-STRATUM RESOLUTION. Every active player in a stratum shares one implied
    value, so a per-player |gap| ranking is just the served ordering inside the stratum.
    The honest unit of analysis is THE STRATUM. This pass ranks strata and then reports how
    many live board rows sit in the strata that are resolvably mis-served.

Controls per docs/EFV_GATE_STANDARD.md section 2: paired bootstrap over resolved players
(the implied side) AND active players (the served side), refit per draw; the stratum label
row-permuted as the zero-information control, recomputed on the CLEAN subset; a permutation
null band on the headline concentration statistic.

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
    SHRINK_K, board_cost, build_cuts, crosstab, implied_fv, ipw_weights, load_side,
    rank_map, score_board, stratum, stratum_means, _acq, _posgrp,
)

random.seed(20260725)
BOOT = 2000
DROP_LEVELS = {"CPX"}
FLOOR = 20.0001


def clean(rows):
    return [r for r in rows
            if r["stratum"][0] not in DROP_LEVELS and r["served"] > FLOOR]


def perm_control(res, active, cuts, B=400, drop=True):
    """Zero-information control on the CLEAN subset: row-permute the stratum label among
    resolved players (identical cell-size marginal, no information)."""
    pool = [r for r in res if r["has_milb"]]
    pool = [r for r in pool if stratum(r, cuts) is not None]
    if drop:
        pool = [r for r in pool if stratum(r, cuts)[0] not in DROP_LEVELS]
    labels = [stratum(r, cuts) for r in pool]
    need = {}
    for a in active:
        need.setdefault((a["stratum"], a["pit"]), []).append(a)
    sds, means = [], []
    for _ in range(B):
        perm = labels[:]
        random.shuffle(perm)
        cells = collections.defaultdict(lambda: [0.0, 0.0])
        lvl = collections.defaultdict(lambda: [0.0, 0.0])
        for r, s in zip(pool, perm):
            c = cells[s]
            c[0] += r["y"]
            c[1] += 1.0
            L = lvl[s[0]]
            L[0] += r["y"]
            L[1] += 1.0
        lvm = {k: (v[0] / v[1] if v[1] else 0.0) for k, v in lvl.items()}
        gaps = []
        for (s, pit), rows in need.items():
            c = cells.get(s)
            if c is None:
                continue
            m = c[0] / c[1] if c[1] else 0.0
            mu = (c[1] * m + SHRINK_K * lvm.get(s[0], 0.0)) / (c[1] + SHRINK_K)
            imp = implied_fv(mu, pit)
            for a in rows:
                gaps.append(a["served"] - imp)
        if len(gaps) > 30:
            g0 = st.mean(gaps)
            sds.append(st.pstdev([g - g0 for g in gaps]))
            means.append(g0)
    return sds, means


def stratum_offsets(rows, res_by_side, cuts_by_side, B=BOOT):
    """Per-stratum CENTERED offset = (mean served - implied) - (board-wide mean gap).
    Positive => this stratum is served ABOVE how the board treats strata on average, given
    what the stratum historically produced.

    Paired bootstrap: resample RESOLVED players (moves `implied`) and ACTIVE players
    (moves `mean served`) on every draw, and recompute the centering constant on the same
    draw, so the CI is on the CENTERED quantity."""
    keys = sorted({(r["pit"],) + r["stratum"] for r in rows})
    act_by = collections.defaultdict(list)
    for r in rows:
        act_by[(r["pit"],) + r["stratum"]].append(r["served"])

    pools = {}
    for pit, res in res_by_side.items():
        cuts = cuts_by_side[pit]
        p = [(stratum(r, cuts), r["y"]) for r in res if r["has_milb"]]
        pools[pit] = [x for x in p
                      if x[0] is not None and x[0][0] not in DROP_LEVELS]

    draws = collections.defaultdict(list)
    rr = random.randrange
    for _ in range(B):
        imp = {}
        for pit, pool in pools.items():
            n = len(pool)
            cells = collections.defaultdict(lambda: [0.0, 0.0])
            lvl = collections.defaultdict(lambda: [0.0, 0.0])
            for _i in range(n):
                s, y = pool[rr(n)]
                c = cells[s]
                c[0] += y
                c[1] += 1.0
                L = lvl[s[0]]
                L[0] += y
                L[1] += 1.0
            lvm = {k: (v[0] / v[1] if v[1] else 0.0) for k, v in lvl.items()}
            for s, c in cells.items():
                m = c[0] / c[1] if c[1] else 0.0
                mu = (c[1] * m + SHRINK_K * lvm.get(s[0], 0.0)) / (c[1] + SHRINK_K)
                imp[(pit,) + s] = implied_fv(mu, pit)
        raw, wts = {}, {}
        for k in keys:
            if k not in imp:
                continue
            sv = act_by[k]
            n = len(sv)
            bs = [sv[rr(n)] for _ in range(n)]
            raw[k] = st.mean(bs) - imp[k]
            wts[k] = n
        if not raw:
            continue
        tot = sum(wts.values())
        centre = sum(raw[k] * wts[k] for k in raw) / tot
        for k in raw:
            draws[k].append(raw[k] - centre)

    out = []
    gmean = None
    allgaps = []
    for r in rows:
        allgaps.append(r["gap"])
    gmean = st.mean(allgaps)
    for k in keys:
        d = draws.get(k)
        if not d or len(d) < B * 0.5:
            continue
        d.sort()
        lo, hi = d[int(0.025 * len(d))], d[int(0.975 * len(d))]
        sv = act_by[k]
        out.append({
            "side": "PIT" if k[0] else "HIT", "stratum": "/".join(k[1:]),
            "n_active": len(sv), "mean_served": st.mean(sv),
            "centered_offset": st.mean(d), "lo": lo, "hi": hi,
            "resolvable": lo > 0 or hi < 0,
        })
    out.sort(key=lambda r: -r["centered_offset"])
    return out, gmean


def main() -> int:
    xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    served_all = {k: v["xfv_grade"] for k, v in xfv.items()
                  if v.get("kind") == "active" and isinstance(v.get("xfv_grade"), (int, float))}
    cons_all = {k: v.get("consensus_fv") for k, v in xfv.items()}
    bslot = rank_map(list(served_all.items()))

    res_h, act_h = load_side(False)
    res_p, act_p = load_side(True)
    cuts_h, cuts_p = build_cuts(res_h), build_cuts(res_p)

    scored = []
    for pit, res, act, cuts in ((False, res_h, act_h, cuts_h), (True, res_p, act_p, cuts_p)):
        cells, _lv, ncell = stratum_means(res, cuts)
        w = ipw_weights(res)
        cells_ipw, _l2, _n2 = stratum_means(res, cuts, weights=w)
        s = score_board(act, cells, served_all, cuts)
        ipw = {r["key"]: r["gap"] for r in score_board(act, cells_ipw, served_all, cuts)}
        for r in s:
            r["gap_ipw"] = ipw.get(r["key"])
            r["cons"] = cons_all.get(r["key"])
            r["slot"] = bslot.get(r["key"])
            r["ncell"] = ncell.get(r["stratum"], 0)
        scored.extend(s)

    print("=" * 78)
    print("PASS-1 ARTIFACT AUDIT: what the raw |gap| lists were actually made of")
    print("=" * 78)
    n0 = len(scored)
    cpx = [r for r in scored if r["stratum"][0] in DROP_LEVELS]
    floor = [r for r in scored if r["served"] <= FLOOR]
    print(f"  stratifiable board rows                   {n0}")
    print(f"  in the DEGENERATE CPX stratum             {len(cpx)}  "
          f"({len(cpx) / n0:.1%})  every cell inverts to the FV-20 floor")
    print(f"  served at the FV-20 model floor           {len(floor)}  ({len(floor) / n0:.1%})")
    rows = clean(scored)
    print(f"  -> CLEAN analysis set                     {len(rows)}  ({len(rows) / n0:.1%})")

    gm = st.mean([r["gap"] for r in rows])
    for r in rows:
        r["cgap"] = r["gap"] - gm
    print(f"\n  board-wide mean raw gap on the clean set  {gm:+.2f} FV")
    print("  (this constant is the SCALE MISMATCH between the served grade distribution and")
    print("   the compressed stratum-implied surface; it is removed by centering, and")
    print("   removing it changes no ranking)")

    # confound demonstration
    xs = sorted(rows, key=lambda r: r["served"])
    q = len(xs) // 5
    print("\n  PROOF the RAW gap is just the served grade wearing a hat:")
    print(f"  {'served quintile':<20}{'n':>6}{'meanServed':>12}{'meanRawGap':>12}{'meanCgap':>10}")
    for i in range(5):
        b = xs[i * q:(i + 1) * q] if i < 4 else xs[4 * q:]
        print(f"  {'Q' + str(i + 1):<20}{len(b):>6}{st.mean(x['served'] for x in b):>12.1f}"
              f"{st.mean(x['gap'] for x in b):>+12.2f}{st.mean(x['cgap'] for x in b):>+10.2f}")

    # ---- zero-information control on the CLEAN set
    print("\n" + "=" * 78)
    print("ZERO-INFORMATION CONTROL, recomputed on the CLEAN set")
    print("=" * 78)
    for pit, res, cuts, nm in ((False, res_h, cuts_h, "HIT"), (True, res_p, cuts_p, "PIT")):
        sub = [r for r in rows if r["pit"] == pit]
        if len(sub) < 50:
            continue
        sds, means = perm_control(res, sub, cuts)
        sds.sort()
        real = st.pstdev([r["cgap"] for r in sub])
        p95 = sds[int(0.95 * len(sds))]
        v = "REAL" if real > p95 else "NULL"
        print(f"  {nm}: centered-gap sd real {real:6.2f}   permuted mean {st.mean(sds):6.2f} "
              f"[p5 {sds[int(0.05 * len(sds))]:.2f}, p95 {p95:.2f}]   -> {v}")
        if v == "NULL":
            print("      a stratum surface with NO information manufactures the same spread")

    # ---- stratum ranking
    print("\n" + "=" * 78)
    print("(b) THE REAL UNIT OF ANALYSIS: strata, ranked by CENTERED offset")
    print("=" * 78)
    print("centered offset = (mean served eFV in the stratum) - (stratum-implied FV),")
    print("minus the board-wide constant. POSITIVE = served high for what it produces.")
    offs, _ = stratum_offsets(rows, {False: res_h, True: res_p},
                              {False: cuts_h, True: cuts_p})
    print(f"\n  {'side':<5}{'stratum':<24}{'nAct':>6}{'servd':>7}{'cOffset':>9}"
          f"{'CI95':>18}  resolvable")
    for o in offs:
        ci = f"[{o['lo']:+.2f},{o['hi']:+.2f}]"
        print(f"  {o['side']:<5}{o['stratum']:<24}{o['n_active']:>6}{o['mean_served']:>7.1f}"
              f"{o['centered_offset']:>+9.2f}{ci:>18}"
              f"  {'YES' if o['resolvable'] else 'no'}")
    pos = [o for o in offs if o["resolvable"] and o["centered_offset"] > 0]
    neg = [o for o in offs if o["resolvable"] and o["centered_offset"] < 0]
    npos = sum(o["n_active"] for o in pos)
    nneg = sum(o["n_active"] for o in neg)
    print(f"\n  strata resolvably OVER-served : {len(pos)} of {len(offs)}  "
          f"covering {npos} live board rows ({npos / max(len(rows), 1):.1%} of the clean board)")
    print(f"  strata resolvably UNDER-served: {len(neg)} of {len(offs)}  "
          f"covering {nneg} live board rows ({nneg / max(len(rows), 1):.1%})")

    # ---- crosstabs on centered gap
    print("\n" + "=" * 78)
    print("(b) CONCENTRATION on the CLEAN, CENTERED gap")
    print("=" * 78)
    for r in rows:
        r["gap"] = r["cgap"]          # crosstab() reads r["gap"]
    ct = []
    ct += crosstab(rows, "level", lambda r: r["stratum"][0])
    ct += crosstab(rows, "age-for-level", lambda r: r["stratum"][1])
    ct += crosstab(rows, "production-for-level", lambda r: r["stratum"][2])
    ct += crosstab(rows, "level x age", lambda r: f"{r['stratum'][0]}/{r['stratum'][1]}", 20)
    ct += crosstab(rows, "side", lambda r: "PIT" if r["pit"] else "HIT")
    ct += crosstab(rows, "position", _posgrp, 25)
    ct += crosstab(rows, "acquisition", _acq, 20)
    ct += crosstab(rows, "n consensus sources", lambda r: f"{int(r['nsrc'] or 0)} src", 20)
    ct += crosstab(rows, "board region",
                   lambda r: ("top100" if (r["slot"] or 9999) <= 100 else
                              "101-300" if (r["slot"] or 9999) <= 300 else
                              "301-1000" if (r["slot"] or 9999) <= 1000 else "1000+"), 20)

    # ---- WITHIN the top of the board: is Bradfield's class special?
    print("\n" + "=" * 78)
    print("IS THE OWNER'S CLASS SPECIAL, OR IS THE WHOLE TOP OF THE BOARD LIKE THIS?")
    print("=" * 78)
    print("Centering on the whole board still leaves the served-grade confound INSIDE the")
    print("top of the board. So re-center on the top 300 only and ask which strata stand out")
    print("among players the board actually promotes.")
    for cutoff in (300, 600):
        top = [r for r in rows if (r["slot"] or 99999) <= cutoff]
        if len(top) < 40:
            continue
        m = st.mean(r["gap"] for r in top)
        by = collections.defaultdict(list)
        for r in top:
            by[("PIT" if r["pit"] else "HIT",) + r["stratum"]].append(r["gap"] - m)
        print(f"\n  TOP {cutoff}: n={len(top)}, mean centered gap {m:+.2f} "
              f"(re-centered to 0 below)")
        print(f"  {'side/stratum':<32}{'n':>5}{'offset':>9}")
        for k, v in sorted(by.items(), key=lambda kv: -st.mean(kv[1])):
            if len(v) < 5:
                continue
            print(f"  {'/'.join(str(x) for x in k):<32}{len(v):>5}{st.mean(v):>+9.2f}")

    # ---- (a) corrected lists
    print("\n" + "=" * 78)
    print("(a) WORST 50 EACH DIRECTION, clean + centered")
    print("=" * 78)
    print("NOTE: every active player inside a stratum shares one implied value, so the")
    print("ordering INSIDE a stratum is just the served ordering. These lists identify")
    print("which board rows sit in mis-served strata; they do not rank individuals.")

    def show(rs, title):
        print(f"\n{title}")
        print(f"  {'#':>3}{'slot':>6} {'player':<26}{'srv':>6}{'imp':>6}{'cgap':>7}"
              f"{'ipwG':>7}{'cons':>6} {'stratum':<22}{'nCell':>6}")
        for i, r in enumerate(rs, 1):
            gi = (r["gap_ipw"] - gm) if r["gap_ipw"] is not None else float("nan")
            co = r["cons"] if r["cons"] is not None else float("nan")
            print(f"  {i:>3}{r['slot'] or 0:>6} {r['key'][:25]:<26}{r['served']:>6.1f}"
                  f"{r['implied']:>6.1f}{r['cgap']:>+7.1f}{gi:>+7.1f}{co:>6.1f} "
                  f"{'/'.join(r['stratum']):<22}{r['ncell']:>6}")

    over = sorted(rows, key=lambda r: -r["cgap"])[:50]
    under = sorted(rows, key=lambda r: r["cgap"])[:50]
    show(over, "OVER-SERVED 50")
    show(under, "UNDER-SERVED 50")

    print("\n  OWNER-FLAGGED NAMES (clean set, centered):")
    order = sorted(rows, key=lambda r: -r["cgap"])
    for r in order:
        if any(f in r["key"] for f in
               ("enrique_bradfield_jr", "franklin_arias", "roch_cholowsky", "sloan")):
            pct = (order.index(r) + 1) / len(order)
            print(f"    {r['key']:<26} slot {r['slot']:>4}  served {r['served']:5.1f}  "
                  f"implied {r['implied']:5.1f}  centered gap {r['cgap']:+6.1f}  "
                  f"(worse than {1 - pct:.1%} of the clean board)  {'/'.join(r['stratum'])}")

    # ---- (c) board cost, clean
    print("\n" + "=" * 78)
    print("(c) BOARD COST, clean set only")
    print("=" * 78)
    off = collections.defaultdict(list)
    for r in rows:
        off[(r["pit"],) + r["stratum"]].append(r["gap"])
    offs2 = {k: st.mean(v) for k, v in off.items()}
    costs = [
        board_cost(served_all, rows, "STRATUM RECENTER, clean set",
                   {r["key"]: r["served"] - offs2[(r["pit"],) + r["stratum"]] for r in rows}),
        board_cost(served_all, rows, "HALF RECENTER, clean set",
                   {r["key"]: r["served"] - 0.5 * offs2[(r["pit"],) + r["stratum"]]
                    for r in rows}),
        board_cost(served_all, rows, "RESOLVABLE STRATA ONLY (CI95 excludes 0)",
                   {r["key"]: r["served"] - offs2[(r["pit"],) + r["stratum"]] for r in rows
                    if any(o["stratum"] == "/".join(r["stratum"])
                           and o["side"] == ("PIT" if r["pit"] else "HIT") and o["resolvable"]
                           for o in offs)}),
    ]

    (DATA / "xfv_generality2_eval.json").write_text(json.dumps({
        "n_stratifiable": n0, "n_cpx": len(cpx), "n_floor": len(floor),
        "n_clean": len(rows), "board_mean_raw_gap": round(gm, 3),
        "stratum_offsets": [{k: (round(v, 3) if isinstance(v, float) else v)
                             for k, v in o.items()} for o in offs],
        "n_over_served_strata": len(pos), "n_rows_over_served_strata": npos,
        "n_under_served_strata": len(neg), "n_rows_under_served_strata": nneg,
        "crosstabs": ct, "board_costs": costs,
        "over50": [{"key": r["key"], "slot": r["slot"], "served": round(r["served"], 2),
                    "implied": round(r["implied"], 2), "cgap": round(r["cgap"], 2),
                    "stratum": "/".join(r["stratum"])} for r in over],
        "under50": [{"key": r["key"], "slot": r["slot"], "served": round(r["served"], 2),
                     "implied": round(r["implied"], 2), "cgap": round(r["cgap"], 2),
                     "stratum": "/".join(r["stratum"])} for r in under],
    }, indent=1), encoding="utf-8")
    print("\nwrote data/xfv_generality2_eval.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
