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

# The keep/reweight DECISION reads only outcome seasons that are closed:
# debut-2026 first-season rates are in progress and drift with every stats
# refresh, so a decision computed on them is a moving target (2026-07 audit
# finding). Full-pool numbers are still reported for context.
DECISION_MAX_DEBUT_YEAR = 2025


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
    """{mlbam: {"z": {comp: signed z}, "sc_plus_analog": 100+10z/sd}} for
    one AAA season pool, sd being the pool's own composite sd. Core-component pool membership and z math mirror
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
    zrows: list[tuple[int, dict, float]] = []
    for mid, vals in per:
        zs = {}
        for c in comps:
            v = vals.get(c)
            if v is None or c not in stats:
                continue
            zs[c] = signs[c] * (v - stats[c][0]) / stats[c][1]
        zrows.append((mid, zs, _mean([zs[c] for c in CORE])))
    # Composite scale: arkmetric_forward_eval.sc_analog_index divides the
    # equal-weight mean by the pool's own composite sd since a953ddc0
    # (2026-08-07, the SC+ rescale). This copy kept the old 100 + 10z and
    # failed the parity check on 3,537 of 3,588 rows; it mirrors the same
    # divisor and guard here. Component z values are unchanged.
    sd = (st.pstdev([z for _, _, z in zrows]) if len(zrows) > 1 else 1.0)
    if sd <= 1e-9:
        sd = 1.0
    out: dict[int, dict] = {}
    for mid, zs, comp_z in zrows:
        out[mid] = {"z": zs,
                    "sc_plus_analog": round(100 + 10 * (comp_z / sd), 1)}
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
            pooled_closed = {"xw": [], "xe": [], "xc": [], "y": []}
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
                closed_fold = (test_season + 1) <= DECISION_MAX_DEBUT_YEAR
                for r in test:
                    pooled["xw"].append(sum(w_r[c] * r["z"][c] for c in top2))
                    pooled["xe"].append(sum(w_eq[c] * r["z"][c] for c in top2))
                    pooled["xc"].append(r["composite_z"])
                    pooled["y"].append(r[outcome_key])
                    if closed_fold:
                        pooled_closed["xw"].append(pooled["xw"][-1])
                        pooled_closed["xe"].append(pooled["xe"][-1])
                        pooled_closed["xc"].append(pooled["xc"][-1])
                        pooled_closed["y"].append(pooled["y"][-1])
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
                # Decision instrument: closed outcome seasons only (stable
                # under stats refreshes; see DECISION_MAX_DEBUT_YEAR).
                "pooled_oos_closed": {
                    "n": len(pooled_closed["y"]),
                    "r_blend_r_weighted": _pearson(pooled_closed["xw"], pooled_closed["y"]),
                    "r_blend_top2_equal": _pearson(pooled_closed["xe"], pooled_closed["y"]),
                    "r_composite": _pearson(pooled_closed["xc"], pooled_closed["y"]),
                },
            }
        out[label] = block
    return out


LABELS = {"launch_speed": "avg EV", "hardhit_percent": "HardHit%",
          "barrels_per_bbe_percent": "Barrel%/BBE",
          "swing_miss_percent": "SwingMiss%", "xwoba": "xwOBA",
          "k_percent": "K%", "bb_percent": "BB%"}


def _join(names):
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _beats(a, b):
    """Comparison word derived from the two numbers (2026-10-08: the
    2026-07-02 prose hardcoded 'beats', 'directionally positive' and 'misses
    the bar', and three of those went false on the next run)."""
    if a is None or b is None:
        return "cannot be compared with"
    return "beats" if a > b else "does not beat"


def _component_sentence(tbl_rate, tbl_war, outcome):
    groups = {"signal": [], "lean": [], "noise": []}
    for c in CORE:
        read = _classify(tbl_rate, tbl_war, c)
        key = ("signal" if read.startswith("signal")
               else "lean" if read.startswith("lean") else "noise")
        b = tbl_rate[c]
        flip = (b.get("r") is not None and tbl_war[c].get("r") is not None
                and (b["r"] > 0) != (tbl_war[c]["r"] > 0))
        txt = f"{LABELS[c]} (r={b['r']}"
        if key == "signal":
            txt += f", p={b['p_two_sided']}"
        if flip:
            txt += ", sign flips on the WAR join"
        groups[key].append(txt + ")")
    parts = []
    if groups["signal"]:
        parts.append(f"{_join(groups['signal'])} "
                     f"{'carries' if len(groups['signal']) == 1 else 'carry'} "
                     f"the forward signal vs {outcome} (p<{P_SIGNAL:.2f})")
    else:
        parts.append(f"no core component clears p<{P_SIGNAL:.2f} vs {outcome}")
    if groups["lean"]:
        parts.append(f"{_join(groups['lean'])} "
                     f"{'is a weak lean' if len(groups['lean']) == 1 else 'are weak leans'}")
    if groups["noise"]:
        parts.append(f"{_join(groups['noise'])} "
                     f"{'is' if len(groups['noise']) == 1 else 'are'} noise at these ns")
    return "; ".join(parts)


def findings(per_comp, blend):
    """Headline answers. Every number AND every comparison word is derived
    from the computed tables (deterministic; regenerated on every run)."""
    h = per_comp["hitters"]["vs_first_mlb_ops"]
    hw = per_comp["hitters"]["vs_war_2y"]
    p = per_comp["pitchers"]["vs_first_mlb_era_inv"]
    pw = per_comp["pitchers"]["vs_war_2y"]
    bh = blend["rate_outcome"]["hitters"]["pooled_oos"]
    bp = blend["rate_outcome"]["pitchers"]["pooled_oos"]
    wh = blend["war_outcome"]["hitters"]["pooled_oos"]

    def _gain(b):
        return round((b["r_blend_r_weighted"] or 0) - (b["r_composite"] or 0), 4)

    gh, gp = _gain(bh), _gain(bp)
    clears = [s for s, g in (("hitter", gh), ("pitcher", gp))
              if g >= BLEND_IMPROVE_MIN]
    misses = [s for s, g in (("hitter", gh), ("pitcher", gp))
              if g < BLEND_IMPROVE_MIN]
    war_rev = ((wh["r_blend_r_weighted"] or 0) < (wh["r_composite"] or 0))
    bar = f"+{BLEND_IMPROVE_MIN:.2f}"
    if misses:
        bar_txt = (f"misses the pre-registered {bar} bar on the "
                   f"{_join(misses)} side{'s' if len(misses) > 1 else ''}")
        if clears:
            bar_txt = (f"clears the {bar} bar on the {_join(clears)} side "
                       f"but " + bar_txt)
    else:
        bar_txt = f"clears the pre-registered {bar} bar on both sides"
    war_txt = (f"{'REVERSES' if war_rev else 'holds'} on the hitter 2y-bWAR "
               f"join (blend {wh['r_blend_r_weighted']} vs composite "
               f"{wh['r_composite']})")
    robust = (not misses) and not war_rev
    xw_sides = [s for s, t in (("hit", hw), ("pit", pw))
                if (t["xwoba"]["r"] or 0) > (t["composite"]["r"] or 0)]
    xw_word = ("beats the composite on both sides" if len(xw_sides) == 2
               else "beats the composite on one side only" if xw_sides
               else "does not beat the composite on either side")
    return {
        "which_component_carries_signal": {
            "hitters": _component_sentence(
                h, hw, "first-MLB OPS"),
            "pitchers": _component_sentence(
                p, pw, "inverted first-MLB ERA"),
        },
        "reference_components_outperform": (
            f"plain K% {_beats(p['k_percent']['r'], p['composite']['r'])} "
            f"the whole contact composite for pitchers "
            f"(r={p['k_percent']['r']} vs composite {p['composite']['r']}); "
            f"BB% {_beats(h['bb_percent']['r'], h['composite']['r'])} it "
            f"for hitters (r={h['bb_percent']['r']} vs composite "
            f"{h['composite']['r']}); on the 2y-bWAR join Savant xwOBA "
            f"{xw_word} "
            f"(hit {hw['xwoba']['r']} vs {hw['composite']['r']}, "
            f"pit {pw['xwoba']['r']} vs {pw['composite']['r']})"),
        "blend_vs_composite_oos": (
            f"on all pooled out-of-sample rows (open 2026 season included) "
            f"the forward-chained top-2 reweight reads hitters r "
            f"{bh['r_blend_r_weighted']} vs composite {bh['r_composite']} "
            f"(gain {gh}) and pitchers {bp['r_blend_r_weighted']} vs "
            f"{bp['r_composite']} (gain {gp}); it {bar_txt} and {war_txt}, "
            f"so the reweight is "
            f"{'consistent' if robust else 'not robust'} at these ns. The "
            f"decision reads the closed-season rows (see recommendation)"),
    }


def recommendation(per_comp, blend):
    """Deterministic decision rule, documented in the artifact."""
    rate_key = {"hitters": "vs_first_mlb_ops", "pitchers": "vs_first_mlb_era_inv"}
    comp_r = {s: per_comp[s][rate_key[s]]["composite"]["r"] for s in rate_key}
    gains = {}
    for s in ("hitters", "pitchers"):
        po = (blend["rate_outcome"][s].get("pooled_oos_closed")
              or blend["rate_outcome"][s]["pooled_oos"])
        rb, rc = po.get("r_blend_r_weighted"), po.get("r_composite")
        gains[s] = (None if rb is None or rc is None else round(rb - rc, 4))
    both_gain = all(g is not None and g >= BLEND_IMPROVE_MIN
                    and ((blend["rate_outcome"][s].get("pooled_oos_closed")
                          or blend["rate_outcome"][s]["pooled_oos"])
                         .get("r_blend_r_weighted") or 0) >= 0.10
                    for s, g in gains.items())
    both_dead = all(r is not None and abs(r) < DEMOTE_R_MAX
                    for r in comp_r.values())
    if both_gain:
        # The rule fires, but this tool is a DIAGNOSTIC, not a pre-registered
        # ship gate: changing the published SC+ composite requires its own
        # gated experiment (registry row + eval artifact + freshness map),
        # and the closed-basis pool (n ~ 23/side) is far below any shippable
        # bar. The candidate is queued, the shipped composite stays.
        decision = "reweight-candidate (queued; composite unchanged)"
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
                 "sides; otherwise keep as-is. Decision inputs use CLOSED "
                 f"outcome seasons only (debut <= {DECISION_MAX_DEBUT_YEAR}); "
                 "open-season rows appear in pooled_oos for context but do "
                 "not move the decision"),
        "decision_basis": f"pooled_oos_closed (debut <= {DECISION_MAX_DEBUT_YEAR})",
        "shipping_note": ("a reweight of the published SC+ composite ships only "
                          "through a dedicated pre-registered gated experiment "
                          "(see docs/archive/REVIEW_QUEUE.md); this artifact records the "
                          "candidate signal, it does not authorize the change"),
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

    def _n(side, outcome):
        return per_comp[side][outcome]["composite"]["n"]

    def _open_n(side):
        for f in blend["rate_outcome"][side]["folds"]:
            if f["test_season"] + 1 > DECISION_MAX_DEBUT_YEAR:
                return f.get("test_n")
        return 0

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
            # ns derived from the tables (the 2026-07-02 text said "about
            # 50" and "thin" and went stale as the open season filled in)
            f"ns are small ({_n('hitters', 'vs_first_mlb_ops')} hitters / "
            f"{_n('pitchers', 'vs_first_mlb_era_inv')} pitchers on rate "
            f"outcomes, {_n('hitters', 'vs_war_2y')} / "
            f"{_n('pitchers', 'vs_war_2y')} on the 2y-bWAR join); "
            "single-component r differences under 0.15 are not "
            "individually significant here",
            f"the 2025->2026 test fold reads an open outcome season (2026 "
            f"debuts, test n {_open_n('hitters')} hitters / "
            f"{_open_n('pitchers')} pitchers) and moves with every stats "
            "refresh; pooled_oos includes it, the decision does not",
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
