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
"""
from __future__ import annotations

import json
import logging
from typing import Optional

_log = logging.getLogger(__name__)

SABER_URL = ("https://statsapi.mlb.com/api/v1/stats?stats=sabermetrics"
             "&group=hitting&season={season}&sportId=1&playerPool=All&limit=2000")

RUN_PARTS = ("batting", "baseRunning", "fielding", "positional", "wLeague", "replacement")


def cache_key(season: int) -> str:
    return f"statsapi_saber_hitting_{int(season)}"


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


def fetch_splits(season: int) -> Optional[list]:
    """The season's raw split rows through the shared scraper cache (24h TTL on
    the current season, 30 days on a past one). None on any failure."""
    try:
        from scrapers import _fetch       # network-gated: nothing fetches at import
        fr = _fetch(SABER_URL.format(season=int(season)), cache_key(season),
                    accept_json=True)
        if fr.status != 200 or not fr.body:
            _log.warning("sabermetrics %s: fetch failed (status=%s)", season, fr.status)
            return None
        stats = json.loads(fr.body).get("stats") or []
        return (stats[0].get("splits") or []) if stats else []
    except Exception as e:   # noqa: BLE001 - every reader is best-effort
        _log.warning("sabermetrics %s: unavailable (%s)", season, e)
        return None


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
