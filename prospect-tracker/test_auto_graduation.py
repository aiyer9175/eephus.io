# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the auto-graduation pathway.

When fetch_statline returns a stat line with level='MLB' for a player
still listed as active, run_monthly should call auto_graduate_player
and the next export should show the player in the graduates section.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import storage
from scrapers import Snapshot
from consensus import build_timeseries
from stats import (
    LEVEL_ORDER, LEVEL_LABELS, compute_age_decimal,
    StatLine, _highest_level,
)


class TestLevelOrder:
    def test_mlb_at_top_of_order(self):
        assert LEVEL_ORDER[0] == "MLB"

    def test_mlb_in_labels(self):
        assert LEVEL_LABELS["MLB"] == "MLB"
        assert LEVEL_LABELS["Major League Baseball"] == "MLB"

    def test_highest_level_picks_mlb_over_aaa(self):
        raw = [
            {"league": {"sport": {"name": "Triple-A"}}, "stat": {"gamesPlayed": 10}},
            {"league": {"sport": {"name": "Major League Baseball"}}, "stat": {"gamesPlayed": 5}},
        ]
        result = _highest_level(raw)
        assert result is not None
        assert result["_level"] == "MLB"

    def test_highest_level_aaa_when_no_mlb(self):
        raw = [
            {"league": {"sport": {"name": "Triple-A"}}, "stat": {"gamesPlayed": 50}},
            {"league": {"sport": {"name": "Double-A"}}, "stat": {"gamesPlayed": 20}},
        ]
        result = _highest_level(raw)
        assert result["_level"] == "AAA"


class TestAutoGraduation:
    def test_auto_graduate_inserts_snapshot(self, tmp_path, monkeypatch):
        # v21: auto_graduate_player is a back-compat alias for
        # auto_debut_player, which requires either an explicit debut_date
        # or a career_stats MLB row to anchor the snapshot. The pipeline
        # always passes one (from PlayerIndex.mlbDebutDate); the test
        # mirrors that contract.
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()

        snap = Snapshot(
            source="fangraphs", snapshot_date="2026-02-16",
            interval_label="FG 2026 Report",
            player_key="test_guy", player_name="Test Guy",
            position="SS", org="PIT", rank=1, fv=60.0, status="active",
        )
        storage.insert_snapshots([snap])

        # Before graduation: player is active
        ts = build_timeseries(storage.load_all_snapshots())
        assert len([p for p in ts if p.status == "debuted"]) == 0

        # Trigger auto-graduation (debut_date required post-v21)
        storage.auto_graduate_player("test_guy", grad_date="2026-04-15")

        # After graduation: player should have a graduated snapshot
        ts2 = build_timeseries(storage.load_all_snapshots())
        grads = [p for p in ts2 if p.status == "debuted"]
        assert len(grads) == 1
        assert grads[0].player_key == "test_guy"

    def test_auto_graduate_idempotent(self, tmp_path, monkeypatch):
        """Calling auto_graduate_player twice should not create duplicate rows."""
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()

        snap = Snapshot(
            source="fangraphs", snapshot_date="2026-02-16",
            interval_label="FG 2026 Report",
            player_key="test_guy2", player_name="Test Guy 2",
            position="RHP", org="NYM", rank=5, fv=55.0, status="active",
        )
        storage.insert_snapshots([snap])

        storage.auto_graduate_player("test_guy2", grad_date="2026-04-15")
        storage.auto_graduate_player("test_guy2", grad_date="2026-04-15")  # second call — should be ignored

        ts = build_timeseries(storage.load_all_snapshots())
        grads = [p for p in ts if p.player_key == "test_guy2" and p.status == "debuted"]
        assert len(grads) == 1  # still just one graduate

    def test_auto_graduate_refire_with_different_date_suppressed(self, tmp_path, monkeypatch):
        """A second auto-detect fire with a DIFFERENT date must be suppressed
        (audit residue 2026-07-15, the ryan_vilade class): the player is
        already debuted, so a veteran re-appearance must neither add a row
        nor move the debut date. Previously the snapshots UNIQUE key hid the
        re-fire silently; the guard makes it explicit."""
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()

        snap = Snapshot(
            source="fangraphs", snapshot_date="2026-02-16",
            interval_label="FG 2026 Report",
            player_key="test_guy3", player_name="Test Guy 3",
            position="C", org="BAL", rank=7, fv=50.0, status="active",
        )
        storage.insert_snapshots([snap])

        storage.auto_debut_player("test_guy3", debut_date="2021-09-18")
        storage.auto_debut_player("test_guy3", debut_date="2026-05-17")  # re-fire — suppressed

        ts = build_timeseries(storage.load_all_snapshots())
        p = [x for x in ts if x.player_key == "test_guy3"][0]
        assert p.status == "debuted"
        assert p.debut_date == "2021-09-18"  # first (true) date wins

    def test_auto_debut_date_clamped_to_roster_status(self, tmp_path, monkeypatch):
        """When roster_status already knows an EARLIER mlb_debut_date, a
        later detected date is a re-appearance artifact — the guard clamps
        the stamped snapshot to the known true debut (fixes the class at
        the source; players with no roster_status row are untouched)."""
        import json as _json
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()

        snap = Snapshot(
            source="fangraphs", snapshot_date="2026-02-16",
            interval_label="FG 2026 Report",
            player_key="test_guy4", player_name="Test Guy 4",
            position="OF", org="COL", rank=9, fv=45.0, status="active",
        )
        storage.insert_snapshots([snap])
        with storage.connect() as con:
            con.execute(
                "INSERT INTO roster_status (player_key, payload_json) VALUES (?, ?)",
                ("test_guy4", _json.dumps({"mlb_debut_date": "2021-09-18"})),
            )

        storage.auto_debut_player("test_guy4", debut_date="2026-05-17")

        ts = build_timeseries(storage.load_all_snapshots())
        p = [x for x in ts if x.player_key == "test_guy4"][0]
        assert p.status == "debuted"
        assert p.debut_date == "2021-09-18"  # clamped to the known true debut

    def test_auto_graduate_moves_to_grad_section_in_export(self, tmp_path, monkeypatch):
        """End-to-end: auto-graduated player should appear in graduates in the JSON."""
        import json
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()

        snap = Snapshot(
            source="fangraphs", snapshot_date="2026-02-16",
            interval_label="FG 2026 Report",
            player_key="mlb_guy", player_name="MLB Guy",
            position="OF", org="LAD", rank=10, fv=60.0, status="active",
        )
        storage.insert_snapshots([snap])

        storage.auto_graduate_player("mlb_guy", grad_date="2026-04-15")

        ts = build_timeseries(storage.load_all_snapshots())
        out = tmp_path / "out.json"
        storage.export_timeseries_json(ts, out)
        from storage import load_export_unified as _leu; payload = _leu(out)

        assert payload["active_count"] == 0
        assert payload["debut_count"] == 1
        assert payload["debuts"][0]["player_name"] == "MLB Guy"

    def test_missing_player_does_not_crash(self, tmp_path, monkeypatch):
        """auto_graduate_player with an unknown key should silently do nothing."""
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()
        # Should not raise
        storage.auto_graduate_player("player_that_does_not_exist")

    def test_load_snapshots_canonicalizes_known_aliases(self, tmp_path, monkeypatch):
        """Historical DB rows under old Josuar spellings should collapse."""
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()
        storage.insert_snapshots([
            Snapshot(
                source="just_baseball", snapshot_date="2026-03-04",
                interval_label="JB 2026 Preseason",
                player_key="josuar_de_jesus", player_name="Josuar De Jesus",
                position=None, org=None, rank=58, fv=None, status="active",
            ),
            Snapshot(
                source="fangraphs", snapshot_date="2026-05-17",
                interval_label="FG 2026 Report",
                player_key="josuar_gonzalez", player_name="Josuar Gonzalez",
                position="SS", org="SFG", rank=44, fv=50.0, status="active",
            ),
        ])

        ts = build_timeseries(storage.load_all_snapshots())

        assert len([p for p in ts if p.player_key == "josuar_gonzalez"]) == 1
        assert all("josuar_de_jesus" not in p.player_key for p in ts)


class TestFetchStatlineMLBDetection:
    """
    Unit-level tests for the fetch_statline → MLB-level detection pathway.
    We mock the HTTP call and verify the returned StatLine has level='MLB'
    when the API returns a Major League Baseball split.
    """

    def _make_response(self, level_name: str, is_pitcher: bool = False):
        """Build a fake API response for a player at the given level.
        The MLB Stats API nests level info under split['league']['sport']['name'].
        """
        if is_pitcher:
            stat = {"gamesPlayed": 10, "era": "3.14", "inningsPitched": "45.0",
                    "strikeoutsPer9Inn": "10.2", "walksPer9Inn": "2.8"}
        else:
            stat = {"gamesPlayed": 20, "avg": ".301", "obp": ".380",
                    "slg": ".501", "ops": ".881", "homeRuns": 5,
                    "stolenBases": 3, "plateAppearances": 80,
                    "baseOnBalls": 10, "strikeOuts": 18}
        return {
            "stats": [{
                "splits": [{
                    "league": {"sport": {"name": level_name}},
                    "stat": stat,
                }]
            }]
        }

    def test_mlb_split_returns_mlb_statline(self):
        from stats import fetch_statline
        fake = self._make_response("Major League Baseball")
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake
        mock_resp.raise_for_status = MagicMock()

        with patch("stats.requests.get", return_value=mock_resp), \
             patch("stats.time.sleep"):
            sl = fetch_statline("test", 12345, 2026, is_pitcher=False)

        assert sl is not None
        assert sl.level == "MLB"

    def test_aaa_split_returns_aaa_statline(self):
        from stats import fetch_statline
        fake = self._make_response("Triple-A")
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake
        mock_resp.raise_for_status = MagicMock()

        with patch("stats.requests.get", return_value=mock_resp), \
             patch("stats.time.sleep"):
            sl = fetch_statline("test", 12345, 2026, is_pitcher=False)

        assert sl is not None
        assert sl.level == "AAA"

    def test_mlb_split_for_pitcher(self):
        from stats import fetch_statline
        fake = self._make_response("Major League Baseball", is_pitcher=True)
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake
        mock_resp.raise_for_status = MagicMock()

        with patch("stats.requests.get", return_value=mock_resp), \
             patch("stats.time.sleep"):
            sl = fetch_statline("test", 12345, 2026, is_pitcher=True)

        assert sl is not None
        assert sl.level == "MLB"
        assert sl.is_pitcher is True
        assert sl.era == "3.14"

    def test_prefers_mlb_over_aaa_in_same_response(self):
        """Player called up mid-season: response has both AAA and MLB splits."""
        from stats import fetch_statline
        fake = {
            "stats": [{
                "splits": [
                    {
                        "league": {"sport": {"name": "Triple-A"}},
                        "stat": {"gamesPlayed": 40, "avg": ".290", "obp": ".360",
                                 "slg": ".480", "ops": ".840", "homeRuns": 8,
                                 "stolenBases": 5, "plateAppearances": 160,
                                 "baseOnBalls": 18, "strikeOuts": 35},
                    },
                    {
                        "league": {"sport": {"name": "Major League Baseball"}},
                        "stat": {"gamesPlayed": 12, "avg": ".250", "obp": ".320",
                                 "slg": ".400", "ops": ".720", "homeRuns": 2,
                                 "stolenBases": 0, "plateAppearances": 40,
                                 "baseOnBalls": 4, "strikeOuts": 10},
                    },
                ]
            }]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake
        mock_resp.raise_for_status = MagicMock()

        with patch("stats.requests.get", return_value=mock_resp), \
             patch("stats.time.sleep"):
            sl = fetch_statline("test", 12345, 2026, is_pitcher=False)

        assert sl is not None
        assert sl.level == "MLB", \
            f"Expected MLB (called-up player), got {sl.level}"
        assert sl.games == 12  # MLB games, not AAA games

    def test_complex_statline_falls_back_to_year_by_year(self):
        from stats import fetch_statline

        empty = {"stats": [{"splits": []}]}
        cpx = {"stats": [{"splits": [{
            "season": "2026",
            "league": {"name": "Arizona Complex League"},
            "stat": {"gamesPlayed": 8, "avg": ".423", "obp": ".545",
                     "slg": ".654", "ops": "1.199", "homeRuns": 1,
                     "stolenBases": 2, "plateAppearances": 33,
                     "baseOnBalls": 7, "strikeOuts": 8},
        }]}]}
        responses = []
        for payload in (empty, empty, cpx):
            mock_resp = MagicMock()
            mock_resp.json.return_value = payload
            mock_resp.raise_for_status = MagicMock()
            responses.append(mock_resp)

        with patch("stats.requests.get", side_effect=responses), \
             patch("stats.time.sleep"):
            sl = fetch_statline("josuar_gonzalez", 829034, 2026, is_pitcher=False)

        assert sl is not None
        assert sl.level == "CPX"
        assert sl.avg == ".423"


class TestMlbPipelineInternational:
    def test_parses_static_international_rankings_without_org(self):
        from scrapers import FetchResult, scrape_mlb_international

        html = """
        <main>
          <h1>Prospect Rankings</h1>
          <div>Rank Player Position Birthplace Age Height / Weight Bats Throws</div>
          <div>1</div>
          <img alt="Photo headshot of Luis Hernández">
          <div>Luis Hernández</div>
          <div>SS San Juan de los Morros, Venezuela 17 5' 10" / 172 lbs R R</div>
          <div>2</div>
          <img alt="Photo headshot of Wandy Asigen">
          <div>Wandy Asigen</div>
          <div>SS Puerto Plata, Dominican Republic 16 6' 0" / 180 lbs L R</div>
          <button>Show Full List</button>
        </main>
        """

        with patch("scrapers._fetch", return_value=FetchResult(html, 200, False, "u")):
            rows = scrape_mlb_international(
                "https://www.mlb.com/milb/prospects/international/",
                "MLB Pipeline 2026 International",
                "2026-05-19",
                2026,
            )

        assert [r.player_key for r in rows] == ["luis_hernandez", "wandy_asigen"]
        # Rank is intentionally None for the IFA scraper — the IFA list
        # ranks players 1-50 within the international class only, NOT
        # against the overall Top-100 prospect pool. Surfacing it would
        # let a #1 IFA (real FV ~55) inherit a Top-100 #1 rank-implied
        # FV ~70 through the consensus engine.
        assert rows[0].rank is None
        assert rows[0].position == "SS"
        assert rows[0].org is None
