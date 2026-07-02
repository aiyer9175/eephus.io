# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SC+ per-component forward-signal isolation (analysis only).

SC+ (Statcast+) pools four historical-analog components (avg EV,
HardHit%, Barrel%/BBE, SwingMiss%) into one composite whose pooled
forward r vs first-MLB outcomes is weak (~0.12-0.17, see
data/statcast_plus_eval.json). This tool answers three questions the
composite number hides:

  1. Which component carries the signal, per side (hitter/pitcher),
     against first-MLB rate outcomes AND first-2y bWAR?
  2. Which components are noise?
  3. Does a reweighted 2-component blend beat the current equal-weight
     4-component composite OUT-OF-SAMPLE (forward-chained by cohort,
     weights fit only on earlier cohorts, so no refit leakage)?

Cohort construction, pool restriction (AAA-only, min 100 PA), outcome
joins and sign conventions are REUSED from arkmetric_forward_eval
(the audit's SC+ forward-eval machinery); parity with its composite is
asserted exactly at runtime. Reference components (xwOBA, K%, BB% from
the same Savant aggregates) are scored alongside for context but are
NOT blend candidates: the recommendation is about reweighting SC+'s
own components, not replacing the metric.

Everything is deterministic: no RNG anywhere (component ties break on
a fixed component order). Offline: cached Savant CSVs + cached
StatsAPI season splits only (fetch=False throughout).

Output: data/sc_plus_component_eval.json (method, per-component table,
blend check, recommendation block). Recommendation only; this tool
does NOT modify statcast_metrics.py.

Run: python tools/sc_plus_component_eval.py
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import arkmetric_forward_eval as afe  # noqa: E402
import milb_history as mh             # noqa: E402
import storage                        # noqa: E402

OUT_PATH = ROOT / "data" / "sc_plus_component_eval.json"

SEASONS = afe.SEASONS                       # (2023, 2024, 2025)
CORE = list(afe.COMPONENTS)                 # the 4 SC+ analog components
# reference-only components present in the same Savant aggregates
EXTRAS = ("xwoba", "k_percent", "bb_percent")

CORE_SIGNS = {
    "batter": {"launch_speed": 1, "hardhit_percent": 1,
               "barrels_per_bbe_percent": 1, "swing_miss_percent": -1},
    "pitcher": {"launch_speed": -1, "hardhit_percent": -1,
                "barrels_per_bbe_percent": -1, "swing_miss_percent": 1},
}
EXTRA_SIGNS = {
    "batter": {"xwoba": 1, "k_percent": -1, "bb_percent": 1},
    "pitcher": {"xwoba": -1, "k_percent": 1, "bb_percent": -1},
}

# forward-chained blend folds: (train pool seasons, test pool season).
# Pool season S maps to debut year S+1; weights are fit on strictly
# earlier cohorts only.
RATE_FOLDS = (((2023,), 2024), ((2023, 2024), 2025))
WAR_FOLDS = (((2023,), 2024),)   # 2026 debuts have no 2y-WAR window yet

BLEND_IMPROVE_MIN = 0.05   # pooled-OOS r gain required to call "reweight"
DEMOTE_R_MAX = 0.05        # composite pooled r below this on BOTH sides
P_SIGNAL = 0.10            # per-component two-sided p threshold


# ---------------------------------------------------------------- stats

def _mean(v):
    return sum(v) / len(v)


def _pearson(xs, ys):
    return afe._pearson(list(xs), list(ys))


def _spearman(xs, ys):
    return afe._spearman(list(xs), list(ys))


def _p_two_sided(r, n):
    """Fisher-z approximate two-sided p for a Pearson r."""
    if r is None or n < 8 or abs(r) >= 1:
        return None
    z = math.atanh(r) * math.sqrt(n - 3)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return round(p, 4)


# --------------------------------------------------- component z tables

def component_z_table(season: int, side: str) -> dict[int, dict]:
    """{mlbam: {"z": {comp: signed z}, "sc_plus_analog": 100+10z}} for one
    AAA season pool. Core-component pool membership and z math mirror
    arkmetric_forward_eval.sc_analog_index exactly (parity asserted in
    run()); extras get a z only where the CSV value exists, with pool
    stats over the same qualifying players."""
    aaa = afe._aaa_mlbams(season)
    rows = afe.savant_rows(season, side, fetch=False)
    signs = dict(CORE_SIGNS[side]) | dict(EXTRA_SIGNS[side])
    comps = CORE + list(EXTRAS)
    cols: dict[str, list[float]] = {c: [] for c in comps}
    per: list[tuple[int, dict]] = []
    for r in rows:
        mid = afe._f(r.get("player_id"))
        pa = afe._f(r.get("pa")) or 0
        if mid is None or int(mid) not in aaa or pa < afe.MIN_POOL_PA:
            continue
        core_vals = {c: afe._f(r.get(c)) for c in CORE}
        if any(v is None for v in core_vals.values()):
            continue
        vals = dict(core_vals)
        for c in EXTRAS:
            vals[c] = afe._f(r.get(c))
        per.append((int(mid), vals))
        for c, v in vals.items():
            if v is not None:
                cols[c].append(v)
    if len(per) < 30:
        return {}
    import statistics as st
    stats = {c: (st.mean(v), st.pstdev(v) or 1.0)
             for c, v in cols.items() if len(v) >= 30}
    out: dict[int, dict] = {}
    for mid, vals in per:
        zs = {}
        for c in comps:
            v = vals.get(c)
            if v is None or c not in stats:
                continue
            zs[c] = signs[c] * (v - stats[c][0]) / stats[c][1]
        comp_z = _mean([zs[c] for c in CORE])
        out[mid] = {"z": zs, "sc_plus_analog": round(100 + 10 * comp_z, 1)}
    return out


# ------------------------------------------------------------- records

def build_records() -> tuple[list[dict], dict, dict]:
    """One record per cohort-joined debut player:
    {side, season, mid, z, composite_z, rate (OPS / -ERA), war}.
    Join logic mirrors arkmetric_forward_eval.run (hitter-pool-first
    elif, min-PA / min-BF gates, WAR only for debut_year <= 2025)."""
    debuts = afe._load_debuts()
    with storage.connect() as con:
        cw = {}
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            cw[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}

    records: list[dict] = []
    pool_n: dict[str, dict[str, int]] = {}
    cohort_n: dict[str, int] = {}
    for season in SEASONS:
        debut_year = season + 1
        tab_h = component_z_table(season, "batter")
        tab_p = component_z_table(season, "pitcher")
        pool_n[str(season)] = {"batter": len(tab_h), "pitcher": len(tab_p)}
        mlb_h = mh.player_index(debut_year, "hitting", fetch=False)
        mlb_p = mh.player_index(debut_year, "pitching", fetch=False)
        n = 0
        for d in debuts:
            dd = d.get("debut_date") or ""
            mid = d.get("mlbam_id")
            if not mid or not dd or int(dd[:4]) != debut_year:
                continue
            mid = int(mid)
            if mid in tab_h:
                side, tab, mlb = "hit", tab_h, mlb_h
            elif mid in tab_p:
                side, tab, mlb = "pit", tab_p, mlb_p
            else:
                continue
            rec = {"side": side, "season": season, "mid": mid,
                   "z": tab[mid]["z"],
                   "composite_z": (tab[mid]["sc_plus_analog"] - 100) / 10,
                   "rate": None, "war": None}
            rows = [r for r in (mlb.get(mid) or []) if r["level"] == "MLB"]
            row = rows[0] if rows else None
            if side == "hit":
                ops = afe._f(row.get("ops")) if row else None
                pa = afe._f(row.get("pa")) if row else 0
                if ops is not None and (pa or 0) >= afe.MIN_PA:
                    rec["rate"] = ops
                    n += 1
            else:
                era = afe._f(row.get("era")) if row else None
                bf = afe._f(row.get("bf")) if row else 0
                if era is not None and (bf or 0) >= afe.MIN_BF:
                    rec["rate"] = -era   # invert: higher = better
                    n += 1
            if debut_year <= 2025:
                rec["war"] = afe._war_first2(d["player_key"], debut_year, cw)
            if rec["rate"] is not None or rec["war"] is not None:
                records.append(rec)
        cohort_n[f"{season}->{debut_year}"] = n
    return records, pool_n, cohort_n


def assert_parity() -> int:
    """My core-composite must equal arkmetric_forward_eval's
    sc_analog_index value-for-value (guards against silent divergence
    from the published composite)."""
    mismatches = 0
    for season in SEASONS:
        for side in ("batter", "pitcher"):
            ref = afe.sc_analog_index(season, side)
            mine = component_z_table(season, side)
            if set(ref) != set(mine):
                mismatches += len(set(ref) ^ set(mine))
                continue
            for mid, v in ref.items():
                if abs(mine[mid]["sc_plus_analog"] - v) > 1e-9:
                    mismatches += 1
    if mismatches:
        raise AssertionError(f"composite parity broken: {mismatches} mismatches")
    return mismatches


# ------------------------------------------------------------- analysis

def _corr_block(recs, comp, outcome_key):
    xs, ys = [], []
    for r in recs:
        y = r[outcome_key]
        x = r["composite_z"] if comp == "composite" else r["z"].get(comp)
        if x is None or y is None:
            continue
        xs.append(x)
        ys.append(y)
    r_ = _pearson(xs, ys)
    return {"n": len(xs), "r": r_, "rho": _spearman(xs, ys),
            "p_two_sided": _p_two_sided(r_, len(xs))}


def per_component_tables(records):
    comps = CORE + list(EXTRAS) + ["composite"]
    out = {}
    for side, rate_name in (("hit", "vs_first_mlb_ops"),
                            ("pit", "vs_first_mlb_era_inv")):
        recs = [r for r in records if r["side"] == side]
        out_side = {rate_name: {}, "vs_war_2y": {}}
        for c in comps:
            out_side[rate_name][c] = _corr_block(recs, c, "rate")
            out_side["vs_war_2y"][c] = _corr_block(recs, c, "war")
        out["hitters" if side == "hit" else "pitchers"] = out_side
    return out


def _classify(tbl_rate, tbl_war, comp):
    """Deterministic per-component read: signal / lean-signal / noise."""
    b = tbl_rate[comp]
    w = tbl_war[comp]
    r, p = b.get("r"), b.get("p_two_sided")
    if r is None:
        return "insufficient n"
    if p is not None and p < P_SIGNAL and r > 0:
        return "signal (p<%.2f on rate outcome)" % P_SIGNAL
    wr = w.get("r")
    if r > 0.10 and wr is not None and wr > 0:
        return "lean signal (r>0.10 both outcomes, not significant at n)"
    return "noise at these ns"


def blend_check(records):
    """Forward-chained: pick top-2 core components and weights on TRAIN
    cohorts only, score on the later TEST cohort, pool OOS rows across
    folds, compare against the equal-weight 4-component composite on
    identical rows."""
    out = {}
    for outcome_key, folds, label in (("rate", RATE_FOLDS, "rate_outcome"),
                                      ("war", WAR_FOLDS, "war_outcome")):
        block = {}
        for side, name in (("hit", "hitters"), ("pit", "pitchers")):
            recs = [r for r in records if r["side"] == side
                    and r[outcome_key] is not None]
            fold_rows = []
            pooled = {"xw": [], "xe": [], "xc": [], "y": []}
            for train_seasons, test_season in folds:
                train = [r for r in recs if r["season"] in train_seasons]
                test = [r for r in recs if r["season"] == test_season]
                train_r = {}
                for c in CORE:
                    xs = [r["z"][c] for r in train]
                    ys = [r[outcome_key] for r in train]
                    train_r[c] = _pearson(xs, ys)
                usable = [c for c in CORE if train_r[c] is not None]
                if len(usable) < 2 or len(test) < 2:
                    fold_rows.append({
                        "train_seasons": list(train_seasons),
                        "test_season": test_season,
                        "skipped": "insufficient n",
                        "train_n": len(train), "test_n": len(test)})
                    continue
                # deterministic: |r| desc, fixed CORE order breaks ties
                top2 = sorted(usable,
                              key=lambda c: (-abs(train_r[c]), CORE.index(c)))[:2]
                denom = sum(abs(train_r[c]) for c in top2) or 1.0
                w_r = {c: train_r[c] / denom for c in top2}
                w_eq = {c: (0.5 if train_r[c] >= 0 else -0.5) for c in top2}
                for r in test:
                    pooled["xw"].append(sum(w_r[c] * r["z"][c] for c in top2))
                    pooled["xe"].append(sum(w_eq[c] * r["z"][c] for c in top2))
                    pooled["xc"].append(r["composite_z"])
                    pooled["y"].append(r[outcome_key])
                ys_t = [r[outcome_key] for r in test]
                fold_rows.append({
                    "train_seasons": list(train_seasons),
                    "test_season": test_season,
                    "train_n": len(train), "test_n": len(test),
                    "train_r_by_component": {c: train_r[c] for c in CORE},
                    "top2": top2,
                    "weights_r_prop": {c: round(w_r[c], 4) for c in top2},
                    "r_test_blend_r_weighted": _pearson(
                        [sum(w_r[c] * r["z"][c] for c in top2) for r in test], ys_t),
                    "r_test_blend_top2_equal": _pearson(
                        [sum(w_eq[c] * r["z"][c] for c in top2) for r in test], ys_t),
                    "r_test_composite": _pearson(
                        [r["composite_z"] for r in test], ys_t),
                })
            block[name] = {
                "folds": fold_rows,
                "pooled_oos": {
                    "n": len(pooled["y"]),
                    "r_blend_r_weighted": _pearson(pooled["xw"], pooled["y"]),
                    "rho_blend_r_weighted": _spearman(pooled["xw"], pooled["y"]),
                    "r_blend_top2_equal": _pearson(pooled["xe"], pooled["y"]),
                    "r_composite": _pearson(pooled["xc"], pooled["y"]),
                    "rho_composite": _spearman(pooled["xc"], pooled["y"]),
                },
            }
        out[label] = block
    return out


def findings(per_comp, blend):
    """Headline answers, numbers interpolated from the computed tables
    (deterministic; regenerated on every run)."""
    h = per_comp["hitters"]["vs_first_mlb_ops"]
    hw = per_comp["hitters"]["vs_war_2y"]
    p = per_comp["pitchers"]["vs_first_mlb_era_inv"]
    pw = per_comp["pitchers"]["vs_war_2y"]
    bh = blend["rate_outcome"]["hitters"]["pooled_oos"]
    bp = blend["rate_outcome"]["pitchers"]["pooled_oos"]
    wh = blend["war_outcome"]["hitters"]["pooled_oos"]
    return {
        "which_component_carries_signal": {
            "hitters": f"Barrel%/BBE is the only core component with a "
                       f"meaningful forward r vs first-MLB OPS "
                       f"(r={h['barrels_per_bbe_percent']['r']}, "
                       f"p={h['barrels_per_bbe_percent']['p_two_sided']}); "
                       f"avg EV is a weak lean "
                       f"(r={h['launch_speed']['r']}); HardHit% "
                       f"(r={h['hardhit_percent']['r']}) and SwingMiss% "
                       f"(r={h['swing_miss_percent']['r']}, sign flips on "
                       f"the WAR join) are noise",
            "pitchers": f"SwingMiss% carries essentially all of it "
                        f"(r={p['swing_miss_percent']['r']} vs inverted "
                        f"first-MLB ERA, "
                        f"p={p['swing_miss_percent']['p_two_sided']}); all "
                        f"three contact-against components are noise, with "
                        f"Barrel%-against mildly wrong-signed "
                        f"(r={p['barrels_per_bbe_percent']['r']})",
        },
        "reference_components_outperform": (
            f"plain K% beats the whole contact composite for pitchers "
            f"(r={p['k_percent']['r']} vs composite "
            f"{p['composite']['r']}), and BB% does for hitters "
            f"(r={h['bb_percent']['r']} vs composite "
            f"{h['composite']['r']}); on the 2y-bWAR join Savant xwOBA "
            f"beats the composite on both sides "
            f"(hit {hw['xwoba']['r']} vs {hw['composite']['r']}, "
            f"pit {pw['xwoba']['r']} vs {pw['composite']['r']}). The weak "
            f"part of SC+ is the contact-quality framing, not the Savant "
            f"source data"),
        "blend_vs_composite_oos": (
            f"the forward-chained top-2 reweight is directionally positive "
            f"on rate outcomes (hitters r {bh['r_blend_r_weighted']} vs "
            f"composite {bh['r_composite']}, gain "
            f"{round((bh['r_blend_r_weighted'] or 0) - (bh['r_composite'] or 0), 4)}; "
            f"pitchers {bp['r_blend_r_weighted']} vs {bp['r_composite']}, "
            f"gain "
            f"{round((bp['r_blend_r_weighted'] or 0) - (bp['r_composite'] or 0), 4)}) "
            f"but misses the pre-registered +0.05 bar on the pitcher side "
            f"and REVERSES on the hitter 2y-bWAR join (blend "
            f"{wh['r_blend_r_weighted']} vs composite {wh['r_composite']}), "
            f"so the reweight is not robust at these ns"),
    }


def recommendation(per_comp, blend):
    """Deterministic decision rule, documented in the artifact."""
    rate_key = {"hitters": "vs_first_mlb_ops", "pitchers": "vs_first_mlb_era_inv"}
    comp_r = {s: per_comp[s][rate_key[s]]["composite"]["r"] for s in rate_key}
    gains = {}
    for s in ("hitters", "pitchers"):
        po = blend["rate_outcome"][s]["pooled_oos"]
        rb, rc = po.get("r_blend_r_weighted"), po.get("r_composite")
        gains[s] = (None if rb is None or rc is None else round(rb - rc, 4))
    both_gain = all(g is not None and g >= BLEND_IMPROVE_MIN
                    and (blend["rate_outcome"][s]["pooled_oos"]["r_blend_r_weighted"]
                         or 0) >= 0.10
                    for s, g in gains.items())
    both_dead = all(r is not None and abs(r) < DEMOTE_R_MAX
                    for r in comp_r.values())
    if both_gain:
        decision = "reweight"
    elif both_dead:
        decision = "demote"
    else:
        decision = "keep composite as-is"
    return {
        "decision": decision,
        "rule": ("reweight if the forward-chained 2-component blend beats the "
                 f"composite by >= {BLEND_IMPROVE_MIN} pooled-OOS r on BOTH "
                 "sides (blend r >= 0.10); demote if the composite's pooled "
                 f"forward r is under {DEMOTE_R_MAX} in absolute value on both "
                 "sides; otherwise keep as-is"),
        "oos_gain_blend_minus_composite": gains,
        "composite_pooled_r_rate": comp_r,
    }


# ------------------------------------------------------------------ run

def run(persist: bool = True) -> dict:
    assert_parity()
    records, pool_n, cohort_n = build_records()
    per_comp = per_component_tables(records)
    blend = blend_check(records)
    rec = recommendation(per_comp, blend)

    reads = {}
    for s, rk in (("hitters", "vs_first_mlb_ops"),
                  ("pitchers", "vs_first_mlb_era_inv")):
        reads[s] = {c: _classify(per_comp[s][rk], per_comp[s]["vs_war_2y"], c)
                    for c in CORE}

    out = {
        "generated_at": date.today().isoformat(),
        "tool": "tools/sc_plus_component_eval.py",
        "method": {
            "basis": "arkmetric_forward_eval cohort construction reused "
                     "exactly (AAA pool, min 100 PA/BF, debut year = pool "
                     "season + 1, hitter-pool-first join); composite parity "
                     "with sc_analog_index asserted value-for-value at "
                     "runtime",
            "components": {
                "core": CORE,
                "reference_only": list(EXTRAS),
                "signs": {"core": CORE_SIGNS, "reference": EXTRA_SIGNS},
                "note": "each component is z-scored within its season-side "
                        "AAA pool with the SC+ sign convention, so pooled "
                        "correlations across seasons are pool-relative; "
                        "reference components come from the same Savant "
                        "aggregates but are not SC+ inputs and are excluded "
                        "from the blend search",
            },
            "outcomes": "first-MLB-season OPS (>=100 PA) / ERA (>=100 BF, "
                        "inverted so higher = better); first-2y bWAR "
                        "(debut years 2024-2025 only, 2026 window open)",
            "blend": "forward-chained: top-2 core components and weights "
                     "(proportional to train r, plus an equal-weight "
                     "variant) fit on earlier cohorts only, scored on the "
                     "next cohort; OOS rows pooled across folds and "
                     "compared to the equal-weight 4-component composite "
                     "on identical rows; no refit leakage",
            "p_values": "Fisher-z approximation, two-sided; treat as rough "
                        "at these ns",
            "determinism": "no RNG anywhere; component ties break on fixed "
                           "component order (seedless by construction)",
        },
        "pools": pool_n,
        "cohort_n": cohort_n,
        "per_component": per_comp,
        "component_read": reads,
        "blend_check": blend,
        "findings": findings(per_comp, blend),
        "recommendation": rec,
        "caveats": [
            "ns are small (about 50 per side on rate outcomes, about 100 "
            "on the 2y-bWAR join); single-component r differences under "
            "0.15 are not individually significant here",
            "the 2025->2026 test fold is thin (2026 debut season in "
            "progress), so pooled OOS leans on the 2024->2025 fold",
            "this scores the 4-component historical analog, not the live "
            "6-component SC+ (Z-Contact/Chase have no historical source)",
        ],
    }
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    rep = run()
    print("pools:", rep["pools"])
    print("cohorts:", rep["cohort_n"])
    for side in ("hitters", "pitchers"):
        print(f"-- {side} --")
        for outc, tbl in rep["per_component"][side].items():
            print(" ", outc)
            for c, b in tbl.items():
                print(f"    {c:28s} r={b['r']!s:8s} rho={b['rho']!s:8s} "
                      f"n={b['n']:<4d} p={b['p_two_sided']}")
        print("  reads:", rep["component_read"][side])
        po = rep["blend_check"]["rate_outcome"][side]["pooled_oos"]
        print("  pooled OOS (rate):", po)
    print("recommendation:", rep["recommendation"]["decision"])
    print("wrote", OUT_PATH)
