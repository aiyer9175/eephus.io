# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Stats module - Hitter Leaderboards sidecar (data/hitter_leaderboards.json).

The hitter analog of bullpen_export.py / starter_export.py. Assembles the HEM+
hitter board + team Offense+ from the MLB StatsAPI season HITTING leaderboard
(fa_sources.fetch_statsapi_season_stats, which is cached per season). No leverage
or durability walk: HEM+ is a pure offensive-rate skill index (shrunk wOBA, 100 =
average qualified hitter); volume (PA), baserunning (SB), and the rate slash line
ride as context columns.

Feeds hem_plus.score_pool(), which anchors HEM+ to the hitter pool and rolls up
team offenses. Also builds the yearly hitter-history file for the /mlbstats/
history tabs.

One column on this board is NOT ours: wRC+ is the industry's published value,
read verbatim from MLB's bulk season-total sabermetrics feed and joined by MLBAM
id (load_published_wrc_plus). This site derives no wRC+; the column exists so the
site's own HEM+ can be read beside the number the industry publishes. It is a
live-board column only: export_history does not carry it, so a past-season board
drops it rather than rendering a blank column.

Run: `python hitter_export.py [season]`  or  `python hitter_export.py history`.
The live run also rebuilds the Defense board afterwards (export_then_defense),
because that board joins this one's HEM+.
Wired into run_monthly (best-effort). NETWORK-GATED + BEST-EFFORT: nothing
fetches at import; any pull failure logs and returns 0 rather than aborting.
"""
from __future__ import annotations

import functools
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import hem_plus
import pitch_rates_boards
from hem_plus import Hitter
from bullpen_export import (_team_abbrev_map, _num, score_war_rate,
                            stamp_team_war, stamp_history_war,
                            join_war_rate_3yr, guard_nonempty_block,
                            team_basis_meta, basis_rows_for, _active_mlbam_ids,
                            _warn_unresolved_teams, _ingest_red,
                            WAR_RATE_POOL_MIN_PA, WAR_RATE_DISPLAY_MIN_PA)
import fa_sources
from war_source import safe_ewar_vintage as _war_source_vintage

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "hitter_leaderboards.json"
HISTORY_PATH = DATA_DIR / "hitter_history.json"
EVAL_PATH = DATA_DIR / "hem_plus_eval.json"
MULTIYR_PATH = DATA_DIR / "hem_plus_multiyear_eval.json"
HISTORY_SEASONS = [2021, 2022, 2023, 2024, 2025]


def _join_hem_plus_3yr(hitters: list[dict], season: Optional[int] = None) -> dict:
    """Stamp hem_plus_3yr / percentile / tag from the Last 3 window's HEM+
    (bullpen_export.join_window_3yr: the value the Last 3 view prints, behind
    the served-eWAR basis guard, uncoloured with the window pool's percentile).
    Companion SKILL column; an unmatched hitter renders blank. MULTIYR_PATH
    stays the gate record and is not read for display."""
    from bullpen_export import join_window_3yr
    return join_window_3yr(hitters, board="hitters", block="hitters",
                           metric="hem_plus", season=season, who="hitters")


@functools.lru_cache(maxsize=1)
def _tmap() -> dict:
    """Team id -> abbreviation, fetched once (offline-safe: {} on failure)."""
    return _team_abbrev_map()


def load_season_hitting(season: int) -> list[dict]:
    """All MLB hitters' season lines from the StatsAPI hitting leaderboard
    (playerPool 'all'), via the cached fa_sources fetcher. One flat row per
    player. [] on any failure (offline / API change)."""
    try:
        rows = fa_sources.fetch_statsapi_season_stats(int(season), "hitting")
    except Exception as e:
        _log.warning("StatsAPI season hitting (%s) failed: %s", season, e)
        return []
    if not rows:
        return []
    tmap = _tmap()
    out = []
    n_unresolved = 0
    for r in rows:
        st = r.get("stat") or {}
        pl = r.get("player") or {}
        tm = r.get("team") or {}
        pid = pl.get("id")
        if not pid:
            continue
        tid = tm.get("id") if isinstance(tm, dict) else None
        # `or ""` is kept (a genuinely unassigned row must still serve a blank),
        # but the blank is COUNTED now: see bullpen_export._warn_unresolved_teams.
        abbr = tmap.get(tid) or ""
        if not abbr:
            n_unresolved += 1
        out.append({
            "mlbam": int(pid), "name": pl.get("fullName", ""),
            "team": abbr,
            "PA": st.get("plateAppearances"), "AB": st.get("atBats"), "H": st.get("hits"),
            "2B": st.get("doubles"), "3B": st.get("triples"), "HR": st.get("homeRuns"),
            "BB": st.get("baseOnBalls"), "IBB": st.get("intentionalWalks"),
            "HBP": st.get("hitByPitch"), "SF": st.get("sacFlies"), "SO": st.get("strikeOuts"),
            "SB": st.get("stolenBases"), "CS": st.get("caughtStealing"),
            "RBI": st.get("rbi"), "R": st.get("runs"),
            # MLB's primary-position label on the same row (0 new calls). The
            # lineup cards read it to keep pitchers off the bench and to name a
            # DH, which the fielding-innings feed cannot see.
            "primary_pos": (r.get("position") or {}).get("abbreviation"),
            # Pitches seen (0 new calls). Read only by the P/PA columns, which
            # ship behind pitch_rates.SERVE_PITCH_RATES.
            "NP": st.get("numberOfPitches"),
        })
    _warn_unresolved_teams(n_unresolved, len(out), tmap, f"hitting {season}")
    # Owner decision 2026-08-05: team charts follow the current roster, not the
    # club the stats were earned with. See bullpen_export.TEAM_BASIS for the
    # basis note and the one-line revert.
    from bullpen_export import apply_current_team
    apply_current_team(out, label=f"hitting {season}")
    return out


def build_hitters(rows: list[dict]) -> list[Hitter]:
    """StatsAPI season rows -> Hitter records."""
    out: list[Hitter] = []
    for r in rows:
        mlbam = r.get("mlbam")
        if mlbam is None:
            continue
        out.append(Hitter(
            key=str(mlbam), name=str(r.get("name", "")), team=str(r.get("team", "")),
            mlbam=int(mlbam),
            pa=_num(r.get("PA")) or 0.0, ab=_num(r.get("AB")) or 0.0, h=_num(r.get("H")) or 0.0,
            doub=_num(r.get("2B")) or 0.0, trip=_num(r.get("3B")) or 0.0, hr=_num(r.get("HR")) or 0.0,
            bb=_num(r.get("BB")) or 0.0, ibb=_num(r.get("IBB")) or 0.0, hbp=_num(r.get("HBP")) or 0.0,
            sf=_num(r.get("SF")) or 0.0, so=_num(r.get("SO")) or 0.0,
            sb=_num(r.get("SB")) or 0.0, cs=_num(r.get("CS")) or 0.0,
            rbi=_num(r.get("RBI")) or 0.0, r=_num(r.get("R")) or 0.0,
            primary_pos=r.get("primary_pos") or None,
            np=_num(r.get("NP")),
        ))
    return out


def _np_pos_by_id(hitters: list[Hitter]) -> tuple[dict, dict]:
    """{mlbam: pitches seen} and {mlbam: primary position} off the Hitter
    records, for the P/PA join (pitch_rates_boards)."""
    np_by_id, pos_by_id = {}, {}
    for h in hitters:
        if h.mlbam is None:
            continue
        np_by_id[int(h.mlbam)] = h.np
        pos_by_id[int(h.mlbam)] = h.primary_pos
    return np_by_id, pos_by_id


# --------------------------------------------------------------------------- #
# Published wRC+ (INDUSTRY value, displayed verbatim - this site derives none)
# --------------------------------------------------------------------------- #
# ONE bulk season-scoped call, cached on disk by scrapers._fetch exactly like its
# neighbours in fa_sources (fa_statsapi_*, savant_pf_*). Season totals BY
# CONSTRUCTION: a season-scoped sabermetrics request returns one aggregated row
# per player, so there is no stint decomposition to mis-index (see
# load_published_wrc_plus for the measurement and the guard).
# The URL lives in saber_feed, the one loader every reader of this feed shares
# (the Defense board and the eWAR replica read the same rows).
from saber_feed import SABER_URL as _SABER_URL  # noqa: E402

# Color bands for the wRC+ column, DERIVED FROM THE MEASURED SPREAD of published
# wRC+, NOT inherited from HEM+.
#
# Why they cannot be inherited: HEM+ is a shrunk ratio index and published wRC+
# is not, so the same 100 anchor sits on two different widths. Measured over the
# pooled 2021-2026 QUALIFIED pools (n = 2,069 hitter-seasons: the five history
# boards plus the live board): published wRC+ mean 100.86 / SD 25.27 against
# HEM+ mean 99.15 / SD 17.69, a ratio of 1.43. Reusing hemClass 88/112/130 on
# that wider distribution would paint 29.9 / 37.9 / 19.7 / 12.4 percent of
# qualified hitters low / average / good / elite, against the HEM+ reference of
# 26.5 / 50.9 / 17.6 / 4.9. It would call elite 2.5x as often as HEM+ does and
# hollow out the average band. So the bands are re-derived.
#
# Derivation, on the ROUNDED integers this column actually displays, by two
# independent methods that agree:
#   percentile-match (put each break at the same qualified-pool percentile as the
#     HEM+ break it replaces): 88 -> 85.0, 112 -> 119.0, 130 -> 141.0
#   sigma-match (put each break at the same z on the wRC+ pool):
#                              88 -> 84.9, 112 -> 119.2, 130 -> 144.9
# Rounded to the nearest 5 that minimises total band-share error against HEM+
# (a sweep of all 125 round-5 triples over low 75-95 / good 110-130 / elite
# 135-155): 85 / 120 / 145, L1 error 2.80 percentage points summed over the four
# bands (shares 26.0 / 52.1 / 17.9 / 4.1 against the HEM+ reference 26.5 / 50.9 /
# 17.6 / 4.9). Runner-up 85/120/150 scored 4.54, then 85/120/140 at 4.74.
#
# Cross-check, not an input: the industry's own published rule-of-thumb reading
# of wRC+ breaks at 80 (below average), 115 (above average) and 140 (great). The
# measurement landed within 5 points of all three without being pointed at them.
#
# assets/mlbstats.js wrcClass() mirrors these three numbers, and
# test_hitter_wrc_plus.py pins the mirror so the two cannot drift.
WRC_PLUS_BANDS = {"low": 85, "good": 120, "elite": 145}
# Sample floor for the PUBLISHED wRC+ column, matching WAR/PA+, the site's
# existing rate-index convention. Published wRC+ is UNSHRUNK, unlike the EB-shrunk
# HEM+ it sits beside: at 1 PA, HEM+ reads 100.0 and wRC+ reads 481. See
# _join_wrc_plus for the measurement.
WRC_PLUS_MIN_PA = 100


@functools.lru_cache(maxsize=8)
def load_published_wrc_plus(season: int) -> dict:
    """MLB's PUBLISHED wRC+ for one season, keyed by MLBAM id. One bulk call.

    Returns {"values": {mlbam: int wRC+}, ...disclosure counters}. Never raises;
    empty values on any failure, so the column simply goes blank.

    NEVER A STINT, AND THE CODE DOES NOT TRUST THAT BY FAITH. The predecessor
    defect on the sqlite path was reading splits[-1] off a season-scoped
    response, which silently stored ONE STINT for a traded player. Two
    protections here:

      1. Rows are grouped by MLBAM id and the group is resolved explicitly. No
         positional index is ever taken. `splits[-1]`, `splits[0]` and "last one
         wins" appear nowhere in this function, on purpose.
      2. If a group ever holds more than one row it is a stint decomposition,
         and the season total is the row carrying the numTeams > 1 marker. If
         that row is not unique the id is REFUSED, because every remaining
         choice is a positional guess.

         NOT the same test stats.py uses, and the difference matters. stats.py
         selects on the PRESENCE of numTeams, which is correct for the
         per-player endpoint where only the aggregate row carries it. The BULK
         feed sets numTeams on EVERY row (measured 2026: 647 rows at 1, 27 at
         2, 2 at 3), so a presence test here would match everything and decide
         nothing. Same defect, two endpoints, two different correct tests.

    Measured 2026-07-31 over seasons 2021-2026: 5,120 feed rows, 5,120 distinct
    player ids, ZERO groups larger than one, so branch 2 is a guard and not a
    live code path today. numTeams is nonetheless populated and correct on every
    row (2026: 647 ones, 27 twos, 2 threes), and the 29 multi-team hitters on the
    live board agree with the board's own season-total wOBA to within 0.0074 (max
    over the 29), which is what proves these rows are aggregates, not stints.

    IDENTITY. The join key is the MLBAM id and NOTHING ELSE. Measured on
    prospects.db 2026-07-31, the sqlite `sabermetrics` table has 51 mlbam ids
    carrying more than one player_key; 10 of those groups carry a wRC+ and 7 of
    the 10 DISAGREE with themselves (jackson_chourio 115.9 vs 109.9,
    jeferson_quero 120.9 vs 124.7, victor_mesa_jr 112.8 vs 113.3, chase_delauter
    124.0 vs 130.3, cody_freeman 190.3 vs 47.7, josh_smith 67.3 vs 64.1,
    sterlin_thompson 79.1 vs 53.1). The resolution rule for this column is that
    player_key never enters the join: a colliding pair CANNOT produce two numbers
    on this board, because both keys resolve to the one mlbam and read the one
    published season total. That is also why this column does not read the sqlite
    table, which additionally covers only 226 of 277 qualified hitters (the 51
    misses include Judge, Trout, Harper, Freeman, Machado and Schwarber).
    """
    season = int(season)
    meta = {"values": {}, "source": "statsapi sabermetrics (bulk, season totals)",
            "season": season, "n_rows": 0, "n_players": 0, "n_multi_team": 0,
            "n_ambiguous": 0, "ambiguous_ids": []}
    try:
        from scrapers import _fetch      # network-gated: nothing fetches at import
        fr = _fetch(_SABER_URL.format(season=season),
                    f"statsapi_saber_hitting_{season}", accept_json=True)
        if fr.status != 200 or not fr.body:
            _log.warning("sabermetrics %s: fetch failed (status=%s)", season, fr.status)
            return meta
        stats = json.loads(fr.body).get("stats") or []
        splits = (stats[0].get("splits") or []) if stats else []
    except Exception as e:   # noqa: BLE001 - best-effort join, never aborts the board
        _log.warning("sabermetrics %s: unavailable (%s)", season, e)
        return meta

    by_id: dict[int, list[dict]] = {}
    for s in splits:
        pid = (s.get("player") or {}).get("id")
        val = (s.get("stat") or {}).get("wRcPlus")
        if pid is None or val is None:
            continue
        by_id.setdefault(int(pid), []).append(s)

    values: dict[int, int] = {}
    ambiguous: list[int] = []
    n_multi = 0
    for pid, group in by_id.items():
        if len(group) == 1:
            row = group[0]
        else:
            # Stint decomposition. Take the season-total marker, never a position.
            tot = [r for r in group if (r.get("numTeams") or 1) > 1]
            if len(tot) != 1:
                ambiguous.append(pid)
                continue
            row = tot[0]
        if (row.get("numTeams") or 1) > 1:
            n_multi += 1
        try:
            values[pid] = int(round(float(row["stat"]["wRcPlus"])))
        except (TypeError, ValueError, KeyError):
            continue
    meta.update({"values": values, "n_rows": len(splits), "n_players": len(values),
                 "n_multi_team": n_multi, "n_ambiguous": len(ambiguous),
                 "ambiguous_ids": sorted(ambiguous)})
    return meta


def _join_wrc_plus(hitters: list[dict], season: int) -> dict:
    """Stamp the PUBLISHED wRC+ onto board rows by MLBAM id, and return the
    disclosure block the payload carries.

    Nothing here is computed: the value is MLB's published season figure, read
    verbatim and only rounded to the integer the industry publishes it at (a "+"
    stat, so round-to-nearest per the display convention, not the ceiling that
    FV/tool grades take).

    SAMPLE FLOOR (WRC_PLUS_MIN_PA, added 2026-07-31 after review). The original
    version stamped every row the feed covered on the reasoning that a published
    fact is not a pool-anchored index a thin sample would distort. That reasoning is
    wrong HERE, and the reason is the column it sits beside. HEM+ is EB-SHRUNK, so a
    1-PA hitter reads exactly 100.0; published wRC+ is UNSHRUNK, so the same man
    reads 481. Measured on the live board: HEM+ sd 13.9 over range [63, 166] against
    wRC+ sd 58.6 over [-100, 481], with 134 rows under 50 PA and 40 negative. Sorting
    the unqualified view by wRC+ put a 1-PA pitcher (Victor Mederos, 481) above every
    real hitter in baseball. Two indices side by side that answer the same question
    at wildly different sample discipline is a false comparison, and the bands are fit
    on the QUALIFIED pool (sd 25.27) so they mean nothing at sd 58.6 anyway.

    The floor matches WAR/PA+, the site's existing rate-index convention, which is
    already nulled below 100 PA. Below the floor the field is ABSENT rather than
    zeroed, so the column renders empty and sorts to the bottom instead of asserting
    a number nobody should read. Nothing is hidden that the reader can act on: those
    rows already carry the is-provisional row treatment and the prov chip."""
    src = load_published_wrc_plus(season)
    vals = src.get("values") or {}
    n = n_q = 0
    n_board = len(hitters)
    n_qual = sum(1 for h in hitters if h.get("qualified"))
    n_thin = 0
    n_eligible = sum(1 for h in hitters if (h.get("pa") or 0) >= WRC_PLUS_MIN_PA)
    for h in hitters:
        mid = h.get("mlbam")
        v = vals.get(int(mid)) if mid is not None else None
        if v is None:
            continue
        if (h.get("pa") or 0) < WRC_PLUS_MIN_PA:
            n_thin += 1
            continue
        h["wrc_plus"] = v
        n += 1
        if h.get("qualified"):
            n_q += 1
    return {
        "available": bool(n),
        "source": src.get("source"),
        "published": True,
        "n_feed_rows": src.get("n_rows"), "n_feed_players": src.get("n_players"),
        "n_multi_team": src.get("n_multi_team"),
        "n_ambiguous": src.get("n_ambiguous"), "ambiguous_ids": src.get("ambiguous_ids"),
        "min_pa": WRC_PLUS_MIN_PA, "n_below_min_pa": n_thin,
        # Coverage on the population the column actually targets. hit_rate is
        # stamped/board and so is depressed by the sample floor by design;
        # this is the number that detects a real FEED regression.
        "n_eligible": n_eligible,
        "hit_rate_eligible": round(n / n_eligible, 4) if n_eligible else None,
        "n_stamped": n, "n_board": n_board,
        "hit_rate": round(n / n_board, 4) if n_board else None,
        "n_stamped_qualified": n_q, "n_qualified": n_qual,
        "hit_rate_qualified": round(n_q / n_qual, 4) if n_qual else None,
        "bands": dict(WRC_PLUS_BANDS),
        "note": ("wRC+ is MLB's PUBLISHED value, read verbatim from the bulk "
                 "season-total sabermetrics feed and joined by MLBAM id; this "
                 "site derives none (HEM+ is its own offense index). A season "
                 "total, never a stint, so a traded hitter reads one line. "
                 "Shown at " + str(WRC_PLUS_MIN_PA) + "+ PA only: unlike HEM+ "
                 "it is unshrunk."),
    }


def _join_xhem_plus(hitters: list[dict], season: int) -> int:
    """Stamp xhem_plus (the HEM+ ratio scale on Savant xwOBA -- 'deserved offense')
    + luck_gap (Savant xwOBA minus Savant wOBA, in wOBA points) onto tracked
    hitters. xwOBA forward-predicts next-year wOBA better than actual wOBA
    (validated: tools/xhem_plus_lab.py), so this is a companion 'deserved-offense'
    read. MLB-only + min-BBE gated, so it stamps only the tracked subset; missing
    -> fields absent (column blank). Best-effort.

    LUCK IS READ IN wOBA POINTS, BOTH SIDES UNSHRUNK (2026-09-24). luck_gap used
    to be xHEM+ minus HEM+. HEM+ is EB-shrunk toward the pool and xHEM+ is not,
    so the difference mostly measured how far shrinkage pulled a hitter toward
    100: on the 2026-09-24 board it disagreed in sign with Savant xwOBA minus
    wOBA on 126 of 460 hitters (Ha-Seong Kim read -43 with his xwOBA .046 above
    his wOBA), and the good hitters all read unlucky. It is now Savant's own
    est_woba minus Savant's own woba off the same leaderboard row, the pitcher
    boards' convention (starter_export / bullpen_export `luck`) with the sign
    set so + still means results below the contact. `luck_gap_woba` (Savant's
    wOBA, the other leg of the difference) rides the row so luck_gap is
    checkable against the served numbers; the luck_gap_ prefix keeps it inside
    the luck_gap family the multi-year window spec already explains."""
    try:
        import mlb_player_export as mpe
        rows = mpe._savant("expected", int(season), "batter")
    except Exception:
        return 0
    # xwOBA needs a minimum sample: a 1-PA player who homered shows est_woba ~0.8,
    # which is noise, not deserved talent. Gate the join (and the pool anchor) at a
    # real Savant PA sample. xwOBA is already de-luck'd, so no further shrink.
    _XHEM_MIN_PA = 100.0
    xw = {}
    woba_by: dict[int, float] = {}
    for r in rows:
        try:
            mid = int(r["player_id"]); ew = float(r["est_woba"]); pa = float(r["pa"])
        except (TypeError, ValueError, KeyError):
            continue
        if pa >= _XHEM_MIN_PA and ew > 0:
            xw[mid] = (ew, pa)
            try:
                woba_by[mid] = float(r["woba"])
            except (TypeError, ValueError, KeyError):
                pass
    if not xw:
        return 0
    # PA-weighted pool mean xwOBA anchors the ratio so the tracked pool averages 100.
    dtot = sum(pa for _, pa in xw.values())
    pool = (sum(x * pa for x, pa in xw.values()) / dtot) if dtot else None
    if not pool:
        return 0
    n = 0
    for h in hitters:
        ent = xw.get(int(h["mlbam"])) if h.get("mlbam") is not None else None
        if not ent:
            continue
        # Same widened scale as HEM+ (hem_plus.HEM_SPREAD_GAIN), so xHEM+ and HEM+
        # sit on ONE ruler. Luck is NOT their difference (see the docstring).
        h["xhem_plus"] = int(round(100.0 + hem_plus.HEM_SPREAD_GAIN * (100.0 * ent[0] / pool - 100.0)))
        h["xwoba"] = round(ent[0], 3)
        wo = woba_by.get(int(h["mlbam"]))
        if wo is not None:
            h["luck_gap_woba"] = round(wo, 3)
            h["luck_gap"] = round(ent[0] - wo, 3)   # + = results below his contact
        n += 1
    return n


def _join_savant_custom(hitters: list[dict], season: int) -> dict:
    """Stamp the Savant custom-leaderboard DISPLAY columns (X05-01) onto the
    board rows by mlbam and return their provenance block. No score on this
    board reads them. Fail-soft: any error serves an unavailable block
    and blank columns."""
    try:
        import savant_leaderboards as _sl
        return _sl.join(hitters, int(season), "batter")
    except Exception as e:   # noqa: BLE001 - a display join must not take a board down
        return {"available": False, "reason": f"savant_leaderboards unavailable ({type(e).__name__})"}


def _join_fwdhem_plus(hitters: list[dict], hem_raw: dict, season: int) -> int:
    """Stamp fwdhem_plus ('xHEM+ Blend') onto tracked hitters: the validated T1-3
    forward blend, 0.7 * z(Savant est_woba) + 0.3 * z(unrounded HEM+ core), z-scored
    within the season over the joined pool, then mapped back onto the HEM+ ratio
    display scale (the joined pool's own HEM+ mean/spread), so it reads on the same
    ruler as HEM+/xHEM+. Forward-beats xwOBA-alone at predicting next-year wOBA
    (validated: tools/xhem_plus_lab.py X-H5, x_h5_blend block of
    data/xhem_plus_eval.json). Same Savant gating as xHEM+ (MLB-only, min 100
    Savant PA), so it stamps only the tracked subset; missing -> field absent
    (column blank). `hem_raw` is {mlbam: unrounded hem_plus_raw} from the scored
    Hitter objects (display rounding never enters the blend). Best-effort."""
    try:
        import mlb_player_export as mpe
        rows = mpe._savant("expected", int(season), "batter")
    except Exception:
        return 0
    _FWDHEM_MIN_PA = 100.0     # same sample gate as the xHEM+ join
    W_XWOBA, W_HEM = 0.7, 0.3  # T1-3 pre-registered weights
    xw = {}
    for r in rows:
        try:
            mid = int(r["player_id"]); ew = float(r["est_woba"]); pa = float(r["pa"])
        except (TypeError, ValueError, KeyError):
            continue
        if pa >= _FWDHEM_MIN_PA and ew > 0:
            xw[mid] = ew
    # joined pool: tracked hitters with BOTH a real Savant sample and a HEM core
    pool = {m: (ew, hem_raw[m]) for m, ew in xw.items() if hem_raw.get(m) is not None}
    if len(pool) < 2:
        return 0

    def _mu_sd(vals):
        k = len(vals)
        mu = sum(vals) / k
        sd = (sum((v - mu) ** 2 for v in vals) / (k - 1)) ** 0.5
        return mu, sd

    mu_x, sd_x = _mu_sd([v[0] for v in pool.values()])
    mu_h, sd_h = _mu_sd([v[1] for v in pool.values()])
    if not sd_x or not sd_h:
        return 0
    blend = {m: W_XWOBA * (ew - mu_x) / sd_x + W_HEM * (hp - mu_h) / sd_h
             for m, (ew, hp) in pool.items()}
    # A 0.7/0.3 blend of two unit-z legs has pool sd < 1 (the legs are not
    # perfectly correlated), so re-standardize the blend over the pool before
    # mapping back onto the HEM+ ratio display scale via the pool's own HEM+
    # location/spread. Both steps are monotone, so the validated forward
    # RANKING is exactly the shipped ranking; only the display width changes.
    _, sd_b = _mu_sd(list(blend.values()))
    if not sd_b:
        return 0
    n = 0
    for h in hitters:
        z = blend.get(int(h["mlbam"])) if h.get("mlbam") is not None else None
        if z is None:
            continue
        h["fwdhem_plus"] = int(round(mu_h + sd_h * (z / sd_b)))
        n += 1
    return n


def _join_pwoba(hitters: list[dict], season: int) -> int:
    """Stamp pwoba (projected NEXT-season wOBA) + pwoba_pctile onto tracked
    hitters, straight from the FA engine (fa_projection.project_player
    woba_proj) -- the validated projection engine that already prices the FA
    class board and MLB Projections. This is a RE-ANCHOR, not a new model: the
    T1-10 pHEM+ Marcel-lite gate (data/phem_marcel_lite_eval.json, registry row
    phem_marcel_lite) was WON by this engine's projected wOBA (gate rho 0.5189
    vs best incumbent 0.4939, lo95 +0.0010, pass_under_v2 true), so the ship is
    exposing what the engine already computes.

    Mirrors the vets path of proj_export._veteran_rows: corpus history for the
    trailing 3 seasons, point-in-time fits (fitted_models at target-1, the
    cached fa_fits pickle), the in-progress season handled by season_fraction
    reliability-blending (PT only; the rate Marcel exposure-weights the partial
    sample down on its own). Same MIN_PA=100 exposure floor as the vet
    universe, so a 5-PA cup of coffee never shows a league-mean projection as
    if it meant something. pwoba_pctile is the percentile within the joined
    pool (the JS color ramp). Missing anything -> fields absent (column
    blank). Best-effort: offline it rides the cached corpus/fits; any failure
    returns 0 and the board ships without the column values."""
    try:
        import fa_projection as fp
        corpus = fp.build_corpus()
        league = corpus["league"]
        target = int(season) + 1
        curves, _ = fp.fitted_models(corpus, target - 1)
    except Exception as e:   # noqa: BLE001 - best-effort join, never aborts the board
        _log.warning("pwoba join unavailable (%s)", e)
        return 0
    # In-progress current season: same reliability treatment as the live vets
    # export (proj_export). Affects playing time only; woba_proj is rate-side.
    frac = fp.season_fraction(league, int(season))
    in_prog = (int(season), frac) if frac < 1.0 else None
    _PWOBA_MIN_PA = 100.0     # proj_export MIN_PA: the vet-universe exposure floor
    by_player: dict[int, dict[int, dict]] = {}
    for r in corpus["hit"]:
        if r.get("mlbam") and r["season"] >= target - 3:
            by_player.setdefault(int(r["mlbam"]), {})[r["season"]] = r
    stamped: list[dict] = []
    for h in hitters:
        mid = h.get("mlbam")
        seasons = by_player.get(int(mid)) if mid is not None else None
        if not seasons:
            continue
        hist = [seasons[t] for t in (target - 1, target - 2, target - 3) if t in seasons]
        if not hist or max((r.get("pa") or 0) for r in hist) < _PWOBA_MIN_PA:
            continue
        # Age anchored to the row that supplied it (the proj_export convention);
        # ageless histories still project, they just skip the aging deltas.
        age_row = next((r for r in hist if r.get("age")), None)
        age = (age_row["age"] + (target - age_row["season"])) if age_row else None
        try:
            proj = fp.project_player(hist, "hit", target, curves, league, age,
                                     in_progress=in_prog)
        except Exception:   # noqa: BLE001 - one bad history never drops the board
            continue
        w = (proj or {}).get("woba_proj")
        if w is None:
            continue
        h["pwoba"] = round(float(w), 3)
        stamped.append(h)
    # Percentile within the joined pool (mid-rank, 0-100) for the color ramp.
    if len(stamped) >= 2:
        import bisect
        vals = sorted(h["pwoba"] for h in stamped)
        n = len(vals)
        for h in stamped:
            lo = bisect.bisect_left(vals, h["pwoba"])
            hi = bisect.bisect_right(vals, h["pwoba"])
            h["pwoba_pctile"] = int(round(100.0 * ((lo + hi) / 2.0) / n))
    return len(stamped)


def _join_war_pa_plus(hitters: list[dict], season: int) -> dict:
    """HITTER-anchored WAR/PA+: 100 = the average hitter's BATTING eWAR per plate
    appearance, on the 100 + 10z scale (convention 3, ten points per pool sigma,
    NOT the HEM+ ratio scale that the columns around it use).

    Batting WAR only, on the eWAR basis, whose batting side equals bWAR until the
    SDR defense drop (so this index did not move at the 2026-09 epoch). The reader
    is a whole-player value rate, not a rate skill:
    unlike HEM+, which is offensive rate alone, WAR/PA+ carries fielding,
    baserunning and the positional adjustment, which is exactly why it is noisier
    and why it sits behind a 100-PA display gate.

    TWO-WAY PLAYERS need no discount here. The WAR reader keeps the batting and
    pitching sides on separate keys, so a two-way player's BATTING WAR is divided
    by his plate appearances on this board while his PITCHING WAR is divided by
    his innings on a pitcher board. Two indexes, two denominators, both correct;
    he legitimately appears on both boards. proj_export.TWO_WAY_PIT_PTH_FACTOR
    exists for a display path where one denominator has to carry both sides, and
    it does not apply.

    Best-effort: WAR unavailable or degenerate -> nothing stamped, column blank."""
    return score_war_rate(
        hitters, season, side="bat", denom_key="pa",
        pool_min=WAR_RATE_POOL_MIN_PA, display_min=WAR_RATE_DISPLAY_MIN_PA,
        out_key="war_pa_plus", anchor="hitters with 50+ PA")


def _join_war_pa_plus_3yr(hitters: list[dict]) -> dict:
    """Frozen trailing-window WAR/PA+ on the hitter block of
    data/war_rate_plus_multiyear_eval.json. Vintage, not pipeline output: see
    bullpen_export.join_war_rate_3yr for the full disclosure contract."""
    return join_war_rate_3yr(hitters, "hit", "war_pa_plus_3yr", "hitters")


def _verdict() -> str:
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
        return (j.get("verdict") or {}).get("status") or "provisional"
    except Exception:
        return "provisional"


def _backtest() -> dict:
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    fs = j.get("forward_spearman_vs_wOBA_next") or {}
    v = j.get("verdict") or {}
    return {
        "status": v.get("status") or "provisional",
        "n_pairs": j.get("n_forward_pairs"),
        "seasons": len(j.get("seasons") or []),
        "rho_hem_plus": fs.get("hem_plus"),
        "rho_woba": fs.get("raw_woba"),
        "rho_ops": fs.get("ops"),
        "rho_avg": fs.get("avg"),
        "disclaimer": ("HEM+ predicts next-year wOBA out of sample. PA, SB and the slash "
                       "line are context: HEM+ is rate skill, not volume or speed."),
    }


@functools.lru_cache(maxsize=4)
def load_bat_side(season: int) -> Optional[dict]:
    """{mlbam: 'L'|'R'|'S'} for every MLB player, one bulk StatsAPI call. Feeds the
    handedness-aware lineup construction (hem_plus.build_batting_order).

    Returns None - never {} - when the lens is unavailable, which is the
    bullpen_export._active_mlbam_ids posture ("never break the board", with an
    explicit sentinel the caller can act on). This used to return {} on failure
    and the caller read that as "nothing to stamp" and shipped anyway: measured
    2026-08-05 on the served board, `bats` was null on 618 of 618 hitters and all
    30 teams published BYTE-IDENTICAL vs-LHP and vs-RHP orders while the page's
    own note told the reader the two lists were staggered by handedness.

    An empty map is not "no platoon data", it is "no platoon lens", and the two
    must not be indistinguishable downstream. A parse that yields zero usable
    codes is the same outage as a failed fetch, so it returns None too, and both
    log the counts."""
    try:
        import bullpen_export as be
        data = be._get_json("sports/1/players", {"season": int(season)})
    except Exception as e:   # noqa: BLE001 - best-effort, network/parse anything
        _log.warning("batSide fetch failed for %s (%s); the platoon lineup lens "
                     "is UNAVAILABLE this run", season, e)
        return None
    people = data.get("people") or []
    out = {}
    for p in people:
        bs = (p.get("batSide") or {}).get("code")
        if p.get("id") and bs:
            out[int(p["id"])] = bs
    if not out:
        _log.warning("batSide feed for %s returned %d people and 0 usable batSide "
                     "codes; treating the platoon lineup lens as UNAVAILABLE",
                     season, len(people))
        return None
    _log.info("batSide %s: %d codes resolved from %d people", season, len(out), len(people))
    return out


def _platoon_split_availability(teams: list[dict], platoon_counts: Optional[dict]) -> dict:
    """Did the per-hand HEM+ actually reach the served lineup slots this run?

    The falsifiable companion to `bat_side` (audit F08-02). `bat_side.available`
    only says the handedness LENS joined; it stayed true for months while every
    derived split was identically equal, because the lens re-lensed the ORDER and
    the slots still carried the season number. This block reports the thing that
    was actually missing: how many slots carry a hand-specific value, and whether
    the two hand means can differ at all.

    `n_teams_split_equal` is the tripwire. It counts clubs whose vs-LHP and
    vs-RHP PA-weighted means are still bit-identical WITH the lens reported
    available. On the broken build that was 30 of 30. It WARNS and never raises:
    the nightly vintage write is what the 600-game clock and the schema-4 accrual
    both run on, and an unconditional raise here would stop that stream dead."""
    n_slots = n_split = 0
    n_teams = n_equal = 0
    try:
        import leaderboard_vintages as _lv
    except Exception:   # noqa: BLE001 - the reduction is optional for this count
        _lv = None
    for t in teams:
        orders = t.get("orders")
        if not isinstance(orders, dict) or not orders:
            continue
        n_teams += 1
        for side in ("vl", "vr"):
            for s in (orders.get(side) or []):
                n_slots += 1
                if s.get("hem_plus_split") is not None:
                    n_split += 1
        if _lv is not None:
            vl, vr = _lv.off_splits_from_hitter_team(t)
            if vl is not None and vr is not None and vl == vr:
                n_equal += 1
    available = bool(platoon_counts) and n_split > 0
    meta = {
        "available": available,
        "n_slots": n_slots,
        "n_slots_split": n_split,
        "n_teams_with_orders": n_teams,
        "n_teams_split_equal": n_equal,
        "n_rows_vs_lhp": len((platoon_counts or {}).get("L") or {}),
        "n_rows_vs_rhp": len((platoon_counts or {}).get("R") or {}),
        "source": ("StatsAPI statSplits sitCodes vl/vr, playerPool=All, two bulk "
                   "calls; per-hand HEM+ is the season shrunk wOBA times the "
                   "hitter's platoon ratio regressed toward the league ratio for "
                   "his bat side, on the same season pool anchor"),
        # The per-hand construction (hem_plus.SPLIT_ESTIMATOR). The nightly
        # vintage copies it into the 5f hitter-column basis, where the 5e / 5f
        # dark clocks read it (owner-signed restart, 2026-09-25).
        "estimator": hem_plus.SPLIT_ESTIMATOR,
        "k": dict(hem_plus.K_PLATOON),
    }
    if available and n_teams and n_equal == n_teams:
        meta["warning"] = (
            f"per-hand HEM+ reported available but all {n_equal} clubs still serve "
            "an identical vs-LHP / vs-RHP mean; the split carries no information "
            "this run (audit F08-02)")
        _log.warning(meta["warning"])
    elif not available:
        meta["reason"] = ("no platoon split feed this run; every slot carries the "
                          "season HEM+ on both hands, so any derived split is "
                          "identically equal")
    return meta


@functools.lru_cache(maxsize=4)
def load_platoon_splits(season: int) -> Optional[dict]:
    """{'L': {mlbam: counts}, 'R': {mlbam: counts}} - every hitter's counting line
    against each pitcher hand, in TWO bulk StatsAPI calls. Feeds the per-hand HEM+
    (hem_plus.build_split_hem) and therefore the off_vs_lhp / off_vs_rhp capture.

    WHY (audit F08-02, 2026-09-10). Before this, the two hand-labelled orders both
    carried each hitter's SEASON hem_plus, so the PA-weighted split was a mean over
    a permutation of the same nine bats and `off_vs_lhp` equalled `off_vs_rhp`
    bit-for-bit on all 30 clubs across all 480 captured rows. The lens was up and
    the orders genuinely differed; only the VALUES could not. The pre-registered
    handedness gate would have measured its own twin.

    `playerPool=All` is load-bearing: the default pool returns QUALIFIED hitters
    only (139 of them on 2026-09-10) and the everyday nine reaches well past that.
    With it, one call per hand covers 642 hitters vs LHP and 649 vs RHP, and all
    270 constructed lineup bats resolve on BOTH hands (median 131 vs-LHP PA).

    Returns None - never {} - on any outage, which is the load_bat_side posture:
    an empty map is not "no platoon data", it is "no platoon lens", and the two
    must not be indistinguishable downstream. A hand that comes back empty fails
    the whole map, because a one-sided split is worse than none: it would make one
    hand real and the other a fallback, and nothing downstream could tell."""
    try:
        import bullpen_export as be
    except Exception as e:   # noqa: BLE001
        _log.warning("platoon splits unavailable for %s (%s)", season, e)
        return None
    out: dict = {}
    for hand, sit in (("L", "vl"), ("R", "vr")):
        try:
            data = be._get_json("stats", {
                "stats": "statSplits", "sitCodes": sit, "group": "hitting",
                "season": int(season), "gameType": "R", "sportId": 1,
                "playerPool": "All", "limit": 2000})
        except Exception as e:   # noqa: BLE001 - network/parse anything
            _log.warning("platoon split fetch failed for %s %s (%s); the per-hand "
                         "HEM+ lens is UNAVAILABLE this run", season, sit, e)
            return None
        rows = {}
        for sp in ((data.get("stats") or [{}])[0].get("splits") or []):
            pid = (sp.get("player") or {}).get("id")
            st = sp.get("stat")
            if pid and isinstance(st, dict):
                rows[int(pid)] = st
        if not rows:
            _log.warning("platoon split feed for %s %s returned 0 usable rows; "
                         "treating the per-hand HEM+ lens as UNAVAILABLE", season, sit)
            return None
        out[hand] = rows
    _log.info("platoon splits %s: vs-LHP %d rows, vs-RHP %d rows",
              season, len(out.get("L") or {}), len(out.get("R") or {}))
    return out


# WHICH KEY EACH CONSUMER READS. Published inside the bat_side block so the
# contract lives in the artifact and not only in this file's head.
_ORDER_KEY_CONTRACT = {
    "split": ("teams[].orders.vr / teams[].orders.vl - the hand-labelled orders. "
              "Trust the LABELS only when bat_side.available is true."),
    "neutral": ("teams[].order_no_platoon - present ONLY when the split was not "
                "applied. The one constructed nine, under a name that claims "
                "nothing about handedness."),
    "flag": ("teams[].platoon_applied - false means render ONE lineup and say the "
             "split is unavailable; do not offer a vs-LHP / vs-RHP toggle."),
}


def _orders_identical(o: dict) -> bool:
    """Did vs-RHP and vs-LHP come out as the same nine, in the same slots?"""
    vr, vl = (o.get("vr") or []), (o.get("vl") or [])
    if not vr or not vl or len(vr) != len(vl):
        return False
    return all((a or {}).get("key") == (b or {}).get("key") for a, b in zip(vr, vl))


def _platoon_availability(teams: list[dict], bat_side: Optional[dict],
                          n_stamped: int, n_hitters: int, log=print) -> dict:
    """Disclose whether the vs-LHP / vs-RHP split was actually applied, and give
    every consumer something real to render either way. Mutates `teams` (stamps
    `platoon_applied`, and adds `order_no_platoon` when the lens is missing).
    Returns the payload's bat_side block.

    THE FABRICATED LENS (measured 2026-08-05). hem_plus.team_offense ALWAYS emits
    orders["vr"] and orders["vl"]; the only thing that can make them differ is
    Hitter.bats, which this module stamps from load_bat_side. With the bat side
    missing, hem_plus._platoon_adj returns 0.0 for every hitter and the handedness
    stagger has no hands to stagger, so the two orders come out byte-identical -
    and the served file did exactly that for all 30 teams while every one of 618
    hitters carried a null `bats`. Two identical lists under two different hand
    labels do not read as "no data"; they read as "the split was applied and it
    did not change anything", which is a claim this board never earned.

    NOTHING IS REMOVED, BECAUSE REMOVING IT TRADED ONE SILENT BLANK FOR ANOTHER.
    The first cut of this guard popped `orders` outright. Measured on the same
    2026-08-05 board that motivated it, `bats` is null on 618 of 618 hitters, so
    that strip fires on EVERY run in today's data state, and both live readers of
    the key lose their board: betting_export.props_fair_lines does
    `(t.get("orders") or {}).get("vr")` and would have priced ZERO hitter props
    on the betting page, and assets/mlbstats.js would have dropped all 30
    constructed nines back to the raw HEM+ depth ladder. An empty chart is not a
    more honest chart than a mislabelled one, it is a second outage. A lineup we
    computed exists; only the HANDEDNESS CLAIM does not.

    So the orders STAY and the claim is withdrawn instead:

      * `platoon_applied` is stamped false on every team, which is the flag a
        renderer branches on to show one lineup plus "no platoon split available"
        rather than a two-tab toggle over identical lists;
      * `order_no_platoon` carries that single nine under a name that asserts
        nothing, for a consumer that would rather read an honest key than a
        hand-labelled one it has to distrust;
      * per-slot `platoon_adv` is dropped from both orders, because a False "no
        platoon advantage" marker is itself a handedness claim;
      * `orders.vr` / `orders.vl` are left in place, byte-identical, so no
        existing reader dark-starts. bat_side.available=false is what tells a
        reader the two labels are not earned this run.

    Measuring `n_teams_identical_orders` in BOTH branches keeps the assertion
    falsifiable: 30 of 30 identical with the lens reported available would mean
    the stamp joined and the split still did nothing."""
    n_teams = len(teams)
    if bat_side is None:
        reason = "batSide feed unavailable (fetch failed or returned no usable codes)"
    elif not n_stamped:
        reason = (f"batSide feed returned {len(bat_side)} codes but none matched "
                  f"the {n_hitters} hitters on this board")
    else:
        reason = None
    n_with = n_identical = 0
    for t in teams:
        o = t.get("orders")
        t["platoon_applied"] = reason is None
        if not isinstance(o, dict) or not o:
            continue
        n_with += 1
        if _orders_identical(o):
            n_identical += 1
    if reason is None:
        return {
            "available": True, "n_stamped": n_stamped, "n_hitters": n_hitters,
            "n_feed_codes": len(bat_side or {}),
            "n_teams_with_orders": n_with,
            "n_teams_identical_orders": n_identical,
            "keys": _ORDER_KEY_CONTRACT,
            "note": ("Bat side (L/R/S) drives the vs-LHP / vs-RHP order: the "
                     "platoon term and the handedness stagger both read it."),
        }
    n_neutral = 0
    for t in teams:
        o = t.get("orders")
        if not isinstance(o, dict) or not o:
            continue
        for k in ("vr", "vl"):
            for slot in (o.get(k) or []):
                if isinstance(slot, dict):
                    slot.pop("platoon_adv", None)
        src = o.get("vr") or o.get("vl")
        if src:
            # A copy, not an alias: the neutral key must survive any later
            # re-keying of `orders` without carrying the edit across.
            t["order_no_platoon"] = [dict(s) if isinstance(s, dict) else s
                                     for s in src]
            n_neutral += 1
    if callable(log):
        log(f"  hitters: bat side UNAVAILABLE ({reason}); the vs-LHP / vs-RHP "
            f"orders on {n_with} of {n_teams} teams are IDENTICAL "
            f"({n_identical} confirmed) and are published with "
            f"platoon_applied=false plus order_no_platoon "
            f"({n_neutral} teams) rather than as an earned split")
    _ingest_red("hitter_bat_side",
                (f"bat side unavailable ({reason}); the vs-LHP / vs-RHP lineup "
                 f"orders on {n_with} of {n_teams} team charts are byte-identical "
                 f"and carry platoon_applied=false. The lineups still serve; only "
                 f"the handedness split is unavailable."))
    return {
        "available": False, "reason": reason, "n_stamped": n_stamped,
        "n_hitters": n_hitters, "n_feed_codes": len(bat_side or {}),
        "n_teams_with_orders": n_with, "n_teams_identical_orders": n_identical,
        "n_order_no_platoon": n_neutral, "n_teams": n_teams,
        "keys": _ORDER_KEY_CONTRACT,
        "note": ("The vs-LHP / vs-RHP labels are NOT earned this run: with no bat "
                 "side the platoon term is 0.0 for every hitter, so both orders are "
                 "the same nine. The lineups still serve: read "
                 "teams[].order_no_platoon (or either half of teams[].orders) and "
                 "show one lineup with the split marked unavailable."),
    }


def _roster_filter_meta(teams: list, active_ids) -> dict:
    """What the active-roster filter did, published so it can be audited.

    Same reasoning as the team-basis block beside it: a filter a reader cannot
    see is indistinguishable from no filter, and this one changes which nine
    names appear on a chart. n_dropped counts CONSTRUCTED slots removed, not
    leaderboard rows: the leaderboard is the season as played and keeps everyone.
    """
    return {
        "applied": active_ids is not None,
        "n_active_roster_ids": (len(active_ids) if active_ids is not None else None),
        "n_dropped_from_constructions": sum(int(t.get("n_off_roster_dropped") or 0)
                                            for t in teams),
        "basis": "StatsAPI rosterType=active (26-man), so an optioned or injured "
                 "player drops",
        "scope": "the constructed orders, lineup and bench ONLY. Offense+ and every "
                 "other aggregate stay on the full season pool: HEM+ over PA already "
                 "taken stands whether or not the player is hurt now, and Offense+ "
                 "feeds betting_model and the leaderboard vintages behind the "
                 "600-game clock.",
        "on_failure": "a failed roster fetch filters NOTHING rather than blanking the "
                      "charts; a player whose mlbam cannot be read is kept",
    }


# --------------------------------------------------------------------------- #
# Lineup cards: positions for the bench and the nine, and the status of the
# regulars the active-roster filter dropped. Display only; see hem_plus
# team_offense for the fence around `orders`.
# --------------------------------------------------------------------------- #
CACHE_DIR = Path(__file__).parent / ".cache"
#: Freshness window on the cached 40-man rosters, the one leaderboard_vintages
#: uses for its IL read (IL_CACHE_MAX_AGE_HOURS).
ROSTER_STATUS_MAX_AGE_HOURS = 48.0
#: StatsAPI 40-man status code -> card label. D<n> codes read IL-<n>. A code
#: not listed shows MLB's own description; code A on a player the live active
#: walk dropped is a skew between the two feeds and gets no reason.
ROSTER_STATUS_LABELS = {"RM": "Minors", "BRV": "Bereavement", "A": "Not active"}


def load_positions(season: int) -> tuple[Optional[dict], dict]:
    """({mlbam: {pos: innings}}, meta) from defense_export.load_season_innings,
    the StatsAPI season-fielding feed the Defense board already reads through
    the same 24-hour scraper cache. No second fetcher.

    None, never {}, when the lens is down (the load_bat_side posture): an empty
    map would read as "nobody has a position" and blank every marker silently."""
    meta = {"available": False, "source": "statsapi season fielding (bulk), "
            "via defense_export.load_season_innings",
            "min_innings": hem_plus.PLATOON_OPTION_MIN_POS_INN}
    try:
        import defense_export
        doc = defense_export.load_season_innings(int(season))
    except Exception as e:   # noqa: BLE001 - display lens, never aborts the board
        meta["reason"] = f"fielding feed unavailable ({type(e).__name__})"
        return None, meta
    players = (doc or {}).get("players") or {}
    out = {}
    for pid, rec in players.items():
        inn = (rec or {}).get("inn")
        if isinstance(inn, dict):
            try:
                out[int(pid)] = dict(inn)
            except (TypeError, ValueError):
                continue
    meta["fetched_at"] = (doc or {}).get("fetched_at")
    if not out:
        meta["reason"] = "fielding feed returned no fielders this run"
        return None, meta
    meta.update({"available": True, "n_fielders": len(out)})
    return out, meta


def _status_label(code: Optional[str], desc: Optional[str]) -> str:
    c = str(code or "").upper()
    if len(c) > 1 and c[0] == "D" and c[1:].isdigit():
        return "IL-" + c[1:]
    return ROSTER_STATUS_LABELS.get(c) or (desc or c or "Not active")


def _roster_40man(season: int, team_id, now: float,
                  cache_dir: Optional[Path] = None) -> Optional[dict]:
    """{mlbam: (code, description)} off the cached 40-man roster for one club,
    or None when the cache is absent, unreadable or older than the window.
    Reads the file proj_export._il_out60 refreshes nightly; never fetches."""
    p = Path(cache_dir or CACHE_DIR) / f"statsapi_roster_40man_{team_id}_{season}.json"
    try:
        if (now - p.stat().st_mtime) / 3600.0 > ROSTER_STATUS_MAX_AGE_HOURS:
            return None
        roster = json.loads(p.read_text(encoding="utf-8")).get("roster") or []
    except (OSError, ValueError, AttributeError):
        return None
    out = {}
    for r in roster:
        mid = ((r or {}).get("person") or {}).get("id")
        st = (r or {}).get("status") or {}
        if mid:
            out[int(mid)] = (st.get("code"), st.get("description"))
    return out


def stamp_regulars_out(teams: list[dict], season: int, *,
                       team_ids: Optional[dict] = None,
                       cache_dir: Optional[Path] = None,
                       now: Optional[float] = None) -> dict:
    """Stamp status_code / status_label on every teams[].regulars_out row and
    return the roster_status meta block. Membership was already decided by the
    live active walk; this only names the reason, and never guesses one:

      * a fresh 40-man cache with the player on it -> his status (IL-10, Minors);
      * a fresh cache without him -> "Off 40-man";
      * no fresh cache for his club -> "Not active", no code.

    `team_ids` is {team abbreviation: StatsAPI team id}; default inverts _tmap()."""
    import time
    now = time.time() if now is None else now
    if team_ids is None:
        team_ids = {abbr: tid for tid, abbr in _tmap().items() if abbr}
    rosters: dict = {}
    n_lab = n_unlab = 0
    for t in teams:
        rows = t.get("regulars_out") or []
        if not rows:
            continue
        abbr = t.get("team")
        if abbr not in rosters:
            tid = team_ids.get(abbr)
            rosters[abbr] = (_roster_40man(season, tid, now, cache_dir)
                             if tid is not None else None)
        roster = rosters[abbr]
        for r in rows:
            mid = r.get("mlbam")
            if roster is None or mid is None:
                r["status_code"], r["status_label"] = None, "Not active"
                n_unlab += 1
            elif int(mid) not in roster:
                r["status_code"], r["status_label"] = None, "Off 40-man"
                n_lab += 1
            else:
                code, desc = roster[int(mid)]
                r["status_code"], r["status_label"] = code, _status_label(code, desc)
                if str(code or "").upper() == "A":
                    n_unlab += 1
                else:
                    n_lab += 1
    return {"available": any(v is not None for v in rosters.values()),
            "source": "cached StatsAPI 40-man rosters (statsapi_roster_40man_*), no fetch",
            "max_age_hours": ROSTER_STATUS_MAX_AGE_HOURS,
            "n_labelled": n_lab, "n_unlabelled": n_unlab}


def _margin_basis() -> dict:
    """The PLT margin's derivation summary, from hem_plus's frozen record."""
    d = hem_plus.PLATOON_OPTION_MARGIN_DERIVATION
    return {"estimator": d["estimator"], "season": d["season"],
            "n_hitters_both_hands": d["n_hitters_both_hands"],
            "spread_low": d["spread_low"], "spread_high": d["spread_high"],
            "round_to": d["round_to"],
            "rule": ("population SD of (vs-LHP minus vs-RHP HEM+) within a bat side "
                     "and vs-LHP PA band, cells of 8+ hitters; the low end rounded up "
                     "to a multiple of 5")}


def _lineup_cards_meta(teams: list[dict], pos_meta: dict, status_meta: dict,
                       split_available: bool) -> dict:
    """The lineup-card disclosure block: what resolved, and the three marker
    constants echoed so the page never types them."""
    n_nine = n_nine_res = n_bench = n_bench_res = 0
    n_opts = {"vl": 0, "vr": 0}
    n_withheld = n_out = 0
    for t in teams:
        for m in (t.get("slot_meta") or {}).values():
            n_nine += 1
            n_nine_res += bool(m.get("pos"))
        for b in t.get("bench") or []:
            n_bench += 1
            n_bench_res += bool(b.get("pos"))
        po = t.get("platoon_options") or {}
        for side in ("vl", "vr"):
            n_opts[side] += len(po.get(side) or [])
            n_withheld += int((po.get("n_withheld") or {}).get(side) or 0)
        n_out += len(t.get("regulars_out") or [])
    positions = dict(pos_meta)
    positions.update({"n_nine": n_nine, "n_nine_resolved": n_nine_res,
                      "n_bench": n_bench, "n_bench_resolved": n_bench_res})
    out = {
        "positions": positions,
        "roster_status": status_meta,
        "constants": {"min_split_pa": hem_plus.PLATOON_OPTION_MIN_SPLIT_PA,
                      "margin": hem_plus.PLATOON_OPTION_MARGIN,
                      "min_pos_innings": hem_plus.PLATOON_OPTION_MIN_POS_INN},
        # Where the margin came from (tools/plt_margin_lab.py): the low end of
        # the within-side, within-band spread of a hitter's two hand numbers,
        # rounded up to a multiple of 5. Frozen in hem_plus, echoed here so the
        # glossary's figures trace to the payload.
        "margin_basis": _margin_basis(),
        "n_platoon_options": n_opts,
        "n_withheld_by_floor": n_withheld,
        "n_regulars_out": n_out,
        "display_only": ("bench per-hand fields, slot_meta, platoon_options and "
                         "regulars_out are display siblings of teams[].orders; "
                         "no betting or vintage reader may use them"),
    }
    if not pos_meta.get("available"):
        out["reason"] = ("no platoon options this run: " + str(pos_meta.get("reason")
                         or "fielding positions unavailable"))
    elif not split_available:
        out["reason"] = "no platoon options this run: per-hand HEM+ unavailable"
    return out


def export(season: Optional[int] = None, *, out_path: Optional[Path] = None,
           write: bool = True, log=print, today: Optional[str] = None) -> int:
    """Build data/hitter_leaderboards.json and return the hitter count."""
    season = int(season or date.today().year)
    out_path = out_path or OUT_PATH
    today = today or date.today().isoformat()

    log(f"  hitters: loading {season} StatsAPI season hitting...")
    rows = load_season_hitting(season)
    if not rows:
        log(f"  hitters: no hitting data for {season} (source blocked or empty); skipping")
        return 0
    hitters = build_hitters(rows)
    # Stamp bat side (L/R/S) before scoring so team_offense can construct the
    # handedness-staggered vs-LHP / vs-RHP orders. None => the lens is
    # unavailable, which _platoon_availability turns into a served-but-unlabelled
    # lineup (platoon_applied=false + order_no_platoon) rather than either two
    # identical lineups or an empty chart (see load_bat_side).
    bat_side = load_bat_side(season)
    n_bs = 0
    if bat_side:
        for h in hitters:
            bs = bat_side.get(int(h.mlbam)) if h.mlbam is not None else None
            if bs:
                h.bats = bs
                n_bs += 1
        log(f"  hitters: bat side stamped for {n_bs} of {len(hitters)} hitters")
    # WHO CAN ACTUALLY PLAY TONIGHT. Without this the constructed nine is built
    # from everyone with a plate appearance this season, so Nick Kurtz batted
    # second for the Athletics on 434 PA while out for the year, and 37 of 270
    # slots league-wide were held by players off an active roster. Shared with
    # the bullpen depth ladders, which have filtered all along; it is the hitter
    # and starter charts that never did. None (a failed feed) filters nothing.
    active_ids = _active_mlbam_ids(int(season))
    # PER-HAND HEM+ (audit F08-02). Without this the two hand-labelled orders carry
    # the same season number for the same nine bats, so the derived off_vs_lhp /
    # off_vs_rhp split is permutation-invariant and identically equal. None leaves
    # every slot on the season number, exactly as before.
    platoon_counts = load_platoon_splits(int(season))
    # Positions for the lineup cards (bench and nine) and the platoon-option
    # rule. Display only: `orders` and Offense+ are built without them.
    positions, pos_meta = load_positions(int(season))
    scored = hem_plus.score_pool(hitters, active_ids, platoon_counts, positions)
    ps_meta = _platoon_split_availability(scored.get("teams") or [], platoon_counts)
    if platoon_counts:
        # The league platoon ratio each bat side was regressed toward this run.
        mu = hem_plus.league_platoon_ratios(
            platoon_counts, {int(h.mlbam): h.bats for h in hitters
                             if h.mlbam is not None and h.bats})
        ps_meta["league_ratio"] = {s: round(v, 4) for s, v in mu.items()}
    log(f"  hitters: per-hand HEM+ {'available' if ps_meta['available'] else 'UNAVAILABLE'}"
        f" ({ps_meta.get('n_slots_split', 0)} of {ps_meta.get('n_slots', 0)} lineup slots)")
    h3_meta = _join_hem_plus_3yr(scored["hitters"], season)
    if h3_meta.get("n_stamped"):
        log(f"  hitters: 3-year HEM+ joined for {h3_meta['n_stamped']} hitters "
            f"(Last 3 window built {h3_meta.get('generated_at')})")
    wrc_meta = _join_wrc_plus(scored["hitters"], season)
    if wrc_meta.get("available"):
        log(f"  hitters: published wRC+ joined for {wrc_meta['n_stamped']}/"
            f"{wrc_meta['n_board']} hitters "
            f"({wrc_meta['n_stamped_qualified']}/{wrc_meta['n_qualified']} qualified)")
    else:
        log("  hitters: published wRC+ unavailable; column blank")
    n_xh = _join_xhem_plus(scored["hitters"], season)
    if n_xh:
        log(f"  hitters: xHEM+ (Savant deserved offense) joined for {n_xh} hitters")
    # UNROUNDED HEM+ core off the scored Hitter objects (score_pool mutates in
    # place), so the blend never sees display rounding.
    _hem_raw = {int(h.mlbam): h.hem_plus_raw for h in hitters
                if h.mlbam is not None and h.hem_plus_raw is not None}
    n_fh = _join_fwdhem_plus(scored["hitters"], _hem_raw, season)
    if n_fh:
        log(f"  hitters: fwdHEM+ (xHEM+ Blend forward column) joined for {n_fh} hitters")
    n_pw = _join_pwoba(scored["hitters"], season)
    sv_meta = _join_savant_custom(scored["hitters"], season)
    if sv_meta.get("available"):
        log(f"  hitters: Savant discipline columns joined for {sv_meta['n_joined']}/"
            f"{sv_meta['n_board']} hitters ({sv_meta['n_qualified_joined']}/"
            f"{sv_meta['n_qualified']} qualified)")
    if n_pw:
        log(f"  hitters: pWOBA (FA-engine projected next-season wOBA) joined for {n_pw} hitters")
    wr_meta = _join_war_pa_plus(scored["hitters"], season)
    if wr_meta.get("available"):
        log(f"  hitters: WAR/PA+ joined for {wr_meta['n_stamped']} hitters "
            f"(pool {wr_meta['pool_n']})")
    elif wr_meta.get("refused"):
        log(f"  hitters: WAR/PA+ refused ({wr_meta['refused']})")
    wr3_meta = _join_war_pa_plus_3yr(scored["hitters"])
    if wr3_meta.get("n_stamped"):
        log(f"  hitters: 3-year WAR/PA+ joined for {wr3_meta['n_stamped']} hitters "
            f"(frozen lab vintage {wr3_meta.get('generated_at')})")

    # ZERO-TEAM ROLLUP GUARD. The `if not rows` check above protects the hitter
    # rows and protected nothing else: a blanked team code leaves every row intact
    # and empties scored["teams"], which is exactly how 0 team offenses published
    # over 30 and Offense+ read a flat 100 everywhere. See guard_nonempty_block.
    teams, rollup_meta = guard_nonempty_block(
        scored["teams"], out_path, key="teams", source="hitter_leaderboards",
        label="hitters", log=log)
    # TEAM eWAR (E5). Beside Offense+: the BATTING side (batting, baserunning,
    # fielding and position: the whole position-player value) of the hitters
    # this club holds, summed unrounded over every row of the board that names
    # it. Runs on the SERVED teams; an uncovered club carries no value.
    rollup_meta["team_war"] = stamp_team_war(
        teams, scored["hitters"], season, side="bat")
    if rollup_meta["team_war"].get("n_teams_stamped"):
        log(f"  hitters: team eWAR stamped on "
            f"{rollup_meta['team_war']['n_teams_stamped']} lineups "
            f"({rollup_meta['team_war']['n_rows_summed']} rows summed)")
    # Orders ride ON the team rollups, so this runs on the SERVED teams (a
    # kept-stale rollup carries orders built from the same absent bat side).
    bs_meta = _platoon_availability(teams, bat_side, n_bs, len(hitters), log=log)
    status_meta = stamp_regulars_out(teams, season)
    lc_meta = _lineup_cards_meta(teams, pos_meta, status_meta, ps_meta["available"])
    log(f"  hitters: lineup cards: positions "
        f"{'available' if pos_meta.get('available') else 'UNAVAILABLE'}; "
        f"platoon options vs LHP {lc_meta['n_platoon_options']['vl']}, vs RHP "
        f"{lc_meta['n_platoon_options']['vr']} ({lc_meta['n_withheld_by_floor']} "
        f"withheld by the split-PA floor); {lc_meta['n_regulars_out']} regulars out")

    # P/PA AND PAR (owner asks 17 and 20), dark while SERVE_PITCH_RATES is False:
    # with the flag off no key below is written and the board is byte-identical.
    pr_block = None
    if pitch_rates_boards.serving():
        pr_ctx = pitch_rates_boards.season_context(season)
        np_by_id, pos_by_id = _np_pos_by_id(hitters)
        pr_n = pitch_rates_boards.stamp_hitter_rows(scored["hitters"], np_by_id, pr_ctx)
        pr_t = pitch_rates_boards.stamp_hitter_teams(teams, scored["hitters"], np_by_id,
                                                     pos_by_id, pr_ctx)
        pr_block = pitch_rates_boards.payload_block(pr_ctx, "hit", today, pr_n, pr_t)
        log(f"  hitters: P/PA stamped on {pr_n['stamped']} of {pr_n['rows']} hitters, "
            f"{pr_t} lineups")

    payload = {
        "generated_at": today, "season": season, "as_of": today,
        "verdict": _verdict(), "backtest": _backtest(),
        # Source and build date of the 3-year HEM+ column: the Last 3 window
        # (see _join_hem_plus_3yr).
        "multiyear": h3_meta,
        # Provenance + coverage of the PUBLISHED wRC+ column, and the color
        # bands the frontend mirrors (see WRC_PLUS_BANDS).
        "wrc_plus": wrc_meta,
        # WAR/PA+ scale block (anchor pool + measured pool parameters) and the
        # vintage of its FROZEN 3-year companion.
        "war_rate": wr_meta,
        # WHICH BUILD the served eWAR numerator comes from, and whether it has
        # fallen behind the frame under it (audit F10-02 / F11-01). data/ewar.json
        # re-prices its live season nightly; a missed or refused night leaves a
        # current-season WAR behind the innings beside it, and the side-map
        # receipt (war_source.side_war_by_season) makes `stale` say so.
        "ewar_vintage": _war_source_vintage(as_of=today),
        "multiyear_war_rate": wr3_meta,
        # Provenance and join coverage of the Savant discipline and batted-ball
        # display columns (see _join_savant_custom).
        "savant_custom": sv_meta,
        # Whether the vs-LHP / vs-RHP lineup split was actually applied this run
        # (see _platoon_availability): available=false means the two hand labels
        # are NOT earned (the orders are identical), not that the lineups are
        # missing. `keys` names the key each consumer should read.
        "bat_side": bs_meta,
        # Whether the per-hand HEM+ (real platoon lines) reached the lineup slots
        # this run, and how many slots it covered. available=false means every
        # slot carries the SEASON number on both hands, which makes any derived
        # vs-LHP / vs-RHP split identically equal (audit F08-02).
        "platoon_splits": ps_meta,
        # Lineup-card disclosure: positions and roster-status coverage, the
        # platoon-option constants and counts (see _lineup_cards_meta).
        "lineup_cards": lc_meta,
        # Which club a row's `team` names, how many rows were repointed, and how
        # many serve a blank team (see bullpen_export.team_basis_meta), plus the
        # zero-rollup guard's verdict for this run.
        "team_basis": team_basis_meta(rows, label=f"hitting {season}"),
        "roster_filter": _roster_filter_meta(scored.get("teams") or [], active_ids),
        "team_rollup": rollup_meta,
        "pool": scored["pool"], "hitters": scored["hitters"], "teams": teams,
    }
    if pr_block is not None:
        # Anchors, counts, season and basis of the P/PA columns (flag on only).
        payload[pitch_rates_boards.PAYLOAD_KEY] = pr_block
    n = len(scored["hitters"])
    log(f"  hitters: {n} hitters ({scored['pool'].get('n_qualified', 0)} qualified), "
        f"{len(teams)} team offenses")
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        log(f"  hitters: wrote {out_path.name}")
    return n


# `woba_raw` is the season wOBA AS RECORDED and `woba` the pool-shrunk one HEM+
# is scaled from (E8). Both ship: the live board serves the pair under "wOBA"
# and "Shrunk wOBA", and a history row that carried only the shrunk value under
# the unqualified header "wOBA" was the label defect the overhaul audit found.
_HISTORY_FIELDS = ("mlbam", "name", "team", "hem_plus", "tier", "pa", "ab", "hr", "bb",
                   "sb", "woba_raw", "woba", "avg", "obp", "slg", "ops", "iso",
                   "bb_pct", "k_pct", "babip", "qualified")


def export_history(seasons=None, *, out_path: Optional[Path] = None,
                   write: bool = True, log=print) -> dict:
    """Build data/hitter_history.json - per-season qualified-hitter boards for the
    /mlbstats/ yearly history tabs. One cached StatsAPI call per season.

    Each row also carries `war`, that season's POSITION-PLAYER eWAR, joined per
    (player, season) (E6), and the recorded `woba_raw` beside the shrunk `woba`
    (E8)."""
    seasons = list(seasons or HISTORY_SEASONS)
    out_path = out_path or HISTORY_PATH
    hist = {}
    basis_rows: list[dict] = []
    ewar_join: dict[str, dict] = {}
    pr_seasons: dict[str, dict] = {}
    for y in seasons:
        log(f"  hitter-history: {y}...")
        rows = load_season_hitting(y)
        if not rows:
            log(f"  hitter-history: no data for {y}; skipping")
            continue
        season_hitters = build_hitters(rows)
        scored = hem_plus.score_pool(season_hitters)
        qual = [s for s in scored["hitters"] if s.get("qualified")]
        basis_rows.extend(basis_rows_for(qual, rows))
        board = [{k: s.get(k) for k in _HISTORY_FIELDS} for s in qual]
        # eWAR per (player, season), E6: the BATTING side, on the served row, so
        # an uncovered hitter carries no key rather than a null.
        ewar_join[str(y)] = stamp_history_war(board, y, side="bat",
                                              label="hitter-history", log=log)
        # P/PA and PAR, a season fact against that season's own anchor (flag on only).
        if pitch_rates_boards.serving():
            pr_ctx = pitch_rates_boards.season_context(y)
            pr_n = pitch_rates_boards.stamp_hitter_rows(
                board, _np_pos_by_id(season_hitters)[0], pr_ctx)
            pr_seasons[str(y)] = pitch_rates_boards.history_season(pr_ctx, "hit", pr_n)
        board.sort(key=lambda s: (s.get("hem_plus") or -999), reverse=True)
        hist[str(y)] = {"season": y, "n_qualified": len(board), "hitters": board}
        log(f"  hitter-history: {y} -> {len(board)} qualified")
    payload = {
        "generated_at": date.today().isoformat(),
        "seasons": [int(y) for y in hist],
        "note": ("Qualified hitters by season. HEM+: offensive-rate skill on shrunk wOBA, "
                 "100 = average qualified hitter. Slash line and volume are context."),
        "team_basis": team_basis_meta(basis_rows, label="hitter history",
                                      scope="history"),
        # Season by season, including a refusal: see bullpen_export.
        "ewar_join": ewar_join,
        # The payload receipt, iff the column: see bullpen_export.export_history.
        **({"ewar_vintage": _war_source_vintage(as_of=date.today().isoformat())}
           if any("war" in r for y in hist.values() for r in y["hitters"])
           else {}),
        "history": hist,
    }
    if pitch_rates_boards.serving():
        payload[pitch_rates_boards.PAYLOAD_KEY] = pitch_rates_boards.history_block(
            pr_seasons, date.today().isoformat())
    if write and hist:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        log(f"  hitter-history: wrote {out_path.name} ({len(hist)} seasons)")
    return payload


def export_then_defense(season: Optional[int] = None, *, log=print) -> int:
    """The standalone entry point: write the hitter board, then the Defense
    board that joins HEM+ from it.

    THE DEFECT THIS CLOSES (audit RML03, 2026-10-01). data/defense_leaderboards
    copies hem_plus off this board by MLBAM for the glove-versus-bat chart and
    the Standard view. Both run_monthly paths already run the defense export
    after this one, but a hand run of `python hitter_export.py` (the per-hand
    HEM+ change, d4a76a62 and 24c56eca) rewrote this board alone and left 5 of
    652 fielders on the previous build's HEM+ until the next nightly. A board
    that did not write (0 hitters) leaves the Defense board alone."""
    n = export(season, log=log)
    if n:
        import defense_export
        defense_export.export(season, log=log)
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "history":
        _yrs = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else None
        export_history(_yrs)
    else:
        _season = int(sys.argv[1]) if len(sys.argv) > 1 else None
        export_then_defense(_season)
