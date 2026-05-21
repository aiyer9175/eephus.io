"""Tests for the FanGraphs four-CSV auto-ingest (v2)."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fangraphs_csv import (
    _parse_filename,
    _parse_grade_pair,
    _parse_summary_row,
    _parse_position_row,
    _parse_pitching_row,
    _parse_physical_row,
    _join_report_set,
    _build_snapshot,
    _detect_publish_date,
    ingest_drops,
)


# ---------------------------------------------------------------------------
# Filename parser
# ---------------------------------------------------------------------------

class TestParseFilename:
    def test_summary(self):
        assert _parse_filename("summary-demo.csv") == ("summary", "demo")

    def test_position(self):
        assert _parse_filename("position-2025-updated.csv") == \
            ("position", "2025-updated")

    def test_pitching(self):
        assert _parse_filename("pitching-org-pit.csv") == ("pitching", "org-pit")

    def test_physical_short(self):
        assert _parse_filename("physical-demo.csv") == ("physical", "demo")

    def test_physical_long(self):
        assert _parse_filename("physicalattributes-demo.csv") == ("physical", "demo")

    def test_case_insensitive(self):
        assert _parse_filename("Summary-Demo.CSV") == ("summary", "demo")

    def test_rejects_v1_pattern(self):
        assert _parse_filename("fangraphs_top100_2026-05-21.csv") is None

    def test_rejects_unknown_type(self):
        assert _parse_filename("offense-demo.csv") is None

    def test_rejects_no_slug(self):
        assert _parse_filename("summary-.csv") is None


# ---------------------------------------------------------------------------
# Grade pair parser
# ---------------------------------------------------------------------------

class TestParseGradePair:
    def test_standard(self):
        assert _parse_grade_pair("20 / 45") == (20.0, 45.0)

    def test_single_value(self):
        assert _parse_grade_pair("60") == (None, 60.0)

    def test_blank(self):
        assert _parse_grade_pair("") == (None, None)

    def test_present_only(self):
        assert _parse_grade_pair("50 / ") == (50.0, None)

    def test_future_only(self):
        assert _parse_grade_pair(" / 70") == (None, 70.0)

    def test_out_of_range_drops(self):
        assert _parse_grade_pair("10 / 85") == (None, None)

    def test_junk(self):
        assert _parse_grade_pair("foo / bar") == (None, None)


# ---------------------------------------------------------------------------
# Row parsers
# ---------------------------------------------------------------------------

class TestSummaryRow:
    def test_minimum(self):
        r = _parse_summary_row({"Name": "Konnor Griffin", "Org": "PIT",
                                "Pos": "SS", "FV": "65", "PlayerId": "35376"})
        assert r["player_name"] == "Konnor Griffin"
        assert r["org"] == "PIT"
        assert r["position"] == "SS"
        assert r["fv"] == 65
        assert r["fg_player_id"] == 35376
        assert r["player_key"]

    def test_rich_fields(self):
        r = _parse_summary_row({
            "Top 100": "1", "Org Rk": "1", "Name": "Test Bat",
            "Org": "LAD", "Pos": "CF", "Current Level": "AA",
            "ETA": "2026", "FV": "55", "Risk": "Medium",
            "Trend": "Up", "Age": "21.5", "Ht": "6 4", "Wt": "210",
            "B": "L", "T": "R", "Sign Yr": "2023", "Sign Mkt": "Draft",
            "Sign Org": "LAD", "Bonus": "2500000",
            "Signed From": "Vanderbilt", "Report": "A long report.",
            "Video": "https://video", "PlayerId": "99999",
        })
        assert r["rank"] == 1
        assert r["org_rank"] == 1
        assert r["current_level"] == "AA"
        assert r["eta_year"] == 2026
        assert r["risk"] == "Medium"
        assert r["trend"] == "Up"
        assert r["age"] == 21.5
        assert r["weight"] == 210
        assert r["sign_year"] == 2023
        assert r["bonus"] == 2500000
        assert r["signed_from"] == "Vanderbilt"
        assert r["report"] == "A long report."

    def test_skips_no_name(self):
        assert _parse_summary_row({"Org": "PIT", "Pos": "SS", "FV": "60"}) is None


class TestPositionRow:
    def test_pres_fut(self):
        r = _parse_position_row({
            "Name": "Konnor Griffin", "Pos": "SS", "Org": "PIT",
            "Hit": "20 / 45", "Game Pwr": "20 / 70", "Raw Pwr": "60 / 70",
            "Spd": "70 / 70", "Fld": "35 / 55",
            "Con Style": "InsideOut", "Versa": "SS/CF",
            "Hard Hit%": "0.5", "PlayerId": "35376",
        })
        assert r["tools_future"]["hit"] == 45
        assert r["tools_future"]["game_pwr"] == 70
        assert r["tools_future"]["raw_pwr"] == 70
        assert r["tools_future"]["speed"] == 70
        assert r["tools_future"]["field"] == 55
        assert r["tools_present"]["hit"] == 20
        assert r["tools_present"]["game_pwr"] == 20
        assert r["contact_style"] == "InsideOut"
        assert r["versa"] == "SS/CF"
        assert r["hard_hit_pct"] == 0.5

    def test_handles_pitcher_blank(self):
        r = _parse_position_row({
            "Name": "Pitcher", "Pos": "RHP", "Org": "NYM",
            "Hit": "", "Game Pwr": "", "Raw Pwr": "",
            "Spd": "", "Fld": "", "Versa": "",
            "PlayerId": "12345",
        })
        assert r["tools_future"] == {}


class TestPitchingRow:
    def test_pres_fut(self):
        r = _parse_pitching_row({
            "Name": "Bubba Chandler", "Pos": "SP", "Org": "PIT",
            "TJ Date": "May 12, 2024", "FB Type": "Rise",
            "FB": "70 / 70", "SL": "45 / 50", "CB": "",
            "CH": "55 / 70", "CMD": "40 / 45",
            "Sits": "96-99", "Tops": "102", "PlayerId": "29868",
        })
        assert r["tools_future"]["fb"] == 70
        assert r["tools_future"]["sl"] == 50
        assert r["tools_future"]["ch"] == 70
        assert r["tools_future"]["cmd"] == 45
        assert "cb" not in r["tools_future"]
        assert r["tj_date"] == "2024-05-12"
        assert r["fb_type"] == "Rise"
        assert r["sits"] == "96-99"
        assert r["tops"] == "102"


class TestPhysicalRow:
    def test_basic(self):
        r = _parse_physical_row({
            "Name": "Konnor Griffin", "Pos": "SS", "Age": "19.4",
            "Frame": "2", "Athl": "2", "Levers": "Long",
            "Arm": "55", "Perf": "1", "Delivery": "",
            "PlayerId": "35376",
        })
        assert r["frame"] == 2
        assert r["athl"] == 2
        assert r["levers"] == "Long"
        assert r["arm"] == 55
        assert r["perf"] == 1
        assert r["delivery"] is None


# ---------------------------------------------------------------------------
# Join report set
# ---------------------------------------------------------------------------

class TestJoinReportSet:
    def _summary(self, name, pid, fv=60):
        return _parse_summary_row({"Name": name, "Org": "PIT", "Pos": "SS",
                                   "FV": str(fv), "PlayerId": pid})

    def test_join_by_fg_id(self):
        s = [self._summary("Konnor Griffin", "35376")]
        p = [_parse_position_row({"Name": "Konnor Griffin", "Pos": "SS",
                                   "Org": "PIT", "Hit": "20 / 45",
                                   "PlayerId": "35376"})]
        merged = _join_report_set(s, p, [], [])
        assert len(merged) == 1
        assert merged[0]["_position"]["tools_future"]["hit"] == 45

    def test_join_by_name_fallback(self):
        s = [self._summary("Konnor Griffin", "35376")]
        p = [_parse_position_row({"Name": "Konnor Griffin", "Pos": "SS",
                                   "Org": "PIT", "Hit": "20 / 45"})]
        merged = _join_report_set(s, p, [], [])
        assert len(merged) == 1
        assert merged[0]["_position"] is not None

    def test_summary_only(self):
        s = [self._summary("Solo Bat", "111")]
        merged = _join_report_set(s, [], [], [])
        assert len(merged) == 1
        assert "_position" not in merged[0]

    def test_orphan_dropped(self):
        s = [self._summary("Match Me", "111")]
        p = [_parse_position_row({"Name": "Unrelated", "Pos": "SS",
                                   "Org": "PIT", "Hit": "20 / 45",
                                   "PlayerId": "999"})]
        merged = _join_report_set(s, p, [], [])
        assert len(merged) == 1
        assert "_position" not in merged[0]


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------

class TestBuildSnapshot:
    def test_full_merge(self):
        s = _parse_summary_row({
            "Top 100": "1", "Name": "Konnor Griffin", "Org": "PIT",
            "Pos": "SS", "FV": "65", "Risk": "High", "Age": "19.4",
            "Report": "Best in baseball.", "Video": "url",
            "PlayerId": "35376", "Sign Yr": "2024", "Bonus": "6530000",
        })
        p = _parse_position_row({
            "Name": "Konnor Griffin", "Pos": "SS", "Org": "PIT",
            "Hit": "20 / 45", "Con Style": "InsideOut", "Versa": "SS/CF",
            "Hard Hit%": "0.5", "PlayerId": "35376",
        })
        pi = _parse_pitching_row({"Name": "Konnor Griffin", "Pos": "SS",
                                   "Org": "PIT", "PlayerId": "35376"})
        ph = _parse_physical_row({
            "Name": "Konnor Griffin", "Pos": "SS", "Age": "19.4",
            "Frame": "2", "Athl": "2", "Levers": "Long",
            "Arm": "55", "Perf": "1", "PlayerId": "35376",
        })
        merged = _join_report_set([s], [p], [pi], [ph])
        snap = _build_snapshot(merged[0], "demo", "2025-08-01")
        assert snap.source == "fangraphs"
        assert snap.interval_label == "demo"
        assert snap.snapshot_date == "2025-08-01"
        assert snap.player_name == "Konnor Griffin"
        assert snap.org == "PIT"
        assert snap.position == "SS"
        assert snap.fv == 65
        assert snap.rank == 1
        assert snap.tools["hit"] == 45
        extras = snap.tools["_extras"]
        assert extras["fg_player_id"] == 35376
        assert extras["risk"] == "High"
        assert extras["contact_style"] == "InsideOut"
        assert extras["versa"] == "SS/CF"
        assert extras["hard_hit_pct"] == 0.5
        assert extras["frame"] == 2
        assert extras["athl"] == 2
        assert extras["levers"] == "Long"
        assert extras["arm"] == 55
        assert extras["perf"] == 1
        assert extras["report"] == "Best in baseball."
        assert extras["present"]["hit"] == 20

    def test_pitcher_pitching_block(self):
        s = _parse_summary_row({"Name": "Bubba Chandler", "Org": "PIT",
                                 "Pos": "SP", "FV": "60",
                                 "PlayerId": "29868", "Age": "23.0"})
        pi = _parse_pitching_row({
            "Name": "Bubba Chandler", "Pos": "SP", "Org": "PIT",
            "FB": "70 / 70", "SL": "45 / 50", "CH": "55 / 70",
            "CMD": "40 / 45", "Sits": "96-99", "Tops": "102",
            "FB Type": "Rise", "PlayerId": "29868",
        })
        merged = _join_report_set([s], [], [pi], [])
        snap = _build_snapshot(merged[0], "demo", "2025-08-01")
        assert snap.tools["fb"] == 70
        assert snap.tools["sl"] == 50
        assert snap.tools["ch"] == 70
        assert snap.tools["cmd"] == 45
        assert snap.tools["_extras"]["fb_type"] == "Rise"
        assert snap.tools["_extras"]["sits"] == "96-99"
        assert snap.tools["_extras"]["tops"] == "102"


# ---------------------------------------------------------------------------
# Date auto-detect
# ---------------------------------------------------------------------------

class TestDetectPublishDate:
    def test_median_back_solve(self):
        target = date(2025, 7, 29)
        rows = []
        birth_dates = {}
        for i in range(6):
            bd = target - timedelta(days=int(365.25 * (18 + i * 0.5)))
            pkey = f"player_{i}"
            rows.append({
                "player_key": pkey,
                "age": (target - bd).days / 365.25,
            })
            birth_dates[pkey] = bd.isoformat()
        out = _detect_publish_date(rows, birth_dates, today=target + timedelta(days=10))
        assert out is not None
        out_date = date.fromisoformat(out)
        assert abs((out_date - target).days) <= 1

    def test_falls_back_to_mtime_when_no_matches(self):
        # mtime ~ 2024-06-01 12:00 UTC
        out = _detect_publish_date(
            [{"player_key": "unknown", "age": 21.0}],
            birth_dates={},
            fallback_mtime=1717243200.0,
            today=date(2026, 1, 1),
        )
        assert out is not None
        assert out.startswith("2024-")

    def test_no_signal_no_fallback_returns_none(self):
        out = _detect_publish_date([], {}, fallback_mtime=None,
                                    today=date(2026, 1, 1))
        assert out is None


# ---------------------------------------------------------------------------
# ingest_drops integration
# ---------------------------------------------------------------------------

_SUMMARY_CSV = '''Top 100,Org Rk,Name,Org,Pos,Current Level,ETA,FV,Risk,Trend,Age,Ht,Wt,B,T,Sign Yr,Sign Mkt,Sign Org,Bonus,Signed From,Report,Video,PlayerId
1,1,"Konnor Griffin","PIT","SS","MLB",2026,"65","High",,"19.4361111","6 4","210","R","R",2024,"Draft","PIT",6530000,"Jackson Prep","Best.","",35376
2,1,"Bubba Chandler","PIT","SP","MLB",2025,"60","Medium",,"23.0472222","6 3","200","R","R",2021,"Draft","PIT",3000000,"North Oconee","Power arm.","",29868
'''

_POSITION_CSV = '''Name,Pos,Org,Top 100,Org Rk,Age,Hit,Pitch Sel,Bat Ctrl,Con Style,Game Pwr,Raw Pwr,Spd,Fld,Versa,Hard Hit%,FV,PlayerId
"Konnor Griffin","SS","PIT",1,1,"19.4361111","20 / 45",50,50,"InsideOut","20 / 70","60 / 70","70 / 70","35 / 55","SS/CF",0.5,"65",35376
'''

_PITCHING_CSV = '''Name,Pos,Org,Top 100,Org Rk,Age,TJ Date,FB Type,FB,SL,CB,CH,CMD,Sits,Tops,FV,PlayerId
"Bubba Chandler","SP","PIT",2,1,"23.0472222",,"Rise","70 / 70","45 / 50","","55 / 70","40 / 45","96-99","102","60",29868
'''

_PHYSICAL_CSV = '''Name,Pos,Age,Frame,Athl,Levers,Arm,Perf,Delivery,PlayerId
"Konnor Griffin","SS","19.4361111",2,2,"Long",55,1,,35376
"Bubba Chandler","SP","23.0472222",1,1,"Long",70,0,"Smooth",29868
'''


class TestIngestDrops:
    def test_full_report_set(self, tmp_path, monkeypatch):
        inserted_snaps = []

        def _fake_insert(snaps):
            n = 0
            for s in snaps:
                inserted_snaps.append(s)
                n += 1
            return n

        monkeypatch.setattr("storage.insert_snapshots", _fake_insert)
        monkeypatch.setattr("storage.load_birth_dates", lambda: {
            "konnor_griffin":  (date(2025, 7, 29) - timedelta(days=int(365.25 * 19.4361111))).isoformat(),
            "bubba_chandler":  (date(2025, 7, 29) - timedelta(days=int(365.25 * 23.0472222))).isoformat(),
        })

        drop = tmp_path / "drop"
        processed = drop / "processed"
        drop.mkdir()
        (drop / "summary-demo.csv").write_text(_SUMMARY_CSV, encoding="utf-8")
        (drop / "position-demo.csv").write_text(_POSITION_CSV, encoding="utf-8")
        (drop / "pitching-demo.csv").write_text(_PITCHING_CSV, encoding="utf-8")
        (drop / "physicalattributes-demo.csv").write_text(_PHYSICAL_CSV, encoding="utf-8")

        n_inserted, n_sets = ingest_drops(
            today=date(2026, 1, 1),
            drop_dir=drop, processed_dir=processed,
        )
        assert n_sets == 1
        assert n_inserted == 2
        set_dirs = list(processed.glob("demo__*"))
        assert len(set_dirs) == 1
        moved = sorted(p.name for p in set_dirs[0].iterdir())
        assert "summary-demo.csv" in moved
        assert "position-demo.csv" in moved
        assert "pitching-demo.csv" in moved
        assert "physicalattributes-demo.csv" in moved
        by_name = {s.player_name: s for s in inserted_snaps}
        griffin = by_name["Konnor Griffin"]
        assert griffin.tools["hit"] == 45
        assert griffin.tools["_extras"]["contact_style"] == "InsideOut"
        assert griffin.tools["_extras"]["versa"] == "SS/CF"
        assert griffin.tools["_extras"]["hard_hit_pct"] == 0.5
        assert griffin.tools["_extras"]["frame"] == 2
        assert griffin.tools["_extras"]["arm"] == 55
        chandler = by_name["Bubba Chandler"]
        assert chandler.tools["fb"] == 70
        assert chandler.tools["_extras"]["sits"] == "96-99"

    def test_missing_summary_skips(self, tmp_path, monkeypatch):
        monkeypatch.setattr("storage.insert_snapshots",
                            lambda snaps: len(list(snaps)))
        monkeypatch.setattr("storage.load_birth_dates", lambda: {})
        drop = tmp_path / "drop"
        processed = drop / "processed"
        drop.mkdir()
        bad = drop / "position-orphan.csv"
        bad.write_text(_POSITION_CSV, encoding="utf-8")
        n_inserted, n_sets = ingest_drops(
            today=date(2026, 1, 1),
            drop_dir=drop, processed_dir=processed,
        )
        assert n_inserted == 0
        assert n_sets == 0
        assert bad.exists()

    def test_unparseable_filename_skips(self, tmp_path, monkeypatch):
        monkeypatch.setattr("storage.insert_snapshots",
                            lambda snaps: len(list(snaps)))
        monkeypatch.setattr("storage.load_birth_dates", lambda: {})
        drop = tmp_path / "drop"
        processed = drop / "processed"
        drop.mkdir()
        (drop / "random.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        n_inserted, n_sets = ingest_drops(
            today=date(2026, 1, 1),
            drop_dir=drop, processed_dir=processed,
        )
        assert n_inserted == 0
        assert n_sets == 0
