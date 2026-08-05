# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MEASUREMENT ONLY - the rest-of-season TALENT BASIS, shipped vs the
alternatives.  (lane A2b, 2026-08-04d; re-pointed at the shipped operator
2026-08-05.)

THE QUESTION.  proj_export's rest-of-season leg prices the balance of the
IN-PROGRESS season (2026).  Until 2026-08-05 it priced it off `war[0]`, which is
the FIRST_SEASON (2027) projection - one full aging year PAST the season
actually being sold.  For an aging veteran that is a real, signed bias: his 2026
talent is a shade ABOVE his 2027 projection, so the remainder he is traded on
was systematically underpriced.  The old in-code comment chose war[0] on purpose
("deliberately does not read 2026 results to date, which measure what the
SELLING club already banked"), and that reasoning is sound about BANKED
PRODUCTION but silent about TALENT TIMING: the question here is only which
season's talent estimate the remainder is priced on, not whether to re-bank
April.

WHAT SHIPPED (owner decision, 2026-08-05): the de-aged basis, i.e. `deaged_full`
below.  See proj_export.ROS_TALENT_BASIS and
docs/ros-talent-basis-2026-08-05/DECISION.md, which records the executing
agent's dissent on MAGNITUDE.  THIS SCRIPT STILL CHANGES NOTHING; it measures.

THE DE-AGING IS THE CODEBASE'S OWN FITTED CURVE, NOT A CONSTANT.  fa_market's
`_decay_path` is the only WAR aging operator in the tree: moving INTO age a it
adds `fp.curve_delta(curves, side, decay_role, "war_rate", a)` to the
per-600-PA / per-250-BF WAR RATE and `curve_delta(..., "pt", a)` to the
projected exposure, then re-multiplies.  Both deltas are ADDITIVE, so the step
is exactly invertible: to walk one year BACK from age a, subtract the same two
deltas evaluated at a.  Each veteran's year-1 (rate, exposure) is rebuilt from
the same Marcel call proj_export makes, that one step is inverted, and the ratio
to his champion year-1 WAR is applied to the SHIPPED `war[0]`, so the ML
quantile head's information survives and only the aging timing moves.

ONE OPERATOR, ONE COPY.  The arithmetic above is NOT reimplemented here: it is
`proj_export.deaged_year1`, the exact function production prices with, imported
below.  This probe and the shipped leg cannot drift apart; if the operator
changes, these numbers change with it.

Curves and corpus are read from the on-disk caches (`.cache/fa_corpus.pkl`,
`.cache/fa_fits_*.pkl`); nothing is refetched, refit or rewritten.  The only
file written is `data/ros_talent_basis_probe.json`.

TWO VARIANTS, because the exposure leg is the aggressive half:
  * `deaged_full` - un-ages BOTH the WAR rate and the playing-time projection.
    Faithful inverse of `_decay_path`.  For a 34-year-old starter the fitted pt
    delta is large (~-127 BF/yr), so this variant moves a lot.  THIS IS WHAT
    SHIPS.
  * `deaged_rate`  - un-ages the WAR RATE only, holding the Marcel exposure
    projection fixed.  Defensible on its own terms: the year-1 PT projection is
    already fit on what the player is doing THIS season, so it is arguably not
    stale the way the rate is.  NOT a switchable production basis - it is the
    obvious step-down if the shipped magnitude is later gated back.

Plus the two bases already published on every row, for reference:
  * `warPTH[0]`    - the if-healthy (playing-time-held) display path.
  * `warY1Champ`   - the champion (non-ML) mean year-1.

SALARY CANCELS.  Under the shipped-after-A2 convention the leg is
f * (V(w) - salary), so changing only the talent basis moves surTotal by exactly
f * (V(w_alt) - V(w_ship)).  That is why this probe needs no contract file.

BASELINE.  The comparison baseline is the FIRST_SEASON basis - what the leg
priced before 2026-08-05 - reconstructed from the served row.  If the artifact
on disk predates the A2a proration fix (production leg V(f*w) instead of
f*V(w)), the convexity correction f*V(w) - V(f*w) is added so the baseline is
still "what the next export would print"; the probe DETECTS which convention the
artifact carries instead of assuming, and reports it.

UNRESOLVED ROWS are reported, never silently given a 1.0 multiplier.  Production
falls back to the first_season basis for them and labels the served row
`rosBasis="first_season_unresolved"`; this probe scores them at zero delta,
which is the same thing.

Usage:  python tools/ros_talent_basis_probe.py
"""

from __future__ import annotations

import json
import pickle
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fa_projection as fp          # noqa: E402
import proj_export as pe            # noqa: E402
import value_framework as vf        # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "ros_talent_basis_probe.json"
CORPUS_PKL = ROOT / ".cache" / "fa_corpus.pkl"


def _season_value_usd(war: float, dpw: float) -> float:
    """proj_export._season_value_usd at t=0 (the rest-of-season leg's own t)."""
    base_flat = float(vf._config()["dollars_per_war"]["flat"])
    return vf.tiered_war_value_usd(war) * (dpw / base_flat)


def _deage_ratios(first_season: int, wanted: set[int]) -> dict[int, dict]:
    """{mlbam: {ratio_full, ratio_rate, war1_champ, sides:[...]}} - the one-year
    inverse of `_decay_path` for every requested veteran.

    THE OPERATOR IS `proj_export.deaged_year1`, the shipped one, called twice
    per player (full inverse and rate-only). Nothing about the aging arithmetic
    or the per-side universe gate is re-implemented here, so this probe cannot
    measure something other than what production prices.

    Inputs are the SAME ones proj_export builds from (cached corpus, cached
    fits, same three-season history window, same in-progress fraction), so the
    champion year-1 this reproduces is the row's own warY1Champ.

    Players whose de-aging is UNRESOLVED (the champion year-1 is at or below
    proj_export.DEAGE_MIN_CHAMP_WAR, so a multiplicative ratio is undefined) are
    ABSENT from the returned map - never present with a 1.0 ratio.
    """
    if not CORPUS_PKL.exists():
        return {}
    with open(CORPUS_PKL, "rb") as fh:
        corpus = pickle.load(fh)
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, first_season - 1)
    in_prog = (first_season - 1, fp.season_fraction(league, first_season - 1))

    by: dict[tuple[str, int], dict[int, dict]] = defaultdict(dict)
    for side in ("hit", "pit"):
        for row in corpus[side]:
            mid = row.get("mlbam")
            if mid in wanted and row["season"] >= first_season - 3:
                by[(side, mid)][row["season"]] = row

    out: dict[int, dict] = {}
    for mid in wanted:
        hist_by_side = {}
        for side in ("hit", "pit"):
            hist = pe.recent_history(by.get((side, mid)) or {}, first_season)
            if hist:
                hist_by_side[side] = hist
        full = pe.deaged_year1(hist_by_side, first_season, curves, war_map,
                               league, in_prog)
        if full is None:
            continue                       # unresolved - reported, not imputed
        rate = pe.deaged_year1(hist_by_side, first_season, curves, war_map,
                               league, in_prog, rate_only=True)
        out[mid] = {"ratio_full": full["ratio"],
                    "ratio_rate": (rate or full)["ratio"],
                    "war1_champ": round(full["war1_champ"], 3),
                    "sides": full["sides"]}
    return out


def _priced_basis_war(v: dict) -> float | None:
    """The full-season talent the served row's rest-of-season leg was priced on.

    `rosWar` is published as basis_war * rosFrac under EVERY basis (that is the
    invariant proj_export keeps: the display WAR describes the same talent the
    dollars do), so dividing it back out recovers the basis without knowing
    which one produced it. Falls back to war[0] for artifacts old enough to
    predate `rosWar`.
    """
    f = v.get("rosFrac")
    rw = v.get("rosWar")
    if f and rw is not None:
        return float(rw) / float(f)
    war = v.get("war") or []
    return float(war[0]) if war and war[0] is not None else None


def _artifact_predates_the_proration_fix(vets: list[dict], dpw: float,
                                         first: int) -> bool | None:
    """Does the served artifact price the RoS production leg as V(f*w) (the
    pre-2026-08-04d form) or f*V(w)?

    DETECTED, NOT ASSUMED. A single-season (expiring) contract's `aav` IS its
    current-season salary, so for those rows the leg can be recomputed from
    published fields alone; rows where the two conventions differ by less than
    the 0.1M publication rounding are not decisive and are skipped. Returns None
    when too few decisive rows exist to tell, in which case no correction is
    applied and the report says so.
    """
    new = old = 0
    for v in vets:
        f, aav, war = v.get("rosFrac"), v.get("aav"), (v.get("war") or [])
        if (not f or aav is None or not war or war[0] is None
                or v.get("thru") != first - 1 or v.get("surRos") is None):
            continue
        f, sal = float(f), float(aav)
        # The talent the row was ACTUALLY priced on, recovered from the row
        # itself (rosWar == basis_war * f under every basis this file knows).
        # Reading war[0] here would misread a de-aged artifact as "neither".
        w = _priced_basis_war(v)
        if w is None:
            continue
        got = float(v["surRos"]) * 1e6
        n_usd = f * (_season_value_usd(w, dpw) - sal)
        o_usd = _season_value_usd(w * f, dpw) - sal * f
        if abs(n_usd - o_usd) <= 250_000:
            continue
        if abs(got - n_usd) <= 60_000:
            new += 1
        elif abs(got - o_usd) <= 60_000:
            old += 1
    if new + old < 5:
        return None
    return old > new


def _pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def _age_profile(vets: list[dict], ratios: dict[int, dict]) -> dict:
    """Median de-aging multiplier by age - the shape the whole argument turns
    on. Monotone in age is the claim the DIRECTION rests on; the LEVEL at the
    top ages is the claim the recorded dissent is about, so both ship here
    rather than in prose that can go stale."""
    by_age: dict[int, list[float]] = defaultdict(list)
    for v in vets:
        mid, age = v.get("mlbam"), v.get("age")
        r = ratios.get(int(mid)) if mid else None
        if r is None or age is None:
            continue
        by_age[int(age)].append(r["ratio_full"])
    return {str(a): {"n": len(vals), "median_multiplier": round(st.median(vals), 3),
                     "n_over_1p5": sum(1 for x in vals if x > 1.5)}
            for a, vals in sorted(by_age.items())}


def _summary(deltas: list[float]) -> dict:
    if not deltas:
        return {"n": 0}
    return {
        "n": len(deltas),
        "n_up": sum(1 for d in deltas if d > 0.5),
        "n_down": sum(1 for d in deltas if d < -0.5),
        "min_usd": int(min(deltas)),
        "p10_usd": int(_pct(deltas, 0.10)),
        "median_usd": int(st.median(deltas)),
        "mean_usd": int(st.mean(deltas)),
        "p90_usd": int(_pct(deltas, 0.90)),
        "max_usd": int(max(deltas)),
        "sum_usd": int(sum(deltas)),
    }


def main() -> int:
    proj = json.loads((DATA / "mlb_projections.json").read_text(encoding="utf-8"))
    first = int(proj["first_season"])
    dpw = float(proj["dpw_usd"])
    vets = [v for v in (proj.get("vets") or [])
            if v.get("rosFrac") and (v.get("war") or [None])[0] is not None]
    wanted = {int(v["mlbam"]) for v in vets if v.get("mlbam")}
    ratios = _deage_ratios(first, wanted)

    pre_a2a = _artifact_predates_the_proration_fix(vets, dpw, first)

    bases = ("deaged_full", "deaged_rate", "warPTH0", "warY1Champ")
    deltas: dict[str, list[float]] = {b: [] for b in bases}
    flips: dict[str, list] = {b: [] for b in bases}
    rows: list[dict] = []
    unresolved = 0

    for v in vets:
        f = float(v["rosFrac"])
        w0 = float(v["war"][0])
        mid = v.get("mlbam")
        r = ratios.get(int(mid)) if mid else None
        served = v.get("surTotal")
        if served is None:
            continue
        # BASELINE = the FIRST_SEASON basis (war[0], un-de-aged), which is what
        # the leg priced before 2026-08-05. Recovered from the served row rather
        # than assumed: back out whatever talent the row was priced on and
        # re-price it on war[0]. Salary cancels, so only the value term moves.
        # When the artifact ALSO predates the A2a proration fix, add the
        # convexity correction f*V(w) - V(f*w) on top, so the baseline is still
        # "what an export of the old basis would print today".
        w_priced = _priced_basis_war(v)
        v0 = _season_value_usd(w0, dpw)
        base = float(served) + (v0 - _season_value_usd(w_priced, dpw)) * f
        if pre_a2a:
            base += (f * _season_value_usd(w_priced, dpw)
                     - _season_value_usd(w_priced * f, dpw))
        alt_war = {
            "deaged_full": (w0 * r["ratio_full"]) if r else None,
            "deaged_rate": (w0 * r["ratio_rate"]) if r else None,
            "warPTH0": (float(v["warPTH"][0]) if v.get("warPTH") else None),
            "warY1Champ": (float(v["warY1Champ"])
                           if v.get("warY1Champ") is not None else None),
        }
        if r is None:
            unresolved += 1
        row = {"key": v.get("key"), "name": v.get("name"), "pos": v.get("pos"),
               "age": v.get("age"), "war0": round(w0, 2),
               "rosFrac": f, "surTotal_baseline": int(base)}
        for b in bases:
            w_alt = alt_war[b]
            if w_alt is None:
                continue
            d = f * (_season_value_usd(w_alt, dpw) - v0)
            deltas[b].append(d)
            row[f"war_{b}"] = round(w_alt, 3)
            row[f"delta_{b}_usd"] = int(d)
            row[f"surTotal_{b}"] = int(base + d)
            if (base < 0) != ((base + d) < 0):
                flips[b].append({"key": v.get("key"), "name": v.get("name"),
                                 "from": int(base), "to": int(base + d)})
        rows.append(row)

    out = {
        "generated_for": ("lane A2b (2026-08-04d), re-pointed 2026-08-05 at the "
                          "SHIPPED operator - MEASUREMENT ONLY, changes nothing"),
        "first_season": first,
        "ros_fraction": proj.get("ros_fraction"),
        "dpw_usd": dpw,
        "shipped_basis": pe.ROS_TALENT_BASIS,
        "shipped_basis_probe_name": "deaged_full",
        "artifact_ros_talent_basis": proj.get("ros_talent_basis") or "first_season (unstamped)",
        "artifact_predates_proration_fix": pre_a2a,
        "n_vet_rows_with_ros_leg": len(rows),
        "n_deaging_unresolved": unresolved,
        "unresolved_policy": ("production falls back to the first_season basis "
                              "and ships rosBasis='first_season_unresolved'; "
                              "here they score zero delta, which is the same "
                              "thing. Never a silent 1.0 multiplier."),
        "baseline": ("the FIRST_SEASON basis (war[0]), re-derived from the "
                     "served row" + (" plus the A2a convexity correction "
                                     "f*V(w) - V(f*w)" if pre_a2a else "")),
        "de_aging_operator": ("inverse of fa_market._decay_path at the player's "
                              "own age: rate -= curve_delta(war_rate, a), "
                              "expo -= curve_delta(pt, a) (deaged_full); "
                              "rate only (deaged_rate)"),
        "summary": {b: _summary(deltas[b]) for b in bases},
        # The population effect of what SHIPPED, over EVERY row carrying the leg
        # - unresolved rows included at their policy value of exactly zero. The
        # per-basis `summary` above conditions on the basis being computable,
        # which flatters it by dropping 134 deliberate no-ops.
        "shipped_effect_all_rows": _summary(
            [float(r.get("delta_deaged_full_usd", 0)) for r in rows]),
        "deaging_multiplier_by_age": _age_profile(vets, ratios),
        "sign_flips": {b: {"n": len(flips[b]), "rows": flips[b][:25]}
                       for b in bases},
        "top_movers": {},
        "rows": rows,
    }
    for b in bases:
        rk = f"delta_{b}_usd"
        movers = sorted((r for r in rows if rk in r),
                        key=lambda r: -abs(r[rk]))[:15]
        out["top_movers"][b] = [{"name": r["name"], "pos": r["pos"],
                                 "age": r["age"], "war0": r["war0"],
                                 "war_alt": r.get(f"war_{b}"),
                                 "delta_usd": r[rk],
                                 "surTotal_before": r["surTotal_baseline"],
                                 "surTotal_after": r[f"surTotal_{b}"]}
                                for r in movers]

    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")

    print(f"rows with a rest-of-season leg: {len(rows)}  "
          f"(de-aging unresolved on {unresolved})")
    print(f"shipped basis: {pe.ROS_TALENT_BASIS}  (probe name: deaged_full)   "
          f"artifact basis stamp: {out['artifact_ros_talent_basis']}   "
          f"pre-A2a artifact: {pre_a2a}")
    _sa = out["shipped_effect_all_rows"]
    print("SHIPPED effect over ALL %d rows (unresolved counted at 0): "
          "median %+d  mean %+d  p90 %+d  max %+d  sum %+d"
          % (_sa["n"], _sa["median_usd"], _sa["mean_usd"], _sa["p90_usd"],
             _sa["max_usd"], _sa["sum_usd"]))
    for b in bases:
        s = out["summary"][b]
        if not s.get("n"):
            continue
        print(f"\n{b}: n={s['n']} up={s['n_up']} down={s['n_down']} "
              f"sign_flips={len(flips[b])}")
        print("  delta USD  min %d  p10 %d  median %d  mean %d  p90 %d  max %d"
              % (s["min_usd"], s["p10_usd"], s["median_usd"], s["mean_usd"],
                 s["p90_usd"], s["max_usd"]))
        print("  top 15 movers by |delta|:")
        for m in out["top_movers"][b]:
            print("    %-26s %-4s age %-4s war0 %5.2f -> %6.3f  "
                  "delta %+11d  surTotal %+12d -> %+12d"
                  % (m["name"][:26], m["pos"], m["age"], m["war0"],
                     m["war_alt"], m["delta_usd"], m["surTotal_before"],
                     m["surTotal_after"]))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
