# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pitch rates: P/IP, P/BF, P/PA and PAR. The ONE definition every consumer imports.

Owner asks 10, 11 and 12 of 2026-09-30 (plan Part 8, item P8.1; the lane design is
part8/pitch_metrics.md sections 2 to 4). This module owns:

  * the rates. Innings are outs / 3, always: a line of "6.1" is 19 outs, never 6.1
    innings (outs_from_ip, the bullpen_export.ip_to_float rule). P/IP = pitches /
    (outs / 3); P/BF = pitches / batters faced; P/PA = pitches seen / plate
    appearances. A zero or missing denominator gives None, never 0 and never inf.
  * the league anchors, POOLED: the sum of pitches over the sum of outs x 3 (or
    over the sum of PA or BF). Never an average of player rates. MLB pitchers
    anchor to the league ROLE line (every start, or every relief outing, from
    StatsAPI's sp/rp statSplits); hitters to every non-pitcher's line; MiLB to the
    (level, season) and the same role.
  * the tracking guard. MiLB pitch counts are real only where Gameday logged every
    pitch; an untracked level-season prints about 1.7 to 2.5 pitches per PA. A
    level-season is "usable" only when every club with TRACK_MIN_TEAM_PA or more PA
    sees TRACK_MIN_TEAM_P_PA or more pitches per PA; "untracked" when more than
    half of its PA sit on clubs under that floor (or no club reaches the PA
    floor); "partial" otherwise. Rates and anchors are None outside usable
    level-seasons, so no consumer can print one.
  * PAR = round(100 x player rate / anchor rate), nearest point. Not inverted, no
    good or bad colour: 100 is the average for the role, 110 is 10 percent more
    pitches.
  * team PAR = 100 x a club's unit rate / the unweighted mean of the club unit
    rates, so the clubs average 100. team_par() takes unit rates on EITHER club
    basis (club today for the boards, earned for the Teams tab; plan 8.D row 2):
    the caller names the membership, this module owns the arithmetic.

Sources:
  * MiLB season lines: StatsAPI stats=season per (sport, season, group), cached
    lean in .cache/pitch_rates/{group}_{sport}_{season}.json. A sibling cache,
    NEVER .cache/milb_stats (the eFV inputs; plan STOP S6).
  * Role lines: stats=statSplits&sitCodes=sp,rp&group=pitching (gameType=R at
    sportId 1, playerPool=ALL, paginated) in
    .cache/pitch_rates/pitching_sprp_{sport}_{season}.json.
  * MLB season lines: the files fa_sources.fetch_statsapi_season_stats already
    keeps (.cache/fa_statsapi_{group}_{season}.json). Read from disk; this module
    adds no request for them.
  Current-season caches refresh after milb_history._SEASON_TTL_SEC; past seasons
  are cached for good. Every fetch outcome files through
  bullpen_export.record_ingest, so a failure reaches data/ingest_health.json.

Serving: SERVE_PITCH_RATES is True since the flip (Q8_06, plan PM-07, after the
fWAR label epoch's step Z): build() writes data/pitch_rates.json and the board,
PROSPX and glossary keys are served. Set it False and build() writes only
.cache/pitch_rates/preview.json, with no payload key, page column, glossary hook
or public file change. run_monthly's step 6b4-pr runs build() before the boards.

Run:
  python pitch_rates.py --warm 2011 2026   one-time cache warm, then the preview
  python pitch_rates.py --build            rebuild from the caches, no network
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

from milb_history import SPORT_LEVEL, _SEASON_TTL_SEC, _level16

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Flag, constants, paths
# --------------------------------------------------------------------------- #
SERVE_PITCH_RATES = True

TRACK_MIN_TEAM_P_PA = 3.3
TRACK_MIN_TEAM_PA = 200
# A level-season with more than this share of its PA on clubs under the P/PA floor
# is untracked; above zero and up to it, partial (the lane's section 2.2 table:
# AA 2011 at 39.2 percent is partial, complex 2017 at 64.7 percent untracked).
TRACK_UNTRACKED_PA_SHARE = 0.5

# Role-split parity: the sp + rp lines must carry the season line's batters faced.
# Off by more than the first tolerance, the level-season's role anchors fall back
# to the season line (stamped); off by more than the second, the level-season is
# excluded for P/IP and P/BF (stamped role_split_mismatch).
ROLE_SPLIT_FALLBACK_TOL = 0.005
ROLE_SPLIT_EXCLUDE_TOL = 0.05

# Season-line fallback role classes (the lane's section 2.1 table): a starter line
# has GS / G at or above this share; a reliever line has no start.
FALLBACK_SP_GS_SHARE = 0.8

MLB_FIRST = 2008
MILB_FIRST = 2011
SHORT_SEASON_LAST = 2020      # sportId 15 (short-season A) was retired after 2020
MILB_SPORTS = (11, 12, 13, 14, 15, 16)
MILB_LEVELS = ("AAA", "AA", "A+", "A", "CPX", "DSL")
STABILITY_FIRST = 2021        # consecutive-season pairs from here on (2020 skipped)
STABILITY_FLOORS = {"hit_pa": 300, "sp_outs": 300, "rp_outs": 120}

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache" / "pitch_rates"
MLB_CACHE_DIR = ROOT / ".cache"            # where fa_sources keeps fa_statsapi_*
PLATOON_DIR = ROOT / ".cache" / "milb_platoon"
PREVIEW_PATH = CACHE_DIR / "preview.json"
DATA_PATH = ROOT / "data" / "pitch_rates.json"

STATSAPI = "https://statsapi.mlb.com/api/v1/stats"
PAGE_LIMIT = 2000
REQUEST_PAUSE_SEC = 0.3
_UA = {"User-Agent": "Mozilla/5.0"}

INGEST_SEASON = "pitch_rates_season_lines"
INGEST_ROLE = "pitch_rates_role_splits"

BASIS_ROLE = "role_split"
BASIS_FALLBACK = "season_line_fallback"
STAMP_MISMATCH = "role_split_mismatch"


# --------------------------------------------------------------------------- #
# Rates and indexes (pure)
# --------------------------------------------------------------------------- #
def _num(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def outs_from_ip(ip) -> int | None:
    """MLB innings notation to outs: "6.1" is 19 outs, "6.2" is 20. A value whose
    tenths digit is 3 or more is not MLB notation and is read as true innings, the
    same guard bullpen_export.ip_to_float applies."""
    v = _num(ip)
    if v is None:
        return None
    whole = int(v)
    tenths = round((v - whole) * 10)
    if tenths >= 3:
        return int(round(v * 3))
    return whole * 3 + tenths


def innings(outs) -> float | None:
    o = _num(outs)
    return None if o is None else o / 3.0


def _ratio(num, den) -> float | None:
    n, d = _num(num), _num(den)
    if n is None or d is None or d <= 0:
        return None
    return n / d


def p_ip(np_, outs) -> float | None:
    """Pitches per inning, innings counted as outs / 3."""
    o = _num(outs)
    if o is None or o <= 0:
        return None
    return _ratio(np_, o / 3.0)


def p_bf(np_, bf) -> float | None:
    return _ratio(np_, bf)


def p_pa(np_, pa) -> float | None:
    return _ratio(np_, pa)


def par(rate, anchor) -> int | None:
    """PAR = 100 x rate / anchor, rounded to the NEAREST point (halves up; plus
    stats round nearest, grades round up). None when either side is missing."""
    r, a = _num(rate), _num(anchor)
    if r is None or a is None or a <= 0:
        return None
    return int(math.floor(100.0 * r / a + 0.5))


def par_delta(rate, anchor) -> float | None:
    """The owner's literal delta: rate minus anchor, in pitches."""
    r, a = _num(rate), _num(anchor)
    if r is None or a is None:
        return None
    return r - a


def team_par(unit_rates: dict) -> dict:
    """{club: 100 x club rate / unweighted mean of the club rates}.

    `unit_rates` maps a club to its unit rate (lineup P/PA, rotation P/IP or
    bullpen P/IP) on whichever club basis the caller built it (club today for the
    boards, earned for the Teams tab). Clubs with no rate are left out of the mean
    and get None. Unrounded, so the values average exactly 100; a display rounds
    them nearest, like par()."""
    rates = {k: _num(v) for k, v in (unit_rates or {}).items()}
    vals = [v for v in rates.values() if v is not None and v > 0]
    if not vals:
        return {k: None for k in rates}
    mean = sum(vals) / len(vals)
    return {k: (None if v is None or v <= 0 else 100.0 * v / mean)
            for k, v in rates.items()}


# --------------------------------------------------------------------------- #
# Lean rows
# --------------------------------------------------------------------------- #
def _level_sport16(league: str) -> str:
    """DSL or CPX for a sportId-16 row. The season lines name the league by its
    abbreviation ("DSL"), which milb_history._level16 reads; the statSplits
    response names it in full ("Dominican Summer League"), which that check misses
    and would fold every DSL starter and reliever line into CPX."""
    up = (league or "").upper()
    if "DOMINICAN" in up or "VENEZUELAN" in up:
        return "DSL"
    return _level16(league)


def _level_for(sport_id: int, league: str) -> str:
    if sport_id == 16:
        return _level_sport16(league)
    return SPORT_LEVEL.get(sport_id, "?")


def _lean(split: dict, sport_id: int, group: str, role: bool = False) -> dict:
    st = split.get("stat") or {}
    league = (split.get("league") or {}).get("name") or ""
    team_id = (split.get("team") or {}).get("id")
    row = {"mlbam": (split.get("player") or {}).get("id"),
           "team_id": team_id, "league": league,
           "level": _level_for(sport_id, league),
           "np": st.get("numberOfPitches"), "g": st.get("gamesPlayed")}
    if role:
        row["code"] = (split.get("split") or {}).get("code")
    if group == "hitting":
        row["pa"] = st.get("plateAppearances")
        row["pos"] = (split.get("position") or {}).get("abbreviation")
    else:
        outs = st.get("outs")
        if outs is None:
            outs = st.get("outsPitched")
        if outs is None:
            outs = outs_from_ip(st.get("inningsPitched"))
        row.update({"bf": st.get("battersFaced"), "outs": outs,
                    "g": st.get("gamesPitched", st.get("gamesPlayed")),
                    "gs": st.get("gamesStarted")})
    return row


def _relevel(rows: list[dict], sport_id: int) -> list[dict]:
    if sport_id == 16:
        for r in rows:
            r["level"] = _level_sport16(r.get("league") or "")
    return rows


# --------------------------------------------------------------------------- #
# Fetchers (network only here; cache-first; ingest health on every outcome)
# --------------------------------------------------------------------------- #
def _record(source: str, *, ok: bool, n_rows: int = 0, message: str = "") -> None:
    """bullpen_export.record_ingest, the export layer's one ingest-health client.
    A healthy fetch logs only when a pipeline is already up (the heartbeat rule);
    a failure always files."""
    try:
        from bullpen_export import record_ingest
        record_ingest(source, ok=ok, n_rows=n_rows, message=message,
                      import_fallback=not ok)
    except Exception:                                   # noqa: BLE001 - reporting only
        log.debug("pitch_rates: could not record ingest for %s", source, exc_info=True)


def _http_json(url: str) -> dict:
    import urllib.request
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read())


def _paged(url: str) -> tuple[list[dict], int, int]:
    """Every split behind a paginated stats URL. Raises when the pages fall short
    of totalSplits, so a partial response is never cached as a season."""
    splits: list[dict] = []
    offset, pages, total = 0, 0, 0
    while True:
        if pages:
            time.sleep(REQUEST_PAUSE_SEC)
        d = _http_json(f"{url}&limit={PAGE_LIMIT}&offset={offset}")
        pages += 1
        block = (d.get("stats") or [{}])[0]
        page = block.get("splits") or []
        total = int(block.get("totalSplits") or 0)
        splits.extend(page)
        offset += len(page)
        if not page or offset >= total:
            break
    if len(splits) < total:
        raise RuntimeError(f"short read: {len(splits)} of {total} splits")
    return splits, total, pages


_READ_MEMO: dict = {}


def _read_cache(path: Path):
    """Parsed JSON of a cache file, memoized on (path, mtime, size) so one build
    parses each season file once. Callers never mutate what this returns."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key in _READ_MEMO:
        return _READ_MEMO[key]
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    _READ_MEMO[key] = obj
    return obj


def _stale(path: Path, season: int) -> bool:
    return (season >= date.today().year
            and (time.time() - path.stat().st_mtime) >= _SEASON_TTL_SEC)


def _write_json(path: Path, obj, indent=None) -> None:
    """Same-directory temp file, then os.replace: a reader sees the old file or the
    new one, never half of either."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.stem}.",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(obj, fh, indent=indent, separators=None if indent else (",", ":"))
            if indent:
                fh.write("\n")
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _cached_fetch(path: Path, url: str, sport_id: int, season: int, group: str,
                  role: bool, source: str, fetch: bool) -> list[dict]:
    cached = _read_cache(path)
    if cached is not None and not (fetch and _stale(path, season)):
        return _relevel(cached.get("rows") or [], sport_id)
    if not fetch:
        return _relevel(cached.get("rows") or [], sport_id) if cached is not None else []
    tag = f"{group}{'_sprp' if role else ''} sport={sport_id} season={season}"
    try:
        splits, total, pages = _paged(url)
    except Exception as e:                              # noqa: BLE001
        log.warning("pitch_rates fetch failed %s: %s", tag, e)
        _record(source, ok=False, message=f"{tag}: {e}")
        return _relevel(cached.get("rows") or [], sport_id) if cached is not None else []
    rows = [_lean(s, sport_id, group, role=role) for s in splits]
    if not rows and (cached is not None or season >= date.today().year):
        # An empty refetch keeps the prior cache, and an empty current season is
        # never cached (it may be a feed hiccup). A past season that is empty
        # (2020, or a retired sport) is cached so the warm does not ask again.
        _record(source, ok=False, message=f"{tag}: empty response")
        return _relevel(cached.get("rows") or [], sport_id) if cached is not None else []
    meta = {"sport": sport_id, "season": season, "group": group,
            "sitCodes": "sp,rp" if role else None, "totalSplits": total,
            "rows": len(rows), "pages": pages,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _write_json(path, {"meta": meta, "rows": rows})
    _record(source, ok=True, n_rows=len(rows), message=tag)
    return rows


def fetch_season_lines(sport_id: int, season: int, group: str,
                       fetch: bool = True) -> list[dict]:
    """Every player's season line for one MiLB (sport, season, group), lean:
    mlbam, team_id, league, level, np, pa or bf, outs, g, gs (hitting rows also
    carry pos). Cached in .cache/pitch_rates/; [] when uncached and fetch=False."""
    path = CACHE_DIR / f"{group}_{sport_id}_{season}.json"
    url = (f"{STATSAPI}?stats=season&group={group}&season={season}"
           f"&sportIds={sport_id}&playerPool=ALL")
    return _cached_fetch(path, url, sport_id, season, group, False,
                         INGEST_SEASON, fetch)


def fetch_role_splits(sport_id: int, season: int, fetch: bool = True) -> list[dict]:
    """Every pitcher's starter (code "sp") and reliever (code "rp") line for one
    (sport, season): stats=statSplits&sitCodes=sp,rp, gameType=R at sportId 1,
    playerPool=ALL, paginated. Cached in .cache/pitch_rates/pitching_sprp_*."""
    path = CACHE_DIR / f"pitching_sprp_{sport_id}_{season}.json"
    url = (f"{STATSAPI}?stats=statSplits&sitCodes=sp,rp&group=pitching"
           f"&season={season}&sportIds={sport_id}&playerPool=ALL"
           + ("&gameType=R" if sport_id == 1 else ""))
    return _cached_fetch(path, url, sport_id, season, "pitching", True,
                         INGEST_ROLE, fetch)


def mlb_season_lines(season: int, group: str, fetch: bool = False) -> list[dict]:
    """MLB season lines from the file fa_sources.fetch_statsapi_season_stats
    keeps. Read from disk; only when the file is absent and fetch=True does it ask
    fa_sources (which owns that cache and its TTL)."""
    path = MLB_CACHE_DIR / f"fa_statsapi_{group}_{season}.json"
    splits = None
    raw = _read_cache(path)
    if raw is not None:
        memo = _MLB_LEAN_MEMO.get(id(raw))
        if memo is not None and memo[0] is raw:
            return memo[1]
        stats = raw.get("stats") or []
        splits = (stats[0].get("splits") or []) if stats else []
        lean = [_lean(s, 1, group) for s in splits]
        _MLB_LEAN_MEMO[id(raw)] = (raw, lean)
        return lean
    if fetch:
        from fa_sources import fetch_statsapi_season_stats
        splits = fetch_statsapi_season_stats(season, group)
    return [_lean(s, 1, group) for s in (splits or [])]


_MLB_LEAN_MEMO: dict = {}


# --------------------------------------------------------------------------- #
# Level plumbing
# --------------------------------------------------------------------------- #
def _sports_for(level: str, season: int) -> tuple[int, ...]:
    if level == "MLB":
        return (1,)
    out = tuple(s for s, lv in SPORT_LEVEL.items() if lv == level and s != 1)
    if level in ("CPX", "DSL"):
        out = (16,)
    if season > SHORT_SEASON_LAST:
        out = tuple(s for s in out if s != 15)
    return out


def _lines(level: str, season: int, group: str, fetch: bool = False) -> list[dict]:
    if level == "MLB":
        rows = mlb_season_lines(season, group, fetch=fetch)
    else:
        rows = []
        for sp in _sports_for(level, season):
            rows += fetch_season_lines(sp, season, group, fetch=fetch)
    return [r for r in rows if r.get("level") == level]


def _role_lines(level: str, season: int, fetch: bool = False) -> list[dict]:
    rows = []
    for sp in _sports_for(level, season):
        rows += fetch_role_splits(sp, season, fetch=fetch)
    return [r for r in rows if r.get("level") == level]


def _teamed(rows):
    """Rows that carry a club. A row with no team id is a multi-club total in some
    feeds; summing it beside its stints would count the season twice (the
    stats.fetch_career_stats convention)."""
    return [r for r in rows if r.get("team_id") is not None]


def _sum(rows, *fields) -> dict:
    """Pooled counts over rows that carry a pitch count. A row without one adds
    nothing to either side of a rate."""
    out = {f: 0 for f in fields}
    out["n"] = 0
    out["missing_np"] = 0
    for r in rows:
        if _num(r.get("np")) is None:
            out["missing_np"] += 1
            continue
        out["n"] += 1
        for f in fields:
            out[f] += int(_num(r.get(f)) or 0)
    return out


def _is_pitcher_bat(r) -> bool:
    return (r.get("pos") or "") == "P"


# --------------------------------------------------------------------------- #
# Tracking
# --------------------------------------------------------------------------- #
def classify_tracking(hit_rows: list[dict]) -> dict:
    """The tracking verdict for one level-season from its hitting lines (every
    row with a club, pitchers' bats included: this is a property of the feed)."""
    clubs: dict = {}
    for r in _teamed(hit_rows):
        np_, pa = _num(r.get("np")), _num(r.get("pa"))
        if np_ is None or pa is None:
            continue
        c = clubs.setdefault(r["team_id"], [0.0, 0.0])
        c[0] += np_
        c[1] += pa
    tot_np = sum(c[0] for c in clubs.values())
    tot_pa = sum(c[1] for c in clubs.values())
    pooled = p_pa(tot_np, tot_pa)
    qual = {k: c for k, c in clubs.items() if c[1] >= TRACK_MIN_TEAM_PA}
    under = {k: c for k, c in qual.items() if c[0] / c[1] < TRACK_MIN_TEAM_P_PA}
    under_pa = sum(c[1] for c in under.values())
    share = under_pa / tot_pa if tot_pa else None
    if pooled is None or not qual or share > TRACK_UNTRACKED_PA_SHARE:
        status = "untracked"
    elif under:
        status = "partial"
    else:
        status = "usable"
    return {"status": status,
            "pooled_p_pa": None if pooled is None else round(pooled, 4),
            "pa": int(tot_pa), "n_clubs": len(qual), "n_clubs_under": len(under),
            "pa_share_under": None if share is None else round(share, 4)}


def tracking_detail(level: str, season: int, fetch: bool = False) -> dict:
    return classify_tracking(_lines(level, season, "hitting", fetch=fetch))


def tracking(level: str, season: int, fetch: bool = False) -> str:
    """"usable" | "partial" | "untracked" for one (level, season), computed from
    this module's own hitting lines."""
    return tracking_detail(level, season, fetch=fetch)["status"]


# --------------------------------------------------------------------------- #
# Anchors
# --------------------------------------------------------------------------- #
def _hit_block(rows) -> dict:
    s = _sum([r for r in _teamed(rows) if not _is_pitcher_bat(r)], "np", "pa")
    s["p_pa"] = p_pa(s["np"], s["pa"])
    return s


def _sp_block(rows) -> dict:
    s = _sum(_teamed(rows), "np", "outs", "bf", "g", "gs")
    s["p_ip"] = p_ip(s["np"], s["outs"])
    s["p_bf"] = p_bf(s["np"], s["bf"])
    s["pit_per_gs"] = _ratio(s["np"], s["gs"])
    s["sp_ip_per_gs"] = _ratio(s["outs"] / 3.0, s["gs"]) if s["gs"] else None
    return s


def _rp_block(rows) -> dict:
    s = _sum(_teamed(rows), "np", "outs", "bf", "g")
    s["p_ip"] = p_ip(s["np"], s["outs"])
    s["p_bf"] = p_bf(s["np"], s["bf"])
    s["pit_per_g"] = _ratio(s["np"], s["g"])
    return s


def _fallback_class(r) -> str | None:
    g, gs = _num(r.get("g")) or 0, _num(r.get("gs")) or 0
    if g <= 0:
        return None
    if gs / g >= FALLBACK_SP_GS_SHARE:
        return "sp"
    if gs == 0:
        return "rp"
    return None


def _bf_total(rows) -> int:
    return int(sum(_num(r.get("bf")) or 0 for r in _teamed(rows)))


def role_parity(role_rows, season_rows) -> dict:
    """Receipt (a): the sp + rp lines' batters faced against the season lines'."""
    rb, sb = _bf_total(role_rows), _bf_total(season_rows)
    rel = abs(rb - sb) / sb if sb else None
    if not role_rows:
        verdict = "no_role_split"
    elif rel is None:
        verdict = "no_season_line"
    elif rel <= ROLE_SPLIT_FALLBACK_TOL:
        verdict = "ok"
    elif rel <= ROLE_SPLIT_EXCLUDE_TOL:
        verdict = "fallback"
    else:
        verdict = "excluded"
    return {"role_split_bf": rb, "season_line_bf": sb,
            "bf_rel_diff": None if rel is None else round(rel, 6), "verdict": verdict}


_RATE_KEYS = ("p_pa", "p_ip", "p_bf", "pit_per_gs", "pit_per_g", "sp_ip_per_gs")


def _blank_rates(block: dict) -> dict:
    for k in _RATE_KEYS:
        if k in block:
            block[k] = None
    return block


def league_rates(level: str, season: int, fetch: bool = False) -> dict:
    """The pooled anchors for one (level, season): hitters' P/PA and the starter
    and reliever lines. Rates are None outside usable level-seasons; the counts
    stay so the arithmetic can be checked."""
    hit_rows = _lines(level, season, "hitting", fetch=fetch)
    pit_rows = _lines(level, season, "pitching", fetch=fetch)
    role_rows = _role_lines(level, season, fetch=fetch)
    trk = classify_tracking(hit_rows)
    status = trk["status"]
    par_r = role_parity(role_rows, pit_rows)
    if par_r["verdict"] == "ok":
        basis = BASIS_ROLE
        sp = _sp_block([r for r in role_rows if r.get("code") == "sp"])
        rp = _rp_block([r for r in role_rows if r.get("code") == "rp"])
    else:
        basis = BASIS_FALLBACK
        sp = _sp_block([r for r in pit_rows if _fallback_class(r) == "sp"])
        rp = _rp_block([r for r in pit_rows if _fallback_class(r) == "rp"])
    pitching_status = status
    stamp = None
    if par_r["verdict"] == "excluded":
        pitching_status, stamp = "untracked", STAMP_MISMATCH
    elif par_r["verdict"] in ("no_role_split", "no_season_line") and not pit_rows:
        pitching_status = "untracked"
    hit = _hit_block(hit_rows)
    if status != "usable":
        _blank_rates(hit)
    if pitching_status != "usable":
        _blank_rates(sp)
        _blank_rates(rp)
    return {"level": level, "season": season, "tracking": trk["status"],
            "tracking_detail": trk, "pitching_status": pitching_status,
            "pitching_stamp": stamp, "basis": basis, "role_parity": par_r,
            "hit": hit, "sp": sp, "rp": rp}


# --------------------------------------------------------------------------- #
# Player lines
# --------------------------------------------------------------------------- #
def _acc(dst: dict, r: dict, fields) -> None:
    for f in fields:
        v = _num(r.get(f))
        if v is not None:
            dst[f] = dst.get(f, 0) + int(v)
    if _num(r.get("np")) is None:
        dst["missing_np"] = dst.get("missing_np", 0) + 1


def player_lines(season: int, level: str, fetch: bool = False) -> dict:
    """{mlbam: line} for one (season, level), stints summed and rows without a
    club skipped. Hitters carry `hit` (np, pa, p_pa); pitchers carry `pit` with
    the season line, the sp and rp lines, the majority role (the role with more
    batters faced) and that role's P/IP and P/BF. Rates are None when the
    level-season is not usable for that side; a pitcher with no role line, or a
    level-season on the season-line fallback, is stamped season_line_fallback."""
    lr = league_rates(level, season, fetch=fetch)
    hit_ok = lr["tracking"] == "usable"
    pit_ok = lr["pitching_status"] == "usable"
    out: dict = {}

    def _slot(pid):
        return out.setdefault(pid, {"mlbam": pid, "season": season, "level": level,
                                    "hit": None, "pit": None})

    for r in _teamed(_lines(level, season, "hitting", fetch=fetch)):
        if r.get("mlbam") is None:
            continue
        h = _slot(r["mlbam"])["hit"] or {}
        _acc(h, r, ("np", "pa", "g"))
        if r.get("pos"):
            h["pos"] = r["pos"]
        _slot(r["mlbam"])["hit"] = h
    for p in out.values():
        h = p["hit"]
        if h is not None:
            h["p_pa"] = p_pa(h.get("np"), h.get("pa")) if hit_ok and not h.get("missing_np") else None

    season_pit: dict = {}
    for r in _teamed(_lines(level, season, "pitching", fetch=fetch)):
        if r.get("mlbam") is not None:
            _acc(season_pit.setdefault(r["mlbam"], {}), r, ("np", "outs", "bf", "g", "gs"))
    roles: dict = {}
    for r in _teamed(_role_lines(level, season, fetch=fetch)):
        if r.get("mlbam") is not None and r.get("code") in ("sp", "rp"):
            _acc(roles.setdefault(r["mlbam"], {}).setdefault(r["code"], {}), r,
                 ("np", "outs", "bf", "g", "gs"))
    for pid in set(season_pit) | set(roles):
        sl = season_pit.get(pid)
        rl = roles.get(pid) or {}
        use_roles = lr["basis"] == BASIS_ROLE and bool(rl)
        if use_roles:
            sp_bf = (rl.get("sp") or {}).get("bf", 0)
            rp_bf = (rl.get("rp") or {}).get("bf", 0)
            role = "SP" if sp_bf >= rp_bf and rl.get("sp") else "RP"
            line = rl.get("sp" if role == "SP" else "rp") or {}
            basis = BASIS_ROLE
        else:
            line = sl or {}
            g, gs = line.get("g", 0), line.get("gs", 0)
            role = "SP" if g and gs / g >= 0.5 else "RP"
            basis = BASIS_FALLBACK
        ok = pit_ok and not line.get("missing_np")
        _slot(pid)["pit"] = {
            "season_line": sl, "sp": rl.get("sp"), "rp": rl.get("rp"),
            "role": role, "basis": basis,
            "p_ip": p_ip(line.get("np"), line.get("outs")) if ok else None,
            "p_bf": p_bf(line.get("np"), line.get("bf")) if ok else None,
        }
    return out


# --------------------------------------------------------------------------- #
# Teams, stability, parity
# --------------------------------------------------------------------------- #
def team_unit_rates(rows: list[dict], kind: str, club_of=None) -> dict:
    """{club: pooled unit rate}. kind "lineup" pools hitters' pitches over PA
    (pitchers' bats excluded); "rotation" and "bullpen" pool pitches over outs / 3
    from starter or reliever role lines. `club_of(row)` names the membership
    (default: the club on the row itself)."""
    club_of = club_of or (lambda r: r.get("team_id"))
    acc: dict = {}
    for r in _teamed(rows):
        if kind == "lineup" and _is_pitcher_bat(r):
            continue
        np_ = _num(r.get("np"))
        den = _num(r.get("pa") if kind == "lineup" else r.get("outs"))
        club = club_of(r)
        if np_ is None or den is None or club is None:
            continue
        a = acc.setdefault(club, [0.0, 0.0])
        a[0] += np_
        a[1] += den
    if kind == "lineup":
        return {k: p_pa(a[0], a[1]) for k, a in acc.items()}
    return {k: p_ip(a[0], a[1]) for k, a in acc.items()}


def _pearson(xs, ys) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def stability(first: int, last: int, fetch: bool = False) -> dict:
    """Year-to-year r on consecutive MLB seasons (2020 skipped), so no copy ever
    types one: hitter P/PA (PA floor both years), starter P/IP and P/BF on the sp
    line (outs floor), reliever P/IP on the rp line (outs floor)."""
    per: dict = {}
    for s in range(first, last + 1):
        if s == 2020:
            continue
        pl = player_lines(s, "MLB", fetch=fetch)
        h = {pid: v["hit"]["p_pa"] for pid, v in pl.items()
             if v["hit"] and (v["hit"].get("pa") or 0) >= STABILITY_FLOORS["hit_pa"]
             and v["hit"].get("pos") != "P" and v["hit"]["p_pa"] is not None}
        spl, rpl = {}, {}
        for pid, v in pl.items():
            pit = v["pit"]
            if not pit:
                continue
            sp, rp = pit.get("sp") or {}, pit.get("rp") or {}
            if sp.get("outs", 0) >= STABILITY_FLOORS["sp_outs"] and not sp.get("missing_np"):
                spl[pid] = (p_ip(sp["np"], sp["outs"]), p_bf(sp["np"], sp.get("bf")))
            if rp.get("outs", 0) >= STABILITY_FLOORS["rp_outs"] and not rp.get("missing_np"):
                rpl[pid] = p_ip(rp["np"], rp["outs"])
        per[s] = (h, spl, rpl)
    pairs = [(a, a + 1) for a in range(first, last) if a in per and a + 1 in per]
    hx, hy, sx, sy, bx, by, rx, ry = ([] for _ in range(8))
    for a, b in pairs:
        ha, sa, ra = per[a]
        hb, sb, rb = per[b]
        for pid in ha.keys() & hb.keys():
            hx.append(ha[pid]); hy.append(hb[pid])
        for pid in sa.keys() & sb.keys():
            sx.append(sa[pid][0]); sy.append(sb[pid][0])
            if sa[pid][1] is not None and sb[pid][1] is not None:
                bx.append(sa[pid][1]); by.append(sb[pid][1])
        for pid in ra.keys() & rb.keys():
            rx.append(ra[pid]); ry.append(rb[pid])

    def _r(x, y):
        v = _pearson(x, y)
        return {"r": None if v is None else round(v, 3), "pairs": len(x)}
    return {"seasons": [first, last], "season_pairs": [list(p) for p in pairs],
            "floors": dict(STABILITY_FLOORS),
            "hitter_p_pa": _r(hx, hy), "starter_p_ip": _r(sx, sy),
            "starter_p_bf": _r(bx, by), "reliever_p_ip": _r(rx, ry),
            "basis": "MLB role lines (sp, rp) and non-pitcher hitting lines, "
                     "consecutive seasons, the floor met in both"}


def platoon_parity(sport_id: int, season: int, group: str) -> dict | None:
    """Receipt (b): this producer's totals against the orphan .cache/milb_platoon
    vl + vr totals for the same (sport, season, group). Read-only; None when that
    file does not exist."""
    import gzip
    path = PLATOON_DIR / f"raw_{group}_{sport_id}_{season}.json.gz"
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return None
    fields = ("np", "pa") if group == "hitting" else ("np", "bf", "outs")
    plat = {f: 0 for f in fields}
    for s in raw.get("splits") or []:
        if not (s.get("team") or {}).get("id"):
            continue
        lean = _lean(s, sport_id, group)
        for f in fields:
            plat[f] += int(_num(lean.get(f)) or 0)
    mine = {f: 0 for f in fields}
    for r in _teamed(fetch_season_lines(sport_id, season, group, fetch=False)):
        for f in fields:
            mine[f] += int(_num(r.get(f)) or 0)
    fetched = (raw.get("meta") or {}).get("fetched_at") or ""
    # Pitches and PA / BF are the receipt. Outs are reported, not compared: a
    # vs-left / vs-right split holds only the outs made inside a plate appearance,
    # so outs made on the bases (caught stealing, pickoffs) sit in the season line
    # alone and the split runs about 1 to 2 percent short by construction.
    compared = tuple(f for f in fields if f != "outs")
    rel = max((abs(mine[f] - plat[f]) / plat[f]) if plat[f] else float(mine[f] != 0)
              for f in compared)
    # The orphan files were written 2026-07-23: a season still under way then is
    # a part-season snapshot and cannot be a reference for the full season.
    stale = fetched[:10] < f"{season}-10-01"
    return {"sport": sport_id, "season": season, "group": group,
            "producer": mine, "platoon": plat, "compared": list(compared),
            "equal": all(mine[f] == plat[f] for f in compared),
            "max_rel_diff": round(rel, 6),
            "within_tol": None if stale else rel <= ROLE_SPLIT_FALLBACK_TOL,
            "reference_stale": stale, "platoon_fetched_at": fetched}


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def _rounded(block: dict | None, nd: int = 4) -> dict | None:
    if block is None:
        return None
    return {k: (round(v, nd) if isinstance(v, float) else v) for k, v in block.items()}


def _last_season(pattern_dir: Path, prefix: str) -> int:
    best = 0
    for p in pattern_dir.glob(f"{prefix}*.json"):
        tail = p.stem.rsplit("_", 1)[-1]
        if tail.isdigit():
            best = max(best, int(tail))
    return min(best, date.today().year) if best else date.today().year


def build(write: bool = True, fetch: bool = False) -> dict:
    """The pitch-rates artifact. While SERVE_PITCH_RATES is False it is written
    ONLY to .cache/pitch_rates/preview.json; data/pitch_rates.json is written
    only when the flag is True."""
    mlb_last = _last_season(MLB_CACHE_DIR, "fa_statsapi_pitching_")
    milb_last = max(mlb_last, _last_season(CACHE_DIR, "hitting_11_"))
    mlb: dict = {}
    teams: dict = {}
    parity_a: list = []
    for s in range(MLB_FIRST, mlb_last + 1):
        lr = league_rates("MLB", s, fetch=fetch)
        mlb[str(s)] = {"tracking": lr["tracking"], "pitching_status": lr["pitching_status"],
                       "pitching_stamp": lr["pitching_stamp"], "basis": lr["basis"],
                       "hit": _rounded(lr["hit"]), "sp": _rounded(lr["sp"]),
                       "rp": _rounded(lr["rp"])}
        parity_a.append({"level": "MLB", "season": s, **lr["role_parity"]})
        hit = _lines("MLB", s, "hitting", fetch=fetch)
        roles = _role_lines("MLB", s, fetch=fetch)
        units = {"lineup": team_unit_rates(hit, "lineup"),
                 "rotation": team_unit_rates([r for r in roles if r.get("code") == "sp"], "rotation"),
                 "bullpen": team_unit_rates([r for r in roles if r.get("code") == "rp"], "bullpen")}
        if lr["basis"] != BASIS_ROLE:
            units["rotation"], units["bullpen"] = {}, {}
        teams[str(s)] = {}
        for kind, rates in units.items():
            tp = team_par(rates)
            teams[str(s)][kind] = {str(k): {"rate": None if v is None else round(v, 4),
                                            "par": None if tp.get(k) is None else par(tp[k], 100.0),
                                            "par_exact": None if tp.get(k) is None else round(tp[k], 4)}
                                   for k, v in sorted(rates.items(), key=lambda kv: str(kv[0]))}
    milb: dict = {}
    track_rows: list = []
    for level in MILB_LEVELS:
        milb[level] = {}
        for s in range(MILB_FIRST, milb_last + 1):
            lr = league_rates(level, s, fetch=fetch)
            milb[level][str(s)] = {"tracking": lr["tracking"],
                                   "pitching_status": lr["pitching_status"],
                                   "pitching_stamp": lr["pitching_stamp"],
                                   "basis": lr["basis"], "hit": _rounded(lr["hit"]),
                                   "sp": _rounded(lr["sp"]), "rp": _rounded(lr["rp"])}
            parity_a.append({"level": level, "season": s, **lr["role_parity"]})
            track_rows.append({"level": level, "season": s, **lr["tracking_detail"],
                               "pitching_status": lr["pitching_status"],
                               "pitching_stamp": lr["pitching_stamp"],
                               "basis": lr["basis"],
                               "role_split_bf": lr["role_parity"]["role_split_bf"],
                               "season_line_bf": lr["role_parity"]["season_line_bf"]})
    parity_b = []
    for sp in (11, 12, 13, 14, 16):
        for s in range(MILB_FIRST, milb_last + 1):
            for g in ("hitting", "pitching"):
                rec = platoon_parity(sp, s, g)
                if rec is not None:
                    parity_b.append(rec)
    payload = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "serve_flag": SERVE_PITCH_RATES,
        "definitions": {
            "innings": "outs / 3; a line of 6.1 is 19 outs",
            "p_ip": "pitches / (outs / 3)", "p_bf": "pitches / batters faced",
            "p_pa": "pitches seen / plate appearances",
            "anchor": "pooled: sum of pitches over sum of outs x 3, PA or BF; never "
                      "an average of player rates",
            "par": "round(100 x rate / anchor), nearest point; not inverted, uncoloured",
            "team_par": "100 x club unit rate / unweighted mean of the club unit rates",
            "tracking": f"usable when every club with {TRACK_MIN_TEAM_PA}+ PA sees "
                        f"{TRACK_MIN_TEAM_P_PA}+ P/PA; untracked when more than "
                        f"{TRACK_UNTRACKED_PA_SHARE:.0%} of the PA sit on clubs under "
                        "that floor; partial otherwise",
            "role_parity": f"sp + rp BF within {ROLE_SPLIT_FALLBACK_TOL:.1%} of the "
                           f"season-line BF: role_split; within {ROLE_SPLIT_EXCLUDE_TOL:.0%}: "
                           "season_line_fallback; beyond: untracked for P/IP and P/BF, "
                           "stamped role_split_mismatch",
        },
        "constants": {"TRACK_MIN_TEAM_P_PA": TRACK_MIN_TEAM_P_PA,
                      "TRACK_MIN_TEAM_PA": TRACK_MIN_TEAM_PA,
                      "TRACK_UNTRACKED_PA_SHARE": TRACK_UNTRACKED_PA_SHARE,
                      "ROLE_SPLIT_FALLBACK_TOL": ROLE_SPLIT_FALLBACK_TOL,
                      "ROLE_SPLIT_EXCLUDE_TOL": ROLE_SPLIT_EXCLUDE_TOL,
                      "FALLBACK_SP_GS_SHARE": FALLBACK_SP_GS_SHARE},
        "mlb": mlb,
        "milb": milb,
        "tracking": track_rows,
        "teams": {"basis": "line_team: the club on the player's StatsAPI season or "
                           "role line (for a player who changed clubs, the line's "
                           "club). Consumers pass their own membership through "
                           "team_unit_rates(club_of=...) and team_par().",
                  "mlb": teams},
        "stability": stability(STABILITY_FIRST, mlb_last, fetch=fetch),
        "parity": {"role_split_bf": parity_a, "milb_platoon_totals": parity_b},
    }
    if write:
        if SERVE_PITCH_RATES:
            _write_json(DATA_PATH, payload, indent=1)
        else:
            _write_json(PREVIEW_PATH, payload, indent=1)
    return payload


def warm(first: int, last: int) -> int:
    """One-time cache warm (MiLB season lines and role splits for first..last, the
    MLB role splits for MLB_FIRST..last). Writes .cache/pitch_rates only."""
    n = 0
    for s in range(min(first, MLB_FIRST), last + 1):
        fetch_role_splits(1, s, fetch=True)
        n += 1
    for s in range(first, last + 1):
        for sp in MILB_SPORTS:
            if sp == 15 and s > SHORT_SEASON_LAST:
                continue
            for g in ("hitting", "pitching"):
                fetch_season_lines(sp, s, g, fetch=True)
            fetch_role_splits(sp, s, fetch=True)
            n += 3
            time.sleep(REQUEST_PAUSE_SEC)
    return n


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if argv[:1] == ["--warm"] and len(argv) == 3:
        n = warm(int(argv[1]), int(argv[2]))
        log.info("pitch_rates warm: %d (sport, season, group) reads", n)
        build(write=True, fetch=False)
        log.info("pitch_rates: wrote %s", DATA_PATH if SERVE_PITCH_RATES else PREVIEW_PATH)
        return 0
    if argv[:1] == ["--build"]:
        build(write=True, fetch=False)
        log.info("pitch_rates: wrote %s", DATA_PATH if SERVE_PITCH_RATES else PREVIEW_PATH)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
