"""Tests for the bulk season-stats fetch + career-cache merge path."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import stats
from stats import (
    bulk_fetch_season_stats, merge_bulk_into_career_cache,
    _career_row_from_bulk_split, BULK_STATS_SPORT_IDS,
)


def _resp(data: dict, status: int = 200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = data
    m.raise_for_status = MagicMock()
    return m


def _split_hitter(pid: int, name: str, sport_id: int, *,
                  avg=".280", ops="0.800", pa=400, hr=10, ab=350,
                  bb=30, so=80, games=100):
    """Build one hitter split in the bulk endpoint's actual response shape."""
    return {
        "season": "2026",
        "player": {"id": pid, "fullName": name},
        "league": {"id": 117, "name": "INT"},
        "sport": {"id": sport_id, "abbreviation": stats._SPORT_ID_TO_LEVEL[sport_id]},
        "stat": {
            "gamesPlayed": games,
            "avg": avg, "obp": ".370", "slg": ".430", "ops": ops,
            "homeRuns": hr, "stolenBases": 5, "rbi": 40, "atBats": ab,
            "plateAppearances": pa, "baseOnBalls": bb, "strikeOuts": so,
        },
    }


def _split_pitcher(pid: int, name: str, sport_id: int, *,
                   era="3.50", ip=120.0, wins=10, losses=5,
                   k_per_9=9.0, bb_per_9=2.5, whip="1.20", games=22):
    return {
        "season": "2026",
        "player": {"id": pid, "fullName": name},
        "league": {"id": 110, "name": "EAS"},
        "sport": {"id": sport_id, "abbreviation": stats._SPORT_ID_TO_LEVEL[sport_id]},
        "stat": {
            "gamesPlayed": games,
            "era": era, "inningsPitched": str(ip),
            "wins": wins, "losses": losses,
            "strikeoutsPer9Inn": k_per_9, "walksPer9Inn": bb_per_9,
            "whip": whip,
        },
    }


def _bulk_response(splits: list[dict]) -> dict:
    return {"stats": [{"splits": splits}]}


# ---------------------------------------------------------------------------
# Row shape (the splice depends on every key the per-player path produces)
# ---------------------------------------------------------------------------

class TestCareerRowFromBulkSplit:
    def test_hitter_row_has_expected_fields(self):
        split = _split_hitter(123, "Test Hitter", sport_id=11, pa=200,
                              bb=20, so=50, ab=180)
        row = _career_row_from_bulk_split(split, group="hitting")
        assert row is not None
        assert row["season"] == 2026
        assert row["level"] == "AAA"
        assert row["level_label"] == "AAA"
        assert row["is_pitcher"] is False
        assert row["ab"] == 180
        # bb_pct = 20/200 * 100 = 10.0
        assert row["bb_pct"] == 10.0
        # k_pct = 50/200 * 100 = 25.0
        assert row["k_pct"] == 25.0

    def test_pitcher_row_has_expected_fields(self):
        split = _split_pitcher(456, "Test Pitcher", sport_id=12,
                               ip=80.5, wins=6, losses=2)
        row = _career_row_from_bulk_split(split, group="pitching")
        assert row is not None
        assert row["level"] == "AA"
        assert row["is_pitcher"] is True
        assert row["ip"] == 80.5
        assert row["wins"] == 6
        assert row["losses"] == 2

    def test_unknown_sport_id_returns_none(self):
        # sport_id=22 (DSL etc.) isn't in _SPORT_ID_TO_LEVEL → drop the row
        # rather than guess a level.
        split = {
            "season": "2026",
            "player": {"id": 1, "fullName": "DSL Kid"},
            "sport": {"id": 22, "abbreviation": "DSL"},
            "stat": {"avg": ".300"},
        }
        assert _career_row_from_bulk_split(split, group="hitting") is None


# ---------------------------------------------------------------------------
# Bulk fetcher — single & multi-sport, pagination, level collapse
# ---------------------------------------------------------------------------

class TestBulkFetchSeasonStats:
    def test_single_sport_single_page(self):
        with patch("stats.requests.get") as mock_get:
            mock_get.return_value = _resp(_bulk_response([
                _split_hitter(1, "Alpha", sport_id=11),
                _split_hitter(2, "Beta",  sport_id=11),
            ]))
            out = bulk_fetch_season_stats(2026, group="hitting", sport_ids=[11])
        assert set(out.keys()) == {1, 2}
        assert out[1]["level"] == "AAA"
        # One sport, one page (returned <page_size splits) → one call.
        assert mock_get.call_count == 1

    def test_multi_sport_calls_each(self):
        responses = {
            11: _bulk_response([_split_hitter(1, "AAA-Guy",  sport_id=11)]),
            12: _bulk_response([_split_hitter(2, "AA-Guy",   sport_id=12)]),
            13: _bulk_response([_split_hitter(3, "Aplus-Guy",sport_id=13)]),
        }
        def fake_get(url, timeout=None):
            for sid, body in responses.items():
                if f"sportIds={sid}" in url:
                    return _resp(body)
            return _resp({"stats": []})
        with patch("stats.requests.get", side_effect=fake_get):
            out = bulk_fetch_season_stats(2026, group="hitting",
                                          sport_ids=[11, 12, 13])
        assert {out[1]["level"], out[2]["level"], out[3]["level"]} \
            == {"AAA", "AA", "A+"}

    def test_player_at_two_levels_keeps_highest(self):
        """Same mlbam_id seen in both AAA and AA → keep AAA (higher)."""
        responses = {
            11: _bulk_response([_split_hitter(99, "Mover", sport_id=11,
                                              avg=".350")]),
            12: _bulk_response([_split_hitter(99, "Mover", sport_id=12,
                                              avg=".200")]),
        }
        def fake_get(url, timeout=None):
            for sid, body in responses.items():
                if f"sportIds={sid}" in url:
                    return _resp(body)
            return _resp({"stats": []})
        with patch("stats.requests.get", side_effect=fake_get):
            out = bulk_fetch_season_stats(2026, group="hitting",
                                          sport_ids=[11, 12])
        assert out[99]["level"] == "AAA"
        assert out[99]["avg"] == ".350"

    def test_pagination_continues_until_short_page(self):
        page1 = _bulk_response([
            _split_hitter(i, f"P{i}", sport_id=11) for i in range(1, 6)
        ])
        page2 = _bulk_response([
            _split_hitter(i, f"P{i}", sport_id=11) for i in range(6, 9)
        ])
        seen_offsets = []
        def fake_get(url, timeout=None):
            if "offset=0" in url:
                seen_offsets.append(0)
                return _resp(page1)
            if "offset=5" in url:
                seen_offsets.append(5)
                return _resp(page2)
            return _resp({"stats": []})
        with patch("stats.requests.get", side_effect=fake_get):
            out = bulk_fetch_season_stats(2026, group="hitting",
                                          sport_ids=[11], page_size=5)
        # 8 distinct players across 2 pages
        assert len(out) == 8
        # Page 1 was full (5 == page_size) → paginate; page 2 was short
        # (3 < page_size) → stop.
        assert seen_offsets == [0, 5]

    def test_network_error_breaks_inner_loop(self):
        """If the HTTP call raises, we abort that sport but continue with
        the next sport."""
        calls = {"n": 0}
        def fake_get(url, timeout=None):
            calls["n"] += 1
            if "sportIds=11" in url:
                raise Exception("boom")
            return _resp(_bulk_response([_split_hitter(2, "B", sport_id=12)]))
        with patch("stats.requests.get", side_effect=fake_get):
            out = bulk_fetch_season_stats(2026, group="hitting",
                                          sport_ids=[11, 12])
        assert set(out.keys()) == {2}


# ---------------------------------------------------------------------------
# Cache merge
# ---------------------------------------------------------------------------

class TestMergeBulkIntoCareerCache:
    def test_inserts_new_2026_row_at_top(self):
        career_cache = {
            "alpha": [
                {"season": 2025, "level": "AA", "level_label": "AA",
                 "games": 90, "avg": ".270", "is_pitcher": False,
                 "ab": 320, "ops": ".760", "obp": ".340", "slg": ".420",
                 "hr": 8, "sb": 3, "rbi": 35, "bb_pct": 8.0, "k_pct": 22.0},
            ],
        }
        bulk_row = {"season": 2026, "level": "AAA", "level_label": "AAA",
                    "games": 30, "avg": ".310", "is_pitcher": False,
                    "ab": 110, "ops": ".900", "obp": ".390", "slg": ".510",
                    "hr": 6, "sb": 2, "rbi": 18, "bb_pct": 12.0, "k_pct": 19.0}
        bulk_by_mlbam = {1001: bulk_row}
        id_cache = {"alpha": 1001}

        updates = merge_bulk_into_career_cache(
            bulk_by_mlbam, career_cache, id_cache,
            season=2026, eligible_keys={"alpha"},
        )
        assert "alpha" in updates
        rows = updates["alpha"]
        assert rows[0]["season"] == 2026
        assert rows[0]["level"] == "AAA"
        assert rows[1]["season"] == 2025
        # The cache was mutated in place too — the rest of the pipeline
        # reads from career_cache, not the returned updates dict.
        assert career_cache["alpha"][0]["season"] == 2026

    def test_replaces_existing_2026_row(self):
        """If a stale 2026 row is in the cache, the bulk row replaces it."""
        career_cache = {
            "beta": [
                {"season": 2026, "level": "AA", "level_label": "AA",
                 "games": 5, "is_pitcher": False, "avg": ".100"},
                {"season": 2025, "level": "A", "level_label": "A",
                 "games": 80, "is_pitcher": False, "avg": ".250"},
            ],
        }
        bulk_row = {"season": 2026, "level": "AAA", "level_label": "AAA",
                    "games": 40, "is_pitcher": False, "avg": ".320"}
        updates = merge_bulk_into_career_cache(
            {2002: bulk_row}, career_cache, {"beta": 2002},
            season=2026, eligible_keys={"beta"},
        )
        rows = updates["beta"]
        assert len(rows) == 2
        assert rows[0]["season"] == 2026
        assert rows[0]["level"] == "AAA"  # the new bulk row, not the stale AA
        assert rows[1]["season"] == 2025

    def test_eligible_keys_excludes_graduates(self):
        """Graduates should not have their cache updated from the bulk."""
        career_cache = {"grad": [], "active": []}
        bulk_by_mlbam = {
            10: {"season": 2026, "level": "MLB", "level_label": "MLB",
                 "games": 60, "is_pitcher": False, "avg": ".285"},
            20: {"season": 2026, "level": "AAA", "level_label": "AAA",
                 "games": 30, "is_pitcher": False, "avg": ".300"},
        }
        id_cache = {"grad": 10, "active": 20}

        updates = merge_bulk_into_career_cache(
            bulk_by_mlbam, career_cache, id_cache,
            season=2026, eligible_keys={"active"},  # graduate excluded
        )
        assert set(updates.keys()) == {"active"}

    def test_caps_at_career_seasons_kept(self):
        """When merging would push the list past CAREER_SEASONS_KEPT,
        oldest seasons get dropped from the tail."""
        from stats import CAREER_SEASONS_KEPT
        # Build CAREER_SEASONS_KEPT existing rows for seasons 2021..2025.
        old_rows = [
            {"season": 2021 + i, "level": "A", "level_label": "A",
             "games": 50, "is_pitcher": False, "avg": ".250"}
            for i in range(CAREER_SEASONS_KEPT)
        ]
        # Reverse to newest-first (the order fetch_career_stats emits).
        old_rows.sort(key=lambda r: -r["season"])
        career_cache = {"gamma": list(old_rows)}
        bulk_row = {"season": 2026, "level": "AAA", "level_label": "AAA",
                    "games": 30, "is_pitcher": False, "avg": ".310"}

        updates = merge_bulk_into_career_cache(
            {3003: bulk_row}, career_cache, {"gamma": 3003},
            season=2026, eligible_keys={"gamma"},
        )
        rows = updates["gamma"]
        assert len(rows) == CAREER_SEASONS_KEPT
        assert rows[0]["season"] == 2026
        # The oldest row (2021) got dropped.
        assert all(r["season"] != 2021 for r in rows)
