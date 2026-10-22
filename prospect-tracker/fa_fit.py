# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Team fit engine for the MLB Free Agency module (Stage 4).

Five transparent components, weighted per fa_config.yaml `fit.weights`,
every score decomposable in the UI:

  NEED      incumbent committed strength at the player's position for the
            contract season (projected WAR of resolved contracted players)
            minus blockers. Blockers come in TWO kinds, both listed in the
            UI: PROSPX prospects with a near ETA at the existing FV grid
            (fv_close >= 50, ETA <= class_year + 1 — read-only, no parallel
            thresholds), and MLB INCUMBENTS already producing at the
            position (the displaced player projects >= incumbent_block_war).
            Incumbent strength also flows CONTINUOUSLY through the
            displacement gap, so only the prospect kind carries an extra
            multiplier — a prospect isn't on the contracted roster, so the
            gap can't see him.
  WINDOW    marginal playoff leverage at the team's projected win total
            for the contract season, read from the SAME artifact the
            /projections/ surface serves (data/mlb_projections.json
            team_outlook): the 85-win team gains far more from +4 WAR than
            the 70-win team. Fixed documented logistic (not fitted, v1).
            The v1 baseline rebuilt its own win total out of contracted
            WAR plus a flat roster-fill stand-in and disagreed with
            /projections/ by a mean 5.60 wins (max 10.0) as used, and by
            6.85 before the roster-fill stand-in is added - see
            team_baselines. The contracted-core form survives as the
            documented fallback when the artifact is absent or partial.
  AFFORD    CAN the team fit the price: CBT-basis payroll vs the
            rule-versioned threshold (Spotrac's own tax-space number when
            present). Habitual taxpayers who keep spending get a documented
            floor — the Dodgers' afford is not zero just because they're
            over the line. For 2027 the threshold is an explicit
            carry-forward and the flag rides every output.
  PARK      destination park factors (Savant, 100 = neutral) aligned to
            the player's batted side; pitchers prefer suppressive parks.
            Deliberately the SMALLEST weight: park is a tiebreaker, not a
            driver (the v1 weighting recommended suppressive parks for
            every pitcher — the Giants-for-all-pitchers failure).
  BEHAVIOR  WILL the team spend: priors from the team's OWN signing
            history — biggest guarantee ever (vs this price), recent
            3-winter FA outlay, $100M-deal participation. Some teams
            structurally never shop in certain aisles.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from functools import lru_cache

import fa_cba
import fa_class
import fa_ident
import fa_market as fm
import fa_projection as fp
import fa_sources
import storage
from trades import canonical_org

log = logging.getLogger(__name__)

POSITIONS = ("C", "1B", "2B", "SS", "3B", "LF", "CF", "RF", "DH", "SP", "RP")
_SAVANT_CLUB_OVERRIDES = {"D-backs": "ARI", "Diamondbacks": "ARI"}
# The 30 MLB clubs. Needed because a club can legitimately have ZERO qualifying
# roster rows, and a club that vanishes from the needs matrix vanishes from every
# player's 30-club fit vector (the measured MIA-has-no-baseWins defect).
ORGS = ("ARI", "ATH", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL",
        "DET", "HOU", "KCR", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY",
        "PHI", "PIT", "SDP", "SEA", "SFG", "STL", "TBR", "TEX", "TOR", "WSN")

# ============================================================================
# F1-F4 (2026-07-30): the fits v4 repairs. Central flip lives here.
# ============================================================================
# Registered under the owner program's Phase F. Criteria and the measured
# before/after are in docs/efv-2026-07-30/FA_LANE_GATES.md section F.
#
# WHAT WAS BROKEN (all measured on the served 2027 board, 228 members):
#   * LAD was the #1 fit for 154 of 228 members (68%); only 6 clubs were ever
#     #1 and only 12 of 30 ever appeared in a top-3; the median #1-vs-#2 gap was
#     0.0180, i.e. the ordering was noise.
#   * SFG was #1 for 85% of pitchers projecting >= 1.0 WAR and top-3 for 100%.
#   * The need roster read ONLY Spotrac contracts signed through the class year,
#     so every arb and pre-arb player was invisible.
#   * win_leverage is symmetric bubble-proximity, so a 0%-playoff club scored
#     3.6x a club already locked into the postseason.
#   * behavior's max-guarantee term is min(...,1)-clipped, which pins it at 1.0
#     for almost every player and turns a player-conditional term into a club
#     constant - which is exactly how one club ends up atop every list.
FIT_ROSTER_SOURCE = "projected"     # "projected" (v4) | "spotrac" (v3 fallback)
FIT_WINDOW_MODE = "playoff"         # "playoff" (v4) | "leverage" (v3)
FIT_BEHAVIOR_MODE = "percentile"    # "percentile" (v4) | "clipped" (v3)
# Weight on the level term (are they actually in the race) against the marginal
# term (does a win change their odds). 0.6 is the SMALLEST level weight that
# makes assertion A3 hold arithmetically for every possible input pair: a
# 0%-playoff club maxes at 1-LEVEL=0.40 while a 90% club floors at 0.6*0.9=0.54.
FIT_WINDOW_LEVEL_W = 0.6
# F2b. How `need` scales. "saturation" is v3: min(1, war_gap / 4.0), which caps a
# sub-2-WAR player's cross-club need spread at a fraction of what the club-level
# components spread by, so behavior decides the ranking for most of the class and
# one club takes every low-need player (measured: LAD #1 for 68% of members, and
# 79% once F1-F4 landed). "share" asks the question the component is actually for -
# what FRACTION of what this player brings is new at this club - which gives every
# player a full 0-1 spread across the 30 clubs, not only stars.
# NEED_MIN_WAR keeps a 0.3-WAR player from scoring a perfect need on the strength
# of a 0.3-WAR gap, so the component stays comparable ACROSS players too.
NEED_MODE = "share"                 # "share" (v4) | "saturation" (v3)
NEED_MIN_WAR = 1.0


def _fit_cfg() -> dict:
    return fa_class.get_config()["fit"]


def _position_norm(raw: str | None) -> str:
    head = (raw or "").upper().split("/")[0].strip()
    if head in ("SP", "SP2", "P", "LHP", "RHP"):
        return "SP"
    if head in ("RP", "CL", "SIRP", "MIRP"):
        return "RP"
    if head in ("OF",):
        return "CF"
    return head if head in POSITIONS else "DH"


# ============================================================================
# Park factors
# ============================================================================

@lru_cache(maxsize=8)
def park_factors(season: int, bat_side: str = "") -> dict[str, dict]:
    """{org: {woba, hr, runs}} (ints, 100 = neutral). Missing venues fall
    back to neutral at lookup time — never invented."""
    rows = fa_sources.fetch_savant_park_factors(season, bat_side)
    out: dict[str, dict] = {}
    for r in rows:
        club = r.get("name_display_club") or ""
        org = _SAVANT_CLUB_OVERRIDES.get(club) or canonical_org(club)
        if not org or len(org) > 3:
            continue
        out[org] = {"woba": int(r.get("index_woba") or 100),
                    "hr": int(r.get("index_hr") or 100),
                    "runs": int(r.get("index_runs") or 100)}
    return out


# Savant's window, in seasons, for a venue the default 3-season view drops.
# 2 is the shortest window that holds a full season plus the current one for a
# club that moved in the season before last, which is exactly the Athletics'
# case (Sutter Health Park since 2025).
SHORT_WINDOW_ROLLING = "2"
# A default-view row whose PA sample is under this share of the view's median
# rests on fewer seasons at its venue than the window claims, and is carried in
# the short-window block beside its sample so a consumer can shrink it. The
# venue audit of 2026-09-11 (every club, 2021-2026, off the cached StatsAPI game
# feeds and Savant's single-season pages) found exactly one such row in the
# 2024-2026 view: Tropicana Field at 34,828 PA, 0.645 of the 53,975 median,
# because the Rays played 2025 at George M. Steinbrenner Field and came back to
# Tropicana for all 72 of their 2026 home games. The next-lowest row sits at
# 0.973 (Busch Stadium), so any cut between the two separates them; 0.8 is "less
# than about two and a half of the three seasons".
SHORT_SAMPLE_PA_SHARE = 0.8


def _park_rows_with_sample(season: int, bat_side: str = "",
                           rolling: str = "") -> dict[str, dict]:
    """{org: {woba, hr, runs, n_pa, year_range, venue}} for one Savant view.

    `park_factors` above is the FA engine's contract and is left exactly as it
    is; this sibling carries the PA sample and the window beside the three
    indices, because a consumer that has to decide how far to trust a factor
    needs its sample, and a factor with no sample on it cannot be shrunk."""
    rows = fa_sources.fetch_savant_park_factors(season, bat_side, rolling=rolling)
    out: dict[str, dict] = {}
    for r in rows:
        club = r.get("name_display_club") or ""
        org = _SAVANT_CLUB_OVERRIDES.get(club) or canonical_org(club)
        if not org or len(org) > 3:
            continue
        try:
            n_pa = int(float(r.get("n_pa") or 0))
        except (TypeError, ValueError):
            n_pa = 0
        out[org] = {"woba": int(r.get("index_woba") or 100),
                    "hr": int(r.get("index_hr") or 100),
                    "runs": int(r.get("index_runs") or 100),
                    "n_pa": n_pa,
                    "year_range": r.get("year_range"),
                    "venue": r.get("venue_name"),
                    "venue_id": _venue_id(r.get("venue_id"))}
    return out


def _venue_id(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _home_venue_ids(season: int) -> dict[str, int] | None:
    """{org: the club's own home venue id} from StatsAPI's team list for
    `season` (fantasy_schedule.fetch_home_venues, cached), or None when the map
    cannot be read. The INDEPENDENT half of the venue check: Savant attributes a
    park row to a venue, StatsAPI says where the club plays, and a row only
    prices a club when the two agree."""
    try:
        import fantasy_schedule as _fs
        m = _fs.fetch_home_venues(season)
    except Exception:                                       # noqa: BLE001
        return None
    out = {}
    for vid, org in (m or {}).items():
        try:
            out[str(org)] = int(vid)
        except (TypeError, ValueError):
            continue
    return out or None


def park_factors_short_window(season: int, *, home_venues: dict | None = None) -> dict:
    """Every club whose home venue holds less than a full 3-season Savant
    sample, with the sample on every row, CHECKED AGAINST THE VENUE THE CLUB
    ACTUALLY PLAYS IN.

    {"season", "rolling", "source", "note", "orgs": {org: {...row, n_pa,
    window, venue_id, statsapi_venue_id, venue_match}}, "refused",
    "venue_check"}. Two kinds of row, each labelled by `window`:

      * "rolling=2": a club ABSENT from `park_factors(season)`, from the
        shortest window that publishes its venue. On 2026-09-11 that is ATH,
        Sutter Health Park at runs 121 on 34,287 PA.
      * "default": a club PRESENT in `park_factors(season)` whose default-view
        row carries under SHORT_SAMPLE_PA_SHARE of the view's median sample,
        i.e. the venue hosted fewer of the window's seasons than the row's
        year_range says. The row is the default view's OWN row (same index,
        same venue), so a consumer can only shrink the served 3-season factor
        by its own sample, never replace it. On 2026-09-11 that is TBR,
        Tropicana Field 2024-2026 at 34,828 PA (2024 and 2026 only).

    THE SAMPLE RULE IS NOT THE VENUE RULE. The PA share says a row rests on
    fewer seasons than its window; it cannot say WHICH park those seasons were
    played in. So every candidate row is checked against StatsAPI's home venue
    for the club that season (`home_venues`, {org: venue id}, default
    `_home_venue_ids`): Savant's `venue_id` must equal it. A row whose venue is
    not where the club plays is REFUSED (listed under `refused`, never in
    `orgs`), so a club that moved can never price at the park it left. With no
    StatsAPI map the rows ship with `venue_match` null, Savant's own venue
    attribution standing alone, and `venue_check.status` says so.

    `venue_check` runs the same comparison over EVERY default-view row, so the
    served artifact answers "is every club priced at the ballpark it plays in
    this season" each time it is built: on 2026-09-11, 29 of 29 default rows
    match and the one club the default view drops is ATH.

    Read by the betting model (betting_model.SERVE_ATH_PARK), dfs_export's park
    leg through betting_model.park_index_from_meta, and `park_component` below,
    each through the one shrink (betting_model.short_window_shrink)."""
    base = park_factors(season)
    dflt = _park_rows_with_sample(season, "")
    ns = sorted(r["n_pa"] for r in dflt.values() if r.get("n_pa"))
    med = None
    if ns:
        mid = len(ns) // 2
        med = ns[mid] if len(ns) % 2 else (ns[mid - 1] + ns[mid]) / 2.0
    if home_venues is None:
        home_venues = _home_venue_ids(season)
    hv = {str(k): v for k, v in (home_venues or {}).items()}

    def checked(o: str, row: dict) -> dict:
        want = hv.get(o)
        got = row.get("venue_id")
        match = None if (want is None or got is None) else int(got) == int(want)
        return {**row, "statsapi_venue_id": want, "venue_match": match}

    short = _park_rows_with_sample(season, "", rolling=SHORT_WINDOW_ROLLING)
    cands = {o: checked(o, {**row, "window": f"rolling={SHORT_WINDOW_ROLLING}"})
             for o, row in short.items() if o not in base}
    if med:
        for o, row in dflt.items():
            if (o in base and o not in cands and row.get("n_pa")
                    and row["n_pa"] < SHORT_SAMPLE_PA_SHARE * med):
                cands[o] = checked(o, {**row, "window": "default"})
    orgs = {o: r for o, r in cands.items() if r["venue_match"] is not False}
    refused = {o: {"venue": r.get("venue"), "venue_id": r.get("venue_id"),
                   "statsapi_venue_id": r.get("statsapi_venue_id"),
                   "window": r.get("window"),
                   "reason": "Savant's row is not at the venue the club plays in"}
               for o, r in cands.items() if r["venue_match"] is False}
    if hv:
        mism = {o: {"savant_venue": r.get("venue"), "savant_venue_id": r.get("venue_id"),
                    "statsapi_venue_id": hv.get(o)}
                for o, r in dflt.items()
                if hv.get(o) is not None and r.get("venue_id") is not None
                and int(r["venue_id"]) != int(hv[o])}
        venue_check = {
            "status": "checked",
            "basis": ("Savant's default-view venue_id against StatsAPI's home venue "
                      f"for each club, season {season}"),
            "n_default_rows": len(dflt),
            "n_match": sum(1 for o, r in dflt.items() if hv.get(o) is not None
                           and r.get("venue_id") is not None
                           and int(r["venue_id"]) == int(hv[o])),
            "mismatch": mism,
            "absent_from_default_view": sorted(o for o in hv if o not in dflt),
        }
    else:
        venue_check = {"status": "unavailable",
                       "basis": ("StatsAPI's team list could not be read; Savant's "
                                 "own venue attribution stands alone")}
    return {
        "season": season,
        "rolling": int(SHORT_WINDOW_ROLLING),
        "source": ("Baseball Savant statcast-park-factors, rolling="
                   f"{SHORT_WINDOW_ROLLING} for a venue the default view drops, and "
                   "the default view's own row for a venue it carries on a short "
                   "sample; batSide all"),
        "note": ("clubs whose venue holds less than a full 3-season sample only; "
                 "every row carries its PA sample and its window so a consumer can "
                 "shrink it, and no consumer may treat it as a 3-season factor"),
        "default_view_median_n_pa": med,
        "short_sample_pa_share": SHORT_SAMPLE_PA_SHARE,
        "orgs": orgs,
        "refused": refused,
        "venue_check": venue_check,
    }


def park_factors_by_hand(season: int) -> dict:
    """The default 3-season view split by batter side, with the sample.

    {"season", "source", "note", "L": {org: row}, "R": {org: row}}. Read by the
    betting module's DARK capture only (leaderboard_vintages parks_by_hand and
    betting_props_dark's hand arms); the FA engine keeps reading
    `park_factors(season, bat_side)` exactly as before.

    MEASURED 2026-09-11 BEFORE ANY CONSUMER EXISTED, off Savant's own
    single-season pages 2019 and 2021-2026 (176 stable venue-season pairs): the
    per-venue L minus R difference in index_runs has a season-to-season
    correlation of 0.0065, a 3-season reliability of 0.0191, so the RUNS split
    is almost entirely noise at the samples Savant publishes. The index_hr split
    correlates 0.1406 season to season, 0.3293 at three seasons: weak, and
    real. docs/diamond-betting.md section 5i carries the arithmetic."""
    out = {"season": season,
           "source": "Baseball Savant statcast-park-factors, default 3-season view, "
                     "batSide L and R",
           "note": ("per-hand indices at 100 = neutral with the PA sample; the "
                    "runs split is measured near-pure noise and the HR split weak, "
                    "see docs/diamond-betting.md section 5i"),
           "L": {}, "R": {}}
    for side in ("L", "R"):
        out[side] = _park_rows_with_sample(season, side)
    return out


@lru_cache(maxsize=8)
def _short_window_rows(season: int) -> dict:
    """{org: row} off `park_factors_short_window`, or {} on any failure: the
    team-fit park component must never fail a board over an optional view."""
    try:
        return dict((park_factors_short_window(season) or {}).get("orgs") or {})
    except Exception:                                       # noqa: BLE001
        log.warning("fit: short-window park rows for %s unavailable; the short-"
                    "sample clubs keep their default-view reading", season)
        return {}


def venue_park_row(org: str, season: int, bat_side: str = "") -> dict | None:
    """The {woba, hr, runs} the team fit reads for `org`, venue-correct.

    The default 3-season view by batted side, then all hands, exactly as
    before, EXCEPT for a club in betting_model.SHORT_WINDOW_PARK_ORGS whose
    venue holds a short sample (SERVE_ATH_PARK, owner decision 2026-09-11): the
    Athletics, whom the default view drops and who therefore read NEUTRAL here
    until 2026-09-11, take Sutter Health Park's short-window row, and the Rays'
    Tropicana row (2024 and 2026 only) is read as it was. In both cases every
    index's deviation from 100 is scaled by the one shrink the betting model
    prices with (betting_model.short_window_shrink on the venue's all-hands PA).
    The shrink was measured on the runs index and is applied to wOBA and HR as
    the same reliability ratio: an approximation, stated. None when nothing
    resolves, which the caller reads as neutral."""
    pf = park_factors(season, bat_side).get(org) or park_factors(season).get(org)
    try:
        import betting_model as _bm
    except Exception:                                       # noqa: BLE001
        return pf
    if not _bm.SERVE_ATH_PARK or org not in _bm.SHORT_WINDOW_PARK_ORGS:
        return pf
    # A season Savant has not published (a future class's winter) has no view
    # to be short against; it stays neutral and fetches nothing.
    if not park_factors(season):
        return pf
    short = _short_window_rows(season).get(org)
    if not isinstance(short, dict):
        return pf
    if pf is not None and short.get("window") != "default":
        return pf          # a measured default-view row is never replaced
    k = _bm.short_window_shrink(short.get("n_pa"))
    if k is None:
        return pf
    src = pf if pf is not None else short
    out = {}
    for key in ("woba", "hr", "runs"):
        try:
            out[key] = round(100.0 + k * (float(src.get(key)) - 100.0), 1)
        except (TypeError, ValueError):
            out[key] = 100
    return out


def park_component(player: dict, org: str, season: int) -> dict:
    """0..1 score + the underlying indices. Hitters want >100 wOBA/HR in
    their batted side; pitchers want <100. ±25 index points saturate —
    flattened from the v1 ±20 (and the weight cut in fa_config) after the
    measured failure mode: the most suppressive park topped EVERY pitcher's
    fit list because park alone separated otherwise-similar teams.

    The row is `venue_park_row`, so a short-sample venue (the Athletics at
    Sutter Health Park, the Rays' Tropicana row) reads its own shrunk factor
    rather than neutral or an unshrunk two-season number."""
    side = (player.get("bat_throw") or "").split("/")[0].strip().upper()
    bat_side = side if side in ("L", "R") else ""
    pf = venue_park_row(org, season, bat_side) or {"woba": 100, "hr": 100, "runs": 100}
    idx = (pf["woba"] + pf["hr"]) / 2.0
    is_pitcher = _position_norm(player.get("position")) in ("SP", "RP")
    edge = (100.0 - idx) if is_pitcher else (idx - 100.0)
    score = max(0.0, min(1.0, 0.5 + edge / 60.0))
    return {"score": round(score, 3), "park_woba": pf["woba"], "park_hr": pf["hr"],
            "bat_side": bat_side or None, "view": "suppressive-good" if is_pitcher else "hitter-good"}


# ============================================================================
# Rosters, baselines, needs
# ============================================================================

@lru_cache(maxsize=2)
def _contracted_projections(class_year: int) -> dict[str, list[dict]]:
    """{org: [{name, position, war_proj}]} — every Spotrac-contracted
    player signed through ``class_year``, identity-resolved via the shared
    war_daily index and projected with the LATEST fitted models. Unresolved
    players are counted, not faked."""
    from spotrac import scrape_all_spotrac_contracts, _SPOTRAC_TEAM_SLUGS
    slug_to_org = {slug: code for code, slug in _SPOTRAC_TEAM_SLUGS.items()}
    corpus = fp.build_corpus()
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, class_year - 1)
    in_prog = (class_year - 1, fp.season_fraction(league, class_year - 1))
    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    out: dict[str, list[dict]] = defaultdict(list)
    n_unresolved = 0
    for c in scrape_all_spotrac_contracts():
            if (c.get("signed_through") or 0) < class_year:
                continue
            org = slug_to_org.get(c.get("team_slug"))
            name = c.get("player_name")
            if not org or not name:
                continue
            mlbam = fa_ident.resolve(name, range(class_year - 4, class_year))
            if not mlbam:
                n_unresolved += 1
                continue
            pos = _position_norm(c.get("position"))
            side = "pit" if pos in ("SP", "RP") else "hit"
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (class_year - 1, class_year - 2, class_year - 3)
                    if t in seasons]
            if not hist:
                continue
            age_prev = next((h.get("age") for h in hist if h.get("age")), None)
            age = (age_prev + (class_year - hist[0]["season"])) if age_prev else None
            # pt_cap=False: the FA Fit stays on the uncapped engine (PLAN 9.7
            # R4a, owner answer TM-Q1), whatever projection.pt_cap_enabled says.
            proj = fp.project_player(hist, side, class_year, curves, league, age,
                                     in_progress=in_prog, pt_cap=False)
            if proj is None:
                continue
            war = fp.war_from_projection(proj, side, war_map, league, class_year)
            out[org].append({"name": name, "position": pos, "war_proj": round(war, 2)})
    log.info("fit rosters %d: %d orgs, %d unresolved contracted names",
             class_year, len(out), n_unresolved)
    return dict(out)


@lru_cache(maxsize=2)
def _org_and_pos_by_mlbam(season: int) -> dict[int, tuple[str, str]]:
    """{mlbam: (org, position abbreviation)} from the 40-man rosters StatsAPI
    already caches for /projections/ (same _fetch keys proj_export uses, so this
    adds no new network dependency and rides the existing 24h TTL).

    This exists because data/mlb_projections.json carries `team` ONLY on rows
    that joined a Spotrac contract: all 361 arb/pre-arb (`thru` is None) rows
    have team=None, so the artifact alone cannot say which club controls Jazz
    Chisholm Jr. The 40-man roster is the missing org key, and it also supplies a
    real position for the 149 rows whose projection `pos` is the generic "H".
    Returns {} on ANY defect so the caller can fall back deterministically."""
    import json
    try:
        from scrapers import _fetch
    except Exception:                                       # noqa: BLE001
        return {}
    fr = _fetch(f"https://statsapi.mlb.com/api/v1/teams?sportId=1&season={season}",
                f"statsapi_teams_{season}", accept_json=True)
    if fr.status != 200 or not fr.body:
        log.warning("fa_fit: statsapi teams %d unavailable", season)
        return {}
    try:
        teams = json.loads(fr.body).get("teams") or []
    except (ValueError, TypeError):
        return {}
    out: dict[int, tuple[str, str]] = {}
    n_orgs = 0
    for t in teams:
        tid, name = t.get("id"), t.get("name")
        org = canonical_org(name or "")
        if not tid or not org or len(org) > 3:
            continue
        rr = _fetch("https://statsapi.mlb.com/api/v1/teams/"
                    f"{tid}/roster?rosterType=40Man&season={season}",
                    f"statsapi_roster_40man_{tid}_{season}", accept_json=True)
        if rr.status != 200 or not rr.body:
            continue
        try:
            roster = json.loads(rr.body).get("roster") or []
        except (ValueError, TypeError):
            continue
        n_orgs += 1
        for p in roster:
            pid = (p.get("person") or {}).get("id")
            if pid:
                out[int(pid)] = (org, ((p.get("position") or {})
                                       .get("abbreviation") or ""))
    if n_orgs != 30:
        log.warning("fa_fit: 40-man rosters covered %d clubs for %d (need 30)",
                    n_orgs, season)
        return {}
    return out


_GENERIC_POS = {"", "H", "P", "TWP", "INF", "IF", "MI", "UT", "UTIL"}


@lru_cache(maxsize=2)
def _projected_roster(class_year: int) -> dict[str, list[dict]]:
    """F1. {org: [{name, position, war_proj, control_kind}]} for ``class_year``,
    read from the SAME artifact /projections/ serves
    (data/mlb_projections.json) instead of a live Spotrac scrape.

    WHO COUNTS AS ON THE ROSTER for the contract season:
      contract   a vet row with `thru` >= class_year (what v3 saw)
      control    a vet row with `thru` is None - arb and pre-arb, club-controlled
                 and therefore on the roster, which v3 could not see at all
      prospect   a prospect row with `eta` <= class_year
    ORG comes from the row's own `team` where present and from the cached 40-man
    roster otherwise (see _org_and_pos_by_mlbam - the arb/pre-arb rows carry no
    team). POSITION comes from the row's `pos` when it is a real position and
    from the 40-man abbreviation when it is generic ("H").
    WAR is warY1Champ (the champion path) where present, else war[0], matching
    what _contracted_projections computed with fp.war_from_projection.

    Returns {} on ANY defect (missing/unparseable artifact, fewer than 30 orgs
    represented) so team_baselines/needs_matrix can fall back to the Spotrac
    construction with `roster_source` flagged, mirroring the baseline_source
    pattern in team_baselines."""
    import json
    from pathlib import Path
    try:
        d = json.loads((Path(__file__).parent / "data" / "mlb_projections.json")
                       .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("fa_fit: mlb_projections.json unavailable - projected roster "
                    "falls back to the Spotrac contract scrape")
        return {}
    idx = _org_and_pos_by_mlbam(class_year - 1)
    out: dict[str, list[dict]] = defaultdict(list)
    n_no_org = 0
    for r in d.get("vets") or []:
        thru = r.get("thru")
        if thru is not None and int(thru) < class_year:
            continue                        # contract expires before the season
        mlbam = r.get("mlbam")
        ext = idx.get(int(mlbam)) if mlbam else None
        org = r.get("team") or (ext[0] if ext else None)
        if not org:
            n_no_org += 1
            continue
        raw = (r.get("pos") or "").upper().strip()
        if raw in _GENERIC_POS or not raw:
            raw = (ext[1] if ext else "") or raw
        war = r.get("warY1Champ")
        if war is None:
            arr = r.get("war") or []
            war = arr[0] if arr else None
        if war is None:
            continue
        out[org].append({"name": r.get("name"), "position": _position_norm(raw),
                         "war_proj": round(float(war), 2),
                         "control_kind": "contract" if thru is not None else "control"})
    for p in d.get("prospects") or []:
        eta, org = p.get("eta"), p.get("team")
        if not org or eta is None or int(eta) > class_year:
            continue
        arr = p.get("war") or []
        if not arr:
            continue
        out[org].append({"name": p.get("name"),
                         "position": _position_norm(p.get("pos")),
                         "war_proj": round(float(arr[0]), 2),
                         "control_kind": "prospect"})
    if len(out) < 30:
        log.warning("fa_fit: projected roster covered %d orgs (need 30) - "
                    "falling back to the Spotrac scrape", len(out))
        return {}
    log.info("fa_fit projected roster %d: %d orgs, %d rows, %d rows without an "
             "org key", class_year, len(out), sum(len(v) for v in out.values()),
             n_no_org)
    return dict(out)


def _rosters(class_year: int) -> tuple[dict[str, list[dict]], str]:
    """(rosters, source). The projected roster is PRIMARY; the Spotrac
    contract scrape is the flagged fallback."""
    if FIT_ROSTER_SOURCE == "projected":
        proj = _projected_roster(class_year)
        if proj:
            return proj, "mlb_projections"
    return _contracted_projections(class_year), "spotrac_contracts"


@lru_cache(maxsize=2)
def _blockers(class_year: int) -> dict[tuple[str, str], list[dict]]:
    """{(org, position): [prospect blockers]} from the EXISTING platform
    export — read-only, existing FV grid (>= blocker_fv_min), near ETA."""
    import json
    from pathlib import Path
    cfg = _fit_cfg()
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    try:
        d = json.loads((Path(__file__).parent / "data" / "timeseries.json")
                       .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("fit blockers: timeseries.json unavailable")
        return {}
    try:
        xfv_by = (json.loads((Path(__file__).parent / "data" / "xfv.json")
                  .read_text(encoding="utf-8")).get("by_player") or {})
    except (OSError, ValueError):
        xfv_by = {}
    for p in d.get("players") or []:
        # eFV sweep: a near-ETA prospect blocks on the eFV grade (the OOS-better
        # prospect read) where present, consensus FV otherwise. Read-only join, same
        # platform invariant as the timeseries read above. Uses the CONSENSUS-SCALE
        # xfv_grade_quantile (NOT the now-realized headline xfv_grade): blocker_fv_min is
        # a consensus-scale threshold, so the grade fed to it must stay on that scale.
        _xg = (xfv_by.get(p.get("player_key")) or {}).get("xfv_grade_quantile")
        fv = _xg if _xg is not None else p.get("fv_close")
        eta = (p.get("eta") or {}).get("year")
        if (fv is not None and fv >= cfg["blocker_fv_min"] and p.get("org")
                and eta is not None and eta <= class_year + cfg["blocker_eta_horizon"]):
            out[(p["org"], _position_norm(p.get("position")))].append(
                {"player_key": p["player_key"], "player_name": p["player_name"],
                 "fv": fv, "eta": eta})
    return dict(out)


def needs_matrix(class_year: int) -> dict[str, dict[str, dict]]:
    """{org: {position: {incumbent_war, incumbents, blockers, mlb_blockers,
    outgoing}}}. Blockers come in two kinds: PROSPX prospects (near-ETA,
    FV grid) and MLB incumbents already producing at the slot the signing
    would displace (war_proj >= incumbent_block_war) — a team whose
    displaced starter projects 3 WAR is not a buyer there, and the UI says
    WHO is doing the blocking, not just that it's blocked."""
    cfg = _fit_cfg()
    inc_block = float(cfg.get("incumbent_block_war", 2.5))
    rosters, roster_source = _rosters(class_year)
    blockers = _blockers(class_year)
    outgoing: dict[tuple[str, str], list[str]] = defaultdict(list)
    for p in storage.load_fa_class_players(class_year).values():
        if p.get("from_team"):
            outgoing[(p["from_team"], _position_norm(p.get("position")))].append(p["player_name"])
    out: dict[str, dict[str, dict]] = {}
    # F2 SILENT-DROP FIX. The org universe is the 30 MLB CLUBS, not "clubs that
    # happen to have a qualifying roster row". fit_scores iterates needs.items(),
    # so a club absent here is absent from every player's 30-club fit vector - the
    # measured MIA-has-no-baseWins defect. A club with an empty roster is scored
    # explicitly at maximum need instead, which is the truthful reading.
    # from_team rides foreign postings too (Woo Jin An -> "KOR"), and a posting
    # league must not get a needs page of its own, so the union is intersected
    # with the club list rather than taken raw.
    orgs = set(ORGS) | (set(rosters) & set(ORGS))
    for org in sorted(orgs):
        out[org] = {}
        roster = rosters.get(org, [])
        for pos in POSITIONS:
            inc = sorted((r for r in roster if r["position"] == pos),
                         key=lambda r: -r["war_proj"])
            # Need is about DISPLACEMENT, not unit totals: an ace joining
            # a rotation displaces the 5th starter, not the staff sum; a
            # position player displaces the incumbent starter; a reliever
            # the back of the pen. unit_war (the sum) stays for context.
            slot = {"SP": 4, "RP": 2}.get(pos, 0)
            # F2 SLOT RULE. v3 read `inc[slot] if len(inc) > slot else 0.0`, which
            # handed MAXIMUM need to any club with <= 4 contracted starters - and
            # since the v3 roster could not see arb/pre-arb arms, that was most of
            # the league (SFG's 5th-starter slot scored 0.00 while its real SP5
            # projects 0.26). With the projected roster the slot is usually filled;
            # when it still is not, fall back to the WEAKEST player actually at the
            # position rather than asserting zero, because a club with four
            # starters does have a fifth arm, just not a good one. A position with
            # nobody at all keeps 0.0 - that one really is empty.
            displaced = (inc[slot]["war_proj"] if len(inc) > slot
                         else (inc[-1]["war_proj"] if inc else 0.0))
            # How much of the displacement depth actually exists. 1.0 means the
            # slot itself is populated; below 1.0 means "thin" - and the UI can
            # now tell "thin because young and cheap" from "empty".
            completeness = min(1.0, len(inc) / float(slot + 1))
            # MLB incumbent blocker: the player the signing would actually
            # DISPLACE (the starter at the slot, the 5th starter, the back
            # of the pen) when he himself projects as a real producer. An
            # ace doesn't block adding another SP — only a full slot does.
            # The WAR already discounts need through the gap; this list
            # exists so the surfaces can NAME the blocker.
            mlb_blockers = ([{"player_name": inc[slot]["name"],
                              "war_proj": inc[slot]["war_proj"]}]
                            if len(inc) > slot and inc[slot]["war_proj"] >= inc_block
                            else [])
            out[org][pos] = {
                "unit_war": round(sum(max(0.0, r["war_proj"]) for r in inc[:5 if pos == "SP" else 2]), 2),
                "displaced_war": round(max(0.0, displaced), 2),
                "incumbents": inc[:3],
                "blockers": blockers.get((org, pos), []),
                "mlb_blockers": mlb_blockers,
                "outgoing": outgoing.get((org, pos), []),
                "roster_completeness": round(completeness, 2),
                "n_at_position": len(inc),
                "n_controlled": sum(1 for r in inc
                                    if r.get("control_kind") in ("control", "prospect")),
                "roster_source": roster_source,
            }
    return out


@lru_cache(maxsize=1)
def _outlook_wins(class_year: int) -> dict[str, float]:
    """{org: projected wins in ``class_year``} read from the /projections/
    module's committed artifact (data/mlb_projections.json team_outlook).

    Returns {} on ANY defect (missing file, unparseable, no team_outlook, a
    club count other than 30, or no byYear row for the season) so the caller
    can fall back deterministically. Never partially fills: a 22-club read
    would silently give 8 clubs a different baseline definition than the
    other 22, which is exactly the cross-page contradiction this replaces."""
    import json
    from pathlib import Path
    try:
        d = json.loads((Path(__file__).parent / "data" / "mlb_projections.json")
                       .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("fa_fit: mlb_projections.json unavailable — "
                    "team baselines fall back to the contracted core")
        return {}
    out: dict[str, float] = {}
    for t in (d.get("team_outlook") or []):
        org = t.get("team")
        if not org:
            continue
        for by in (t.get("byYear") or []):
            if by.get("season") != class_year:
                continue
            # THE FA FIT FIELD (docs/TEAM_PROJECTIONS_GATE.md section 6.2, PLAN
            # 9.7 round 5): the un-budgeted wins of the pre-free-agency frame.
            # While the T2 club budget (proj_export.TEAM_PT_BUDGET_LIVE) is
            # off, `wins` is that total; when it serves, the same total rides
            # under `winsFaFit` and `wins` becomes the budgeted roll-up, so the
            # baseline here never moves with that flag.
            w = by.get("winsFaFit", by.get("wins"))
            if w is not None:
                out[org] = float(w)
                break
    if len(out) != 30:
        log.warning("fa_fit: team_outlook covers %d clubs for %d (need 30) — "
                    "team baselines fall back to the contracted core",
                    len(out), class_year)
        return {}
    return out


@lru_cache(maxsize=2)
def team_baselines(class_year: int) -> dict[str, dict]:
    """{org: {war_committed, baseline_wins, fill_wins, baseline_source}}.

    ``baseline_wins`` is the club's projected win total for the contract
    season, read from the SAME artifact /projections/ serves
    (data/mlb_projections.json team_outlook). The FA module used to rebuild
    its own baseline out of contracted-player WAR plus a flat
    ``roster_fill_wins`` stand-in for the arb/pre-arb slots it cannot see.
    Measured 2026-07-25 on the committed artifacts for 2027, comparing the
    number ``win_leverage`` actually consumed (replacement 47.7 + contracted
    WAR + fill 12) against team_outlook: mean |delta| 5.60 wins, signed mean
    +5.15, sd 3.23, max 10.0 (COL 81.3 vs 71.3), and the 30 club totals
    summed to 2584.4 where a league season sums to 2430.0 by construction.
    Two pages of the same site published different win projections for the
    same club, and the FA side invented 154.4 league wins that do not exist.
    Against the BARE baseline_wins (before the fill is added) the gap runs
    the other way: mean |delta| 6.85, signed -6.85, max 16.1.

    ``fill_wins`` is what ``win_leverage`` must still add: 0 on the outlook
    source (a full win total is already a full win total) and the configured
    ``roster_fill_wins`` on the fallback, where the baseline genuinely
    excludes the unsigned slots. FALLBACK: any defect in the artifact
    (absent, unparseable, or not covering all 30 clubs for the season) drops
    the whole module back to the contracted-core construction, flagged in
    ``baseline_source`` so the discrepancy is visible rather than silent."""
    cfg = _fit_cfg()
    fill = float((cfg.get("win_curve") or {}).get("roster_fill_wins", 0))
    wins = _outlook_wins(class_year)
    rosters, roster_source = _rosters(class_year)
    out = {}
    # F2: every club gets a row, including one with an empty roster.
    for org in ORGS:
        roster = rosters.get(org) or []
        war = sum(max(0.0, r["war_proj"]) for r in roster)
        row = {"war_committed": round(war, 1), "roster_source": roster_source,
               "n_roster": len(roster)}
        if org in wins:
            row["baseline_wins"] = round(wins[org], 1)
            row["fill_wins"] = 0.0
            row["baseline_source"] = "mlb_projections"
        else:
            row["baseline_wins"] = round(cfg["replacement_wins"] + war, 1)
            row["fill_wins"] = fill
            row["baseline_source"] = "contracted_core"
        out[org] = row
    return out


@lru_cache(maxsize=1)
def _playoff_pct_now(class_year: int) -> dict[str, float]:
    """{org: current-season playoffPct} from data/mlb_projections.json
    team_outlook[].current.playoffPct. REPORTED as a cross-check, not consumed:
    it is the IN-PROGRESS season's probability, not the contract season's, and
    the artifact is currently missing the whole `current` block for one club
    (ARI reads null as of 2026-07-29), which is a defect in that artifact rather
    than something this module should paper over."""
    import json
    from pathlib import Path
    try:
        d = json.loads((Path(__file__).parent / "data" / "mlb_projections.json")
                       .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, float] = {}
    for t in (d.get("team_outlook") or []):
        org = t.get("team")
        p = (t.get("current") or {}).get("playoffPct")
        if org and p is not None:
            out[org] = float(p)
    return out


def playoff_prob(wins: float, fill_wins: float | None = None) -> float:
    """P(postseason) at a talent level, from the SAME documented logistic
    win_leverage differentiates. This is the level term; win_leverage is its
    marginal term. One curve, one input, all 30 clubs, no imputation."""
    import math
    wc = _fit_cfg()["win_curve"]
    f = float(wc.get("roster_fill_wins", 0)) if fill_wins is None else float(fill_wins)
    return 1.0 / (1.0 + math.exp(-((wins + f) - wc["center"]) / wc["scale"]))


def contention(org: str, class_year: int, wins: float,
               fill_wins: float | None = None) -> dict:
    """F3. The window component: MARGINAL playoff leverage blended with the
    LEVEL of postseason probability at the club's projected win total for the
    contract season.

    v3 used the marginal term alone. Leverage is 4p(1-p), symmetric about the
    curve center, so a club with no chance and a club already locked in both
    score low while a bubble club scores 1.0 - and the measured consequence was a
    0%-playoff Giants scoring 0.624 against a locked-in Dodgers' 0.175, which is
    the wrong answer to the question a free agent is asking. The window is not
    "how close is this club to a coin flip"; it is "does this club win because of
    me", and that needs the level as well as the derivative.

    WHY NOT team_outlook[].current.playoffPct, which the plan named: it is the
    IN-PROGRESS season's probability, not the contract season's, and the artifact
    is missing the entire `current` block for one club right now. Deriving the
    level from the club's own PROJECTED CLASS-YEAR wins through the curve the
    module already documents keeps one definition for all 30 clubs, uses the
    right season, and imputes nothing. The served playoffPct is attached to the
    component output as a cross-check so the two can be compared on the surface.

    FIT_WINDOW_LEVEL_W = 0.6 is chosen so the ordering constraint holds for EVERY
    possible input pair, not on average: a 0%-playoff club can reach at most
    1 - 0.6 = 0.40 while a 90% club cannot fall below 0.6 * 0.9 = 0.54."""
    lev = win_leverage(wins, fill_wins)
    if FIT_WINDOW_MODE != "playoff":
        return {"score": round(lev, 3), "leverage": round(lev, 3),
                "playoff_prob": None, "window_source": "leverage_v3"}
    p = playoff_prob(wins, fill_wins)
    w = FIT_WINDOW_LEVEL_W
    served = _playoff_pct_now(class_year).get(org)
    return {"score": round((1.0 - w) * lev + w * p, 3),
            "leverage": round(lev, 3), "playoff_prob": round(p, 3),
            "playoff_pct_now": round(served, 3) if served is not None else None,
            "window_source": "playoff_blend_v4"}


def win_leverage(wins: float, fill_wins: float | None = None) -> float:
    """Marginal playoff leverage at a talent level: P×(1−P) of the fixed
    documented logistic, normalized to peak 1.0 at the curve center.

    ``fill_wins`` is added to ``wins`` before the curve: the contracted-core
    baseline excludes the arb/pre-arb slots a club will fill anyway, so it
    needs the configured stand-in. A full projected win total does not, and
    passes 0. None keeps the configured default (the historical signature)."""
    import math
    wc = _fit_cfg()["win_curve"]
    f = float(wc.get("roster_fill_wins", 0)) if fill_wins is None else float(fill_wins)
    p = 1.0 / (1.0 + math.exp(-((wins + f) - wc["center"]) / wc["scale"]))
    return 4.0 * p * (1.0 - p)


# ============================================================================
# Affordability + behavior
# ============================================================================

@lru_cache(maxsize=2)
def affordability(class_year: int) -> dict[str, dict]:
    """{org: {committed_usd, tax_payroll_usd, threshold_usd, space_usd,
    carry_forward, payor_status}} — rule-versioned; the 2027 threshold is
    an explicit carry-forward and the flag rides every consumer. Space is
    measured on the CBT BASIS (Spotrac's own tax-space figure when
    present) — the number front offices actually budget against."""
    thr = fa_cba.cbt_threshold(class_year)
    pay = storage.load_fa_team_payroll(class_year)
    tax_prev = storage.load_fa_team_payroll(class_year - 1)
    out = {}
    for (team, _season), row in pay.items():
        committed = row.get("total_payroll_usd") or 0
        tax_payroll = row.get("tax_payroll_usd")
        space = row.get("space_usd")
        if space is None:
            space = thr["threshold_usd"] - (tax_payroll or committed)
        prev = tax_prev.get((team, class_year - 1)) or {}
        out[team] = {
            "committed_usd": committed,
            "tax_payroll_usd": tax_payroll,
            "threshold_usd": thr["threshold_usd"],
            "space_usd": space,
            "carry_forward": thr["carry_forward"],
            "payor_status": prev.get("payor_status_raw") or row.get("payor_status_raw"),
        }
    return out


@lru_cache(maxsize=1)
def behavior_priors() -> dict[str, dict]:
    """Per-team WILL-SPEND priors from the team's OWN signings in the
    corpus: max guarantee ever, count of $100M deals, total FA spend, and
    the recent 3-winter outlay (spending appetite is a recency story —
    an owner who spent $400M since 2024 is live in a way 2016 can't show)."""
    signings = storage.load_fa_signings()
    last_winter = max((y for (_k, y) in signings), default=0)
    out: dict[str, dict] = defaultdict(lambda: {"max_guarantee_usd": 0,
                                                "n_100m": 0, "total_spend_usd": 0,
                                                "recent_spend_usd": 0,
                                                "guarantees": []})
    for (_k, y), s in signings.items():
        team, g = s.get("to_team"), s.get("guarantee_usd") or 0
        if not team or not s.get("mlb_deal"):
            continue
        b = out[team]
        b["max_guarantee_usd"] = max(b["max_guarantee_usd"], g)
        b["total_spend_usd"] += g
        # F4: the club's OWN guarantee distribution. behavior's will-spend term
        # needs to answer "has this club ever routinely gone THIS big", which a
        # single max cannot, and a sorted list can.
        b["guarantees"].append(g)
        # TEAMFIT CONDITIONAL (2026-08-19): the banded recent/rich terms need
        # the club's per-deal (winter, guarantee) events, not just aggregates.
        b.setdefault("events", []).append((y, g))
        if y >= last_winter - 2:
            b["recent_spend_usd"] += g
        if g >= 100_000_000:
            b["n_100m"] += 1
    for b in out.values():
        b["guarantees"].sort()
    return dict(out)


@lru_cache(maxsize=1)
def _corpus_last_winter() -> int:
    """Newest class year in the signings corpus (the recency anchor both the
    aggregate recent term and the banded conditional terms share)."""
    signings = storage.load_fa_signings()
    return max((y for (_k, y) in signings), default=0)


def _cond_terms(events: list, guar: float, y_recent_min: int) -> tuple:
    """(recent band outlay, career band deal count) for one club's signing
    events [(winter, guarantee), ...] against THIS player's price band
    [g/F, g*F], F = fa_config fit.behavior_cond_band_factor (frozen 2.5,
    sync-tested against fa_fit_backtest.TEAMFIT_COND_BAND_FACTOR). Mirrors
    fa_fit_backtest._cond_terms exactly; kept local so serving never imports
    the backtest's heavy chain (standings/payroll reconstruction)."""
    factor = float(_fit_cfg().get("behavior_cond_band_factor", 2.5))
    lo, hi = guar / factor, guar * factor
    outlay, n_band = 0.0, 0
    for y, g in events or []:
        if lo <= g <= hi:
            n_band += 1
            if y >= y_recent_min:
                outlay += g
    return outlay, n_band


def _spend_reach(prior: dict, guar: float) -> float:
    """F4. Share of the club's OWN historical MLB-deal guarantees that are at
    least as large as this price - "how routine is a deal this size here".

    Replaces `min(1.0, max_guarantee / price) ** 0.5`, whose clip pinned it at
    1.0 for nearly every player (any club that has ever signed a $100M deal is at
    the cap for every sub-$100M free agent), turning the highest-weighted
    component into a per-club CONSTANT that took at most three distinct values
    across all 223 members. That constant is the mechanism behind
    Dodgers-for-everyone: with behavior at weight 0.45 and no player dependence,
    the club with the richest history wins almost every list before need is
    consulted. The share form is monotone decreasing in price, never saturates,
    and is 0 for a club that has genuinely never gone there."""
    gs = prior.get("guarantees") or []
    if not gs:
        return 0.0
    if FIT_BEHAVIOR_MODE != "percentile":
        return min(1.0, (prior.get("max_guarantee_usd") or 0) / max(guar, 1)) ** 0.5
    import bisect
    return (len(gs) - bisect.bisect_left(gs, guar)) / float(len(gs))


# ============================================================================
# Composite fit
# ============================================================================

def _is_taxpayer(payor_status: str | None) -> bool:
    """Spotrac's payor strings are free-form; anything that isn't an
    explicit non-payor reads as a taxpayer signal."""
    s = (payor_status or "").strip().lower()
    return bool(s) and "non" not in s


def fit_scores(player: dict, market_pred: dict, class_year: int,
               top_n: int = 5) -> list[dict]:
    """Per-team transparent composite for one class member. ``player`` is a
    class row (position, bat_throw, from_team); ``market_pred`` carries
    proj_guarantee_usd / proj_aav_usd. Every component returns its inputs."""
    cfg = _fit_cfg()
    w = cfg["weights"]
    bw = cfg.get("behavior_weights") or {"max_guar": 0.5, "recent": 0.3, "rich": 0.2}
    pos = _position_norm(player.get("position"))
    needs = needs_matrix(class_year)
    bases = team_baselines(class_year)
    afford = affordability(class_year)
    priors = behavior_priors()
    # League-max recent spend normalizes the will-spend component to [0,1].
    max_recent = max((b.get("recent_spend_usd") or 0) for b in priors.values()) or 1
    # TEAMFIT CONDITIONAL (gated PASS 2026-08-19, shipped: recent/rich confined
    # to the player's price band; docs/fa-2026-08-19/TEAMFIT_CONDITIONAL_GATE.md,
    # artifact fa_gate3_eval.json teamfit_conditional_gate.shipped == true).
    cond_on = bool(cfg.get("behavior_conditional"))
    _guar_band = float(market_pred.get("proj_guarantee_usd") or 20_000_000)
    _cond, _max_band = {}, 0.0
    if cond_on:
        _yrmin = _corpus_last_winter() - 2
        _cond = {org: _cond_terms((priors.get(org) or {}).get("events") or [],
                                  _guar_band, _yrmin) for org in needs}
        _max_band = max((v[0] for v in _cond.values()), default=0.0)
    # `is None` (not `or`): a projected war_y1 of exactly 0.0 is a real value (a
    # replacement-level bat), not "missing" -- `or 1.0` gave zero-WAR members a phantom
    # 1.0-WAR displacement gap and inflated their fit scores.
    _w1 = (player.get("_war_path") or {}).get("war_y1")
    war1 = _w1 if _w1 is not None else 1.0
    rows = []
    for org, by_pos in needs.items():
        cell = by_pos.get(pos) or {}
        gap = max(0.0, war1 - (cell.get("displaced_war") or 0.0))
        # Prospect blockers carry the multiplier (they're invisible to the
        # contracted-roster gap); MLB incumbents already discount need
        # continuously THROUGH the gap, so they're listed but not
        # double-counted.
        prospect_blocked = bool(cell.get("blockers"))
        need_base = (min(1.0, gap / max(war1, NEED_MIN_WAR))
                     if NEED_MODE == "share"
                     else min(1.0, gap / cfg["need_war_saturation"]))
        need = need_base * (float(cfg.get("prospect_block_multiplier", 0.5))
                            if prospect_blocked else 1.0)
        blocked_by = ([{"player_name": b["player_name"], "kind": "prospect"}
                       for b in (cell.get("blockers") or [])]
                      + [{"player_name": b["player_name"], "kind": "mlb",
                          "war_proj": b.get("war_proj")}
                         for b in (cell.get("mlb_blockers") or [])])
        base = bases.get(org) or {"baseline_wins": cfg["replacement_wins"],
                                  "fill_wins": None,
                                  "baseline_source": "replacement_floor"}
        win = contention(org, class_year, base["baseline_wins"] + war1 / 2.0,
                         base.get("fill_wins"))
        window = win["score"]
        a = afford.get(org) or {}
        b = priors.get(org) or {}
        aav = market_pred.get("proj_aav_usd") or 10_000_000
        space = a.get("space_usd")
        afford_score = (max(0.0, min(1.0, space / (aav * 2.0))) if space is not None else 0.5)
        # Habitual-taxpayer floor: a club that lives above the threshold AND
        # keeps signing nine-figure deals is not priced out by CBT space —
        # its real constraint is appetite (the behavior component's job).
        if (_is_taxpayer(a.get("payor_status")) and (b.get("n_100m") or 0) >= 3):
            afford_score = max(afford_score, float(cfg.get("taxpayer_afford_floor", 0.4)))
        park = park_component(player, org, class_year - 1)
        guar = market_pred.get("proj_guarantee_usd") or 20_000_000
        scale = _spend_reach(b, float(guar))
        # HISTORY. The aggregate form: `recent` divides by the league-max
        # 3-winter outlay and `rich` clips at n_100m/5, both CLUB CONSTANTS,
        # the mechanism behind Gate 3's concentration failure (one club top-1
        # for 228 of 228). The R6.3 rewrite (within-club conditional RATES,
        # 2026-08-04) was refuted: its falsification showed no change confined
        # to this block could reach the gate ON THAT CANDIDATE.
        #
        # SUPERSEDED FOR THE BANDED VARIANT ONLY (2026-08-19): the price-band
        # candidate (recent/rich confined to [g/F, g*F]) passed all four
        # frozen clauses of docs/fa-2026-08-19/TEAMFIT_CONDITIONAL_GATE.md
        # (chain MRR inside its MDE floor, concentration tripwire GREEN,
        # LAD behavior top-1 1.00 -> 0.38, permuted control null) and the
        # R6.3 falsification number does not reproduce on the current class.
        # The gate record lives in fa_gate3_eval.json teamfit_conditional_gate;
        # any OTHER behavior-only rewrite stays banned per R6.3.
        if cond_on:
            _outlay, _nband = _cond.get(org) or (0.0, 0)
            recent = (_outlay / _max_band) if _max_band > 0 else 0.0
            rich = min(1.0, _nband / 5.0)
        else:
            recent = min(1.0, (b.get("recent_spend_usd") or 0) / max_recent)
            rich = min(1.0, (b.get("n_100m") or 0) / 5.0)
        behavior = bw["max_guar"] * scale + bw["recent"] * recent + bw["rich"] * rich
        comp = (w["need"] * need + w["window"] * window + w["afford"] * afford_score
                + w["park"] * park["score"] + w["behavior"] * behavior)
        rows.append({
            "org": org, "fit": round(comp, 3),
            "components": {
                "need": {"score": round(need, 3), "war_gap": round(gap, 2),
                         "displaced_war": cell.get("displaced_war"),
                         "unit_war": cell.get("unit_war"),
                         "roster_completeness": cell.get("roster_completeness"),
                         "n_at_position": cell.get("n_at_position"),
                         "n_controlled": cell.get("n_controlled"),
                         "roster_source": cell.get("roster_source"),
                         "blocked_by": blocked_by,
                         "outgoing": cell.get("outgoing") or []},
                "window": {**win,
                           "baseline_wins": base.get("baseline_wins"),
                           "baseline_source": base.get("baseline_source")},
                "afford": {"score": round(afford_score, 3),
                           "space_usd": space,
                           "tax_payroll_usd": a.get("tax_payroll_usd"),
                           "carry_forward": a.get("carry_forward", True),
                           "payor_status": a.get("payor_status")},
                "park": park,
                "behavior": {"score": round(behavior, 3),
                             "max_guarantee_usd": b.get("max_guarantee_usd"),
                             "recent_spend_usd": b.get("recent_spend_usd"),
                             "n_100m": b.get("n_100m", 0),
                             **({"conditional": True,
                                 "band_recent_outlay_usd": round((_cond.get(org) or (0.0, 0))[0]),
                                 "band_deal_count": (_cond.get(org) or (0.0, 0))[1]}
                                if cond_on else {})},
            },
        })
    rows.sort(key=lambda r: -r["fit"])
    return rows[:top_n]
