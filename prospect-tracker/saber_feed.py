# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB StatsAPI sabermetrics feed: one loader for every reader of FanGraphs'
served WAR components.

`stats=sabermetrics` publishes FanGraphs' WAR line per player-season: batting,
baseRunning, fielding, positional, wLeague, replacement, rar and war, plus woba,
wRaa and wRcPlus. Three programs read it and must read it the same way: the
hitter board's published wRC+ column, the DEM+ Defense board, and the
FanGraphs-frame eWAR replica. A betting builder may read runs from here but may
never import the Defense board, so the loader lives in neither.

THE STINT GUARD. Rows are grouped by MLBAM id and a group of more than one row
resolves to the unique numTeams > 1 season total, or the id is refused. No
positional index is ever taken (the splits[-1] defect on the sqlite path).

FRAMING. The feed does not publish catcher framing as a field, but it sits
inside `rar`: framing = rar - (batting + baseRunning + fielding + positional +
wLeague + replacement). On 2011, 2016, 2023, 2024 and 2025 that residual equals
FanGraphs CFraming on every catcher (max difference 0.0) and is zero on every
non-catcher. `framing_residual` returns the raw residual; deciding who caught is
the caller's job, because it needs innings this feed does not carry.

TWO KEYS NAMED `fielding`. The season FIELDING group's `fielding` is fielding
percentage as a string ("1.000"); this group's is runs as a float. `run_value`
refuses a string, so the two cannot be confused.

THE PITCHING GROUP (fWAR label epoch, precondition E3 part 2). The same endpoint
with `group=pitching` publishes FanGraphs' pitcher WAR line per player-season:
war, rar, fip, xfip, ra9War, gmli, exli, pli, inli, eraMinus, fipMinus, md and
sd. It carries no innings, games or starts (those come from the raw StatsAPI
season stats). Its cache key is `statsapi_saber_pitching_<season>`, beside the
hitting one, and `load_pitching_components` reads it with the same stint guard
and the same refusal of a string run value. The hitting functions keep their
signatures and their behaviour: `group` defaults to "hitting" everywhere.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

_log = logging.getLogger(__name__)

SABER_URL = ("https://statsapi.mlb.com/api/v1/stats?stats=sabermetrics"
             "&group=hitting&season={season}&sportId=1&playerPool=All&limit=2000")

SABER_PITCHING_URL = ("https://statsapi.mlb.com/api/v1/stats?stats=sabermetrics"
                      "&group=pitching&season={season}&sportId=1&playerPool=All&limit=2000")

#: The feed's row cap (the `limit` both URLs send). A response holding exactly
#: this many rows may be truncated, so a reader that must be complete refuses it.
SABER_LIMIT = 2000

#: {group: URL template}. The two groups the sabermetrics feed publishes.
SABER_URLS = {"hitting": SABER_URL, "pitching": SABER_PITCHING_URL}

RUN_PARTS = ("batting", "baseRunning", "fielding", "positional", "wLeague", "replacement")

#: The pitching group's published fields, in the feed's own names.
PITCHING_FIELDS = ("war", "rar", "fip", "xfip", "ra9War", "gmli", "exli", "pli",
                   "inli", "eraMinus", "fipMinus", "md", "sd")


def _group(group: str) -> str:
    if group not in SABER_URLS:
        raise ValueError(f"unknown sabermetrics group {group!r}; use one of {tuple(SABER_URLS)}")
    return group


def cache_key(season: int, group: str = "hitting") -> str:
    return f"statsapi_saber_{_group(group)}_{int(season)}"


def pitching_cache_key(season: int) -> str:
    return cache_key(season, "pitching")


def parse_splits(body) -> list:
    """The split rows of one sabermetrics response body (str, bytes or the
    decoded dict). [] when the body holds no stats block."""
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8")
    blob = json.loads(body) if isinstance(body, str) else (body or {})
    stats = blob.get("stats") or []
    return (stats[0].get("splits") or []) if stats else []


def run_value(v) -> Optional[float]:
    """A run component as a float, or None. A STRING is refused: that is the
    fielding group's percentage key, never a run value."""
    if v is None or isinstance(v, str) or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def framing_residual(stat: dict) -> Optional[float]:
    """rar minus the six published components, or None when any is missing."""
    rar = run_value((stat or {}).get("rar"))
    if rar is None:
        return None
    tot = 0.0
    for k in RUN_PARTS:
        v = run_value(stat.get(k))
        if v is None:
            return None
        tot += v
    return rar - tot


def resolve_groups(splits: list, require: str | None = None) -> tuple[dict, list, int]:
    """Group rows by MLBAM id and resolve each group to one season-total row.

    Returns ({mlbam: row}, ambiguous_ids, n_multi_team). `require` drops rows
    whose stat lacks that key before grouping."""
    by_id: dict[int, list] = {}
    for s in splits or []:
        pid = (s.get("player") or {}).get("id")
        if pid is None:
            continue
        if require and (s.get("stat") or {}).get(require) is None:
            continue
        by_id.setdefault(int(pid), []).append(s)
    out: dict[int, dict] = {}
    ambiguous: list[int] = []
    n_multi = 0
    for pid, group in by_id.items():
        if len(group) == 1:
            row = group[0]
        else:
            tot = [r for r in group if (r.get("numTeams") or 1) > 1]
            if len(tot) != 1:
                ambiguous.append(pid)
                continue
            row = tot[0]
        if (row.get("numTeams") or 1) > 1:
            n_multi += 1
        out[pid] = row
    return out, sorted(ambiguous), n_multi


def fetch_splits(season: int, group: str = "hitting") -> Optional[list]:
    """The season's raw split rows through the shared scraper cache (24h TTL on
    the current season, 30 days on a past one). None on any failure."""
    try:
        from scrapers import _fetch       # network-gated: nothing fetches at import
        fr = _fetch(SABER_URLS[_group(group)].format(season=int(season)),
                    cache_key(season, group), accept_json=True)
        if fr.status != 200 or not fr.body:
            _log.warning("sabermetrics %s: fetch failed (status=%s)", season, fr.status)
            return None
        stats = json.loads(fr.body).get("stats") or []
        return (stats[0].get("splits") or []) if stats else []
    except Exception as e:   # noqa: BLE001 - every reader is best-effort
        _log.warning("sabermetrics %s: unavailable (%s)", season, e)
        return None


def fetch_pitching_splits(season: int) -> Optional[list]:
    """The pitching group's raw split rows (fetch_splits with group=pitching)."""
    return fetch_splits(season, "pitching")


def load_components(season: int) -> dict:
    """{"values": {mlbam: {fld, frm, pos, bat, bsr, lg, rep, rar, war, name,
    team_id}}, plus counters}. `frm` is the raw residual; the caller strips it
    from anyone who did not catch."""
    season = int(season)
    meta = {"values": {}, "season": season, "n_rows": 0, "n_players": 0,
            "n_multi_team": 0, "n_ambiguous": 0, "ambiguous_ids": [],
            "source": "statsapi sabermetrics (bulk, season totals)"}
    splits = fetch_splits(season)
    if not splits:
        return meta
    rows, ambiguous, n_multi = resolve_groups(splits, require="fielding")
    values: dict[int, dict] = {}
    for pid, row in rows.items():
        st = row.get("stat") or {}
        fld = run_value(st.get("fielding"))
        if fld is None:
            continue
        values[pid] = {
            "fld": fld, "frm": framing_residual(st),
            "pos": run_value(st.get("positional")),
            "bat": run_value(st.get("batting")), "bsr": run_value(st.get("baseRunning")),
            "lg": run_value(st.get("wLeague")), "rep": run_value(st.get("replacement")),
            "rar": run_value(st.get("rar")), "war": run_value(st.get("war")),
            "name": (row.get("player") or {}).get("fullName", ""),
            "team_id": (row.get("team") or {}).get("id"),
        }
    meta.update({"values": values, "n_rows": len(splits), "n_players": len(values),
                 "n_multi_team": n_multi, "n_ambiguous": len(ambiguous),
                 "ambiguous_ids": ambiguous})
    return meta


def pitching_values(splits: list) -> tuple[dict, list, int]:
    """Season-total pitching rows -> ({mlbam: {field: float|None, ...,
    num_teams, name, team_id}}, ambiguous_ids, n_multi_team).

    A row without a numeric `war` is dropped (the pitching analogue of the
    hitting reader's `fielding` requirement); every field goes through
    `run_value`, so a string is refused to None and never read as a number."""
    rows, ambiguous, n_multi = resolve_groups(splits, require="war")
    values: dict[int, dict] = {}
    for pid, row in rows.items():
        st = row.get("stat") or {}
        if run_value(st.get("war")) is None:
            continue
        rec = {k: run_value(st.get(k)) for k in PITCHING_FIELDS}
        rec.update({"num_teams": row.get("numTeams") or 1,
                    "name": (row.get("player") or {}).get("fullName", ""),
                    "team_id": (row.get("team") or {}).get("id")})
        values[pid] = rec
    return values, ambiguous, n_multi


def load_pitching_components(season: int) -> dict:
    """{"values": {mlbam: {war, rar, fip, xfip, ra9War, gmli, exli, pli, inli,
    eraMinus, fipMinus, md, sd, num_teams, name, team_id}}, plus the same
    counters load_components returns}. The pitching group's reader, through the
    shared scraper cache under `statsapi_saber_pitching_<season>`."""
    season = int(season)
    meta = {"values": {}, "season": season, "group": "pitching", "n_rows": 0,
            "n_players": 0, "n_multi_team": 0, "n_ambiguous": 0, "ambiguous_ids": [],
            "source": "statsapi sabermetrics, group=pitching (bulk, season totals)"}
    splits = fetch_pitching_splits(season)
    if not splits:
        return meta
    values, ambiguous, n_multi = pitching_values(splits)
    meta.update({"values": values, "n_rows": len(splits), "n_players": len(values),
                 "n_multi_team": n_multi, "n_ambiguous": len(ambiguous),
                 "ambiguous_ids": ambiguous})
    return meta
