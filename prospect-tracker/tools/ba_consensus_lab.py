# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Lane BA1 lab: should Baseball America vote in the consensus, and what does
its selection bias do to consensus_fv_raw (the dominant eFV feature)?

Pre-registration: docs/efv-2026-08-07b/BA_SOURCE_GATE.md (written first).
Artifact:         data/ba_consensus_eval.json

Writes NOTHING except its own artifact. Reads prospects.db, data/timeseries.json,
data/debuts.json and the two shipped xfv matrices read-only.

Run:  python tools/ba_consensus_lab.py
"""
from __future__ import annotations

import io
import json
import math
import random
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import consensus as C                     # noqa: E402
import grade_normalization as GN          # noqa: E402
import source_backtest as SB              # noqa: E402
import storage                            # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "ba_consensus_eval.json"

BA = "baseballamerica"
N_SEEDS = 24
AS_OF_YEAR = 2026


def _jload(p):
    return json.load(io.open(str(p), encoding="utf-8"))


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _sd(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _pct(sorted_xs, q):
    if not sorted_xs:
        return None
    i = min(len(sorted_xs) - 1, max(0, int(round(q * (len(sorted_xs) - 1)))))
    return sorted_xs[i]


def _pearson(x, y):
    n = len(x)
    if n < 4:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _boot_ci(pairs, stat, seeds=2000, seed=17):
    """Paired bootstrap CI95 of stat(sample) over a list of records."""
    if not pairs:
        return None, None
    rnd = random.Random(seed)
    n = len(pairs)
    vals = []
    for _ in range(seeds):
        s = [pairs[rnd.randrange(n)] for _ in range(n)]
        v = stat(s)
        if v is not None:
            vals.append(v)
    if len(vals) < 50:
        return None, None
    vals.sort()
    return _pct(vals, 0.025), _pct(vals, 0.975)


# ---------------------------------------------------------------------------
# STEP 1: normalization cells + the era scale break
# ---------------------------------------------------------------------------
def step1_normalization(snaps):
    cells = []
    years = sorted({int(s.snapshot_date[:4]) for s in snaps if s.source == BA})
    roles = ("hitter", "pitcher")
    # role census of BA rows, so a cell's n is readable against its supply
    supply = defaultdict(int)
    for s in snaps:
        if s.source != BA or s.fv is None:
            continue
        supply[(GN._is_pitcher(s.position) and "pitcher" or "hitter",
                int(s.snapshot_date[:4]))] += 1

    remapper_probe = {}
    # Rebuild the exact table build_remapper would construct, by calling the
    # same private pieces (read-only).
    for role in roles:
        for yr in years:
            own = GN._pairs(BA, role, yr)
            src, ref, pooled = GN._paired_dists(BA, role, yr)
            in_table = bool(len(src) > 0 and len(ref) > 0
                            and GN._mappable(src, ref) and len(src) >= GN._MIN_N)
            offset = (float(sum(src) / len(src) - sum(ref) / len(ref))
                      if len(src) and len(ref) else None)
            cells.append({
                "source": BA, "role": role, "year": yr,
                "ba_rows_with_fv": supply.get((role, yr), 0),
                "paired_n_own_year": len(own),
                "min_n": GN._MIN_N,
                "meets_min_n_own_year": len(own) >= GN._MIN_N,
                "pooled_across_years": bool(pooled),
                "paired_n_used": int(len(src)),
                "fitted_offset_fv": round(offset, 3) if offset is not None else None,
                "in_build_remapper_table": bool(in_table),
                "drift": GN.drift_row(BA, role, yr),
            })
    # what the LIVE remapper actually does to a probe grade in each cell
    remap = GN.build_remapper(aliases=C.SOURCE_ALIASES)
    for role in roles:
        pos = "RHP" if role == "pitcher" else "OF"
        for yr in years:
            remap_probe = {}
            for g in (40.0, 45.0, 50.0, 55.0, 60.0):
                remap_probe[str(int(g))] = round(remap(g, BA, pos, yr), 3)
            remapper_probe[f"{role}_{yr}"] = remap_probe

    def _bad(c):
        return (c["pooled_across_years"] or not c["meets_min_n_own_year"]
                or not c["in_build_remapper_table"])

    # Two readings, both reported. "live" = cells BA rows currently route into.
    # "table" = every cell build_remapper actually publishes for this source,
    # including one no BA row reaches today only because of a data defect.
    live_blockers = [c for c in cells if c["ba_rows_with_fv"] > 0 and _bad(c)]
    table_blockers = [c for c in cells if c["in_build_remapper_table"] and _bad(c)]

    # Position census. A NULL / unrecognised position silently routes a pitcher
    # into the hitter cell, and empties the pitcher cell so it pools across
    # years (leak D1 on a new source).
    pos_census = defaultdict(lambda: defaultdict(int))
    for s in snaps:
        if s.source != BA:
            continue
        pos_census[s.snapshot_date][str(s.position)] += 1
    # How many 2023 BA rows are really pitchers, per ANOTHER source's position?
    other_pos = {}
    for s in snaps:
        if s.source == BA or not s.position:
            continue
        other_pos.setdefault(s.player_key, s.position)
    misrouted = [s.player_key for s in snaps
                 if s.source == BA and s.snapshot_date == "2023-02-15"
                 and not GN._is_pitcher(s.position)
                 and GN._is_pitcher(other_pos.get(s.player_key))]

    return {
        "cells": cells,
        "remapper_probe": remapper_probe,
        "n_cells": len(cells),
        "n_live_blocker_cells": len(live_blockers),
        "live_blocker_cells": [{k: c[k] for k in
                                ("role", "year", "paired_n_own_year",
                                 "pooled_across_years", "in_build_remapper_table")}
                               for c in live_blockers],
        "n_table_blocker_cells": len(table_blockers),
        "table_blocker_cells": [{k: c[k] for k in
                                 ("role", "year", "ba_rows_with_fv",
                                  "paired_n_own_year", "paired_n_used",
                                  "pooled_across_years", "fitted_offset_fv",
                                  "in_build_remapper_table")}
                                for c in table_blockers],
        "position_census_by_vintage": {k: dict(v) for k, v in pos_census.items()},
        "pitcher_tokens": sorted(GN._PITCHER_TOKENS),
        "n_2023_rows_misrouted_to_hitter_cell": len(misrouted),
        "misrouted_examples": sorted(misrouted)[:12],
        "gate_g1_pass_live": len(live_blockers) == 0,
        "gate_g1_pass_table": len(table_blockers) == 0,
    }


def step1b_scale_break(snaps):
    """Reproduce the two arithmetic checks the brief supplies."""
    ba = defaultdict(dict)          # player -> year -> fv
    fg = defaultdict(dict)
    for s in snaps:
        if s.fv is None:
            continue
        yr = int(s.snapshot_date[:4])
        if s.source == BA and s.snapshot_date != "2026-06-03":
            ba[s.player_key][yr] = float(s.fv)
        elif s.source == "fangraphs":
            # latest fangraphs grade in that cycle year
            prev = fg[s.player_key].get(yr)
            if prev is None or s.snapshot_date >= prev[0]:
                fg[s.player_key][yr] = (s.snapshot_date, float(s.fv))
    consec = []
    for a, b in ((2023, 2024), (2024, 2025), (2025, 2026)):
        d = [v[b] - v[a] for v in ba.values() if a in v and b in v]
        consec.append({"pair": f"{a}->{b}", "n": len(d),
                       "mean": round(_mean(d), 3) if d else None,
                       "sd": round(_sd(d), 3) if len(d) > 1 else None})
    vsfg = []
    for yr in (2023, 2024, 2025, 2026):
        d = [ba[pk][yr] - fg[pk][yr][1]
             for pk in ba if yr in ba[pk] and yr in fg.get(pk, {})]
        vsfg.append({"year": yr, "n": len(d),
                     "mean": round(_mean(d), 3) if d else None,
                     "sd": round(_sd(d), 3) if len(d) > 1 else None})
    return {"consecutive_board_delta": consec, "ba_minus_fangraphs": vsfg}


# ---------------------------------------------------------------------------
# STEP 2: org-list guard
# ---------------------------------------------------------------------------
def step2_org_guard(snaps, arm_points_full):
    ba_rows = [s for s in snaps if s.source == BA]
    labels = sorted({s.interval_label or "" for s in ba_rows})
    org_labels = [lb for lb in labels if " Top 30" in lb]
    matched = [lb for lb in org_labels if C._ORG_LIST_LABEL_RE.search(lb)]
    unmatched = [lb for lb in org_labels if not C._ORG_LIST_LABEL_RE.search(lb)]
    other_labels = [lb for lb in labels if lb not in set(org_labels)]

    # Which BA rows are rank-implied ELIGIBLE (i.e. survive the org-list filter)?
    eligible = []
    for s in ba_rows:
        if s.rank is None:
            continue
        lbl = s.interval_label or ""
        is_org = ("_org_" in lbl) or (C._ORG_LIST_LABEL_RE.search(lbl) is not None)
        if not is_org:
            eligible.append(s)
    # Of those, how many actually REACH rank_implied_fv (only when no explicit FV
    # exists at that consensus point)?
    reached = 0
    reached_examples = []
    for s in eligible:
        pts = arm_points_full.get(s.player_key) or []
        for pt in pts:
            if pt["snapshot_date"] < s.snapshot_date:
                continue
            if pt.get("avg_fv") is None and pt.get("rank_implied_fv") is not None:
                if BA in (pt.get("per_source") or {}):
                    reached += 1
                    if len(reached_examples) < 10:
                        reached_examples.append({
                            "player_key": s.player_key,
                            "label": s.interval_label,
                            "rank": s.rank,
                            "date": pt["snapshot_date"],
                            "rank_implied_fv": pt["rank_implied_fv"],
                            "consensus_fv_raw": pt["consensus_fv_raw"],
                        })
                    break
    return {
        "n_distinct_labels": len(labels),
        "n_org_board_labels": len(org_labels),
        "n_org_labels_matched_by_regex": len(matched),
        "unmatched_org_labels": unmatched,
        "non_org_labels": other_labels,
        "n_org_board_rows": sum(1 for s in ba_rows
                                if C._ORG_LIST_LABEL_RE.search(s.interval_label or "")),
        "n_rank_implied_eligible_ba_rows": len(eligible),
        "n_eligible_rows_from_org_boards": sum(
            1 for s in eligible if " Top 30" in (s.interval_label or "")),
        "eligible_row_labels": sorted({s.interval_label for s in eligible}),
        "n_ba_players_reaching_rank_implied": reached,
        "reached_examples": reached_examples,
        "gate_g2_pass": (len(unmatched) == 0),
    }


# ---------------------------------------------------------------------------
# Arm construction
# ---------------------------------------------------------------------------
def build_arm(snaps, keep_ba=True, ba_override=None, full=False):
    """Return {player_key: [point dicts sorted by date]}.

    keep_ba=False drops every BA snapshot. ba_override replaces the BA rows
    with a permuted assignment.
    """
    base = [s for s in snaps if s.source != BA]
    if keep_ba:
        base = base + (ba_override if ba_override is not None
                       else [s for s in snaps if s.source == BA])
    ts = C.build_timeseries(base, normalize=C.ADOPT_NORMALIZED_CONSENSUS)
    out = {}
    for p in ts:
        if full:
            out[p.player_key] = [asdict(pt) for pt in p.points]
        else:
            out[p.player_key] = [(pt.snapshot_date, pt.consensus_fv_raw)
                                 for pt in p.points]
    return out


def asof_value(series, cutoff):
    """series: [(date, cfv)] sorted. Latest strictly before cutoff, or last."""
    if not series:
        return None, None
    if cutoff is None:
        return series[-1][1], series[-1][0]
    elig = [s for s in series if s[0] < cutoff]
    if not elig:
        return None, None
    return elig[-1][1], elig[-1][0]


# ---------------------------------------------------------------------------
# STEP 3: does BA make the CONSENSUS more accurate?
# ---------------------------------------------------------------------------
_UNI_CACHE = []


def _served_universe():
    if not _UNI_CACHE:
        _UNI_CACHE.extend(SB._load_universe(DATA))
    return _UNI_CACHE


def _universe_with_points(arm_full):
    """Served universe (same one source_backtest scores) with LAB points."""
    uni = []
    for p in _served_universe():
        pts = arm_full.get(p.get("player_key"))
        if pts is None:
            continue
        q = dict(p)
        q["points"] = pts
        uni.append(q)
    return uni


def step3_accuracy(arm_with_full, arm_without_full, ba_players_by_year):
    years = [y for y in SB.CANDIDATE_YEARS if (AS_OF_YEAR - y) >= SB.MIN_LAG_YEARS]
    uni_w = _universe_with_points(arm_with_full)
    uni_o = _universe_with_points(arm_without_full)
    by_key_o = {p["player_key"]: p for p in uni_o}

    per_year = []
    pooled_rows = []
    for y in years:
        rows = []
        for p in uni_w:
            g_w = SB._rater_grades_for_year(p, y)
            if SB.CONSENSUS_KEY not in g_w:
                continue
            q = by_key_o.get(p["player_key"])
            if q is None:
                continue
            g_o = SB._rater_grades_for_year(q, y)
            if SB.CONSENSUS_KEY not in g_o:
                continue
            out = SB._outcome(p)
            rows.append({
                "key": p["player_key"], "year": y,
                "w": g_w[SB.CONSENSUS_KEY], "o": g_o[SB.CONSENSUS_KEY],
                "war": out["war"], "contrib": out["contributor"],
                "debuted": out["debuted"],
                "ba": p["player_key"] in ba_players_by_year.get(y, set()),
            })
        if len(rows) < 4:
            continue
        moved = [r for r in rows if abs(r["w"] - r["o"]) > 1e-9]
        sp_w = SB._spearman([r["w"] for r in rows], [r["war"] for r in rows])
        sp_o = SB._spearman([r["o"] for r in rows], [r["war"] for r in rows])
        au_w = SB._auc([r["w"] for r in rows], [r["contrib"] for r in rows])
        au_o = SB._auc([r["o"] for r in rows], [r["contrib"] for r in rows])
        per_year.append({
            "year": y, "n_common": len(rows),
            "n_rows_moved_by_ba": len(moved),
            "n_ba_covered": sum(1 for r in rows if r["ba"]),
            "spearman_with": round(sp_w, 5) if sp_w is not None else None,
            "spearman_without": round(sp_o, 5) if sp_o is not None else None,
            "d_spearman": (round(sp_w - sp_o, 5)
                           if None not in (sp_w, sp_o) else None),
            "auc_with": round(au_w, 5) if au_w is not None else None,
            "auc_without": round(au_o, 5) if au_o is not None else None,
            "d_auc": round(au_w - au_o, 5) if None not in (au_w, au_o) else None,
        })
        pooled_rows.extend(rows)

    affected = [r for r in pooled_rows if abs(r["w"] - r["o"]) > 1e-9]

    def _dsp(sample):
        a = SB._spearman([r["w"] for r in sample], [r["war"] for r in sample])
        b = SB._spearman([r["o"] for r in sample], [r["war"] for r in sample])
        return None if None in (a, b) else a - b

    def _dauc(sample):
        a = SB._auc([r["w"] for r in sample], [r["contrib"] for r in sample])
        b = SB._auc([r["o"] for r in sample], [r["contrib"] for r in sample])
        return None if None in (a, b) else a - b

    res = {"years_scored": years, "per_year": per_year,
           "pooled_n": len(pooled_rows), "n_rows_moved_by_ba": len(affected)}

    # Score the AFFECTED-YEAR pool only, since every earlier year is identical
    # by construction (forward-fill cannot reach back before 2023-02-15).
    aff_years = sorted({r["year"] for r in affected})
    pool = [r for r in pooled_rows if r["year"] in aff_years]
    res["affected_years"] = aff_years
    res["affected_year_pool_n"] = len(pool)
    if len(pool) >= 20:
        res["d_spearman_affected"] = _dsp(pool)
        res["d_auc_affected"] = _dauc(pool)
        lo, hi = _boot_ci(pool, _dsp)
        res["d_spearman_ci95"] = [lo, hi]
        lo, hi = _boot_ci(pool, _dauc, seed=23)
        res["d_auc_ci95"] = [lo, hi]
        # MDE floor: the half-width of a zero-information placebo band, built by
        # scoring the WITHOUT arm against itself under a row-label permutation.
        rnd = random.Random(101)
        placebo = []
        for _ in range(400):
            s = [pool[rnd.randrange(len(pool))] for _ in range(len(pool))]
            v = SB._spearman([r["o"] for r in s], [r["war"] for r in s])
            if v is not None:
                placebo.append(v)
        placebo.sort()
        base = SB._spearman([r["o"] for r in pool], [r["war"] for r in pool])
        res["spearman_without_affected"] = round(base, 5) if base else None
        res["mde_floor_spearman_halfwidth"] = (
            round((_pct(placebo, 0.975) - _pct(placebo, 0.025)) / 2.0, 5)
            if placebo else None)
    return res


# ---------------------------------------------------------------------------
# STEP 4: does BA selection bias contaminate consensus_fv_raw?
# ---------------------------------------------------------------------------
def _matrix_rows():
    rows = []
    for side, path in (("hit", DATA / "xfv_hitter_matrix.json"),
                       ("pit", DATA / "xfv_pitcher_matrix.json")):
        for r in _jload(path):
            rows.append({
                "side": side,
                "player_key": r.get("player_key"),
                "kind": r.get("kind"),
                "cutoff": r.get("cutoff"),
                "asof_date": r.get("asof_date"),
                "shipped_cfv": r.get("consensus_fv_raw"),
                "target_resolved": r.get("target_resolved"),
                "debuted": r.get("kind") == "debuted",
            })
    return rows


def step4_deltas(rows, arm_with, arm_without, ba_covered, tag="", boot=True):
    recs = []
    for r in rows:
        vw, dw = asof_value(arm_with.get(r["player_key"]) or [], r["cutoff"])
        vo, do = asof_value(arm_without.get(r["player_key"]) or [], r["cutoff"])
        if vw is None or vo is None:
            continue
        recs.append({**r, "cfv_with": vw, "cfv_without": vo,
                     "delta": vw - vo, "asof_with": dw, "asof_without": do,
                     "ba_covered": r["player_key"] in ba_covered})
    moved = [r for r in recs if abs(r["delta"]) > 1e-9]
    out = {"tag": tag, "n_rows_joined": len(recs), "n_rows_moved": len(moved)}
    if not moved:
        out["note"] = "no training row moved"
        return out, recs

    deb = [r["delta"] for r in moved if r["debuted"]]
    bus = [r["delta"] for r in moved if not r["debuted"]]
    out["delta_all"] = {
        "n": len(moved),
        "mean": round(_mean([r["delta"] for r in moved]), 4),
        "sd": round(_sd([r["delta"] for r in moved]) or 0.0, 4),
        "max_abs": round(max(abs(r["delta"]) for r in moved), 4),
    }
    out["delta_debuted"] = {"n": len(deb),
                            "mean": round(_mean(deb), 4) if deb else None}
    out["delta_bust"] = {"n": len(bus),
                         "mean": round(_mean(bus), 4) if bus else None}
    out["debuted_minus_bust_mean_delta"] = (
        round(_mean(deb) - _mean(bus), 4) if deb and bus else None)

    # correlation of delta with the label, on rows that MOVED
    d = [r["delta"] for r in moved]
    lab = [1.0 if r["debuted"] else 0.0 for r in moved]
    war = [float(r["target_resolved"] or 0.0) for r in moved]
    out["corr_delta_debuted"] = (round(_pearson(d, lab), 4)
                                 if _pearson(d, lab) is not None else None)
    out["corr_delta_war"] = (round(_pearson(d, war), 4)
                             if _pearson(d, war) is not None else None)

    def _cd(sample):
        a = [x["delta"] for x in sample]
        b = [1.0 if x["debuted"] else 0.0 for x in sample]
        return _pearson(a, b)

    def _cw(sample):
        a = [x["delta"] for x in sample]
        b = [float(x["target_resolved"] or 0.0) for x in sample]
        return _pearson(a, b)

    def _gap(sample):
        dd = [x["delta"] for x in sample if x["debuted"]]
        bb = [x["delta"] for x in sample if not x["debuted"]]
        if not dd or not bb:
            return None
        return _mean(dd) - _mean(bb)

    if boot:
        lo, hi = _boot_ci(moved, _cd, seed=31)
        out["corr_delta_debuted_ci95"] = [lo, hi]
        lo, hi = _boot_ci(moved, _cw, seed=37)
        out["corr_delta_war_ci95"] = [lo, hi]
        lo, hi = _boot_ci(moved, _gap, seed=41)
        out["debuted_minus_bust_ci95"] = [lo, hi]

    # coverage-side outcome rates
    for side in ("hit", "pit"):
        srows = [r for r in rows if r["side"] == side]
        cov = [r for r in srows if r["player_key"] in ba_covered]
        out[f"coverage_{side}"] = {
            "pool_n": len(srows),
            "pool_debuted": sum(1 for r in srows if r["debuted"]),
            "pool_debut_rate": round(sum(1 for r in srows if r["debuted"]) /
                                     len(srows), 4) if srows else None,
            "covered_n": len(cov),
            "covered_debuted": sum(1 for r in cov if r["debuted"]),
            "covered_debut_rate": round(sum(1 for r in cov if r["debuted"]) /
                                        len(cov), 4) if cov else None,
            "lift_pts": (round(100 * (sum(1 for r in cov if r["debuted"]) / len(cov)
                                      - sum(1 for r in srows if r["debuted"]) / len(srows)), 2)
                         if cov and srows else None),
        }
    return out, recs


# ---------------------------------------------------------------------------
# C1: permuted coverage control
# ---------------------------------------------------------------------------
def permuted_ba(snaps, seed, pool_mode, covered_clubs):
    """Reassign each BA board's grade tuples to randomly chosen players,
    holding per-board count and the grade/rank distribution fixed."""
    rnd = random.Random(seed)
    ba_rows = [s for s in snaps if s.source == BA]
    # identity bank: player_key -> (name, position, org) from non-BA rows
    ident = {}
    year_pool = defaultdict(set)
    for s in snaps:
        if s.source == BA:
            continue
        yr = int(s.snapshot_date[:4])
        ident.setdefault(s.player_key, (s.player_name, s.position, s.org))
        if pool_mode == "all" or (s.org in covered_clubs):
            year_pool[yr].add(s.player_key)
    out = []
    for date_key in sorted({s.snapshot_date for s in ba_rows}):
        rows = [s for s in ba_rows if s.snapshot_date == date_key]
        yr = int(date_key[:4])
        cand = sorted(year_pool.get(yr) or set())
        if len(cand) < len(rows):
            cand = sorted(set(cand) | set(ident.keys()))
        pick = rnd.sample(cand, len(rows))
        for s, pk in zip(rows, pick):
            nm, pos, org = ident.get(pk, (pk, s.position, s.org))
            out.append(type(s)(
                source=s.source, snapshot_date=s.snapshot_date,
                interval_label=s.interval_label, player_key=pk,
                player_name=nm, position=pos, org=org,
                rank=s.rank, fv=s.fv, status=s.status,
                tools=s.tools, fv_plus=s.fv_plus))
    return out


# ---------------------------------------------------------------------------
# C2: within-league control
# ---------------------------------------------------------------------------
def step_c2(snaps, ba_covered_by_year, covered_clubs):
    uni = {p.get("player_key"): p for p in _served_universe()}
    out_rows = []
    for yr in (2023, 2024, 2025):
        # players on a BA-covered club in that cycle year, per non-BA rows
        club_players = set()
        for s in snaps:
            if s.source == BA:
                continue
            if int(s.snapshot_date[:4]) != yr:
                continue
            if s.org in covered_clubs:
                club_players.add(s.player_key)
        cov = ba_covered_by_year.get(yr, set()) & set(uni)
        unc = (club_players - ba_covered_by_year.get(yr, set())) & set(uni)

        def agg(keys):
            outs = [SB._outcome(uni[k]) for k in keys]
            if not outs:
                return None
            return {
                "n": len(outs),
                "debut_rate": round(sum(1 for o in outs if o["debuted"]) / len(outs), 4),
                "mean_war": round(sum(o["war"] for o in outs) / len(outs), 3),
                "contributor_rate": round(sum(1 for o in outs if o["contributor"]) / len(outs), 4),
            }
        out_rows.append({"year": yr,
                         "ba_covered_on_covered_clubs": agg(cov),
                         "same_clubs_not_ba_covered": agg(unc)})
    return out_rows


def step_c2_sources(arm_with_full, snaps, covered_clubs):
    """Voting-source count by league group, on points dated 2023-02-15+."""
    org_of = {}
    for s in snaps:
        if s.source == BA:
            continue
        org_of[s.player_key] = s.org
    grp = defaultdict(list)
    for pk, pts in arm_with_full.items():
        recent = [p for p in pts if p["snapshot_date"] >= "2023-02-15"]
        if not recent:
            continue
        n = len(recent[-1].get("sources_contributing") or [])
        g = "ba_covered_club" if org_of.get(pk) in covered_clubs else "other_club"
        grp[g].append(n)
    return {g: {"n_players": len(v), "mean_voting_sources": round(_mean(v), 3)}
            for g, v in grp.items()}


# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    snaps = storage.load_all_snapshots()
    ba_rows = [s for s in snaps if s.source == BA]
    # ORG-BOARD rows only. The pre-existing 2026-06-03 BA Top 100 carries rows
    # from all 30 clubs, so deriving the covered-club set from every BA row
    # silently turns the within-league control into a whole-population control.
    ba_org_rows = [s for s in ba_rows
                   if C._ORG_LIST_LABEL_RE.search(s.interval_label or "")]
    covered_clubs = sorted({s.org for s in ba_org_rows if s.org})
    ba_covered = {s.player_key for s in ba_org_rows}
    ba_by_year = defaultdict(set)
    for s in ba_org_rows:
        ba_by_year[int(s.snapshot_date[:4])].add(s.player_key)

    res = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lane": "BA1",
        "preregistration": "docs/efv-2026-08-07b/BA_SOURCE_GATE.md",
        "corpus": {
            "n_snapshots": len(snaps),
            "n_ba_rows": len(ba_rows),
            "n_ba_org_board_rows": len(ba_org_rows),
            "ba_dates": sorted({s.snapshot_date for s in ba_rows}),
            "ba_org_board_clubs": covered_clubs,
            "n_ba_org_board_clubs": len(covered_clubs),
            "n_ba_distinct_players_org_boards": len(ba_covered),
            "n_ba_distinct_players_all_rows": len({s.player_key for s in ba_rows}),
        },
    }

    print("step 1 ...", flush=True)
    res["step1_normalization"] = step1_normalization(snaps)
    res["step1b_scale_break"] = step1b_scale_break(snaps)

    print("arms ...", flush=True)
    arm_with_full = build_arm(snaps, keep_ba=True, full=True)
    arm_without_full = build_arm(snaps, keep_ba=False, full=True)
    arm_with = {k: [(p["snapshot_date"], p["consensus_fv_raw"]) for p in v]
                for k, v in arm_with_full.items()}
    arm_without = {k: [(p["snapshot_date"], p["consensus_fv_raw"]) for p in v]
                   for k, v in arm_without_full.items()}

    print("step 2 ...", flush=True)
    res["step2_org_guard"] = step2_org_guard(snaps, arm_with_full)

    print("step 3 ...", flush=True)
    res["step3_consensus_accuracy"] = step3_accuracy(
        arm_with_full, arm_without_full, ba_by_year)

    print("step 4 ...", flush=True)
    rows = _matrix_rows()
    real, recs = step4_deltas(rows, arm_with, arm_without, ba_covered, tag="real")
    res["step4_selection"] = real

    # reproduction check of the shipped matrix from the WITHOUT arm
    rep = [r for r in recs if r["shipped_cfv"] is not None]
    close = sum(1 for r in rep if abs(r["cfv_without"] - r["shipped_cfv"]) <= 0.01)
    res["step4_selection"]["shipped_matrix_reproduction"] = {
        "n": len(rep), "n_matching_without_arm": close,
        "rate": round(close / len(rep), 4) if rep else None,
        "mean_abs_gap": round(_mean([abs(r["cfv_without"] - r["shipped_cfv"])
                                     for r in rep]), 4) if rep else None,
        "by_kind": {
            k: {"n": len([r for r in rep if r["kind"] == k]),
                "rate": round(sum(1 for r in rep if r["kind"] == k
                                  and abs(r["cfv_without"] - r["shipped_cfv"]) <= 0.01)
                              / max(1, len([r for r in rep if r["kind"] == k])), 4)}
            for k in ("debuted", "bust")},
    }

    print("control C1 ...", flush=True)
    c1 = {}
    for mode in ("all", "covered_clubs"):
        band = []
        for i in range(N_SEEDS):
            perm = permuted_ba(snaps, 1000 + i, mode, set(covered_clubs))
            arm_p = build_arm(snaps, keep_ba=True, ba_override=perm, full=False)
            pcov = {s.player_key for s in perm}
            out, _ = step4_deltas(rows, arm_p, arm_without, pcov,
                                  tag=f"perm_{mode}_{i}", boot=False)
            band.append(out)
            print(f"  {mode} seed {i} moved={out['n_rows_moved']}", flush=True)
        keys = ("n_rows_moved", "debuted_minus_bust_mean_delta",
                "corr_delta_debuted", "corr_delta_war")
        summ = {}
        for k in keys:
            vals = sorted(b[k] for b in band if b.get(k) is not None)
            summ[k] = {"n_seeds": len(vals),
                       "p5": _pct(vals, 0.05), "p50": _pct(vals, 0.50),
                       "p95": _pct(vals, 0.95),
                       "min": vals[0] if vals else None,
                       "max": vals[-1] if vals else None}
        # covered debut-rate lift under permutation
        lifts_h = sorted(b["coverage_hit"]["lift_pts"] for b in band
                         if b.get("coverage_hit", {}).get("lift_pts") is not None)
        lifts_p = sorted(b["coverage_pit"]["lift_pts"] for b in band
                         if b.get("coverage_pit", {}).get("lift_pts") is not None)
        summ["coverage_lift_pts_hit"] = {"p5": _pct(lifts_h, 0.05),
                                         "p50": _pct(lifts_h, 0.50),
                                         "p95": _pct(lifts_h, 0.95)}
        summ["coverage_lift_pts_pit"] = {"p5": _pct(lifts_p, 0.05),
                                         "p50": _pct(lifts_p, 0.50),
                                         "p95": _pct(lifts_p, 0.95)}
        c1[mode] = {"n_seeds": N_SEEDS, "summary": summ,
                    "seeds": [{k: b.get(k) for k in
                               ("tag", "n_rows_moved", "delta_all",
                                "debuted_minus_bust_mean_delta",
                                "corr_delta_debuted", "corr_delta_war",
                                "coverage_hit", "coverage_pit")} for b in band]}
    res["control_c1_permuted_coverage"] = c1

    print("control C2 ...", flush=True)
    res["control_c2_within_league"] = {
        "outcomes": step_c2(snaps, ba_by_year, set(covered_clubs)),
        "voting_sources_by_club_group": step_c2_sources(
            arm_with_full, snaps, set(covered_clubs)),
        "note": ("BA covers 13 clubs; the American League has 15, so SEA and TEX "
                 "are AL clubs WITHOUT BA coverage in this corpus."),
    }

    res["runtime_sec"] = round(time.time() - t0, 1)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("wrote", OUT, res["runtime_sec"], "s")


if __name__ == "__main__":
    main()
