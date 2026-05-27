# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the FanGraphs four-CSV auto-ingest (v3)."""

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
    _classify_csv,
    _sniff_headers,
    _group_subfolders,
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
        # v14 — perf no longer parsed; key is absent from the row dict.
        assert "perf" not in r
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
        # v14 — perf grade no longer ingested (statistical performance
        # surfaces elsewhere via wRC+ / xFIP-).
        assert "perf" not in extras
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
    def test_calendar_known_slug(self):
        # Known (year, kind) from the calendar table — back-solve and
        # mtime fallback are bypassed.
        out = _detect_publish_date("2025updated", [], {},
                                    fallback_mtime=None,
                                    today=date(2026, 1, 1))
        assert out == "2025-07-31"

    def test_calendar_dashed_slug(self):
        out = _detect_publish_date("2024-report", [], {},
                                    fallback_mtime=None,
                                    today=date(2026, 1, 1))
        assert out == "2024-02-14"

    def test_calendar_underscore_slug(self):
        out = _detect_publish_date("2023_Graduated", [], {},
                                    fallback_mtime=None,
                                    today=date(2026, 1, 1))
        assert out == "2023-11-06"

    def test_calendar_unknown_year_uses_kind_defaults(self):
        # 2099 isn't in the table, but the kind defaults should fire.
        out = _detect_publish_date("2099updated", [], {},
                                    fallback_mtime=None,
                                    today=date(2100, 1, 1))
        assert out == "2099-07-30"  # _FG_TYPE_DEFAULTS["updated"]

    def test_median_back_solve_when_slug_doesnt_match(self):
        # Free-form slug ("midseason-special") doesn't match the regex
        # → fall through to age-based back-solve.
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
        out = _detect_publish_date("midseason-special", rows, birth_dates,
                                    today=target + timedelta(days=10))
        assert out is not None
        out_date = date.fromisoformat(out)
        assert abs((out_date - target).days) <= 1

    def test_falls_back_to_mtime_when_no_matches(self):
        # mtime ~ 2024-06-01 12:00 UTC. Free-form slug → calendar
        # bypassed, no birth dates → back-solve fails, mtime path used.
        out = _detect_publish_date(
            "freeform-slug",
            [{"player_key": "unknown", "age": 21.0}],
            birth_dates={},
            fallback_mtime=1717243200.0,
            today=date(2026, 1, 1),
        )
        assert out is not None
        assert out.startswith("2024-")

    def test_no_signal_no_fallback_returns_none(self):
        out = _detect_publish_date("free-form", [], {}, fallback_mtime=None,
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


# ---------------------------------------------------------------------------
# Content-based CSV type classifier
# ---------------------------------------------------------------------------

class TestClassifyCsv:
    def test_summary_signature(self):
        headers = ["Top 100", "Org Rk", "Name", "Org", "Pos", "FV",
                   "Report", "Video", "PlayerId"]
        assert _classify_csv(headers) == "summary"

    def test_position_signature_with_versa(self):
        headers = ["Name", "Pos", "Org", "Top 100", "Hit", "Versa",
                   "Con Style", "Hard Hit%", "FV", "PlayerId"]
        assert _classify_csv(headers) == "position"

    def test_position_signature_old_layout(self):
        # Older FG exports (2021-2024) don't have Versa/Con Style but
        # do have Pitch Sel + Hit.
        headers = ["Name", "Pos", "Org", "Top 100", "Hit", "Pitch Sel",
                   "Bat Ctrl", "Game Pwr", "Avg EV", "Max EV", "Hard Hit%",
                   "FV", "PlayerId"]
        assert _classify_csv(headers) == "position"

    def test_pitching_signature(self):
        headers = ["Name", "Pos", "Org", "TJ Date", "FB Type", "FB",
                   "SL", "CMD", "Sits", "Tops", "FV", "PlayerId"]
        assert _classify_csv(headers) == "pitching"

    def test_physical_signature(self):
        headers = ["Name", "Pos", "Age", "Frame", "Athl", "Levers",
                   "Arm", "Perf", "Delivery", "PlayerId"]
        assert _classify_csv(headers) == "physical"

    def test_unclassifiable(self):
        headers = ["Foo", "Bar", "Baz"]
        assert _classify_csv(headers) is None

    def test_summary_wins_when_both_signatures_present(self):
        # If a CSV somehow has both Report (summary) and Pitch Sel
        # (position), the summary classification wins by ordering.
        headers = ["Name", "Hit", "Pitch Sel", "Report"]
        assert _classify_csv(headers) == "summary"


# ---------------------------------------------------------------------------
# Position parser — new extras
# ---------------------------------------------------------------------------

class TestPositionExtras:
    def test_avg_ev_max_ev(self):
        r = _parse_position_row({
            "Name": "Test Bat", "Pos": "CF", "Org": "LAD",
            "Hit": "60", "Avg EV": "92.5", "Max EV": "113.4",
            "PlayerId": "111",
        })
        assert r["avg_ev"] == 92.5
        assert r["max_ev"] == 113.4


class TestPitchingExtras:
    def test_rpm_columns(self):
        r = _parse_pitching_row({
            "Name": "Test Arm", "Pos": "SP", "Org": "NYM",
            "FB": "60", "RPM FB": "2350", "RPM Break": "2800",
            "PlayerId": "222",
        })
        assert r["rpm_fb"] == 2350
        assert r["rpm_break"] == 2800


# ---------------------------------------------------------------------------
# Subfolder layout end-to-end
# ---------------------------------------------------------------------------

class TestSubfolderLayout:
    def test_group_subfolders_classifies_by_content(self, tmp_path):
        sub = tmp_path / "2025_Updated"
        sub.mkdir()
        (sub / "anything1.csv").write_text(_SUMMARY_CSV, encoding="utf-8")
        (sub / "anything2.csv").write_text(_POSITION_CSV, encoding="utf-8")
        (sub / "anything3.csv").write_text(_PITCHING_CSV, encoding="utf-8")
        (sub / "anything4.csv").write_text(_PHYSICAL_CSV, encoding="utf-8")

        groups = _group_subfolders(tmp_path)
        assert len(groups) == 1
        grp = groups[0]
        assert grp["slug"] == "2025_Updated"
        assert grp["_is_subfolder"] is True
        assert "summary" in grp
        assert "position" in grp
        assert "pitching" in grp
        assert "physical" in grp
        assert grp["_unclassified"] == []

    def test_subfolder_ingest_moves_whole_folder(self, tmp_path, monkeypatch):
        inserted = []
        monkeypatch.setattr("storage.insert_snapshots",
                            lambda snaps: (inserted.extend(snaps), len(snaps))[1])
        monkeypatch.setattr("storage.load_birth_dates", lambda: {
            "konnor_griffin":  (date(2025, 7, 29) - timedelta(days=int(365.25 * 19.4361111))).isoformat(),
            "bubba_chandler":  (date(2025, 7, 29) - timedelta(days=int(365.25 * 23.0472222))).isoformat(),
        })

        drop = tmp_path / "drop"
        processed = drop / "processed"
        drop.mkdir()
        sub = drop / "2025_Updated"
        sub.mkdir()
        (sub / "filename-can-be-anything.csv").write_text(_SUMMARY_CSV, encoding="utf-8")
        (sub / "another-anything.csv").write_text(_POSITION_CSV, encoding="utf-8")
        (sub / "blah.csv").write_text(_PITCHING_CSV, encoding="utf-8")
        (sub / "different.csv").write_text(_PHYSICAL_CSV, encoding="utf-8")

        n_inserted, n_sets = ingest_drops(
            today=date(2026, 1, 1),
            drop_dir=drop, processed_dir=processed,
        )
        assert n_sets == 1
        assert n_inserted == 2

        # Whole folder moved to processed/<slug>__<date>/
        moved_dirs = list(processed.glob("2025_Updated__*"))
        assert len(moved_dirs) == 1
        moved_files = sorted(p.name for p in moved_dirs[0].iterdir())
        assert "filename-can-be-anything.csv" in moved_files
        assert "another-anything.csv" in moved_files
        assert "blah.csv" in moved_files
        assert "different.csv" in moved_files
        # Original subfolder gone.
        assert not sub.exists()

    def test_subfolder_missing_summary_stays_put(self, tmp_path, monkeypatch):
        monkeypatch.setattr("storage.insert_snapshots",
                            lambda snaps: len(list(snaps)))
        monkeypatch.setattr("storage.load_birth_dates", lambda: {})
        drop = tmp_path / "drop"
        processed = drop / "processed"
        drop.mkdir()
        sub = drop / "incomplete-set"
        sub.mkdir()
        (sub / "x.csv").write_text(_POSITION_CSV, encoding="utf-8")

        n_inserted, n_sets = ingest_drops(
            today=date(2026, 1, 1),
            drop_dir=drop, processed_dir=processed,
        )
        assert n_sets == 0
        assert sub.exists()  # folder stays for the user to fix


# ---------------------------------------------------------------------------
# called_from_run_monthly hint
# ---------------------------------------------------------------------------

class TestCalledFromRunMonthlyHint:
    def test_standalone_call_prints_hint(self, tmp_path, monkeypatch, caplog):
        import logging
        caplog.set_level(logging.INFO, logger="fangraphs_csv")
        monkeypatch.setattr("storage.insert_snapshots",
                            lambda snaps: len(list(snaps)))
        monkeypatch.setattr("storage.load_birth_dates", lambda: {
            "konnor_griffin":  (date(2025, 7, 29) - timedelta(days=int(365.25 * 19.4361111))).isoformat(),
            "bubba_chandler":  (date(2025, 7, 29) - timedelta(days=int(365.25 * 23.0472222))).isoformat(),
        })

        drop = tmp_path / "drop"
        processed = drop / "processed"
        drop.mkdir()
        (drop / "summary-x.csv").write_text(_SUMMARY_CSV, encoding="utf-8")
        ingest_drops(
            today=date(2026, 1, 1),
            drop_dir=drop, processed_dir=processed,
            called_from_run_monthly=False,
        )
        joined = "\n".join(rec.getMessage() for rec in caplog.records)
        assert "rebuild-only" in joined

    def test_run_monthly_call_suppresses_hint(self, tmp_path, monkeypatch, caplog):
        import logging
        caplog.set_level(logging.INFO, logger="fangraphs_csv")
        monkeypatch.setattr("storage.insert_snapshots",
                            lambda snaps: len(list(snaps)))
        monkeypatch.setattr("storage.load_birth_dates", lambda: {
            "konnor_griffin":  (date(2025, 7, 29) - timedelta(days=int(365.25 * 19.4361111))).isoformat(),
            "bubba_chandler":  (date(2025, 7, 29) - timedelta(days=int(365.25 * 23.0472222))).isoformat(),
        })

        drop = tmp_path / "drop"
        processed = drop / "processed"
        drop.mkdir()
        (drop / "summary-x.csv").write_text(_SUMMARY_CSV, encoding="utf-8")
        ingest_drops(
            today=date(2026, 1, 1),
            drop_dir=drop, processed_dir=processed,
            called_from_run_monthly=True,
        )
        joined = "\n".join(rec.getMessage() for rec in caplog.records)
        assert "rebuild-only" not in joined


# ---------------------------------------------------------------------------
# Pitch Sel / Bat Ctrl as canonical hitter tools (Step 3 of the
# "we're still failing to pull tools from FG" integration)
# ---------------------------------------------------------------------------

class TestPitchSelBatCtrlCanonical:
    def test_position_row_promotes_pitch_sel_and_bat_ctrl(self):
        """FG-published Pitch Sel and Bat Ctrl land in tools_future as
        canonical hitter tools (no "/" split — single value treated as
        future-only by _parse_grade_pair), NOT in extras."""
        r = _parse_position_row({
            "Name": "Konnor Griffin", "Pos": "SS", "Org": "PIT",
            "Hit": "20 / 45", "Pitch Sel": "60", "Bat Ctrl": "70",
            "PlayerId": "35376",
        })
        assert r["tools_future"]["pitch_sel"] == 60
        assert r["tools_future"]["bat_ctrl"] == 70
        # Extras must not duplicate them.
        assert "pitch_sel" not in r
        assert "bat_ctrl" not in r

    def test_build_snapshot_does_not_keep_pitch_sel_in_extras(self):
        s = _parse_summary_row({
            "Name": "Konnor Griffin", "Org": "PIT", "Pos": "SS",
            "FV": "65", "PlayerId": "35376",
        })
        p = _parse_position_row({
            "Name": "Konnor Griffin", "Pos": "SS", "Org": "PIT",
            "Hit": "20 / 45", "Pitch Sel": "60", "Bat Ctrl": "70",
            "PlayerId": "35376",
        })
        merged = _join_report_set([s], [p], [], [])
        snap = _build_snapshot(merged[0], "demo", "2025-08-01")
        assert snap.tools["pitch_sel"] == 60
        assert snap.tools["bat_ctrl"] == 70
        extras = snap.tools.get("_extras", {})
        assert "pitch_sel" not in extras
        assert "bat_ctrl" not in extras


# ---------------------------------------------------------------------------
# Storage round-trip: load_all_snapshots must preserve _extras and not
# corrupt numeric tool grades. Guard against the Step 1 regression.
# ---------------------------------------------------------------------------

class TestStorageRoundTripPreservesExtras:
    def test_insert_and_load_keeps_extras(self, tmp_path, monkeypatch):
        """Round-trip a FG snapshot with _extras through SQLite and
        confirm the load path returns both numeric tools AND the
        sibling _extras dict intact."""
        from scrapers import Snapshot
        import storage as storage_mod

        # Point storage at an isolated DB for this test.
        db_path = tmp_path / "test_prospects.db"
        monkeypatch.setattr(storage_mod, "DB_PATH", db_path)

        storage_mod.init_db()
        snap = Snapshot(
            source="fangraphs",
            snapshot_date="2025-08-15",
            interval_label="2025updated",
            player_key="jesus_made",
            player_name="Jesús Made",
            position="SS",
            org="MIL",
            rank=1,
            fv=62.0,
            status="active",
            tools={
                "hit": 60.0, "game_pwr": 60.0, "speed": 60.0,
                "pitch_sel": 55.0, "bat_ctrl": 60.0,
                "_extras": {
                    "height": "6' 0", "weight": 190, "bats": "R", "throws": "R",
                    "contact_style": "InsideOut", "hard_hit_pct": 0.5,
                    "frame": 3, "athl": 4, "perf": 4, "delivery": "Smooth",
                },
            },
        )
        storage_mod.insert_snapshots([snap])
        loaded = storage_mod.load_all_snapshots()
        assert len(loaded) == 1
        out = loaded[0]
        assert out.source == "fangraphs"
        assert out.tools["hit"] == 60.0
        assert out.tools["pitch_sel"] == 55.0
        assert out.tools["bat_ctrl"] == 60.0
        # _extras is the load-path's biggest historical victim — verify
        # it survives intact (this is the bug the integration fixes).
        ex = out.tools["_extras"]
        assert ex["height"] == "6' 0"
        assert ex["weight"] == 190
        assert ex["bats"] == "R"
        assert ex["throws"] == "R"
        assert ex["contact_style"] == "InsideOut"
        assert ex["hard_hit_pct"] == 0.5
        assert ex["frame"] == 3
        assert ex["athl"] == 4
        assert ex["perf"] == 4
        assert ex["delivery"] == "Smooth"

    def test_legacy_extras_pitch_sel_lifted_to_canonical(self, tmp_path, monkeypatch):
        """Backwards-compat: legacy DB rows that stored pitch_sel/
        bat_ctrl under _extras get lifted to canonical tools at load
        time, so existing rows don't need a re-ingest to participate
        in consensus aggregation."""
        from scrapers import Snapshot
        import storage as storage_mod

        db_path = tmp_path / "test_legacy.db"
        monkeypatch.setattr(storage_mod, "DB_PATH", db_path)
        storage_mod.init_db()
        snap = Snapshot(
            source="fangraphs",
            snapshot_date="2024-02-14",
            interval_label="2024report",
            player_key="legacy_guy",
            player_name="Legacy Guy",
            position="SS", org="PIT", rank=50, fv=50.0, status="active",
            tools={
                "hit": 50.0,
                "_extras": {"pitch_sel": 55, "bat_ctrl": 60, "height": "6' 2"},
            },
        )
        storage_mod.insert_snapshots([snap])
        loaded = storage_mod.load_all_snapshots()
        out = loaded[0]
        # Lifted to canonical hitter tools.
        assert out.tools["pitch_sel"] == 55.0
        assert out.tools["bat_ctrl"] == 60.0
        # _extras stays intact (we don't strip the source data — a
        # future re-ingest with new code will overwrite).
        assert out.tools["_extras"]["pitch_sel"] == 55


# ---------------------------------------------------------------------------
# Consensus aggregation must skip the _extras sibling key (Step 2)
# ---------------------------------------------------------------------------

class TestConsensusSkipsExtras:
    def test_extras_key_not_in_tools_by_key(self):
        """compute_consensus_point must treat `_extras` as metadata —
        never aggregate it as a numeric tool grade (float({...}) would
        raise; missing skip = pollution of tools_by_key)."""
        from scrapers import Snapshot
        from consensus import compute_consensus_point

        a = Snapshot(source="fangraphs", snapshot_date="2025-08-15",
                     interval_label="2025updated", player_key="x",
                     player_name="X", position="SS", org="MIL",
                     rank=1, fv=60.0, status="active",
                     tools={"hit": 60.0, "_extras": {"height": "6' 0"}})
        b = Snapshot(source="mlb_pipeline", snapshot_date="2025-08-15",
                     interval_label="pipe", player_key="x",
                     player_name="X", position="SS", org="MIL",
                     rank=2, fv=55.0, status="active",
                     tools={"hit": 55.0})
        pt = compute_consensus_point([a, b])
        assert pt is not None
        assert "_extras" not in pt.tools_consensus
        assert pt.tools_consensus["hit"] == 57.5
        # _extras must still ride per_source so the UI sees it.
        assert pt.per_source["fangraphs"]["tools"]["_extras"] == {"height": "6' 0"}


# ---------------------------------------------------------------------------
# Two-way player tool composites (Step 9)
# ---------------------------------------------------------------------------

class TestTwoWayPlayerComposites:
    def test_both_payloads_emit_when_both_keys_present(self):
        """A consensus-grades dict with both hitter and pitcher canonical
        keys produces a usable hitter composite AND pitcher composite
        when _compute_tool_composites is called for each side."""
        from storage import _compute_tool_composites

        grades = {
            "hit": 55.0, "game_pwr": 60.0, "raw_pwr": 60.0,
            "speed": 50.0, "field": 50.0,
            "fb": 65.0, "sl": 55.0, "cb": 50.0, "ch": 55.0, "cmd": 50.0,
        }
        hitter = _compute_tool_composites(grades, is_pitcher=False)
        pitcher = _compute_tool_composites(grades, is_pitcher=True)
        assert hitter is not None and hitter["composite_off"] is not None
        assert pitcher is not None and pitcher["composite_stuff"] is not None
        # Hitter payload should not over-claim stuff; pitcher payload
        # should not over-claim offense.
        assert hitter["composite_stuff"] is None
        assert pitcher["composite_off"] is None


# ---------------------------------------------------------------------------
# v18 — FG board year coverage audit
# ---------------------------------------------------------------------------

class TestFanGraphsYearCoverage:
    """Audit that the timeseries.json carries FG snapshots across the
    full 2021-2026 window. Catches regressions where a year's CSV drop
    silently disappears between rebuilds (the parser silently ignores
    missing files; without this assertion, a gap year goes unnoticed).
    """

    @classmethod
    def setup_class(cls):
        import json
        ts_path = Path(__file__).parent / "data" / "timeseries.json"
        with open(ts_path, "r", encoding="utf-8") as fh:
            cls.payload = json.load(fh)

    def _fg_labels(self):
        labels = set()
        for p in self.payload.get("players", []):
            for pt in p.get("points", []):
                fg = (pt.get("per_source") or {}).get("fangraphs")
                if fg and fg.get("interval_label"):
                    labels.add(fg["interval_label"])
        return labels

    def test_report_cycle_every_year_2021_2026(self):
        labels = self._fg_labels()
        missing = []
        for y in range(2021, 2027):
            if f"{y}report" not in labels:
                missing.append(f"{y}report")
        assert not missing, (
            f"FG report cycle missing for years: {missing}. "
            f"Re-drop the corresponding CSV set into data/fangraphs_imports/."
        )

    def test_updated_cycle_every_year_2021_2025(self):
        # 2026 updated drops in late July (post-deadline) — exclude until
        # the current calendar year is past the drop window.
        labels = self._fg_labels()
        missing = [f"{y}updated" for y in range(2021, 2026)
                    if f"{y}updated" not in labels]
        assert not missing, (
            f"FG updated cycle missing for years: {missing}. "
            f"Re-drop the corresponding CSV set into data/fangraphs_imports/."
        )

    def test_draft_cycle_present_for_recent_years(self):
        labels = self._fg_labels()
        # Draft cycle is a separate FG product (the draft-prospect
        # boards). Coverage exists for 2021-2025; 2026 lands closer to
        # the actual draft date.
        missing = [f"{y}draft" for y in range(2021, 2026)
                    if f"{y}draft" not in labels]
        assert not missing, (
            f"FG draft board missing for years: {missing}."
        )
