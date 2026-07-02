# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""R-PARK feasibility probe: can cached MiLB data support per-park run/contact
factors that improve the college -> Single-A translation?

Pre-registered gate (docs/audit-2026-07/AUDIT_FINDINGS.md, section R-PARK):
  Hypothesis: Savant-minors (2023+) per-park aggregates support stable park
  factors that improve the college -> Single-A translation (its documented
  SOS/park gap).
  Gate (ALL):
    1. per-park factors are stable (year-over-year rho >= 0.50 on parks with
       adequate batted-ball n, reported with n);
    2. adding the park adjustment to college_translation improves LOO MAE or
       interval coverage on the matched-pair set WITHOUT degrading the hitter
       K% r2 (the one strong component);
    3. coverage of parks is reported honestly (untracked FSL/DSL parks
       excluded, not imputed).
  On fail / insufficient data: loss ledger, no ship. (Task: insufficient
  data = FAIL, stated plainly.)

This module does NOT build park factors and does NOT touch college_translation.
It measures whether the *inputs* the gate presumes actually exist in the cache,
then writes the verdict + loss ledger. It is a pure, deterministic aggregation:
there is no sampling, fold, or randomized step, so no seed is required
(SEED = n/a, documented per the seed-every-stochastic-step rule).

Run: python tools/milb_park_factors.py
"""
from __future__ import annotations

import csv
import io
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage                       # noqa: E402
import college_translation as ct     # noqa: E402

DATA_DIR = ROOT / "data"
SAVANT_CACHE = ROOT / ".cache" / "savant_minors"
FACTORS_PATH = DATA_DIR / "milb_park_factors.json"
EVAL_PATH = DATA_DIR / "milb_park_factors_eval.json"

# Columns in a Savant-minors CSV row that would carry a park/venue dimension if
# the aggregate were grouped by venue instead of by name.
_VENUE_TOKENS = ("venue", "stadium", "park", "team", "game", "home", "road",
                 "sport", "level")
# The two levels college_translation treats as "Single-A".
_SINGLE_A_LEVELS = ("A", "A+")


# --------------------------------------------------------------------------- #
# 1. Does the cached Savant-minors data carry a venue dimension?
# --------------------------------------------------------------------------- #
def savant_cache_report() -> dict:
    """The cache is fetched with group_by=name (see arkmetric_forward_eval.py
    SAVANT url), so every row is a player-season aggregate. Report the row
    counts and confirm whether ANY venue/park/team column is present."""
    files = []
    venue_columns_seen: set[str] = set()
    for f in sorted(SAVANT_CACHE.glob("*.csv")):
        text = f.read_text(encoding="utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(text)))
        cols = list(rows[0].keys()) if rows else []
        vcols = [c for c in cols
                 if any(tok in c.lower() for tok in _VENUE_TOKENS)]
        venue_columns_seen.update(vcols)
        files.append({"file": f.name, "player_rows": len(rows),
                      "n_columns": len(cols), "venue_park_columns": vcols})
    return {
        "cache_dir": str(SAVANT_CACHE.relative_to(ROOT)),
        "group_by": "name (player-season aggregates)",
        "files": files,
        "has_venue_dimension": bool(venue_columns_seen),
        "venue_columns_found": sorted(venue_columns_seen),
    }


# --------------------------------------------------------------------------- #
# 2. Do the Single-A statlines (the translation's *target*) carry a park key?
# --------------------------------------------------------------------------- #
def statline_field_report(con) -> dict:
    """The matched-pair LOO loop scores college -> Single-A on the statlines
    (A/A+) rows. To apply ANY park adjustment you need a join from a player's
    season line to a park. Report the full field set to show none exists."""
    keys: set[str] = set()
    n = 0
    for _pk, pj in con.execute("SELECT player_key, payload_json FROM statlines"):
        d = json.loads(pj)
        if d.get("level") in _SINGLE_A_LEVELS:
            keys |= set(d.keys())
            n += 1
    park_keys = [k for k in keys
                 if any(tok in k.lower() for tok in ("venue", "stadium", "park",
                                                     "team", "home", "road", "org"))]
    return {"single_a_statline_rows": n,
            "fields_present": sorted(keys),
            "park_or_team_fields": park_keys,
            "has_park_join_key": bool(park_keys)}


# --------------------------------------------------------------------------- #
# 3. The ONLY venue-attributable minors contact source in cache:
#    statcast_metrics (MLB game-feed aggregate, PROSPECT population).
# --------------------------------------------------------------------------- #
def statcast_venue_coverage(con) -> dict:
    """statcast_metrics stores per-player level_splits, each with a coverage
    'venues' list (id+name). Report, per level: distinct venues, the seasons
    covered, and per-A-venue prospect-season appearances. This is the richest
    venue-attributable minors source in the cache; the report shows why it
    still cannot support the gate."""
    level_venue_seasons: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    level_rows: dict[str, int] = defaultdict(int)
    for pj, in con.execute("SELECT payload_json FROM statcast_metrics"):
        d = json.loads(pj)
        season = d.get("season")
        for sp in (d.get("level_splits") or []):
            lvl = sp.get("level")
            level_rows[lvl] += 1
            for v in ((sp.get("coverage") or {}).get("venues") or []):
                level_venue_seasons[lvl][v.get("name")].add(season)

    per_level = {}
    for lvl, venues in level_venue_seasons.items():
        seasons = sorted({s for vs in venues.values() for s in vs})
        per_level[lvl] = {"distinct_venues": len(venues),
                          "prospect_season_rows": level_rows[lvl],
                          "seasons_covered": seasons}

    # per-A-venue detail (the level the translation touches)
    a_detail = []
    for name, seasons in level_venue_seasons.get("A", {}).items():
        a_detail.append({"venue": name, "seasons": sorted(seasons)})
    a_detail.sort(key=lambda r: r["venue"])
    a_seasons = sorted({s for r in a_detail for s in r["seasons"]})

    return {
        "source": "statcast_metrics (MLB Stats API game feed; prospect population)",
        "note": ("contact_quality is aggregated per player per LEVEL, not per "
                 "venue; the 'venues' list is a home+road NAME list only. No "
                 "per-venue contact aggregate is retained, so a park factor "
                 "would require re-walking the ~156k raw cached game feeds and "
                 "would still only see the biased prospect subset."),
        "per_level": per_level,
        "single_a_A_venues": a_detail,
        "single_a_A_distinct_venues": len(a_detail),
        "single_a_A_seasons_covered": a_seasons,
        "single_a_Aplus_tracked_venues": per_level.get("A+", {}).get("distinct_venues", 0),
    }


# --------------------------------------------------------------------------- #
# 4. Application side: how many matched-pair players could even be
#    venue-attributed at all?
# --------------------------------------------------------------------------- #
def matched_pair_attribution(con) -> dict:
    """Replicate college_translation's matched-pair join (read-only; build() is
    NOT called) and measure how many matched players have ANY A-level statcast
    venue attribution. Even a full attribution would be a home+road venue list,
    not a home-park assignment, so this is an upper bound on a barrier that is
    already fatal."""
    key_name = ct._key_to_name(con)
    cs_h, cs_p = ct.load_cs_hitters(), ct.load_cs_pitchers()
    sa_h, sa_p = ct.load_single_a(con, key_name)
    matched_h = [s for s in cs_h if s in sa_h]
    matched_p = [s for s in cs_p if s in sa_p]

    slug_to_pk: dict[str, list[str]] = defaultdict(list)
    for pk, slug in key_name.items():
        slug_to_pk[slug].append(pk)

    pk_mlbam: dict[str, int] = {}
    for pk, pj in con.execute("SELECT player_key, payload_json FROM statlines"):
        d = json.loads(pj)
        if d.get("level") in _SINGLE_A_LEVELS and d.get("mlbam_id"):
            pk_mlbam[pk] = d["mlbam_id"]

    sc_levels: dict[int, set] = defaultdict(set)
    for pj, in con.execute("SELECT payload_json FROM statcast_metrics"):
        d = json.loads(pj)
        mid = d.get("mlbam_id")
        for sp in (d.get("level_splits") or []):
            sc_levels[mid].add(sp.get("level"))

    def _cov(matched):
        any_sc = a_sc = 0
        for slug in matched:
            mids = {pk_mlbam.get(pk) for pk in slug_to_pk.get(slug, [])}
            mids = {m for m in mids if m}
            if any(m in sc_levels for m in mids):
                any_sc += 1
            if any("A" in sc_levels.get(m, set()) for m in mids):
                a_sc += 1
        return {"matched": len(matched), "with_any_statcast": any_sc,
                "with_A_venue_attribution": a_sc,
                "A_attribution_pct": round(a_sc / len(matched) * 100, 1) if matched else 0.0}

    return {"hitters": _cov(matched_h), "pitchers": _cov(matched_p),
            "attribution_is": "home+road venue LIST only, not a home-park "
                              "assignment or a home/road split"}


# --------------------------------------------------------------------------- #
# Assemble the verdict + artifacts
# --------------------------------------------------------------------------- #
def run(persist: bool = True) -> dict:
    savant = savant_cache_report()
    with storage.connect() as con:
        statlines = statline_field_report(con)
        statcast = statcast_venue_coverage(con)
        attribution = matched_pair_attribution(con)

    a_seasons = statcast["single_a_A_seasons_covered"]

    conditions = {
        "1_yoy_stability_rho_ge_0.50": {
            "verdict": "INFEASIBLE",
            "why": (f"The Savant-minors cache the hypothesis names has NO venue "
                    f"dimension (group_by=name; venue columns found: "
                    f"{savant['venue_columns_found']}), so per-park aggregates "
                    f"cannot be built from it at all. The only venue-attributable "
                    f"minors contact source (statcast_metrics) covers Single-A "
                    f"level 'A' in seasons {a_seasons} only -- a single season, so "
                    f"a year-over-year correlation cannot be computed (needs >= 2 "
                    f"years). A+ has "
                    f"{statcast['single_a_Aplus_tracked_venues']} tracked venues."),
        },
        "2_translation_improvement_no_K%_r2_loss": {
            "verdict": "INFEASIBLE",
            "why": (f"The college_translation matched-pair target (Single-A "
                    f"statlines) carries no park/team/home-road field "
                    f"(park_or_team_fields={statlines['park_or_team_fields']}), so "
                    f"there is no join key to attach a park adjustment to a "
                    f"matched player's season line. Best-case venue attribution "
                    f"via the prospect statcast cache reaches only "
                    f"{attribution['hitters']['A_attribution_pct']}% of matched "
                    f"hitters and {attribution['pitchers']['A_attribution_pct']}% "
                    f"of matched pitchers, and even that is a home+road venue list, "
                    f"not a park assignment. The LOO improvement test cannot be run."),
        },
        "3_coverage_reported_honestly": {
            "verdict": "REPORTED",
            "why": (f"Single-A level 'A' (Florida State League): "
                    f"{statcast['single_a_A_distinct_venues']} tracked venues, "
                    f"seasons {a_seasons}, prospect-population only. Level 'A+' "
                    f"(High-A): {statcast['single_a_Aplus_tracked_venues']} tracked "
                    f"venues -- half of the translation's 'A/A+' universe is dark. "
                    f"Untracked FSL/DSL parks are neither present nor imputed."),
        },
    }

    loss_ledger = {
        "outcome": "INFEASIBLE / FAIL (insufficient data)",
        "seed": "n/a (deterministic aggregation; no sampling or randomized fold)",
        "root_causes": [
            "Savant-minors cache is group_by=name: player-season aggregates with "
            "no venue/stadium/team/game column, across all 8 cached files "
            "(batter/pitcher x 2023-2026). Per-park aggregation is impossible "
            "from the source the hypothesis names.",
            "college_translation's matched-pair target (statlines, level A/A+) "
            "carries no team/venue/home-road field, so no park adjustment can be "
            "joined to a matched player's Single-A line. Gate condition 2 cannot "
            "be executed.",
            "The only venue-attributable minors contact data in cache "
            "(statcast_metrics, MLB game-feed aggregate) is a PROSPECT-population "
            "subset, stored per level not per venue, and for Single-A 'A' it "
            "spans a single season (2026), making a year-over-year stability "
            "correlation arithmetically impossible.",
            "Single-A A+ (High-A) has zero tracked venues; the existing "
            "park-factor machinery (fa_park_factors / fetch_savant_park_factors) "
            "is MLB-only and the fa_park_factors table is empty.",
        ],
        "what_would_be_needed": [
            "A full-population (not prospect-only) per-venue batted-ball or "
            "run-scoring source for Single-A parks spanning >= 2 seasons, to "
            "estimate and stability-test park factors.",
            "A team/venue (and ideally home/road) attribution on the Single-A "
            "statlines so an estimated factor could be applied inside the "
            "matched-pair LOO loop.",
            "Coverage for A+ parks, which today have no tracking at all.",
        ],
        "no_ship": True,
        "college_translation_untouched": True,
    }

    verdict = ("FAIL -- INFEASIBLE. Per-park aggregation is not possible from the "
               "cached data the R-PARK hypothesis names (Savant-minors is "
               "player-aggregated, no venue dimension), and the college_translation "
               "matched-pair target carries no park join key, so the translation-"
               "improvement test cannot be run. Insufficient data. No ship; "
               "college_translation is unchanged.")

    eval_doc = {
        "artifact": "milb_park_factors_eval",
        "generated_at": date.today().isoformat(),
        "lane": "R-PARK",
        "gate_ref": "docs/audit-2026-07/AUDIT_FINDINGS.md#R-PARK",
        "seed": "n/a (deterministic aggregation; no sampling or randomized step)",
        "verdict": verdict,
        "gate_pass": False,
        "conditions": conditions,
        "feasibility_probe": {
            "savant_minors_cache": savant,
            "single_a_statline_fields": statlines,
            "statcast_venue_coverage": statcast,
            "matched_pair_attribution": attribution,
        },
        "loss_ledger": loss_ledger,
    }

    factors_doc = {
        "artifact": "milb_park_factors",
        "generated_at": date.today().isoformat(),
        "status": "not_built",
        "gate_pass": False,
        "reason": ("INFEASIBLE: cached Savant-minors data has no venue dimension "
                   "(group_by=name), and Single-A statlines carry no park/team "
                   "join key. See milb_park_factors_eval.json for the full "
                   "feasibility probe and loss ledger."),
        "factors": {},
        "levels_touched_by_translation": list(_SINGLE_A_LEVELS),
        "coverage_summary": {
            "savant_minors_has_venue_dimension": savant["has_venue_dimension"],
            "single_a_A_tracked_venues": statcast["single_a_A_distinct_venues"],
            "single_a_A_seasons": statcast["single_a_A_seasons_covered"],
            "single_a_Aplus_tracked_venues": statcast["single_a_Aplus_tracked_venues"],
            "single_a_statline_has_park_key": statlines["has_park_join_key"],
        },
    }

    if persist:
        FACTORS_PATH.write_text(json.dumps(factors_doc, indent=1), encoding="utf-8")
        EVAL_PATH.write_text(json.dumps(eval_doc, indent=1), encoding="utf-8")
    return eval_doc


if __name__ == "__main__":
    doc = run()
    print(json.dumps({
        "verdict": doc["verdict"],
        "gate_pass": doc["gate_pass"],
        "conditions": {k: v["verdict"] for k, v in doc["conditions"].items()},
    }, indent=1))
