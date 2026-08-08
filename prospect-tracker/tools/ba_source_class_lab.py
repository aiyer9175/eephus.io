"""Lane BA3 lab: is Baseball America scoreable as a rater under source_backtest,
and what does admitting it cost the common set?

Pre-registration: docs/efv-2026-08-07b/BA_SOURCE_CLASS_GATE.md (sections 0-5 were
written before this file existed). Writes data/ba_source_class_eval.json.

Run: python tools/ba_source_class_lab.py

Reads only. Never writes data/source_backtest.json or any other served artifact.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import source_backtest as sb  # noqa: E402

DB = ROOT / "prospects.db"
OUT = ROOT / "data" / "ba_source_class_eval.json"
BA = "baseballamerica"
RUN_YEAR = date.today().year

# Gate thresholds. All four are pre-registered in BA_SOURCE_CLASS_GATE.md section 3.
G1_MIN_RESOLVABLE_ROWS = 100      # self-added, declared
G2_MIN_COMMON_RETENTION = 0.75    # self-added, declared
G3_MAX_INCUMBENT_MOVE = 0.02      # self-added, declared


def _r(v, n=4):
    return round(v, n) if v is not None else None


# ---------------------------------------------------------------- universe
def load_universe():
    uni = sb._load_universe()
    by_key = {}
    for p in uni:
        k = p.get("player_key")
        if k:
            by_key[k] = p
    return uni, by_key


# ---------------------------------------------------------------- BA overlay
def ba_from_db():
    """{year: {player_key: fv}} for BA rows inside each base year's preseason
    window, mirroring _rater_grades_for_year's max-across-window rule.
    Also returns the raw per-snapshot rows for the scale-break control."""
    con = sqlite3.connect(str(DB))
    try:
        rows = con.execute(
            "SELECT player_key, player_name, snapshot_date, fv, position, org, "
            "interval_label, tools_json FROM snapshots WHERE source=?", (BA,)).fetchall()
    finally:
        con.close()
    by_year = defaultdict(dict)
    per_snap = defaultdict(list)
    n_null_fv = 0
    for pk, name, sd, fv, pos, org, label, tj in rows:
        per_snap[sd].append({"pk": pk, "name": name, "fv": fv, "pos": pos,
                             "org": org, "label": label, "tools_json": tj})
        if fv is None:
            n_null_fv += 1
            continue
        y = int(str(sd)[:4])
        lo, hi = f"{y}{sb._WINDOW_START_MMDD}", f"{y}{sb._WINDOW_END_MMDD}"
        if not (lo <= str(sd) < hi):
            continue
        cur = by_year[y].get(pk)
        by_year[y][pk] = float(fv) if cur is None else max(cur, float(fv))
    return dict(by_year), dict(per_snap), n_null_fv


# ---------------------------------------------------------------- core engine
def _ba_from_per_source(p, year):
    """BA's max published preseason FV for `p` in `year` read straight out of the
    EXPORTED per_source, i.e. the path _rater_grades_for_year would take if BA
    were in SCORED_SOURCES. Returns None when the export carries no BA grade."""
    lo, hi = f"{year}{sb._WINDOW_START_MMDD}", f"{year}{sb._WINDOW_END_MMDD}"
    best = None
    for pt in (p.get("points") or []):
        sd = pt.get("snapshot_date")
        if not sd or not (lo <= sd < hi):
            continue
        v = ((pt.get("per_source") or {}).get(BA) or {}).get("fv_published")
        if v is None:
            continue
        v = float(v)
        best = v if best is None else max(best, v)
    return best


def build(universe, years, extra_raters, ba_by_year, ba_source="db"):
    """Mirror of run_source_backtest's common-set construction, parameterised on
    the rater list. extra_raters=() reproduces the shipped artifact (CONTROL F).

    ba_source="db"         : BA grades overlaid from prospects.db by player_key.
    ba_source="per_source" : BA grades read from the exported per_source block,
                             which is the path the real code would take.
    """
    raters = list(sb.SCORED_SOURCES) + [sb.CONSENSUS_KEY] + list(extra_raters)
    rows_by_rater = {r: [] for r in raters}
    common_by_year = {y: [] for y in years}
    for p in universe:
        out = sb._outcome(p)
        pk = p.get("player_key")
        for y in years:
            grades = dict(sb._rater_grades_for_year(p, y))
            if BA in extra_raters:
                v = (ba_by_year.get(y, {}).get(pk) if ba_source == "db"
                     else _ba_from_per_source(p, y))
                if v is not None:
                    # BA rows only count when the player has a preseason point at
                    # all, exactly as the real export would place them.
                    grades[BA] = v
            if not grades:
                continue
            for rater, fv in grades.items():
                if rater in rows_by_rater:
                    rows_by_rater[rater].append(
                        {"fv": fv, "outcome": out, "year": y, "key": pk})
            if all(r in grades for r in raters):
                common_by_year[y].append({
                    "key": pk, "name": p.get("player_name"), "year": y,
                    "org": p.get("org"),
                    "grades": {r: grades[r] for r in raters}, "outcome": out})
    return raters, rows_by_rater, common_by_year


def acc(rows, raters):
    res = {}
    for r in raters:
        rr = [c for c in rows if c["grades"].get(r) is not None]
        if not rr:
            continue
        fvs = [c["grades"][r] for c in rr]
        wars = [c["outcome"]["war"] for c in rr]
        contrib = [c["outcome"]["contributor"] for c in rr]
        res[r] = {"n": len(rr), "spearman": _r(sb._spearman(fvs, wars)),
                  "auc": _r(sb._auc(fvs, contrib))}
    return res


def own_rows_acc(rows):
    fvs = [c["fv"] for c in rows]
    wars = [c["outcome"]["war"] for c in rows]
    contrib = [c["outcome"]["contributor"] for c in rows]
    return {"n": len(rows), "spearman": _r(sb._spearman(fvs, wars)),
            "auc": _r(sb._auc(fvs, contrib)),
            "debut_rate": _r(sum(1 for c in rows if c["outcome"]["debuted"]) / len(rows), 4)
            if rows else None}


# ---------------------------------------------------------------- controls
def control_scale_break(per_snap):
    """CONTROL S: same-player consecutive-board BA delta, and BA minus
    contemporaneous FanGraphs on the same players."""
    dates = ["2023-02-15", "2024-02-15", "2025-02-15", "2026-02-15"]
    fv = {d: {r["pk"]: float(r["fv"]) for r in per_snap.get(d, []) if r["fv"] is not None}
          for d in dates}
    consec = []
    for a, b in zip(dates, dates[1:]):
        common = set(fv[a]) & set(fv[b])
        d = [fv[b][k] - fv[a][k] for k in common]
        consec.append({"from": a[:4], "to": b[:4], "n": len(d),
                       "mean": _r(sum(d) / len(d), 2) if d else None,
                       "sd": _r((sum((x - sum(d) / len(d)) ** 2 for x in d) / (len(d) - 1)) ** 0.5, 2)
                       if len(d) > 1 else None})
    # BA minus FanGraphs, same cycle year, latest FG fv in that year.
    con = sqlite3.connect(str(DB))
    try:
        fg_rows = con.execute(
            "SELECT player_key, snapshot_date, fv FROM snapshots "
            "WHERE source='fangraphs' AND fv IS NOT NULL").fetchall()
    finally:
        con.close()
    fg = {}
    for pk, sd, v in fg_rows:
        y = int(str(sd)[:4])
        k = (y, pk)
        if k not in fg or str(sd) > fg[k][0]:
            fg[k] = (str(sd), float(v))
    vs = []
    for d in dates:
        y = int(d[:4])
        diffs = [fv[d][pk] - fg[(y, pk)][1] for pk in fv[d] if (y, pk) in fg]
        m = sum(diffs) / len(diffs) if diffs else None
        vs.append({"year": y, "n": len(diffs), "mean": _r(m, 2),
                   "sd": _r((sum((x - m) ** 2 for x in diffs) / (len(diffs) - 1)) ** 0.5, 2)
                   if len(diffs) > 1 else None})
    return {"consecutive_board_delta": consec, "ba_minus_fangraphs": vs}


def control_gradenorm():
    """GATE 5: per (role, year) BA-vs-FanGraphs paired overlap, pooled flag, offset."""
    try:
        import numpy as np

        import grade_normalization as gn
    except Exception as exc:                                   # noqa: BLE001
        return {"error": str(exc)}
    out = []
    for year in (2023, 2024, 2025, 2026):
        for role in ("hitter", "pitcher"):
            pairs = gn._pairs(BA, role, year)
            src, ref, pooled = gn._paired_dists(BA, role, year)
            offset = (float(np.mean(src) - np.mean(ref))
                      if len(src) and len(ref) else None)
            out.append({"role": role, "year": year, "n_cycle_pairs": len(pairs),
                        "min_n": gn._MIN_N,
                        "below_min_n": len(pairs) < gn._MIN_N,
                        "pooled_across_years": bool(pooled),
                        "n_used": int(len(src)),
                        "offset_fv": _r(offset, 3),
                        "mappable": bool(len(src) and len(ref)
                                         and gn._mappable(src, ref))})
    return out


def control_selection(ba_keys):
    """CONTROL X: debut-rate lift of BA-covered rows on the shipped eFV matrices."""
    import efv_dataset
    out = {}
    for side, label in (("hit", "hitter"), ("pit", "pitcher")):
        try:
            rows = json.loads(efv_dataset.matrix_path(side).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            out[label] = {"error": str(exc)}
            continue
        deb = sum(1 for r in rows if r.get("kind") == "debuted")
        cov = [r for r in rows if r.get("player_key") in ba_keys]
        cdeb = sum(1 for r in cov if r.get("kind") == "debuted")
        out[label] = {
            "pool_n": len(rows), "pool_debuted": deb,
            "pool_debuted_rate": _r(deb / len(rows), 4) if rows else None,
            "ba_covered_n": len(cov), "ba_covered_debuted": cdeb,
            "ba_covered_debuted_rate": _r(cdeb / len(cov), 4) if cov else None,
            "lift_pts": _r((cdeb / len(cov) - deb / len(rows)) * 100, 1)
            if cov and rows else None,
        }
    return out


def control_league(universe, ba_orgs, cycle_year=2026):
    """CONTROL L: distinct real (non-synthetic) grading sources per player in the
    current cycle, split by whether the player's org is one BA covers.

    Reported BOTH with and without BA's own vote, because BA is already present in
    the exported per_source: assuming it is not, and adding 1, would double-count.
    The counterfactual is therefore the WITHOUT column, and the live state is WITH."""
    cov_with, cov_without, oth_with, oth_without = [], [], [], []
    n_ba_voting = 0
    for p in universe:
        srcs = set()
        for pt in (p.get("points") or []):
            sd = str(pt.get("snapshot_date") or "")
            if not sd.startswith(str(cycle_year)):
                continue
            for s, v in (pt.get("per_source") or {}).items():
                if (isinstance(v, dict) and v.get("fv_published") is not None
                        and s not in ("performance_ingest", "draft_signing")):
                    srcs.add(s)
        if not srcs:
            continue
        has_ba = BA in srcs
        n_ba_voting += int(has_ba)
        n_with = len(srcs)
        n_without = n_with - int(has_ba)
        if p.get("org") in ba_orgs:
            cov_with.append(n_with)
            cov_without.append(n_without)
        else:
            oth_with.append(n_with)
            oth_without.append(n_without)

    def _m(a):
        return {"n_players": len(a),
                "mean_sources": _r(sum(a) / len(a), 3) if a else None,
                "median_sources": sorted(a)[len(a) // 2] if a else None}
    cw, cwo, ow, owo = _m(cov_with), _m(cov_without), _m(oth_with), _m(oth_without)
    return {"cycle_year": cycle_year,
            "ba_orgs": sorted(ba_orgs), "n_ba_orgs": len(ba_orgs),
            "n_players_with_a_ba_vote": n_ba_voting,
            "ba_already_voting": n_ba_voting > 0,
            "without_ba_vote": {"ba_covered_orgs": cwo, "other_orgs": owo,
                                "asymmetry_pts": _r((cwo["mean_sources"] or 0)
                                                    - (owo["mean_sources"] or 0), 3)},
            "with_ba_vote": {"ba_covered_orgs": cw, "other_orgs": ow,
                             "asymmetry_pts": _r((cw["mean_sources"] or 0)
                                                 - (ow["mean_sources"] or 0), 3)},
            "note": ("BA votes only for players in ba_orgs, so its presence raises the "
                     "vote count for covered-org players and not for anyone else. Both "
                     "columns are measured, not assumed: the WITHOUT column is the "
                     "counterfactual and the WITH column is what the export currently "
                     "serves.")}


def control_position_basis(per_snap):
    """CONTROL P (unregistered diagnostic, added after GATE 5 flagged a zero-pair
    cell): the role grade_normalization assigns each BA row, from the RAW
    snapshots.position it stores, versus the role the same player carries on the
    FanGraphs / MLB Pipeline snapshots for the same cycle. A vintage whose position
    column is empty gets normalized entirely on the hitter basis."""
    import grade_normalization as gn
    con = sqlite3.connect(str(DB))
    try:
        ref = con.execute(
            "SELECT player_key, snapshot_date, position FROM snapshots "
            "WHERE source IN ('fangraphs','mlb_pipeline') AND position IS NOT NULL").fetchall()
        fg = con.execute(
            "SELECT player_key, snapshot_date, fv FROM snapshots "
            "WHERE source='fangraphs' AND fv IS NOT NULL").fetchall()
    finally:
        con.close()
    truth = {}
    for pk, sd, pos in ref:
        y = int(str(sd)[:4])
        k = (y, pk)
        if k not in truth or str(sd) > truth[k][0]:
            truth[k] = (str(sd), pos)
    fgv = {}
    for pk, sd, v in fg:
        y = int(str(sd)[:4])
        k = (y, pk)
        if k not in fgv or str(sd) > fgv[k][0]:
            fgv[k] = (str(sd), float(v))

    out = []
    for sd in sorted(per_snap):
        rows = [r for r in per_snap[sd] if r["fv"] is not None]
        if not rows:
            continue
        y = int(sd[:4])
        n_pos_null = sum(1 for r in rows if not r["pos"])
        assigned = Counter("pitcher" if gn._is_pitcher(r["pos"]) else "hitter" for r in rows)
        true_role, mism = Counter(), 0
        by_true = {"hitter": [], "pitcher": []}
        for r in rows:
            t = truth.get((y, r["pk"]))
            if not t:
                continue
            tr = "pitcher" if gn._is_pitcher(t[1]) else "hitter"
            true_role[tr] += 1
            ar = "pitcher" if gn._is_pitcher(r["pos"]) else "hitter"
            if ar != tr:
                mism += 1
            if (y, r["pk"]) in fgv:
                by_true[tr].append(r["fv"] - fgv[(y, r["pk"])][1])
        offs = {}
        for k, v in by_true.items():
            offs[k] = {"n": len(v), "ba_minus_fg_mean": _r(sum(v) / len(v), 3) if v else None}
        out.append({
            "snapshot_date": sd, "n_rows": len(rows),
            "n_position_null": n_pos_null,
            "distinct_position_tokens": sorted({r["pos"] for r in rows if r["pos"]}),
            "role_assigned_by_gradenorm": dict(assigned),
            "role_from_other_sources": dict(true_role),
            "n_role_mismatch": mism,
            "mismatch_rate": _r(mism / sum(true_role.values()), 4) if sum(true_role.values()) else None,
            "within_year_offset_by_true_role": offs,
        })
    return out


# ---------------------------------------------------------------- main
def main():
    universe, by_key = load_universe()
    years = sb._resolved_years(universe, RUN_YEAR)
    ba_by_year, per_snap, n_null_fv = ba_from_db()

    # ---- CONTROL F: overlay off must reproduce the shipped artifact.
    raters3, rows3, common3 = build(universe, years, (), ba_by_year)
    pooled3_rows = [c for y in years for c in common3[y]]
    a3 = acc(pooled3_rows, raters3)
    shipped = json.loads((ROOT / "data" / "source_backtest.json").read_text(encoding="utf-8"))
    sp = shipped["accuracy"]["pooled"]
    checks = [("common_n", len(pooled3_rows), shipped["accuracy"]["common_n"]),
              ("window.years", years, shipped["window"]["years"])]
    for s in ("fangraphs", "mlb_pipeline", "prospx_consensus"):
        checks.append((f"{s}.spearman", a3[s]["spearman"], sp[s]["spearman"]))
        checks.append((f"{s}.auc", a3[s]["auc"], sp[s]["auc"]))
    # F1: against the SERVED artifact. Informative, but it is only a valid harness
    # test when the served artifact was built from the SAME universe export. The
    # pipeline rewrote timeseries.json and debuts.json at 2026-08-08 01:05, mid-lane,
    # while data/source_backtest.json still dates from the 17:59 export, so a
    # mismatch here diagnoses a STALE REFERENCE, not a broken harness. The vintage
    # comparison below is what tells the two apart.
    ts_mtime = datetime.fromtimestamp(
        (ROOT / "data" / "timeseries.json").stat().st_mtime, timezone.utc).isoformat()
    control_f = {
        "leg_f1_vs_served_artifact": {
            "checks": [{"quantity": q, "lab": got, "shipped": want, "match": got == want}
                       for q, got, want in checks],
            "served_generated_at": shipped.get("generated_at"),
            "universe_export_mtime_utc": ts_mtime,
        }}
    control_f["leg_f1_vs_served_artifact"]["pass"] = all(
        c["match"] for c in control_f["leg_f1_vs_served_artifact"]["checks"])
    control_f["leg_f1_vs_served_artifact"]["reference_is_same_vintage"] = bool(
        (shipped.get("generated_at") or "") >= ts_mtime)

    # F2: against a LIVE recompute of run_source_backtest on the SAME inputs, with
    # the eFV legs stubbed (they refit models and are not this lane's subject).
    # This is the binding fidelity test: it cannot go stale.
    import types
    _stub = types.ModuleType("efv_model")
    _stub.oos_grades = lambda side: {}
    _stub.block_rho_eval = lambda: None
    sys.modules.setdefault("efv_model", _stub)
    _saved = sb._xfv_vs_consensus
    sb._xfv_vs_consensus = lambda data_dir=None: None
    try:
        live = sb.run_source_backtest(write=False)
    finally:
        sb._xfv_vs_consensus = _saved
    lp = live["accuracy"]["pooled"]
    f2 = [{"quantity": "common_n", "lab": len(pooled3_rows),
           "live": live["accuracy"]["common_n"],
           "match": len(pooled3_rows) == live["accuracy"]["common_n"]},
          {"quantity": "window.years", "lab": years, "live": live["window"]["years"],
           "match": years == live["window"]["years"]}]
    for s in ("fangraphs", "mlb_pipeline", "prospx_consensus"):
        for m in ("spearman", "auc"):
            f2.append({"quantity": f"{s}.{m}", "lab": a3[s][m], "live": lp[s][m],
                       "match": a3[s][m] == lp[s][m]})
    control_f["leg_f2_vs_live_recompute"] = {
        "checks": f2, "pass": all(c["match"] for c in f2)}
    control_f["derived_classification_live"] = live["source_classification"]
    control_f["insufficient_history_live"] = live["insufficient_history"]
    # The binding leg is F2. F1 is reported either way.
    control_f["pass"] = control_f["leg_f2_vs_live_recompute"]["pass"]

    # ---- resolvability, counted in rows
    ukeys = set(by_key)
    vintages = []
    all_snap_dates = sorted(per_snap)
    for sd in all_snap_dates:
        rows = per_snap[sd]
        y = int(sd[:4])
        lo, hi = f"{y}{sb._WINDOW_START_MMDD}", f"{y}{sb._WINDOW_END_MMDD}"
        in_win = lo <= sd < hi
        with_fv = [r for r in rows if r["fv"] is not None]
        joined = [r for r in with_fv if r["pk"] in ukeys]
        lag_ok = (RUN_YEAR - y) >= sb.MIN_LAG_YEARS
        in_cand = y in sb.CANDIDATE_YEARS
        first_year = y + sb.MIN_LAG_YEARS
        vintages.append({
            "snapshot_date": sd, "base_year": y, "rows_db": len(rows),
            "rows_with_fv": len(with_fv), "in_preseason_window": in_win,
            "rows_in_window": len(with_fv) if in_win else 0,
            "rows_joined": len(joined) if in_win else 0,
            "rows_resolvable": len(joined) if (in_win and lag_ok and in_cand) else 0,
            "lag_years": RUN_YEAR - y, "min_lag_years": sb.MIN_LAG_YEARS,
            "lag_satisfied": lag_ok, "in_candidate_years": in_cand,
            "scoreable_from_run_year": first_year,
            # A base year can be blocked by PHYSICS (not enough development lag
            # yet) or by the hardcoded CANDIDATE_YEARS tuple, which is a different
            # kind of blocked and does not clear itself with time.
            "blocked_by_candidate_years_tuple": bool(not in_cand),
            "blocked_by_lag_only": bool(in_cand and not lag_ok),
            "orgs": sorted({r["org"] for r in rows if r["org"]}),
        })
    resolvable_total = sum(v["rows_resolvable"] for v in vintages)
    resolvable_vintages = [v for v in vintages if v["rows_resolvable"] > 0]

    # ---- GATE 1
    gate1 = {"resolvable_vintages": len(resolvable_vintages),
             "max_rows_resolvable": max((v["rows_resolvable"] for v in vintages), default=0),
             "total_rows_resolvable": resolvable_total,
             "threshold_rows": G1_MIN_RESOLVABLE_ROWS}
    gate1["pass"] = gate1["max_rows_resolvable"] >= G1_MIN_RESOLVABLE_ROWS

    # ---- overlay ON
    raters4, rows4, common4 = build(universe, years, (BA,), ba_by_year)
    pooled4_rows = [c for y in years for c in common4[y]]
    a4 = acc(pooled4_rows, raters4)

    # ---- CONTROL E (export equivalence): the same measurement with BA read from
    # the EXPORTED per_source instead of overlaid from the database. If the two
    # disagree, the overlay is not the path the real code takes and every "after"
    # number above is about a population the pipeline would not produce.
    _r4e, _rows4e, _common4e = build(universe, years, (BA,), ba_by_year,
                                     ba_source="per_source")
    pooled4e_rows = [c for y in years for c in _common4e[y]]
    a4e = acc(pooled4e_rows, _r4e)
    control_e = {
        "common_n_db_overlay": len(pooled4_rows),
        "common_n_exported_per_source": len(pooled4e_rows),
        "acc_db_overlay": a4, "acc_exported_per_source": a4e,
        "agrees": len(pooled4_rows) == len(pooled4e_rows) and all(
            (a4.get(k) or {}).get(m) == (a4e.get(k) or {}).get(m)
            for k in raters4 for m in ("spearman", "auc")),
        "note": ("the export forward-fills a source across later snapshot dates, so "
                 "a BA grade can appear on in-window dates the database has no row "
                 "for; any disagreement here is that forward-fill, and the exported "
                 "figure is the one the shipped code would compute"),
    }

    # ---- GATE 2
    before, after = len(pooled3_rows), len(pooled4_rows)
    gate2 = {"common_n_before": before, "common_n_after": after,
             "retention": _r(after / before, 4) if before else None,
             "threshold_retention": G2_MIN_COMMON_RETENTION,
             "per_year_before": {y: len(common3[y]) for y in years},
             "per_year_after": {y: len(common4[y]) for y in years}}
    gate2["pass"] = bool(before and (after / before) >= G2_MIN_COMMON_RETENTION)

    # year-matched charitable comparison: restrict BOTH sides to years where BA
    # actually has a resolvable vintage, so the collapse is not just "years".
    ba_years = [v["base_year"] for v in resolvable_vintages]
    ym_before = [c for y in ba_years for c in common3.get(y, [])]
    ym_after = [c for y in ba_years for c in common4.get(y, [])]
    year_matched = {
        "years": ba_years,
        "common_n_before": len(ym_before), "common_n_after": len(ym_after),
        "retention": _r(len(ym_after) / len(ym_before), 4) if ym_before else None,
        "acc_before": acc(ym_before, raters3), "acc_after": acc(ym_after, raters4),
    }

    # ---- GATE 3
    moves = {}
    for s in raters3:
        b, a = a3.get(s) or {}, a4.get(s) or {}
        if b.get("spearman") is None or a.get("spearman") is None:
            moves[s] = {"before": b, "after": a, "d_spearman": None, "d_auc": None}
            continue
        moves[s] = {"before": b, "after": a,
                    "d_spearman": _r(a["spearman"] - b["spearman"], 4),
                    "d_auc": _r(a["auc"] - b["auc"], 4) if (a.get("auc") is not None
                                                            and b.get("auc") is not None) else None}
    gate3 = {"threshold": G3_MAX_INCUMBENT_MOVE, "moves": moves}
    gate3["pass"] = all(
        m["d_spearman"] is not None and abs(m["d_spearman"]) <= G3_MAX_INCUMBENT_MOVE
        and (m["d_auc"] is None or abs(m["d_auc"]) <= G3_MAX_INCUMBENT_MOVE)
        for m in moves.values())

    # ---- GATE 4: era purity of any scored BA pool
    scored_ba_years = sorted({v["base_year"] for v in resolvable_vintages})
    era_of = {y: ("adjusted_grade" if y >= 2026 else "ba_grade") for y in scored_ba_years}
    gate4 = {"scored_ba_base_years": scored_ba_years,
             "era_by_year": era_of,
             "distinct_eras_in_pool": len(set(era_of.values())),
             "fv_field_scored": "per_source.baseballamerica.fv_published == snapshots.fv (RAW)",
             }
    gate4["pass"] = len(set(era_of.values())) <= 1

    # ---- the downstream claim GATE 3 protects: does the blend still beat its
    # best input? source_backtest._beats reads accuracy.pooled, so admitting BA
    # recomputes this on the shrunken population.
    def _beats(a, sources):
        cons = (a.get(sb.CONSENSUS_KEY) or {}).get("spearman")
        cauc = (a.get(sb.CONSENSUS_KEY) or {}).get("auc")
        bi = max((v for v in ((a.get(s) or {}).get("spearman") for s in sources)
                  if v is not None), default=None)
        ba_ = max((v for v in ((a.get(s) or {}).get("auc") for s in sources)
                   if v is not None), default=None)
        return {"spearman": {"consensus": cons, "best_input": bi,
                             "consensus_wins": bool(cons is not None and bi is not None and cons >= bi)},
                "auc": {"consensus": cauc, "best_input": ba_,
                        "consensus_wins": bool(cauc is not None and ba_ is not None and cauc >= ba_)}}
    cvi_before = _beats(a3, sb.SCORED_SOURCES)
    cvi_after = _beats(a4, list(sb.SCORED_SOURCES) + [BA])
    consensus_claim = {
        "before": cvi_before, "after": cvi_after,
        "flips": {m: cvi_before[m]["consensus_wins"] != cvi_after[m]["consensus_wins"]
                  for m in ("spearman", "auc")},
        "note": ("accuracy.consensus_vs_inputs is the site's core defence of blending. "
                 "It is computed on accuracy.pooled, so it moves with the common set."),
    }
    # rank order of the incumbent raters, before and after
    def _order(a, keys):
        return [k for k, _ in sorted(((k, (a.get(k) or {}).get("spearman"))
                                      for k in keys if (a.get(k) or {}).get("spearman") is not None),
                                     key=lambda t: -t[1])]
    consensus_claim["rater_order_before"] = _order(a3, raters3)
    consensus_claim["rater_order_after"] = _order(a4, raters3)
    consensus_claim["rater_order_flips"] = (
        consensus_claim["rater_order_before"] != consensus_claim["rater_order_after"])

    # ---- CONTROL C: BA's own rows vs the common set
    ba_own = own_rows_acc(rows4[BA]) if rows4.get(BA) else None
    ba_common = a4.get(BA)
    control_c = {"own_rows": ba_own, "common_set": ba_common,
                 "own_rows_flatters": bool(ba_own and ba_common
                                           and ba_own["spearman"] is not None
                                           and ba_common["spearman"] is not None
                                           and ba_own["spearman"] > ba_common["spearman"])}

    # ---- CONTROL R: rank-only rows
    control_r = {"ba_rows_with_null_fv": n_null_fv,
                 "null_fv_snapshot_dates": sorted({d for d, rs in per_snap.items()
                                                   if any(r["fv"] is None for r in rs)}),
                 "null_fv_rows_entering_any_fv_stat": 0,
                 "note": ("rows with fv IS NULL are dropped before by_year is built and "
                          "before grade_normalization's query, so none can be read as FV 0")}

    ba_keys = {r["pk"] for rs in per_snap.values() for r in rs if r["fv"] is not None}
    ba_orgs = {r["org"] for rs in per_snap.values() for r in rs
               if r["org"] and r["label"] and "Top 30" in str(r["label"])}
    # CONTROL L must run on the UNSPLICED universe: splicing BA into per_source
    # would add BA to its own baseline vote count and hide the asymmetry it is
    # measuring. Everything that reads `universe` runs above the splice below.
    control_l = control_league(universe, ba_orgs)

    # ---- the SHIPPED derived classification, exercised on both states of the
    # universe: as exported today (BA has no preseason rows yet) and with the BA
    # org boards spliced in as points (what the next export produces). If the
    # shipped code and this lab ever disagree, this cross-check is what says so.
    def _classify(uni):
        syr, sro, sow, cov, n = {}, {}, {}, {}, 0
        for p in uni:
            inw, ow = sb._all_source_grades_by_year(p)
            for y, srcs in inw.items():
                for s, fv in srcs.items():
                    t = syr if fv is not None else sro
                    t.setdefault(s, {})
                    t[s][y] = t[s].get(y, 0) + 1
            for y, srcs in ow.items():
                for s in srcs:
                    sow.setdefault(s, {})
                    sow[s][y] = sow[s].get(y, 0) + 1
            for y in years:
                g = sb._rater_grades_for_year(p, y)
                if g and all(r in g for r in raters3):
                    n += 1
                    for s, fv in inw.get(y, {}).items():
                        if fv is not None:
                            cov[s] = cov.get(s, 0) + 1
        return sb.classify_sources(syr, sro, sow, cov, n, years, RUN_YEAR), n

    cls_before, n_before = _classify(universe)
    ba_idx: dict = {}
    for sd, rs in per_snap.items():
        for r in rs:
            if r["fv"] is not None:
                ba_idx.setdefault(r["pk"], []).append((sd, r["fv"]))
    for p in universe:                      # splice, in place, after cls_before
        hits = ba_idx.get(p.get("player_key"))
        if not hits:
            continue
        pts = p.setdefault("points", [])
        idx = {pt.get("snapshot_date"): pt for pt in pts}
        for sd, fv in hits:
            pt = idx.get(sd)
            if pt is None:
                pt = {"snapshot_date": sd, "per_source": {}}
                pts.append(pt)
                idx[sd] = pt
            pt.setdefault("per_source", {})[BA] = {"rank": None, "fv_published": fv}
    cls_after, n_after = _classify(universe)
    derived = {
        "before_export": {"common_n": n_before, "records": cls_before},
        "after_export_simulated": {"common_n": n_after, "records": cls_after,
                                   "common_n_note": ("spliced points carry no "
                                                     "consensus_fv_raw, so a few rows "
                                                     "drop out of the common set; the "
                                                     "gate numbers above use the "
                                                     "grade-merge harness instead, which "
                                                     "passes CONTROL F at 4259")},
        # The export at 2026-08-08 01:05 already carries BA, so `before_export` is
        # no longer the pre-BA state on this run. Both facts are reported: whether
        # the live universe already reflects BA, and whether the derived record
        # reaches the measured verdict on the live universe (which is the point).
        "live_universe_already_carries_ba": bool(
            any(r["source"] == BA and r["rows_by_base_year"] for r in cls_before)),
        "ba_blocked_by_live": next((r["blocked_by"] for r in cls_before
                                    if r["source"] == BA), None),
        "ba_blocked_by_after_splice": next((r["blocked_by"] for r in cls_after
                                            if r["source"] == BA), None),
        "reaches_measured_verdict": bool(
            any(r["source"] == BA and r["blocked_by"] == "common_set_collapse"
                for r in cls_before)),
        "names_preserved": sorted(r["source"] for r in cls_before if not r["scoreable_now"]),
    }
    # NOTE: `universe` is now mutated (BA spliced in). Nothing after this line may
    # recompute a gate number or a control from it.

    result = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_year": RUN_YEAR,
        "preregistration": "docs/efv-2026-08-07b/BA_SOURCE_CLASS_GATE.md",
        "constants": {"MIN_LAG_YEARS": sb.MIN_LAG_YEARS,
                      "CANDIDATE_YEARS": list(sb.CANDIDATE_YEARS),
                      "window": [sb._WINDOW_START_MMDD, sb._WINDOW_END_MMDD],
                      "SCORED_SOURCES": list(sb.SCORED_SOURCES)},
        "resolved_years": years,
        "vintages": vintages,
        "control_f_harness_fidelity": control_f,
        "control_e_export_equivalence": control_e,
        "gate1_resolvability": gate1,
        "gate2_common_set_integrity": gate2,
        "gate2_year_matched": year_matched,
        "gate3_no_silent_restatement": gate3,
        "gate4_era_purity": gate4,
        "gate3b_downstream_consensus_claim": consensus_claim,
        "gate5_gradenorm_absorption": control_gradenorm(),
        "control_p_position_basis": control_position_basis(per_snap),
        "control_c_coverage_not_skill": control_c,
        "control_r_rank_only": control_r,
        "control_s_scale_break": control_scale_break(per_snap),
        "control_l_league_selection": control_l,
        "control_x_selection_hazard": control_selection(ba_keys),
        "derived_classification_crosscheck": derived,
    }
    result["verdict"] = {
        "gate1_pass": gate1["pass"], "gate2_pass": gate2["pass"],
        "gate3_pass": gate3["pass"], "gate4_pass": gate4["pass"],
        "ba_enters_scored_sources": bool(control_f["pass"] and gate1["pass"]
                                         and gate2["pass"] and gate3["pass"]
                                         and gate4["pass"]),
    }
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")

    # ---- console
    f1 = control_f["leg_f1_vs_served_artifact"]
    print("CONTROL F1 (vs SERVED artifact):", "PASS" if f1["pass"] else "FAIL",
          " same_vintage=", f1["reference_is_same_vintage"],
          " served=", f1["served_generated_at"], " export=", f1["universe_export_mtime_utc"])
    for c in f1["checks"]:
        print(f"   {'ok ' if c['match'] else 'XX '}{c['quantity']:<28} lab={c['lab']}  shipped={c['shipped']}")
    f2 = control_f["leg_f2_vs_live_recompute"]
    print("CONTROL F2 (vs LIVE recompute, binding):", "PASS" if f2["pass"] else "FAIL")
    for c in f2["checks"]:
        print(f"   {'ok ' if c['match'] else 'XX '}{c['quantity']:<28} lab={c['lab']}  live={c['live']}")
    print("CONTROL E (export equivalence):", "agrees" if control_e["agrees"] else "DIFFERS",
          " db_overlay_n=", control_e["common_n_db_overlay"],
          " exported_n=", control_e["common_n_exported_per_source"])
    print("   exported-basis acc:", a4e)
    print("\nVINTAGES")
    for v in vintages:
        print(f"  {v['snapshot_date']}  db={v['rows_db']:<4} fv={v['rows_with_fv']:<4} "
              f"inwin={v['in_preseason_window']!s:<5} joined={v['rows_joined']:<4} "
              f"resolvable={v['rows_resolvable']:<4} lag={v['lag_years']} "
              f"cand={v['in_candidate_years']!s:<5} scoreable_from={v['scoreable_from_run_year']}")
    print(f"\nGATE 1 resolvability: {'PASS' if gate1['pass'] else 'FAIL'}  {gate1}")
    print(f"GATE 2 common set: {'PASS' if gate2['pass'] else 'FAIL'}  "
          f"before={before} after={after} retention={gate2['retention']}")
    print(f"   per-year before {gate2['per_year_before']}")
    print(f"   per-year after  {gate2['per_year_after']}")
    print(f"   year-matched ({ba_years}) before={year_matched['common_n_before']} "
          f"after={year_matched['common_n_after']} retention={year_matched['retention']}")
    print(f"GATE 3 restatement: {'PASS' if gate3['pass'] else 'FAIL'}")
    for s, m in moves.items():
        print(f"   {s:<18} rho {m['before'].get('spearman')} -> {m['after'].get('spearman')} "
              f"(d={m['d_spearman']})   auc {m['before'].get('auc')} -> {m['after'].get('auc')} (d={m['d_auc']})")
    print("   year-matched acc before:", year_matched["acc_before"])
    print("   year-matched acc after :", year_matched["acc_after"])
    print(f"GATE 4 era purity: {'PASS' if gate4['pass'] else 'FAIL'}  {gate4['era_by_year']}")
    print("\nGATE 5 gradenorm cells:")
    for c in result["gate5_gradenorm_absorption"] if isinstance(
            result["gate5_gradenorm_absorption"], list) else []:
        print(f"   {c['role']:<8} {c['year']}  n_cycle={c['n_cycle_pairs']:<4} "
              f"below_min_n={c['below_min_n']!s:<5} pooled={c['pooled_across_years']!s:<5} "
              f"n_used={c['n_used']:<5} offset={c['offset_fv']}")
    print("\nGATE 3b downstream consensus claim")
    print("   before:", consensus_claim["before"])
    print("   after :", consensus_claim["after"])
    print("   flips :", consensus_claim["flips"],
          " rater order", consensus_claim["rater_order_before"], "->",
          consensus_claim["rater_order_after"],
          "FLIPS" if consensus_claim["rater_order_flips"] else "stable")
    print("\nCONTROL P position basis")
    for c in result["control_p_position_basis"]:
        print(f"   {c['snapshot_date']}  n={c['n_rows']:<4} pos_null={c['n_position_null']:<4} "
              f"tokens={c['distinct_position_tokens'][:6]} assigned={c['role_assigned_by_gradenorm']} "
              f"true={c['role_from_other_sources']} mismatch={c['n_role_mismatch']} "
              f"({c['mismatch_rate']})  offsets={c['within_year_offset_by_true_role']}")
    print("\nCONTROL C  own rows:", ba_own, "\n           common set:", ba_common)
    print("CONTROL S consecutive:", result["control_s_scale_break"]["consecutive_board_delta"])
    print("CONTROL S vs FG      :", result["control_s_scale_break"]["ba_minus_fangraphs"])
    print("CONTROL L:", result["control_l_league_selection"])
    print("CONTROL X:", result["control_x_selection_hazard"])
    print("CONTROL R:", result["control_r_rank_only"])
    print("\nDERIVED CLASSIFICATION (shipped code, before export):")
    for r in cls_before:
        print(f"   {r['source']:<16} blocked_by={r['blocked_by']:<22} "
              f"rows={r['rows_by_base_year']} out_of_window={r['out_of_window_rows_by_year']}")
    print("DERIVED CLASSIFICATION (shipped code, after BA export simulated):")
    for r in cls_after:
        print(f"   {r['source']:<16} blocked_by={r['blocked_by']:<22} "
              f"rows={r['rows_by_base_year']} ret={r['common_set_retention']} "
              f"from={r['scoreable_from_run_year']} "
              f"tuple_blocked={r['base_years_blocked_by_candidate_years']}")
    print("   live universe already carries BA:", derived["live_universe_already_carries_ba"],
          " BA blocked_by (live):", derived["ba_blocked_by_live"],
          " reaches measured verdict:", derived["reaches_measured_verdict"],
          " names preserved:", derived["names_preserved"])
    print("\nVERDICT:", result["verdict"])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
