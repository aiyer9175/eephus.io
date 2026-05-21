"""Tests for the FanGraphs CSV auto-ingest module.

Run: python -m pytest test_fangraphs_csv.py -v
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fangraphs_csv import (
    _parse_filename,
    _parse_row,
    _to_grade,
    _to_int,
    parse_csv,
    ingest_drops,
)


# ---------------------------------------------------------------------------
# Filename parser
# ---------------------------------------------------------------------------

class TestParseFilename:
    def test_top100(self):
        assert _parse_filename("fangraphs_top100_2026-05-21.csv") == \
            ("top100", "2026-05-21")

    def test_org_board(self):
        assert _parse_filename("fangraphs_org-PIT_2026-05-21.csv") == \
            ("org-pit", "2026-05-21")

    def test_draft_board(self):
        assert _parse_filename("fangraphs_draft-2026_2026-04-01.csv") == \
            ("draft-2026", "2026-04-01")

    def test_case_insensitive_extension(self):
        assert _parse_filename("fangraphs_top100_2026-05-21.CSV") == \
            ("top100", "2026-05-21")

    def test_rejects_wrong_prefix(self):
        assert _parse_filename("mlb_top100_2026-05-21.csv") is None

    def test_rejects_missing_date(self):
        assert _parse_filename("fangraphs_top100.csv") is None

    def test_rejects_bad_date(self):
        assert _parse_filename("fangraphs_top100_2026-13-01.csv") is None

    def test_accepts_free_form_slug(self):
        assert _parse_filename("fangraphs_midseason-update_2026-07-15.csv") == \
            ("midseason-update", "2026-07-15")


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------

class TestCoercion:
    def test_to_int_blank(self):
        assert _to_int("") is None
        assert _to_int("—") is None
        assert _to_int(None) is None

    def test_to_int_commas_and_dollar(self):
        assert _to_int("$6,530,000") == 6530000

    def test_to_grade_valid(self):
        assert _to_grade("60") == 60.0

    def test_to_grade_out_of_range(self):
        assert _to_grade("85") is None
        assert _to_grade("15") is None

    def test_to_grade_blank(self):
        assert _to_grade("") is None


# ---------------------------------------------------------------------------
# Row → Snapshot
# ---------------------------------------------------------------------------

class TestParseRow:
    def test_standard_board_row(self):
        # Matches the sample-csv.csv shape (no tool grades).
        row = {
            "Top 100": "1", "Org Rk": "0", "Name": "Konnor Griffin",
            "Org": "PIT", "Pos": "SS", "Current Level": "MLB", "ETA": "2026",
            "FV": "70", "Risk": "High", "Trend": "",
            "Age": "20.06", "Ht": "6' 4\"", "Wt": "225",
            "B": "R", "T": "R",
            "Sign Yr": "2024", "Sign Mkt": "Draft", "Sign Org": "PIT",
            "Bonus": "6530000", "Signed From": "Jackson Prep (MS)",
            "Report": "Best prospect in baseball.", "Video": "https://...",
            "PlayerId": "12345",
        }
        snap = _parse_row(row, "top100", "2026-05-21")
        assert snap is not None
        assert snap.source == "fangraphs"
        assert snap.interval_label == "top100"
        assert snap.snapshot_date == "2026-05-21"
        assert snap.player_name == "Konnor Griffin"
        assert snap.player_key  # normalize_key produced something
        assert snap.org == "PIT"
        assert snap.position == "SS"
        assert snap.rank == 1
        assert snap.fv == 70
        assert snap.status == "active"
        # No tool grades on this CSV shape — but extras should be present.
        assert snap.tools is not None
        extras = snap.tools.get("_extras") or {}
        assert extras.get("risk") == "High"
        assert extras.get("eta_year") == 2026
        assert extras.get("current_level") == "MLB"
        assert extras.get("org_rank") == 0
        assert extras.get("weight") == 225
        assert extras.get("bats") == "R"
        assert extras.get("throws") == "R"
        assert extras.get("sign_year") == 2024
        assert extras.get("sign_org") == "PIT"
        assert extras.get("bonus") == 6530000
        assert extras.get("signed_from") == "Jackson Prep (MS)"
        assert extras.get("video_url") == "https://..."
        assert extras.get("fg_player_id") == 12345
        assert extras.get("report") == "Best prospect in baseball."

    def test_scouting_summary_with_tools(self):
        # Tool grades populate when columns are present + in range.
        row = {
            "Name": "Test Hitter", "Org": "LAD", "Pos": "CF", "FV": "55",
            "Hit": "60", "Game": "70", "Raw": "70", "Spd": "55",
            "Fld": "50", "Thr": "55", "Contact": "Above-Average",
        }
        snap = _parse_row(row, "top100", "2026-05-21")
        assert snap is not None
        assert snap.tools is not None
        assert snap.tools["hit"] == 60
        assert snap.tools["game_pwr"] == 70
        assert snap.tools["raw_pwr"] == 70
        assert snap.tools["speed"] == 55
        assert snap.tools["field"] == 50
        assert snap.tools["throw"] == 55
        extras = snap.tools.get("_extras") or {}
        assert extras.get("contact_style") == "Above-Average"

    def test_pitcher_tools(self):
        row = {
            "Name": "Ace Arms", "Org": "NYM", "Pos": "RHP", "FV": "60",
            "FB": "70", "SL": "60", "CB": "55", "CH": "55", "Cmd": "50",
        }
        snap = _parse_row(row, "top100", "2026-05-21")
        assert snap is not None
        assert snap.tools["fb"] == 70
        assert snap.tools["sl"] == 60
        assert snap.tools["cb"] == 55
        assert snap.tools["ch"] == 55
        assert snap.tools["cmd"] == 50

    def test_out_of_range_tool_dropped(self):
        # Grade outside [20,80] surfaces as missing rather than clamped.
        row = {"Name": "Bad Grade", "Org": "BOS", "Pos": "SS", "Hit": "85"}
        snap = _parse_row(row, "top100", "2026-05-21")
        # No valid tools + no extras → tools should be None.
        assert snap is not None
        assert snap.tools is None

    def test_skips_row_without_name(self):
        row = {"Org": "PIT", "Pos": "SS", "FV": "60"}
        snap = _parse_row(row, "top100", "2026-05-21")
        assert snap is None

    def test_rank_falls_back_to_org_rank(self):
        # An org-board CSV doesn't have a Top-100 column; org_rank should
        # populate the rank field instead.
        row = {"Name": "Org Prospect", "Org": "PIT", "Pos": "SS",
               "FV": "50", "Org Rk": "3"}
        snap = _parse_row(row, "org-pit", "2026-05-21")
        assert snap is not None
        assert snap.rank == 3


# ---------------------------------------------------------------------------
# parse_csv (whole-file)
# ---------------------------------------------------------------------------

_STANDARD_CSV = '''Top 100,Org Rk,Name,Org,Pos,Current Level,ETA,FV,Risk,Trend,Age,Ht,Wt,B,T,Sign Yr,Sign Mkt,Sign Org,Bonus,Signed From,Report,Video,PlayerId
1,0,"Konnor Griffin","PIT","SS","MLB",2026,"70","High",,"20.06","6 4","225","R","R",2024,"Draft","PIT",6530000,"Jackson Prep","short report","",12345
2,0,"Roman Anthony","BOS","CF","MLB",2025,"70","Low",,"21.5","6 2","200","L","R",2022,"Draft","BOS",2500000,"Marjory Stoneman Douglas HS","another report","",67890
'''

_TOOLS_CSV = '''Name,Org,Pos,FV,Hit,Game,Raw,Spd,Fld,Thr,Contact
Test Hitter,LAD,CF,55,60,70,70,55,50,55,Above-Average
Solid Bat,NYY,LF,50,55,55,60,40,45,40,Average
'''

_MALFORMED_CSV = '''Foo,Bar,Baz
1,2,3
'''


class TestParseCsv:
    def test_standard_csv(self, tmp_path):
        path = tmp_path / "fangraphs_top100_2026-05-21.csv"
        path.write_text(_STANDARD_CSV, encoding="utf-8")
        snaps, err = parse_csv(path)
        assert err is None
        assert len(snaps) == 2
        names = {s.player_name for s in snaps}
        assert "Konnor Griffin" in names
        assert "Roman Anthony" in names

    def test_tools_csv(self, tmp_path):
        path = tmp_path / "fangraphs_top100_2026-05-21.csv"
        path.write_text(_TOOLS_CSV, encoding="utf-8")
        snaps, err = parse_csv(path)
        assert err is None
        assert len(snaps) == 2
        by_name = {s.player_name: s for s in snaps}
        assert by_name["Test Hitter"].tools["hit"] == 60
        assert by_name["Test Hitter"].tools["_extras"]["contact_style"] == "Above-Average"

    def test_malformed_filename(self, tmp_path):
        path = tmp_path / "wrong_name.csv"
        path.write_text(_STANDARD_CSV, encoding="utf-8")
        snaps, err = parse_csv(path)
        assert snaps == []
        assert err and "filename" in err

    def test_missing_name_column(self, tmp_path):
        path = tmp_path / "fangraphs_top100_2026-05-21.csv"
        path.write_text(_MALFORMED_CSV, encoding="utf-8")
        snaps, err = parse_csv(path)
        assert snaps == []
        assert err and "Name" in err


# ---------------------------------------------------------------------------
# ingest_drops (file-move behavior, monkey-patched DB)
# ---------------------------------------------------------------------------

class TestIngestDrops:
    def test_ingests_and_moves_to_processed(self, tmp_path, monkeypatch):
        # Stub out the DB insert so the test doesn't touch the real DB.
        inserted = []

        def _fake_insert(snaps):
            n = 0
            for s in snaps:
                inserted.append(s)
                n += 1
            return n

        import fangraphs_csv as _mod
        monkeypatch.setattr("storage.insert_snapshots", _fake_insert)

        drop = tmp_path / "drop"
        processed = tmp_path / "drop" / "processed"
        drop.mkdir()
        (drop / "fangraphs_top100_2026-05-21.csv").write_text(
            _STANDARD_CSV, encoding="utf-8")

        n_snaps, n_files = _mod.ingest_drops(
            today=date(2026, 5, 21),
            drop_dir=drop, processed_dir=processed,
        )
        assert n_snaps == 2
        assert n_files == 1
        # Original file gone from drop folder.
        assert not (drop / "fangraphs_top100_2026-05-21.csv").exists()
        # Moved into processed/ with timestamp suffix.
        moved = list(processed.glob("fangraphs_top100_2026-05-21.csv.imported.*"))
        assert len(moved) == 1

    def test_bad_filename_stays_put(self, tmp_path, monkeypatch):
        import fangraphs_csv as _mod
        monkeypatch.setattr("storage.insert_snapshots",
                            lambda snaps: len(list(snaps)))
        drop = tmp_path / "drop"
        processed = drop / "processed"
        drop.mkdir()
        bad = drop / "not_a_fangraphs_file.csv"
        bad.write_text(_STANDARD_CSV, encoding="utf-8")

        n_snaps, n_files = _mod.ingest_drops(
            today=date(2026, 5, 21),
            drop_dir=drop, processed_dir=processed,
        )
        assert n_snaps == 0
        assert n_files == 0
        # File stays put for the user to rename.
        assert bad.exists()

    def test_no_files_returns_zero(self, tmp_path):
        import fangraphs_csv as _mod
        drop = tmp_path / "drop"
        processed = drop / "processed"
        n_snaps, n_files = _mod.ingest_drops(
            drop_dir=drop, processed_dir=processed,
        )
        assert n_snaps == 0
        assert n_files == 0
