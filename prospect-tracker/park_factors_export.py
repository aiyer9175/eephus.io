# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
#
# ============================================================================
# DISPLAY ONLY. THE MODEL PATH STAYS OFF.
#
# efv_park_line.py is the model consumer of these factors and it is flag-gated
# OFF (PARKLINE_HIT_DEFAULT / PARKLINE_PIT_DEFAULT = False) under a registered
# M-FAIL verdict: docs/wills-2026-07-23/GATES.md section W2 recorded
# M-FAIL-DISPLAY-CANDIDATE on both sides (hit delta +0.0005, lo95 -0.0011;
# pit -0.0021, lo95 -0.0051) and the registration says the layer stays off
# PERMANENTLY while the factor table itself is sanctioned to ship as a
# display-only product. This module is that display path and nothing else. It
# imports no efv_*, proj_*, fa_* or valuation module, reads no served number,
# and writes no file that any model reads.
# ============================================================================
"""Park-factor display sidecar: data/milb_park_factors_display.json.

data/milb_park_factors.json is a 592 KB research artifact: 202 venues plus
1,211 team-season rows with the raw per-team home and road rate inputs. It is
correct and it stays untouched. This module verifies it and emits a light,
venue-keyed companion (roughly 12 percent of the size) that a site table or a
player-card chip can load directly: one row per venue, labeled with the level,
league and current affiliate the source table only carries at the team-season
grain, with the trailing-window factor series for a sparkline.

THREE DECISIONS MADE HERE, all of them on the evidence:

1. THE DISPLAYED NUMBER IS THE 3-SEASON WINDOW, NOT THE SINGLE SEASON. The
   single-season factors are not stable enough to put in front of a reader:
   venue-level year-over-year Spearman on run_pf runs 0.353 to 0.479 across
   the five season pairs (n 137 to 171), below the 0.50 stability bar the
   R-PARK registration set. The 3-season aggregate is a different animal: an
   independent split-half (mean of 2021/2023/2025 against mean of
   2022/2024/2026, so no shared season) gives Spearman 0.735 on run_pf
   (n = 143) and 0.760 on hr_pf (n = 138). The window number is publishable;
   the single-season number is not, so this file does not carry it. Per-season
   home-game counts ARE carried, because sample size belongs next to a factor.

2. NOTHING IS CLAMPED. The source method block records application clamps of
   [0.90, 1.10] on run and [0.80, 1.25] on HR. Those exist so a frozen eFV
   formula cannot be handed an outlier; they are a safety rail on a model path
   that is switched off, not a statement about the ballpark. Clamping the
   display would compress 13 of 201 venues on run and 17 of 200 on HR, and
   would silently turn Hodgetown's real 1.209 into 1.100. The display ships
   the measured value. The clamp bounds travel in the meta block so a reader
   can see what the model path would have done, and the count of venues the
   clamps would have moved is published alongside them.

3. THE POOLED NON-VENUE IS EXCLUDED. venue_id 401, named "TBD", is not a
   ballpark: it is the bucket StatsAPI hands back for unlabeled DSL sites, and
   it absorbs 133 team-seasons and 3,975 home games across every DSL club. Its
   factor is 1.00 by construction because it is its own comparison set.
   Dropping it from a venue table is the only correct handling; it is listed
   in meta.excluded with the reason so the omission is visible rather than
   quiet.

Source method, quoted rather than re-derived: team-season (home RS+RA per
game) over (road RS+RA per game) from StatsAPI schedule final scores, regular
season only, centered on the unweighted league-season mean ratio, EB-shrunk
toward 1.0 with K_G = 70 home games, venue assigned as the modal home venue,
venue-season as the home-game-weighted mean, and the 3-season window using
only seasons at or before t so it is vintage-safe. hr_pf comes from the
league-wide team statSplits fetch (hitting HR plus pitching HR allowed, i.e.
all HR hit at the venue) on the same centering, shrink and window.

Run: python park_factors_export.py [--verify]
"""
from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SRC_PATH = DATA / "milb_park_factors.json"
OUT_PATH = DATA / "milb_park_factors_display.json"

SCHEMA = 1
POOLED_NON_VENUE = 401            # StatsAPI "TBD", the unlabeled-DSL bucket
LEVEL_ORDER = ("AAA", "AA", "A+", "A", "CPX", "DSL")
LEVEL_LABEL = {"AAA": "Triple-A", "AA": "Double-A", "A+": "High-A",
               "A": "Single-A", "CPX": "Complex", "DSL": "Dominican Summer"}
MIN_PCT_POOL = 8                  # do not rank a venue inside a tiny level pool

# Face-valid extremes recorded in docs/wills-2026-07-23/GATES.md section W2.
# Checked on every run: if the table ever stops reproducing them, the doc and
# the data have diverged and the export refuses rather than shipping quietly.
GATES_EXTREMES = {
    "Hodgetown": (1.209, 1.428),
    "Las Vegas Ballpark": (1.121, 1.210),
    "McCormick Field": (1.133, 1.215),
    "Dickey-Stephens Park": (0.840, 0.751),
}


def _r3(x):
    """Round half UP to 3 places. Plain round() is banker's rounding over a
    binary float, which turns the 1.2085 stored for Hodgetown into 1.208 and
    puts the display one unit off the 1.209 recorded in GATES.md."""
    if x is None:
        return None
    return float(Decimal(repr(float(x))).quantize(Decimal("0.001"),
                                                  rounding=ROUND_HALF_UP))


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0] * len(xs)
    for k, i in enumerate(order):
        out[i] = k
    return out


def _spearman(a, b):
    n = len(a)
    if n < 4:
        return None
    ra, rb = _rank(a), _rank(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((y - mb) ** 2 for y in rb) ** 0.5
    return None if not (da and db) else round(num / (da * db), 3)


def _pct(vals, x):
    """Percentile rank 0-100 of x within vals (vals includes x)."""
    n = len(vals)
    below = sum(1 for v in vals if v < x)
    ties = sum(1 for v in vals if v == x)
    return int(round(100.0 * (below + 0.5 * ties) / n))


def _latest(series: dict):
    if not series:
        return None, None
    k = max(series, key=int)
    return int(k), series[k]


def verify(src: dict) -> dict:
    """Structural and statistical verification of the source table. Every
    claim this module's docstring makes is recomputed here."""
    venues = src["venues"]
    team_seasons = src["team_seasons"]
    real = [v for v in venues if v["venue_id"] != POOLED_NON_VENUE]

    problems = []
    for v in venues:
        for f in ("venue_id", "venue_name", "seasons", "window_run_pf",
                  "window_hr_pf"):
            if f not in v:
                problems.append(f"venue {v.get('venue_id')} missing {f}")
    ts_vids = {r["venue_id"] for r in team_seasons}
    v_vids = {v["venue_id"] for v in venues}
    if ts_vids - v_vids:
        problems.append(f"{len(ts_vids - v_vids)} team_season venues absent "
                        "from the venue table")
    if v_vids - ts_vids:
        problems.append(f"{len(v_vids - ts_vids)} venues with no team_season")

    seasons = sorted({int(s) for v in venues for s in v["seasons"]})
    vs_total = sum(len(v["seasons"]) for v in venues)
    vs_no_hr = sum(1 for v in venues for s in v["seasons"].values()
                   if s.get("hr_pf") is None)

    # stability: single-season YoY vs an independent split-half of the window
    yoy = {}
    for key in ("run_pf", "hr_pf"):
        yoy[key] = {}
        for y in seasons[:-1]:
            a, b = [], []
            for v in real:
                s1 = v["seasons"].get(str(y))
                s2 = v["seasons"].get(str(y + 1))
                if s1 and s2 and s1.get(key) is not None \
                        and s2.get(key) is not None:
                    a.append(s1[key])
                    b.append(s2[key])
            if len(a) >= 4:
                yoy[key][f"{y}_{y + 1}"] = {"n": len(a),
                                            "spearman": _spearman(a, b)}
    odd = [str(y) for y in seasons if y % 2 == 1]
    even = [str(y) for y in seasons if y % 2 == 0]
    split = {}
    for key in ("run_pf", "hr_pf"):
        A, B = [], []
        for v in real:
            o = [v["seasons"][s][key] for s in odd
                 if s in v["seasons"] and v["seasons"][s].get(key) is not None]
            e = [v["seasons"][s][key] for s in even
                 if s in v["seasons"] and v["seasons"][s].get(key) is not None]
            if len(o) >= 2 and len(e) >= 2:
                A.append(sum(o) / len(o))
                B.append(sum(e) / len(e))
        split[key] = {"n": len(A), "spearman": _spearman(A, B),
                      "halves": [odd, even]}

    # what the model-side clamps would have compressed on the display
    clamps = src.get("method", {}).get("application_clamps", {})
    moved = {}
    for key, wkey in (("run_pf", "window_run_pf"), ("hr_pf", "window_hr_pf")):
        lo, hi = clamps.get(key, (None, None))
        vals = [w for v in real for w in [_latest(v[wkey])[1]] if w is not None]
        moved[key] = {
            "bounds": [lo, hi],
            "venues": len(vals),
            "would_move": (None if lo is None else
                           sum(1 for x in vals if x < lo or x > hi)),
            "observed_range": [_r3(min(vals)), _r3(max(vals))],
        }

    extremes = {}
    for name, (want_run, want_hr) in GATES_EXTREMES.items():
        v = next((x for x in real if x["venue_name"] == name), None)
        if v is None:
            extremes[name] = {"found": False}
            problems.append(f"GATES extreme venue missing: {name}")
            continue
        _, run = _latest(v["window_run_pf"])
        _, hr = _latest(v["window_hr_pf"])
        ok = _r3(run) == want_run and _r3(hr) == want_hr
        extremes[name] = {"found": True, "run_pf": _r3(run), "hr_pf": _r3(hr),
                          "gates_says": [want_run, want_hr], "match": ok}
        if not ok:
            problems.append(f"GATES extreme mismatch at {name}")

    pooled = next((v for v in venues if v["venue_id"] == POOLED_NON_VENUE),
                  None)
    pooled_ts = [r for r in team_seasons
                 if r["venue_id"] == POOLED_NON_VENUE]

    return {
        "n_venues_source": len(venues),
        "n_venues_display": len(real),
        "n_team_seasons": len(team_seasons),
        "seasons": seasons,
        "venue_seasons": vs_total,
        "venue_seasons_missing_hr_pf": vs_no_hr,
        "structural_problems": problems,
        "yoy_single_season_spearman": yoy,
        "split_half_window_spearman": split,
        "stability_reading": (
            "single-season run_pf year-over-year Spearman runs "
            f"{min(x['spearman'] for x in yoy['run_pf'].values()):.3f} to "
            f"{max(x['spearman'] for x in yoy['run_pf'].values()):.3f}, under "
            "the 0.50 bar the R-PARK registration set, so single-season "
            "factors are NOT displayed. The independent split-half of the "
            f"multi-season aggregate is {split['run_pf']['spearman']} on run "
            f"and {split['hr_pf']['spearman']} on HR, which clears it, so the "
            "trailing-window value is what ships."),
        "clamp_exposure": moved,
        "gates_extremes": extremes,
        "pooled_non_venue": {
            "venue_id": POOLED_NON_VENUE,
            "venue_name": None if pooled is None else pooled["venue_name"],
            "team_seasons": len(pooled_ts),
            "home_games": sum(r["g_home"] for r in pooled_ts),
            "levels": sorted({r["level"] for r in pooled_ts}),
            "reason": "StatsAPI's unlabeled-site bucket, not a ballpark; it "
                      "pools every DSL club so its factor is 1.00 against "
                      "itself by construction. Excluded from the display "
                      "table.",
        },
    }


def build(src: dict) -> dict:
    ver = verify(src)
    if ver["structural_problems"]:
        raise SystemExit("REFUSING TO SHIP: " +
                         "; ".join(ver["structural_problems"]))

    venues = {v["venue_id"]: v for v in src["venues"]}
    by_venue = defaultdict(list)
    for r in src["team_seasons"]:
        by_venue[r["venue_id"]].append(r)

    seasons = ver["seasons"]
    max_season = max(seasons)

    rows = []
    for vid, v in venues.items():
        if vid == POOLED_NON_VENUE:
            continue
        ts = by_venue.get(vid, [])
        if not ts:
            continue
        last_ts_season = max(r["season"] for r in ts)
        cur = [r for r in ts if r["season"] == last_ts_season]
        lvl_w, lg_w, team_w = Counter(), Counter(), Counter()
        for r in cur:
            lvl_w[r["level"]] += r["g_home"]
            if r.get("league"):
                lg_w[r["league"]] += r["g_home"]
            team_w[r["team_name"]] += r["g_home"]

        wr_season, run = _latest(v["window_run_pf"])
        _, hr = _latest(v["window_hr_pf"])
        rows.append({
            "id": vid,
            "name": v["venue_name"],
            "lvl": max(lvl_w, key=lvl_w.get) if lvl_w else None,
            "lg": max(lg_w, key=lg_w.get) if lg_w else None,
            "team": max(team_w, key=team_w.get) if team_w else None,
            "shared": 1 if len(team_w) > 1 else 0,
            "last": last_ts_season,
            "stale": 1 if last_ts_season < max_season else 0,
            "g": sum(r["g_home"] for r in ts),
            "as_of": wr_season,
            "run": _r3(run),
            "hr": _r3(hr),
            "wr": [None if str(y) not in v["window_run_pf"]
                   else _r3(v["window_run_pf"][str(y)]) for y in seasons],
            "wh": [None if str(y) not in v["window_hr_pf"]
                   else _r3(v["window_hr_pf"][str(y)]) for y in seasons],
            "gs": [None if str(y) not in v["seasons"]
                   else v["seasons"][str(y)]["g_home"] for y in seasons],
        })

    # percentile within level, over the non-stale pool only (a venue whose
    # last season is 2023 does not belong in a 2026 ranking)
    pools = defaultdict(lambda: {"run": [], "hr": []})
    for r in rows:
        if r["stale"] or not r["lvl"]:
            continue
        if r["run"] is not None:
            pools[r["lvl"]]["run"].append(r["run"])
        if r["hr"] is not None:
            pools[r["lvl"]]["hr"].append(r["hr"])
    for r in rows:
        r["run_pct"] = r["hr_pct"] = None
        if r["stale"] or not r["lvl"]:
            continue
        p = pools[r["lvl"]]
        if r["run"] is not None and len(p["run"]) >= MIN_PCT_POOL:
            r["run_pct"] = _pct(p["run"], r["run"])
        if r["hr"] is not None and len(p["hr"]) >= MIN_PCT_POOL:
            r["hr_pct"] = _pct(p["hr"], r["hr"])

    # level ladder, then live venues ranked by run factor, then the stale
    # ones underneath (a park with no current tenant does not belong inside a
    # current-season ranking)
    rows.sort(key=lambda r: (LEVEL_ORDER.index(r["lvl"])
                             if r["lvl"] in LEVEL_ORDER else 99,
                             r["stale"],
                             -(r["run"] if r["run"] is not None else 0)))

    return {
        "schema": SCHEMA,
        "generated_at": date.today().isoformat(),
        "source": {
            "artifact": "data/milb_park_factors.json",
            "artifact_generated_at": src.get("generated_at"),
            "built_by": src.get("tool"),
            "experiment": src.get("experiment"),
            "relation": "read-only reshape; the source artifact is not "
                        "modified by this module",
        },
        "contract": (
            "DISPLAY ONLY. efv_park_line.py is the model consumer of these "
            "factors and stays flag-gated OFF under the registered W2 M-FAIL "
            "verdict. Nothing here may be fed to a grade, a projection, a "
            "translation or a valuation."),
        "method": src.get("method"),
        "meta": {
            "seasons": seasons,
            "current_season": max_season,
            "partial_seasons": [max_season],
            "partial_note": src.get("method", {}).get("note_2026"),
            "displayed_value": (
                "trailing 3-season window ending at the venue's most recent "
                "rated season, vintage-safe (uses only seasons at or before "
                "that year). Single-season factors are deliberately absent: "
                "see verification.stability_reading."),
            "clamping": (
                "NONE. The [0.90, 1.10] run and [0.80, 1.25] HR bounds in the "
                "method block are application clamps for a model path that is "
                "switched off. Applying them to the display would compress "
                f"{ver['clamp_exposure']['run_pf']['would_move']} venues on "
                f"run and {ver['clamp_exposure']['hr_pf']['would_move']} on "
                "HR, including turning Hodgetown's measured 1.209 into 1.100. "
                "The measured value ships."),
            "neutral": 1.0,
            "reading": "1.05 means the venue played about 5 percent more "
                       "runs (or HR) than its league-season baseline, after "
                       "shrinking toward neutral with K_G = 70 home games.",
            "levels": [{"code": c, "label": LEVEL_LABEL[c]}
                       for c in LEVEL_ORDER],
            "percentile": f"rank within the same level among non-stale "
                          f"venues; suppressed for level pools under "
                          f"{MIN_PCT_POOL} venues",
            "stale": "1 when the venue has no team-season at the current "
                     "season; its factor is a historical reading and it is "
                     "left out of the percentile pool",
            "shared": "1 when more than one club called the venue home in "
                      "its last rated season (the factor pools them)",
            "series": {"wr": "window run factor per season in meta.seasons "
                             "order",
                       "wh": "window HR factor, same order",
                       "gs": "home games observed that season, same order; "
                             "null where the venue was not rated"},
            "excluded": [ver["pooled_non_venue"]],
            "hr_coverage": (
                f"{ver['venue_seasons'] - ver['venue_seasons_missing_hr_pf']} "
                f"of {ver['venue_seasons']} venue-seasons carry an HR factor; "
                "the gaps are complex-level sites with no team split fetched"),
        },
        "verification": ver,
        "n": len(rows),
        "venues": rows,
    }


def run(persist: bool = True) -> dict:
    src = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    out = build(src)
    if persist:
        text = json.dumps(out, separators=(",", ":"), sort_keys=False) + "\n"
        if not OUT_PATH.exists() or OUT_PATH.read_text(encoding="utf-8") != text:
            OUT_PATH.write_text(text, encoding="utf-8")
            log.info("wrote %s (%d venues)", OUT_PATH, len(out["venues"]))
    return out


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    src = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    if "--verify" in sys.argv:
        print(json.dumps(verify(src), indent=1))
    else:
        out = run(persist=True)
        v = out["verification"]
        print(f"venues      {out['n']} (source {v['n_venues_source']}, "
              f"1 pooled non-venue excluded)")
        print(f"seasons     {out['meta']['seasons']}")
        print("stability   run split-half "
              f"{v['split_half_window_spearman']['run_pf']['spearman']}, "
              f"hr {v['split_half_window_spearman']['hr_pf']['spearman']}")
        print(f"extremes    "
              f"{sum(1 for x in v['gates_extremes'].values() if x.get('match'))}"
              f"/{len(v['gates_extremes'])} match GATES.md")
        print(f"src bytes   {SRC_PATH.stat().st_size}")
        print(f"out bytes   {OUT_PATH.stat().st_size}")
