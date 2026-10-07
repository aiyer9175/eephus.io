# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""fantasy_export.py — data/fantasy.json for the /fantasy/ module.

Rest-of-season (ROS) fantasy projections for the whole MLB player pool, scored
by the canonical Ottoneu engines (`fantasy_scoring`), plus the forward
probable-pitcher schedule (`fantasy_schedule`). The client re-scores in any of
the four systems from the per-player COUNTING-STAT vectors we bake here.

Projection method (reuses the Gate-1-validated FA engine, no new model):
  * `fp.build_corpus()` → `fp.fitted_models()` → `fp.project_player(target=cur+1,
    in_progress=(cur, frac))` gives each player's current TRUE-TALENT rate
    components + full-season playing time, blending the partial current season
    (fa_projection.py:587-639).
  * ROS playing time = projected full-season PT × (1 − season_fraction): what's
    left to play. Once the regular season is over (season_mode, read off the
    StatsAPI calendar) the payload is stamped mode "next_season" and serves the
    same engine's full-season line for season + 1, unscaled. The pool floors
    read the full-season PT in both modes. Counting stats = rates × ROS PT, inverting ISO/BABIP into hit
    types with the SAME algebra as `_assemble_hitter` (fa_projection.py:694-717).
  * Skill counting stats (H, 1B/2B/3B, HR, BB, K, IP) are engine-projected.
    CONTEXT stats the rate model can't produce — R, RBI, SB (hitters); W, QS, H
    allowed (pitchers); SV, HLD (relievers) — are heuristic estimates, clearly
    marked `_est`, scaled from league rates / observed pace. These affect roto R/
    RBI/SB/W/SV and the FGP hit penalty only; the core skill ranking stands on
    the engine.

Best-effort + additive: any failure logs and degrades (a section renders "being
computed"); never aborts the pipeline. Run: `python fantasy_export.py`
(or `--limit N` for a fast partial). Wired into run_monthly (see run_monthly).
"""
from __future__ import annotations

import functools
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import dynasty_blend
import fa_projection as fp
import fantasy_rank as frank
import fantasy_schedule as fsched
import fantasy_scoring as fscore

log = logging.getLogger("fantasy_export")

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "fantasy.json"

# League anchors for the CONTEXT-stat heuristics (rate model doesn't emit these).
#
# MEASURED, NOT ASSUMED (2026-09-17). Every anchor carrying that date below was
# COUNTED off the cached StatsAPI box scores: all 2,286 completed 2026 regular
# season games that .cache/betting/completed_games.json lists and
# .cache/game_feeds holds, both clubs, every player row, no sampling. The fields
# read are public counting stats (PA, AB, IP, ER, BF, HBP, SB, CS), so nothing
# here is an outcome any board is graded against. The anchors with no date are
# the older hand numbers and are now labelled as hand numbers.
_LG_OBP, _LG_SLG = 0.315, 0.410  # hand anchors, R and RBI heuristics only
_LG_PIT_BABIP = 0.290           # hits-allowed on balls in play
_SP_DECISION_RATE = 0.60        # fraction of a start that yields a W/L decision
_LG_CS_PER_SB = 0.2999          # caught stealing per stolen base. 2026-09-17:
                                # 929 CS on 3,098 SB. The old 0.26 was a hand
                                # number 13% light, so every base stealer was
                                # credited with steals he was never charged for
                                # being thrown out on. FanGraphs points charge
                                # -2.8 a caught stealing, so this was worth
                                # points and not just a column.
_LG_SB_PER_PA = 0.01790         # stolen bases per plate appearance. 2026-09-17:
                                # 3,098 in 173,074. This is the DEFAULT for a
                                # bat with no observed pace; the old 0.012 has
                                # never been exercised on a served row (every
                                # hitter resolves a rate), so this moves nothing
                                # today and stops being wrong the day it does.

# PITCHER HIT BATSMEN, BY ROLE, because the two roles are not one rate and the
# surfaces that read them are not one surface. 2026-09-17: starters 1,047 hit
# batsmen in 98,470 batters faced, relievers 951 in 74,604. The code carried
# 0.008 for both, 25% light on a starter and 37% light on a reliever.
#
# WHY BY ROLE AND NOT THE 0.01154 POOLED RATE. The one SERVED BETTING surface a
# ROS pitcher line reaches is the props "Hits allowed" fair line, and every row
# on that board is an announced STARTER. Pricing a starter off a pooled rate
# that reliever innings pull upward moves that published number further than the
# repair the plan authorised, which names 0.01072: the audit's starter subset,
# reproduced here at 0.01063 on a larger sample. The reliever rate is separately
# right for the reliever rows, so nothing is traded away to get it.
_LG_HBP_PER_BF_SP = 0.01063     # starters, 1,047 in 98,470
_LG_HBP_PER_BF_RP = 0.01275     # relievers, 951 in 74,604

# THE QUALITY-START RULE'S LEVEL, re-set 2026-09-17; its two slopes are not.
# The slopes are stated conventions and refitting them on outcomes would be a
# model fit, which this repair is not. What was measurably wrong was the level.
# On the 3,995 real starts in the sample (BF >= 18, so an opener is not counted
# as a failed start), mean 5.4701 IP, the league quality-start rate is 0.3772.
# The rule returned 0.26581 at those inputs against a league FIP of 4.00. The
# intercept absorbs the whole 0.11139 gap: same shape, measured level.
_QS_INTERCEPT = 0.3114
_QS_IP_SLOPE = 0.14
_QS_FIP_SLOPE = 0.11
_QS_CEILING = 0.85

# ---------------------------------------------------------------------------
# THE POOL FLOORS AND THE SEASON MODE (2026-09-24).
#
# The floors used to read the REST-OF-SEASON remainder: a hitter left the pool
# under 20 ROS PA and a pitcher under 8 ROS IP. ROS playing time is the
# full-season projection times (1 - season_fraction), so the floor tightened
# every day of the season and emptied the pool before the season ended: on the
# 2026-09-07 corpus (fraction 0.891) every pitcher was gone past fraction 0.953
# and every hitter past 0.969, and the 2026-09-23 build (0.976) served 0
# players. Every rest-of-season board, the streamers, the closer grid, the DFS
# slate and the betting props went dark with games still left to play. Only
# 28 relievers survived at 0.891, because a 60-inning arm has under 8 innings
# left by early September. The floors now read the FULL-SEASON projection, so
# who is in the pool no longer depends on the date.
#
# THE LEVELS. The old floors, read on the full season, ran from 20 PA / 8 IP
# on opening day to 80 PA / 32 IP at three quarters of the season, and the
# August builds that sat there served 1,184 to 1,250 players inside the
# 600KB corpus budget (test_fantasy_split). Carrying 20 / 8 over unchanged
# measured 1,487 players and 697KB on 2026-09-24, most of the extra rows being
# arms projected under 30 innings that no fantasy board ranks. 100 PA and 30 IP
# (a bench bat, a middle reliever) measured 1,203 players, the August size.
#
# OWNER ANSWER M21-1 (2026-09-25): 20 projected full-season PA and 8 IP, the
# old levels read on the full season, with the corpus budget raised to 720KB
# (test_fantasy_split) to carry the wider pool. Hand floors on a display pool,
# not fitted to any outcome.
_POOL_FLOOR_PA = 20          # projected full-season plate appearances
_POOL_FLOOR_IP = 8           # projected full-season innings

# THE SEASON MODE. "ros" scales each full-season projection to what is left of
# the regular season. "next_season" serves the same engine's full-season line
# for the following season, unscaled, because once the regular season is over
# "rest of season" is zero for everyone and a board of zeros is not a board.
# The switch reads the StatsAPI season calendar (fsched.regular_season_dates);
# when the calendar cannot be read the PA ratio stands in, and only a ratio that
# has reached the clamp counts as a finished season.
MODE_ROS = "ros"
MODE_NEXT_SEASON = "next_season"
_SEASON_DONE_FRAC = 0.999


def season_mode(frac: float, *, today: date | None = None,
                regular_season_end: str | None = None) -> str:
    """MODE_NEXT_SEASON once the regular season is over, else MODE_ROS. Pure.

    With a calendar end date, the season is over on the day after it. Without
    one, only a PA ratio at the clamp (the league has already played at least
    last season's plate appearances) counts."""
    today = today or date.today()
    if regular_season_end:
        try:
            return (MODE_NEXT_SEASON if today > date.fromisoformat(regular_season_end)
                    else MODE_ROS)
        except ValueError:
            pass
    return MODE_NEXT_SEASON if frac >= _SEASON_DONE_FRAC else MODE_ROS

# ---------------------------------------------------------------------------
# ONE opponent-offense matchup multiplier, for every board that prices a start.
#
# There were two of them (audit L17-F6, 2026-09-10), riding the SAME served row:
# _start_score clamped 100 / Offense+ into [0.6, 1.5] and dfs_export's pitcher
# line clamped Offense+ / 100 into [0.82, 1.22]. Those bands are not reciprocals
# of one another, since [1/1.5, 1/0.6] is [0.667, 1.667], so one club could be
# worth two different amounts depending on which of the two boards you read.
#
# The band kept is the NARROW one, because it is the honest one: [0.82, 1.22] is
# reciprocally symmetric to within 0.0005 (1 / 0.82 = 1.2195), so no club can be
# worth more to face than its mirror is to avoid. It is still a guard rail and
# not the operative term: Offense+ has to leave [82, 122] before it binds.
#
# WHAT THIS DOES NOT DO. It does not put a park factor on the streamer score,
# and it does not change WHICH numbers each board multiplies: the streamer score
# still scales a whole per-start point total (innings and strikeouts included,
# which dfs_export's own docstring argues is wrong), and the DFS line still
# scales only the hits, earned runs and home runs allowed. Both are the other
# halves of L17-F6 and both are decisions, not repairs.
MATCHUP_CLAMP = (0.82, 1.22)


def matchup_mult(opp_off: float | None, *, side: str) -> float:
    """The opponent-offense matchup multiplier for ONE start, in ONE band.

    `side="allowed"` is the multiplier on what a pitcher gives up, which RISES
    with the opponent's offense. `side="total"` is the multiplier a streamer
    score puts on a whole per-start point total, which FALLS as the opponent's
    offense rises. The two are reciprocals and they are clamped in the same
    band, which is the entire point of routing both through one function.

    An unreadable, zero or missing index prices at a neutral 1.0 rather than
    dividing by it. Saying which kind of neutral that is stays the caller's job
    (`opp_off_resolved` on the streamer row, `matchup_resolved` on the DFS game
    side): a measured league-average opponent and a lookup that found nothing
    produce the same multiplier and must not read the same."""
    if side not in ("allowed", "total"):
        raise ValueError(f"unknown matchup side {side!r}")
    try:
        idx = float(opp_off)
    except (TypeError, ValueError):
        return 1.0
    if idx <= 0:
        return 1.0
    raw = (idx / 100.0) if side == "allowed" else (100.0 / idx)
    return min(max(raw, MATCHUP_CLAMP[0]), MATCHUP_CLAMP[1])


def _load_json(name: str) -> dict | list | None:
    p = DATA_DIR / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _record_ingest_safe(source: str, *, ok: bool, message: str = "",
                        n_rows: int = 0) -> None:
    """File one outcome into the ingest-health RED ledger, never raising.

    THE ledger call for this module and for dfs_export (which imports it rather
    than growing a second copy). run_monthly.write_ingest_health drains it into
    data/ingest_health.json and prints `!!! INGEST RED` in the run summary, so a
    join or a fetch that quietly produced nothing becomes visible on the day it
    happens instead of days later as a blank module.

    Best-effort BY DESIGN: reporting must never be the reason a refresh fails,
    and importing run_monthly is expensive enough that only anomaly paths should
    reach this."""
    try:
        from run_monthly import _record_ingest
        _record_ingest(source, ok=ok, n_rows=n_rows, message=message)
    except Exception:
        log.debug("could not record ingest health for %s", source, exc_info=True)


def _json_blob(payload: dict, source: str) -> str | None:
    """Serialize an artifact, or report and refuse to write one.

    `allow_nan=False` is the whole point. json.dumps DEFAULTS to emitting the
    bare tokens NaN / Infinity, which are not JSON at all: the browser's
    JSON.parse throws on the first one, so a single non-finite number anywhere
    in the tree does not degrade one section, it dark-starts the entire page.
    Refusing to write keeps the previous (parseable) artifact served, the same
    trade refresh_live's EMPTY-FETCH GUARD makes for an empty schedule.

    Returns None after an error log AND a RED ledger row, so a caller cannot
    swallow the failure by accident. dfs_export writes through this too."""
    try:
        return json.dumps(payload, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        msg = (f"{source}: payload is not serializable as valid JSON ({exc}); "
               "refused to write it. A non-finite number reaches the page as a "
               "bare NaN token that JSON.parse rejects, which blanks the whole "
               "surface. The previous artifact stays served.")
        log.error(msg)
        _record_ingest_safe(source, ok=False, message=msg)
        return None


# ONE eFV BASIS FOR THIS WHOLE MODULE (2026-08-03). /fantasy/ used to show two
# different eFV numbers on one page: Call-up Watch read raw `xfv_grade` while the
# Dynasty board's eFV column read the RETIRED `xfv_grade_quantile`, so the same
# prospect could carry two grades a tab apart. Both now go through _board_grade,
# which mirrors build_site._load_xfv_grades / storage.BOARD_GRADE_FIELD / the
# prospx client's efvBoardValue exactly. The SCALE is owned by efv_board_scale;
# no copy of the coefficients lives here.
try:
    from efv_board_scale import board_value as _efv_board_value
except Exception:                                            # pragma: no cover
    def _efv_board_value(rec):
        return (rec or {}).get("xfv_grade")


def _board_grade(rec: dict | None):
    """THE displayed eFV grade for an xfv.json record, or None. Unrounded -
    callers that display it round to NEAREST (eFV is not a scouting FV)."""
    rec = rec or {}
    g = _efv_board_value(rec)
    if g is None:
        g = rec.get("xfv_grade_realized")
    if g is None:
        g = rec.get("xfv_grade_quantile")
    return float(g) if isinstance(g, (int, float)) else None


@functools.lru_cache(maxsize=1)
def _efv_by_key() -> dict:
    """{player_key: board eFV grade} off data/xfv.json - the site-wide grade.
    Empty when the artifact is absent (fresh checkout), so callers fall back
    to consensus rather than failing."""
    x = _load_json("xfv.json") or {}
    by = x.get("by_player") if isinstance(x, dict) else None
    if not isinstance(by, dict):
        return {}
    out = {}
    for k, v in by.items():
        g = _board_grade(v) if isinstance(v, dict) else None
        if g is not None:
            out[k] = g
    return out


def _sb_rate_by_mlbam() -> dict:
    """Observed season-to-date SB per PA from the hitter leaderboard (the only
    committed SB source) — the base rate for the ROS SB estimate."""
    lb = _load_json("hitter_leaderboards.json") or {}
    out: dict = {}
    for r in (lb.get("hitters") or []):
        mid, pa, sb = r.get("mlbam"), r.get("pa"), r.get("sb")
        if mid and pa and pa > 0 and sb is not None:
            out[int(mid)] = sb / pa
    return out


def _names_from_leaderboards() -> dict:
    """{mlbam: name} from the three skill leaderboards — the local, committed name
    source (corpus rows carry no display name; proj_export uses pybaseball)."""
    out: dict = {}
    for fname, key in (("hitter_leaderboards.json", "hitters"),
                       ("starter_leaderboards.json", "starters"),
                       ("bullpen_leaderboards.json", "relievers")):
        for r in ((_load_json(fname) or {}).get(key) or []):
            if r.get("mlbam") and r.get("name"):
                out.setdefault(int(r["mlbam"]), r["name"])
    return out


def _name_from_links(links, mid) -> str | None:
    """Resolve a display name from player_links.json. Its shape is
    {generated_at, byKey, byMlbam}; the mlbam->entry map is nested under byMlbam
    and is STRING-keyed, so the lookup must go through byMlbam[str(mid)] (not the
    top-level dict). Returns None when absent."""
    by_mlbam = links.get("byMlbam") if isinstance(links, dict) else None
    e = (by_mlbam or {}).get(str(mid)) if isinstance(by_mlbam, dict) else None
    if isinstance(e, dict):
        return e.get("name")
    return e if isinstance(e, str) else None


def _hitter_ros(proj: dict, ros_pa: float, sb_per_pa: float | None) -> dict:
    """Invert the projected per-PA rate components into ROS counting stats over
    `ros_pa`, mirroring _assemble_hitter's hit-type algebra."""
    a = fp._pcfg()["assembly"]
    pa = max(0.0, ros_pa)
    bb = proj["bb_pct"] * pa
    hbp = a["hbp_rate"] * pa
    sf = a["sf_rate"] * pa
    ab = max(0.0, pa - bb - hbp - sf)
    so = proj["k_pct"] * pa
    hr = proj["hr_pa"] * pa
    bip = max(0.0, ab - so - hr + sf)
    hits_in_play = (proj["babip"] or 0.28) * bip
    h = hits_in_play + hr
    eb_nonhr = max(0.0, proj["iso"] * ab - 3 * hr)          # 2B + 2·3B, ISO is per-AB
    ratio = a["double_triple_ratio"]
    triples = eb_nonhr / (ratio + 2) if (ratio + 2) else 0.0
    doubles = ratio * triples
    singles = max(0.0, h - hr - doubles - triples)
    # Context estimates (heuristic): SB from observed pace; R from OBP; RBI from SLG.
    obp = ((h + bb + hbp) / pa) if pa > 0 else 0.0
    slg = ((singles + 2 * doubles + 3 * triples + 4 * hr) / ab) if ab > 0 else 0.0
    r_pa = 0.12                                             # league R (≈RBI) per PA anchor
    sb = (sb_per_pa if sb_per_pa is not None else _LG_SB_PER_PA) * pa
    runs = r_pa * (obp / _LG_OBP) * pa
    rbi = r_pa * (slg / _LG_SLG) * pa
    return {
        "pa": round(pa, 1), "ab": round(ab, 1),
        "h": round(h, 1), "single": round(singles, 1), "double": round(doubles, 1),
        "triple": round(triples, 1), "hr": round(hr, 1), "bb": round(bb, 1),
        "hbp": round(hbp, 1), "so": round(so, 1),
        "sb": round(sb, 1), "cs": round(sb * _LG_CS_PER_SB, 1),
        "r": round(runs, 1), "rbi": round(rbi, 1),
        "avg": round(h / ab, 3) if ab > 0 else None,
        "obp": round(obp, 3), "slg": round(slg, 3),
        "_est": ["r", "rbi", "sb", "cs"],
    }


def _pitcher_ros(proj: dict, ros_bf: float, ros_ip: float, role: str,
                 ip_per_gs: float | None) -> dict:
    """ROS pitcher counting stats. K/BB/HR/IP are engine-projected; H allowed,
    W, QS, SV/HLD are heuristic context estimates."""
    bf = max(0.0, ros_bf)
    ip = max(0.0, ros_ip)
    k = proj["k_pct"] * bf
    bb = proj["bb_pct"] * bf
    hr = proj["hr_bf"] * bf
    hbp = (_LG_HBP_PER_BF_SP if role == "SP" else _LG_HBP_PER_BF_RP) * bf
    bip = max(0.0, bf - k - bb - hbp - hr)
    h = _LG_PIT_BABIP * bip + hr                            # hits allowed (est)
    fip = proj.get("fip_proj") or 4.2
    er = (fip / 9.0) * ip                                   # ERA≈FIP for pricing
    whip = ((h + bb) / ip) if ip > 0 else None
    row = {
        "role": role, "ip": round(ip, 1), "bf": round(bf, 0),
        "k": round(k, 1), "bb": round(bb, 1), "hr": round(hr, 1),
        "hbp": round(hbp, 1), "h": round(h, 1), "er": round(er, 1),
        "era": round(9 * er / ip, 2) if ip > 0 else None,
        "whip": round(whip, 2) if whip is not None else None,
        "hr9": round(9 * hr / ip, 2) if ip > 0 else None,
        # era belongs in _est (added 2026-08-16): it is 9*er/ip and er is priced
        # at FIP (the line above), so the ERA column is exactly as heuristic as
        # the h and er it derives from. Marking only h/er let the client render
        # a FIP-derived ERA without the estimate marker its own inputs carried.
        "_est": ["h", "er", "era"],
    }
    if role == "SP":
        ipgs = ip_per_gs or 5.4
        starts = ip / ipgs if ipgs > 0 else 0.0
        qs_rate = min(_QS_CEILING,
                      max(0.0, _QS_INTERCEPT
                          + _QS_IP_SLOPE * (ipgs - 5.0)
                          - _QS_FIP_SLOPE * (fip - 4.0)))
        decisions = starts * _SP_DECISION_RATE
        pwin = min(0.80, max(0.20, 0.5 - 0.07 * (fip - 4.2)))
        row.update({"gs": round(starts, 1), "qs": round(starts * qs_rate, 1),
                    "w": round(decisions * pwin, 1),
                    "l": round(decisions * (1 - pwin), 1)})
        row["_est"] += ["w", "l", "qs", "gs"]
    else:
        row.update({"sv": 0.0, "hld": 0.0, "_rp": True})    # filled from pace in build
        row["_est"] += ["sv", "hld"]
    return row


def _rp_saves_holds() -> dict:
    """Season-to-date SV/HLD per reliever (bullpen leaderboard) for the ROS pace
    forecast."""
    lb = _load_json("bullpen_leaderboards.json") or {}
    out: dict = {}
    for r in (lb.get("relievers") or []):
        mid = r.get("mlbam")
        if mid:
            out[int(mid)] = {"sv": r.get("saves") or 0, "hld": r.get("holds") or 0,
                             "gmli": r.get("gmli")}
    return out


def _ip_per_gs() -> dict:
    lb = _load_json("starter_leaderboards.json") or {}
    return {int(r["mlbam"]): r.get("ip_per_gs")
            for r in (lb.get("starters") or []) if r.get("mlbam")}


def _active_roster_ids():
    """The shared active-roster set, or None when the walk was not trustworthy.

    Imported lazily so this module keeps working with no network and so a
    bullpen_export import cycle cannot form at module load.
    """
    try:
        from bullpen_export import _active_mlbam_ids
        from datetime import date
        return _active_mlbam_ids(date.today().year)
    except Exception:                                      # noqa: BLE001
        return None


def _season_calendar(season: int) -> dict | None:
    """The regular-season dates for `season`, or None. Best-effort."""
    try:
        return fsched.regular_season_dates(season)
    except Exception:                                      # noqa: BLE001
        log.exception("fantasy: season calendar lookup failed")
        return None


def build_players(limit: int | None = None, *, today: date | None = None,
                  calendar: dict | None | bool = True) -> dict:
    """Project the whole pool and score it. Returns the full payload dict.

    `today` and `calendar` are injectable for tests: calendar=True looks the
    season calendar up, a dict ({"start", "end"}) is used as given, and None
    means unknown (the PA ratio decides the mode)."""
    corpus = fp.build_corpus()
    league = corpus["league"]
    seasons = [s for s in league if isinstance(s, int)]
    cur = max(seasons) if seasons else datetime.now(timezone.utc).year
    curves, _war_map = fp.fitted_models(corpus, cur)
    frac = fp.season_fraction(league, cur)
    if calendar is True:
        calendar = _season_calendar(cur)
    mode = season_mode(frac, today=today,
                       regular_season_end=(calendar or {}).get("end"))
    # The share of each full-season projection this board serves: what is left
    # of the regular season, or all of next season's.
    remaining = 1.0 if mode == MODE_NEXT_SEASON else max(0.0, 1.0 - frac)
    # A finished season is a complete season: the engine then reads it whole,
    # with no in-progress playing-time blend (fa_projection._pt_expo at 1.0).
    elapsed = 1.0 if mode == MODE_NEXT_SEASON else frac
    in_prog = (cur, elapsed)

    # Latest-3-season history per player per side.
    by_player: dict[str, dict[int, dict[int, dict]]] = {"hit": {}, "pit": {}}
    for side in ("hit", "pit"):
        for row in corpus[side]:
            mid = row.get("mlbam")
            if mid and row.get("season", 0) >= cur - 3:
                by_player[side].setdefault(int(mid), {})[row["season"]] = row

    sb_rate = _sb_rate_by_mlbam()
    rp_sh = _rp_saves_holds()
    ipgs_map = _ip_per_gs()
    name_map = _names_from_leaderboards()
    links = (_load_json("player_links.json") or {})

    def _name(mid: int) -> str | None:
        if mid in name_map:
            return name_map[mid]
        return _name_from_links(links, mid)

    players: list[dict] = []
    # THE FANTASY RANK'S MLB LEG (owner answer M21-4, fantasy_rank.py): each
    # pooled row's per-season lines over the rank's horizon, walked from the
    # SAME projection on the same aging curves. Collected here because this
    # loop is the only place the projection and the curves meet; it rides out
    # under "_rank_inputs", which export() pops before anything is written.
    horizon: list[dict] = []

    def _horizon(mid, side, pos, proj, role, **kw):
        try:
            lines = frank.mlb_horizon_lines(proj, side, role, curves, **kw)
        except Exception:                                    # noqa: BLE001
            log.exception("fantasy: horizon lines failed for %s", mid)
            return
        if lines:
            horizon.append({"mlbam": mid, "side": side, "pos": pos, "lines": lines})

    ids = set(by_player["hit"]) | set(by_player["pit"])
    for i, mid in enumerate(sorted(ids)):
        if limit and i >= limit:
            break
        for side in ("hit", "pit"):
            seasons_d = by_player[side].get(mid)
            if not seasons_d:
                continue
            hist = [seasons_d[t] for t in (cur, cur - 1, cur - 2) if t in seasons_d]
            if not hist:
                continue
            expo = "pa" if side == "hit" else "ip"
            if (max((h.get(expo) or 0) for h in hist)) < (100 if side == "hit" else 20):
                continue
            age_row = next((h for h in hist if h.get("age")), None)
            role = hist[0].get("role")
            age = (age_row["age"] + (cur + 1 - age_row["season"])) if age_row else None
            proj = fp.project_player(hist, side, cur + 1, curves, league, age,
                                     role=role, in_progress=in_prog)
            if not proj:
                continue
            name = _name(mid)
            if side == "hit":
                if (proj.get("pt_proj") or 0) < _POOL_FLOOR_PA:
                    continue
                ros_pa = (proj.get("pt_proj") or 0) * remaining
                stats = _hitter_ros(proj, ros_pa, sb_rate.get(mid))
                pts = fscore.score_points(stats, "fgp", "hit")
                players.append({"mlbam": mid, "name": name, "side": "hit",
                                "pos": role, "ros": stats, "fpts_fgp": pts})
                _horizon(mid, "hit", role, proj, proj.get("role") or role,
                         sb_pa=sb_rate.get(mid))
            else:
                if (proj.get("ip_proj") or 0) < _POOL_FLOOR_IP:
                    continue
                ros_bf = (proj.get("pt_proj") or 0) * remaining
                ros_ip = (proj.get("ip_proj") or 0) * remaining
                pr = "SP" if (role == "SP") else "RP"
                stats = _pitcher_ros(proj, ros_bf, ros_ip, pr, ipgs_map.get(mid))
                if pr == "RP" and elapsed > 0:
                    sh = rp_sh.get(mid) or {}
                    stats["sv"] = round((sh.get("sv") or 0) * remaining / elapsed, 1)
                    stats["hld"] = round((sh.get("hld") or 0) * remaining / elapsed, 1)
                pts = fscore.score_points(stats, "fgp", "pit")
                players.append({"mlbam": mid, "name": name, "side": "pit",
                                "pos": pr, "ros": stats, "fpts_fgp": pts})
                sh = rp_sh.get(mid) or {}
                _horizon(mid, "pit", pr, proj, pr,
                         sv0=((sh.get("sv") or 0) / elapsed) if (pr == "RP" and elapsed > 0) else 0.0,
                         hld0=((sh.get("hld") or 0) / elapsed) if (pr == "RP" and elapsed > 0) else 0.0)

    _enrich(players)
    # Name, club and a display position ride the horizon rows from the
    # enriched pool rows (a hitter's corpus role is the bare "H", so his
    # lineup slots stand in for it).
    _who = {(p["mlbam"], p["side"]): p for p in players}
    for h in horizon:
        p = _who.get((h["mlbam"], h["side"])) or {}
        h["name"], h["team"] = p.get("name"), p.get("team")
        if h["side"] == "hit" and p.get("elig"):
            h["pos"] = "/".join(p["elig"][:2])
    # ROSTER STATUS, FLAGGED AND NEVER FILTERED. This is a rest-of-season board, so
    # an injured player is the most important row on it: a manager rostering him
    # needs to SEE that he is out. Dropping him, the way the lineup charts
    # correctly drop him, would be the bug here. Measured before this shipped: 190
    # of 743 served players (25.6%) were not on an active roster and nothing said
    # so anywhere.
    active_ids = _active_roster_ids()
    n_off = 0
    for pl in players:
        mid = pl.get("mlbam")
        if active_ids is None or mid is None:
            pl["roster_status"] = "unknown"
            continue
        on = int(mid) in active_ids
        pl["roster_status"] = "active" if on else "off_roster"
        n_off += 0 if on else 1
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "season": cur,
        "season_fraction": round(frac, 3),
        # What the counting lines in `players` cover. "ros": the rest of
        # `season`'s regular season. "next_season": the full `target_season`,
        # served once the regular season is over (see season_mode).
        "mode": mode,
        "target_season": cur + 1 if mode == MODE_NEXT_SEASON else cur,
        "regular_season": calendar or None,
        "pool_floor": {"hit_pa": _POOL_FLOOR_PA, "pit_ip": _POOL_FLOOR_IP,
                       "basis": "projected full-season playing time, not the "
                                "rest-of-season remainder"},
        "n_players": len(players),
        "roster_status": {
            "applied": active_ids is not None,
            "n_off_roster": n_off,
            "basis": "StatsAPI rosterType=active (26-man); an optioned or injured "
                     "player reads off_roster",
            "policy": ("FLAGGED, NEVER FILTERED. This is a rest-of-season board, so a "
                       "player who is out is still the row a manager most needs to see. "
                       "The lineup and rotation charts filter instead, because those are "
                       "claims about tonight."),
            "on_failure": "a roster walk covering fewer than 28 of 30 clubs flags "
                          "every player 'unknown' rather than mislabelling whole clubs",
        },
        "scoring": fscore.points_weight_tables(),
        "scoring_catalog": fscore.SCORING_CATALOG,
        "players": players,
        # Popped by export() before the write; never served.
        "_rank_inputs": {"horizon": horizon, "corpus": corpus, "curves": curves,
                         "league": league, "first_season": cur + 1},
    }


def _lb_index(fname: str, key: str) -> dict:
    return {int(r["mlbam"]): r
            for r in ((_load_json(fname) or {}).get(key) or []) if r.get("mlbam")}


def _player_luck(p: dict):
    """Raw regression-candidate luck for a player: hitter luck_gap (Savant
    xwOBA - wOBA) or pitcher luck (wOBA - xwOBA allowed), both in wOBA points
    and both signed so + means results behind the expected stats."""
    s = p.get("skill") or {}
    return s.get("luck_gap") if p.get("side") == "hit" else s.get("luck")


def _buy_sell(players: list[dict], n: int = 50,
              share: float = 1.0) -> tuple[list, list]:
    """Combined Buy-Low / Sell-High mlbam lists (positive luck = unlucky = buy).

    THE 20-POINT GATE READS THE FULL-SEASON LINE (2026-09-24). `share` is the
    part of the full-season projection each served line covers (1 - fraction
    on a rest-of-season corpus, 1.0 on a next-season one). The gate used to
    read the rest-of-season points directly, so it closed as the season ran
    out: at fraction 0.983 no player projected 20 more points and both lists
    were empty. Dividing by `share` puts the gate back on the player, not the
    calendar, the same move the pool floors made.

    Hitter luck_gap and pitcher luck are both in wOBA points since 2026-09-24
    (the hitter side used to be xHEM+ minus HEM+, a plus-stat delta ~500x
    wider, which is why this scaling exists). On one unit the per-side scale
    is a small correction (board pool sd about .023 hitters vs .024 pitchers
    on 2026-09-24), kept so a spread change on one side cannot tilt both
    lists toward the other. Scale each side's luck by its own pool spread
    (population std) onto a common axis before the combined sort. Scaling by
    std (not mean-centering) preserves the sign, so a buy row keeps a positive gap and a sell row a negative one."""
    import statistics
    share = share if (share and share > 0) else 1.0
    luckable = [p for p in players
                if _player_luck(p) is not None
                and (p.get("fpts_fgp") or 0) / share > 20]
    scale: dict = {}
    for side in ("hit", "pit"):
        vals = [_player_luck(p) for p in luckable if p.get("side") == side]
        scale[side] = statistics.pstdev(vals) if len(vals) >= 2 else 0.0

    def _norm(p):
        sd = scale.get(p.get("side")) or 0.0
        return (_player_luck(p) / sd) if sd else 0.0

    # Entries carry SIDE, unlike the other section lists, because this is the one
    # section a bare mlbam cannot resolve. Every other section is single-sided by
    # construction (ros_hitter is hitters, closer_depth is relievers), so its
    # renderer already knows which side to look up. buy/sell is the only COMBINED
    # ranking, so a two-way player's two records are both eligible and a bare id
    # is genuinely ambiguous. Shohei Ohtani is that player today: he is ranked in
    # on his HIT-side luck_gap, and before this the client resolved him to his
    # pitcher record and rendered a pitcher's luck number under a hitter's ranking.
    buy = [{"mlbam": p["mlbam"], "side": p.get("side")}
           for p in sorted(luckable, key=lambda p: -_norm(p))[:n]]
    sell = [{"mlbam": p["mlbam"], "side": p.get("side")}
            for p in sorted(luckable, key=lambda p: _norm(p))[:n]]
    return buy, sell


def _attach_swing_trend(players: list[dict]) -> None:
    """W6 DISPLAY-ONLY mechanics-trend annotation from the per-season Swing+
    sidecar (data/swing_plus.json, Will Cahoon's model). Latest-season minus
    prior-season Swing+; annotated only when the move is >= +/-5 points.
    NON-SCORING by construction: no ranking, sorting, or section-membership
    code reads swing_trend (_buy_sell sorts on luck only) - the client renders
    it as a context chip on the buy/sell boards."""
    sw = (_load_json("swing_plus.json") or {}).get("players") or {}
    for p in players:
        seasons = (sw.get(str(p.get("mlbam"))) or {}).get("seasons") or {}
        yrs = sorted(y for y in seasons
                     if (seasons[y] or {}).get("swing_plus") is not None)
        if len(yrs) < 2:
            continue
        cur, prev = seasons[yrs[-1]], seasons[yrs[-2]]
        delta = round(float(cur["swing_plus"]) - float(prev["swing_plus"]), 1)
        if abs(delta) >= 5:
            p["swing_trend"] = {"delta": delta,
                                "from": int(yrs[-2]), "to": int(yrs[-1])}


@functools.lru_cache(maxsize=64)
def _canon_org(code: str | None) -> str | None:
    """THE org-code canonicaliser for this module and for dfs_export.

    WHAT IT IS FOR. The hitter/bullpen leaderboards key teams by MLB-style codes
    (AZ, CWS, KC, SD, SF, TB, WSH) while the schedule feed emits the canonical
    codes (ARI, CHW, KCR, SDP, SFG, TBR, WSN). Re-key on ingest and
    teams_ctx.get(opp_org) resolves all 30 opponents; do not, and 7 of them fall
    through to the neutral offense_plus=100 path with nothing raised and nothing
    logged (data/fantasy_startscore_eval.json: 23% of 2026 starts affected).

    ONE IMPLEMENTATION, on purpose. This used to be a private 7-entry map right
    here, which disagreed with trades.canonical_org (the site's owner of this
    mapping) in two ways that both cost real rows: it was MISSING OAK -> ATH,
    and any future code change would have had to be found in two places by
    somebody who did not know the second one existed.

    Lazy import: trades.py pulls requests and the scrapers, and this module sits
    on the daily path (the same reason fantasy_schedule._org imports lazily).
    An unavailable canonicaliser returns the code as given, which is exactly
    what an unmapped code already did."""
    if not code:
        return None
    try:
        from trades import canonical_org
    except Exception:                                        # pragma: no cover
        log.warning("trades.canonical_org unavailable; org codes left as given")
        return code
    return canonical_org(code) or code


# One process files at most one short-context RED: _teams_context is called by
# build_sections AND by dfs_export inside the same run, and a ledger that
# repeats itself is a ledger people stop reading.
_MLB_CLUBS = 30
_teams_ctx_reported = False


def _teams_context_health(ctx: dict) -> dict:
    """How much of the opponent context actually resolved, by field."""
    def _n(field: str) -> int:
        return sum(1 for r in (ctx or {}).values()
                   if isinstance((r or {}).get(field), (int, float)))
    return {"n_orgs": len(ctx or {}), "n_offense_plus": _n("offense_plus"),
            "n_bullpen_plus": _n("bullpen_plus")}


def _teams_context() -> dict:
    """{org: {offense_plus, heart_hem, bullpen_plus, leverage_deploy_plus}} - the
    opponent-quality context a streamer ranking needs.

    Keyed by CANONICAL org on both legs (see _canon_org). A row whose code will
    not canonicalize is DROPPED rather than filed under a None key: a None key
    answers `teams_ctx.get(opp_org)` for every game side whose org failed to
    resolve, which hands an unknown opponent some real club's Offense+.

    The COUNT is reported when it comes up short. Nothing downstream fails on a
    thin context - every consumer defaults a missing club to the neutral 100 -
    so a broken join and a league-average opponent read identically unless
    somebody counts. That is the 2026-08-05 defect class exactly."""
    out: dict = {}
    for fname, fields in (
            ("hitter_leaderboards.json", ("offense_plus", "heart_hem")),
            ("bullpen_leaderboards.json", ("bullpen_plus", "leverage_deploy_plus"))):
        for t in ((_load_json(fname) or {}).get("teams") or []):
            org = _canon_org(t.get("team"))
            if not org:
                continue
            out.setdefault(org, {}).update({f: t.get(f) for f in fields})
    _report_teams_context(out)
    return out


def _report_teams_context(ctx: dict) -> None:
    """Log (and RED, once) an opponent context that does not cover all 30 clubs."""
    global _teams_ctx_reported
    h = _teams_context_health(ctx)
    if h["n_offense_plus"] >= _MLB_CLUBS and h["n_bullpen_plus"] >= _MLB_CLUBS:
        log.info("fantasy: opponent context resolved for %d orgs (Offense+ %d, "
                 "Bullpen+ %d)", h["n_orgs"], h["n_offense_plus"], h["n_bullpen_plus"])
        return
    msg = (f"opponent context covers {h['n_offense_plus']}/{_MLB_CLUBS} clubs on "
           f"Offense+ and {h['n_bullpen_plus']}/{_MLB_CLUBS} on Bullpen+; every "
           f"club that missed is priced at the neutral 100 on the streamer, "
           f"two-start and DFS boards")
    log.warning("fantasy: %s", msg)
    if not _teams_ctx_reported:
        _teams_ctx_reported = True
        _record_ingest_safe("fantasy_teams_context", ok=False, message=msg,
                            n_rows=h["n_offense_plus"])


def _enrich(players: list[dict]) -> None:
    """Attach each player's team + the skill metrics the /fantasy/ surface reads
    from the matching skill leaderboard (mlbam-joined). Powers the section
    signals (luck_gap/luck -> buy/sell, gmli/saves -> closers) and the card
    HEM+/SEM+/REM+ display. Only the read keys are baked: the old p['std'] block
    and the wider skill set had zero reader (client or server) - dead payload.

    ALSO bakes `elig`, the fantasy position eligibility list (2026-08-05, for
    the /dfs/ and /redraft/ split). The corpus role for a hitter is the bare
    string "H", which is useless to a lineup slot, so eligibility is joined from
    data/fielding_innings.json, the innings feed run_monthly d9b1 refreshes every
    night (owner decision 24, 2026-09-11; it used to read the June
    data/mlb_fielding_positions.json, which nothing refreshes). refresh_live
    re-stamps it every night through the same _hitter_elig, so the nightly
    innings reach /redraft/ and /dfs/ without waiting for this monthly build.
    Additive: every existing reader of `pos` is untouched.

    DATA-HOLE FALLBACK (2026-08-16): the three skill leaderboards carry only
    players who qualified for a board, so joining team from them alone left
    169 of 1184 pool players teamless, 10 nameless and 88 hitters without elig
    on the live artifact. data/mlb_player_detail.json (mlbam-resolvable,
    nightly-fresh) backfills team, name and a single-position elig; it fills
    holes only and never overrides a leaderboard value."""
    hit = _lb_index("hitter_leaderboards.json", "hitters")
    sp = _lb_index("starter_leaderboards.json", "starters")
    rp = _lb_index("bullpen_leaderboards.json", "relievers")
    elig = _elig_positions()
    detail = _detail_by_mlbam()
    for p in players:
        mid, r = p["mlbam"], None
        if p["side"] == "hit":
            r = hit.get(mid) or {}
            p["skill"] = {k: r.get(k) for k in ("hem_plus", "luck_gap")}
            slots = _hitter_elig(mid, elig, detail)
            if slots:
                p["elig"] = slots
        elif p["pos"] == "SP":
            r = sp.get(mid) or {}
            p["skill"] = {k: r.get(k) for k in ("sem_plus", "luck")}
            p["elig"] = ["P"]
        else:
            r = rp.get(mid) or {}
            p["skill"] = {k: r.get(k) for k in ("rem_plus", "gmli", "saves", "luck")}
            p["elig"] = ["P"]
        # ONE CODE SET (2026-09-25). The leaderboards key clubs MLB-style (AZ,
        # CWS, KC, SD, SF, TB, WSH) and mlb_player_detail mixes both families,
        # while team_next7, closer_depth, the streamer rows and DFS key the
        # canonical codes. Copying the raw code split the pool into 34 to 37
        # codes for 30 clubs and dropped the card's next-7 strip for every
        # player on those seven clubs (260 of 1,220 on the 2026-09-24 build).
        p["team"] = _canon_org(r.get("team"))
        d = detail.get(mid)
        if d:
            if not p.get("team"):
                p["team"] = _canon_org(d.get("team"))
            if not p.get("name"):
                p["name"] = d.get("name")


# StatsAPI fielding abbreviation -> fantasy lineup slot. A hitter with no
# fielding position over the games floor gets no `elig` at all rather than a
# guessed one; the reader falls back to UTIL and says so.
_POS_SLOT = {"C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS",
             "LF": "OF", "CF": "OF", "RF": "OF", "OF": "OF", "DH": "UTIL"}
_ELIG_MIN_GAMES = 5


#: The nightly-refreshed innings feed eligibility reads (fielding_innings.py).
ELIG_SOURCE = "fielding_innings.json"


def _elig_season(raw: dict, season: int | None = None) -> tuple[int | None, dict]:
    """(season, {mlbam(str): {POS: {"g", "gs", "inn"}}}) for the eligibility
    season: `season` when given, else the artifact's newest season (the live one
    during the year, which run_monthly d9b1 rewrites nightly)."""
    seasons = (raw or {}).get("seasons") if isinstance(raw, dict) else None
    if not isinstance(seasons, dict) or not seasons:
        return None, {}
    keys = [int(k) for k in seasons if str(k).isdigit()]
    if not keys:
        return None, {}
    y = int(season) if season is not None else max(keys)
    block = seasons.get(str(y))
    return (y, block) if isinstance(block, dict) else (y, {})


#: SEASON ROLLOVER. fielding_innings.refresh_current writes a new season's key
#: the first night the feed returns rows, so on opening day the newest block is
#: a handful of games and a newest-season-only read would strip almost every
#: hitter to UTIL. Until a player has _ELIG_CARRY_GAMES appearances in the field
#: this season, every position he played _ELIG_CARRY_GAMES or more games at the
#: season before still counts (and, with no games yet this season, last season's
#: modal position does). Once he reaches it, this season alone decides, which is
#: the rule the June file applied, so an established regular's slots in
#: September are exactly the newest season's.
_ELIG_CARRY_GAMES = 20


def _games_by_pos(pos) -> dict:
    """{POS: games} off one player's innings-feed block, pitching dropped."""
    if not isinstance(pos, dict):
        return {}
    return {p: float((v or {}).get("g") or 0) for p, v in pos.items() if p != "P"}


def _add_slots(slots: list, counts: dict, floor: float, keep_modal: bool) -> None:
    """Append the lineup slots for the positions at >= floor games, most-played
    first; with keep_modal the most-played position counts whatever its games."""
    if not counts:
        return
    modal = max(counts, key=lambda p: counts[p])
    for p, games in sorted(counts.items(), key=lambda kv: -kv[1]):
        if games < floor and not (keep_modal and p == modal):
            continue
        s = _POS_SLOT.get(p)
        if s and s not in slots:
            slots.append(s)


def _elig_positions(season: int | None = None) -> dict:
    """{mlbam: [slot, ...]} from data/fielding_innings.json for the newest
    season on it (or `season`). A position counts at >= _ELIG_MIN_GAMES games
    this season, most-played first; the modal position always counts so a
    mid-season call-up is never slotless. Under _ELIG_CARRY_GAMES appearances
    this season, the prior season's positions at >= _ELIG_CARRY_GAMES games are
    appended (the rollover carry above). Empty when the artifact is absent (fresh
    checkout), which simply leaves `elig` off the row."""
    raw = _load_json(ELIG_SOURCE)
    y, cur = _elig_season(raw, season)
    if y is None:
        return {}
    _py, prev = _elig_season(raw, y - 1)
    out: dict = {}
    for key in set(cur) | set(prev):
        try:
            mid = int(key)
        except (TypeError, ValueError):
            continue
        if not mid:
            continue
        now, before = _games_by_pos(cur.get(key)), _games_by_pos(prev.get(key))
        slots: list = []
        _add_slots(slots, now, _ELIG_MIN_GAMES, keep_modal=True)
        if sum(now.values()) < _ELIG_CARRY_GAMES:
            _add_slots(slots, before, _ELIG_CARRY_GAMES, keep_modal=not now)
        if slots:
            out[mid] = slots
    return out


def _hitter_elig(mid, elig: dict, detail: dict):
    """One hitter's served `elig`: the innings-feed slots, else the single slot
    of his mlb_player_detail position (the 2026-08-16 data-hole fallback), else
    None, which leaves the key off the row."""
    slots = elig.get(mid)
    if slots:
        return list(slots)
    slot = _POS_SLOT.get((detail.get(mid) or {}).get("pos") or "")
    return [slot] if slot else None


def _detail_by_mlbam() -> dict:
    """{mlbam: {team, name, pos}} off data/mlb_player_detail.json - the fallback
    identity join for pool players the three skill leaderboards never carried
    (see _enrich). One load, three fields kept, dict lookups after that; empty
    when the artifact is absent, which simply leaves the holes as they were."""
    raw = _load_json("mlb_player_detail.json")
    players = (raw or {}).get("players") if isinstance(raw, dict) else None
    out: dict = {}
    if not isinstance(players, dict):
        return out
    for rec in players.values():
        mid = (rec or {}).get("mlbam")
        if not mid:
            continue
        out[int(mid)] = {"team": rec.get("team"), "name": rec.get("name"),
                         "pos": rec.get("pos")}
    return out


def _injury_chip(pl: dict) -> dict:
    """The injury chip fields for one timeseries player (wiring W02, 2026-10-07).

    Copied, never derived: `il` is the PROSPX card's own il_status (type and
    placement date) when the player is on the IL right now, and `tj` is
    health_profile's Tommy John surgery date when is_post_tj is set (date None
    when only the flag is known). The client counts days and months from these
    dates, the same arithmetic PROSPX's Injured list runs. Empty dict for a
    healthy player, so the keys ride only on the rows that need them.

    DISPLAY ONLY: no score, sort or tier reads these keys. The dynasty blend
    weights are stated conventions (do-not-reopen item 14), and the chip must
    not become a sixth term."""
    out: dict = {}
    il = pl.get("il_status") or {}
    if il.get("is_on_il"):
        out["il"] = {"type": il.get("type"), "since": il.get("since")}
    hp = pl.get("health_profile") or {}
    if hp.get("is_post_tj"):
        out["tj"] = {"date": hp.get("tj_surgery_date")}
    return out


def _callup_watch(ts: dict | None = None) -> list:
    """Best-effort: fantasy-relevant prospects near the majors, from PROSPX forward
    signals (timeseries.json, a generated artifact). Empty when unavailable. Accepts
    a pre-loaded timeseries dict so build_sections parses the ~66MB file once for
    both this and the dynasty ranking."""
    if ts is None:
        ts = _load_json("timeseries.json")
    if not isinstance(ts, dict):
        return []
    out = []
    for pl in (ts.get("players") or []):
        eta = pl.get("eta")
        eta_year = eta.get("year") if isinstance(eta, dict) else eta
        near = (str(eta_year) in ("2026", "2027")) if eta_year else False
        if near and pl.get("mlbam_id"):
            # eFV leads, consensus is the fallback: this column served an
            # unlabeled consensus FV on a site whose grade is eFV, so a
            # call-up-watch row could disagree with the same player's board row.
            efv = (_efv_by_key() or {}).get(pl.get("player_key"))
            out.append({"mlbam": pl.get("mlbam_id"), "name": pl.get("player_name"),
                        "org": pl.get("org"), "pos": pl.get("position"), "eta": eta_year,
                        "fv": pl.get("consensus_fv") or pl.get("fv_close"),
                        "fvE": round(efv, 1) if efv is not None else None,
                        **_injury_chip(pl)})
    out.sort(key=lambda x: -(x.get("fvE") if x.get("fvE") is not None else (x.get("fv") or 0)))
    return out[:60]


# The blend weights and the ETA-proximity decay live in dynasty_blend (shared
# with the card market exporter until that module was removed 2026-09-05). This module carried its own copies
# until 2026-08-16, when the card clone was found decaying ETA at 0.25 against
# this module's 0.18; one importable module is the only shape that cannot
# re-diverge.


def _dynasty_tier(rank: int) -> str:
    """Rank-bucket label for the dynasty board (mirrors how ranking products group
    an ordered list into tiers)."""
    if rank <= 10:
        return "Elite"
    if rank <= 25:
        return "Tier 1"
    if rank <= 50:
        return "Tier 2"
    if rank <= 100:
        return "Tier 3"
    if rank <= 200:
        return "Tier 4"
    return "Depth"


def _dynasty_prospects(ts: dict | None, season: int, xfv: dict | None = None,
                       n: int = 300) -> list:
    """eFV-derived Dynasty Prospect rankings.

    A DISPLAY-LAYER blend (like the client's scoring re-rank), not a trained model:
    it moves no served eFV number and triggers no model gate. Joins the flagship
    eFV rows in data/xfv.json (by_player, slug-keyed) to the PROSPX prospect roster
    in timeseries.json (player_key -> mlbam / name / org / pos / ETA), then ranks
    by the shared dynasty_blend composite with THE board grade PRIMARY:

        score = _board_grade(xr)                       # primary driver, the shown eFV
              + W_STAR * p_bucket['star']              # ceiling premium (star odds)
              + W_BUST * p_bust                        # floor risk (negative weight)
              + W_ETA * eta_proximity(eta, season)     # sooner ETA = value sooner
              + W_SURPLUS * clamp(surplus_mm / 100)    # surplus composite (tiebreak)

    Driver and DISPLAYED `efv` column are the SAME number since 2026-08-16: the
    board grade PROSPX, the homepage and /projections/ serve, so the ranking can
    no longer contradict its own visible column (see the driver comment below for
    the measurement). One eFV basis across Dynasty and Call-up Watch, as before.

    Returns rows sorted desc with rank + rank-bucket tier + the eFV outcome band
    (band_p10_mm..band_p90_mm, $M). Best-effort: empty list when inputs unavailable."""
    if not isinstance(ts, dict):
        return []
    if xfv is None:
        xfv = _load_json("xfv.json")
    by_player = (xfv or {}).get("by_player")
    if not isinstance(by_player, dict):
        return []
    rows: list[dict] = []
    for pl in (ts.get("players") or []):
        key = pl.get("player_key")
        xr = by_player.get(key) if key else None
        mid = pl.get("mlbam_id")
        if not xr or not mid:
            continue
        # THE DRIVER IS THE BOARD GRADE (2026-08-16). Until today the score drove
        # on the retired xfv_grade_quantile, a scale the site displays nowhere,
        # while the row displayed _board_grade. The comment that used to sit here
        # defended that with a fear: swapping the driver would silently re-weight
        # the composite, because the weights were set against the quantile's
        # spread. Measured on the live artifacts, the fear points the wrong way.
        # On the served top-300 board, ranking on _board_grade with UNCHANGED
        # weights cut visible adjacent inversions 82 to 75, >=2pt inversions 52
        # to 20, the worst inversion 7.2 to 3.4 FV, and lifted Spearman(rank,
        # shown eFV) 0.848 to 0.951 - a variance-matched re-derivation was WORSE
        # than leaving them alone (98 inversions). The quantile now survives only
        # inside _board_grade's standing fallback chain (board_value ->
        # xfv_grade_realized -> xfv_grade_quantile), where it is a last resort,
        # not a driver. tools/dynasty_basis_probe.py reproduces the measurement.
        grade = _board_grade(xr)
        if grade is None:
            continue
        pb = xr.get("p_bucket") or {}
        star = pb.get("star") or 0.0
        bust = xr.get("p_bust")
        if bust is None:
            bust = pb.get("bust") or 0.0
        eta = pl.get("eta")
        eta_year = eta.get("year") if isinstance(eta, dict) else (eta if isinstance(eta, int) else None)
        score = dynasty_blend.blend_score(
            grade, star, bust,
            dynasty_blend.eta_proximity(eta_year, season),
            dynasty_blend.surplus_norm(xr.get("surplus_mm")))
        rows.append({
            "mlbam": mid, "name": pl.get("player_name"), "org": pl.get("org"),
            "pos": pl.get("position"), "eta": eta_year,
            "efv": round(grade, 1), "star": round(star * 100),
            "bust": round((bust or 0.0) * 100),
            "surplus": round(xr.get("surplus_mm") or 0.0),
            "band": [xr.get("band_p10_mm"), xr.get("band_p90_mm")],
            "score": round(score, 1),
            # Display-only injury chip, added AFTER the score is fixed.
            **_injury_chip(pl),
        })
    rows.sort(key=lambda r: -(r["score"] if r.get("score") is not None else -1e9))
    rows = rows[:n]
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        r["tier"] = _dynasty_tier(i + 1)
    return rows


def _start_score(p: dict, opp_org: str | None, teams_ctx: dict) -> dict | None:
    """Expected FGP for ONE start: per-start ROS points scaled by the opponent's
    offense (weaker offense → better streamer).

    THE FALLBACK 100 IS NOW LABELLED. An opponent we cannot look up still prices
    at Offense+ 100, because a league-average opponent is the honest guess and
    changing that would move served numbers. What changes is that the row says
    which kind of 100 it is: `opp_off_resolved` false means nobody measured this
    club today. Five clubs genuinely sit at 100, so an unlabelled 100 made a
    total join failure look exactly like an average lineup - and that is how the
    7-org code-set miss went unnoticed for months. The multiplier math below is
    untouched."""
    if not p:
        return None
    ros = p.get("ros") or {}
    gs = ros.get("gs") or 0
    if gs <= 0:
        return None
    per_start = (p.get("fpts_fgp") or 0) / gs
    raw_off = ((teams_ctx or {}).get(opp_org) or {}).get("offense_plus")
    resolved = isinstance(raw_off, (int, float)) and bool(raw_off)
    opp_off = raw_off if resolved else 100
    # ONE band with the DFS pitcher line (L17-F6). This used to clamp into
    # [0.6, 1.5], which is not the reciprocal of the band the same row's
    # DFS multiplier used. See matchup_mult.
    mult = matchup_mult(opp_off, side="total")
    return {"per_start_fgp": round(per_start * mult, 1),
            "per_start_base": round(per_start, 1), "opp_off": opp_off,
            "opp_off_resolved": resolved}


def _team_next7(sched7: dict | None, teams_ctx: dict) -> dict:
    """sections.team_next7: {org: [{d, opp, home, opp_off, opp_bp}, ...]} for the
    next 7 days (2026-08-16), the schedule strip the player card renders.

    The raw slate is schedule.team_sched7 (see _attach_schedule: the 7-day
    probables fetch used to be discarded once two_start was derived from it);
    this join only adds the opponent context the card colors chips by, from the
    same _teams_context the streamer and DFS boards already price against. An
    opponent the context cannot resolve carries None rather than a fabricated
    100: the card renders that chip neutral, which is the same "missing is not
    average" rule the DFS matchup mark enforces. Values are rounded to ints
    because 30 orgs x 7 games ride the corpus payload and a decimal tail is
    pure bytes on a display strip."""
    def _plus(v):
        return round(v) if isinstance(v, (int, float)) else None
    out: dict = {}
    for org, games in (sched7 or {}).items():
        rows = []
        for g in (games or [])[:7]:
            g = g or {}
            opp = g.get("opp")
            ctx = (teams_ctx or {}).get(opp) or {}
            rows.append({"d": g.get("d"), "opp": opp,
                         "home": bool(g.get("home")),
                         "opp_off": _plus(ctx.get("offense_plus")),
                         "opp_bp": _plus(ctx.get("bullpen_plus"))})
        if rows:
            out[org] = rows
    return out


def _line_share(payload: dict) -> float:
    """The part of a full-season projection the payload's lines cover: 1.0 on
    a next-season corpus, 1 - season_fraction on a rest-of-season one, and 1.0
    when the payload does not say (a payload from before 2026-09-24)."""
    if payload.get("mode") == MODE_NEXT_SEASON:
        return 1.0
    frac = payload.get("season_fraction")
    if not isinstance(frac, (int, float)):
        return 1.0
    return max(0.0, 1.0 - float(frac))


_CLOSER_DEPTH_N = 5


def _closer_role_score(r: dict) -> float:
    """The grid's hand role score: the average Leverage Index at entry (gmLI)
    dominates, saves and REM+ break ties. A role ORDER, not a saves forecast:
    the save-share model lost its gate (docs/fantasy-closer-gate-2026-08-16.md)
    and this score is the one that clause keeps."""
    return ((r.get("gmli") or 0) * 100 + (r.get("saves") or 0) * 3
            + (r.get("rem_plus") or 0) * 0.2)


def _closer_depth(lb: dict | None = None) -> tuple[dict, dict]:
    """(closer_depth, closer_rows) for the Closer Grid and the card's role chip.

    THE POPULATION IS THE RELIEVER BOARD (2026-09-24), not the rest-of-season
    pool. The grid used to group the pool's RP rows, and three things went
    wrong with that:
      * the pool thinned as the season ran out (28 RP rows on 2026-09-07, 0 on
        09-23), so the grid showed 17 keys and then none;
      * the pool marks every non-SP role RP, so starters with no gmLI
        (Bello, Assad, Fedde, Quantrill and five more) topped their clubs
        with the CLOSER chip;
      * it grouped by the raw team code, so CHW/CWS, SD/SDP and WSH/WSN
        rendered as six clubs.
    bullpen_leaderboards.relievers is the site's reliever board: 509 of its
    510 arms carry a gmLI on 2026-09-24, and every club is there. The grid
    takes its QUALIFIED arms (the board's own fixed sample rule, rem_plus.QUALIFY_MIN_*, not a
    threshold picked here) with a gmLI, keys them by the canonical org, and
    orders each club by the unchanged hand score. Without the qualified rule an
    arm with one appearance tops his club on gmLI alone.

    closer_depth keeps its {org: [mlbam, ...]} shape. closer_rows carries the
    fields the grid renders ({str(mlbam): {name, team, gmli, saves, rem_plus}})
    for every listed arm; build_sections serves the ones with no pool row, so
    both clients can draw the grid whatever the pool holds."""
    if lb is None:
        lb = _load_json("bullpen_leaderboards.json") or {}
    by_team: dict[str, list] = {}
    for r in (lb.get("relievers") or []):
        if not r.get("qualified") or r.get("gmli") is None or not r.get("mlbam"):
            continue
        org = _canon_org(r.get("team"))
        if org:
            by_team.setdefault(org, []).append(r)
    depth: dict = {}
    rows: dict = {}
    for org in sorted(by_team):
        top = sorted(by_team[org],
                     key=lambda r: (-_closer_role_score(r), int(r["mlbam"])))[:_CLOSER_DEPTH_N]
        depth[org] = [int(r["mlbam"]) for r in top]
        for r in top:
            rows[str(int(r["mlbam"]))] = {
                "name": r.get("name"), "team": org, "gmli": r.get("gmli"),
                "saves": r.get("saves"), "rem_plus": r.get("rem_plus")}
    return depth, rows


def build_sections(payload: dict) -> dict:
    """Organize the projected pool + schedule + skill context into the sections
    (eleven of them as of 2026-08-16; the count in this line has drifted twice,
    so count the keys below rather than trusting a number in prose).
    ROS/streamer/buy-sell/closer sections reference the MLB pool by mlbam (client
    resolves against `players`); the prospect sections (callup_watch, dynasty) are
    self-contained rows joined from timeseries.json + xfv.json; team_next7 is the
    per-club 7-day schedule strip the player card renders."""
    # Read the eFV grades fresh on every build (2026-09-25). run_monthly builds
    # this corpus at 6b6, then regenerates xfv.json in the chained daily run and
    # calls refresh_live in the SAME process; the one-slot cache kept Call-up
    # Watch on the grades from before the regen.
    _efv_by_key.cache_clear()
    players = payload["players"]
    # Display-only Swing+ mechanics-trend chips (attached here so the daily
    # refresh_live path re-bakes them too). Never read by any section sort.
    _attach_swing_trend(players)
    hitters = [p for p in players if p["side"] == "hit"]
    sps = [p for p in players if p.get("pos") == "SP"]
    rps = [p for p in players if p["side"] == "pit" and p.get("pos") == "RP"]
    sp_by_id = {p["mlbam"]: p for p in sps}
    teams_ctx = _teams_context()

    def rank(lst, n):
        return [p["mlbam"] for p in sorted(lst, key=lambda p: -(p.get("fpts_fgp") if p.get("fpts_fgp") is not None else -1e9))[:n]]

    sections: dict = {
        "ros_hitter": rank(hitters, 350),
        "ros_sp": rank(sps, 250),
        "ros_rp": rank(rps, 180),
    }

    # Buy-Low / Sell-High. Hitters by luck_gap (Savant xwOBA - wOBA), pitchers
    # by `luck` (wOBA - xwOBA allowed), both in wOBA points and both + when
    # results sit behind the expected stats. _buy_sell normalizes each side by
    # its own spread before the combined sort (see _buy_sell).
    sections["buy_low"], sections["sell_high"] = _buy_sell(
        players, share=_line_share(payload))

    # Closer Depth Chart: the reliever board's arms grouped by club and ordered
    # by the hand role score. See _closer_depth for the population. The inline
    # rows ride only for arms the pool does not carry: a pooled arm's skill
    # block is joined off the same reliever board row (_enrich), and the
    # corpus has a 600KB budget.
    pooled = {p["mlbam"] for p in players if p.get("side") == "pit"}
    depth, closer_rows = _closer_depth()
    sections["closer_depth"] = depth
    sections["closer_rows"] = {k: v for k, v in closer_rows.items()
                               if int(k) not in pooled}

    # Once the regular season is over there is no slate to stream or to count
    # two starts in, and the lines on `players` are next season's full-season
    # totals, which no per-start score may be cut from.
    next_season = payload.get("mode") == MODE_NEXT_SEASON

    # Daily SP Streamers — each announced probable start over the next 3 days,
    # ranked by matchup-adjusted expected FGP.
    sched = payload.get("schedule") or {}
    streamers = []
    for g in ([] if next_season else (sched.get("games") or [])):
        for me, opp in (("home", "away"), ("away", "home")):
            pp = (g.get(me) or {}).get("probable")
            if not pp or not pp.get("mlbam"):
                continue
            sc = _start_score(sp_by_id.get(pp["mlbam"]), (g.get(opp) or {}).get("org"), teams_ctx)
            if not sc:
                continue
            # is_home rides the row so the client can print vs or @; until
            # 2026-09-25 every streamer read "@" and half of them were home.
            sc.update({"mlbam": pp["mlbam"], "name": pp.get("name"), "date": g.get("date"),
                       "team": (g.get(me) or {}).get("org"), "opp_org": (g.get(opp) or {}).get("org"),
                       "is_home": me == "home",
                       "venue": (g.get("venue") or {}).get("name")})
            streamers.append(sc)
    streamers.sort(key=lambda s: -(s.get("per_start_fgp") or -1e9))
    sections["daily_streamers"] = streamers
    # Count the fallback opponents out loud. A streamer board where every row
    # carries the neutral 100 is a board with no matchup term at all, and it
    # renders exactly like a working one.
    n_unres = sum(1 for s in streamers if not s.get("opp_off_resolved"))
    if n_unres:
        log.warning("fantasy: %d of %d streamer starts could not resolve an "
                    "opponent Offense+ and are priced at the neutral 100",
                    n_unres, len(streamers))

    # Two-Start SP — pitchers with 2 starts this week (announced + projected),
    # ranked by summed expected FGP. A projected leg scores through the same
    # _start_score (the opponent multiplier only needs opp_org) and carries its
    # `projected` flag into the row payload for the client's "(proj)" suffix.
    two = []
    for mid_s, starts in ({} if next_season else (sched.get("two_start") or {})).items():
        p = sp_by_id.get(int(mid_s))
        legs, total, n_priced = [], 0.0, 0
        for st in starts:
            sc = _start_score(p, st.get("opp_org"), teams_ctx)
            leg = {"date": st.get("date"), "opp_org": st.get("opp_org"),
                   "exp_fgp": (sc or {}).get("per_start_fgp")}
            if st.get("is_home") is not None:
                leg["is_home"] = bool(st.get("is_home"))
            if st.get("projected"):
                leg["projected"] = True
            legs.append(leg)
            if leg["exp_fgp"] is not None:
                n_priced += 1
                total += leg["exp_fgp"]
        # Pool misses (spot starters / no ROS projection) still list: fall back
        # to the schedule's own probable name + org so the row never renders
        # blank. A row with NO priced leg carries total_fgp None, not 0.0: a
        # zero is a projection of zero points, and nobody projected him
        # (2026-09-24: all 30 rows of the 09-23 build read 0.0 over an empty
        # pool). None sorts last and renders as a dash.
        first = starts[0] if starts else {}
        two.append({"mlbam": int(mid_s),
                    "name": (p or {}).get("name") or first.get("name"),
                    "team": _canon_org((p or {}).get("team") or first.get("team_org")),
                    "n_starts": len(starts),
                    "total_fgp": round(total, 1) if n_priced else None,
                    "legs": legs})
    two.sort(key=lambda s: -(s.get("total_fgp") or -1e9))
    sections["two_start"] = two

    # The per-club next-7 strip for the player card, off the same 7-day slate
    # two_start already rides and the same opponent context the streamers price
    # against. Absent on a payload from before 2026-08-16, which simply renders
    # no strip.
    sections["team_next7"] = _team_next7(sched.get("team_sched7"), teams_ctx)

    # Parse the ~66MB timeseries.json ONCE for both prospect-roster sections.
    ts = _load_json("timeseries.json")
    sections["callup_watch"] = _callup_watch(ts)
    season = payload.get("season") or datetime.now(timezone.utc).year
    sections["dynasty"] = _dynasty_prospects(ts, season)
    return sections


def _attach_schedule(payload: dict) -> None:
    """Attach the next-3-day probables (streamers) and the 7-day two-start view.

    Two-start uses PROJECTED second legs (fsched.projected_two_start): probables
    only post ~4-5 days out, so requiring two ANNOUNCED starts left the section
    empty by construction. Legs keep their `projected` flag for the client."""
    try:
        s3, e3 = fsched.date_window(3)
        games3 = fsched.fetch_probables(s3, e3)
        s7, e7 = fsched.date_window(7)
        games7 = fsched.fetch_probables(s7, e7)
        starts7 = fsched.starts_index(games7)
        team_sched = fsched.team_schedule(games7)
        two = fsched.projected_two_start(starts7, team_sched, e7)
        # THE POSTSEASON SLATE, FOR /betting/ ONLY (owner decision 2026-10-01,
        # INT-A1). A separate list so `games`, which the streamer, two-start
        # and DFS boards read, stays regular-season. A failed fetch is [] and
        # the betting board simply has no postseason rows that night.
        try:
            post3 = fsched.fetch_postseason(s3, e3)
        except Exception:                                    # noqa: BLE001
            log.exception("fantasy: postseason schedule fetch failed - continuing")
            post3 = []
        payload["schedule"] = {
            "streamer_window": [s3, e3],
            "games": games3,
            "postseason_games": post3,
            "two_start": {str(m): v for m, v in two.items()},
            # The 7-day per-club slate, compacted to (date, opponent, side).
            # Until 2026-08-16 games7 was fetched and then DISCARDED once
            # two_start was derived from it; keeping this ~10KB view is what
            # lets build_sections bake the card's next-7 strip (team_next7)
            # without a second fetch, and lets a kept stale schedule keep its
            # strip too.
            "team_sched7": {org: [{"d": g.get("date"), "opp": g.get("opp_org"),
                                   "home": bool(g.get("is_home"))}
                                  for g in lst[:7]]
                            for org, lst in team_sched.items()},
            # Every ANNOUNCED probable start in the 7-day window, compacted to
            # (mlbam, date). ~2KB. The two-start ledger grades yesterday's
            # projected legs against these postings (2026-08-16); a projected
            # leg is by construction absent from this list on the day it is
            # projected, so a leg can never confirm itself.
            "announced7": [{"mlbam": s["mlbam"], "d": s.get("date")}
                           for s in starts7
                           if s.get("mlbam") and s.get("date")],
        }
    except Exception:
        log.exception("fantasy: schedule attach failed — continuing without probables")
        payload["schedule"] = {"games": [], "two_start": {}, "team_sched7": {},
                               "announced7": []}


def _record_schedule_anomaly(n_prev: int) -> None:
    """Raise an empty schedule fetch into the ingest-health RED ledger.

    Best-effort by design: this is a reporting path, and it must never be the
    reason a refresh fails. The ledger is what the deploy shell prints as
    `!!! INGEST RED`, so a silent schedule outage becomes visible instead of
    showing up days later as four empty modules."""
    _record_ingest_safe(
        "fantasy_schedule", ok=False,
        message=(f"probables fetch returned 0 game days; kept the previous "
                 f"{n_prev}-day schedule. Streamers, two-start, DFS and the "
                 f"betting slate all read this schedule."))


# ---------------------------------------------------------------------------
# Two-start projection ledger (2026-08-16). AN INSTRUMENT, NOT A MODEL.
#
# The two-start section serves PROJECTED second legs (a rest-cycle guess, see
# fsched.projected_two_start) and nothing ever measured whether those guesses
# come true. This ledger is the measurement: every projected leg served by the
# daily refresh is recorded, and when the real probable postings later confirm
# or refute it, a grade row is appended. After a few weeks the hit rate decides
# whether a rotation-order model is worth building at all; until then no served
# number moves and nothing reads this file at serve time.
#
# Durable per-box state, so it lives under .cache/ (the deploy box runs
# `git checkout -- .` nightly and would revert anything under data/).
# Append-only jsonl in the normal case; the file is BOUNDED by a documented
# compaction (rows older than _LEDGER_RETENTION_DAYS dropped, then a hard line
# cap), applied in the same write pass, so it cannot grow without limit.
# ---------------------------------------------------------------------------
LEDGER_PATH = Path(__file__).parent / ".cache" / "two_start_ledger.jsonl"
_LEDGER_RETENTION_DAYS = 120     # projections older than this have been graded
                                 # or never will be; drop them on write
_LEDGER_MAX_LINES = 50000        # hard cap behind the retention window, so a
                                 # clock bug cannot produce an unbounded file
# A posting within this many days of the projected leg is the SAME start moved,
# not a different one: rotations slide a day around off days and openers. The
# announced first leg sits >= 4 days from the projected second (the projection
# window is D+4..D+6), so it can never fall inside this slack.
_LEDGER_GRADE_SLACK_DAYS = 2


def _ledger_rows(path: Path) -> list[dict]:
    """Every parseable row of the ledger, oldest first. A corrupt line is
    skipped rather than fatal: the ledger is an instrument and a torn write
    (the box lost power mid-append) must not brick the daily refresh."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict):
            rows.append(r)
    return rows


def _rest_window(first_date: str | None) -> list | None:
    """[D+4, D+6] for an announced first leg on D: the window the projection
    was drawn from (fsched.projected_two_start's rest cycle)."""
    try:
        d0 = date.fromisoformat(first_date or "")
    except ValueError:
        return None
    return [(d0 + timedelta(days=4)).isoformat(), (d0 + timedelta(days=6)).isoformat()]


def _grade_pending(pending: list, ann_by_pid: dict, today: str) -> list:
    """Grade rows for the pending projected legs the announced postings can now
    confirm or refute. Pure. Three outcomes, graded on the POSTING (which is
    what the projection claimed would happen), not on the game result:

      * started: a probable is posted for the pitcher ON the projected date;
      * pushed: a probable is posted within _LEDGER_GRADE_SLACK_DAYS of it but
        on a different date (the start moved, the rotation-order guess held);
      * skipped: the projected date has passed and no posting ever matched
        while it was in view.

    Anything else stays pending: probables post ~4-5 days out, so a projected
    leg is UNGRADEABLE on the day it is made and that is not a miss."""
    out: list = []
    for (mid, leg_date) in pending:
        dates = ann_by_pid.get(mid) or set()
        resolved = resolved_date = None
        if leg_date in dates:
            resolved, resolved_date = "started", leg_date
        else:
            near = []
            for d in dates:
                try:
                    gap = abs((date.fromisoformat(d)
                               - date.fromisoformat(leg_date)).days)
                except ValueError:
                    continue
                if gap <= _LEDGER_GRADE_SLACK_DAYS:
                    near.append(d)
            if near:
                resolved, resolved_date = "pushed", min(near)
            elif leg_date < today:
                resolved, resolved_date = "skipped", today
        if resolved:
            out.append({"kind": "grade", "mlbam": mid, "projected_date": leg_date,
                        "resolved": resolved, "resolved_date": resolved_date,
                        "graded_on": today})
    return out


def _compact_ledger(rows: list, today: str) -> tuple[list, int]:
    """(kept rows, dropped count) under the documented bound: a row's anchor
    date (date_projected for projections, graded_on for grades) must be within
    _LEDGER_RETENTION_DAYS of today, and the survivors are hard-capped at
    _LEDGER_MAX_LINES newest."""
    try:
        cutoff = (date.fromisoformat(today)
                  - timedelta(days=_LEDGER_RETENTION_DAYS)).isoformat()
    except ValueError:
        return rows, 0
    kept = [r for r in rows
            if str(r.get("date_projected") or r.get("graded_on") or today) >= cutoff]
    if len(kept) > _LEDGER_MAX_LINES:
        kept = kept[-_LEDGER_MAX_LINES:]
    return kept, len(rows) - len(kept)


def update_two_start_ledger(two_start: dict, announced: list, *, today: str,
                            path: Path | None = None) -> dict:
    """One daily pass over the ledger: record today's served projected legs,
    grade whatever the announced postings now resolve, compact, write.

    `two_start` is the payload's schedule.two_start ({mlbam_str: [legs]}, legs
    carrying `projected` on the guessed ones); `announced` is the compact
    schedule.announced7 list ([{mlbam, d}]). Idempotent per (mlbam, projected
    leg date) per day for projections and per (mlbam, projected leg date)
    forever for grades, so re-running a refresh appends nothing new. Returns
    {projected_added, grades_added, compacted_away, n_rows} for the caller's
    log line. Never raises past its caller's try (refresh_live wraps it): the
    ledger must never be the reason a refresh fails."""
    path = Path(path) if path is not None else LEDGER_PATH
    rows = _ledger_rows(path)
    proj_seen = {(r.get("date_projected"), r.get("mlbam"), r.get("leg_date"))
                 for r in rows if r.get("kind") == "projected"}
    graded = {(r.get("mlbam"), r.get("projected_date"))
              for r in rows if r.get("kind") == "grade"}

    new_rows: list = []
    for mid_s, legs in (two_start or {}).items():
        try:
            mid = int(mid_s)
        except (TypeError, ValueError):
            continue
        legs = legs or []
        first = legs[0] if legs else {}
        for leg in legs:
            leg = leg or {}
            if not leg.get("projected"):
                continue
            leg_date = leg.get("date")
            if not leg_date:
                continue
            key = (today, mid, leg_date)
            if key in proj_seen:
                continue
            proj_seen.add(key)
            new_rows.append({
                "kind": "projected", "date_projected": today, "mlbam": mid,
                "name": leg.get("name") or first.get("name"),
                "org": leg.get("team_org") or first.get("team_org"),
                "leg_date": leg_date,
                "leg_date_window": _rest_window(first.get("date")),
                "source_row": {"opp_org": leg.get("opp_org"),
                               "is_home": leg.get("is_home"),
                               "venue": leg.get("venue")},
            })

    ann_by_pid: dict = {}
    for a in announced or []:
        m, d0 = (a or {}).get("mlbam"), (a or {}).get("d")
        if m and d0:
            ann_by_pid.setdefault(int(m), set()).add(d0)
    pending: dict = {}
    for r in rows + new_rows:
        if r.get("kind") != "projected":
            continue
        k = (r.get("mlbam"), r.get("leg_date"))
        if None in k or k in graded:
            continue
        pending[k] = True
    grades = _grade_pending(list(pending), ann_by_pid, today)
    new_rows.extend(grades)

    kept, dropped = _compact_ledger(rows, today)
    path.parent.mkdir(parents=True, exist_ok=True)
    if dropped:
        # Compaction rewrites; the normal day is a pure append.
        text = "".join(json.dumps(r, separators=(",", ":")) + "\n"
                       for r in kept + new_rows)
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    elif new_rows:
        with path.open("a", encoding="utf-8") as fh:
            for r in new_rows:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    return {"projected_added": sum(1 for r in new_rows if r["kind"] == "projected"),
            "grades_added": len(grades),
            "compacted_away": dropped,
            "n_rows": len(kept) + len(new_rows)}


def two_start_ledger_summary(path: Path | None = None) -> dict:
    """The instrument's readout: how the projected second legs have graded so
    far. Readable by a future page lane; nothing served reads it today. Legs
    are counted DISTINCT by (mlbam, projected leg date), because the same leg
    is legitimately re-served on consecutive days while it stays in the window
    and that is one guess, not several."""
    rows = _ledger_rows(Path(path) if path is not None else LEDGER_PATH)
    legs = {(r.get("mlbam"), r.get("leg_date")) for r in rows
            if r.get("kind") == "projected"}
    grades = [r for r in rows if r.get("kind") == "grade"]
    by_outcome: dict = {}
    for g in grades:
        by_outcome[str(g.get("resolved"))] = by_outcome.get(str(g.get("resolved")), 0) + 1
    n_graded = len(grades)
    started = by_outcome.get("started", 0)
    pushed = by_outcome.get("pushed", 0)
    graded_pairs = {(g.get("mlbam"), g.get("projected_date")) for g in grades}
    days = sorted({r.get("date_projected") for r in rows
                   if r.get("kind") == "projected" and r.get("date_projected")})
    return {
        "n_rows": len(rows),
        "n_projected_rows": sum(1 for r in rows if r.get("kind") == "projected"),
        "n_distinct_legs": len(legs),
        "n_graded": n_graded,
        # Counted over the legs still on file, not len(legs) - len(grades): a
        # compacted projection can leave a grade behind, and subtraction would
        # let that orphan hide a genuinely pending leg.
        "n_pending": sum(1 for k in legs if k not in graded_pairs),
        "by_outcome": by_outcome,
        # started alone is the strict read; started+pushed is the generous one
        # (the rotation-order guess held, the calendar slid). Both are served
        # so nobody has to re-derive them from the raw rows.
        "hit_rate_strict": round(started / n_graded, 3) if n_graded else None,
        "hit_rate_with_pushed": (round((started + pushed) / n_graded, 3)
                                 if n_graded else None),
        "first_projected": days[0] if days else None,
        "last_projected": days[-1] if days else None,
    }


def _restamp_elig(payload: dict, log=print) -> int:
    """RE-STAMP HITTER ELIGIBILITY EVERY NIGHT (owner decision 24, 2026-09-11:
    eligibility reads the nightly innings feed). refresh_live reuses the monthly
    rows, and dfs_export reads the `elig` baked on them before its own live
    lookup, so without this the nightly innings would reach /redraft/ and /dfs/
    only on the next monthly build. The rule is _enrich's (_hitter_elig), so a
    nightly row and a monthly row can never disagree. When the innings artifact
    is absent or empty the baked values stand: an empty read must not strip every
    hitter to UTIL. Best-effort: a failure here never fails the refresh. Returns
    the number of hitter rows whose elig changed."""
    try:
        elig = _elig_positions()
        if not elig:
            if callable(log):
                log(f"fantasy: {ELIG_SOURCE} unreadable or empty; baked elig kept")
            return 0
        detail = _detail_by_mlbam()
        n = 0
        for pl in payload.get("players") or []:
            if pl.get("side") != "hit" or pl.get("mlbam") is None:
                continue
            new = _hitter_elig(int(pl["mlbam"]), elig, detail)
            if new != pl.get("elig"):
                n += 1
            if new:
                pl["elig"] = new
            else:
                pl.pop("elig", None)
        if callable(log):
            log(f"fantasy: hitter eligibility re-stamped from {ELIG_SOURCE}, {n} changed")
        return n
    except Exception:
        logging.getLogger("fantasy_export").exception(
            "fantasy: eligibility re-stamp failed - baked elig kept")
        return 0


def refresh_live(log=print) -> int:
    """DAILY cheap refresh: reuse the monthly ROS players, re-pull the probable-
    pitcher schedule, and rebuild the schedule-driven sections (streamers,
    two-start). Skips the heavy build_corpus()/projection entirely, so it's safe
    on the daily path (and off the OOM-sensitive monthly build). No-op until the
    monthly build has created data/fantasy.json.

    A corpus with no players still gets its sections rebuilt (2026-09-25): the
    prospect sections (Dynasty, Call-up Watch) read timeseries.json and
    xfv.json, not the pool, and returning early on an empty pool froze them
    between monthly builds while PROSPX and /projections/ moved nightly."""
    payload = _load_json("fantasy.json")
    if not isinstance(payload, dict) or not isinstance(payload.get("players"), list):
        if callable(log):
            log("fantasy: no monthly fantasy.json yet — skipping daily refresh")
        return 0
    # RE-STAMP ROSTER STATUS EVERY NIGHT. This path deliberately REUSES the
    # monthly ROS players and skips the projection rebuild, which is what makes
    # it cheap; but roster status is the one field on those rows that goes stale
    # in hours rather than weeks. Without this the flag would only refresh on the
    # monthly build, so a player who hit the IL on the 3rd would read "active"
    # until the 1st of the following month, which is exactly the staleness the
    # flag exists to remove. One roster walk and a loop over ~650 rows; no
    # projection is touched.
    _active = _active_roster_ids()
    _n_off = 0
    for _pl in payload.get("players") or []:
        _mid = _pl.get("mlbam")
        if _active is None or _mid is None:
            _pl["roster_status"] = "unknown"
            continue
        _on = int(_mid) in _active
        _pl["roster_status"] = "active" if _on else "off_roster"
        _n_off += 0 if _on else 1
    payload["roster_status"] = {
        "applied": _active is not None,
        "n_off_roster": _n_off,
        "refreshed": "daily",
        "basis": "StatsAPI rosterType=active (26-man); an optioned or injured "
                 "player reads off_roster",
        "policy": ("FLAGGED, NEVER FILTERED. This is a rest-of-season board, so a "
                   "player who is out is still the row a manager most needs to see. "
                   "The lineup and rotation charts filter instead, because those are "
                   "claims about tonight."),
        "on_failure": "a roster walk covering fewer than 28 of 30 clubs flags "
                      "every player 'unknown' rather than mislabelling whole clubs",
    }
    if callable(log):
        log(f"fantasy: roster status re-stamped, {_n_off} off-roster")
    _restamp_elig(payload, log)
    # A corpus built before the canonical team codes (2026-09-25) carries the
    # leaderboards' MLB-style codes; re-key it here so the nightly fixes it
    # without waiting for the monthly build. Idempotent on canonical codes.
    for _pl in payload.get("players") or []:
        if _pl.get("team"):
            _pl["team"] = _canon_org(_pl["team"])
    # Keep the schedule we already have, so an empty fetch can be told apart from
    # a genuinely empty slate (see the guard below).
    _prev_games = ((payload.get("schedule") or {}).get("games") or {})
    _prev_sched7 = ((payload.get("schedule") or {}).get("team_sched7") or {})
    _prev_ann7 = ((payload.get("schedule") or {}).get("announced7") or [])
    _attach_schedule(payload)
    _new_games = ((payload.get("schedule") or {}).get("games") or {})
    # EMPTY-FETCH GUARD (2026-08-05). A StatsAPI hiccup during the daily refresh
    # returned zero game days mid-season, `build_sections` faithfully rebuilt
    # streamers and two-start as empty, and the resulting artifact was published
    # and committed - which dark-started FOUR surfaces at once (redraft streamers,
    # redraft two-start, the DFS slate, and the betting board, all of which read
    # this one schedule). Nothing errored, because an empty slate is a legitimate
    # state in the off-season and on an off day.
    # So: never let an empty fetch OVERWRITE a populated schedule. Losing a day of
    # freshness is recoverable on the next run; publishing four empty modules is
    # what a reader sees.
    if _prev_games and not _new_games:
        payload["schedule"]["games"] = _prev_games
        # The 7-day club slate rides the same fetch, so a kept schedule keeps
        # its next-7 strip too rather than blanking the card's chips while the
        # streamer board still shows yesterday's slate (2026-08-16).
        if _prev_sched7 and not payload["schedule"].get("team_sched7"):
            payload["schedule"]["team_sched7"] = _prev_sched7
        # The announced-starts view rides the same fetch; keeping it with the
        # kept schedule stops the two-start ledger from mis-grading a leg as
        # skipped on a day the feed was simply down (2026-08-16).
        if _prev_ann7 and not payload["schedule"].get("announced7"):
            payload["schedule"]["announced7"] = _prev_ann7
        payload["schedule"]["stale_schedule"] = True
        if callable(log):
            log("fantasy: schedule fetch returned NO game days but the previous "
                f"payload had {len(_prev_games)} - keeping the older schedule "
                "rather than publishing empty streamer/two-start/DFS/betting boards")
        _record_schedule_anomaly(len(_prev_games))
    else:
        payload.get("schedule", {}).pop("stale_schedule", None)
    payload["sections"] = build_sections(payload)
    payload["schedule_refreshed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    blob = _json_blob(payload, "fantasy_export")
    if blob is None:
        return 0                    # already logged + RED; the old file stands
    OUT_PATH.write_text(blob, encoding="utf-8")
    # The Fantasy Rank's prospect leg follows the board it was just rebuilt
    # from (the MLB leg waits for the monthly corpus, cached by export()).
    try:
        frank.refresh((payload.get("sections") or {}).get("dynasty") or [],
                      int(payload.get("season") or date.today().year), log_fn=log)
    except Exception:                                        # noqa: BLE001
        logging.getLogger("fantasy_export").exception(
            "fantasy: Fantasy Rank refresh failed - previous rank file kept")
    # The two-start ledger records what was ACTUALLY served, so it runs only
    # after the write above succeeds. Best-effort by the same doctrine as the
    # ingest ledger: an instrument must never be the reason a refresh fails.
    try:
        sched = payload.get("schedule") or {}
        res = update_two_start_ledger(sched.get("two_start") or {},
                                      sched.get("announced7") or [],
                                      today=date.today().isoformat())
        if callable(log) and (res["projected_added"] or res["grades_added"]):
            log(f"fantasy: two-start ledger +{res['projected_added']} projected, "
                f"+{res['grades_added']} graded ({res['n_rows']} rows)")
    except Exception:
        logging.getLogger("fantasy_export").exception(
            "fantasy: two-start ledger update failed - continuing")
    if callable(log):
        n = len((payload.get("sections") or {}).get("daily_streamers") or [])
        log(f"fantasy: daily schedule refresh — {n} streamer starts")
    return len(payload.get("players") or [])


def export(log=print, *, limit: int | None = None) -> int:
    """Build data/fantasy.json. Returns the player count."""
    payload = build_players(limit=limit)
    rank_inputs = payload.pop("_rank_inputs", None)
    _attach_schedule(payload)
    payload["sections"] = build_sections(payload)
    blob = _json_blob(payload, "fantasy_export")
    if blob is None:
        # The monthly corpus is the source of truth for /redraft/, /dynasty/,
        # /dfs/ and the betting slate. A corpus that will not serialize is a
        # model failure, not a quiet day, so it is raised as well as reported:
        # run_monthly's step wrapper logs it, and the previous fantasy.json
        # keeps serving rather than being replaced by nothing.
        raise ValueError("fantasy.json payload contains non-finite values")
    # EMPTY-OVERWRITE GUARD (2026-09-24). The 2026-09-23 monthly build replaced
    # a populated corpus with 0 players and nothing refused it, which darkened
    # every rest-of-season board, the DFS slate and the betting props at once.
    # No mode makes an empty pool correct (next_season serves full-season lines
    # all winter), so an empty build never replaces a populated file: the old
    # file keeps serving, the ingest ledger goes RED, and the step raises.
    n_prev = _existing_player_count()
    if payload["n_players"] == 0 and n_prev > 0:
        _record_ingest_safe(
            "fantasy_corpus", ok=False,
            message=(f"the corpus build produced 0 players (mode {payload.get('mode')}, "
                     f"fraction {payload.get('season_fraction')}); kept the previous "
                     f"{n_prev}-player fantasy.json. Redraft, DFS and the betting "
                     f"props all read it."))
        raise ValueError(f"fantasy corpus built 0 players; refusing to replace "
                         f"the {n_prev}-player file")
    DATA_DIR.mkdir(exist_ok=True)
    OUT_PATH.write_text(blob, encoding="utf-8")
    _export_rank(rank_inputs, payload, log)
    if callable(log):
        what = ("full-season " + str(payload.get("target_season"))
                if payload.get("mode") == MODE_NEXT_SEASON else "ROS")
        log(f"fantasy: {payload['n_players']} players projected {what} "
            f"({payload['season']} @ {payload['season_fraction']:.0%} elapsed)")
    return payload["n_players"]


def _export_rank(rank_inputs: dict | None, payload: dict, log=print) -> None:
    """The second output, data/fantasy_rank.json (fantasy_rank.RANK_PATH):
    the Dynasty Fantasy Rank, built off this corpus build and the Dynasty
    Board's prospects. Best-effort: it never fails the corpus, which is
    already written, and a failure keeps the previous rank file served."""
    if not rank_inputs or not rank_inputs.get("horizon"):
        return
    try:
        frank.export_from_inputs(rank_inputs,
                                 (payload.get("sections") or {}).get("dynasty") or [],
                                 log_fn=log)
    except Exception:                                        # noqa: BLE001
        logging.getLogger("fantasy_export").exception(
            "fantasy: Fantasy Rank build failed - previous rank file kept")
        _record_ingest_safe("fantasy_rank", ok=False,
                            message="the Fantasy Rank build raised; the previous "
                                    "data/fantasy_rank.json stays served")


def _existing_player_count() -> int:
    """Players in the fantasy.json on disk now, 0 when there is none."""
    try:
        prev = json.loads(Path(OUT_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(prev, dict):
        return 0
    return len(prev.get("players") or [])


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Build data/fantasy.json (ROS projections + scoring).")
    ap.add_argument("--limit", type=int, default=None, help="cap players (fast partial verify)")
    args = ap.parse_args()
    n = export(log=print, limit=args.limit)
    print(f"wrote {OUT_PATH} ({n} players)")
