# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""GENERALITY LANE. How big is the class of players the board mis-serves the way it
mis-serves Enrique Bradfield Jr?

The owner has flagged four names (Arias, Sloan, Cholowsky, Bradfield). A per-name patch is
worthless if the defect is systematic, and a systematic rewrite is worthless if it is four
names. This lab scores EVERY active board row against the realized outcome of its own
historical stratum (level x age-for-level x production-for-level), ranks the disagreements
in BOTH directions, cross-tabulates where they concentrate, and prices the board-level cost
of regrading everything.

METHOD. Stratum-implied grade = value_framework.realized_implied_fv() of the stratum's
shrunk mean realized 6-year WAR. That is the same inversion the shipped model's own
valuation config uses, so the units are the model's units, not invented ones.

CONTROLS (docs/EFV_GATE_STANDARD.md section 2):
  * paired bootstrap over RESOLVED players, recomputing every stratum mean per draw, so
    each active row's gap carries a CI and we can separate resolvable gaps from noise;
  * a zero-information control: the stratum LABEL row-permuted among resolved players
    (identical cell-size marginal, no information), which tells us how much apparent
    mis-grading a stratum surface manufactures from nothing;
  * a permutation null band on the headline concentration statistics.

SURVIVORSHIP (part d) is measured FIRST and gates the reading of everything else, because
the stratum surface can only be built on resolved players who have a MiLB track record, and
whether a bust keeps a MiLB track record is not independent of busting.

Read-only. Writes one eval artifact under data/.
"""
from __future__ import annotations

import collections
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

import value_framework as vf  # noqa: E402

SEED = 20260725
random.seed(SEED)

SHRINK_K = 15.0          # pseudocount toward the level mean, in players
BOOT = 1000
EXPOSURE = 6             # realized_war_6yr is a 6-season total


# ---------------------------------------------------------------- helpers

_IMP_CACHE: dict = {}


def implied_fv(war6: float, is_pitcher: bool) -> float:
    """Stratum mean 6yr WAR -> FV, via the shipped inversion.

    Memoized on WAR rounded to 0.005, which is 3 orders of magnitude finer than any
    stratum mean's bootstrap sd; realized_implied_fv() runs a 40-step bisection and is the
    whole cost of the paired bootstrap."""
    k = (round(war6 * 200.0), is_pitcher)
    v = _IMP_CACHE.get(k)
    if v is None:
        r = vf.realized_implied_fv(k[0] / 200.0, is_pitcher, exposure_seasons=EXPOSURE)
        v = _IMP_CACHE[k] = (float(r) if r is not None else 20.0)
    return v


def implied_fv_leadmethod(war6: float) -> float:
    """The lead's inversion (config fv_to_6yr_avg_war on the ANNUAL mean), kept for
    continuity with the numbers already reported. Degenerate below FV 45."""
    ann = war6 / float(EXPOSURE)
    grid = [(fv, vf.fv_to_6yr_avg_war(fv)) for fv in range(20, 81)]
    grid = [(fv, w) for fv, w in grid if w is not None]
    for fv, w in grid:
        if ann <= w:
            return float(fv)
    return 80.0


def cohort_year(m: dict):
    v = m.get("cutoff")
    try:
        return int(str(v)[:4])
    except Exception:
        return None


LEVEL_GROUP = {
    "AAA": "AAA", "AA": "AA", "A+": "A+", "HIA": "A+",
    "A": "A", "LOA": "A", "A-": "A", "SS": "A",
    "ROK": "CPX", "R": "CPX", "CPX": "CPX", "DSL": "CPX", "FCL": "CPX", "ACL": "CPX",
}


def level_of(mb: dict):
    lv = mb.get("milb_level")
    if not lv:
        return None
    return LEVEL_GROUP.get(str(lv).upper(), str(lv).upper())


def bucket(v, edges, names):
    for e, n in zip(edges, names):
        if v < e:
            return n
    return names[-1]


# ---------------------------------------------------------------- load

def load_side(is_pitcher: bool):
    """-> (resolved rows, active rows). Each row: key, side, level, age, prod, war/grade."""
    if is_pitcher:
        scored = json.loads((DATA / "xfv_scored_pitcher.json").read_text(encoding="utf-8"))
        mat = json.loads((DATA / "xfv_pitcher_matrix.json").read_text(encoding="utf-8"))
        live = json.loads((DATA / "xfv_live_pitcher_matrix.json").read_text(encoding="utf-8"))
    else:
        scored = json.loads((DATA / "xfv_scored.json").read_text(encoding="utf-8"))
        mat = json.loads((DATA / "xfv_hitter_matrix.json").read_text(encoding="utf-8"))
        live = json.loads((DATA / "xfv_live_hitter_matrix.json").read_text(encoding="utf-8"))
    sc = {r["player_key"]: r for r in scored}

    def feat(m):
        mb = m.get("milb") if isinstance(m.get("milb"), dict) else {}
        lv = level_of(mb)
        age = mb.get("age")
        prod = mb.get("era_rel") if is_pitcher else mb.get("ops_rel")
        if is_pitcher and prod is not None:
            prod = -float(prod)          # lower ERA is better; flip so higher = better
        return mb, lv, age, prod

    resolved = []
    for m in mat:
        s = sc.get(m["player_key"])
        if not s:
            continue
        y = s.get("realized_war_6yr")
        if not isinstance(y, (int, float)):
            continue
        mb, lv, age, prod = feat(m)
        resolved.append({
            "key": m["player_key"], "pit": is_pitcher, "kind": s.get("kind"),
            "y": float(y), "lv": lv, "age": age, "prod": prod,
            "cohort": cohort_year(m), "has_milb": bool(lv),
            "cons": s.get("consensus_fv"), "grade": s.get("xfv_grade"),
            "censored": bool(m.get("censored")),
            "pos": m.get("position"), "is_ifa": m.get("is_ifa"),
            "is_college": m.get("is_college"), "pick": m.get("pick_overall"),
            "nsrc": m.get("n_sources"),
        })

    active = []
    for m in live:
        if m.get("kind") != "active":
            continue
        mb, lv, age, prod = feat(m)
        active.append({
            "key": m["player_key"], "pit": is_pitcher, "lv": lv, "age": age, "prod": prod,
            "age_now": m.get("age_now"), "pos": m.get("position"),
            "is_ifa": m.get("is_ifa"), "is_college": m.get("is_college"),
            "pick": m.get("pick_overall"), "nsrc": m.get("n_sources"),
            "age_rel_level": mb.get("age_rel_level"),
            "n_milb_seasons": mb.get("n_milb_seasons"),
        })
    return resolved, active


# ---------------------------------------------------------------- strata

def build_cuts(resolved):
    """Within-level tercile cuts for age and production, from the RESOLVED pool."""
    cuts = {}
    bylv = collections.defaultdict(list)
    for r in resolved:
        if r["lv"] and r["age"] is not None and r["prod"] is not None:
            bylv[r["lv"]].append(r)
    for lv, rows in bylv.items():
        ages = sorted(x["age"] for x in rows)
        prods = sorted(x["prod"] for x in rows)
        if len(rows) < 12:
            continue

        def q(v, p):
            return v[max(0, min(len(v) - 1, int(p * len(v))))]
        cuts[lv] = {
            "age": (q(ages, 1 / 3), q(ages, 2 / 3)),
            "prod": (q(prods, 1 / 3), q(prods, 2 / 3)),
            "n": len(rows),
        }
    return cuts


def stratum(row, cuts):
    lv = row["lv"]
    if not lv or lv not in cuts or row["age"] is None or row["prod"] is None:
        return None
    ca, cp = cuts[lv]["age"], cuts[lv]["prod"]
    a = bucket(row["age"], ca, ["young", "onTime", "old"])
    p = bucket(row["prod"], cp, ["lowProd", "midProd", "highProd"])
    return (lv, a, p)


def stratum_means(resolved, cuts, weights=None, keys=None):
    """-> {stratum: shrunk mean 6yr WAR}, {level: mean}, {stratum: n}."""
    cells = collections.defaultdict(lambda: [0.0, 0.0])   # sumw*y, sumw
    lvl = collections.defaultdict(lambda: [0.0, 0.0])
    n = collections.Counter()
    src = resolved if keys is None else keys
    for r in src:
        s = stratum(r, cuts)
        if s is None:
            continue
        w = 1.0 if weights is None else float(weights.get(r["key"], 1.0))
        cells[s][0] += w * r["y"]
        cells[s][1] += w
        lvl[s[0]][0] += w * r["y"]
        lvl[s[0]][1] += w
        n[s] += 1
    lvmean = {k: (v[0] / v[1] if v[1] else 0.0) for k, v in lvl.items()}
    out = {}
    for s, (sy, sw) in cells.items():
        m = sy / sw if sw else 0.0
        base = lvmean.get(s[0], 0.0)
        out[s] = (sw * m + SHRINK_K * base) / (sw + SHRINK_K)
    return out, lvmean, n


# ---------------------------------------------------------------- part (d)

def survivorship(resolved_h, resolved_p):
    print("=" * 78)
    print("(d) SURVIVORSHIP CHECK on the surface every other number here rests on")
    print("=" * 78)
    print("A stratum can only be built from players who HAVE a MiLB track record.")
    print("If busts keep that record at a different rate than debuts, the stratum-mean")
    print("realized WAR is biased and every implied grade below inherits the bias.\n")
    out = {}
    for name, res in (("HITTERS", resolved_h), ("PITCHERS", resolved_p)):
        c = collections.Counter((r["kind"], r["has_milb"]) for r in res)
        bT, bF = c[("bust", True)], c[("bust", False)]
        dT, dF = c[("debuted", True)], c[("debuted", False)]
        rb = bT / max(bT + bF, 1)
        rd = dT / max(dT + dF, 1)
        share_all = (bT + bF) / max(bT + bF + dT + dF, 1)
        share_h = bT / max(bT + dT, 1)
        print(f"{name}: bust retention {rb:.3f} ({bT}/{bT + bF})   "
              f"debut retention {rd:.3f} ({dT}/{dT + dF})")
        print(f"  bust share of the RESOLVED pool {share_all:.3f}  ->  "
              f"of the HAS-MiLB pool {share_h:.3f}   "
              f"(busts under-represented by {share_all - share_h:+.3f})")
        out[name] = {"bust_retention": round(rb, 4), "debut_retention": round(rd, 4),
                     "bust_share_resolved": round(share_all, 4),
                     "bust_share_has_milb": round(share_h, 4)}
        byyr = collections.defaultdict(collections.Counter)
        for r in res:
            byyr[r["cohort"]][(r["kind"], r["has_milb"])] += 1
        rows = []
        for y in sorted(k for k in byyr if k):
            cc = byyr[y]
            b1, b0 = cc[("bust", True)], cc[("bust", False)]
            d1, d0 = cc[("debuted", True)], cc[("debuted", False)]
            if b1 + b0 + d1 + d0 < 15:
                continue
            rows.append((y, b1 / max(b1 + b0, 1), b1 + b0,
                         d1 / max(d1 + d0, 1), d1 + d0,
                         (b1 + b0) / max(b1 + b0 + d1 + d0, 1),
                         b1 / max(b1 + d1, 1)))
        print("   cohort  bustRetain(n)     debutRetain(n)    trueBustShare -> observed")
        for y, rb_, nb, rd_, nd, sa, sh in rows:
            flag = "  <== UNUSABLE" if rb_ < 0.35 else ""
            print(f"   {y}    {rb_:.3f} ({nb:4d})     {rd_:.3f} ({nd:4d})     "
                  f"{sa:.3f} -> {sh:.3f}{flag}")
        out[name]["by_cohort"] = [
            {"cohort": y, "bust_retention": round(rb_, 4), "n_bust": nb,
             "debut_retention": round(rd_, 4), "n_debut": nd,
             "true_bust_share": round(sa, 4), "observed_bust_share": round(sh, 4)}
            for y, rb_, nb, rd_, nd, sa, sh in rows]
        cen = collections.Counter(r["censored"] for r in res if r["has_milb"])
        print(f"   censored 6yr windows inside the has-MiLB pool: "
              f"{cen[True]}/{cen[True] + cen[False]} = "
              f"{cen[True] / max(cen[True] + cen[False], 1):.3f}\n")
        out[name]["censored_rate_has_milb"] = round(
            cen[True] / max(cen[True] + cen[False], 1), 4)
    return out


def ipw_weights(resolved):
    """Inverse-probability weights restoring each cohort's TRUE bust:debut mix inside the
    has-MiLB pool. Corrects the dominant, measured selection; does not claim to fix
    within-kind selection."""
    byyr = collections.defaultdict(collections.Counter)
    for r in resolved:
        byyr[r["cohort"]][(r["kind"], r["has_milb"])] += 1
    w = {}
    for r in resolved:
        if not r["has_milb"]:
            continue
        c = byyr[r["cohort"]]
        t = c[(r["kind"], True)] + c[(r["kind"], False)]
        keep = c[(r["kind"], True)]
        w[r["key"]] = (t / keep) if keep else 0.0
    return w


# ---------------------------------------------------------------- scoring

def score_board(active, cells, served, cuts):
    """Attach stratum-implied grade + gap to every active row we can stratify."""
    out = []
    for a in active:
        s = stratum(a, cuts)
        if s is None:
            continue
        g = served.get(a["key"])
        if not isinstance(g, (int, float)):
            continue
        mu = cells.get(s)
        if mu is None:
            continue
        imp = implied_fv(mu, a["pit"])
        r = dict(a)
        r["stratum"] = s
        r["stratum_war"] = mu
        r["implied"] = imp
        r["served"] = float(g)
        r["gap"] = float(g) - imp
        out.append(r)
    return out


def bootstrap_gaps(resolved, active, served, cuts, B=BOOT, weights=None):
    """Paired bootstrap over RESOLVED players; recompute every stratum mean per draw and
    re-derive each active row's gap. -> {key: (lo, hi)} CI95 on the gap."""
    pool = [(stratum(r, cuts), r["y"], 1.0 if weights is None else float(weights.get(r["key"], 1.0)))
            for r in resolved if r["has_milb"]]
    pool = [p for p in pool if p[0] is not None]
    n = len(pool)
    # active rows collapse to (stratum, served, side); score each DISTINCT stratum once per
    # draw instead of once per player.
    need = {}
    for a in active:
        need.setdefault((a["stratum"], a["pit"]), []).append(a)
    draws = collections.defaultdict(list)
    rr = random.randrange
    for _ in range(B):
        cells = collections.defaultdict(lambda: [0.0, 0.0])
        lvl = collections.defaultdict(lambda: [0.0, 0.0])
        for _i in range(n):
            s, y, w = pool[rr(n)]
            c = cells[s]
            c[0] += w * y
            c[1] += w
            L = lvl[s[0]]
            L[0] += w * y
            L[1] += w
        lvmean = {k: (v[0] / v[1] if v[1] else 0.0) for k, v in lvl.items()}
        for (s, pit), rows in need.items():
            c = cells.get(s)
            if c is None:
                continue
            m = c[0] / c[1] if c[1] else 0.0
            mu = (c[1] * m + SHRINK_K * lvmean.get(s[0], 0.0)) / (c[1] + SHRINK_K)
            imp = implied_fv(mu, pit)
            for a in rows:
                draws[a["key"]].append(a["served"] - imp)
    ci = {}
    for k, v in draws.items():
        if len(v) < B * 0.5:
            continue
        v.sort()
        ci[k] = (v[int(0.025 * len(v))], v[int(0.975 * len(v))])
    return ci


def permuted_control(resolved, active, served, cuts, B=200, weights=None):
    """ZERO-INFORMATION CONTROL. Row-permute the stratum LABEL among resolved players:
    identical cell-size marginal, no relationship to outcome. How much |gap| spread does a
    stratum surface manufacture from nothing?"""
    pool = [r for r in resolved if stratum(r, cuts) is not None]
    labels = [stratum(r, cuts) for r in pool]
    spreads, meangaps = [], []
    for _ in range(B):
        perm = labels[:]
        random.shuffle(perm)
        cells = collections.defaultdict(lambda: [0.0, 0.0])
        lvl = collections.defaultdict(lambda: [0.0, 0.0])
        for r, s in zip(pool, perm):
            w = 1.0 if weights is None else float(weights.get(r["key"], 1.0))
            cells[s][0] += w * r["y"]
            cells[s][1] += w
            lvl[s[0]][0] += w * r["y"]
            lvl[s[0]][1] += w
        lvmean = {k: (v[0] / v[1] if v[1] else 0.0) for k, v in lvl.items()}
        mu = {}
        for s, (sy, sw) in cells.items():
            m = sy / sw if sw else 0.0
            mu[s] = (sw * m + SHRINK_K * lvmean.get(s[0], 0.0)) / (sw + SHRINK_K)
        gaps = []
        for a in active:
            v = mu.get(a["stratum"])
            if v is None:
                continue
            gaps.append(a["served"] - implied_fv(v, a["pit"]))
        if len(gaps) > 30:
            spreads.append(st.pstdev(gaps))
            meangaps.append(st.mean(gaps))
    return spreads, meangaps


# ---------------------------------------------------------------- (b) crosstabs

def _acq(a):
    if (a.get("is_ifa") or 0) >= 1:
        return "IFA"
    if (a.get("is_college") or 0) >= 1:
        return "college"
    if a.get("pick") is not None:
        return "HS/draft"
    return "unknown"


def _posgrp(a):
    p = (a.get("pos") or "").upper()
    if not p:
        return "?"
    head = p.split("/")[0]
    if head in ("SP", "RP", "P", "LHP", "RHP"):
        return head
    if head in ("C",):
        return "C"
    if head in ("SS", "2B", "3B", "1B", "IF", "DH"):
        return head
    if head in ("CF", "LF", "RF", "OF"):
        return head
    return head


def crosstab(rows, dim, fn, minn=15):
    agg = collections.defaultdict(list)
    for r in rows:
        agg[fn(r)].append(r["gap"])
    out = []
    for k, v in agg.items():
        if len(v) < minn:
            continue
        over = sum(1 for g in v if g > 0)
        out.append((k, len(v), st.mean(v), st.median(v), over / len(v),
                    sum(1 for g in v if g >= 10) / len(v)))
    out.sort(key=lambda t: -t[2])
    print(f"\n  {dim:<22}{'n':>6}{'meanGap':>10}{'medGap':>9}{'%over':>8}{'%gap>=10':>10}")
    for k, n, mu, md, po, p10 in out:
        print(f"  {str(k):<22}{n:>6}{mu:>+10.2f}{md:>+9.2f}{po:>8.1%}{p10:>10.1%}")
    return [{"dim": dim, "value": str(k), "n": n, "mean_gap": round(mu, 3),
             "median_gap": round(md, 3), "frac_over": round(po, 4),
             "frac_gap_ge_10": round(p10, 4)} for k, n, mu, md, po, p10 in out]


# ---------------------------------------------------------------- (c) board cost

def rank_map(pairs):
    """pairs: [(key, value)] -> {key: rank} descending by value."""
    s = sorted(pairs, key=lambda t: (-t[1], t[0]))
    return {k: i for i, (k, _v) in enumerate(s, 1)}


def board_cost(served_all, scored_rows, label, regrade):
    """served_all: {key: served grade} for EVERY active row (the real board).
    regrade: {key: new grade} for the subset we can stratify. Rows we cannot stratify keep
    their served grade, which is the honest counterfactual: a fix only touches what it can
    see."""
    base = rank_map(list(served_all.items()))
    new_vals = dict(served_all)
    new_vals.update(regrade)
    new = rank_map(list(new_vals.items()))
    common = [k for k in base if k in new]
    moves = [abs(base[k] - new[k]) for k in common]
    t100_before = {k for k in common if base[k] <= 100}
    t100_after = {k for k in common if new[k] <= 100}
    changed = t100_before ^ t100_after
    t100_moves = [abs(base[k] - new[k]) for k in t100_before]
    print(f"\n  [{label}]  regraded rows {len(regrade)} of {len(served_all)} board rows")
    print(f"    median |rank move| ALL rows        {st.median(moves):8.1f}")
    print(f"    mean   |rank move| ALL rows        {st.mean(moves):8.1f}")
    print(f"    median |rank move| current top-100 {st.median(t100_moves):8.1f}")
    print(f"    top-100 slots changing occupant    {len(changed) // 2:8d} "
          f"of 100  ({len(t100_before - t100_after)} drop out, "
          f"{len(t100_after - t100_before)} come in)")
    drops = sorted(t100_before - t100_after, key=lambda k: base[k])
    adds = sorted(t100_after - t100_before, key=lambda k: new[k])
    print(f"    DROP OUT (first 15): "
          + ", ".join(f"{k}#{base[k]}->{new[k]}" for k in drops[:15]))
    print(f"    COME IN  (first 15): "
          + ", ".join(f"{k}#{base[k]}->{new[k]}" for k in adds[:15]))
    return {"label": label, "n_regraded": len(regrade), "n_board": len(served_all),
            "median_abs_rank_move": round(st.median(moves), 2),
            "mean_abs_rank_move": round(st.mean(moves), 2),
            "median_abs_rank_move_top100": round(st.median(t100_moves), 2),
            "top100_slots_changed": len(changed) // 2,
            "top100_drop_out": [{"key": k, "from": base[k], "to": new[k]} for k in drops[:40]],
            "top100_come_in": [{"key": k, "from": base[k], "to": new[k]} for k in adds[:40]]}


# ---------------------------------------------------------------- main

def main() -> int:
    xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    served_all = {k: v["xfv_grade"] for k, v in xfv.items()
                  if v.get("kind") == "active" and isinstance(v.get("xfv_grade"), (int, float))}
    cons_all = {k: v.get("consensus_fv") for k, v in xfv.items()}
    print(f"BOARD: {len(served_all)} active rows served on xfv_grade "
          f"(build_site line 759: the DISPLAYED eFV site-wide as of 2026-07-25).")
    bslot = rank_map(list(served_all.items()))
    print(f"  sanity: enrique_bradfield_jr served {served_all['enrique_bradfield_jr']:.2f}, "
          f"board slot {bslot['enrique_bradfield_jr']}\n")

    res_h, act_h = load_side(False)
    res_p, act_p = load_side(True)
    surv = survivorship(res_h, res_p)

    report = {"survivorship": surv, "board_rows": len(served_all)}
    all_scored = []
    per_side = {}

    for side, res, act in (("HIT", res_h, act_h), ("PIT", res_p, act_p)):
        print("=" * 78)
        print(f"STRATUM SURFACE: {side}")
        print("=" * 78)
        cuts = build_cuts(res)
        for lv in sorted(cuts):
            c = cuts[lv]
            print(f"  {lv:<4} n={c['n']:<5} age terciles {c['age'][0]:.1f}/{c['age'][1]:.1f}"
                  f"   prod terciles {c['prod'][0]:+.3f}/{c['prod'][1]:+.3f}")
        w = ipw_weights(res)
        cells_raw, lvm, ncell = stratum_means(res, cuts)
        cells_ipw, _l2, _n2 = stratum_means(res, cuts, weights=w)
        recent = [r for r in res if (r["cohort"] or 0) >= 2021]
        cells_rec, _l3, nrec = stratum_means(recent, cuts, keys=recent)

        print(f"\n  {'stratum':<24}{'n':>5}{'meanWAR':>9}{'impFV':>7}"
              f"{'impFV_ipw':>11}{'impFV_2021+':>12}{'lead_inv':>10}")
        for s in sorted(cells_raw, key=lambda s: (s[0], s[1], s[2])):
            if ncell[s] < 8:
                continue
            ip = implied_fv(cells_raw[s], side == "PIT")
            iw = implied_fv(cells_ipw.get(s, cells_raw[s]), side == "PIT")
            ir = implied_fv(cells_rec[s], side == "PIT") if s in cells_rec else float("nan")
            print(f"  {'/'.join(s):<24}{ncell[s]:>5}{cells_raw[s]:>9.2f}{ip:>7.1f}"
                  f"{iw:>11.1f}{ir:>12.1f}"
                  f"{implied_fv_leadmethod(cells_raw[s]):>10.1f}")

        scored = score_board(act, cells_raw, served_all, cuts)
        scored_ipw = {r["key"]: r for r in score_board(act, cells_ipw, served_all, cuts)}
        for r in scored:
            o = scored_ipw.get(r["key"])
            r["implied_ipw"] = o["implied"] if o else None
            r["gap_ipw"] = o["gap"] if o else None
            r["cons"] = cons_all.get(r["key"])
            r["slot"] = bslot.get(r["key"])
        print(f"\n  stratifiable active {side} rows: {len(scored)} of {len(act)} "
              f"({len(scored) / max(len(act), 1):.1%})")

        ci = bootstrap_gaps(res, scored, served_all, cuts)
        nres = sum(1 for r in scored if r["key"] in ci
                   and (ci[r["key"]][0] > 0 or ci[r["key"]][1] < 0))
        print(f"  gaps whose paired-bootstrap CI95 excludes zero: {nres} "
              f"({nres / max(len(scored), 1):.1%})")
        for r in scored:
            r["ci"] = ci.get(r["key"])

        spreads, meangaps = permuted_control(res, scored, served_all, cuts)
        real_sd = st.pstdev([r["gap"] for r in scored])
        real_mu = st.mean([r["gap"] for r in scored])
        spreads.sort()
        print(f"\n  ZERO-INFORMATION CONTROL (stratum label row-permuted, B={len(spreads)}):")
        print(f"    real   |gap| sd {real_sd:6.2f}   mean gap {real_mu:+6.2f}")
        print(f"    permuted   sd  {st.mean(spreads):6.2f} "
              f"[p5 {spreads[int(0.05 * len(spreads))]:.2f}, "
              f"p95 {spreads[int(0.95 * len(spreads))]:.2f}]   "
              f"mean gap {st.mean(meangaps):+6.2f}")
        verdict = ("REAL: the stratum surface carries information the permuted twin does not"
                   if real_sd > spreads[int(0.95 * len(spreads))] else
                   "NULL: a zero-information stratum surface manufactures the same spread")
        print(f"    -> {verdict}")

        per_side[side] = {
            "n_active_stratifiable": len(scored), "n_active": len(act),
            "gap_sd": round(real_sd, 3), "gap_mean": round(real_mu, 3),
            "perm_sd_mean": round(st.mean(spreads), 3),
            "perm_sd_p95": round(spreads[int(0.95 * len(spreads))], 3),
            "perm_verdict": verdict,
            "n_gap_ci_excludes_zero": nres,
            "cuts": {lv: {"age": list(c["age"]), "prod": list(c["prod"]), "n": c["n"]}
                     for lv, c in cuts.items()},
            "strata": [{"stratum": "/".join(s), "n": ncell[s],
                        "mean_war6": round(cells_raw[s], 3),
                        "implied_fv": round(implied_fv(cells_raw[s], side == "PIT"), 2),
                        "implied_fv_ipw": round(implied_fv(cells_ipw.get(s, cells_raw[s]),
                                                           side == "PIT"), 2),
                        "implied_fv_2021plus": (round(implied_fv(cells_rec[s], side == "PIT"), 2)
                                                if s in cells_rec else None)}
                       for s in sorted(cells_raw) if ncell[s] >= 8],
        }
        all_scored.extend(scored)

    # ---------------- (a) the two lists
    print("\n" + "=" * 78)
    print("(a) WORST 50 EACH DIRECTION  |served eFV - stratum-implied FV|")
    print("=" * 78)

    def show(rows, title):
        print(f"\n{title}")
        print(f"  {'#':>3} {'slot':>5} {'player':<26}{'srv':>6}{'imp':>6}{'gap':>7}"
              f"{'ipw':>6}{'cons':>6} {'stratum':<22}{'CI95 gap':>18}")
        for i, r in enumerate(rows, 1):
            ci = r.get("ci")
            cis = f"[{ci[0]:+.1f},{ci[1]:+.1f}]" if ci else "n/a"
            res = "*" if ci and (ci[0] > 0 or ci[1] < 0) else " "
            gi = r["gap_ipw"] if r["gap_ipw"] is not None else float("nan")
            co = r["cons"] if r["cons"] is not None else float("nan")
            print(f"  {i:>3} {r['slot'] or 0:>5} {r['key'][:25]:<26}{r['served']:>6.1f}"
                  f"{r['implied']:>6.1f}{r['gap']:>+7.1f}{gi:>+6.1f}{co:>6.1f} "
                  f"{'/'.join(r['stratum']):<22}{cis:>17}{res}")

    over = sorted(all_scored, key=lambda r: -r["gap"])[:50]
    under = sorted(all_scored, key=lambda r: r["gap"])[:50]
    show(over, "OVER-GRADED 50 (served far ABOVE what the stratum historically produced)")
    show(under, "UNDER-GRADED 50 (served far BELOW what the stratum historically produced)")
    print("\n  * = paired-bootstrap CI95 on the gap excludes zero")

    flagged = ["enrique_bradfield_jr", "franklin_arias", "roch_cholowsky", "sloan"]
    ordered = sorted(all_scored, key=lambda x: -x["gap"])
    print("\n  OWNER-FLAGGED NAMES:")
    for r in ordered:
        if any(f in r["key"] for f in flagged):
            rk = ordered.index(r) + 1
            print(f"    {r['key']:<28} slot {r['slot']:>4}  served {r['served']:.1f}  "
                  f"implied {r['implied']:.1f}  gap {r['gap']:+.1f}  "
                  f"ipw {r['gap_ipw']:+.1f}  stratum {'/'.join(r['stratum'])}  "
                  f"over-rank {rk}/{len(all_scored)}")

    # ---------------- (b) concentration
    print("\n" + "=" * 78)
    print("(b) WHERE IS IT CONCENTRATED?")
    print("=" * 78)
    ct = []
    ct += crosstab(all_scored, "level", lambda r: r["stratum"][0])
    ct += crosstab(all_scored, "age-for-level", lambda r: r["stratum"][1])
    ct += crosstab(all_scored, "production-for-level", lambda r: r["stratum"][2])
    ct += crosstab(all_scored, "level x age", lambda r: f"{r['stratum'][0]}/{r['stratum'][1]}",
                   minn=20)
    ct += crosstab(all_scored, "side", lambda r: "PIT" if r["pit"] else "HIT")
    ct += crosstab(all_scored, "position", _posgrp, minn=25)
    ct += crosstab(all_scored, "acquisition", _acq, minn=20)
    ct += crosstab(all_scored, "n consensus sources",
                   lambda r: f"{int(r['nsrc'] or 0)} src", minn=20)
    ct += crosstab(all_scored, "board region",
                   lambda r: ("top100" if (r["slot"] or 9999) <= 100 else
                              "101-300" if (r["slot"] or 9999) <= 300 else
                              "301-1000" if (r["slot"] or 9999) <= 1000 else "1000+"),
                   minn=20)

    # ---------------- (c) board cost
    print("\n" + "=" * 78)
    print("(c) BOARD-LEVEL COST OF REGRADING")
    print("=" * 78)
    print("Two counterfactuals. FULL REPLACEMENT is the upper bound and is not a proposal;")
    print("STRATUM RECENTER is what a real fix looks like (a per-stratum offset that leaves")
    print("the ordering inside a stratum alone).")
    costs = []
    costs.append(board_cost(served_all, all_scored, "FULL REPLACEMENT served -> implied",
                            {r["key"]: r["implied"] for r in all_scored}))
    off = collections.defaultdict(list)
    for r in all_scored:
        off[(r["pit"],) + r["stratum"]].append(r["gap"])
    offs = {k: st.mean(v) for k, v in off.items()}
    costs.append(board_cost(served_all, all_scored, "STRATUM RECENTER (offset only)",
                            {r["key"]: r["served"] - offs[(r["pit"],) + r["stratum"]]
                             for r in all_scored}))
    costs.append(board_cost(served_all, all_scored, "HALF RECENTER (50% shrunk offset)",
                            {r["key"]: r["served"] - 0.5 * offs[(r["pit"],) + r["stratum"]]
                             for r in all_scored}))
    old = {r["key"] for r in all_scored if r["stratum"][1] == "old"}
    costs.append(board_cost(served_all, all_scored,
                            "OLD-FOR-LEVEL ONLY recenter (the narrow fix)",
                            {r["key"]: r["served"] - offs[(r["pit"],) + r["stratum"]]
                             for r in all_scored if r["key"] in old}))

    report["per_side"] = per_side
    report["crosstabs"] = ct
    report["board_costs"] = costs

    def pack(rows):
        return [{"key": r["key"], "slot": r["slot"], "served": round(r["served"], 2),
                 "implied": round(r["implied"], 2), "gap": round(r["gap"], 2),
                 "gap_ipw": (round(r["gap_ipw"], 2) if r["gap_ipw"] is not None else None),
                 "consensus": r["cons"], "stratum": "/".join(r["stratum"]),
                 "ci95": [round(x, 2) for x in r["ci"]] if r.get("ci") else None}
                for r in rows]
    report["worst_over_50"] = pack(over)
    report["worst_under_50"] = pack(under)
    (DATA / "xfv_generality_eval.json").write_text(
        json.dumps(report, indent=1), encoding="utf-8")
    print("\nwrote data/xfv_generality_eval.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
