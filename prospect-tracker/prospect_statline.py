# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The prospect arrival line (`prospect_statline`): projected first-three-season MLB
rates for a prospect, conditional on reaching the majors, plus WAR assembled through
LANE A's component framework on FanGraphs' frame. Built by TL_11_STATLINE_BUILD_DARK
to docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md (Plan Part 9 section 9.4.6
'Prospect stat-line projections'; LANE_C.md section 2.6), which this module follows
part by part. Class 2: nothing served reads it while
proj_export.SERVE_PROSPECT_STATLINE is False; TL_18_STATLINE_DISPLAY_FLIP turned it
on after the spent look (gate Part 13) and serve_doc / write_served write the served
file data/prospect_statline.json for the stats whose L1 verdict in
data/prospect_statline_eval.json is PASS (gate Part 12), from the fit the look scored.

THE UNIT (gate 2.1). One row per debuted player at his last snapshot strictly before
his MLB debut (efv_dataset._asof_point at efv_dataset.resolved_debut_date); the side
is the as-of side (efv_dataset._side_match); a player is his own cluster.

THE INPUTS (gate 1.1), each refit inside every fold on that fold's training cohorts:
  TIP_first   tool_implied tables (fit_tables on the training cohorts' MLB seasons at
              age 26 and over inside their windows, else their pooled first-three-season
              line when fewer than two bins survive) read at the consensus tool grade,
              plus the stat's age change to 27 through tool_implied.tip_first, a hook
              on aging_v3.AgingModel.component_curve with aging v2 (U3, U6)
  TIP_now     the same table at the FanGraphs present grade (its own input)
  translation college_translation._fit (the milb_translation estimator) from the final
              pre-debut level-relative K% and BB% to the first MLB season's rate
  level-relative ISO and BABIP   the final pre-debut MiLB season against its
              level-season mean on the ladder cache (milb_history), strictly pre-debut
  proxy       efv_proxy's estimator (StandardScaler + Ridge alpha 3.0 on the eFV
              feature vector) refit on the training cohorts' first-MLB est_woba
  age delta   the component curve's cumulative change from the arrival age to 27
  playing time   LANE A's framework rule for a player at arrival, recorded below

THE MODEL (gate 1.2). Per stat and side a stacked ridge: level 0 is the inputs above
as their own prediction of the stat where they have one; level 1 a ridge with an
intercept on the standardized level-0 values, rows weighted by pooled exposure, a
missing input at the training mean with a missing indicator, the penalty chosen by
nested forward-chained cross-validation on the grid 10 ** k, k = -3, -2.5, ... 3,
ties to the larger penalty. Bands (1.3): the point plus the 10th and 90th percentiles
of the inner chain's out-of-fold residuals. WAR (1.4): the point predictions and the
playing-time rule through proj_components.hitter_heads / pitcher_heads at the
constants of proj_components.season_constants(T - 1); never a sum of quantile points.

FRAMES. Development: debut cohorts 2017 to 2021, scored 2019, 2020 and 2021, each
fit on the strictly earlier cohorts (gate 3.1). Holdout H (2022 to 2024) is read once
by TL_17 through run_look; development mode raises on any 2022 or later debut. R-VM
(2025 and later, efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR) raises in every mode.
Nothing here groups, filters, bins or weights by consensus FV (docs/PROSPECT_ANCHOR_
GATE.md): the strata are side, debut age band, position group and last level.

Run: python prospect_statline.py --dev         (the one development read)
     python prospect_statline.py --dry-run     (the reporting path on fixtures)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LABS_DIR = DATA_DIR / "_labs"
DEV_PATH = LABS_DIR / "prospect_statline_dev.json"
EVAL_PATH = DATA_DIR / "prospect_statline_eval.json"
PREVIEW_DIR = ROOT / ".cache" / "prospect_statline" / "preview"
PREVIEW_PATH = PREVIEW_DIR / "prospect_statline.json"
GATE_DOC = ROOT / "docs" / "proj-prospect-2026-10" / "PROSPECT_STATLINE_GATE.md"
SAVANT_DIR = ROOT / ".cache" / "savant_mlb"
FRAME_NAME = "FanGraphs frame"

#: Development frame (gate 3.1) and holdout H (gate 3.2).
DEV_COHORTS: tuple[int, ...] = (2017, 2018, 2019, 2020, 2021)
DEV_TEST_YEARS: tuple[int, ...] = (2019, 2020, 2021)
HOLDOUT_COHORTS: tuple[int, ...] = (2022, 2023, 2024)
HOLDOUT_FIRST_DEBUT_YEAR = 2022
EARLIEST_COHORT = 2016          # the first Savant expected-stats season on disk
WINDOW_SEASONS = 3
MATURITY_AGE = 27
EXPOSURE_FLOOR = 150.0          # pooled PA or BF per rate (gate 2.2)
MIN_SCORED_ROWS = 4 * 15        # a stat under this is NOT COMPUTABLE (gate 5.5)
MIN_STRATUM_ROWS = 20
PENALTY_GRID = tuple(10.0 ** (k / 2.0) for k in range(-6, 7))      # 13 values
BOOT_B = 2000
BOOT_SEED = 20261210
HOLM_ALPHA = 0.05
COVERAGE_BAND = (0.75, 0.85)
SEASON_FLAGS = {2020: "60-game season inside the window"}

#: The served file (TL_18_STATLINE_DISPLAY_FLIP, gate Part 12) and its copy.
SERVED_PATH = DATA_DIR / "prospect_statline.json"
SERVED_HEADING = "If he reaches the majors, first three seasons"
STAT_LABEL = {"k_pct": "K%", "bb_pct": "BB%", "iso": "ISO", "avg": "AVG", "babip": "BABIP",
              "woba": "wOBA", "xwoba": "xwOBA", "hr_bf": "HR per BF"}
BASELINE_NAME = {"B0": "the league-average rookie line", "B1": "the translated minor league rate alone",
                 "B2": "the tool-implied value of his grade alone", "B3": "the xwOBA prior alone"}
SERVED_ROUND = 4

HIT_STATS = ("k_pct", "bb_pct", "iso", "avg", "babip", "woba", "xwoba")
PIT_STATS = ("k_pct", "bb_pct", "hr_bf", "babip", "xwoba")
STATS = {"hit": HIT_STATS, "pit": PIT_STATS}

#: Tool to stat, the framework table (TOOL_IMPLIED_PRODUCTION_GATE.md 1.1): the tool
#: whose table predicts the stat and the table's orientation.
TOOL_FOR_STAT = {
    "hit": {"k_pct": ("hit", -1), "avg": ("hit", 1), "babip": ("hit", 1), "iso": ("game_pwr", 1)},
    "pit": {"k_pct": ("fb", 1), "bb_pct": ("cmd", -1)},
}
#: The aging component a stat reads (aging_v3 v2 curves); absent means no age input.
AGE_COMP = {"hit": {"k_pct": "k_pct", "bb_pct": "bb_pct", "iso": "iso", "babip": "babip"},
            "pit": {"k_pct": "k_pct", "bb_pct": "bb_pct", "hr_bf": "hr_bf"}}
TRANSLATION_STATS = ("k_pct", "bb_pct")
PROXY_STATS = {"hit": ("xwoba", "woba"), "pit": ("xwoba",)}
LEVEL_REL_STATS = {"hit": {"iso": "iso_rel", "babip": "babip_rel"}, "pit": {}}
STRATA = ("side", "debut_age_band", "position_group", "last_level")
_STATS_RE = re.compile(r"\b20\d\d-\d\d-\d\d\b")


class ReservedFrameError(RuntimeError):
    """A read of R-VM (debut cohorts 2025 and later), refused in every mode."""


class HoldoutFrameError(RuntimeError):
    """A read of holdout H (debut cohorts 2022 to 2024) outside the one look."""


class LookRefused(RuntimeError):
    """The look's preconditions (gate Part 10) do not hold."""


def _f(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# guards (gate 1.6, 3.3, Part 11)
# ---------------------------------------------------------------------------

def guard_years(cohort_years, *, mode: str) -> None:
    """Raise before any read: R-VM in every mode; holdout H in development and
    preview mode (the look reads it once, through run_look)."""
    try:
        from efv_vintage_frame import R_VM_FIRST_DEBUT_YEAR
    except ImportError:                                        # pragma: no cover
        R_VM_FIRST_DEBUT_YEAR = 2025
    years = sorted({int(y) for y in cohort_years})
    rvm = [y for y in years if y >= R_VM_FIRST_DEBUT_YEAR]
    if rvm:
        raise ReservedFrameError(
            f"debut cohorts {rvm} are reserved (R-VM, from {R_VM_FIRST_DEBUT_YEAR}); "
            "prospect_statline never reads them in any mode")
    hold = [y for y in years if y >= HOLDOUT_FIRST_DEBUT_YEAR]
    if hold and mode != "look":
        raise HoldoutFrameError(
            f"debut cohorts {hold} are holdout H (gate 3.2), read once by TL_17's look; "
            f"mode {mode!r} may not read them")


def _check_cohorts(rows: list[dict], cohort_years) -> None:
    allowed = {int(y) for y in cohort_years}
    bad = sorted({r["debut_year"] for r in rows if r["debut_year"] not in allowed})
    if bad:
        raise RuntimeError(f"rows outside the requested cohorts: {bad}")


# ---------------------------------------------------------------------------
# realized lines (gate 2.2, 2.3): StatsAPI season caches, Savant, the frozen vintage
# ---------------------------------------------------------------------------

_HIT_COUNTS = {"pa": "plateAppearances", "ab": "atBats", "h": "hits", "d": "doubles",
               "t": "triples", "hr": "homeRuns", "bb": "baseOnBalls", "ibb": "intentionalWalks",
               "hbp": "hitByPitch", "sf": "sacFlies", "so": "strikeOuts", "g": "gamesPlayed"}
_PIT_COUNTS = {"bf": "battersFaced", "so": "strikeOuts", "bb": "baseOnBalls", "hr": "homeRuns",
               "h": "hits", "ab": "atBats", "sf": "sacFlies", "g": "gamesPlayed",
               "gs": "gamesStarted"}


def _innings(raw) -> float:
    try:
        from proj_components import innings
        return float(innings(raw))
    except Exception:                                          # pragma: no cover
        return _f(raw) or 0.0


@lru_cache(maxsize=None)
def season_lines(season: int, group: str) -> dict:
    """{mlbam: counts} for one season and group from the raw StatsAPI season cache,
    read inside scrapers.cache_only() (nothing fetched, nothing written). A repeated
    id resolves to its season total (saber_feed.resolve_groups); an id with no
    unique total is summed over its team rows (PROJ_COMPONENTS_GATE.md D1)."""
    import fa_sources
    import saber_feed
    import scrapers
    with scrapers.cache_only():
        splits = fa_sources.fetch_statsapi_season_stats(int(season), group)
    spec = _HIT_COUNTS if group == "hitting" else _PIT_COUNTS
    by_id: dict[int, list] = {}
    for s in splits or []:
        pid = (s.get("player") or {}).get("id")
        if pid is not None:
            by_id.setdefault(int(pid), []).append(s)
    resolved, ambiguous, _n = saber_feed.resolve_groups(splits or [])

    def one(stat: dict) -> dict:
        out = {k: (_f(stat.get(src)) or 0.0) for k, src in spec.items()}
        if group == "pitching":
            out["ip"] = _innings(stat.get("inningsPitched"))
        return out

    out = {int(pid): one(row.get("stat") or {}) for pid, row in resolved.items()}
    for pid in ambiguous:
        tot: dict[str, float] = {}
        for row in by_id[int(pid)]:
            for k, v in one(row.get("stat") or {}).items():
                tot[k] = tot.get(k, 0.0) + v
        out[int(pid)] = tot
    return out


@lru_cache(maxsize=None)
def savant_expected(season: int, side: str) -> dict:
    """{mlbam: (est_woba, pa)} from .cache/savant_mlb/expected_<side>_<season>.csv."""
    from mlb_player_export import _savant
    rows = _savant("expected", int(season), "pitcher" if side == "pit" else "batter")
    out = {}
    for r in rows:
        pid, w, pa = _f(r.get("player_id")), _f(r.get("est_woba")), _f(r.get("pa"))
        if pid is not None and w is not None and pa:
            out[int(pid)] = (w, pa)
    return out


def _woba_weights(season: int) -> dict | None:
    import league_constants as LC
    blk = LC.load().get(int(season)) or {}
    w = blk.get("woba_weights")
    return w if w and all(k in w for k in ("ubb", "hbp", "1b", "2b", "3b", "hr")) else None


def realized_line(mlbam: int, debut_year: int, side: str) -> dict:
    """The pooled first-three-season line (seasons D, D + 1, D + 2) of one player:
    {stat: (value, exposure)} with None where the rate cannot be formed, plus the
    pooled exposure, games and seasons present. A window season with no MLB line
    contributes nothing (gate 2.2)."""
    import fwar_frame as F
    seasons = [debut_year + k for k in range(WINDOW_SEASONS)]
    group = "pitching" if side == "pit" else "hitting"
    tot: dict[str, float] = {}
    present = []
    woba_num = woba_den = 0.0
    woba_seasons = 0
    xw_num = xw_pa = 0.0
    for s in seasons:
        line = season_lines(s, group).get(int(mlbam))
        if line:
            present.append(s)
            for k, v in line.items():
                tot[k] = tot.get(k, 0.0) + float(v)
            if side == "hit":
                w = _woba_weights(s)
                if w is not None:
                    num, den = F.woba_parts(line["bb"], line["ibb"], line["hbp"], line["h"],
                                            line["d"], line["t"], line["hr"], line["ab"],
                                            line["sf"], w)
                    woba_num += num
                    woba_den += den
                    woba_seasons += 1
        xw = savant_expected(s, side).get(int(mlbam))
        if xw:
            xw_num += xw[0] * xw[1]
            xw_pa += xw[1]
    out: dict = {"seasons_present": present, "first_season": None}
    first = season_lines(debut_year, group).get(int(mlbam))
    if side == "hit":
        pa = tot.get("pa", 0.0)
        ab = tot.get("ab", 0.0)
        out["exposure"] = pa
        out["g"] = tot.get("g", 0.0)
        out["k_pct"] = (tot["so"] / pa, pa) if pa > 0 else None
        out["bb_pct"] = (tot["bb"] / pa, pa) if pa > 0 else None
        tb = tot.get("h", 0.0) + tot.get("d", 0.0) + 2.0 * tot.get("t", 0.0) + 3.0 * tot.get("hr", 0.0)
        out["iso"] = ((tb - tot["h"]) / ab, pa) if ab > 0 else None
        out["avg"] = (tot["h"] / ab, pa) if ab > 0 else None
        bip = ab - tot.get("so", 0.0) - tot.get("hr", 0.0) + tot.get("sf", 0.0)
        out["babip"] = ((tot["h"] - tot["hr"]) / bip, pa) if bip > 0 else None
        out["woba"] = ((woba_num / woba_den, pa) if woba_den > 0 and woba_seasons == len(present)
                       and present else None)
        if first and first.get("pa", 0) > 0:
            out["first_season"] = {"k_pct": first["so"] / first["pa"],
                                   "bb_pct": first["bb"] / first["pa"], "g": first["g"]}
    else:
        bf = tot.get("bf", 0.0)
        ab = tot.get("ab", 0.0)
        out["exposure"] = bf
        out["g"] = tot.get("g", 0.0)
        out["gs"] = tot.get("gs", 0.0)
        out["ip"] = tot.get("ip", 0.0)
        out["k_pct"] = (tot["so"] / bf, bf) if bf > 0 else None
        out["bb_pct"] = (tot["bb"] / bf, bf) if bf > 0 else None
        out["hr_bf"] = (tot["hr"] / bf, bf) if bf > 0 else None
        bip = ab - tot.get("so", 0.0) - tot.get("hr", 0.0) + tot.get("sf", 0.0)
        out["babip"] = ((tot["h"] - tot["hr"]) / bip, bf) if bip > 0 else None
        if first and first.get("bf", 0) > 0:
            out["first_season"] = {"k_pct": first["so"] / first["bf"],
                                   "bb_pct": first["bb"] / first["bf"], "ip": first["ip"]}
    out["xwoba"] = (xw_num / xw_pa, xw_pa) if xw_pa > 0 else None
    return out


def realized_war(mlbam: int, debut_year: int, totals: dict) -> float:
    """First-three-season fWAR from the frozen vintage (gate 2.3): a window season
    with no row counts 0, so the label is bust-inclusive among debuts."""
    return float(sum(totals.get((int(mlbam), debut_year + k), 0.0) for k in range(WINDOW_SEASONS)))


# ---------------------------------------------------------------------------
# the as-of profile (gate 2.1, 1.1)
# ---------------------------------------------------------------------------

_IF = {"1B", "2B", "3B", "SS", "INF", "UTIL", "IF"}
_OF = {"OF", "LF", "CF", "RF"}
#: The fielded position the assembly prices for an as-of position (gate 1.4:
#: positional runs from the as-of position). A compound position takes its first
#: token; an outfielder with no corner named is priced as a corner (RF).
_FIELD_POS = {"C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS", "LF": "LF", "CF": "CF",
              "RF": "RF", "OF": "RF", "INF": "2B", "IF": "2B", "UTIL": "2B"}


def position_group(position: str | None, side: str) -> str:
    """The Part 7 position group from the as-of position."""
    import value_framework as vf
    if side == "pit":
        return "RP" if vf.is_reliever_position(position) else "SP"
    tok = (str(position or "").split("/")[0] or "").strip().upper()
    if tok == "C":
        return "C"
    if tok in _IF:
        return "IF"
    if tok in _OF:
        return "OF"
    if tok == "DH":
        return "DH"
    return "other"


def field_position(position: str | None) -> str | None:
    tok = (str(position or "").split("/")[0] or "").strip().upper()
    if tok == "DH":
        return None
    return _FIELD_POS.get(tok)


def age_band(age) -> str:
    a = _f(age)
    if a is None:
        return "unknown"
    a = int(math.floor(a))
    if a <= 21:
        return "21 or younger"
    if a <= 23:
        return "22 to 23"
    if a <= 25:
        return "24 to 25"
    return "26 or older"


def level_group(level: str | None) -> str:
    if level == "AAA":
        return "AAA"
    if level == "AA":
        return "AA"
    if level:
        return "A+ or below"
    return "none"


def whole_years(birth: str | None, at: str | None):
    try:
        b = date.fromisoformat(str(birth)[:10])
        d = date.fromisoformat(str(at)[:10])
    except (TypeError, ValueError):
        return None
    years = d.year - b.year - ((d.month, d.day) < (b.month, b.day))
    return years


@lru_cache(maxsize=None)
def _level_babip_mean(season: int, level: str, group: str):
    """The level-season mean BABIP on the ladder cache, exposure-filtered the way
    milb_history.league_norms filters (hitters at 100 PA, pitchers at 100 BF);
    None when fewer than 30 lines qualify. Read from disk only."""
    import milb_history as mh
    idx = mh.player_index(int(season), group, fetch=False)
    vals = []
    for rows in idx.values():
        for r in rows:
            if r.get("level") != level:
                continue
            if group == "hitting":
                pa = _f(r.get("pa")) or 0.0
                if pa < 100:
                    continue
                ab, h, hr = _f(r.get("ab")) or 0.0, _f(r.get("h")) or 0.0, _f(r.get("hr")) or 0.0
                so, sf = _f(r.get("so")) or 0.0, _f(r.get("sf")) or 0.0
                bip = ab - so - hr + sf
                if bip > 0:
                    vals.append((h - hr) / bip)
    if len(vals) < 30:
        return None
    vals.sort()
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def babip_rel(mlbam: int, season: int | None, level: str | None, group: str):
    """The player's final pre-debut level BABIP minus the level-season mean; None
    without the row or the norm. Hitters only."""
    if group != "hitting" or not season or not level:
        return None
    import milb_history as mh
    rows = [r for r in (mh.player_index(int(season), group, fetch=False).get(int(mlbam)) or [])
            if r.get("level") == level]
    if not rows:
        return None
    r = mh.level_row(rows, level, group) or rows[0]
    ab, h, hr = _f(r.get("ab")) or 0.0, _f(r.get("h")) or 0.0, _f(r.get("hr")) or 0.0
    so, sf = _f(r.get("so")) or 0.0, _f(r.get("sf")) or 0.0
    bip = ab - so - hr + sf
    norm = _level_babip_mean(int(season), level, group)
    if bip <= 0 or norm is None:
        return None
    return (h - hr) / bip - norm


def present_grades(point: dict | None) -> dict | None:
    """FanGraphs present grades at the as-of point (snapshots.tools_json
    _extras.present as the points carry it); None when FanGraphs had none."""
    fg = ((point or {}).get("per_source") or {}).get("fangraphs") or {}
    tools = fg.get("tools")
    if not isinstance(tools, dict):
        return None
    pres = (tools.get("_extras") or {}).get("present")
    return {k: _f(v) for k, v in pres.items() if _f(v) is not None} if isinstance(pres, dict) else None


def build_profiles(cohort_years, *, mode: str) -> tuple[list[dict], dict]:
    """One profile per debuted player of the cohorts (gate 2.1), with the as-of
    inputs and the realized outcomes. Returns (rows, accounting)."""
    guard_years(cohort_years, mode=mode)
    from efv_dataset import (_asof_point, _milb_features, _prior_features, _side_match,
                             resolved_debut_date)
    from efv_model import _feature_spec, _vec
    import fwar_vintage
    cohorts = {int(y) for y in cohort_years}
    debuts = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    if isinstance(debuts, dict):
        debuts = debuts.get("players") or []
    totals = fwar_vintage.season_totals(fwar_vintage.load())
    acct = {"debuts_in_cohorts": 0, "no_side": 0, "no_mlbam": 0, "no_asof_point": 0,
            "no_tool_grades": 0, "no_feature_vector": 0, "placeholder_debut_date": 0,
            "profiles": 0}
    rows = []
    for rec in debuts:
        dd, placeholder, _from = resolved_debut_date(rec)
        y = int(dd[:4]) if dd and str(dd)[:4].isdigit() else None
        if y is None or y not in cohorts:
            continue
        acct["debuts_in_cohorts"] += 1
        if y >= HOLDOUT_FIRST_DEBUT_YEAR and mode != "look":
            raise HoldoutFrameError(f"debut {y} inside a {mode} read")
        if placeholder:
            acct["placeholder_debut_date"] += 1
        side = "pit" if _side_match(rec, "pit") else ("hit" if _side_match(rec, "hit") else None)
        if side is None:
            acct["no_side"] += 1
            continue
        mlbam = rec.get("mlbam_id")
        if not mlbam:
            acct["no_mlbam"] += 1
            continue
        pt = _asof_point(rec, dd)
        if pt is None:
            acct["no_asof_point"] += 1
            continue
        tools = {k: _f(v) for k, v in (pt.get("tools_consensus") or {}).items() if _f(v) is not None}
        if not tools:
            acct["no_tool_grades"] += 1
        row = {"consensus_fv_raw": _f(pt.get("consensus_fv_raw")), "position": rec.get("position"),
               "birth_date": rec.get("birth_date")}
        row.update(_prior_features(rec, pt, side))
        milb = _milb_features(int(mlbam), y, rec.get("birth_date"), side, cutoff=dd) or {}
        row["milb"] = milb or None
        keys, _m = _feature_spec(side)
        try:
            vec = _vec(row, side)
            x = [float(vec[k]) for k in keys]
        except Exception:                                      # noqa: BLE001
            acct["no_feature_vector"] += 1
            x = None
        group = "pitching" if side == "pit" else "hitting"
        age = whole_years(rec.get("birth_date"), dd)
        if age is None and milb and _f(milb.get("age")) is not None and milb.get("milb_season"):
            # no birth date on the record: the ladder's age in the final pre-debut
            # season, carried forward to the debut year
            age = int(math.floor(_f(milb["age"]))) + (y - int(milb["milb_season"]))
        prof = {
            "player_key": rec.get("player_key"), "mlbam": int(mlbam), "side": side,
            "debut_year": y, "debut_date": dd, "birth_date": rec.get("birth_date"),
            "position": rec.get("position"),
            "position_group": position_group(rec.get("position"), side),
            "field_position": field_position(rec.get("position")) if side == "hit" else None,
            "arrival_age": age, "debut_age_band": age_band(age),
            "tools": tools, "present": present_grades(pt),
            "consensus_fv_raw": _f(pt.get("consensus_fv_raw")),
            "k_rel": _f(milb.get("k_rel")) if milb else None,
            "bb_rel": _f(milb.get("bb_rel")) if milb else None,
            "iso_rel": _f(milb.get("iso_rel")) if milb else None,
            "babip_rel": babip_rel(int(mlbam), milb.get("milb_season") if milb else None,
                                   milb.get("milb_level") if milb else None, group),
            "last_level": level_group(milb.get("milb_level") if milb else None),
            "proxy_x": x,
            "outcome": realized_line(int(mlbam), y, side),
            "war": realized_war(int(mlbam), y, totals),
        }
        rows.append(prof)
        acct["profiles"] += 1
    _check_cohorts(rows, cohort_years)
    return rows, acct


# ---------------------------------------------------------------------------
# input fits (gate 1.1), each on the training rows of one fold
# ---------------------------------------------------------------------------

def _window_age_rows(rows: list[dict], side: str, stat: str, min_age: int) -> list[dict]:
    """Per training player the stat pooled over the window seasons at which his
    age was `min_age` or more (the maturity frame), one value per player."""
    group = "pitching" if side == "pit" else "hitting"
    out = []
    for r in rows:
        if r["side"] != side or r["arrival_age"] is None:
            continue
        tool = TOOL_FOR_STAT[side][stat][0]
        g = r["tools"].get(tool)
        if g is None:
            continue
        tot: dict[str, float] = {}
        xw_num = xw_pa = 0.0
        for k in range(WINDOW_SEASONS):
            s = r["debut_year"] + k
            if r["arrival_age"] + k < min_age:
                continue
            line = season_lines(s, group).get(r["mlbam"])
            if line:
                for kk, v in line.items():
                    tot[kk] = tot.get(kk, 0.0) + float(v)
            xw = savant_expected(s, side).get(r["mlbam"])
            if xw:
                xw_num += xw[0] * xw[1]
                xw_pa += xw[1]
        v = _rate_from_counts(tot, stat, side, xw_num, xw_pa)
        if v is not None:
            out.append({"grade": g, "value": v[0], "id": r["player_key"],
                        "debut_year": r["debut_year"]})
    return out


def _rate_from_counts(tot: dict, stat: str, side: str, xw_num: float = 0.0, xw_pa: float = 0.0):
    if stat == "xwoba":
        return (xw_num / xw_pa, xw_pa) if xw_pa >= EXPOSURE_FLOOR else None
    expo = tot.get("pa" if side == "hit" else "bf", 0.0)
    if expo < EXPOSURE_FLOOR:
        return None
    ab = tot.get("ab", 0.0)
    if stat == "k_pct":
        return tot.get("so", 0.0) / expo, expo
    if stat == "bb_pct":
        return tot.get("bb", 0.0) / expo, expo
    if stat == "hr_bf":
        return tot.get("hr", 0.0) / expo, expo
    if stat == "avg":
        return (tot.get("h", 0.0) / ab, expo) if ab > 0 else None
    if stat == "iso":
        tb = tot.get("h", 0.0) + tot.get("d", 0.0) + 2.0 * tot.get("t", 0.0) + 3.0 * tot.get("hr", 0.0)
        return ((tb - tot.get("h", 0.0)) / ab, expo) if ab > 0 else None
    if stat == "babip":
        bip = ab - tot.get("so", 0.0) - tot.get("hr", 0.0) + tot.get("sf", 0.0)
        return ((tot.get("h", 0.0) - tot.get("hr", 0.0)) / bip, expo) if bip > 0 else None
    return None


def fit_tip_tables(train: list[dict], side: str) -> dict:
    """{stat: (TipTable, frame)} on the training rows: the maturity frame (window
    seasons at age 26 and over) where at least two bins survive, else the pooled
    first-three-season line (the full-season frame)."""
    import tool_implied as TI
    out = {}
    for stat, (tool, sign) in TOOL_FOR_STAT[side].items():
        mat = _window_age_rows(train, side, stat, MATURITY_AGE - 1)
        table = TI.fit_tables(mat, tool, stat, "maturity", sign=sign)
        frame = "maturity (window seasons at age 26 and over)"
        if len(table.knots) < 2:
            f3 = []
            for r in train:
                if r["side"] != side:
                    continue
                g = r["tools"].get(tool)
                o = r["outcome"].get(stat)
                if g is None or o is None or o[1] < EXPOSURE_FLOOR:
                    continue
                f3.append({"grade": g, "value": o[0], "id": r["player_key"],
                           "debut_year": r["debut_year"]})
            table = TI.fit_tables(f3, tool, stat, "f3", sign=sign)
            frame = "full-season (pooled first-three-season line)"
        out[stat] = (table, frame)
    return out


def fit_translation(train: list[dict], side: str) -> dict:
    """{stat: factor} the milb_translation estimator (college_translation._fit) from
    the final pre-debut level-relative rate to the FIRST MLB season's rate, at the
    served exposure gates (milb_translation.MIN_MLB_GAMES, MIN_MLB_IP)."""
    import college_translation as ct
    import milb_translation as MT
    out = {}
    for stat in TRANSLATION_STATS:
        xs, ys = [], []
        rel = "k_rel" if stat == "k_pct" else "bb_rel"
        for r in train:
            if r["side"] != side or r.get(rel) is None:
                continue
            fs = r["outcome"].get("first_season")
            if not fs or fs.get(stat) is None:
                continue
            if side == "pit":
                if (fs.get("ip") or 0.0) < MT.MIN_MLB_IP:
                    continue
            elif (fs.get("g") or 0.0) < MT.MIN_MLB_GAMES:
                continue
            xs.append(float(r[rel]))
            ys.append(float(fs[stat]))
        fac = ct._fit(xs, ys) if len(xs) >= 8 else None
        if fac:
            out[stat] = fac
    return out


def fit_proxy(train: list[dict], side: str):
    """efv_proxy's estimator (StandardScaler + Ridge alpha 3.0) refit on the training
    rows' first-MLB est_woba at efv_proxy.MIN_PA; None under 25 pairs."""
    import numpy as np
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    import efv_proxy as P
    X, y = [], []
    by_year: dict[int, dict] = {}
    for r in train:
        if r["side"] != side or r["proxy_x"] is None:
            continue
        tg = by_year.get(r["debut_year"])
        if tg is None:
            tg = by_year[r["debut_year"]] = P._pull_targets(r["debut_year"], side)
        t = tg.get(str(r["mlbam"]))
        if t is None:
            continue
        X.append(r["proxy_x"])
        y.append(float(t))
    if len(y) < 25:
        return None
    Xa = np.array(X)
    sc = StandardScaler().fit(Xa)
    rg = Ridge(alpha=3.0).fit(sc.transform(Xa), np.array(y))
    return {"scaler": sc, "ridge": rg, "n": len(y)}


def proxy_predict(fit, x):
    if fit is None or x is None:
        return None
    import numpy as np
    return float(fit["ridge"].predict(fit["scaler"].transform(np.array([x])))[0])


def age_delta(model, side: str, comp: str, bucket: str | None, arrival_age) -> float | None:
    """The cumulative component-curve change from the arrival age to 27, read the
    way tool_implied.tip_first reads the service (one definition, theirs)."""
    import tool_implied as TI
    a = _f(arrival_age)
    if a is None or model is None:
        return None
    try:
        curve = model.component_curve(side, comp, bucket)
    except KeyError:
        return None
    if not curve:
        return None
    a_int = int(round(a))
    d = 0.0
    if a_int < MATURITY_AGE:
        for age in range(a_int + 1, MATURITY_AGE + 1):
            d += TI._curve_value(curve, age)
    elif a_int > MATURITY_AGE:
        for age in range(MATURITY_AGE + 1, a_int + 1):
            d -= TI._curve_value(curve, age)
    return d


def _bucket(prof: dict) -> str:
    if prof["side"] == "pit":
        return prof["position_group"]
    return "C" if prof["position_group"] == "C" else "H"


def level0_inputs(prof: dict, fits: dict, side: str, stat: str) -> dict:
    """The level-0 values of one row for one stat: {name: value or None}."""
    import tool_implied as TI
    out: dict = {}
    tool = TOOL_FOR_STAT[side].get(stat)
    if tool is not None:
        table, _frame = fits["tip"][stat]
        g = prof["tools"].get(tool[0])
        comp = AGE_COMP[side].get(stat)
        if g is not None and table.computable:
            if comp is not None:
                first = TI.tip_first(table, g, prof["arrival_age"], side=side, comp=comp,
                                     bucket=_bucket(prof), model=fits["aging"])
                out["tip_first"] = first["value"]
            else:
                out["tip_first"] = table.read(g)
        else:
            out["tip_first"] = None
        pres = (prof.get("present") or {}).get(tool[0])
        out["tip_now"] = TI.tip_now(table, pres) if pres is not None and table.computable else None
    if stat in TRANSLATION_STATS:
        fac = fits["translation"].get(stat)
        rel = prof.get("k_rel" if stat == "k_pct" else "bb_rel")
        import college_translation as ct
        out["translation"] = ct._predict(fac, rel) if fac and rel is not None else None
    if stat in PROXY_STATS[side]:
        out["proxy"] = proxy_predict(fits["proxy"], prof.get("proxy_x"))
    rel_key = LEVEL_REL_STATS[side].get(stat)
    if rel_key is not None:
        out["level_rel"] = prof.get(rel_key)
    comp = AGE_COMP[side].get(stat)
    if comp is not None:
        out["age_delta"] = age_delta(fits["aging"], side, comp, _bucket(prof), prof["arrival_age"])
    return out


# ---------------------------------------------------------------------------
# the stacked ridge (gate 1.2) and its bands (1.3)
# ---------------------------------------------------------------------------

def _design(rows_x: list[dict], names: list[str], stats: dict | None):
    """Standardized level-0 columns plus a 0/1 missing indicator per input. `stats`
    (means, sds, from the training rows) is computed when None."""
    import numpy as np
    n, p = len(rows_x), len(names)
    raw = np.full((n, p), np.nan)
    for i, x in enumerate(rows_x):
        for j, k in enumerate(names):
            v = x.get(k)
            if v is not None and math.isfinite(float(v)):
                raw[i, j] = float(v)
    if stats is None:
        mu = np.nanmean(raw, axis=0) if n else np.zeros(p)
        mu = np.where(np.isnan(mu), 0.0, mu)
        sd = np.nanstd(raw, axis=0) if n else np.ones(p)
        sd = np.where(np.isnan(sd) | (sd <= 0), 1.0, sd)
        stats = {"mu": mu, "sd": sd}
    miss = np.isnan(raw).astype(float)
    z = np.where(np.isnan(raw), 0.0, (raw - stats["mu"]) / stats["sd"])
    return np.hstack([z, miss]), stats


def ridge_fit(X, y, w, lam: float) -> dict:
    """Weighted ridge with an unpenalized intercept: minimize sum w (y - b0 - x b)^2
    + lam |b|^2, on weighted-centred columns."""
    import numpy as np
    w = np.asarray(w, dtype=float)
    sw = w.sum()
    if sw <= 0 or len(y) == 0:
        return {"b0": float(np.mean(y)) if len(y) else 0.0, "b": np.zeros(X.shape[1])}
    xm = (w[:, None] * X).sum(axis=0) / sw
    ym = float((w * y).sum() / sw)
    if X.shape[1] == 0:
        return {"b0": ym, "b": np.zeros(0)}
    Xc = X - xm
    yc = y - ym
    A = Xc.T @ (w[:, None] * Xc) + lam * np.eye(X.shape[1])
    b = np.linalg.solve(A, Xc.T @ (w * yc))
    return {"b0": ym - float(xm @ b), "b": b}


def ridge_predict(fit: dict, X):
    return fit["b0"] + X @ fit["b"]


def _wmae(err, w) -> float | None:
    import numpy as np
    err = np.asarray(err, dtype=float)
    w = np.asarray(w, dtype=float)
    return float((w * np.abs(err)).sum() / w.sum()) if len(w) and w.sum() > 0 else None


def fit_stat_model(train: list[dict], side: str, stat: str, fits: dict) -> dict | None:
    """The level-1 ridge for one stat and side on the training rows: the penalty by
    nested forward-chained CV inside the training cohorts (the earliest training
    cohort is never an inner test year), bands from the inner chain's out-of-fold
    residuals at the chosen penalty."""
    import numpy as np
    rows = [r for r in train if r["side"] == side and r["outcome"].get(stat) is not None
            and r["outcome"][stat][1] >= EXPOSURE_FLOOR]
    if len(rows) < 8:
        return None
    xs = [level0_inputs(r, fits, side, stat) for r in rows]
    names = sorted({k for x in xs for k in x})
    y = np.array([r["outcome"][stat][0] for r in rows])
    w = np.array([r["outcome"][stat][1] for r in rows])
    years = np.array([r["debut_year"] for r in rows])
    inner_years = sorted({int(t) for t in years if any(years < t)})
    best_lam, best_mae, best_resid = None, None, []
    for lam in PENALTY_GRID:
        errs, ws, resid = [], [], []
        for t in inner_years:
            tr = years < t
            te = years == t
            if tr.sum() < 4 or te.sum() == 0:
                continue
            Xtr, st = _design([xs[i] for i in np.where(tr)[0]], names, None)
            Xte, _ = _design([xs[i] for i in np.where(te)[0]], names, st)
            f = ridge_fit(Xtr, y[tr], w[tr], lam)
            pred = ridge_predict(f, Xte)
            e = y[te] - pred
            errs.extend(e.tolist())
            ws.extend(w[te].tolist())
            resid.extend(e.tolist())
        mae = _wmae(errs, ws) if errs else None
        if mae is None:
            continue
        if best_mae is None or mae < best_mae - 1e-12 or abs(mae - best_mae) <= 1e-12:
            # a tie resolves to the larger penalty (the grid ascends)
            best_lam, best_mae, best_resid = lam, mae, resid
    if best_lam is None:
        best_lam = PENALTY_GRID[-1]
    X, st = _design(xs, names, None)
    f = ridge_fit(X, y, w, best_lam)
    if best_resid:
        q10, q90 = float(np.percentile(best_resid, 10)), float(np.percentile(best_resid, 90))
    else:
        q10 = q90 = 0.0
    return {"side": side, "stat": stat, "names": names, "stats": st, "fit": f, "lam": best_lam,
            "inner_mae": best_mae, "inner_years": inner_years, "n_train": len(rows),
            "n_inner_resid": len(best_resid), "q10": q10, "q90": q90,
            "coef": {k: float(v) for k, v in zip(names + [f"{n}_missing" for n in names], f["b"])},
            "intercept": float(f["b0"])}


def predict_stat(model: dict, prof: dict, fits: dict) -> dict | None:
    """{p50, p10, p90, inputs} for one profile; None without a model."""
    if model is None:
        return None
    x = level0_inputs(prof, fits, model["side"], model["stat"])
    X, _ = _design([x], model["names"], model["stats"])
    p = float(ridge_predict(model["fit"], X)[0])
    return {"p50": p, "p10": p + model["q10"], "p90": p + model["q90"], "inputs": x}


# ---------------------------------------------------------------------------
# baselines (gate Part 4)
# ---------------------------------------------------------------------------

def fit_b0(train: list[dict], side: str) -> dict:
    """B0: the exposure-weighted mean of each stat's pooled line over the training
    cohorts by side and position group, with the side mean as the fallback for a
    group the training cohorts do not carry."""
    out: dict = {}
    for stat in STATS[side]:
        num: dict[str, float] = {}
        den: dict[str, float] = {}
        for r in train:
            o = r["outcome"].get(stat)
            if r["side"] != side or o is None or o[1] < EXPOSURE_FLOOR:
                continue
            for key in (r["position_group"], "__side__"):
                num[key] = num.get(key, 0.0) + o[0] * o[1]
                den[key] = den.get(key, 0.0) + o[1]
        out[stat] = {k: num[k] / den[k] for k in num if den[k] > 0}
    return out


def eligible_baselines(side: str, stat: str) -> tuple[str, ...]:
    ids = ["B0"]
    if stat in TRANSLATION_STATS:
        ids.append("B1")
    if side == "hit" and stat in ("iso", "avg", "babip"):
        ids.append("B2")
    if stat == "xwoba":
        ids.append("B3")
    return tuple(ids)


def baseline_values(prof: dict, stat: str, fits: dict, side: str) -> dict:
    """{baseline id: prediction} of every baseline eligible for the stat (gate Part
    4). A baseline whose own input the row lacks (no MiLB rate, no tool grade, no
    feature vector) prices that row at B0, the league-average rookie line, so every
    baseline covers every scored row; `_fallback` lists the ids that did."""
    import college_translation as ct
    out: dict = {}
    b0 = fits["b0"].get(stat) or {}
    v = b0.get(prof["position_group"], b0.get("__side__"))
    if v is not None:
        out["B0"] = v
    if stat in TRANSLATION_STATS:
        fac = fits["translation"].get(stat)
        rel = prof.get("k_rel" if stat == "k_pct" else "bb_rel")
        if fac and rel is not None:
            out["B1"] = ct._predict(fac, rel)
    if side == "hit" and stat in ("iso", "avg", "babip"):
        import tool_implied as TI
        table, _frame = fits["tip"][stat]
        g = prof["tools"].get(TOOL_FOR_STAT[side][stat][0])
        comp = AGE_COMP[side].get(stat)
        if g is not None and table.computable:
            if comp is not None:
                out["B2"] = TI.tip_first(table, g, prof["arrival_age"], side=side, comp=comp,
                                         bucket=_bucket(prof), model=fits["aging"])["value"]
            else:
                out["B2"] = table.read(g)
    if stat == "xwoba":
        p = proxy_predict(fits["proxy"], prof.get("proxy_x"))
        if p is not None:
            out["B3"] = p
    fallback = []
    if "B0" in out:
        for bid in eligible_baselines(side, stat):
            if bid not in out:
                out[bid] = out["B0"]
                fallback.append(bid)
    out["_fallback"] = fallback
    return out


def inc_war(prof: dict) -> float | None:
    """INC: the served FV-anchored path, prospect_path._baseline_first3 at the as-of
    consensus FV (one continuous number, never binned) and the debut age."""
    import prospect_path
    fv = prof.get("consensus_fv_raw")
    if fv is None:
        return None
    age = None
    try:
        if prof.get("birth_date") and prof.get("debut_date"):
            b = date.fromisoformat(str(prof["birth_date"])[:10])
            age = round((date.fromisoformat(str(prof["debut_date"])[:10]) - b).days / 365.25, 1)
    except ValueError:
        age = None
    if age is None and prof.get("arrival_age") is not None:
        age = float(prof["arrival_age"])
    return prospect_path._baseline_first3(float(fv), prof["side"] == "pit", prof.get("position"), age)


# ---------------------------------------------------------------------------
# WAR through LANE A's assembly (gate 1.4, 1.5)
# ---------------------------------------------------------------------------

def playing_time_rule(train: list[dict]) -> dict:
    """The exposure rule for a player at arrival, recorded at the dev read (gate
    1.5): the training cohorts' mean pooled first-three-season PA (hitters) or BF
    and games (pitchers, by SP and RP), spread evenly over the three seasons; it
    never reads the scored player's own exposure."""
    out: dict = {}
    for side in ("hit", "pit"):
        groups: dict[str, list] = {}
        for r in train:
            if r["side"] != side:
                continue
            key = "H" if side == "hit" else r["position_group"]
            groups.setdefault(key, []).append(r)
        for key, rs in groups.items():
            n = len(rs)
            expo = sum(r["outcome"]["exposure"] for r in rs) / n
            g = sum(r["outcome"]["g"] for r in rs) / n
            out[f"{side}:{key}"] = {"n": n, "pooled_exposure": expo, "per_season": expo / WINDOW_SEASONS,
                                    "games_per_season": g / WINDOW_SEASONS}
    return out


def assembly_constants(season: int, corpus: dict) -> dict:
    """proj_components.season_constants at the last completed training season, the
    league wOBA anchor set to the feed's own lgwOBA (the scale the realized and
    projected wOBA here are on, not the engine corpus's)."""
    import proj_components as PC
    c = dict(PC.season_constants(int(season), corpus))
    if c.get("lg_woba_feed") is not None:
        c["eng_lg_woba"] = float(c["lg_woba_feed"])
    return c


def assemble_war(prof: dict, preds: dict, consts: dict, pt_rule: dict) -> dict | None:
    """First-three-season WAR from the POINT predictions through
    proj_components.hitter_heads / pitcher_heads (H0 to H8, P0 to P3) at PF 1.0.
    Baserunning and fielding, which the line does not project, enter at 0 runs,
    the value the assembly gives a player with no MLB history (listed in the
    heads' not_projected); positional runs from the as-of position. Never a sum
    of quantile points."""
    import proj_components as PC
    import fwar_frame as F
    side = prof["side"]
    key = f"{side}:{'H' if side == 'hit' else prof['position_group']}"
    pt = pt_rule.get(key)
    if pt is None:
        return None
    per = float(pt["per_season"])
    age = prof.get("arrival_age")
    if side == "hit":
        woba = (preds.get("woba") or {}).get("p50")
        if woba is None:
            return None
        pos = prof.get("field_position")
        inn = consts["inn_per_pa"] * per if pos else 0.0
        feat = {"pa_l1": per, "inn_total_l1": inn, "fielding_pa_l1": 0.0, "baseRunning_pa_l1": 0.0,
                "framing_pa_l1": None, "fld_missing_l1": False}
        for p in PC.FIELD_POSITIONS:
            feat[f"inn_{p}_l1"] = inn if p == pos else 0.0
        role = "C" if pos == "C" else "H"
        eng = {"role": role, "decay_role": role, "age": age, "pt_y1": per,
               "expo": [per] * WINDOW_SEASONS,
               "rates": [{"woba": woba, "wrc_plus": None}] * WINDOW_SEASONS, "proj": {}}
        heads = PC.hitter_heads(eng, feat, None, consts, None, horizon=WINDOW_SEASONS)
        lines = heads["lines"]
        war = sum(lines[h]["war_comp"] for h in lines if lines[h]["war_comp"] is not None)
        if any(lines[h]["war_comp"] is None for h in lines):
            return None
        return {"war": float(war), "components": {k: float(sum(lines[h][k] for h in lines))
                                                   for k in ("bat", "bsr", "fld", "pos", "lg", "rep")},
                "not_projected": heads["not_projected"], "pa": per * WINDOW_SEASONS}
    k = (preds.get("k_pct") or {}).get("p50")
    bb = (preds.get("bb_pct") or {}).get("p50")
    hr = (preds.get("hr_bf") or {}).get("p50")
    if k is None or bb is None or hr is None:
        return None
    ip = per / PC.BF_PER_IP
    fip = F.fip(hr * per, bb * per, 0.0, k * per, ip, consts["fip_constant"])
    if fip is None:
        return None
    g = float(pt["games_per_season"]) or 1.0
    role = prof["position_group"]
    gs_share = 1.0 if role == "SP" else 0.0
    feat = {"ip_l1": ip, "g_l1": g, "gs_l1": gs_share * g, "gs_share_l1": gs_share,
            "gmli_l1": None, "ra9gap_100ip_l1": None}
    eng = {"role": role, "decay_role": role, "age": age, "pt_y1": per,
           "expo": [per] * WINDOW_SEASONS, "rates": [{"fip": fip}] * WINDOW_SEASONS, "proj": {}}
    heads = PC.pitcher_heads(eng, feat, None, consts, horizon=WINDOW_SEASONS)
    lines = heads["lines"]
    if any(lines[h]["war_fip"] is None for h in lines):
        return None
    return {"war": float(sum(lines[h]["war_fip"] for h in lines)), "fip": float(fip),
            "not_projected": heads["not_projected"], "bf": per * WINDOW_SEASONS,
            "ip": ip * WINDOW_SEASONS}


# ---------------------------------------------------------------------------
# one fold: fit every input and model on the training rows, score the test rows
# ---------------------------------------------------------------------------

def fit_fold(train: list[dict], last_train_season: int, corpus: dict, *, aging_model=None) -> dict:
    """Every fitted input, baseline and model of one fold on `train` only."""
    import aging_v3
    if aging_model is None:
        aging_model = aging_v3.fitted(corpus, int(last_train_season))
    fits: dict = {"aging": aging_model, "last_train_season": int(last_train_season)}
    fits["pt_rule"] = playing_time_rule(train)
    fits["consts"] = assembly_constants(last_train_season, corpus)
    for key in ("tip", "translation", "proxy", "models", "b0"):
        fits[key] = {}
    for side in ("hit", "pit"):
        side_fits = {"aging": aging_model, "tip": fit_tip_tables(train, side),
                     "translation": fit_translation(train, side), "proxy": fit_proxy(train, side),
                     "b0": fit_b0(train, side)}
        for key in ("tip", "translation", "proxy", "b0"):
            fits[key][side] = side_fits[key]
        fits["models"][side] = {stat: fit_stat_model(train, side, stat, side_fits)
                                for stat in STATS[side]}
    return fits


def _side_fits(fits: dict, side: str) -> dict:
    return {key: fits[key][side] for key in ("tip", "translation", "proxy", "b0")} | {"aging": fits["aging"]}


def score_rows(test: list[dict], fits: dict) -> list[dict]:
    """Per test row: the predictions, the baselines, the assembled WAR and INC."""
    out = []
    for r in test:
        side = r["side"]
        sf = _side_fits(fits, side)
        preds = {stat: predict_stat(fits["models"][side].get(stat), r, sf) for stat in STATS[side]}
        bases = {stat: baseline_values(r, stat, sf, side) for stat in STATS[side]}
        war = assemble_war(r, preds, fits["consts"], fits["pt_rule"])
        out.append({"player_key": r["player_key"], "mlbam": r["mlbam"], "side": side,
                    "debut_year": r["debut_year"], "position_group": r["position_group"],
                    "debut_age_band": r["debut_age_band"], "last_level": r["last_level"],
                    "preds": preds, "baselines": bases, "outcome": r["outcome"],
                    "war_model": None if war is None else war["war"], "war_detail": war,
                    "war_inc": inc_war(r), "war_label": r["war"]})
    return out


# ---------------------------------------------------------------------------
# statistics (gate Parts 5, 6, 7)
# ---------------------------------------------------------------------------

def _draws(scored: list[dict], B: int, seed: int):
    """Row multiplicities of B player-clustered draws, resampled with replacement
    within each (side, debut cohort) group; the same draws serve every stat and
    both legs."""
    import numpy as np
    rng = np.random.default_rng(seed)
    groups: dict[tuple, list[int]] = {}
    for i, s in enumerate(scored):
        groups.setdefault((s["side"], s["debut_year"]), []).append(i)
    n = len(scored)
    counts = np.zeros((B, n), dtype=np.int32)
    for idx in groups.values():
        idx = np.asarray(idx)
        m = len(idx)
        pick = rng.integers(0, m, size=(B, m))
        for b in range(B):
            np.add.at(counts[b], idx[pick[b]], 1)
    return counts


def holm(pvals: dict, alpha: float = HOLM_ALPHA) -> dict:
    """{key: survives} by Holm step-down over the family."""
    items = sorted((p, k) for k, p in pvals.items() if p is not None)
    m = len(items)
    out = {k: False for k in pvals}
    for i, (p, k) in enumerate(items):
        if p <= alpha / (m - i):
            out[k] = True
        else:
            break
    return out


def _rankdata(xs):
    import prospect_path
    return prospect_path._rankdata(list(xs))


def within_spearman(pairs_by_group: dict) -> float | None:
    """The row-count-weighted mean of the within-(side, cohort) Spearman over groups
    of at least MIN_STRATUM_ROWS rows."""
    import prospect_path
    num = den = 0.0
    for g, pairs in pairs_by_group.items():
        if len(pairs) < MIN_STRATUM_ROWS:
            continue
        rho = prospect_path._spearman([p for p, _ in pairs], [o for _, o in pairs])
        if rho is None:
            continue
        num += rho * len(pairs)
        den += len(pairs)
    return num / den if den > 0 else None


def leg_l1(scored: list[dict], side: str, counts, B: int) -> dict:
    """Per stat: MAE of the model and of the best baseline on identical rows, d,
    its one-sided lower bound, p, coverage; Holm within the side's family."""
    import numpy as np
    out: dict = {}
    pvals: dict = {}
    for stat in STATS[side]:
        rows = [(i, s) for i, s in enumerate(scored)
                if s["side"] == side and s["preds"].get(stat) is not None
                and s["outcome"].get(stat) is not None and s["outcome"][stat][1] >= EXPOSURE_FLOOR]
        n = len(rows)
        entry: dict = {"n": n, "side": side, "stat": stat}
        if n < MIN_SCORED_ROWS:
            entry["verdict"] = "NOT COMPUTABLE"
            entry["note"] = f"fewer than {MIN_SCORED_ROWS} scored rows"
            out[stat] = entry
            continue
        idx = np.array([i for i, _ in rows])
        y = np.array([s["outcome"][stat][0] for _, s in rows])
        w = np.array([s["outcome"][stat][1] for _, s in rows])
        p50 = np.array([s["preds"][stat]["p50"] for _, s in rows])
        lo = np.array([s["preds"][stat]["p10"] for _, s in rows])
        hi = np.array([s["preds"][stat]["p90"] for _, s in rows])
        model_mae = _wmae(y - p50, w)
        base_ids = sorted({b for _, s in rows for b in s["baselines"][stat] if b != "_fallback"})
        base_mae = {}
        base_err = {}
        fallback_n = {}
        for bid in base_ids:
            if not all(bid in s["baselines"][stat] for _, s in rows):
                continue
            bv = np.array([s["baselines"][stat][bid] for _, s in rows])
            base_mae[bid] = _wmae(y - bv, w)
            base_err[bid] = y - bv
            fallback_n[bid] = sum(1 for _, s in rows if bid in (s["baselines"][stat].get("_fallback") or []))
        entry.update({"mae_model": model_mae, "mae_baselines": base_mae,
                      "baseline_rows_priced_at_b0": fallback_n})
        if not base_mae:
            entry["verdict"] = "NOT COMPUTABLE"
            entry["note"] = "no baseline covers every scored row"
            out[stat] = entry
            continue
        best = min(base_mae, key=lambda b: (base_mae[b], b))
        d = base_mae[best] - model_mae
        em = np.abs(y - p50)
        eb = np.abs(base_err[best])
        ds = []
        for b in range(B):
            c = counts[b, idx] * w
            sc = c.sum()
            if sc <= 0:
                continue
            ds.append(float(((c * eb).sum() - (c * em).sum()) / sc))
        ds = np.array(ds)
        lb = float(np.percentile(ds, 5)) if len(ds) else None
        ub = float(np.percentile(ds, 95)) if len(ds) else None
        p = (1 + int((ds <= 0).sum())) / (len(ds) + 1) if len(ds) else None
        cov = float(np.mean((y >= lo) & (y <= hi)))
        entry.update({"best_baseline": best, "mae_best_baseline": base_mae[best], "d": d,
                      "d_lb95": lb, "d_ub95": ub, "p_one_sided": p, "coverage_p10_p90": cov,
                      "n_draws": int(len(ds))})
        pvals[stat] = p
        out[stat] = entry
    surv = holm(pvals)
    for stat, entry in out.items():
        if entry.get("verdict") == "NOT COMPUTABLE":
            continue
        entry["holm_survives"] = bool(surv.get(stat))
        cov_ok = COVERAGE_BAND[0] <= entry["coverage_p10_p90"] <= COVERAGE_BAND[1]
        entry["coverage_veto"] = not cov_ok
        if entry["d_lb95"] is not None and entry["d_lb95"] > 0 and entry["holm_survives"] and cov_ok:
            entry["verdict"] = "PASS"
        elif entry["d_ub95"] is not None and entry["d_ub95"] < 0:
            entry["verdict"] = "LOSS"
        else:
            entry["verdict"] = "NULL"
    return out


def leg_l2(scored: list[dict], counts, B: int) -> dict:
    """WAR: the model against INC on identical debuted rows (MAE, within Spearman,
    calibration slope), with the draws' lower bounds."""
    import numpy as np
    import prospect_path
    rows = [(i, s) for i, s in enumerate(scored)
            if s["war_model"] is not None and s["war_inc"] is not None]
    n = len(rows)
    out: dict = {"n": n}
    if n < MIN_SCORED_ROWS:
        out["verdict"] = "NOT COMPUTABLE"
        return out
    idx = np.array([i for i, _ in rows])
    y = np.array([s["war_label"] for _, s in rows])
    pm = np.array([s["war_model"] for _, s in rows])
    pi = np.array([s["war_inc"] for _, s in rows])
    em, ei = np.abs(y - pm), np.abs(y - pi)
    out["mae_model"] = float(em.mean())
    out["mae_inc"] = float(ei.mean())
    out["d_mae"] = out["mae_inc"] - out["mae_model"]

    def groups(sel_counts=None):
        gm: dict = {}
        gi: dict = {}
        for j, (i, s) in enumerate(rows):
            reps = 1 if sel_counts is None else int(sel_counts[i])
            for _ in range(reps):
                gm.setdefault((s["side"], s["debut_year"]), []).append((pm[j], y[j]))
                gi.setdefault((s["side"], s["debut_year"]), []).append((pi[j], y[j]))
        return within_spearman(gm), within_spearman(gi)

    rho_m, rho_i = groups()
    out["rho_model"], out["rho_inc"] = rho_m, rho_i
    out["d_rho"] = None if rho_m is None or rho_i is None else rho_m - rho_i
    out["slope_model"] = (prospect_path._calibration(pm.tolist(), y.tolist()) or {}).get("slope")
    out["slope_inc"] = (prospect_path._calibration(pi.tolist(), y.tolist()) or {}).get("slope")
    d_mae, d_rho = [], []
    for b in range(B):
        c = counts[b, idx]
        sc = c.sum()
        if sc <= 0:
            continue
        d_mae.append(float(((c * ei).sum() - (c * em).sum()) / sc))
        rm, ri = groups(counts[b])
        if rm is not None and ri is not None:
            d_rho.append(rm - ri)
    out["d_mae_lb95"] = float(np.percentile(d_mae, 5)) if d_mae else None
    out["d_rho_lb95"] = float(np.percentile(d_rho, 5)) if d_rho else None
    out["n_draws_rho"] = len(d_rho)
    slope_ok = (out["slope_model"] is not None and out["slope_inc"] is not None
                and abs(out["slope_model"] - 1.0) <= abs(out["slope_inc"] - 1.0))
    if (out["d_mae_lb95"] is not None and out["d_mae_lb95"] > 0
            and out["d_rho_lb95"] is not None and out["d_rho_lb95"] > 0 and slope_ok):
        out["verdict"] = "PASS"
    else:
        out["verdict"] = "INC retains"
    return out


def strata(scored: list[dict]) -> dict:
    """Side, debut age band, position group and last level (gate Part 7): n per
    stratum, the model's and the best baseline's MAE per stat where n reaches
    MIN_STRATUM_ROWS, never adjudicated."""
    out: dict = {}
    for key in STRATA:
        out[key] = {}
        values = sorted({str(s[key]) for s in scored})
        for v in values:
            rows = [s for s in scored if str(s[key]) == v]
            cell: dict = {"n": len(rows)}
            if len(rows) >= MIN_STRATUM_ROWS:
                for side in ("hit", "pit"):
                    for stat in STATS[side]:
                        rs = [s for s in rows if s["side"] == side and s["preds"].get(stat)
                              and s["outcome"].get(stat) and s["outcome"][stat][1] >= EXPOSURE_FLOOR]
                        if len(rs) < MIN_STRATUM_ROWS:
                            continue
                        y = [s["outcome"][stat][0] for s in rs]
                        w = [s["outcome"][stat][1] for s in rs]
                        p = [s["preds"][stat]["p50"] for s in rs]
                        b0 = [s["baselines"][stat].get("B0") for s in rs]
                        cell[f"{side}:{stat}"] = {
                            "n": len(rs), "mae_model": _wmae([a - b for a, b in zip(y, p)], w),
                            "mae_b0": (_wmae([a - b for a, b in zip(y, b0)], w)
                                       if all(b is not None for b in b0) else None)}
                wr = [s for s in rows if s["war_model"] is not None and s["war_inc"] is not None]
                if len(wr) >= MIN_STRATUM_ROWS:
                    cell["war"] = {"n": len(wr),
                                   "mae_model": sum(abs(s["war_label"] - s["war_model"]) for s in wr) / len(wr),
                                   "mae_inc": sum(abs(s["war_label"] - s["war_inc"]) for s in wr) / len(wr)}
            out[key][v] = cell
    return out


def report(scored: list[dict], *, B: int = BOOT_B, seed: int = BOOT_SEED) -> dict:
    """Legs L1 and L2 and the strata on scored rows (the whole reporting path)."""
    counts = _draws(scored, B, seed)
    return {"l1": {side: leg_l1(scored, side, counts, B) for side in ("hit", "pit")},
            "l2": leg_l2(scored, counts, B), "strata": strata(scored),
            "bootstrap": {"B": B, "seed": seed, "clusters": "player within (side, debut cohort)"}}


# ---------------------------------------------------------------------------
# the development read (gate 1.7, 3.1)
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def input_hashes(cohort_years) -> dict:
    out = {"data/debuts.json": _sha256(DATA_DIR / "debuts.json"),
           "data/fwar_vintage.json": _sha256(DATA_DIR / "fwar_vintage.json"),
           "data/league_constants.json": _sha256(DATA_DIR / "league_constants.json")}
    for m in ("prospect_statline.py", "tool_implied.py", "aging_v3.py", "proj_components.py",
              "fwar_frame.py", "efv_proxy.py", "efv_dataset.py", "efv_model.py",
              "college_translation.py", "milb_translation.py", "milb_history.py", "prospect_path.py"):
        out[m] = _sha256(ROOT / m)
    seasons = sorted({int(y) + k for y in cohort_years for k in range(WINDOW_SEASONS)})
    for s in seasons:
        for g in ("hitting", "pitching"):
            out[f".cache/fa_statsapi_{g}_{s}.json"] = _sha256(ROOT / ".cache" / f"fa_statsapi_{g}_{s}.json")
        for side in ("batter", "pitcher"):
            out[f".cache/savant_mlb/expected_{side}_{s}.csv"] = _sha256(SAVANT_DIR / f"expected_{side}_{s}.csv")
    return out


def _fold_receipt(fits: dict, test_year: int, train: list[dict]) -> dict:
    rec: dict = {"test_year": test_year, "train_cohorts": sorted({r["debut_year"] for r in train}),
                 "train_n": len(train), "last_train_season": fits["last_train_season"],
                 "penalties": {}, "tip_frames": {}, "translation": {}, "proxy_n": {},
                 "playing_time": fits["pt_rule"],
                 "assembly_constants": {k: v for k, v in fits["consts"].items() if k != "receipt"}}
    for side in ("hit", "pit"):
        for stat, m in fits["models"][side].items():
            rec["penalties"][f"{side}:{stat}"] = (None if m is None else
                                                  {"lambda": m["lam"], "inner_mae": m["inner_mae"],
                                                   "inner_years": m["inner_years"], "n_train": m["n_train"],
                                                   "inputs": m["names"], "coef": m["coef"],
                                                   "intercept": m["intercept"],
                                                   "band_q10": m["q10"], "band_q90": m["q90"]})
        for stat, (table, frame) in fits["tip"][side].items():
            rec["tip_frames"][f"{side}:{stat}"] = {"frame": frame, "n_rows": table.n_rows,
                                                   "knots": list(table.knots), "values": list(table.values)}
        rec["translation"][side] = fits["translation"][side]
        rec["proxy_n"][side] = None if fits["proxy"][side] is None else fits["proxy"][side]["n"]
    flagged = sorted(set(rec["train_cohorts"]) & set(SEASON_FLAGS))
    if test_year in SEASON_FLAGS or flagged:
        rec["season_flag"] = SEASON_FLAGS[2020]
    return rec


def run_frame(cohort_years, test_years, *, mode: str, B: int = BOOT_B, seed: int = BOOT_SEED,
              corpus=None) -> dict:
    """Forward-chained: each test year fit on the cohorts strictly earlier (development),
    or every holdout cohort together on the training cohorts (look)."""
    guard_years(cohort_years, mode=mode)
    import fa_projection as fp
    corpus = corpus or fp.build_corpus()
    rows, acct = build_profiles(cohort_years, mode=mode)
    scored: list[dict] = []
    folds = []
    if mode == "look":
        train = [r for r in rows if r["debut_year"] < min(test_years)]
        test = [r for r in rows if r["debut_year"] in set(test_years)]
        fits = fit_fold(train, min(test_years) - 1, corpus)
        scored.extend(score_rows(test, fits))
        folds.append(_fold_receipt(fits, min(test_years), train))
    else:
        for t in sorted(int(y) for y in test_years):
            train = [r for r in rows if r["debut_year"] < t]
            test = [r for r in rows if r["debut_year"] == t]
            if not train or not test:
                continue
            fits = fit_fold(train, t - 1, corpus)
            scored.extend(score_rows(test, fits))
            folds.append(_fold_receipt(fits, t, train))
    rep = report(scored, B=B, seed=seed)
    rep["folds"] = folds
    rep["accounting"] = acct
    rep["n_scored_rows"] = len(scored)
    rep["per_fold_n"] = {str(t): sum(1 for s in scored if s["debut_year"] == t)
                         for t in sorted({s["debut_year"] for s in scored})}
    rep["rows"] = [{"player_key": s["player_key"], "side": s["side"], "debut_year": s["debut_year"],
                    "preds": {k: (None if v is None else {kk: v[kk] for kk in ("p50", "p10", "p90")})
                              for k, v in s["preds"].items()},
                    "outcome": {k: v for k, v in s["outcome"].items()
                                if k in STATS[s["side"]] and v is not None},
                    "war_model": s["war_model"], "war_inc": s["war_inc"], "war_label": s["war_label"]}
                   for s in scored]
    return rep


def run_dev(persist: bool = True, B: int = BOOT_B) -> dict:
    """THE ONE development read (gate 1.7): debut cohorts 2017 to 2021, scored 2019,
    2020 and 2021 forward-chained; writes data/_labs/prospect_statline_dev.json
    with role development. Decides nothing (gate 0.1)."""
    rep = run_frame(DEV_COHORTS, DEV_TEST_YEARS, mode="dev", B=B)
    doc = {
        "role": "development",
        "task": "TL_11_STATLINE_BUILD_DARK",
        "module": "prospect_statline.py",
        "gate": "docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md",
        "frame": FRAME_NAME,
        "generated": date.today().isoformat(),
        "cohort_years": list(DEV_COHORTS), "test_years": list(DEV_TEST_YEARS),
        "label": "first-three-season fWAR from the frozen vintage (fwar_vintage.season_totals), "
                 "a window season with no row counts 0 (bust-inclusive among debuts)",
        "stats": {"hit": list(HIT_STATS), "pit": list(PIT_STATS)},
        "exposure_floor": EXPOSURE_FLOOR,
        "penalty_grid": list(PENALTY_GRID),
        "aging": "aging_v3.fitted(corpus, T - 1) per fold, aging v2 component curves (U3, U6); "
                 "no served curves file exists, so the point-in-time fit stands in for 'as served'",
        "missing_input_rule": "a missing level-0 input enters at the training mean (0 after "
                              "standardization) with a 0/1 missing indicator column",
        "playing_time_rule": "the training cohorts' mean pooled first-three-season PA (hitters) or "
                             "BF and games (pitchers by SP and RP), evenly over the three seasons; "
                             "the scored player's own exposure is never read",
        "assembly": "proj_components.hitter_heads / pitcher_heads at season_constants(T - 1) with "
                    "the feed lgwOBA as the wOBA anchor, PF 1.0, no framing charge, baserunning and "
                    "fielding at 0 runs (not projected), positional runs from the as-of position, "
                    "pitcher FIP from the projected K%, BB% and HR per BF with HBP at 0",
        "survivorship": "Debuts only: every number is accuracy among players who reached the majors, "
                        "conditional on reaching MLB, not accuracy over all prospects.",
        "season_flags": {str(k): v for k, v in SEASON_FLAGS.items()},
        "frames": "Development cohorts 2017 to 2021 only (spent, gate 0.1). Holdout H (2022 to "
                  "2024) and R-VM (2025 and later) are never read here. No statistic is cut by "
                  "consensus-FV cell.",
        "decides": "nothing: the development read re-reads spent cohorts; only holdout H (TL_17) "
                   "carries a verdict",
        "inputs_sha256": input_hashes(DEV_COHORTS),
        "results": rep,
    }
    if persist:
        LABS_DIR.mkdir(parents=True, exist_ok=True)
        DEV_PATH.write_text(json.dumps(doc, indent=1, default=_json_default) + "\n", encoding="utf-8")
        log.info("wrote %s", DEV_PATH)
    return doc


def _json_default(o):
    try:
        import numpy as np
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:                                        # pragma: no cover
        pass
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    if hasattr(o, "to_dict"):
        return o.to_dict()
    return str(o)


# ---------------------------------------------------------------------------
# the look (TL_17; gate Part 9 and Part 10) - refused until its preconditions hold
# ---------------------------------------------------------------------------

def freeze_recorded(text: str | None = None) -> bool:
    """True when the gate document carries the dev-read freeze (1.7) amendment."""
    if text is None:
        try:
            text = GATE_DOC.read_text(encoding="utf-8")
        except OSError:
            return False
    return bool(re.search(r"^#+ .*development-read freeze.*$", text, flags=re.M | re.I))


def look_spent(eval_path: Path = EVAL_PATH, text: str | None = None) -> bool:
    if Path(eval_path).exists():
        return True
    if text is None:
        try:
            text = GATE_DOC.read_text(encoding="utf-8")
        except OSError:
            return False
    m = re.search(r"^## Part 13\. Results[^\n]*\n(.*)", text, flags=re.M | re.S)
    body = m.group(1) if m else ""
    return any(line.startswith("###") and _STATS_RE.search(line) and "look" in line.lower()
               for line in body.splitlines())


def run_look(gate_sha: str | None, *, dry_run_done: bool = False, persist: bool = False) -> dict:
    """The holdout read, once, by TL_17. Refuses without the REGISTERED gate sha, the
    1.7 freeze, a dry run and a clean spent check (gate 1.6, Part 10)."""
    from efv_vintage_frame import gate_sha_committed
    if not gate_sha or not gate_sha_committed(gate_sha):
        raise LookRefused("the look needs the sha of the commit carrying the gate at REGISTERED")
    if not freeze_recorded():
        raise LookRefused("the dev-read freeze (gate 1.7) is not recorded")
    if look_spent():
        raise LookRefused("the look is spent (a Part 13 entry or data/prospect_statline_eval.json exists)")
    if not dry_run_done:
        raise LookRefused("run the dry run first (python prospect_statline.py --dry-run)")
    guard_years(HOLDOUT_COHORTS, mode="look")
    years = tuple(y for y in range(EARLIEST_COHORT, HOLDOUT_FIRST_DEBUT_YEAR)) + HOLDOUT_COHORTS
    rep = run_frame(years, HOLDOUT_COHORTS, mode="look")
    rep["role"] = "look"
    rep["inputs_sha256"] = input_hashes(years)
    if persist:
        EVAL_PATH.write_text(json.dumps(rep, indent=1, default=_json_default) + "\n", encoding="utf-8")
    return rep


# ---------------------------------------------------------------------------
# the dry run (gate Part 10 item 2): the reporting path on fixtures carrying None
# ---------------------------------------------------------------------------

def fixture_rows(n: int = 240, seed: int = 7) -> list[dict]:
    """Synthetic scored rows with None values scattered through them; reads no
    real row."""
    import random
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        side = "hit" if i % 3 else "pit"
        stats = STATS[side]
        preds, bases, outcome = {}, {}, {"exposure": 400.0, "g": 100.0}
        for stat in stats:
            if rng.random() < 0.1:
                preds[stat] = None
                outcome[stat] = None
                bases[stat] = {}
                continue
            p = rng.uniform(0.05, 0.35)
            preds[stat] = {"p50": p, "p10": p - 0.05, "p90": p + 0.05, "inputs": {}}
            outcome[stat] = (p + rng.gauss(0, 0.04), 200.0 + rng.random() * 600)
            bases[stat] = {"B0": 0.2, "B1": p + rng.gauss(0, 0.05)} if rng.random() < 0.8 else {"B0": 0.2}
        rows.append({"player_key": f"fixture_{i}", "mlbam": i, "side": side,
                     "debut_year": 2017 + (i % 3), "position_group": "IF" if side == "hit" else "SP",
                     "debut_age_band": "22 to 23", "last_level": "AAA", "preds": preds,
                     "baselines": bases, "outcome": outcome,
                     "war_model": None if rng.random() < 0.1 else rng.uniform(0, 6),
                     "war_detail": None, "war_inc": None if rng.random() < 0.1 else rng.uniform(0, 6),
                     "war_label": rng.uniform(-1, 8)})
    return rows


def dry_run(B: int = 200) -> dict:
    """The whole reporting path on fixtures with None values; writes nothing."""
    rep = report(fixture_rows(), B=B, seed=BOOT_SEED)
    json.dumps(rep, default=_json_default)
    return rep


# ---------------------------------------------------------------------------
# the dark preview (gate Part 12): fields for the served prospects, under .cache only
# ---------------------------------------------------------------------------

def _live_profiles(prospect_keys) -> list[dict]:
    """Profiles of the served prospects from the live eFV matrices (tools, the MiLB
    block, the proxy feature vector) and the timeseries points (FanGraphs present
    grades); arrival age = age now plus the eFV ETA years."""
    from efv_dataset import live_matrix_path
    from efv_model import _feature_spec, _vec
    keys = None if prospect_keys is None else set(prospect_keys)
    try:
        ts = json.loads((DATA_DIR / "timeseries.json").read_text(encoding="utf-8")).get("players") or []
    except (OSError, ValueError):
        ts = []
    latest_point = {}
    for p in ts:
        if p.get("player_key") and (keys is None or p.get("player_key") in keys):
            pts = [q for q in (p.get("points") or []) if q.get("snapshot_date")]
            if pts:
                latest_point[p["player_key"]] = max(pts, key=lambda q: q["snapshot_date"])
    out = []
    for side in ("hit", "pit"):
        try:
            rows = json.loads(live_matrix_path(side).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        fkeys, _m = _feature_spec(side)
        for r in rows:
            pk = r.get("player_key")
            if pk is None or (keys is not None and pk not in keys):
                continue
            tools = {k[5:]: _f(v) for k, v in r.items() if k.startswith("tool_") and _f(v) is not None}
            milb = r.get("milb") or {}
            try:
                vec = _vec(r, side)
                x = [float(vec[k]) for k in fkeys]
            except Exception:                                  # noqa: BLE001
                x = None
            age_now, eta = _f(r.get("age_now")), _f(r.get("eta_years"))
            arrival = None if age_now is None else int(math.floor(age_now + max(0.0, eta or 0.0)))
            group = "pitching" if side == "pit" else "hitting"
            out.append({
                "player_key": pk, "mlbam": r.get("mlbam_id"), "side": side, "debut_year": None,
                "position": r.get("position"), "position_group": position_group(r.get("position"), side),
                "field_position": field_position(r.get("position")) if side == "hit" else None,
                "arrival_age": arrival, "debut_age_band": age_band(arrival),
                "tools": tools, "present": present_grades(latest_point.get(pk)),
                "k_rel": _f(milb.get("k_rel")), "bb_rel": _f(milb.get("bb_rel")),
                "iso_rel": _f(milb.get("iso_rel")),
                "babip_rel": (babip_rel(int(r["mlbam_id"]), milb.get("milb_season"),
                                        milb.get("milb_level"), group) if r.get("mlbam_id") else None),
                "last_level": level_group(milb.get("milb_level")), "proxy_x": x,
            })
    return out


def preview(prospect_keys, *, corpus=None) -> dict:
    """{player_key: {stat: {p50, p10, p90}}} for the served prospects from the model
    fit on the development cohorts (2017 to 2021), the frozen specification. Reads
    no holdout and no R-VM row; the served payload is never touched."""
    import fa_projection as fp
    corpus = corpus or fp.build_corpus()
    train, _acct = build_profiles(DEV_COHORTS, mode="dev")
    fits = fit_fold(train, max(DEV_COHORTS), corpus)
    out = {}
    for prof in _live_profiles(prospect_keys):
        side = prof["side"]
        sf = _side_fits(fits, side)
        line = {}
        for stat in STATS[side]:
            p = predict_stat(fits["models"][side].get(stat), prof, sf)
            if p is not None:
                line[stat] = {k: round(p[k], 4) for k in ("p50", "p10", "p90")}
        if line:
            out[prof["player_key"]] = {"side": side, "line": line}
    return {"generated_at": date.today().isoformat(), "role": "preview, dark",
            "frame": FRAME_NAME, "fit_cohorts": list(DEV_COHORTS),
            "label": "If he reaches the majors, first three seasons (conditional on reaching MLB)",
            "n_rows": len(out), "rows": out}


def write_preview(prospect_keys, path: Path | None = None) -> Path:
    path = Path(path) if path else PREVIEW_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = preview(prospect_keys)
    path.write_text(json.dumps(doc, indent=1, default=_json_default) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# the served file (TL_18_STATLINE_DISPLAY_FLIP, gate Part 12)
# ---------------------------------------------------------------------------

def look_passes(eval_doc: dict | None = None) -> dict:
    """{side: {stat: L1 entry}} for the stats whose L1 verdict in the spent look is
    PASS. Read from the artifact, never typed: a NULL, a LOSS or a coverage veto is
    not in it, and the WAR leg (L2) is not read at all (gate Part 12)."""
    doc = eval_doc if eval_doc is not None else json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    if doc.get("role") != "look" or not doc.get("spent"):
        raise LookRefused("the served stat line reads the spent look's artifact (role look, spent true)")
    l1 = (doc.get("results") or {}).get("l1") or {}
    return {side: {stat: e for stat, e in (l1.get(side) or {}).items() if e.get("verdict") == "PASS"}
            for side in ("hit", "pit")}


def _fit_matches_look(fits: dict, eval_doc: dict, passes: dict) -> dict:
    """{'side:stat': bool}: the served fit reproduces the fit the look scored (same
    penalty, rows, bands and coefficients to 1e-6) for every stat that passed."""
    pen = (((eval_doc.get("results") or {}).get("folds") or [{}])[0]).get("penalties") or {}
    out = {}
    for side, stats in passes.items():
        for stat in stats:
            m = fits["models"][side].get(stat)
            ref = pen.get(f"{side}:{stat}")
            ok = bool(m and ref and m["lam"] == ref["lambda"] and m["n_train"] == ref["n_train"]
                      and abs(m["q10"] - ref["band_q10"]) <= 1e-6
                      and abs(m["q90"] - ref["band_q90"]) <= 1e-6
                      and abs(m["intercept"] - ref["intercept"]) <= 1e-6
                      and all(abs(m["coef"].get(k, 0.0) - v) <= 1e-6 for k, v in ref["coef"].items()))
            out[f"{side}:{stat}"] = ok
    return out


def _stat_receipt(side: str, stat: str, e: dict) -> dict:
    best = e.get("best_baseline")
    return {"label": STAT_LABEL.get(stat, stat), "side": side, "verdict": e.get("verdict"),
            "n": e.get("n"), "mae_model": round(e["mae_model"], 5),
            "best_baseline": best, "best_baseline_name": BASELINE_NAME.get(best, best),
            "mae_best_baseline": round(e["mae_best_baseline"], 5),
            "d": round(e["d"], 5), "d_lb95": round(e["d_lb95"], 5),
            "coverage_p10_p90": round(e["coverage_p10_p90"], 4)}


def serve_doc(prospect_keys=None, *, corpus=None, eval_doc: dict | None = None) -> dict:
    """The served arrival line: for every live prospect on a side with a passed stat,
    {stat: [p10, p50, p90]} from the fit the look scored (debut cohorts 2016 to 2021,
    aging v2), plus the tool-implied value of his grade where the stat has one. A
    stat is left out of a player's row when none of its inputs exists for him (the
    model would print its intercept). Reads no holdout row and no R-VM row; the
    served payload is never touched. Raises when the fit does not reproduce the
    look's penalties, bands and coefficients."""
    import fa_projection as fp
    doc = eval_doc if eval_doc is not None else json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    passes = look_passes(doc)
    stats_by_side = {s: list(v) for s, v in passes.items() if v}
    years = tuple(range(EARLIEST_COHORT, HOLDOUT_FIRST_DEBUT_YEAR))
    if list(doc.get("train_cohorts") or []) != list(years):
        raise LookRefused(f"the look fit cohorts {doc.get('train_cohorts')}, not {list(years)}")
    guard_years(years, mode="dev")
    corpus = corpus or fp.build_corpus()
    train, _acct = build_profiles(years, mode="dev")
    fits = fit_fold(train, max(years), corpus)
    check = _fit_matches_look(fits, doc, passes)
    if not all(check.values()):
        raise RuntimeError("the served fit does not reproduce the look's fit: "
                           + ", ".join(k for k, v in check.items() if not v))
    rows: dict = {}
    left_out = {f"{s}:{st}": 0 for s, sts in stats_by_side.items() for st in sts}
    for prof in _live_profiles(prospect_keys):
        side = prof["side"]
        if side not in stats_by_side:
            continue
        sf = _side_fits(fits, side)
        row: dict = {}
        tip: dict = {}
        for stat in stats_by_side[side]:
            p = predict_stat(fits["models"][side].get(stat), prof, sf)
            if p is None or not any(v is not None for k, v in p["inputs"].items() if k != "age_delta"):
                left_out[f"{side}:{stat}"] += 1
                continue
            row[stat] = [round(p["p10"], SERVED_ROUND), round(p["p50"], SERVED_ROUND),
                         round(p["p90"], SERVED_ROUND)]
            if p["inputs"].get("tip_first") is not None:
                tip[stat] = round(p["inputs"]["tip_first"], SERVED_ROUND)
        if row:
            if tip:
                row["tip"] = tip
            row["mlbam"] = prof["mlbam"]
            rows[prof["player_key"]] = row
    return {
        "generated_at": date.today().isoformat(), "role": "served", "heading": SERVED_HEADING,
        "frame": FRAME_NAME,
        "conditional": ("Conditional on reaching the majors: every figure here is a projected rate over "
                        "his first three MLB seasons if he debuts, checked on players who did debut. It is "
                        "not a chance of reaching the majors and not a projection of all prospects."),
        "source": {"eval_artifact": "data/prospect_statline_eval.json",
                   "gate": "docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md",
                   "look_generated_at": doc.get("generated_at"), "holdout_cohorts": doc.get("holdout_cohorts"),
                   "gate_sha": doc.get("gate_sha")},
        "fit": {"cohorts": [years[0], years[-1]], "n_train": len(train), "aging": "v2",
                "fit_matches_look": check},
        "stats": {stat: _stat_receipt(side, stat, e)
                  for side, sts in passes.items() for stat, e in sts.items()},
        "n_rows": len(rows), "left_out": left_out, "rows": dict(sorted(rows.items())),
    }


def write_served(path: Path | None = None, prospect_keys=None, *, corpus=None,
                 eval_doc: dict | None = None) -> Path:
    path = Path(path) if path else SERVED_PATH
    doc = serve_doc(prospect_keys, corpus=corpus, eval_doc=eval_doc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":"), default=_json_default) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dev", action="store_true", help="the one development read")
    ap.add_argument("--dry-run", action="store_true", help="the reporting path on fixtures")
    ap.add_argument("--B", type=int, default=BOOT_B)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.dry_run:
        rep = dry_run()
        print(json.dumps({"l1": {s: {k: v.get("verdict") for k, v in rep["l1"][s].items()}
                                 for s in rep["l1"]}, "l2": rep["l2"].get("verdict")}))
        return 0
    if args.dev:
        doc = run_dev(B=args.B)
        res = doc["results"]
        for side in ("hit", "pit"):
            for stat, e in res["l1"][side].items():
                print(f"{side} {stat}: n={e.get('n')} model={e.get('mae_model')} "
                      f"best={e.get('best_baseline')} {e.get('mae_best_baseline')} d={e.get('d')} "
                      f"lb={e.get('d_lb95')} p={e.get('p_one_sided')} cov={e.get('coverage_p10_p90')} "
                      f"{e.get('verdict')}")
        l2 = res["l2"]
        print(f"L2: n={l2.get('n')} mae model={l2.get('mae_model')} inc={l2.get('mae_inc')} "
              f"rho model={l2.get('rho_model')} inc={l2.get('rho_inc')} {l2.get('verdict')}")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
