# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""In-house linear-weights production rate for MiLB seasons (wRC-lite / wOBA-lite).

W-WRC lane (docs/efv-2026-07-24/GATES.md, Phase 1b). Builds a level-relative,
reliability-shrunk production rate from an in-house wOBA-lite, as a candidate that may
carry linear-weight SHAPE information the decomposed pieces (k/bb/iso/obp/ops rel) miss.

METHOD (frozen in this header BEFORE any gate arm ran; one attempt per registered arm).
No gate result is asserted in this module: the measured verdicts live only in
data/xfv_wrc_eval.json, written by tools/efv_wrc_lab.py.

wOBA-lite
  FIXED FanGraphs-style linear-weight SHAPE (canonical 2013 wOBA numerator weights):
    uBB .690  HBP .722  1B .888  2B 1.271  3B 1.616  HR 2.101
  The absolute magnitude is irrelevant -- every league-season pool re-derives its own
  wOBA scale so that the pool's average wOBA-lite equals the pool's OBP (the FG
  convention that pins league wOBA to league OBP inside each run environment). Only the
  RELATIVE proportions of the base weights survive that rescale, so this is exactly
  "fixed FG-style weights scaled to the league-season run environment". league = SAME
  sport-season pool (all cached rows of one sportId + season). Numerator uses
  unintentional walks (BB - IBB); denominator = AB + (BB - IBB) + SF + HBP;
  1B = H - 2B - 3B - HR. NO park layer (the W2 park-measurement M-FAIL stands).

level-relative + reliability shrink (exactly the efv_dataset._season_rates convention)
  level mean = the pooled wOBA-lite of the SAME (season, level) pool (the cache rows'
  own level field: DSL/CPX/A/A+/AA/AAA; sportId 16 already split into CPX and DSL,
  matching the matrix level convention). w = pa / (pa + K_REL_PA), K_REL_PA = 100
  (the shipped hitter shrink):  wrc_rel = w * (player_wOBA - level_mean_wOBA).

wrc_rel is 0 / absent when a player-season is uncovered, identical to how ops_rel and
obp_rel read 0 under milb_missing -- so wrc_rel is a clean drop-in swap for ops_rel.

W-SB (Phase 2c), frozen here too:
  sb_rate = SB / PA; level norm = pooled SUM(SB) / SUM(PA) of the same (season, level)
  pool; hit_sb_rel = w * (sb_rate - level_norm), same K = 100. Plain SB rate vs level
  norm as registered; CS is deliberately not folded in (no unregistered freedom).

peak_wrc_rel (DESCRIPTIVE ONLY; the registered arms A1-A4 are the only gates):
  per player, the max wrc_rel across pre-decision PA>=50 seasons, one value per season
  from the player's most-exposed level that season.

Documented asymmetry (a property of the mechanism, not a bug): matrix ops_rel on
AAA-2023+ rows may carry the S-XLINE / park-line adjustments applied upstream of
_season_rates; wrc_rel here is computed from the RAW cached components (no park layer is
registered for this lane).
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache" / "milb_full_stats"

# reliability shrink anchor -- the same constant the shipped hitter rates use
K_REL_PA = 100.0

# Canonical FG 2013 wOBA numerator weights (fixed base; rescaled per sport-season below).
BASE_W = {"ubb": 0.690, "hbp": 0.722, "b1": 0.888, "b2": 1.271, "b3": 1.616, "hr": 2.101}

SPORTS = (11, 12, 13, 14, 16)
SEASONS = range(2011, 2027)
_PEAK_MIN_PA = 50


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _components(r):
    """Raw counting components for one cache row, or None if uninformative (PA<=0)."""
    pa = _f(r.get("pa")) or 0.0
    if pa <= 0:
        return None
    h = _f(r.get("h")) or 0.0
    b2 = _f(r.get("doubles")) or 0.0
    b3 = _f(r.get("triples")) or 0.0
    hr = _f(r.get("hr")) or 0.0
    bb = _f(r.get("bb")) or 0.0
    ibb = _f(r.get("ibb")) or 0.0
    return {"ab": _f(r.get("ab")) or 0.0, "pa": pa,
            "b1": h - b2 - b3 - hr, "b2": b2, "b3": b3, "hr": hr,
            "ubb": max(0.0, bb - ibb), "hbp": _f(r.get("hbp")) or 0.0,
            "sf": _f(r.get("sf")) or 0.0, "sb": _f(r.get("sb")) or 0.0,
            "h": h, "bb": bb}


def _woba_num(c, w):
    return (w["ubb"] * c["ubb"] + w["hbp"] * c["hbp"] + w["b1"] * c["b1"]
            + w["b2"] * c["b2"] + w["b3"] * c["b3"] + w["hr"] * c["hr"])


def _woba_den(c):
    return c["ab"] + c["ubb"] + c["sf"] + c["hbp"]


def load_rows():
    """All cached hitting rows with parsed components attached (skips PA=0 rows)."""
    out = []
    for sport in SPORTS:
        for season in SEASONS:
            fp = CACHE_DIR / f"hitting_{sport}_{season}.json"
            if not fp.exists():
                continue
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, list):
                continue
            for r in data:
                mid, season_r, level = r.get("mlbam"), r.get("season"), r.get("level")
                if mid is None or season_r is None or level is None:
                    continue
                c = _components(r)
                if c is None:
                    continue
                out.append({"mlbam": int(mid), "season": int(season_r),
                            "sport": sport, "level": level, "c": c})
    return out


def build_index():
    """-> (index, leagues) where
       index[(mlbam, season, level)] = {woba, wrc_rel, hit_sb_rel, pa}
       leagues[(season, level)]      = {woba, sb_rate, n}   (report/debug)
    """
    rows = load_rows()

    # 1) sport-season run-environment scale (league = same sport-season pool)
    agg_ss = defaultdict(lambda: defaultdict(float))
    for r in rows:
        a = agg_ss[(r["sport"], r["season"])]
        for k, v in r["c"].items():
            a[k] += v
    scale_ss = {}
    for key, a in agg_ss.items():
        den = _woba_den(a)
        obp_den = a["ab"] + a["bb"] + a["hbp"] + a["sf"]
        if den <= 0 or obp_den <= 0:
            continue
        lg_obp = (a["h"] + a["bb"] + a["hbp"]) / obp_den
        lg_woba_base = _woba_num(a, BASE_W) / den
        scale_ss[key] = (lg_obp / lg_woba_base) if lg_woba_base > 0 else 1.0

    # 2) (season, level) pools: pooled league wOBA + SB norm
    agg_lv = defaultdict(lambda: defaultdict(float))
    for r in rows:
        s = scale_ss.get((r["sport"], r["season"]))
        if s is None:
            continue
        a = agg_lv[(r["season"], r["level"])]
        c = r["c"]
        a["num"] += _woba_num(c, BASE_W) * s
        a["den"] += _woba_den(c)
        a["sb"] += c["sb"]
        a["pa"] += c["pa"]
        a["n"] += 1
    leagues = {}
    for key, a in agg_lv.items():
        if a["den"] <= 0 or a["pa"] <= 0:
            continue
        leagues[key] = {"woba": a["num"] / a["den"], "sb_rate": a["sb"] / a["pa"],
                        "n": int(a["n"])}

    # 3) player rows -> shrunk level-relative values
    index = {}
    for r in rows:
        s = scale_ss.get((r["sport"], r["season"]))
        lg = leagues.get((r["season"], r["level"]))
        if s is None or lg is None:
            continue
        c = r["c"]
        den = _woba_den(c)
        if den <= 0:
            continue
        woba = _woba_num(c, BASE_W) * s / den
        w = c["pa"] / (c["pa"] + K_REL_PA)
        val = {"woba": round(woba, 5),
               "wrc_rel": round(w * (woba - lg["woba"]), 6),
               "hit_sb_rel": round(w * (c["sb"] / c["pa"] - lg["sb_rate"]), 6),
               "pa": c["pa"]}
        key = (r["mlbam"], r["season"], r["level"])
        if key not in index or val["pa"] > index[key]["pa"]:
            index[key] = val
    return index, leagues


def per_player_season(index):
    """index -> {(mlbam, season): most-PA row value} (for peak reads)."""
    best = {}
    for (mlbam, season, _lv), v in index.items():
        k = (mlbam, season)
        if k not in best or v["pa"] > best[k]["pa"]:
            best[k] = v
    return best


def peak_wrc_rel(index, mlbam, upto_season):
    """Max wrc_rel over the player's PA>=50 seasons at or before upto_season.
    Descriptive only (not a registered gate); leakage-safe when upto_season is the
    matrix's pre-decision final season."""
    if mlbam is None or upto_season is None:
        return None
    best_by_season = {}
    for (mid, season, _lv), v in index.items():
        if mid != int(mlbam) or season > int(upto_season) or v["pa"] < _PEAK_MIN_PA:
            continue
        prev = best_by_season.get(season)
        if prev is None or v["pa"] > prev[1]:
            best_by_season[season] = (v["wrc_rel"], v["pa"])
    vals = [x for x, _ in best_by_season.values()]
    return max(vals) if vals else None


if __name__ == "__main__":
    idx, lg = build_index()
    print(f"player-season-level rows indexed: {len(idx)}")
    print(f"league (season, level) pools: {len(lg)}")
    for key in sorted(lg)[-6:]:
        v = lg[key]
        print(f"  {key}: woba {v['woba']:.3f} sb_rate {v['sb_rate']:.4f} n {v['n']}")
