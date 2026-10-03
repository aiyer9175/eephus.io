# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""data/prospx_leaderboard.json: the lazy data file of the PROSPX Leaderboards table.

Task PROSPX_1_LB_DATA (site pass 2026-10-02, SITEPASS_PLAN.md section 5.2). The
Leaderboards read `career_stats` out of the boot file today, and those rows carry
rates and a few counts only: no PA, no H/2B/3B/BB/HBP/SF, no outs, no FIP. So the
Season FIP board is empty, K-BB% cannot be printed and a season cannot be combined
across levels. This file carries the counting components instead, so every rate
recomputes from sums.

Shape (compact JSON, one file, written nightly after the timeseries export):

  generated_at, current_season, seasons: [2021, ...]
  basis: {norms, fip_constant, qualifier, team_games, combined, ...}  how every
         derived number below is built (read it, do not restate it in JS)
  team_games:  {season: {level: n}}   median completed regular-season games per
               team at the level, from the StatsAPI schedule
  level_norms: {season: {level: {...}}}  the bases the served level indexes use
  rows: one per player-season-level, plus one lvl "MiLB" row per player-season
        that sums the levels (MLB rows never enter: the owner rule the board keeps)
     hitter  {k, s, lvl, side:"hit", org, age, g, pa, ab, h, d, t, hr, bb, ibb,
              hbp, sf, so, sb, cs, [ntm], ops_plus_lvl, iso_plus}
     pitcher {k, s, lvl, side:"pit", org, age, g, gs, outs, bf, h, er, bb, hbp,
              so, hr, [ntm], fip, kbb, era_minus_lvl}
     a "MiLB" row adds lvls (the levels played, low to high) and tg (the
     exposure-weighted team games its qualifier divides by)
  current: {player_key: {statcast: {lvl: {...}}, zone: {lvl: {...}},
            indexes: {rps_plus, pow_plus, pd_plus, sc_plus, dvm_plus,
                      pstuff_plus, krp_plus}}}   current season only

Sources. The counting lines are the StatsAPI season lines for every player at the
five affiliated MiLB sports (playerPool=ALL, hydrate=team so a stint carries its
parent club), cached under .cache/prospx_lb/: a past season is fetched once and
kept, the current season refreshes after SEASON_TTL_SEC. The schedule for each
sport-season is cached the same way. Rows are kept for the current active board
only (data/timeseries.json players), joined on mlbam_id, 2021 onward.

Nothing here changes a served number. The level indexes reproduce the served
formulas (storage.py wrc_plus_level and era_minus_level, the board's ISO+, and the
board's RPS+, POW+, PD+ and pStuff+ for the current season); the test file
test_prospx_leaderboard_export.py pins the current-season values to the served
ones. Season FIP, K-BB% and the combined rows are the new derived numbers.
"""

from __future__ import annotations

import gzip
import json
import logging
import math
import os
import statistics
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT = DATA_DIR / "prospx_leaderboard.json"
CACHE_DIR = ROOT / ".cache" / "prospx_lb"

STATSAPI = "https://statsapi.mlb.com/api/v1"
_UA = {"User-Agent": "Mozilla/5.0"}

FIRST_SEASON = 2021
# A past season's lines are final; the current season refreshes once its cache
# file is older than this (the milb_history convention).
SEASON_TTL_SEC = 20 * 3600

# Affiliated MiLB sports. Sport 16 carries both rookie levels; the stint's league
# splits it into DSL (the Dominican and Venezuelan leagues) and CPX.
MILB_SPORTS = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 16: "CPX"}
LEVEL_ORDER = ("DSL", "CPX", "A", "A+", "AA", "AAA")
LEVEL_SPORT = {"AAA": 11, "AA": 12, "A+": 13, "A": 14, "CPX": 16, "DSL": 16}

# FIP's constant. ONE constant on every timeframe (plan section 5.2): the window
# engine's flat _LB_FIP_CONST in prospx/index.html, so a Season FIP and a window
# FIP agree and no window FIP moves. test_prospx_leaderboard_export pins the two.
FIP_CONSTANT = 3.10

# The MiLB rate-title rule, per level and season (SP-D4).
PA_PER_TEAM_GAME = 2.7
IP_PER_TEAM_GAME = 0.8

_HIT_FIELDS = ("g", "pa", "ab", "h", "d", "t", "hr", "bb", "ibb", "hbp", "sf",
               "so", "sb", "cs")
_PIT_FIELDS = ("g", "gs", "outs", "bf", "h", "er", "bb", "hbp", "so", "hr")
_PITCHER_POS = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP", "P"}


# ---------------------------------------------------------------------------
# StatsAPI season lines and schedules, cached
# ---------------------------------------------------------------------------

def _fetch(url: str, timeout: int = 90) -> dict:
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:                              # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def _is_dsl(league_name: str) -> bool:
    name = (league_name or "").strip()
    low = name.lower()
    return name.upper() in ("DSL", "VSL") or "dominican" in low or "venezuelan" in low


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _cache_fresh(path: Path, season: int, today: date) -> bool:
    if not path.exists():
        return False
    if season < today.year:
        return True
    return (time.time() - path.stat().st_mtime) < SEASON_TTL_SEC


def _read_cache(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_cache(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def _lean_line(s: dict, sport: int, group: str) -> dict | None:
    st = s.get("stat") or {}
    team = s.get("team") or {}
    pid = (s.get("player") or {}).get("id")
    if not pid or not team.get("id"):
        return None                       # a line with no team cannot be placed
    league = (s.get("league") or {}).get("name") or ""
    level = MILB_SPORTS[sport]
    if sport == 16 and _is_dsl(league):
        level = "DSL"
    row = {"id": int(pid), "tm": int(team["id"]), "lvl": level,
           "par": team.get("parentOrgName") or team.get("name") or "",
           "age": st.get("age"), "g": _int(st.get("gamesPlayed"))}
    if _int(s.get("numTeams")) > 1:
        row["ntm"] = _int(s.get("numTeams"))
    if group == "hitting":
        row.update({
            "pa": _int(st.get("plateAppearances")), "ab": _int(st.get("atBats")),
            "h": _int(st.get("hits")), "d": _int(st.get("doubles")),
            "t": _int(st.get("triples")), "hr": _int(st.get("homeRuns")),
            "bb": _int(st.get("baseOnBalls")), "ibb": _int(st.get("intentionalWalks")),
            "hbp": _int(st.get("hitByPitch")), "sf": _int(st.get("sacFlies")),
            "so": _int(st.get("strikeOuts")), "sb": _int(st.get("stolenBases")),
            "cs": _int(st.get("caughtStealing")),
        })
    else:
        row.update({
            "gs": _int(st.get("gamesStarted")), "outs": _int(st.get("outs")),
            "bf": _int(st.get("battersFaced")), "h": _int(st.get("hits")),
            "er": _int(st.get("earnedRuns")), "bb": _int(st.get("baseOnBalls")),
            "hbp": _int(st.get("hitBatsmen")), "so": _int(st.get("strikeOuts")),
            "hr": _int(st.get("homeRuns")),
        })
    return row


def _league_ids(sport: int, season: int) -> list[int | None]:
    """The leagues to request one by one. The season endpoint returns ONE line per
    player per request, team stints summed and labelled with the last team, so a
    sport-16 request lumps a player's DSL and complex-league games into one line
    under whichever league he finished in (measured 2026-10-02: Yolfran Castillo
    2024, 70 DSL AB + 60 ACL AB served as one 130 AB ACL line). Requesting each
    sport-16 league on its own keeps the two levels apart. The other sports are one
    level each, so one request per sport is exact."""
    if sport != 16:
        return [None]
    d = _fetch(f"{STATSAPI}/league?sportId={sport}&season={season}")
    return [int(lg["id"]) for lg in (d.get("leagues") or []) if lg.get("id")]


def season_lines(sport: int, season: int, group: str, *, fetch: bool = True,
                 today: date | None = None) -> list[dict]:
    """Every player's season line(s) at one (sport, season, group): one line per
    player and league request (see _league_ids), cached lean. [] when uncached and
    fetch is False."""
    today = today or date.today()
    path = CACHE_DIR / f"{group}_{sport}_{season}.json"
    cached = _read_cache(path)
    if cached is not None and (not fetch or _cache_fresh(path, season, today)):
        return cached
    if not fetch:
        return []
    lines: list[dict] = []
    try:
        for lid in _league_ids(sport, season):
            offset = 0
            while True:
                url = (f"{STATSAPI}/stats?stats=season&group={group}&season={season}"
                       f"&sportIds={sport}&playerPool=ALL&hydrate=team"
                       + (f"&leagueIds={lid}" if lid is not None else "")
                       + f"&limit=2000&offset={offset}")
                block = (_fetch(url).get("stats") or [{}])[0]
                page = block.get("splits") or []
                for s in page:
                    row = _lean_line(s, sport, group)
                    if row is not None:
                        lines.append(row)
                total = block.get("totalSplits") or 0
                offset += len(page)
                if not page or offset >= total:
                    break
    except Exception as e:                                  # noqa: BLE001
        log.warning("prospx_lb: %s sport=%s season=%s fetch failed: %s",
                    group, sport, season, e)
        return cached if cached is not None else []
    if not lines and cached is not None:
        return cached
    _write_cache(path, lines)
    return lines


def schedule_team_games(sport: int, season: int, *, fetch: bool = True,
                        today: date | None = None) -> dict[int, int]:
    """{team_id: completed regular-season games} for one sport-season, from the
    StatsAPI schedule. A game counts once its state is Final or Completed Early; a
    postponed or cancelled entry does not, and a made-up game counts once (gamePk)."""
    today = today or date.today()
    path = CACHE_DIR / f"schedule_{sport}_{season}.json"
    cached = _read_cache(path)
    if cached is not None and (not fetch or _cache_fresh(path, season, today)):
        return {int(k): int(v) for k, v in cached.items()}
    if not fetch:
        return {}
    try:
        d = _fetch(f"{STATSAPI}/schedule?sportId={sport}&season={season}&gameType=R")
    except Exception as e:                                  # noqa: BLE001
        log.warning("prospx_lb: schedule sport=%s season=%s fetch failed: %s",
                    sport, season, e)
        return {int(k): int(v) for k, v in (cached or {}).items()}
    done: dict[int, tuple[int, int]] = {}
    for day in d.get("dates") or []:
        for g in day.get("games") or []:
            if g.get("gameType") != "R":
                continue
            stt = g.get("status") or {}
            if stt.get("detailedState") not in ("Final", "Completed Early") \
                    and not str(stt.get("detailedState") or "").startswith("Final"):
                continue
            teams = g.get("teams") or {}
            h = ((teams.get("home") or {}).get("team") or {}).get("id")
            a = ((teams.get("away") or {}).get("team") or {}).get("id")
            if h and a:
                done[int(g.get("gamePk") or 0)] = (int(h), int(a))
    counts: dict[int, int] = defaultdict(int)
    for h, a in done.values():
        counts[h] += 1
        counts[a] += 1
    if not counts and cached is not None:
        return {int(k): int(v) for k, v in cached.items()}
    _write_cache(path, {str(k): v for k, v in counts.items()})
    return dict(counts)


# ---------------------------------------------------------------------------
# Derived numbers (one definition each, mirrored from the served formulas)
# ---------------------------------------------------------------------------

def _js_round(x: float) -> int:
    """Math.round: half rounds toward +infinity."""
    return int(math.floor(x + 0.5))


def _clamp_plus(v):
    if v is None or not math.isfinite(v):
        return None
    return max(0, min(250, _js_round(v)))


def fip(outs: int, hr: int, bb: int, hbp: int, so: int) -> float | None:
    """The window engine's _lbFip with HBP known (a season line always carries it)."""
    ip = outs / 3.0
    if ip <= 0:
        return None
    return round((13 * hr + 3 * (bb + hbp) - 2 * so) / ip + FIP_CONSTANT, 2)


def k_minus_bb_pct(so: int, bb: int, bf: int) -> float | None:
    return round(100.0 * (so - bb) / bf, 1) if bf else None


def _ip_notation(outs: int) -> float:
    """The StatsAPI's inningsPitched as a number (45.2 = 45 and two thirds), which
    is what storage.py's K_IP shrink reads off a served line."""
    return outs // 3 + (outs % 3) / 10.0


def era_minus_lvl(er: int, outs: int, avg_era: float | None, k_ip: float) -> int | None:
    """storage.py era_minus_level: the line's ERA (the API's two-decimal string)
    shrunk toward the level's average ERA by IP (in the API's X.Y notation)."""
    if not outs or not avg_era:
        return None
    # The API rounds its ERA string half up (31 ER in 40 IP prints 6.98); float
    # round() would give 6.97 and move the index by a point.
    from decimal import Decimal, ROUND_HALF_UP
    era = float((Decimal(27 * er) / Decimal(outs)).quantize(Decimal("0.01"),
                                                             rounding=ROUND_HALF_UP))
    ip = _ip_notation(outs)
    era_adj = (ip * era + k_ip * avg_era) / (ip + k_ip)
    return round(era_adj / avg_era * 100)


def _woba_parts(c: dict) -> tuple[float, float]:
    """(base-weight numerator, denominator) of wrc_rates' wOBA-lite."""
    import wrc_rates
    ubb = max(0.0, float(c["bb"] - c["ibb"]))
    comp = {"ubb": ubb, "hbp": float(c["hbp"]),
            "b1": float(c["h"] - c["d"] - c["t"] - c["hr"]), "b2": float(c["d"]),
            "b3": float(c["t"]), "hr": float(c["hr"])}
    num = wrc_rates._woba_num(comp, wrc_rates.BASE_W)
    den = float(c["ab"]) + ubb + float(c["sf"]) + float(c["hbp"])
    return num, den


def ops_plus_lvl(level_rows: list[dict], season: int, norms_season: dict,
                 k_wrc_pa: float) -> int | None:
    """The board's OPS+ lvl (prospx _lvlPlus reads storage's wrc_plus_level): the
    wOBA-lite of the summed components, each level's numerator on its own
    sport-season scale, against the PA-weighted league wOBA of those levels,
    shrunk by K_WRC_PA plate appearances."""
    num = den = pa = lw_pa = 0.0
    for r in level_rows:
        nl = norms_season.get(r["lvl"]) or {}
        scale, lw = nl.get("woba_scale"), nl.get("lg_woba")
        if scale is None or not lw or not r["pa"]:
            return None
        n, dd = _woba_parts(r)
        num += n * scale
        den += dd
        pa += r["pa"]
        lw_pa += lw * r["pa"]
    if den <= 0 or pa <= 0:
        return None
    # wrc_rates stores a player's wOBA at five decimals before storage shrinks it.
    w, lw = round(num / den, 5), lw_pa / pa
    adj = (pa * w + k_wrc_pa * lw) / (pa + k_wrc_pa)
    return round(adj / lw * 100)


def iso_plus(ab: int, h: int, d: int, t: int, hr: int, g: int,
             avg_iso: float | None) -> int | None:
    """The board's computeIsoPlus: ISO over the level's average ISO, shrunk toward
    100 by AB (PLUS_STABILIZE.iso = 150), gated at 20 games."""
    if g < 20 or not ab or not avg_iso or avg_iso <= 0:
        return None
    iso = (d + 2 * t + 3 * hr) / ab
    raw = 100.0 * iso / avg_iso
    rel = ab / (ab + 150.0)
    return _clamp_plus(100 + (raw - 100) * rel)


# ---------------------------------------------------------------------------
# Current-season model indexes: the board's own definitions
# ---------------------------------------------------------------------------
# rps_plus, pow_plus and pd_plus are computed in the browser today (prospx
# _buildRpsPlusCache / computePowerPlus / computeDisciplinePlus over DATA.players)
# and their inputs (statcast_metrics among them) are leaving the boot file. They
# are carried here so the table keeps printing the SAME numbers; the functions
# below are line-for-line mirrors over the same pool, and
# test_prospx_leaderboard_export pins the JS bodies they mirror, so an edit to
# either side fails a test instead of drifting. sc_plus, dvm_plus, pstuff_plus and
# krp_plus are already server-baked and are copied, not recomputed.

_RPS_POS_MULT = {"C": 1.08, "MI": 1.05, "CF": 1.04, "CI": 1.00, "INF": 1.02,
                 "OF": 0.99, "COF": 0.97, "DH": 0.92, "P": 1.00}
_TOOL_PTS = [(20, 40), (30, 60), (40, 85), (45, 92), (50, 100),
             (55, 114), (60, 122), (65, 134), (70, 144), (80, 158)]


def _num(v):
    """JS Number() for the payload's scalars: None for null/undefined/NaN."""
    if v is None or isinstance(v, bool):
        return None if v is None else float(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _position_bucket(pos):
    if not pos:
        return None
    toks = [t.strip().upper() for t in str(pos).split("/") if t.strip()]
    if not toks:
        return None
    for role in ("SIRP", "MIRP", "SP", "RP"):
        if role in toks:
            return role
    if any(t in ("RHP", "LHP", "P") for t in toks):
        return "P"
    if "C" in toks:
        return "C"
    for w in ("SS", "2B", "3B", "1B"):
        if w in toks:
            return w
    if any(t in ("INF", "IF", "MI", "UTIL") for t in toks):
        return "INF"
    for w in ("CF", "LF", "RF"):
        if w in toks:
            return w
    if "OF" in toks:
        return "OF"
    if "DH" in toks:
        return "DH"
    return None


def _rps_group(pos):
    b = _position_bucket(pos)
    if not b:
        return None
    return {"C": "C", "SS": "MI", "2B": "MI", "1B": "CI", "3B": "CI", "CF": "CF",
            "LF": "COF", "RF": "COF", "OF": "OF", "INF": "INF", "DH": "DH",
            "P": "P"}.get(b)


def _lvl_plus(sl):
    v = sl.get("wrc_plus_level")
    return v if v is not None else sl.get("ops_plus_level")


def _rel_prod(p):
    sl = p.get("statline") or {}
    avl = p.get("age_vs_level") or {}
    age_adj = -avl["diff"] * 10 if avl.get("diff") is not None else 0
    if sl.get("is_pitcher"):
        if sl.get("era_minus_level") is None:
            return None
        if (_num(sl.get("ip")) or 0) < 15:
            return None
        return _js_round((100 - sl["era_minus_level"]) + age_adj)
    lp = _lvl_plus(sl)
    if lp is None:
        return None
    if (_num(sl.get("games")) or 0) < 15:
        return None
    return _js_round((lp - 100) + age_adj)


def rps_plus_pool(players: list[dict]) -> dict[str, int]:
    """prospx _buildRpsPlusCache over the board pool -> {player_key: plus}."""
    buckets: dict[str, list] = defaultdict(list)
    age_buckets: dict[int, list] = defaultdict(list)
    rows = []
    for p in players:
        raw = _rel_prod(p)
        if raw is None or p.get("age") is None:
            continue
        ab = int(math.floor(p["age"]))
        ab = 25 if ab >= 25 else ab
        pos = p.get("position_observed") or p.get("position")
        g = _rps_group(pos)
        key = f"{ab}::{g or '?'}"
        mult = _RPS_POS_MULT.get(g, 1.00) if g else 1.00
        rows.append((p["player_key"], key, ab, raw, mult))
        buckets[key].append(raw)
        age_buckets[ab].append(raw)
    out = {}
    for pk, key, ab, raw, mult in rows:
        arr = buckets[key]
        if len(arr) >= 30:
            m = sum(arr) / len(arr)
        else:
            arr = age_buckets[ab]
            m = sum(arr) / len(arr)
        plus = (100 * (raw + 100) / (m + 100)) if m > 0 else (100 + (raw - m))
        plus = plus * mult
        out[pk] = _js_round(max(0, min(250, plus)))
    return out


def _tool_to_plus(grade):
    g = _num(grade)
    if g is None:
        return None
    if g <= _TOOL_PTS[0][0]:
        return _TOOL_PTS[0][1]
    if g >= _TOOL_PTS[-1][0]:
        return _TOOL_PTS[-1][1]
    for (x0, y0), (x1, y1) in zip(_TOOL_PTS, _TOOL_PTS[1:]):
        if x0 <= g <= x1:
            return y0 + (y1 - y0) * (g - x0) / (x1 - x0)
    return 100 + (g - 50) * 2


def _pwr_grade(grades):
    if grades.get("pwr") is not None:
        return grades["pwr"]
    g, r = grades.get("game_pwr"), grades.get("raw_pwr")
    if g is not None and r is not None:
        return (_num(g) + _num(r)) / 2
    return g if g is not None else r


def _perf(level_norms, level):
    return ((level_norms.get(level) or {}).get("perf")) or {}


def pow_plus(p, level_norms):
    """prospx computePowerPlus(p).value."""
    sl = p.get("statline")
    if not sl or sl.get("is_pitcher"):
        return None
    grades = (p.get("tools") or {}).get("grades") or {}
    ab = _num(sl.get("ab")) or 0
    stat = None
    if (_num(sl.get("games")) or 0) >= 20:
        lg = _perf(level_norms, sl.get("level")).get("avg_iso")
        iso = _num(sl.get("iso")) if sl.get("iso") is not None else None
        if lg is not None and lg > 0 and iso is not None:
            stat = 100 * iso / lg
    stat_rel = None if stat is None else ab / (ab + 150)
    cq = ((p.get("statcast_metrics") or {}).get("contact_quality")) or {}
    hh, brl = _num(cq.get("hard_hit_pct")), _num(cq.get("barrel_pct"))
    parts = [(100 * hh / 40.5 if hh is not None and hh > 0 else None, 0.55),
             (100 * brl / 8.8 if brl is not None and brl > 0 else None, 0.45)]
    s = w = 0.0
    for v, wt in parts:
        if v is not None:
            s += v * wt
            w += wt
    sc = None if w == 0 else _clamp_plus(s / w)
    bbe = _num(cq.get("batted_balls")) or 0
    sc_rel = None if sc is None else bbe / (bbe + 40)
    tool = _tool_to_plus(_pwr_grade(grades))

    def c01(r):
        return max(0.0, min(1.0, 1.0 if r is None else r))
    tot = wsum = 0.0
    for v, wt in ((stat, 0.45 * c01(stat_rel)), (sc, 0.25 * c01(sc_rel)), (tool, 0.30)):
        if v is not None and math.isfinite(v) and wt > 0:
            tot += v * wt
            wsum += wt
    return None if wsum == 0 else _clamp_plus(tot / wsum)


def pd_sigmas(players):
    """prospx _pdSigmas: per-level population sd of BB% - K% (n >= 30), pooled."""
    by_level: dict[str, list] = defaultdict(list)
    allv = []
    for q in players:
        s = q.get("statline")
        if not s or s.get("is_pitcher") or not s.get("level"):
            continue
        if (_num(s.get("games")) or 0) < 20:
            continue
        if s.get("bb_pct") is None or s.get("k_pct") is None:
            continue
        diff = _num(s["bb_pct"]) - _num(s["k_pct"])
        by_level[s["level"]].append(diff)
        allv.append(diff)

    def sd(arr):
        if len(arr) < 30:
            return None
        m = sum(arr) / len(arr)
        v = sum((x - m) ** 2 for x in arr) / len(arr)
        return math.sqrt(v) if v > 0 else None
    levels = {lv: sd(a) for lv, a in by_level.items() if sd(a)}
    return levels, (sd(allv) or 9.0)


def pd_plus(p, level_norms, sigmas):
    """prospx computeDisciplinePlus(p).value."""
    sl = p.get("statline")
    if not sl or sl.get("is_pitcher"):
        return None
    grades = (p.get("tools") or {}).get("grades") or {}
    raw = None
    if (_num(sl.get("games")) or 0) >= 20:
        perf = _perf(level_norms, sl.get("level"))
        if None not in (sl.get("bb_pct"), sl.get("k_pct"), perf.get("avg_bb_pct"),
                        perf.get("avg_k_pct")):
            pdiff = _num(sl["bb_pct"]) - _num(sl["k_pct"])
            ldiff = perf["avg_bb_pct"] - perf["avg_k_pct"]
            levels, pooled = sigmas
            sigma = levels.get(sl.get("level")) or pooled
            if sigma > 0:
                raw = _clamp_plus(100 + 10 * (pdiff - ldiff) / sigma)
    tool = _tool_to_plus(grades.get("pitch_sel"))
    if raw is None and tool is None:
        return None
    # (1 - 0.7) as the board writes it, 0.30000000000000004, which settles five
    # half-point roundings on the live pool.
    v = (0.7 * raw + (1 - 0.7) * tool) if (raw is not None and tool is not None) \
        else (raw if raw is not None else tool)
    return _clamp_plus(v)


def pstuff_plus(p, level_norms):
    """prospx computeStuffPlus: the server-baked stf_plus_periph when present."""
    sl = p.get("statline")
    if not sl or not sl.get("is_pitcher"):
        return None
    baked = _num(sl.get("stf_plus_periph"))
    if baked is not None:
        return _clamp_plus(baked)
    ip = _num(sl.get("ip")) or 0
    bf = _num(sl.get("tbf") if sl.get("tbf") is not None else sl.get("batters_faced")) or 0
    if ip < 20 and bf < 30:
        return None
    perf = _perf(level_norms, sl.get("level"))

    def z(val_key, mu_key, std_key, invert):
        raw, mu = sl.get(val_key), _num(perf.get(mu_key))
        if raw is None or perf.get(mu_key) is None:
            return None
        v = _num(raw)
        if v is None or mu is None or mu == 0:
            return None
        emp = _num(perf.get(std_key))
        sigma = emp if (emp is not None and emp > 0) else 0.15 * mu
        if not sigma > 0:
            return None
        zz = (v - mu) / sigma
        return -zz if invert else zz
    parts = [(0.55, z("k_pct", "avg_pitcher_k_pct", "std_pitcher_k_pct", False)),
             (0.30, z("bb_pct", "avg_pitcher_bb_pct", "std_pitcher_bb_pct", True)),
             (0.15, z("hr_per_9", "avg_hr_per_9", "std_hr_per_9", True))]
    parts = [(w, v) for w, v in parts if v is not None and math.isfinite(v)]
    if not parts:
        return None
    wsum = sum(w for w, _ in parts)
    return _clamp_plus(100 + 10 * sum(w * v for w, v in parts) / wsum)


# ---------------------------------------------------------------------------
# Statcast and zone, current season, per level (the board's statcastValue)
# ---------------------------------------------------------------------------

_HARD_TYPES = ("FF", "SI", "FT", "FC")


def _fb_feed(pm, attr):
    hard = [x for x in (pm.get("pitch_summary") or [])
            if x.get("pitch_type") in _HARD_TYPES and x.get(attr) is not None]
    if not hard:
        return None
    hard.sort(key=lambda x: -(x.get("count") or 0))
    return hard[0][attr]


def _statcast_by_level(sc: dict | None, season: int) -> dict:
    if not sc or sc.get("season") != season:
        return {}
    splits = sc.get("level_splits") or [sc]
    out = {}
    for sp in splits:
        if not sp or sp.get("season") != season or not sp.get("level"):
            continue
        cq = sp.get("contact_quality") or {}
        pm = sp.get("pitch_movement") or {}
        rec = {
            "batted_balls": cq.get("batted_balls"),
            "avg_ev": cq.get("avg_ev"), "hard_hit_pct": cq.get("hard_hit_pct"),
            "barrel_pct": cq.get("barrel_pct"),
        }
        if sp.get("is_pitcher"):
            ff = next((x for x in (pm.get("pitch_summary") or [])
                       if x.get("pitch_type") == "FF"), None)
            rec.update({"tracked_pitches": pm.get("tracked_pitches"),
                        "fb_velo_feed": _fb_feed(pm, "avg_velo"),
                        "fb_ivb_feed": _fb_feed(pm, "avg_ivb"),
                        "ivb_ff": ff.get("avg_ivb") if ff else None})
        else:
            rec.update({"p90_ev": cq.get("p90_ev"), "max_ev": cq.get("max_ev"),
                        "pull_air_pct": (cq.get("spray") or {}).get("pull_air_pct"),
                        "xwoba_est": cq.get("xwoba_est"),
                        "xwobacon_est": cq.get("xwobacon_est")})
        rec = {k: v for k, v in rec.items() if v is not None}
        if rec:
            out.setdefault(sp["level"], rec)
    return out


def _zone_by_level(zm: dict | None, season: int) -> dict:
    if not zm:
        return {}
    splits = zm.get("level_splits") or [zm]
    out = {}
    for z in splits:
        if not z or z.get("season") != season or not z.get("level"):
            continue
        rec = {k: z.get(k) for k in ("pitches", "z_swing_pct", "z_contact_pct",
                                     "o_swing_pct", "whiff_pct")}
        rec = {k: v for k, v in rec.items() if v is not None}
        if rec:
            out.setdefault(z["level"], rec)
    return out


# ---------------------------------------------------------------------------
# Level norms per season (the bases the served level indexes use)
# ---------------------------------------------------------------------------

def _wrc_basis() -> tuple[dict, dict]:
    """(sport-season wOBA scale, (season, level) league wOBA) on wrc_rates' basis:
    the scale is the build_index step-1 rescale; the league pool is build_index's."""
    import wrc_rates
    rows = wrc_rates.load_rows()
    agg: dict = defaultdict(lambda: defaultdict(float))
    for r in rows:
        a = agg[(r["sport"], r["season"])]
        for k, v in r["c"].items():
            a[k] += v
    scales = {}
    for key, a in agg.items():
        den = wrc_rates._woba_den(a)
        obp_den = a["ab"] + a["bb"] + a["hbp"] + a["sf"]
        if den <= 0 or obp_den <= 0:
            continue
        lg_obp = (a["h"] + a["bb"] + a["hbp"]) / obp_den
        base = wrc_rates._woba_num(a, wrc_rates.BASE_W) / den
        scales[key] = (lg_obp / base) if base > 0 else 1.0
    _idx, leagues = wrc_rates.build_index()
    return scales, leagues


def build_level_norms(seasons: list[int], current_season: int,
                      career_stats: dict, birth_dates: dict,
                      today: date | None = None) -> dict:
    """{season: {level: norms}} for every MiLB level-season.

    perf norms (avg_era, avg_iso, avg_bb_pct, avg_k_pct, ...) are
    level_norms.compute_level_norms on the served inputs (the stored career rows
    and birth dates) with the season as the window's end and nothing later in the
    pool; for the current season that is the served timeseries level_norms, value
    for value. lg_woba and woba_scale are wrc_rates' league wOBA and sport-season
    scale, the basis of the served wrc_plus_level."""
    from level_norms import compute_level_norms
    today = today or date.today()
    scales, leagues = _wrc_basis()
    keep = ("avg_ops", "avg_avg", "avg_iso", "avg_bb_pct", "avg_k_pct", "avg_era",
            "avg_whip", "avg_hr_per_9", "avg_pitcher_k_pct", "avg_pitcher_bb_pct",
            "std_pitcher_k_pct", "std_pitcher_bb_pct", "std_hr_per_9",
            "sample_n_ops", "sample_n_era")
    out: dict = {}
    for s in seasons:
        upto = {k: [r for r in (rows or []) if (r.get("season") or 0) <= s]
                for k, rows in career_stats.items()}
        ln = compute_level_norms(upto, birth_dates,
                                 today=today if s == current_season else date(s, 7, 1))
        sea = {}
        for lvl in LEVEL_ORDER:
            perf = (ln.get(lvl) or {}).get("perf") or {}
            rec = {k: perf[k] for k in keep if perf.get(k) is not None}
            lg = leagues.get((s, lvl))
            sc = scales.get((LEVEL_SPORT[lvl], s))
            if lg and sc:
                # Full precision: a six-decimal copy moved one served OPS+ lvl by a
                # point at a half boundary (Ayden Johnson, DSL 2026, 96 vs 95).
                rec["lg_woba"] = lg["woba"]
                rec["woba_scale"] = sc
                rec["lg_n"] = lg["n"]
            if rec:
                sea[lvl] = rec
        out[str(s)] = sea
    return out


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------

def _age_on(birth: str | None, season: int, fallback) -> float | None:
    if birth:
        try:
            bd = date.fromisoformat(birth[:10])
            return round((date(season, 7, 1) - bd).days / 365.25, 1)
        except ValueError:
            pass
    f = _num(fallback)
    return round(f, 1) if f is not None else None


def _is_pitcher(p: dict) -> bool:
    sl = p.get("statline") or {}
    if sl.get("is_pitcher") is not None:
        return bool(sl["is_pitcher"])
    return _position_bucket(p.get("position")) in ("SIRP", "MIRP", "SP", "RP", "P")


def _canonical(name: str) -> str | None:
    try:
        from trades import canonical_org
        return canonical_org(name) if name else None
    except Exception:                                       # noqa: BLE001
        return name or None


def build(*, fetch: bool = True, today: date | None = None,
          data_dir: Path = DATA_DIR) -> dict:
    today = today or date.today()
    boot = json.loads((data_dir / "timeseries.json").read_text(encoding="utf-8"))
    players = boot.get("players") or []
    try:
        xfv = json.loads((data_dir / "xfv.json").read_text(encoding="utf-8"))
        xfv_by = xfv.get("by_player") or {}
    except (OSError, ValueError):
        xfv_by = {}

    by_id: dict[int, dict] = {}
    for p in players:
        mid = p.get("mlbam_id")
        if mid and p.get("player_key"):
            by_id.setdefault(int(mid), p)

    from rate_stabilization import K_IP
    from storage import K_WRC_PA, load_birth_dates, load_career_stats

    # Season lines and schedules.
    seasons_all = list(range(FIRST_SEASON, today.year + 1))
    team_level: dict[tuple[int, int], str] = {}
    lines: dict[tuple, list] = defaultdict(list)       # (id, season, lvl, side)
    for season in seasons_all:
        for sport in MILB_SPORTS:
            for group, side in (("hitting", "hit"), ("pitching", "pit")):
                for ln in season_lines(sport, season, group, fetch=fetch, today=today):
                    team_level[(season, ln["tm"])] = ln["lvl"]
                    p = by_id.get(ln["id"])
                    if p is None or (side == "pit") != _is_pitcher(p):
                        continue
                    lines[(ln["id"], season, ln["lvl"], side)].append(ln)

    team_games: dict[str, dict] = {}
    for season in seasons_all:
        per_level: dict[str, list] = defaultdict(list)
        for sport in MILB_SPORTS:
            for tm, n in schedule_team_games(sport, season, fetch=fetch, today=today).items():
                lvl = team_level.get((season, tm))
                if lvl and n:
                    per_level[lvl].append(n)
        if per_level:
            team_games[str(season)] = {lv: int(round(statistics.median(v)))
                                       for lv, v in sorted(per_level.items(),
                                                           key=lambda kv: LEVEL_ORDER.index(kv[0]))}

    seasons = sorted({k[1] for k in lines})
    current_season = max(seasons) if seasons else today.year
    level_norms = build_level_norms(seasons, current_season, load_career_stats(),
                                    load_birth_dates(), today=today)

    # Level rows, then one MiLB row per player-season.
    rows: list[dict] = []
    grouped: dict[tuple, list] = defaultdict(list)
    for (mid, season, lvl, side), stints in lines.items():
        p = by_id[mid]
        fields = _HIT_FIELDS if side == "hit" else _PIT_FIELDS
        tot = {f: sum(_int(s.get(f)) for s in stints) for f in fields}
        expo = "pa" if side == "hit" else "bf"
        if not tot[expo] and not tot.get("outs"):
            continue
        main = max(stints, key=lambda s: _int(s.get(expo)))
        row = {"k": p["player_key"], "s": season, "lvl": lvl, "side": side,
               "org": _canonical(main.get("par")),
               "age": _age_on(p.get("birth_date"), season, main.get("age"))}
        row.update(tot)
        ntm = sum(_int(s.get("ntm")) or 1 for s in stints)
        if ntm > 1:
            row["ntm"] = ntm
        grouped[(p["player_key"], season, side)].append(row)

    for (pk, season, side), lrows in sorted(grouped.items()):
        lrows.sort(key=lambda r: LEVEL_ORDER.index(r["lvl"]))
        ns = level_norms.get(str(season)) or {}
        tg_s = team_games.get(str(season)) or {}
        for r in lrows:
            _derive(r, [r], season, ns, K_WRC_PA, K_IP)
            rows.append(r)
        fields = _HIT_FIELDS if side == "hit" else _PIT_FIELDS
        expo = "pa" if side == "hit" else "outs"
        comb = {"k": pk, "s": season, "lvl": "MiLB", "side": side,
                "lvls": [r["lvl"] for r in lrows]}
        top = max(lrows, key=lambda r: r[expo])
        comb["org"] = top["org"]
        comb["age"] = lrows[0]["age"]
        for f in fields:
            comb[f] = sum(r[f] for r in lrows)
        wsum = sum(r[expo] for r in lrows)
        if wsum and all(tg_s.get(r["lvl"]) for r in lrows):
            comb["tg"] = round(sum(r[expo] * tg_s[r["lvl"]] for r in lrows) / wsum, 1)
        _derive(comb, lrows, season, ns, K_WRC_PA, K_IP)
        rows.append(comb)

    # Current-season statcast, zone and model indexes.
    ln_served = boot.get("level_norms") or {}
    rps = rps_plus_pool(players)
    sig = pd_sigmas(players)
    current: dict[str, dict] = {}
    for p in players:
        pk = p.get("player_key")
        if not pk:
            continue
        idx = {
            "rps_plus": rps.get(pk),
            "pow_plus": pow_plus(p, ln_served),
            "pd_plus": pd_plus(p, ln_served, sig),
            "sc_plus": _num(p.get("statcast_plus")),
            "dvm_plus": _num(p.get("dollar_dvm_plus")),
            "pstuff_plus": pstuff_plus(p, ln_served),
            "krp_plus": _num((xfv_by.get(pk) or {}).get("krp_plus")),
        }
        # The board's "+" boards read the current statline only and gate on its
        # season, so a player whose statline is a prior season carries none here.
        if (p.get("statline") or {}).get("season") != current_season:
            idx = {}
        idx = {k: (int(v) if isinstance(v, float) and v.is_integer() else v)
               for k, v in idx.items() if v is not None}
        rec = {"statcast": _statcast_by_level(p.get("statcast_metrics"), current_season),
               "zone": _zone_by_level(p.get("zone_metrics"), current_season),
               "indexes": idx}
        rec = {k: v for k, v in rec.items() if v}
        if rec:
            current[pk] = rec

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "current_season": current_season,
        "seasons": seasons,
        "basis": _basis(K_WRC_PA, K_IP),
        "team_games": team_games,
        "level_norms": level_norms,
        "rows": rows,
        "current": current,
    }


def _derive(r: dict, level_rows: list[dict], season: int, ns: dict,
            k_wrc_pa: float, k_ip: float) -> None:
    """The row's derived numbers, in place."""
    if r["side"] == "hit":
        v = ops_plus_lvl(level_rows, season, ns, k_wrc_pa)
        if v is not None:
            r["ops_plus_lvl"] = v
        ab = sum(x["ab"] for x in level_rows)
        if ab and all((ns.get(x["lvl"]) or {}).get("avg_iso") for x in level_rows):
            lg_iso = sum(x["ab"] * ns[x["lvl"]]["avg_iso"] for x in level_rows) / ab
            v = iso_plus(r["ab"], r["h"], r["d"], r["t"], r["hr"], r["g"], lg_iso)
            if v is not None:
                r["iso_plus"] = v
        return
    f = fip(r["outs"], r["hr"], r["bb"], r["hbp"], r["so"])
    if f is not None:
        r["fip"] = f
    kb = k_minus_bb_pct(r["so"], r["bb"], r["bf"])
    if kb is not None:
        r["kbb"] = kb
    outs = sum(x["outs"] for x in level_rows)
    if outs and all((ns.get(x["lvl"]) or {}).get("avg_era") for x in level_rows):
        lg_era = sum(x["outs"] * ns[x["lvl"]]["avg_era"] for x in level_rows) / outs
        v = era_minus_lvl(r["er"], r["outs"], lg_era, k_ip)
        if v is not None:
            r["era_minus_lvl"] = v


def _basis(k_wrc_pa: float, k_ip: float) -> dict:
    return {
        "source": "MLB StatsAPI season lines (stats=season, playerPool=ALL): one line "
                  "per player per sport, and per league at sport 16 so DSL and CPX stay "
                  "apart; current active board only (timeseries players), MLB never",
        "fip_constant": FIP_CONSTANT,
        "fip": "(13*HR + 3*(BB+HBP) - 2*SO) / (outs/3) + fip_constant, the window "
               "engine's formula and constant",
        "kbb": "100 * (SO - BB) / BF",
        "qualifier": {"pa_per_team_game": PA_PER_TEAM_GAME,
                      "ip_per_team_game": IP_PER_TEAM_GAME,
                      "rule": "MiLB rate-title rule per level and season; a MiLB row "
                              "divides by tg, its exposure-weighted team games"},
        "team_games": "median completed regular-season games per team at the level, "
                      "StatsAPI schedule (Final or Completed Early, once per gamePk)",
        "norms": {
            "perf": "level_norms.compute_level_norms on the stored career rows and "
                    "birth dates, window ending at the season, nothing later; the "
                    "current season equals the served timeseries level_norms",
            "lg_woba": "wrc_rates league wOBA-lite of the (season, level) pool",
            "woba_scale": "wrc_rates sport-season rescale (league wOBA = league OBP)",
        },
        "ops_plus_lvl": f"storage wrc_plus_level: wOBA-lite vs lg_woba, shrunk by "
                        f"K_WRC_PA = {k_wrc_pa:g} PA (the board's OPS+ lvl)",
        "era_minus_lvl": f"storage era_minus_level: ERA vs avg_era, shrunk by "
                         f"K_IP = {k_ip:g} IP in the API's X.Y notation",
        "iso_plus": "the board's ISO+: ISO vs avg_iso, shrunk toward 100 by AB/(AB+150), "
                    "20 games minimum",
        "combined": "a MiLB row sums its levels; its OPS+ lvl, ISO+ and ERA- lvl use "
                    "the PA-, AB- and outs-weighted norms of those levels",
        "current": "statcast and zone per level for the current season; indexes are "
                   "the board's current-statline values",
    }


def gzip_bytes(payload: dict) -> int:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return len(gzip.compress(raw, compresslevel=9))


def write(payload: dict, out: Path = OUT) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, out)
    return out


def export(*, fetch: bool = True, out: Path = OUT, data_dir: Path = DATA_DIR) -> dict:
    """Build and write data/prospx_leaderboard.json; returns a small summary."""
    t0 = time.monotonic()
    payload = build(fetch=fetch, data_dir=data_dir)
    if not payload["rows"]:
        log.warning("prospx_lb: no rows built; keeping the prior file")
        return {"rows": 0, "written": False}
    write(payload, out)
    return {"rows": len(payload["rows"]), "players": len({r["k"] for r in payload["rows"]}),
            "current": len(payload["current"]), "seasons": payload["seasons"],
            "gzip_bytes": gzip_bytes(payload), "written": True,
            "elapsed_s": round(time.monotonic() - t0, 1)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-fetch", action="store_true",
                    help="cache only, no StatsAPI request")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(json.dumps(export(fetch=not a.no_fetch), indent=1))
