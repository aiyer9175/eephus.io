# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A PROSPX card's career table keeps every level line of a multi-level season (RPR10).

The served defect (2026-10-01): the Statcast (tracked parks) row named a level the
card's own career table lacked for that season, because the table had lost the line.
Aroon Escobar's 2025 read AA 22 AB while the StatsAPI league census has him at A for
316 PA and A+ for 198; Josh Kasevich's 2024 read AAA with no AA line (393 PA).

Cause: the bulk season endpoint answers with the qualified pool only, the bulk merge
replaced a player's whole current season with the one level he qualified at, and the
per-player yearByYear pass skipped him as bulk-covered, so the season froze with one
line when it ended. A second cause sat in the per-player path: it read the level off
the league NAME, which before the 2021 realignment means a different level (Leandro
Cedeno's 2019 Midwest League season, Class A, read A+).

The served-artifact tests read data/timeseries.json (gitignored, written by the
export) and skip cleanly when it, the Statcast sidecar or the league census cache is
absent.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import stats
import run_monthly as R

ROOT = Path(__file__).resolve().parent
TIMESERIES = ROOT / "data" / "timeseries.json"
SIDECAR = ROOT / "data" / "statcast_aaa_hitters.json"
CENSUS = ROOT / ".cache" / "milb_stats"
CENSUS_LEVEL = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 15: "A"}
PITCHER_POS = {"P", "SP", "RP", "RHP", "LHP"}


def _players():
    if not TIMESERIES.exists():
        pytest.skip("data/timeseries.json absent (gitignored export)")
    return json.loads(TIMESERIES.read_text(encoding="utf-8"))["players"]


def _hitter_tables(players):
    """{mlbam: (player, {season: {levels}})} for hitters whose table holds hitting rows."""
    out = {}
    for p in players:
        mid = p.get("mlbam_id")
        rows = [r for r in (p.get("career_stats") or []) if r.get("is_pitcher") is False]
        if not mid or not rows:
            continue
        seasons = defaultdict(set)
        for r in rows:
            seasons[int(r["season"])].add(r["level"])
        out[int(mid)] = (p, seasons)
    return out


def _identity_collision(p) -> bool:
    """A key whose tracked position is a pitcher while its id is a hitter: two people
    share the slug (jesus_castillo: an LAA right-hander 2018-19 and a PIT shortstop
    2024). The monthly fetch asks the pitching feed for a hitter's id, gets nothing,
    and the table keeps whatever it held. That is the identity lane's defect, not a
    lost level line, and is counted separately below."""
    return (p.get("position") or "").upper() in PITCHER_POS


# --------------------------------------------------------------------------- #
# Served artifacts
# --------------------------------------------------------------------------- #

def test_sidecar_levels_appear_in_the_card_table():
    if not SIDECAR.exists():
        pytest.skip("data/statcast_aaa_hitters.json absent")
    side = json.loads(SIDECAR.read_text(encoding="utf-8")).get("by_mlbam") or {}
    tables = _hitter_tables(_players())
    checked, missing, collisions = 0, [], []
    for mid, row in side.items():
        hit = tables.get(int(mid))
        if hit is None or not row.get("season"):
            continue
        p, seasons = hit
        for lvl in row.get("levels") or []:
            checked += 1
            if lvl not in seasons.get(int(row["season"]), set()):
                (collisions if _identity_collision(p) else missing).append(
                    (p["player_key"], row["season"], lvl))
    assert checked > 100, f"only {checked} sidecar levels matched a card table"
    assert not missing, f"{len(missing)} sidecar levels absent from the card table: {missing[:15]}"
    # The identity collisions are pinned by name so a new one fails here too.
    assert {k for k, _s, _l in collisions} <= {"jesus_castillo"}, collisions


def test_every_census_line_of_50_pa_appears_in_the_card_table():
    files = sorted(CENSUS.glob("hitting_1[1-5]_*.json")) if CENSUS.exists() else []
    if not files:
        pytest.skip("StatsAPI league census cache (.cache/milb_stats) absent")
    pa = defaultdict(int)
    for f in files:
        sport = int(f.stem.split("_")[1])
        season = int(f.stem.split("_")[2])
        for r in json.loads(f.read_text(encoding="utf-8")):
            if r.get("mlbam"):
                pa[(int(r["mlbam"]), season, CENSUS_LEVEL[sport])] += int(r.get("pa") or 0)
    tables = _hitter_tables(_players())
    checked, missing, collisions = 0, [], []
    for (mid, season, lvl), n in pa.items():
        hit = tables.get(mid)
        if n < 50 or hit is None:
            continue
        p, seasons = hit
        if season < min(seasons):
            continue                      # older than the table keeps (5 seasons)
        checked += 1
        if lvl not in seasons.get(season, set()):
            (collisions if _identity_collision(p) else missing).append(
                (p["player_key"], season, lvl, n))
    assert checked > 2000, f"only {checked} census lines matched a card table"
    assert not missing, f"{len(missing)} of {checked} census lines absent: {missing[:15]}"
    assert {c[0] for c in collisions} <= {"jesus_castillo"}, collisions


@pytest.mark.parametrize("key,season,level", [
    ("aroon_escobar", 2025, "A"),
    ("aroon_escobar", 2025, "A+"),
    ("josh_kasevich", 2024, "AA"),
])
def test_pinned_level_lines(key, season, level):
    p = next((p for p in _players() if p["player_key"] == key), None)
    if p is None:
        pytest.skip(f"{key} not on the served board")
    have = {(r["season"], r["level"]) for r in p.get("career_stats") or []}
    assert (season, level) in have, sorted(have)


# --------------------------------------------------------------------------- #
# Producer
# --------------------------------------------------------------------------- #

def test_level_from_sport_reads_the_season_classification():
    assert stats._level_from_sport(14, "Midwest League") == "A"        # 2019 Class A
    assert stats._level_from_sport(13, "Florida State League") == "A+"  # 2019 High-A
    assert stats._level_from_sport(15, "New York-Penn League") == "A"
    assert stats._level_from_sport(16, "Gulf Coast League") == "CPX"
    assert stats._level_from_sport(16, "DSL") == "DSL"
    assert stats._level_from_sport(16, "Dominican Summer League") == "DSL"
    assert stats._level_from_sport(None, "Midwest League") is None
    assert stats._level_from_sport(23, "Mexican League") is None


def _yby_split(season, sport_id, league, team_id, pa, ab):
    return {
        "season": str(season),
        "team": {"id": team_id, "name": f"Team {team_id}", "parentOrgName": "St. Louis Cardinals"},
        "league": {"name": league},
        "sport": {"id": sport_id},
        "stat": {"gamesPlayed": 100, "plateAppearances": pa, "atBats": ab,
                 "avg": ".250", "obp": ".320", "slg": ".400", "ops": ".720"},
    }


def test_fetch_career_stats_labels_pre_2021_by_sport_and_keeps_every_level():
    payload = {"stats": [{"splits": [
        _yby_split(2019, 14, "Midwest League", 1, 396, 366),
        _yby_split(2018, 16, "Appalachian League", 2, 258, 223),
        _yby_split(2024, 12, "Eastern League", 3, 393, 363),
        _yby_split(2024, 11, "International League", 4, 170, 157),
        {"season": "2024", "team": None, "league": {}, "sport": {"id": 21},
         "stat": {"plateAppearances": 563}},
    ]}]}
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    with patch.object(stats.requests, "get", return_value=resp):
        rows = stats.fetch_career_stats("x", 1, is_pitcher=False)
    got = [(r["season"], r["level"]) for r in rows]
    assert got == [(2024, "AAA"), (2024, "AA"), (2019, "A"), (2018, "CPX")]


def test_bulk_row_reads_the_season_endpoint_dsl_name():
    split = {
        "season": "2026", "player": {"id": 9, "fullName": "D"},
        "team": {"id": 5, "name": "DSL Team", "parentOrgName": "Texas Rangers"},
        "league": {"name": "DSL"}, "sport": {"id": 16},
        "stat": {"gamesPlayed": 40, "plateAppearances": 150, "atBats": 120},
    }
    assert stats._career_row_from_bulk_split(split, "hitting")["level"] == "DSL"


def test_missing_league_lines_detector():
    idx = {("hitting", 800169): {(2025, "A"), (2025, "A+"), (2025, "AA"), (2026, "AA"),
                                 (2021, "A")}}
    rows = [{"season": 2026, "level": "AA"}, {"season": 2025, "level": "AA"},
            {"season": 2024, "level": "CPX"}]
    assert R._career_missing_league_lines(rows, 800169, False, idx) == [(2025, "A"), (2025, "A+")]
    full = rows + [{"season": 2025, "level": "A"}, {"season": 2025, "level": "A+"}]
    assert R._career_missing_league_lines(full, 800169, False, idx) == []
    # The pitching census is a different group; no id or no rows is nothing to compare.
    assert R._career_missing_league_lines(rows, 800169, True, idx) == []
    assert R._career_missing_league_lines(rows, None, False, idx) == []
    assert R._career_missing_league_lines([], 800169, False, idx) == []


def test_monthly_does_not_skip_a_table_missing_a_census_line():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    loop = src[src.index("incomplete_keys = {"):src.index("cs_tasks.append((key, mlbam, is_p))")]
    assert "and not missing_lines" in loop.split("skipped_bulk += 1")[0]
    assert loop.count("not missing_lines") >= 2, "both the bulk and the freshness skip must yield"
