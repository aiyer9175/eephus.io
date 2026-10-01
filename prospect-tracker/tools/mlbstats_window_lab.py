# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""mlbstats_window_lab - the MULTI-YEAR window lab for the /mlbstats/ boards.

WHAT THIS BUILDS. A fixed, pre-registered set of season WINDOWS, each one a
board in its own right: counts summed, rates pooled once over their own named
denominator, and every "+" index RECOMPUTED for that window by the method the
shipped three-year columns already use. Nothing here is folded in the browser
and nothing is recomputed at export time: the artifacts are frozen and
vintage-stamped exactly as `hem_plus_3yr` and its siblings are.

THE METHOD, PER COLUMN, FOUND IN THIS REPO RATHER THAN INVENTED HERE
====================================================================
Five exporters already ship a multi-season value. Each column names the ONE its
recipe came from, because they do not all weight the same thing, and the column
easiest to get wrong is the one whose shipped recipe is easiest to miss:

  hem_plus     tools/hem_plus_lab._multiyear_proposed  PA-weighted mean of the
                                                       ROUNDED per-season HEM+
  sem_plus     tools/sem_plus_lab._multiyear_proposed  IP-weighted, rounded
  rem_plus     tools/rem_plus_lab._multiyear_proposed  IP-weighted, rounded
  dem_plus     tools/dem_plus_lab._dem3                innings-weighted, on the
                                                       UNROUNDED dem_plus_raw:
                                                       that builder's choice,
                                                       and the one place the
                                                       four labs differ
  gmli         tools/leverage_consistency_eval         RELIEF-ENTRY-weighted
               .proposed_values                        (gmli x appearances),
                                                       never innings-weighted
  war_pa_plus  tools/war_rate_plus_lab.window_values   the same recipe with an
  war_ip_plus                                          arbitrary window length,
                                                       CALLED here, not copied

So the house recipe is one sentence, and this module states it once:

    value(window) = sum over the window of (index in season y) * (that season's
    own denominator), divided by the sum of those denominators, where each
    per-season index was scored against THAT SEASON'S OWN POOL.

Three consequences of that recipe are properties of the shipped columns too,
and they are published rather than hidden:

  1. 100 IS NOT THE WINDOW AVERAGE. The window pool is the union of the seasons'
     pools, so its mean drifts (measured over the shipped history payloads: HEM+
     averages 99.0 over one season and 96.1 over five). `pool_stats` ships n,
     mean and sd for every index on every window so the page reports what 100
     and one standard deviation are ON THAT POOL instead of repeating the
     one-season sentence.
  2. TEN POINTS IS NOT ONE SIGMA of the window pool (HEM+ sd 18.09 over one
     season against 14.87 over five). So NO VALUE RULER, NO TIER, NO BAND
     COLOUR travels onto a window index. That is the rule
     test_value_ruler.py::test_raw_ewar_columns_carry_no_ladder already enforces
     for a count on a pool it was not measured on, and a window pool is a new
     pool by the same argument. The rows carry `pct`, the percentile INSIDE the
     window's own pool, which is the one ordering that survives a change of
     window.
  3. A PARTIAL WINDOW IS NOT A SMALL NUMBER, unlike a count. So every index row
     carries `n_seasons`, `denom_total` and the `established` / `provisional`
     tag each lab already defines, with the labs' own thresholds imported rather
     than retyped.

TWO CHOICES HERE ARE THIS MODULE'S OWN, AND THEY ARE SAID OUT LOUD
==================================================================
  1. RIV+ HAS NO SHIPPED MULTI-YEAR COLUMN. There is no `riv_plus_3yr` anywhere
     in this repo, so the innings weighting is ours. RIV+ is REALISED IMPACT
     rather than a rate skill, and innings are the exposure that produced the
     impact, which is why they are the weight; its established / provisional
     thresholds are REM+'s, because the pool is the same arms, and that is a
     borrowed threshold rather than a measured one.
  2. THE UNIVERSE IS THE WINDOW'S, NOT THE CURRENT SEASON'S. Every shipped
     `_multiyear_proposed` publishes a value only for a player who qualifies in
     the CURRENT season (hem_plus_lab: PA >= 200 this year), so a player who
     stopped playing mid-window has no three-year value at all. This lab
     publishes anyone clearing the window's own summed floor, which is the
     spec's universe rule and is what makes a window a board rather than a
     column on today's board. A 2024-2025 regular with no 2026 line therefore
     gets an l3 index the shipped column would not give him, and that is
     deliberate.

CONTRIBUTING SEASONS. Each metric keeps its OWN rule, because the point of this
module is to travel the shipped method rather than to add a second one:
hem / sem / rem / dem contribute every season in which the player carries that
season's index and a positive denominator (their builders' rule), and
war_pa_plus / war_ip_plus contribute seasons clearing the DISPLAY gate (that
lab's rule, argued in window_values' own docstring). The divergence is real and
it is disclosed per metric in `definition`, not smoothed over.

WHICH WINDOWS, AND WHY ONLY THESE
=================================
`l3`  the trailing three seasons ending at the live season. It is the window the
      shipped `*_3yr` columns are already on, so the window board can be checked
      against a column that already ships (see `reproduction` on the artifact).
      Since owner answer M17-2 (2026-09-25) the Current boards' HEM+, SEM+, REM+
      and DEM+ 3yr columns READ this window (bullpen_export.join_window_3yr),
      and run_monthly rebuilds it nightly (9e-pre0d), so `reproduction` now
      measures the lab evals that stay the gate record, not a served column.
`l5`  the trailing five seasons. It is the longest window that contains no 2020
      (every lab carries EXCLUDE_SEASONS = {2020}; 2022-2026 clears it) and no
      season outside the feed coverage of all six boards, and it roughly doubles
      the sample of l3.

NOT BUILT, and each refusal is a cost or a coverage fact rather than a taste:

  * `l2`: buildable and cheap, but it answers no question `l3` does not answer
    with more sample, and a third published scale is a third thing the page has
    to explain. Add it here if a question turns up for it.
  * `l10` and career: they contain 2020, which every index lab excludes, and the
    leverage feed has no 2020 at all (.cache/win_prob holds 2018, 2019 and
    2021 on). A ten-season index would also be an index over a run environment
    that moved under it.
  * SINGLE SEASONS: a window of length one is the board that already ships
    (data/*_history.json and the live leaderboards). Recomputing one here would
    be a second copy of a served number and a second chance to disagree with it.
    The page reaches a single season through the existing payloads.

Counts and pooled rates travel honestly over ANY window, so an arbitrary
from/to range is still available to the page for those columns: the eWAR board's
substrate for that is data/war_seasons.json (war_board_export.build_seasons).
What cannot be done on an arbitrary range is an index, because every window is a
lab pass.

THE UNIVERSE IS EVERY PLAYER-SEASON
===================================
The fold reads a WHOLE-LEAGUE per-season panel, never the shipped history
payloads, which carry only the rows that qualified in that season (measured:
hitter_history.json ships 362 / 357 / 361 / 365 / 347 rows, every one
`qualified: true`, against 658 rows on the live hitter board). Folding those
would pool a rate over the seasons in which a player happened to qualify, which
is a rate on a basis it was not computed on. The qualified rule is applied to
the WINDOW total, once, at the end, and it filters the rows the artifact
publishes, never the seasons that feed a row.

THE PANEL, AND WHY IT IS NOT A THIRD SUBSTRATE
==============================================
arb_metrics.py already builds a whole-league per-season Arkmetric panel offline
and memoises it under .cache/arb_metrics/, and its docstring records that
widening HISTORY_SEASONS instead was MEASURED and rejected (about 152 KB a
season, so 27 seasons would ship roughly 4 MB to a browser that renders one
pill). This module follows that pattern exactly, with its own memo namespace so
the arbitration model's 18 memo files are never invalidated by a schema change
here: .cache/mlbstats_windows/panel_<season>_v<SCHEMA>.json, completed seasons
only, built from the same offline doors arb_metrics uses
(hitter_export.load_season_hitting and fa_sources.fetch_statsapi_season_stats ->
bullpen_export.rows_from_pitching_splits, both disk-cached 2000-2026) plus
defense_export.score_season and mlb_leverage.fetch_season_all_leverage for the
two boards arb_metrics does not cover. Nothing in .cache/ ships.

THE FIELDING BLOCK IS THE EXCEPTION TO "FROZEN". A completed season's stat line
never changes, which is what makes the memo sound, but the fielding block is
FanGraphs-sourced and FanGraphs can revise a past season (the spec says so in
terms: a window is as of each row's own fetch). So `dfn` carries its own build
date inside the panel and expires after DFN_MAX_AGE_DAYS, rescored in place on
the next run; the rest of the panel is permanent.

eWAR IS NEVER MEMOISED. The panel holds what a completed season's stat line
holds, which never changes; the eWAR sides come from bullpen_export
._side_war_by_season on every run, so a window's `war` column always describes
the eWAR build the boards beside it are on, and the artifact stamps
`war_provider` and `ewar_generated_at` so a join can refuse a mismatch the way
bullpen_export.join_war_rate_3yr already does (audit F10-01).

Run: `python tools/mlbstats_window_lab.py [--force] [season]`
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("EEPHUS_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

_log = logging.getLogger(__name__)

DATA = ROOT / "data"
CACHE_DIR = ROOT / ".cache" / "mlbstats_windows"
INDEX_PATH = DATA / "mlbstats_windows.json"
#: The per-season substrate the Overall window folds, written by
#: war_board_export in the eWAR board's own process.
SUBSTRATE_PATH = DATA / "war_seasons.json"

#: Panel shape version. Bump to invalidate this module's memo files ALONE; the
#: arbitration panel's own SCHEMA is a different constant in a different
#: namespace and must never be bumped from here.
#: v2: the pitching block carries each reliever's RELIEF ENTRIES, because gmLI
#: pools on entries and not on innings (leverage_consistency_eval owns that
#: recipe), and the fielding block carries `dem_plus_raw`, because
#: dem_plus_lab._dem3 weights the UNROUNDED per-season DEM+.
SCHEMA = 2

#: How long a memoised panel's FanGraphs fielding block is trusted. The lab's
#: own cadence (run_monthly.LAB_EVAL_FRESH_DAYS), so a revision to a past
#: season's fielding runs reaches a window within one lab pass instead of
#: waiting for a --force nobody would know to run.
DFN_MAX_AGE_DAYS = 45

#: The windows this lab builds, longest name first in the artifact. `years` is
#: the count of seasons ENDING AT the live season, which is the convention
#: data/war_rate_plus_multiyear_eval.json already ships (`window` [2024, 2025,
#: 2026]); a window that stopped at the last COMPLETE season would disagree with
#: the frozen three-year columns already on the page.
WINDOWS = (
    {"key": "l3", "years": 3, "name": "Last 3"},
    {"key": "l5", "years": 5, "name": "Last 5"},
)

#: A window is REFUSED rather than published when it is thin. Three separate
#: ways to be thin, because a window can be wrong in three ways: a season of the
#: window has no panel at all, a board has too few rows to be a board, or an
#: index pool is too small for a mean and a standard deviation to describe it.
MIN_BOARD_ROWS = 50
MIN_POOL_N = 100
#: ... and a fourth way: a season that loaded every block can still be HALF a
#: season, because the leverage walk reports its coverage and returns what it
#: walked. A block whose season is under this share of the window's median
#: season is a refusal rather than a quietly shorter denominator.
MIN_SEASON_SHARE = 0.5


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _i(v):
    n = _num(v)
    return None if n is None else int(n)


def _r(v, nd=3):
    n = _num(v)
    return None if n is None else round(n, nd)


def _nolog(*_a, **_k):
    return None


# --------------------------------------------------------------------------- #
# thresholds, imported from the labs that own them
# --------------------------------------------------------------------------- #
def _tags() -> dict:
    """{metric: (min seasons, min denominator)} for the established /
    provisional tag, read from the lab that defines each one so a threshold
    cannot drift into a second copy here."""
    from tools import dem_plus_lab, hem_plus_lab, rem_plus_lab, sem_plus_lab
    from tools import leverage_consistency_eval as lce
    from tools import war_rate_plus_lab as wrp
    return {
        "hem_plus": (hem_plus_lab.TAG_MIN_SEASONS, hem_plus_lab.TAG_MIN_PA),
        "sem_plus": (sem_plus_lab.TAG_MIN_SEASONS, sem_plus_lab.TAG_MIN_IP),
        "rem_plus": (rem_plus_lab.TAG_MIN_SEASONS, rem_plus_lab.TAG_MIN_IP),
        "riv_plus": (rem_plus_lab.TAG_MIN_SEASONS, rem_plus_lab.TAG_MIN_IP),
        "dem_plus": (dem_plus_lab.TAG_MIN_SEASONS, dem_plus_lab.TAG_MIN_INN),
        # gmLI is the one POOLED RATE here that carries a tag, because the
        # shipped gmli_3yr does: 2+ seasons and 60+ relief entries, counted in
        # relief entries and not in innings.
        "gmli": (lce.TAG_MIN_SEASONS, lce.TAG_MIN_ENTRIES),
        "war_pa_plus": (wrp.EST_MIN_SEASONS, wrp.EST_MIN_PA),
        "war_ip_plus_sp": (wrp.EST_MIN_SEASONS, wrp.EST_MIN_SP_IP),
        "war_ip_plus_rp": (wrp.EST_MIN_SEASONS, wrp.EST_MIN_RP_IP),
    }


def _excluded_seasons() -> list:
    from tools import war_rate_plus_lab as wrp
    return sorted(wrp.EXCLUDE_SEASONS)


def _qualified_rule() -> dict:
    """The one-season qualified cut of each board, read from the metric module
    that owns it. Applied to the WINDOW TOTAL, flat, exactly as the eWAR board's
    own window rule is (spec decision D5): a threshold that scaled with the
    number of seasons a row happens to carry could not be published in one
    sentence, and a count board is self-protecting anyway."""
    import dem_plus
    import hem_plus
    import leverage_export
    import rem_plus
    import sem_plus
    import war_board_export as wbe
    # EVERY NUMBER AND EVERY SENTENCE IS READ, the leverage board's included:
    # that is the one place a threshold could have drifted without a test
    # noticing, and leverage_export.QUAL_PA / QUAL_STARTS are what the served
    # leverage board opens on.
    overall = (int(wbe.QUAL_MIN_PA), int(wbe.QUAL_MIN_IP))
    hit_pa = int(hem_plus.QUALIFY_MIN_PA)
    sp = (int(sem_plus.QUALIFY_MIN_GS), int(sem_plus.QUALIFY_MIN_IP))
    rp = (int(rem_plus.QUALIFY_MIN_TBF), int(rem_plus.QUALIFY_MIN_IP),
          int(rem_plus.QUALIFY_MIN_G))
    lev = (int(leverage_export.QUAL_PA), int(leverage_export.QUAL_STARTS))
    dfn_inn = int(dem_plus.QUALIFY_MIN_INN)
    return {
        "overall": {"min_pa": overall[0], "min_ip": overall[1],
                    "rule": (f"PA >= {overall[0]} or IP >= {overall[1]} over "
                             f"the whole window")},
        "hitters": {"min_pa": hit_pa,
                    "rule": f"PA >= {hit_pa} over the whole window"},
        "starters": {"min_gs": sp[0], "min_ip": sp[1],
                     "rule": (f"GS >= {sp[0]} or IP >= {sp[1]} over the whole "
                              f"window")},
        "bullpen": {"min_tbf": rp[0], "min_ip": rp[1], "min_g": rp[2],
                    "rule": (f"TBF >= {rp[0]}, or IP >= {rp[1]} with G >= "
                             f"{rp[2]}, over the whole window")},
        "leverage": {"min_pa": lev[0], "min_starts": lev[1],
                     "rule": (f"PA >= {lev[0]} for a batter or starts >= "
                              f"{lev[1]} for a starter, over the whole window")},
        "defense": {"min_inn": dfn_inn,
                    "rule": (f"defensive innings >= {dfn_inn} over the whole "
                             f"window")},
    }


# --------------------------------------------------------------------------- #
# the per-season panel
# --------------------------------------------------------------------------- #
def _panel_path(season: int, cache_dir: Path | None = None) -> Path:
    return (cache_dir or CACHE_DIR) / f"panel_{int(season)}_v{SCHEMA}.json"


def _is_final(season: int) -> bool:
    """A completed season's stat line is frozen, so its panel is permanent. The
    live season is rebuilt on every run and never memoised (arb_metrics._is_final
    makes the same call for the same reason)."""
    return int(season) < date.today().year


def _hitting_block(season: int, log=_nolog) -> tuple[dict, bool]:
    """{mlbam: hitting counts + HEM+} for one season, whole league.

    The COUNTS come off the season line (hitter_export.load_season_hitting, the
    disk-cached fetcher) and the INDEX off the same hem_plus.score_pool the
    board runs, so a panel season is the board's own season and not a second
    scoring of it. The counts the shipped payload drops are exactly the ones a
    pooled rate needs: hitter_history.json ships avg / obp / slg / babip / k_pct
    with no H, 2B, 3B, HBP, SF or SO behind them, so a rate there cannot be
    repooled over a window at all."""
    import hem_plus
    import hitter_export as he
    rows = he.load_season_hitting(int(season))
    if not rows:
        return {}, False
    by_id = {int(r["mlbam"]): r for r in rows if r.get("mlbam") is not None}
    scored = hem_plus.score_pool(he.build_hitters(rows))
    out: dict = {}
    for h in scored.get("hitters") or []:
        mid = h.get("mlbam")
        if mid is None:
            continue
        raw = by_id.get(int(mid)) or {}
        out[int(mid)] = {
            "name": h.get("name"), "team": h.get("team"),
            "pos": raw.get("primary_pos"),
            "hem": _num(h.get("hem_plus")), "qual": bool(h.get("qualified")),
            "pa": _i(raw.get("PA")), "ab": _i(raw.get("AB")), "h": _i(raw.get("H")),
            "2b": _i(raw.get("2B")), "3b": _i(raw.get("3B")), "hr": _i(raw.get("HR")),
            "bb": _i(raw.get("BB")), "ibb": _i(raw.get("IBB")),
            "hbp": _i(raw.get("HBP")), "sf": _i(raw.get("SF")), "so": _i(raw.get("SO")),
            "sb": _i(raw.get("SB")), "cs": _i(raw.get("CS")),
        }
    log(f"    {season}: {len(out)} hitters")
    return out, True


def _pitching_block(season: int, leverage: dict | None, log=_nolog) -> tuple[dict, bool]:
    """{mlbam: pitching counts + SEM+ / REM+ / RIV+} for one season.

    ONE ROW PER PITCHER, NOT ONE PER POOL. SEM+ and REM+ are anchored on two
    pools that must never be merged (ARKMETRIC_SCALE_CONVENTIONS.md:77), so the
    row carries whichever of them the season's role earned him, and the window
    boards select on that: a season he spent relieving is on the bullpen window
    board and a season he spent starting is on the starter one. Summing both
    onto one window row would put relief innings inside a starter's ERA.

    NOT bullpen_export.load_season_pitching, which is a LIVE StatsAPI call. The
    cached fetcher plus rows_from_pitching_splits is the offline door
    arb_metrics documents, and it is the same field mapping by construction."""
    import bullpen_export as be
    import fa_sources
    import rem_plus
    import sem_plus
    import starter_export as se
    try:
        splits = fa_sources.fetch_statsapi_season_stats(int(season), "pitching")
    except Exception as exc:                # noqa: BLE001 - a cold season is a skip
        _log.warning("window lab: %s pitching feed failed: %s", season, exc)
        return {}, False
    rows = be.rows_from_pitching_splits(splits, int(season))
    if not rows:
        return {}, False
    out: dict = {}
    for r in rows:
        mid = r.get("mlbam")
        if mid is None:
            continue
        out[int(mid)] = {
            "name": r.get("name"), "team": r.get("team"),
            "g": _i(r.get("G")), "gs": _i(r.get("GS")),
            "outs": int(round(be.ip_to_float(r.get("IP")) * 3.0)),
            "tbf": _i(r.get("BF")), "er": _i(r.get("ER")), "r": _i(r.get("R")),
            "bb": _i(r.get("BB")), "so": _i(r.get("SO")), "hr": _i(r.get("HR")),
            "hbp": _i(r.get("HBP")), "pit": _i(r.get("Pit")),
            "strk": _i(r.get("Strk")), "cg": _i(r.get("CG")),
            "go": _i(r.get("GO")), "ao": _i(r.get("AO")),
            "sv": _i(r.get("SV")), "hld": _i(r.get("HLD")),
        }
    try:
        for s in sem_plus.score_pool(se.build_starters(rows)).get("starters") or []:
            mid = s.get("mlbam")
            if mid is not None and int(mid) in out:
                out[int(mid)].update({"sem": _num(s.get("sem_plus")),
                                      "sp_qual": bool(s.get("qualified"))})
    except Exception as exc:                # noqa: BLE001 - one pool is not the panel
        _log.warning("window lab: %s starter scoring failed: %s", season, exc)
    try:
        rel = be.build_relievers(rows, leverage or {})
        for r in rem_plus.score_pool(rel).get("relievers") or []:
            mid = r.get("mlbam")
            if mid is None or int(mid) not in out:
                continue
            # `gapp` is RELIEF ENTRIES, off the same winProbability walk
            # (mlb_leverage._finalize returns `appearances`). It is carried
            # because gmLI pools on entries: tools/leverage_consistency_eval
            # .proposed_values builds the shipped gmli_3yr as
            # sum(gmli * appearances) / sum(appearances), and the Reliever
            # dataclass drops the count on the way through.
            lev_row = (leverage or {}).get(int(mid)) or {}
            out[int(mid)].update({
                "rem": _num(r.get("rem_plus")), "riv": _num(r.get("riv_plus")),
                "rp_qual": bool(r.get("qualified")),
                "gmli": _num(r.get("gmli")), "wpa": _num(r.get("wpa")),
                "wpa_li": _num(r.get("wpa_li")),
                "gapp": _i(lev_row.get("appearances")),
                "sd": _i(r.get("sd")), "md": _i(r.get("md")),
            })
    except Exception as exc:                # noqa: BLE001
        _log.warning("window lab: %s reliever scoring failed: %s", season, exc)
    log(f"    {season}: {len(out)} pitchers "
        f"({sum(1 for v in out.values() if v.get('sem') is not None)} SP pool, "
        f"{sum(1 for v in out.values() if v.get('rem') is not None)} RP pool)")
    return out, True


def _defense_block(season: int, log=_nolog) -> tuple[dict, bool]:
    """{mlbam: fielding runs, innings and DEM+} for one season, whole league,
    scored by defense_export.score_season, which is the board's own scorer.

    `file_red=False`: a framing check inside a lab pass must not file an ingest
    red against the served defense board."""
    import defense_export as de
    try:
        res = de.score_season(int(season), log=_nolog, file_red=False)
    except Exception as exc:                # noqa: BLE001 - a cold season is a skip
        _log.warning("window lab: %s defense scoring failed: %s", season, exc)
        return {}, False
    if not res:
        return {}, False
    out: dict = {}
    for f in res.get("fielders") or []:
        if f.mlbam is None or not f.inn:
            continue
        frm = (f.frm_runs if (f.frm_runs is not None
                              and float((f.inn_by_pos or {}).get("C") or 0) > 0)
               else None)
        out[int(f.mlbam)] = {
            "name": f.name, "team": f.team, "pos": f.primary_pos,
            "inn": _r(f.inn, 1),
            "pos_inn": _r(float((f.inn_by_pos or {}).get(f.primary_pos) or 0.0), 1),
            # BOTH: `dem` is the published (rounded) season value, which is
            # what the per-season reproduction check compares against the
            # served board, and `dem_raw` is what the WINDOW weights, because
            # dem_plus_lab._dem3 weights dem_plus_raw. HEM+, SEM+ and REM+
            # weight their rounded per-season value; DEM+ is the exception, and
            # following each builder is the whole point of this module.
            "dem": _num(f.dem_plus), "dem_raw": _num(f.dem_plus_raw),
            "qual": bool(f.qualified),
            "fld_runs": _num(f.fld_runs), "frm_runs": _num(frm),
            "pos_runs": _num(f.pos_runs), "pos_runs_fg": _num(f.pos_runs_fg),
            "po": _num(f.putouts), "a": _num(f.assists), "e": _num(f.errors),
        }
    log(f"    {season}: {len(out)} fielders")
    return out, True


def _leverage_blocks(season: int, log=_nolog) -> tuple[dict, dict, dict, bool]:
    """(batters, starters, relievers, ok) from the cached winProbability walk.

    The reliever map is handed back so the pitching block can score RIV+ and
    gmLI off the same walk instead of paying for a second one."""
    try:
        import mlb_leverage
        rel, bat, strt, cov = mlb_leverage.fetch_season_all_leverage(int(season))
    except Exception as exc:                # noqa: BLE001 - a cold season is a skip
        _log.warning("window lab: %s leverage walk failed: %s", season, exc)
        return {}, {}, {}, False
    if not bat and not strt:
        return {}, {}, {}, False
    log(f"    {season}: {cov.get('games')}/{cov.get('games_total')} games, "
        f"{len(bat)} batters, {len(strt)} starters")
    return ({int(k): v for k, v in bat.items()},
            {int(k): v for k, v in strt.items()},
            rel or {}, True)


def _age_days(stamp) -> int | None:
    """Whole days since an ISO date stamp, or None if it cannot be read."""
    try:
        return (date.today() - date.fromisoformat(str(stamp)[:10])).days
    except (TypeError, ValueError):
        return None


def _write_panel(panel: dict, path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(panel, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:                  # pragma: no cover - defensive
        _log.warning("window lab: could not memoise %s: %s",
                     panel.get("season"), exc)


def season_panel(season: int, *, force: bool = False, cache_dir: Path | None = None,
                 log=_nolog) -> dict:
    """The whole-league panel for one season, memoised for completed seasons.

    A season is memoised only when EVERY block loaded. A partial panel written
    once is trusted forever, which is the defect arb_metrics.season_metrics
    records having shipped (a hitters-only memo that silently dropped every
    pitcher from the model).

    THE FIELDING BLOCK EXPIRES; nothing else does. A completed season's stat
    line is frozen, but its FanGraphs fielding runs can be revised, so `dfn`
    carries its own build date and is rescored in place after DFN_MAX_AGE_DAYS.
    A rescore that fails keeps the block it has rather than dropping a board:
    the age is on the panel and on the window's coverage block either way."""
    season = int(season)
    path = _panel_path(season, cache_dir)
    if not force and _is_final(season) and path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("schema") == SCHEMA:
                panel = {k: ({int(kk): vv for kk, vv in v.items()}
                             if isinstance(v, dict) and k in _PANEL_BLOCKS else v)
                         for k, v in doc.items()}
                age = _age_days((panel.get("block_built_at") or {}).get("dfn")
                                or panel.get("built_at"))
                if age is None or age <= DFN_MAX_AGE_DAYS:
                    return panel
                log(f"  window lab: {season} fielding block is {age}d old "
                    f"(> {DFN_MAX_AGE_DAYS}d); rescoring it")
                dfn, dfn_ok = _defense_block(season, log=log)
                if dfn_ok:
                    panel["dfn"] = dfn
                    panel.setdefault("block_built_at", {})["dfn"] = \
                        date.today().isoformat()
                    (panel.setdefault("sources", {})).update(
                        {"defense": True, "n_fielders": len(dfn)})
                    _write_panel(panel, path)
                else:
                    _log.warning("window lab: %s fielding rescore failed; the "
                                 "%dd-old block stands", season, age)
                return panel
        except (OSError, ValueError):
            _log.warning("window lab: unreadable panel %s; rebuilding", path.name)

    t0 = time.time()
    log(f"  window lab: building the {season} panel...")
    lev_bat, lev_sp, lev_rel, lev_ok = _leverage_blocks(season, log=log)
    hit, hit_ok = _hitting_block(season, log=log)
    pit, pit_ok = _pitching_block(season, lev_rel, log=log)
    dfn, dfn_ok = _defense_block(season, log=log)
    today = date.today().isoformat()
    panel = {
        "schema": SCHEMA, "season": season,
        "built_at": today,
        # PER-BLOCK VINTAGE. Only `dfn` can go stale on a completed season, but
        # every block states when it was read so a window's coverage block can
        # say how old each number is rather than how old the file is.
        "block_built_at": {"hit": today, "pit": today, "dfn": today,
                           "lev": today},
        "complete": bool(hit_ok and pit_ok and dfn_ok and lev_ok),
        "sources": {"hitting": hit_ok, "pitching": pit_ok, "defense": dfn_ok,
                    "leverage": lev_ok,
                    "n_hitters": len(hit), "n_pitchers": len(pit),
                    "n_fielders": len(dfn), "n_lev_batters": len(lev_bat),
                    "n_lev_starters": len(lev_sp)},
        "hit": hit, "pit": pit, "dfn": dfn, "lev_bat": lev_bat, "lev_sp": lev_sp,
    }
    log(f"  window lab: {season} panel in {round(time.time() - t0, 1)}s "
        f"(complete={panel['complete']})")
    if panel["complete"] and _is_final(season):
        _write_panel(panel, path)
    elif not panel["complete"]:
        _log.warning("window lab: %s is incomplete (%s); not memoised", season,
                     panel["sources"])
    return panel


_PANEL_BLOCKS = ("hit", "pit", "dfn", "lev_bat", "lev_sp")


# --------------------------------------------------------------------------- #
# the house window recipe
# --------------------------------------------------------------------------- #
def _pct_map(values: dict) -> dict:
    """The percentile convention the four `_multiyear_proposed` builders use,
    copied rather than re-derived: mid-rank over the pool, rounded to a whole
    percent. The POOL is the rows this window PUBLISHES, which is what makes the
    number readable beside the others on the same board."""
    xs = sorted(values.values())
    n = len(xs)
    out = {}
    for mid, v in values.items():
        lo = sum(1 for s in xs if s < v)
        eq = sum(1 for s in xs if s == v)
        out[mid] = int(round(100.0 * (lo + (eq + 1) / 2.0 - 0.5) / n)) if n else None
    return out


def _mu_sd(xs: list) -> tuple:
    n = len(xs)
    if n < 2:
        return (None, None)
    mu = sum(xs) / n
    sd = (sum((x - mu) ** 2 for x in xs) / (n - 1)) ** 0.5
    return (mu, sd or None)


def window_index(panels: dict, seasons: list, block: str, value_key: str,
                 weight, *, tag: tuple) -> dict:
    """{mlbam: {value, n_seasons, denom_total, tag}} - THE HOUSE RECIPE, in one
    place, for a metric whose per-season index the panel carries.

    `weight` is either a panel key or a callable returning the season's own
    denominator for that metric: PA for HEM+, innings for SEM+ / REM+ / RIV+,
    defensive innings for DEM+, exactly as each `_multiyear_proposed` weights
    it. A season contributes when it carries the index AND a positive
    denominator, which is those builders' rule; the noise a wide-open rule would
    admit is removed at the other end instead, by the window's own qualified
    floor on the summed denominator.

    `tag` is (min seasons, min denominator) from the lab that owns the metric."""
    tag_n, tag_d = tag
    acc: dict = {}
    for y in seasons:
        rows = (panels.get(y) or {}).get(block) or {}
        for mid, r in rows.items():
            v = _num(r.get(value_key))
            w = _num(weight(r) if callable(weight) else r.get(weight))
            if v is None or not w or w <= 0:
                continue
            a = acc.setdefault(int(mid), {"num": 0.0, "den": 0.0, "n": 0})
            a["num"] += v * w
            a["den"] += w
            a["n"] += 1
    out = {}
    for mid, a in acc.items():
        if a["den"] <= 0:
            continue
        est = a["n"] >= tag_n and a["den"] >= tag_d
        out[mid] = {"value": a["num"] / a["den"], "n_seasons": a["n"],
                    "denom_total": round(a["den"], 1),
                    "tag": "established" if est else "provisional"}
    return out


def _stamp_index(rows: dict, key: str, vals: dict, published: set) -> dict:
    """Write one index family onto the window rows and return its pool_stats.

    Four fields per family and no fifth: the value, its percentile inside this
    window's pool, the seasons behind it and the denominator behind it, plus the
    tag. There is deliberately no tier, no band and no `_adj`: a ruler measured
    on a one-season pool does not travel (see the module docstring, point 2)."""
    live = {mid: v["value"] for mid, v in vals.items() if mid in published}
    est = {mid: v["value"] for mid, v in vals.items()
           if mid in published and v["tag"] == "established"}
    pcts = _pct_map(live)
    mu, sd = _mu_sd(sorted(live.values()))
    emu, esd = _mu_sd(sorted(est.values()))
    for mid, v in vals.items():
        row = rows.get(mid)
        if row is None:
            continue
        row[key] = int(round(v["value"]))
        row[f"{key}_raw"] = round(v["value"], 2)
        row[f"{key}_pct"] = pcts.get(mid)
        row[f"{key}_tag"] = v["tag"]
        row[f"{key}_n"] = v["n_seasons"]
        row[f"{key}_denom"] = v["denom_total"]
    # THE POOL THE PAGE SHOWS IS NOT THE POOL THIS DESCRIBES, unless both are
    # published. A window pool is 30-40% provisional (measured on l3: HEM+ 233
    # of 587), and the spec defaults the page to established-only, so the
    # established block is what that view's 100 and one sigma actually are.
    # `pct` stays ranked over EVERY published row, provisional included,
    # because that is the ordering the rows are printed in and one ordering is
    # all a row can carry.
    return {"n": len(live), "mean": _r(mu, 2), "sd": _r(sd, 2),
            "n_established": len(est), "n_provisional": len(live) - len(est),
            "established": {"n": len(est), "mean": _r(emu, 2), "sd": _r(esd, 2)},
            "pct_pool": ("every published row on this board, provisional rows "
                         "included"),
            "note": ("100 is the average of each contributing SEASON'S pool, "
                     "not of this window's pool, because the value is the "
                     "denominator-weighted mean of the per-season index. This "
                     "block reports what the window pool actually is, and "
                     "`established` reports what the established-only view's "
                     "pool is.")}


# --------------------------------------------------------------------------- #
# counts and pooled rates
# --------------------------------------------------------------------------- #
def _sum_counts(panels: dict, seasons: list, block: str, keys: tuple,
                keep=None) -> dict:
    """{mlbam: {summed counts, _yrs, _last, name, team, pos}} over the window.

    ABSENT IS NOT ZERO, the rule arb_metrics.trailing's docstring already
    states: a season the player did not play contributes nothing rather than a
    zero, and a count no season carried stays absent rather than summing to 0.
    `keep(row)` decides which of a player's seasons this board covers at all.
    `_last` is the most recent season with a line, which is where the row's
    club, position and age come from, and it is stated on the payload rather
    than left to be inferred."""
    out: dict = {}
    for y in seasons:
        rows = (panels.get(y) or {}).get(block) or {}
        for mid, r in rows.items():
            if keep is not None and not keep(r):
                continue
            mid = int(mid)
            acc = out.setdefault(mid, {"_yrs": 0, "_last": None, "_seasons": [],
                                       "_clubs": []})
            acc["_yrs"] += 1
            acc["_seasons"].append(int(y))
            if acc["_last"] is None or int(y) >= acc["_last"]:
                acc["_last"] = int(y)
                acc["name"] = r.get("name")
                acc["team"] = r.get("team")
                acc["pos"] = r.get("pos")
            club = r.get("team")
            if club and club not in acc["_clubs"]:
                acc["_clubs"].append(club)
            for k in keys:
                v = _num(r.get(k))
                if v is None:
                    continue
                acc[k] = (acc.get(k) or 0.0) + v
    return out


def _hitter_rates(acc: dict) -> dict:
    """The pooled hitting rates, computed by handing the SUMMED counts back
    through the shipped derivation (hem_plus.derive_rates on a Hitter built by
    hitter_export.build_hitters).

    That is what makes every rate here pooled by its own named denominator
    without a second formula existing anywhere: AVG is H / AB over the window,
    BABIP is (H - HR) / (AB - SO - HR + SF) over the window, OBP is over
    AB + BB + HBP + SF, and OPS is the pooled OBP plus the pooled SLG rather
    than a pooled ratio of its own. Re-typing those denominators here is how a
    wrong number ends up under a right name."""
    import hem_plus
    import hitter_export as he
    row = {"mlbam": 0, "name": "", "team": "",
           "PA": acc.get("pa"), "AB": acc.get("ab"), "H": acc.get("h"),
           "2B": acc.get("2b"), "3B": acc.get("3b"), "HR": acc.get("hr"),
           "BB": acc.get("bb"), "IBB": acc.get("ibb"), "HBP": acc.get("hbp"),
           "SF": acc.get("sf"), "SO": acc.get("so"), "SB": acc.get("sb"),
           "CS": acc.get("cs")}
    hitters = he.build_hitters([row])
    if not hitters:
        return {}
    h = hitters[0]
    hem_plus.derive_rates(h)
    woba = hem_plus._raw_woba(h)
    return {"avg": _r(h.rates.get("avg")), "obp": _r(h.rates.get("obp")),
            "slg": _r(h.rates.get("slg")), "ops": _r(h.rates.get("ops")),
            "iso": _r(h.rates.get("iso")), "babip": _r(h.rates.get("babip")),
            "bb_pct": _r(h.rates.get("bb_pct"), 4),
            "k_pct": _r(h.rates.get("k_pct"), 4),
            "woba_raw": _r(woba), "_woba_den": _r(h.rates.get("woba_denom"), 1)}


def _pitcher_rates(acc: dict, *, starter: bool) -> dict:
    """The pooled pitching rates, computed the same way: the summed counts are
    handed back through the shipped scorer (starter_export.build_starters plus
    sem_plus.derive_rates, or bullpen_export.build_relievers plus
    rem_plus.derive_rates), so ERA is ER / IP x 9 over the window and K% is
    SO / TBF over it.

    SKILL FIP IS NOT AMONG THEM and never can be: sem_plus.fip_skill shrinks the
    component rates toward `pool.mean_k_pct` / `mean_bb_pct` / `mean_hbp_pct` /
    `mean_hr_rate` and offsets the result by `pool.cfip`. Those are five
    parameters of one season's pool, so a window FIP would be a different
    statistic wearing the same header."""
    import bullpen_export as be
    import rem_plus
    import sem_plus
    import starter_export as se
    outs = int(acc.get("outs") or 0)
    row = {"mlbam": 0, "name": "", "team": "",
           "G": acc.get("g"), "GS": acc.get("gs"),
           "IP": f"{outs // 3}.{outs % 3}",
           "BF": acc.get("tbf"), "ER": acc.get("er"), "R": acc.get("r"),
           "BB": acc.get("bb"), "SO": acc.get("so"), "HR": acc.get("hr"),
           "HBP": acc.get("hbp"), "Pit": acc.get("pit"), "Strk": acc.get("strk"),
           "CG": acc.get("cg"), "GO": acc.get("go"), "AO": acc.get("ao"),
           "SV": acc.get("sv"), "HLD": acc.get("hld")}
    if starter:
        built = se.build_starters([row])
        if not built:
            return {}
        s = built[0]
        sem_plus.derive_rates(s)
        # HR/9 is built in the ROW, not in derive_rates (sem_plus.py:327 and
        # rem_plus.py:476 carry the same expression), and the row builder needs a
        # season pool this window does not have. Same expression, over the
        # window's own summed HR and innings.
        return {"era": _r(s.rates.get("era"), 2),
                "hr9": _r(_pooled((acc.get("hr") or 0) * 9.0, outs / 3.0, 2), 2),
                "k_pct": _r(s.rates.get("k_pct"), 4),
                "bb_pct": _r(s.rates.get("bb_pct"), 4),
                "k_bb_pct": _r(s.rates.get("k_bb_pct"), 4),
                "gb_pct": _r(s.rates.get("gb_pct"), 4),
                "ip_per_gs": _r(s.rates.get("ip_per_gs"), 2),
                "strike_pct": _r(s.rates.get("strike_pct"), 4)}
    built = be.build_relievers([row], {})
    if not built:
        return {}
    r = built[0]
    rem_plus.derive_rates(r)
    return {"era": _r(r.rates.get("era"), 2),
            "hr9": _r(_pooled((acc.get("hr") or 0) * 9.0, outs / 3.0, 2), 2),
            "k_pct": _r(r.rates.get("k_pct"), 4),
            "bb_pct": _r(r.rates.get("bb_pct"), 4),
            "k_bb_pct": _r(r.rates.get("k_bb_pct"), 4)}


def _pooled(num: float | None, den: float | None, nd: int = 3):
    if num is None or not den:
        return None
    return round(float(num) / float(den), nd)


# --------------------------------------------------------------------------- #
# the six window boards
# --------------------------------------------------------------------------- #
def _war_window(war_by: dict, seasons: list, mid: int, side) -> tuple:
    """(summed side eWAR, seasons carrying a cell). `side` is "bat", "pit" or
    "both"; "both" is the whole player, summed UNROUNDED and rounded once, which
    is the rule defense_export._stamp_war and war_board_export both apply."""
    by = war_by.get(int(mid)) or {}
    total, n = 0.0, 0
    for y in seasons:
        cell = by.get(int(y))
        if not cell:
            continue
        vals = ([cell.get("bat"), cell.get("pit")] if side == "both"
                else [cell.get(side)])
        got = [v for v in (_num(x) for x in vals) if v is not None]
        if not got:
            continue
        total += sum(got)
        n += 1
    return ((round(total, 1), n) if n else (None, 0))


def _overall_board(seasons: list, war_by: dict, sub: dict, qual: dict) -> dict:
    """The Overall window board, folded from data/war_seasons.json.

    IT IS FOLDED FROM THE SUBSTRATE, not rebuilt here, and that is the point:
    war_board_export writes that file in the SAME process it writes the board
    from the SAME side map, so a window and the Current view cannot disagree.
    Rebuilding the fold from a second read is exactly the defect the substrate
    exists to close (measured 2026-09-17: the served board and data/ewar.json
    disagreed on 173 of the top 400 rows)."""
    fields = {k: i for i, k in enumerate(sub.get("fields") or [])}
    tm, pos_d = sub.get("tm") or [], sub.get("pos") or []
    lo, hi = min(seasons), max(seasons)
    rows = []
    lg_bat = lg_pit = 0.0
    for mid, entry in (sub.get("players") or {}).items():
        name, srows = entry[0], entry[1]
        bat = pit = 0.0
        has_bat = has_pit = False
        pa = ip = g = gs = 0.0
        has = {"pa": False, "ip": False, "g": False, "gs": False}
        yrs, clubs, age, pos, last = 0, [], None, None, None
        for r in srows:
            y = r[fields["season"]]
            if y < lo or y > hi:
                continue
            yrs += 1
            b, p = r[fields["war_bat"]], r[fields["war_pit"]]
            if b is not None:
                bat += b
                has_bat = True
            if p is not None:
                pit += p
                has_pit = True
            for key, acc_name in (("pa", "pa"), ("ip", "ip"), ("g", "g"), ("gs", "gs")):
                v = r[fields[key]]
                if v is None:
                    continue
                has[key] = True
                if key == "pa":
                    pa += v
                elif key == "ip":
                    ip += v
                elif key == "g":
                    g += v
                else:
                    gs += v
            if last is None or y >= last:
                last = y
                age = r[fields["age"]]
                pos = (pos_d[r[fields["pos"]]] if r[fields["pos"]] is not None
                       else None)
            if r[fields["tm"]] is not None:
                for c in tm[r[fields["tm"]]].split("/"):
                    if c and c not in clubs:
                        clubs.append(c)
        if not yrs:
            continue
        lg_bat += bat
        lg_pit += pit
        row = {"mlbam": int(mid), "name": name, "pos": pos, "age": age,
               "yrs": yrs, "clubs": clubs, "last_season": last,
               "war": round(bat + pit, 1),
               "war_bat": round(bat, 1) if has_bat else None,
               "war_pit": round(pit, 1) if has_pit else None,
               "pa": int(pa) if has["pa"] else None,
               "ip": round(ip, 1) if has["ip"] else None,
               "g": int(g) if has["g"] else None,
               "gs": int(gs) if has["gs"] else None}
        # Each side divides by ITS OWN denominator. A single eWAR-per-600 on the
        # summed value would charge a two-way player's pitching to his plate
        # appearances, which is the same reason _side_war_by_season keeps the
        # sides on separate keys.
        # A DISPLAY FLOOR UNDER BOTH RATES, and not a taste.
        # war_rate_plus_lab.window_values gates a contributing season on
        # DISPLAY_MIN_PA / DISPLAY_MIN_RP_IP and its docstring argues exactly
        # this: admitting a sample the one-season column would refuse to print
        # puts small-sample noise at the top of the board (measured on the
        # unfloored build: Ryne Nelson, a starting pitcher, read Bat/600 = 42.0
        # off a handful of plate appearances). This board's own qualified
        # numbers ARE those two floors (war_board_export.QUAL_MIN_PA = 100,
        # QUAL_MIN_IP = 30, both aliases of the WAR-rate display floors), so a
        # side's rate appears exactly when its denominator would have been
        # printable over one season, and `display_min` is on the payload so the
        # page states the rule instead of guessing it.
        row["bat_600"] = (_pooled(bat * 600.0, pa, 2)
                          if (has_bat and pa >= qual["min_pa"]) else None)
        row["pitch_200"] = (_pooled(pit * 200.0, ip, 2)
                            if (has_pit and ip >= qual["min_ip"]) else None)
        row["qualified"] = bool((row["pa"] or 0) >= qual["min_pa"]
                                or (row["ip"] or 0) >= qual["min_ip"])
        # Absent is absent, the board's own convention: a field with nothing
        # behind it is left OFF the row rather than served as a null or a zero.
        rows.append({k: v for k, v in row.items() if v is not None})
    rows.sort(key=lambda r: (-(r["war"] if r["war"] is not None else -99), r["name"]))
    # SUMMED UNROUNDED, ROUNDED ONCE, which is the rule build_seasons states for
    # a row and the league total is no different: summing the rows' printed
    # tenths carries one rounding error per row (measured on l3: 2935.9 that
    # way against 2937.5 honestly, 1.6 wins of rounding).
    league = {"war": round(lg_bat + lg_pit, 1),
              "war_bat": round(lg_bat, 1), "war_pit": round(lg_pit, 1),
              "n_players": len(rows),
              "n_qualified": sum(1 for r in rows if r.get("qualified"))}
    return {"players": rows, "league": league}


def _hitters_board(panels: dict, seasons: list, war_by: dict, qual: dict,
                   tags: dict, wrp: dict) -> tuple[dict, dict]:
    acc = _sum_counts(panels, seasons, "hit",
                      ("pa", "ab", "h", "2b", "3b", "hr", "bb", "ibb", "hbp",
                       "sf", "so", "sb", "cs"))
    rows, published = {}, set()
    for mid, a in acc.items():
        pa = a.get("pa") or 0
        row = {"mlbam": mid, "name": a.get("name"), "team": a.get("team"),
               "pos": a.get("pos"), "yrs": a["_yrs"], "clubs": a["_clubs"],
               "last_season": a["_last"],
               "pa": int(pa), "ab": _i(a.get("ab")), "hr": _i(a.get("hr")),
               "bb": _i(a.get("bb")), "sb": _i(a.get("sb"))}
        rates = _hitter_rates(a)
        row.update({k: v for k, v in rates.items() if not k.startswith("_")})
        war, n = _war_window(war_by, seasons, mid, "bat")
        if war is not None:
            row["war"] = war
            row["war_n"] = n
        row["qualified"] = bool(pa >= qual["min_pa"])
        row["denoms"] = {"pa": int(pa), "ab": _i(a.get("ab")),
                         "obp": _i((a.get("ab") or 0) + (a.get("bb") or 0)
                                   + (a.get("hbp") or 0) + (a.get("sf") or 0)),
                         "babip": _i((a.get("ab") or 0) - (a.get("so") or 0)
                                     - (a.get("hr") or 0) + (a.get("sf") or 0)),
                         "woba": _i(rates.get("_woba_den"))}
        rows[mid] = row
        if row["qualified"]:
            published.add(mid)
    pools = {}
    pools["hem_plus"] = _stamp_index(
        rows, "hem_plus", window_index(panels, seasons, "hit", "hem", "pa",
                                       tag=tags["hem_plus"]), published)
    if wrp.get("hit"):
        pools["war_pa_plus"] = _stamp_index(rows, "war_pa_plus", wrp["hit"],
                                            published)
    out = [r for mid, r in rows.items() if mid in published]
    out.sort(key=lambda r: -(r.get("hem_plus_raw") or -999))
    return {"hitters": out}, pools


def _pitcher_board(panels: dict, seasons: list, war_by: dict, qual: dict,
                   tags: dict, wrp: dict, *, starter: bool) -> tuple[dict, dict]:
    idx_key = "sem" if starter else "rem"
    keep = (lambda r: r.get("sem") is not None) if starter \
        else (lambda r: r.get("rem") is not None)
    keys = ("g", "gs", "outs", "tbf", "er", "r", "bb", "so", "hr", "hbp", "pit",
            "strk", "cg", "go", "ao", "sv", "hld", "wpa", "wpa_li", "sd", "md")
    acc = _sum_counts(panels, seasons, "pit", keys, keep=keep)
    # gmLI POOLS ON RELIEF ENTRIES. tools/leverage_consistency_eval
    # .proposed_values builds the shipped gmli_3yr as sum(gmli * appearances) /
    # sum(appearances) and its own docstring calls it the relief-entry-weighted
    # mean; innings would be a second method and a different number (measured
    # on Adrian Morejon 2024-2026: 1.51 on entries against 1.52 on innings).
    # The tag is that module's own 2 seasons / 60 entries. Computed ONCE for the
    # board, not once per row.
    gmli = ({} if starter else window_index(panels, seasons, "pit", "gmli",
                                            "gapp", tag=tags["gmli"]))
    rows, published = {}, set()
    for mid, a in acc.items():
        ip = round((a.get("outs") or 0) / 3.0, 1)
        row = {"mlbam": mid, "name": a.get("name"), "team": a.get("team"),
               "yrs": a["_yrs"], "clubs": a["_clubs"], "last_season": a["_last"],
               "ip": ip, "g": _i(a.get("g")), "tbf": _i(a.get("tbf"))}
        if starter:
            row["gs"] = _i(a.get("gs"))
            row["cg"] = _i(a.get("cg"))
            row["qualified"] = bool((a.get("gs") or 0) >= qual["min_gs"]
                                    or ip >= qual["min_ip"])
        else:
            row["saves"] = _i(a.get("sv"))
            row["holds"] = _i(a.get("hld"))
            row["sd"] = _i(a.get("sd"))
            row["md"] = _i(a.get("md"))
            row["wpa"] = _r(a.get("wpa"), 2)
            row["wpa_li"] = _r(a.get("wpa_li"), 3)
            row["qualified"] = bool((a.get("tbf") or 0) >= qual["min_tbf"]
                                    or (ip >= qual["min_ip"]
                                        and (a.get("g") or 0) >= qual["min_g"]))
            gm = gmli.get(mid)
            if gm:
                row["gmli"] = _r(gm["value"], 2)
                row["gmli_n"] = gm["n_seasons"]
                row["gmli_entries"] = int(gm["denom_total"])
                row["gmli_tag"] = gm["tag"]
        row.update(_pitcher_rates(a, starter=starter))
        war, n = _war_window(war_by, seasons, mid, "pit")
        if war is not None:
            row["war"] = war
            row["war_n"] = n
        row["denoms"] = {"ip": ip, "tbf": _i(a.get("tbf")),
                         "gs": _i(a.get("gs")),
                         "bip": _i((a.get("go") or 0) + (a.get("ao") or 0)),
                         "pitches": _i(a.get("pit"))}
        if not starter and row.get("gmli") is not None:
            row["denoms"]["entries"] = row["gmli_entries"]
        rows[mid] = row
        if row["qualified"]:
            published.add(mid)
    pools = {}
    metric = "sem_plus" if starter else "rem_plus"
    pools[metric] = _stamp_index(
        rows, metric,
        window_index(panels, seasons, "pit", idx_key,
                     lambda r: (r.get("outs") or 0) / 3.0, tag=tags[metric]),
        published)
    if not starter:
        pools["riv_plus"] = _stamp_index(
            rows, "riv_plus",
            window_index(panels, seasons, "pit", "riv",
                         lambda r: (r.get("outs") or 0) / 3.0,
                         tag=tags["riv_plus"]), published)
    pool_key = "SP" if starter else "RP"
    if wrp.get(pool_key):
        pools["war_ip_plus"] = _stamp_index(rows, "war_ip_plus", wrp[pool_key],
                                            published)
    out = [r for mid, r in rows.items() if mid in published]
    out.sort(key=lambda r: -(r.get(f"{metric}_raw") or -999))
    return ({"starters": out} if starter else {"relievers": out}), pools


def _leverage_board(panels: dict, seasons: list, war_by: dict,
                    qual: dict) -> tuple[dict, dict]:
    """WPA, WPA/LI, pLI and Clutch over a window.

    CLUTCH IS RECOMPOSED, never averaged: it is `WPA / pooled pLI - WPA/LI`,
    built from the summed WPA, the summed WPA/LI and the pooled pLI, each of
    which travels by its own rule first. Averaging three seasons of a composite
    is not the composite of three seasons."""
    out = {}
    # The winProbability fold knows a name and an id and no club, so the club
    # comes from the same season's hitting or pitching panel: one basis per
    # board, never two.
    for y in seasons:
        panel = panels.get(y) or {}
        for blk, src in (("lev_bat", "hit"), ("lev_sp", "pit")):
            for mid, r in (panel.get(blk) or {}).items():
                if not r.get("team"):
                    r["team"] = ((panel.get(src) or {}).get(int(mid)) or {}).get("team")
    bat = _sum_counts(panels, seasons, "lev_bat", ("pa", "wpa", "wpa_li"))
    # pLI is the PA-weighted mean of the season pLI, which is the same fold as
    # an index without the tag: the leverage board publishes no established /
    # provisional tag on it, so none is invented here. Computed ONCE.
    pli_all = window_index(panels, seasons, "lev_bat", "pli", "pa", tag=(1, 0.0))
    brows = []
    for mid, a in bat.items():
        pa = a.get("pa") or 0
        pli = pli_all.get(mid)
        row = {"mlbam": mid, "name": a.get("name"), "team": a.get("team"),
               "yrs": a["_yrs"], "clubs": a["_clubs"], "last_season": a["_last"],
               "pa": int(pa), "wpa": _r(a.get("wpa"), 3),
               "wpa_li": _r(a.get("wpa_li"), 3),
               "pli": _r(pli["value"], 3) if pli else None,
               "denoms": {"pa": int(pa)}}
        if pli and pli["value"]:
            row["clutch"] = _r((a.get("wpa") or 0.0) / pli["value"]
                               - (a.get("wpa_li") or 0.0), 3)
            row["pli_n"] = pli["n_seasons"]
        war, n = _war_window(war_by, seasons, mid, "bat")
        if war is not None:
            row["war"] = war
            row["war_n"] = n
        row["qualified"] = bool(pa >= qual["min_pa"])
        if row["qualified"]:
            brows.append(row)
    brows.sort(key=lambda r: -(r.get("wpa") or -999))

    sp = _sum_counts(panels, seasons, "lev_sp", ("starts", "wpa", "wpa_li"))
    srows = []
    for mid, a in sp.items():
        starts = a.get("starts") or 0
        row = {"mlbam": mid, "name": a.get("name"), "team": a.get("team"),
               "yrs": a["_yrs"], "clubs": a["_clubs"], "last_season": a["_last"],
               "starts": int(starts), "wpa": _r(a.get("wpa"), 3),
               "wpa_li": _r(a.get("wpa_li"), 3),
               "wpa_per_start": _pooled(a.get("wpa"), starts, 3),
               "denoms": {"starts": int(starts)}}
        war, n = _war_window(war_by, seasons, mid, "pit")
        if war is not None:
            row["war"] = war
            row["war_n"] = n
        row["qualified"] = bool(starts >= qual["min_starts"])
        if row["qualified"]:
            srows.append(row)
    srows.sort(key=lambda r: -(r.get("wpa") or -999))
    out = {"batters": brows, "starters": srows}
    return out, {}


def _defense_board(panels: dict, seasons: list, war_by: dict, qual: dict,
                   tags: dict) -> tuple[dict, dict]:
    acc = _sum_counts(panels, seasons, "dfn",
                      ("inn", "pos_inn", "fld_runs", "frm_runs", "pos_runs",
                       "pos_runs_fg", "po", "a", "e"))
    rows, published = {}, set()
    for mid, a in acc.items():
        inn = _num(a.get("inn")) or 0.0
        fld_total = (a.get("fld_runs") or 0.0) + (a.get("frm_runs") or 0.0)
        ch = (a.get("po") or 0.0) + (a.get("a") or 0.0) + (a.get("e") or 0.0)
        row = {"mlbam": mid, "name": a.get("name"), "team": a.get("team"),
               "pos": a.get("pos"), "yrs": a["_yrs"], "clubs": a["_clubs"],
               "last_season": a["_last"],
               "inn": _r(inn, 1), "pos_inn": _r(a.get("pos_inn"), 1),
               "fld_runs": _r(a.get("fld_runs"), 1),
               "frm_runs": _r(a.get("frm_runs"), 1),
               "fld_total": _r(fld_total, 1),
               "pos_runs": _r(a.get("pos_runs"), 1),
               "pos_runs_fg": _r(a.get("pos_runs_fg"), 1),
               "rate_1000": _pooled(1000.0 * fld_total, inn),
               "fld_pct": _pooled((a.get("po") or 0.0) + (a.get("a") or 0.0), ch),
               "denoms": {"inn": _r(inn, 1), "chances": _r(ch, 0)}}
        if a.get("pos_runs") is not None:
            row["def_runs"] = _r(fld_total + (a.get("pos_runs") or 0.0), 1)
        war, n = _war_window(war_by, seasons, mid, "both")
        if war is not None:
            row["war"] = war
            row["war_n"] = n
        row["qualified"] = bool(inn >= qual["min_inn"])
        rows[mid] = row
        if row["qualified"]:
            published.add(mid)
    # `dem_raw`, not `dem`: dem_plus_lab._dem3 weights dem_plus_raw, and this is
    # the one metric of the four whose shipped builder does. Weighting the
    # rounded value instead moved 146 of 400 shared rows by up to 5 points in
    # the build that did it.
    pools = {"dem_plus": _stamp_index(
        rows, "dem_plus",
        window_index(panels, seasons, "dfn", "dem_raw", "inn",
                     tag=tags["dem_plus"]),
        published)}
    out = [r for mid, r in rows.items() if mid in published]
    out.sort(key=lambda r: -(r.get("dem_plus_raw") or -999))
    return {"fielders": out}, pools


# --------------------------------------------------------------------------- #
# the WAR-rate indexes, through the lab that owns them
# --------------------------------------------------------------------------- #
_WRP_FRAME = None


def war_rate_windows(seasons: list, log=_nolog) -> tuple[dict, dict]:
    """({pool: window_values}, meta) for WAR/PA+ and WAR/IP+, by CALLING
    tools/war_rate_plus_lab.window_values with this window's length.

    That function already takes `years`, already weights by the denominator,
    already gates contributing seasons on the display floor and already tags
    established against provisional. Reimplementing any of it here would be the
    second method this module exists not to write. It reads the war_daily stint
    frames through war_source on the SERVED provider, so a failed read leaves
    these two columns absent with a reason rather than taking the build down."""
    meta = {"available": False, "pools": []}
    try:
        from tools import war_rate_plus_lab as wrp
        # ONE read per process: load_frames pulls both war_daily stint frames,
        # and the pitching one is not cached by pybaseball (war_source
        # .stint_frame's ASYMMETRY note), so a read per window is a second
        # download of war_daily_pitch.txt.
        global _WRP_FRAME
        if _WRP_FRAME is None:
            _WRP_FRAME = wrp.load_frames()
        frame = _WRP_FRAME
    except Exception as exc:                # noqa: BLE001 - two columns, not a build
        meta["refused"] = f"{type(exc).__name__}: {exc}"
        _log.warning("window lab: the WAR-rate frames failed (%s); WAR/PA+ and "
                     "WAR/IP+ are absent from this window", exc)
        return {}, meta
    years = len(seasons)
    last = max(seasons)
    out = {}
    for pool in ("hit", "SP", "RP"):
        try:
            out[pool] = wrp.window_values(frame, pool, last, years)
            meta["pools"].append(pool)
        except Exception as exc:            # noqa: BLE001
            _log.warning("window lab: WAR-rate %s window failed: %s", pool, exc)
    meta["available"] = bool(out)
    meta["source"] = "tools/war_rate_plus_lab.window_values"
    log(f"  window lab: WAR-rate windows for {meta['pools']}")
    return out, meta


# --------------------------------------------------------------------------- #
# the artifact
# --------------------------------------------------------------------------- #
def window_seasons(live_season: int, years: int) -> list:
    return list(range(int(live_season) - int(years) + 1, int(live_season) + 1))


def guard_window(block: dict, seasons: list, panels: dict) -> str | None:
    """The reason this window must NOT be published, or None.

    A thin window is refused rather than shipped. The page then says the window
    is unavailable and why, which is a visible absence; a published thin window
    is an invisible wrong answer, and this program exists because of one of
    those (four history payloads documented as carrying eWAR that did not).

    Five questions, in order of how invisible the failure would be: is a season
    missing entirely, did a season lose a BLOCK (the panel's own `complete`),
    is a season half-walked against the window's median season, is a board too
    short to be a board, and is an index pool too small for a mean and a spread
    to describe it."""
    missing = [y for y in seasons if not (panels.get(y) or {}).get("hit")]
    if missing:
        return f"no panel for {missing}"
    # THE PANEL'S OWN COMPLETENESS FLAG. season_panel already computes it and
    # already refuses to memoise on it, and a row-count floor cannot see what it
    # sees: a season whose defense scoring or leverage walk died still carries
    # hitters, so the defense and leverage boards would simply pool fewer
    # seasons than the eWAR column beside them, disclosed nowhere a reader looks.
    incomplete = []
    for y in seasons:
        panel = panels.get(y) or {}
        if panel.get("complete"):
            continue
        src_blocks = panel.get("sources") or {}
        dead = [k for k in ("hitting", "pitching", "defense", "leverage")
                if not src_blocks.get(k)] or ["an unnamed block"]
        incomplete.append(f"{y} is missing {', '.join(dead)}")
    if incomplete:
        return "an incomplete panel is inside this window: " + "; ".join(incomplete)
    # A season can load every block and still be HALF a season: the leverage
    # walk returns what it walked and reports its coverage. So each block's
    # season is measured against the window's own median season.
    for blk, label in (("hit", "hitters"), ("pit", "pitchers"),
                       ("dfn", "fielders"), ("lev_bat", "leverage batters"),
                       ("lev_sp", "leverage starters")):
        counts = [len((panels.get(y) or {}).get(blk) or {}) for y in seasons]
        med = sorted(counts)[len(counts) // 2]
        for y, n in zip(seasons, counts):
            if med and n < MIN_SEASON_SHARE * med:
                return (f"{y} carries {n} {label} against a median season of "
                        f"{med} on this window")
    for name, doc in (block.get("boards") or {}).items():
        for key, rows in doc.items():
            if key in ("league",) or not isinstance(rows, list):
                continue
            if len(rows) < MIN_BOARD_ROWS:
                return (f"the {name} board has {len(rows)} rows on this window "
                        f"(floor {MIN_BOARD_ROWS})")
    for board, pools in (block.get("pool_stats") or {}).items():
        for metric, st in pools.items():
            if (st.get("n") or 0) < MIN_POOL_N:
                return (f"{metric} on the {board} board has {st.get('n')} rows "
                        f"in its window pool (floor {MIN_POOL_N})")
            if st.get("sd") is None:
                return f"{metric} on the {board} board has no spread to report"
    return None


def build_window(key: str, seasons: list, panels: dict, war_by: dict, sub: dict,
                 log=_nolog, overall: bool = True) -> dict:
    """One window: six boards, their pool_stats, and what it is standing on."""
    t0 = time.time()
    tags = _tags()
    qual = _qualified_rule()
    wrp, wrp_meta = war_rate_windows(seasons, log=log)
    boards, pool_stats = {}, {}
    if overall:
        boards["overall"] = _overall_board(seasons, war_by, sub, qual["overall"])
    boards["hitters"], pool_stats["hitters"] = _hitters_board(
        panels, seasons, war_by, qual["hitters"], tags, wrp)
    boards["starters"], pool_stats["starters"] = _pitcher_board(
        panels, seasons, war_by, qual["starters"], tags, wrp, starter=True)
    boards["bullpen"], pool_stats["bullpen"] = _pitcher_board(
        panels, seasons, war_by, qual["bullpen"], tags, wrp, starter=False)
    boards["leverage"], _ = _leverage_board(panels, seasons, war_by,
                                            qual["leverage"])
    boards["defense"], pool_stats["defense"] = _defense_board(
        panels, seasons, war_by, qual["defense"], tags)
    pool_stats = {k: v for k, v in pool_stats.items() if v}
    n_rows = {b: sum(len(v) for v in doc.values() if isinstance(v, list))
              for b, doc in boards.items()}
    log(f"  window lab: {key} ({seasons[0]}-{seasons[-1]}) "
        f"{n_rows} in {round(time.time() - t0, 1)}s")
    return {
        "window": {"key": key, "label": f"{seasons[0]}-{seasons[-1]}",
                   "years": len(seasons), "seasons": seasons},
        "boards": boards, "pool_stats": pool_stats, "n_rows": n_rows,
        "qualified_rule_window": qual,
        "war_rate_source": wrp_meta,
        # WHAT THIS WINDOW IS STANDING ON, season by season: how many rows each
        # panel block delivered, and when each panel was built. A window that
        # looks full because one season carried it reads as such here rather
        # than in nobody's head.
        "coverage": {
            "seasons": seasons,
            "n_published": n_rows,
            "per_season": {str(y): {"hitters": len((panels.get(y) or {}).get("hit") or {}),
                                    "pitchers": len((panels.get(y) or {}).get("pit") or {}),
                                    "fielders": len((panels.get(y) or {}).get("dfn") or {}),
                                    "lev_batters": len((panels.get(y) or {}).get("lev_bat") or {}),
                                    "lev_starters": len((panels.get(y) or {}).get("lev_sp") or {})}
                           for y in seasons},
            "panel_built_at": {str(y): (panels.get(y) or {}).get("built_at")
                               for y in seasons},
            "panel_complete": {str(y): (panels.get(y) or {}).get("complete")
                               for y in seasons},
        },
        "panel_built_at": {str(y): (panels.get(y) or {}).get("built_at")
                           for y in seasons},
    }


def reproduction(window: dict, log=_nolog) -> dict:
    """Does this window's `l3` index reproduce the SHIPPED three-year column?

    The shipped `*_3yr` artifacts are built by the four `_multiyear_proposed`
    functions this module's recipe follows, over the same three seasons, so the
    l3 block should agree with them on every player both cover. It is reported
    rather than asserted because the two are not built on the same day: the live
    season's stat line moves under both, and a lab artifact up to
    LAB_EVAL_FRESH_DAYS old was built on an older copy of it. A DISAGREEMENT ON
    A COMPLETED-SEASON PLAYER would be a method difference and is the thing this
    block exists to make visible.

    EXCEPT THAT THERE ARE NONE (measured 2026-09-17): every player both
    artifacts cover has a live-season line, because a shipped three-year column
    only exists for a player the CURRENT board carries. So the completed-season
    test has an EMPTY POPULATION and can never fire, and a raw equal-count then
    reads as a method disagreement when it is a vintage one.
    `by_window_seasons` reports the statistic that does discriminate: drift
    against an older artifact scales with how much of a window is the LIVE
    season, and a method difference does not care how many seasons a player
    has. Measured against a hem_plus artifact 18 days old, mean |delta| ran
    3.61 for players whose window is the live season ALONE, 1.50 over two
    seasons and 0.98 over three. That gradient is the vintage signature."""
    out = {}
    pairs = (("hem_plus", "hem_plus_multiyear_eval.json", "hem_plus_3yr", "hitters", "hitters"),
             ("sem_plus", "sem_plus_multiyear_eval.json", "sem_plus_3yr", "starters", "starters"),
             ("rem_plus", "rem_plus_multiyear_eval.json", "rem_plus_3yr", "bullpen", "relievers"),
             ("dem_plus", "dem_plus_multiyear_eval.json", "dem_plus_3yr", "defense", "fielders"))
    for metric, fname, field, board, block in pairs:
        path = DATA / fname
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out[metric] = {"available": False, "reason": f"{fname} absent"}
            continue
        prop = (doc.get("proposed_values") or {})
        shipped = prop.get("players") or {}
        window_seasons_shipped = prop.get("window")
        mine = {str(r["mlbam"]): r.get(metric)
                for r in (window.get("boards") or {}).get(board, {}).get(block, [])
                if r.get(metric) is not None}
        both = [k for k in shipped if k in mine and shipped[k].get(field) is not None]
        deltas = [abs(mine[k] - shipped[k][field]) for k in both]
        # THE SPLIT THAT DISCRIMINATES. `*_n` is how many seasons of the
        # window the player actually appears in, so n == 1 means the window IS
        # the live season for him and n == len(seasons) means it is mostly
        # completed ones. Vintage drift rises as n falls; a method difference
        # would be flat in n.
        rows = {str(r["mlbam"]): r
                for r in (window.get("boards") or {}).get(board, {}).get(block, [])}
        _seas = (window.get("window") or {}).get("seasons") or []
        live = _seas[-1] if _seas else None
        by_n: dict = {}
        for k in both:
            r = rows.get(k) or {}
            n = r.get(f"{metric}_n") or r.get("yrs")
            if n:
                by_n.setdefault(int(n), []).append(
                    abs(mine[k] - shipped[k][field]))
        complete = [k for k in both
                    if (rows.get(k) or {}).get("last_season") != live]
        out[metric] = {
            "available": True, "artifact": fname,
            "shipped_window": window_seasons_shipped,
            "generated_at": doc.get("generated_at") or doc.get("as_of"),
            "n_shipped": len(shipped), "n_mine": len(mine), "n_both": len(both),
            "n_equal": sum(1 for d in deltas if d == 0),
            "max_abs_delta": max(deltas) if deltas else None,
            "mean_abs_delta": (round(sum(deltas) / len(deltas), 3) if deltas
                               else None),
            # The population the docstring's test needs, stated even when it
            # is empty, because an empty one IS the finding.
            "n_all_seasons_complete": len(complete),
            "max_abs_delta_all_complete": (
                max(abs(mine[k] - shipped[k][field]) for k in complete)
                if complete else None),
            "by_window_seasons": {
                str(n): {"n": len(v),
                         "n_equal": sum(1 for d in v if d == 0),
                         "mean_abs_delta": round(sum(v) / len(v), 3),
                         "max_abs_delta": max(v)}
                for n, v in sorted(by_n.items())},
            "reads": ("A delta that grows as the LIVE season's share of the"
                      " window grows is vintage drift against an older"
                      " artifact, not a method difference. Read"
                      " by_window_seasons and n_all_seasons_complete before"
                      " reading n_equal."),
        }
        # The gradient goes in the LOG LINE, not just the artifact: a bare
        # "115/327 equal" reads as a method disagreement at 2am, and the
        # thing that tells the two apart is how the delta moves with n.
        _grad = ", ".join(f"{n}yr {b['mean_abs_delta']}"
                          for n, b in out[metric]["by_window_seasons"].items())
        log(f"  window lab: {metric} vs {fname}: {out[metric]['n_equal']}/"
            f"{out[metric]['n_both']} equal, max delta "
            f"{out[metric]['max_abs_delta']}; mean |delta| by seasons in "
            f"window ({_grad}) - rising as the window shortens is vintage "
            f"drift, flat would be a method difference; "
            f"no-live-season players "
            f"{out[metric]['n_all_seasons_complete']}")
    return out


#: (metric, served history payload, its block, panel block, panel key). The
#: history payloads carry the per-season index for every completed season, which
#: is what makes the check below decisive.
_PER_SEASON_CHECK = (
    ("hem_plus", "hitter_history.json", "hitters", "hit", "hem"),
    ("sem_plus", "starter_history.json", "starters", "pit", "sem"),
    ("rem_plus", "bullpen_history.json", "relievers", "pit", "rem"),
    ("dem_plus", "defense_history.json", "fielders", "dfn", "dem"),
)


def per_season_reproduction(panels: dict, log=_nolog) -> dict:
    """THE CHECK THAT CANNOT MOVE UNDER ITS OWN FEET.

    `reproduction` compares this lab's l3 index against a shipped three-year
    artifact built on ANOTHER DAY, so a delta there is a method difference or a
    vintage difference and the block cannot tell you which. This one compares
    the panel's PER-SEASON index for a COMPLETED season against the value that
    season's served history payload publishes. A completed season's stat line is
    frozen and both numbers come out of the same scorer, so a delta here is a
    method difference and nothing else - which is what makes it the block to
    read first when a window looks wrong."""
    out = {}
    for metric, fname, block, pblk, pkey in _PER_SEASON_CHECK:
        try:
            doc = json.loads((DATA / fname).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out[metric] = {"available": False, "reason": f"{fname} absent"}
            continue
        hist = doc.get("history") or {}
        per_season, n_both, n_equal, worst = {}, 0, 0, None
        for y in sorted(panels):
            if not _is_final(y) or str(y) not in hist:
                continue
            rows = (hist.get(str(y)) or {}).get(block) or []
            mine = (panels.get(y) or {}).get(pblk) or {}
            eq = tot = 0
            mx = None
            for r in rows:
                mid = r.get("mlbam")
                if mid is None:
                    continue
                served = r.get(metric)
                ours = (mine.get(int(mid)) or {}).get(pkey)
                if served is None or ours is None:
                    continue
                tot += 1
                d = abs(int(round(ours)) - int(served))
                eq += 1 if d == 0 else 0
                mx = d if mx is None or d > mx else mx
            if not tot:
                continue
            per_season[str(y)] = {"n": tot, "n_equal": eq, "max_abs_delta": mx}
            n_both += tot
            n_equal += eq
            worst = mx if worst is None or (mx is not None and mx > worst) else worst
        out[metric] = {"available": bool(per_season), "artifact": fname,
                       "n": n_both, "n_equal": n_equal, "max_abs_delta": worst,
                       "per_season": per_season,
                       "means": ("the panel's per-season index against the "
                                 "served history payload for the same completed "
                                 "season: a delta is a METHOD difference, never "
                                 "a build date")}
        log(f"  window lab: per-season {metric}: {n_equal}/{n_both} equal, "
            f"max delta {worst}")
    return out


def basis_moved(index_path: Path | None = None) -> bool:
    """True when the SERVED eWAR build is not the one the window artifact was
    built on, so the cadence gate must NOT skip this lab.

    _artifact_fresh's `invalidated_by` hatch exists for exactly this shape, and
    its docstring says why: age is the wrong question for an artifact whose
    inputs were re-keyed under it. The eWAR board rebuilds nightly and this lab
    is on a 45-day cadence, so without this the window's `war` column could sit
    up to 45 days behind the eWAR column beside it - and the test that asserts
    the two share a basis would go red on a rebuild the cadence gate then
    refused to let the pipeline clear."""
    path = Path(index_path or INDEX_PATH)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False        # absent or unreadable: the cadence gate re-runs it
    try:
        import bullpen_export as be
        basis = be.served_war_basis()
    except Exception:       # noqa: BLE001 - a basis we cannot read is not a move
        return False
    return bool(doc.get("war_provider") != basis.get("war_provider")
                or doc.get("ewar_generated_at") != basis.get("ewar_generated_at"))


def built_today(index_path: Path | None = None) -> bool:
    """True when the window index was written today. The nightly live-panel
    step (run_monthly 9e-pre0d) asks this AND basis_moved, so a monthly night
    that already ran 6b4k in the same process does not walk the live season
    twice, while a moved eWAR basis still forces the rebuild."""
    path = Path(index_path or INDEX_PATH)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return str(doc.get("generated_at") or "")[:10] == date.today().isoformat()


# The Savant custom-leaderboard display columns (savant_leaderboards.py, X05-01)
# reach the one-season boards as season rates with no denominator beside them,
# so a window cannot repool them. One reason, keyed per column on each board.
_SAVANT_WINDOW_REASON = ("A Baseball Savant season rate served without the pitch "
                         "or batted-ball count behind it, so it cannot be repooled.")
_SAVANT_HIT_KEYS = ("whiff_pct", "chase_pct", "z_contact_pct", "sweet_spot_pct",
                    "pull_pct")
_SAVANT_PIT_KEYS = ("whiff_pct", "chase_pct", "z_contact_pct", "f_strike_pct",
                    "fb_velo")
# Savant catcher blocking and throwing (savant_catcher.py, X05-02): read for the
# live season only, so no window carries them.
_SAVANT_CATCHER_REASON = ("Baseball Savant's catcher blocking and throwing boards "
                          "are read for the live season only.")
_SAVANT_CATCHER_KEYS = ("c_blk_runs", "c_blk_aa", "c_blk_pitches", "c_cs_runs",
                        "c_cs_aa", "c_sb_att", "c_pop", "c_exchange", "c_arm")


# The Current boards' HEM+ / SEM+ / REM+ / DEM+ 3yr columns read THIS lab's l3
# index since owner answer M17-2 (bullpen_export.join_window_3yr), so on a window
# board the index column already is that number; the WAR-rate 3yr columns are
# still the frozen war_rate_plus_lab artifact.
_CURRENT_3YR_REASON = ("On the Current board this column is the Last 3 window's "
                       "index; on a window board the index column carries the "
                       "window's own value.")
_FROZEN_3YR_REASON = "A frozen lab artifact with a window of its own."


def columns_spec() -> dict:
    """WHAT EVERY COLUMN ON A WINDOW BOARD IS, published so the page reports the
    rule instead of typing it, and so a test can assert the FORMULA rather than
    the presence of a key.

    SUM adds over the window. POOL is one numerator over one named denominator,
    computed by handing the summed counts back through the shipped derivation.
    RECOMPOSED is built from other pooled values. INDEX is the house window
    recipe, and each one names the shipped builder its recipe came from (`from`)
    so the provenance is on the artifact and not only in this module's
    docstring; `own_choice` marks the two places this lab had no shipped recipe
    to follow. HIDDEN is a column the SERVED one-season board carries and a
    window does not, with the reason it does not, so the page can state the
    absence in one line instead of leaving a hole."""
    return {
        "overall": {
            "sum": ["war", "war_bat", "war_pit", "pa", "ip", "g", "gs"],
            "pool": {"bat_600": {"denom": "pa",
                                 "formula": "batting eWAR / PA x 600",
                                 "display_min": 100,
                                 "display_min_note": ("PA over the window, the "
                                                      "WAR-rate display floor "
                                                      "war_board_export.QUAL_MIN_PA "
                                                      "already uses")},
                     "pitch_200": {"denom": "ip",
                                   "formula": "pitching eWAR / IP x 200",
                                   "display_min": 30,
                                   "display_min_note": ("IP over the window, "
                                                        "war_board_export"
                                                        ".QUAL_MIN_IP")}},
            "index": {},
            "hidden": {"role": ("Role is a season fact: a pitcher who started "
                                "one year and relieved the next has no one role "
                                "over a window."),
                       "boards": "Also on is built from today's five boards."},
        },
        "hitters": {
            "sum": ["pa", "ab", "hr", "bb", "sb", "war"],
            "pool": {
                "avg": {"denom": "ab", "formula": "H / AB"},
                "obp": {"denom": "obp", "formula": "(H + BB + HBP) / (AB + BB + HBP + SF)"},
                "slg": {"denom": "ab", "formula": "TB / AB"},
                "iso": {"denom": "ab", "formula": "(TB - H) / AB"},
                "babip": {"denom": "babip", "formula": "(H - HR) / (AB - SO - HR + SF)"},
                "bb_pct": {"denom": "pa", "formula": "BB / PA"},
                "k_pct": {"denom": "pa", "formula": "SO / PA"},
                "woba_raw": {"denom": "woba", "formula": "the wOBA weights over the six events / (AB + BB - IBB + HBP + SF)"},
            },
            "recomposed": {"ops": "pooled OBP + pooled SLG"},
            "index": {
                "hem_plus": {"formula": ("PA-weighted mean of the ROUNDED "
                                         "per-season HEM+"),
                             "from": "tools/hem_plus_lab._multiyear_proposed"},
                "war_pa_plus": {"formula": ("PA-weighted mean of the per-season "
                                            "WAR/PA+, seasons gated on that "
                                            "lab's display floor"),
                                "from": "tools/war_rate_plus_lab.window_values"},
            },
            "hidden": {
                "woba": "The shrink target is that season's pool.",
                "wrc_plus": ("wRC+ is MLB's published season index. We hold the "
                             "index, not the pieces behind it."),
                "tier": "A cut on a season pool.",
                "xhem_plus": "Anchored to one season's pool, and 2016 on without 2020.",
                "xwoba": "The same anchoring and the same coverage gap.",
                "luck_gap": "A difference of two season-pool numbers.",
                "fwdhem_plus": "A forecast of next season.",
                "pwoba": "A forecast of next season.",
                "hem_plus_3yr": _CURRENT_3YR_REASON,
                "war_pa_plus_3yr": _FROZEN_3YR_REASON,
                "war_pa_plus_adj": ("The park and pool adjustment behind WAR/PA+ "
                                    "is fitted on one season's pool, so the "
                                    "adjusted value cannot be re-weighted across "
                                    "seasons."),
                **{k: _SAVANT_WINDOW_REASON for k in _SAVANT_HIT_KEYS},
            },
        },
        "starters": {
            "sum": ["ip", "g", "gs", "tbf", "cg", "war"],
            "pool": {
                "era": {"denom": "ip", "formula": "ER / IP x 9"},
                "hr9": {"denom": "ip", "formula": "HR / IP x 9"},
                "k_pct": {"denom": "tbf", "formula": "SO / TBF"},
                "bb_pct": {"denom": "tbf", "formula": "BB / TBF"},
                "k_bb_pct": {"denom": "tbf", "formula": "(SO - BB) / TBF"},
                "gb_pct": {"denom": "bip", "formula": "groundOuts / (groundOuts + airOuts)"},
                "ip_per_gs": {"denom": "gs", "formula": "IP / GS"},
                "strike_pct": {"denom": "pitches", "formula": "strikes / pitches"},
            },
            "index": {
                "sem_plus": {"formula": ("IP-weighted mean of the ROUNDED "
                                         "per-season SEM+"),
                             "from": "tools/sem_plus_lab._multiyear_proposed"},
                "war_ip_plus": {"formula": ("IP-weighted mean of the per-season "
                                            "WAR/IP+ on the starter pool"),
                                "from": "tools/war_rate_plus_lab.window_values"},
            },
            "hidden": {
                "fip": ("Skill FIP is shrunk toward that season's starter pool "
                        "and offset by that season's FIP constant. Two season "
                        "parameters, so it does not travel."),
                "role": "Role is a season fact.",
                "xsem_plus": "Anchored to one season's pool.",
                "xwoba_against": "The same anchoring and the same coverage gap.",
                "luck": "A difference of two season-pool numbers.",
                "sem_plus_3yr": _CURRENT_3YR_REASON,
                "war_ip_plus_3yr": _FROZEN_3YR_REASON,
                "war_ip_plus_adj": ("The adjustment behind WAR/IP+ is fitted on "
                                    "one season's pool."),
                "swstr_pct": ("Derived from two Baseball Savant season rates "
                              "(whiff% x swing%) with no pitch count beside "
                              "them, so it cannot be repooled."),
                **{k: _SAVANT_WINDOW_REASON for k in _SAVANT_PIT_KEYS},
            },
        },
        "bullpen": {
            "sum": ["ip", "g", "tbf", "saves", "holds", "sd", "md", "wpa",
                    "wpa_li", "war"],
            "pool": {
                "era": {"denom": "ip", "formula": "ER / IP x 9"},
                "hr9": {"denom": "ip", "formula": "HR / IP x 9"},
                "k_pct": {"denom": "tbf", "formula": "SO / TBF"},
                "bb_pct": {"denom": "tbf", "formula": "BB / TBF"},
                "k_bb_pct": {"denom": "tbf", "formula": "(SO - BB) / TBF"},
                "gmli": {"denom": "entries",
                         "formula": ("relief-entry-weighted mean of the "
                                     "per-season gmLI"),
                         "from": ("tools/leverage_consistency_eval"
                                  ".proposed_values"),
                         "tag": ("established with 2+ seasons and 60+ relief "
                                 "entries, that module's own thresholds")},
            },
            "index": {
                "rem_plus": {"formula": ("IP-weighted mean of the ROUNDED "
                                         "per-season REM+"),
                             "from": "tools/rem_plus_lab._multiyear_proposed"},
                "riv_plus": {"formula": "IP-weighted mean of the per-season RIV+",
                             "from": "tools/rem_plus_lab._multiyear_proposed",
                             "own_choice": ("There is no riv_plus_3yr in this "
                                            "repo. RIV+ is realised impact "
                                            "rather than a rate skill, so the "
                                            "weight is the innings that "
                                            "produced the impact, and the "
                                            "established thresholds are REM+'s "
                                            "because the pool is the same "
                                            "arms.")},
                "war_ip_plus": {"formula": ("IP-weighted mean of the per-season "
                                            "WAR/IP+ on the reliever pool"),
                                "from": "tools/war_rate_plus_lab.window_values"},
            },
            "hidden": {
                "fip": "Two season-pool parameters, as on the starter board.",
                "swstr_pct": ("Derived from two Baseball Savant season rates "
                              "(whiff% x swing%) with no pitch count beside "
                              "them, so it cannot be repooled."),
                "gmli_3yr": ("Its source ships no date at all, so it cannot be "
                             "vintage-stamped beside columns that are. The "
                             "window computes its own gmLI by that module's "
                             "recipe instead."),
                "xrem_plus": "Anchored to one season's pool.",
                "xwoba_against": "The same anchoring and the same coverage gap.",
                "rem_plus_3yr": _CURRENT_3YR_REASON,
                "war_ip_plus_3yr": _FROZEN_3YR_REASON,
                "war_ip_plus_adj": ("The adjustment behind WAR/IP+ is fitted on "
                                    "one season's pool."),
                "role": "Role is a season fact.",
                "luck": "A difference of two season-pool numbers.",
                **{k: _SAVANT_WINDOW_REASON for k in _SAVANT_PIT_KEYS},
            },
        },
        "leverage": {
            "sum": ["pa", "starts", "wpa", "wpa_li", "war"],
            "pool": {"pli": {"denom": "pa", "formula": "PA-weighted mean of the per-season pLI"},
                     "wpa_per_start": {"denom": "starts", "formula": "WPA / starts"}},
            "recomposed": {"clutch": "summed WPA / pooled pLI - summed WPA/LI"},
            "index": {},
            "hidden": {
                "gs": ("The leverage board prints the season feed's games "
                       "started beside the walk's own start count. The window "
                       "sums `starts`, which is the denominator every other "
                       "column on the row divides by; two start counts over a "
                       "window would be two answers to one question."),
            },
        },
        "defense": {
            "sum": ["inn", "pos_inn", "fld_runs", "frm_runs", "fld_total",
                    "pos_runs", "pos_runs_fg", "def_runs", "war"],
            "pool": {"rate_1000": {"denom": "inn", "formula": "(fielding + framing runs) / innings x 1000"},
                     "fld_pct": {"denom": "chances", "formula": "(PO + A) / (PO + A + E)"}},
            "index": {
                "dem_plus": {"formula": ("innings-weighted mean of the UNROUNDED "
                                         "per-season DEM+ (dem_plus_raw)"),
                             "from": "tools/dem_plus_lab._dem3",
                             "note": ("The one metric of the four whose shipped "
                                      "builder weights the unrounded value; the "
                                      "other three weight the rounded one, and "
                                      "each is followed rather than "
                                      "harmonised.")},
            },
            "hidden": {
                "rate_1000_shrunk": "The shrink constant is a season-pool parameter.",
                "rel": ("The reliability weight inn / (inn + k) behind the "
                        "shrunk rate; k is that season pool's constant."),
                "dem_plus_pct": ("A percentile inside ONE season's pool. The "
                                 "window carries its own, beside its own value."),
                "dem_plus_pos_pct": "The same, within a position.",
                "dem_plus_3yr": _CURRENT_3YR_REASON,
                "hem_plus": "Inherits the hitter board's anchoring.",
                "tier": "A cut on a season pool.",
                **{k: _SAVANT_CATCHER_REASON for k in _SAVANT_CATCHER_KEYS},
            },
        },
    }


def build(live_season: int | None = None, *, force: bool = False,
          cache_dir: Path | None = None, log=print) -> dict:
    """Every window, plus the index block that describes them."""
    import bullpen_export as be
    live_season = int(live_season or date.today().year)
    t0 = time.time()
    needed = sorted({y for w in WINDOWS
                     for y in window_seasons(live_season, w["years"])})
    panels = {}
    for y in needed:
        panels[y] = season_panel(y, force=force, cache_dir=cache_dir, log=log)
    war_by = be._side_war_by_season()
    try:
        sub = json.loads(SUBSTRATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sub = {"refused": f"{SUBSTRATE_PATH.name} unreadable: {exc}"}
    basis = be.served_war_basis()
    # THE BASIS GUARD (audit F10-01). The substrate is written by
    # war_board_export in its own process; if the eWAR build moved between that
    # write and this one, the Overall window would be a different series from
    # the eWAR column beside it on every other board here. A mismatch drops the
    # Overall board from the window rather than serving two series under one
    # name.
    sub_basis_ok = (sub.get("war_provider") == basis.get("war_provider")
                    and sub.get("ewar_generated_at") == basis.get("ewar_generated_at"))
    invalidate = None
    if sub.get("players") and not sub_basis_ok:
        # ... and the artifact says so in the one key the cadence gate reads, so
        # the next pipeline run REBUILDS instead of skipping a 45-day-fresh file
        # that is missing a whole board.
        invalidate = (f"the Overall board was dropped: the substrate is on "
                      f"{sub.get('war_provider')} / {sub.get('ewar_generated_at')} "
                      f"and the served basis is {basis.get('war_provider')} / "
                      f"{basis.get('ewar_generated_at')}")
        log(f"  window lab: data/war_seasons.json is on "
            f"{sub.get('war_provider')} / {sub.get('ewar_generated_at')} and the "
            f"served basis is {basis.get('war_provider')} / "
            f"{basis.get('ewar_generated_at')}; the Overall window is dropped")
        sub = {"refused": "the substrate is on another eWAR build"}

    # WHAT THE SUBSTRATE ITSELF SAYS IS MISSING. war_board_export publishes the
    # seasons whose feed died and, per season, WHICH GROUP died; a window that
    # folded a season with no feed at all would print a three-season PA total
    # over two seasons of plate appearances, which is the invisible kind of
    # wrong. A dead group is thinner than that and is disclosed rather than
    # refused: the eWAR sides are all there and one side's denominator is not.
    sub_src = sub.get("sources") or {}
    cold_all = {int(y) for y in (sub_src.get("seasons_without_a_feed") or [])}
    cold_groups = {int(y): g
                   for y, g in (sub_src.get("groups_without_a_feed") or {}).items()}

    built, refused = {}, {}
    for spec in WINDOWS:
        seasons = window_seasons(live_season, spec["years"])
        bad = [y for y in seasons if y in set(_excluded_seasons())]
        if bad:
            refused[spec["key"]] = (f"{bad} is inside this window and every "
                                    f"index lab excludes it")
            continue
        overall_absent = None
        if not sub.get("players"):
            overall_absent = sub.get("refused") or "no substrate"
        elif cold_all & set(seasons):
            overall_absent = (f"the substrate has no season feed for "
                              f"{sorted(cold_all & set(seasons))}, so this "
                              f"window's PA, IP, G and GS would be short by a "
                              f"whole season")
        block = build_window(spec["key"], seasons, panels, war_by, sub, log=log,
                             overall=overall_absent is None)
        block["name"] = spec["name"]
        if overall_absent:
            block["overall_absent"] = overall_absent
            log(f"  window lab: {spec['key']} has no Overall board: {overall_absent}")
        caveat = {str(y): g for y, g in cold_groups.items() if y in set(seasons)}
        if caveat and not overall_absent:
            block["overall_caveat"] = {
                "groups_without_a_feed": caveat,
                "means": ("those seasons carry their eWAR and no denominator "
                          "for the named side, so this window's PA or IP is "
                          "summed over fewer seasons than its eWAR is")}
        reason = guard_window(block, seasons, panels)
        if reason:
            refused[spec["key"]] = reason
            log(f"  window lab: REFUSED {spec['key']}: {reason}")
            continue
        built[spec["key"]] = block
    index = {
        "generated_at": date.today().isoformat(),
        "schema": SCHEMA, "live_season": live_season,
        # run_monthly._artifact_fresh reads this key and rebuilds on any truthy
        # value, whatever the stamp says.
        "invalidated_by": invalidate,
        "war_provider": basis.get("war_provider"),
        "ewar_generated_at": basis.get("ewar_generated_at"),
        "excluded_seasons": _excluded_seasons(),
        "qualified_rule_window": _qualified_rule(),
        "columns": columns_spec(),
        "windows": [
            {"key": k, "name": b["name"], "label": b["window"]["label"],
             "years": b["window"]["years"], "seasons": b["window"]["seasons"],
             "file": f"mlbstats_window_{k}.json",
             "n_rows": b["n_rows"], "pool_stats": b["pool_stats"],
             "coverage": b["coverage"]}
            for k, b in built.items()],
        "windows_refused": refused,
        "single_season": ("A window of one season is the board that already "
                          "ships: data/*_history.json for a past season and the "
                          "live leaderboards for this one. Nothing here "
                          "recomputes it."),
        "arbitrary_range": ("Counts and pooled rates travel over any window; an "
                            "index does not, because every window is a lab "
                            "pass. The eWAR board's arbitrary from/to range "
                            "folds data/war_seasons.json."),
        "method": ("Every index here is the denominator-weighted mean of the "
                   "per-season index, each season scored against its own pool, "
                   "which is the recipe hem_plus_3yr, sem_plus_3yr, "
                   "rem_plus_3yr, dem_plus_3yr and war_rate_plus_lab"
                   ".window_values already use. 100 is therefore the average of "
                   "each contributing season's pool and not of this window's, "
                   "and ten points is not one standard deviation of this "
                   "window's pool: pool_stats reports what both actually are, "
                   "and no value ruler, tier or band colour is carried onto a "
                   "window index."),
        "sources": {"panels": {str(y): (panels.get(y) or {}).get("sources")
                               for y in needed},
                    "substrate": {"file": "war_seasons.json",
                                  "generated_at": sub.get("generated_at"),
                                  "basis_matches_served": sub_basis_ok,
                                  "n_player_seasons": (sub.get("sources") or {})
                                  .get("n_player_seasons")},
                    "season_share": sub.get("season_share")},
        "build_seconds": None,
    }
    index["reproduction"] = {
        "per_season": per_season_reproduction(panels, log=log),
        "vs_shipped_3yr": (reproduction(built["l3"], log=log) if "l3" in built
                           else {"available": False,
                                 "reason": "no l3 window was published"}),
    }
    index["build_seconds"] = round(time.time() - t0, 1)
    return {"index": index, "windows": built}


def export(live_season: int | None = None, *, write: bool = True,
           force: bool = False, out_dir: Path | None = None,
           cache_dir: Path | None = None, log=print) -> int:
    """Write the index and one payload per window. Returns the window count.

    ONE FILE PER WINDOW, fetched when the window is picked. The index is small
    and says which windows exist, what their pools are and which columns are on
    them, so the page can draw the control and the copy without fetching a
    board it is not showing."""
    out_dir = Path(out_dir or DATA)
    res = build(live_season, force=force, cache_dir=cache_dir, log=log)
    index, windows = res["index"], res["windows"]
    if not windows:
        log("  window lab: no window survived the guard; nothing was written")
        try:
            import bullpen_export as be
            be._ingest_red("mlbstats_windows",
                           f"no window was publishable: {index['windows_refused']}. "
                           f"The previous window artifacts stand.")
        except Exception:                   # noqa: BLE001 - reporting is best effort
            pass
        return 0
    if not write:
        return len(windows)
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, block in windows.items():
        payload = {"generated_at": index["generated_at"],
                   "schema": SCHEMA,
                   "war_provider": index["war_provider"],
                   "ewar_generated_at": index["ewar_generated_at"],
                   "excluded_seasons": index["excluded_seasons"],
                   "columns": index["columns"],
                   "method": index["method"],
                   "season_share": (index["sources"] or {}).get("season_share"),
                   # THE CONSUMER'S RULE, stated on the payload rather than left
                   # to each consumer. bullpen_export.join_war_rate_3yr is the
                   # precedent: on a basis mismatch it BLANKS the columns rather
                   # than serving them beside a series they are not part of.
                   "war_basis_rule": ("A consumer must blank every eWAR column "
                                      "on this payload when war_provider or "
                                      "ewar_generated_at differ from the served "
                                      "basis, the way bullpen_export"
                                      ".join_war_rate_3yr blanks its columns "
                                      "rather than serving them stale."),
                   **block}
        path = out_dir / f"mlbstats_window_{key}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)
        log(f"  window lab: wrote {path.name} "
            f"({round(path.stat().st_size / 1024)} KB)")
    # A REFUSED WINDOW MUST NOT KEEP SERVING ITS LAST PAYLOAD. Only surviving
    # windows are written, so without this a window that went thin would vanish
    # from the index while its previous file stayed on disk, catalogued, and
    # fetchable by anyone who kept the URL.
    for spec in WINDOWS:
        if spec["key"] in windows:
            continue
        stale = out_dir / f"mlbstats_window_{spec['key']}.json"
        if stale.exists():
            stale.unlink()
            log(f"  window lab: removed {stale.name} - {spec['key']} was "
                f"refused ({index['windows_refused'].get(spec['key'])})")
    tmp = (out_dir / INDEX_PATH.name).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, indent=1), encoding="utf-8")
    tmp.replace(out_dir / INDEX_PATH.name)
    log(f"  window lab: wrote {INDEX_PATH.name} ({len(windows)} windows, "
        f"{index['build_seconds']}s)")
    # THE HEARTBEAT. SCHEDULED_EXPORTS' own comment says silence in the ledger
    # cannot tell "this step ran and found nothing" from "this step never ran",
    # and this lab files only on a total refusal. war_seasons gets its ok=True
    # free from guard_nonempty_block; this one has to file its own.
    try:
        import bullpen_export as be
        be.record_ingest("mlbstats_windows", ok=True, n_rows=len(windows),
                         message=("multi-year windows: "
                                  + ", ".join(sorted(windows))
                                  + (f"; refused {sorted(index['windows_refused'])}"
                                     if index["windows_refused"] else "")),
                         import_fallback=False)
    except Exception:                       # noqa: BLE001 - reporting is best effort
        pass
    return len(windows)


def main(argv: list) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    force = "--force" in argv
    seasons = [int(a) for a in argv if a.isdigit()]
    return 0 if export(seasons[0] if seasons else None, force=force) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
