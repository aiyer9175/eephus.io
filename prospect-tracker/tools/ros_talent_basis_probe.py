# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MEASUREMENT ONLY - what would change if the rest-of-season leg stopped
pricing NEXT year's talent?  (lane A2b, 2026-08-04d)

THE QUESTION.  proj_export's rest-of-season leg prices the balance of the
IN-PROGRESS season (2026) off `war[0]`, which is the FIRST_SEASON (2027)
projection - one full aging year PAST the season actually being sold.  For an
aging veteran that is a real, signed bias: his 2026 talent is a shade ABOVE his
2027 projection, so the remainder he is traded on is systematically underpriced.
The in-code comment chose war[0] on purpose ("deliberately does not read 2026
results to date, which measure what the SELLING club already banked"), and that
reasoning is sound about BANKED PRODUCTION but silent about TALENT TIMING: the
question here is only which season's talent estimate the remainder is priced on,
not whether to re-bank April.

THIS SCRIPT DOES NOT CHANGE THE SHIPPED BASIS.  It measures the move so the
decision is made on numbers.

THE DE-AGING IS THE CODEBASE'S OWN FITTED CURVE, NOT A CONSTANT.  fa_market's
`_decay_path` (fa_market.py:265-283) is the only WAR aging operator in the tree:
moving INTO age a it adds `fp.curve_delta(curves, side, decay_role, "war_rate",
a)` to the per-600-PA / per-250-BF WAR RATE and `curve_delta(..., "pt", a)` to
the projected exposure, then re-multiplies.  Both deltas are ADDITIVE, so the
step is exactly invertible: to walk one year BACK from age a, subtract the same
two deltas evaluated at a.  We rebuild each veteran's year-1 (rate, exposure)
from the same Marcel call proj_export makes, invert that one step, and take the
ratio to his champion year-1 WAR.  The ratio is then applied to the SHIPPED
`war[0]`, so the ML quantile head's information survives and only the aging
timing moves.

Curves and corpus are read from the on-disk caches (`.cache/fa_corpus.pkl`,
`.cache/fa_fits_*.pkl`); nothing is refetched, refit or rewritten.  The only
file written is `data/ros_talent_basis_probe.json`.

TWO VARIANTS, because the exposure leg is the aggressive half:
  * `deaged_full` - un-ages BOTH the WAR rate and the playing-time projection.
    Faithful inverse of `_decay_path`.  For a 34-year-old starter the fitted pt
    delta is large (~-127 BF/yr), so this variant moves a lot.
  * `deaged_rate`  - un-ages the WAR RATE only, holding the Marcel exposure
    projection fixed.  Defensible on its own terms: the year-1 PT projection is
    already fit on what the player is doing THIS season, so it is arguably not
    stale the way the rate is.

Plus the two bases already published on every row, for reference:
  * `warPTH[0]`    - the if-healthy (playing-time-held) display path.
  * `warY1Champ`   - the champion (non-ML) mean year-1.

SALARY CANCELS.  Under the shipped-after-A2 convention the leg is
f * (V(w) - salary), so changing only the talent basis moves surTotal by exactly
f * (V(w_alt) - V(w_ship)).  That is why this probe needs no contract file.

BASELINE NOTE.  data/mlb_projections.json on disk was written under the OLD
V(f*w) production leg.  Every "shipped" number below is the served surTotal plus
the A2a convexity correction f*V(w) - V(f*w), i.e. what the next export will
print.  Re-run this after that export and the baseline term goes to zero.

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
import value_framework as vf        # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "ros_talent_basis_probe.json"
CORPUS_PKL = ROOT / ".cache" / "fa_corpus.pkl"
PER = {"hit": 600.0, "pit": 250.0}
# proj_export's per-side universe floors (proj_export.py:64, applied at :417).
# NOT optional here: a position player with 10 mop-up IP over three seasons has
# a 'pit' corpus row, and the first draft of this probe de-aged that side too.
# Miguel Rojas came out 0.67 -> 3.50 WAR (5.2x) on a pitching exposure the
# served row does not contain, because the pitcher pt delta at 38 (-99 BF) was
# added back to a ~4 BF projection. The served row is HIT-ONLY; so is this.
MIN_PA, MIN_IP = 100, 30


def _season_value_usd(war: float, dpw: float) -> float:
    """proj_export._season_value_usd at t=0 (the rest-of-season leg's own t)."""
    base_flat = float(vf._config()["dollars_per_war"]["flat"])
    return vf.tiered_war_value_usd(war) * (dpw / base_flat)


def _deage_ratios(first_season: int, wanted: set[int]) -> dict[int, dict]:
    """{mlbam: {ratio_full, ratio_rate, war1_champ, sides:[...]}} - the one-year
    inverse of `_decay_path` for every requested veteran.

    Rebuilt from the SAME inputs proj_export uses (cached corpus, cached fits,
    same three-season history window, same in-progress fraction) so the champion
    year-1 this reproduces is the row's own warY1Champ.
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
        tot1 = tot_full = tot_rate = 0.0
        sides: list[dict] = []
        for side in ("hit", "pit"):
            seasons = by.get((side, mid)) or {}
            hist = [seasons[t] for t in (first_season - 1, first_season - 2,
                                         first_season - 3) if t in seasons]
            if not hist:
                continue
            # Same universe gate the served row passed, side by side.
            if side == "hit":
                if max(h.get("pa") or 0 for h in hist) < MIN_PA:
                    continue
            elif max(h.get("ip") or 0 for h in hist) < MIN_IP:
                continue
            age_row = next((h for h in hist if h.get("age")), None)
            if age_row is None:
                continue
            age = age_row["age"] + (first_season - age_row["season"])
            try:
                proj = fp.project_player(hist, side, first_season, curves,
                                         league, age, in_progress=in_prog)
                if proj is None:
                    continue
                war1 = fp.war_from_projection(proj, side, war_map, league,
                                              first_season)
            except Exception:                                   # noqa: BLE001
                continue
            expo = float(proj["pt_proj"] or 0.0)
            if expo <= 0.0 or war1 is None:
                continue
            per = PER[side]
            drole = fp.profile_role(hist, side, proj["role"], league)
            rate = float(war1) / expo * per
            # INVERSE of the one-year forward step in fa_market._decay_path:
            # forward INTO age a adds curve_delta(..., a); backward subtracts it.
            d_rate = fp.curve_delta(curves, side, drole, "war_rate", int(age))
            d_pt = fp.curve_delta(curves, side, drole, "pt", int(age))
            w_full = max(0.0, rate - d_rate) * max(0.0, expo - d_pt) / per
            w_rate = max(0.0, rate - d_rate) * expo / per
            tot1 += float(war1)
            tot_full += w_full
            tot_rate += w_rate
            sides.append({"side": side, "role": drole, "age": round(age, 1),
                          "expo": round(expo, 1), "war1": round(float(war1), 3),
                          "d_war_rate": round(d_rate, 4), "d_pt": round(d_pt, 2),
                          "deaged_full": round(w_full, 3),
                          "deaged_rate": round(w_rate, 3)})
        if not sides or tot1 <= 0.05:
            # A champion year-1 at ~0 makes the RATIO meaningless (0/0); the row
            # is reported as unresolved rather than silently given ratio 1.0.
            continue
        out[mid] = {"ratio_full": tot_full / tot1, "ratio_rate": tot_rate / tot1,
                    "war1_champ": round(tot1, 3), "sides": sides}
    return out


def _pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


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
        # BASELINE = what the next export prints (served + the A2a convexity fix).
        base = float(served) + (f * _season_value_usd(w0, dpw)
                                - _season_value_usd(w0 * f, dpw))
        v0 = _season_value_usd(w0, dpw)
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
        "generated_for": "lane A2b (2026-08-04d) - MEASUREMENT ONLY, basis unchanged",
        "first_season": first,
        "ros_fraction": proj.get("ros_fraction"),
        "dpw_usd": dpw,
        "n_vet_rows_with_ros_leg": len(rows),
        "n_deaging_unresolved": unresolved,
        "baseline": ("served surTotal + the A2a convexity correction "
                     "f*V(w) - V(f*w); re-run after the next export to zero it"),
        "de_aging_operator": ("inverse of fa_market._decay_path at the player's "
                              "own age: rate -= curve_delta(war_rate, a), "
                              "expo -= curve_delta(pt, a) (deaged_full); "
                              "rate only (deaged_rate)"),
        "summary": {b: _summary(deltas[b]) for b in bases},
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
