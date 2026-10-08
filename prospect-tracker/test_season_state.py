# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One season state for the whole site (site pass SP-D5, task PROSPX_4_SEASON_STATE).

WHY THIS EXISTS (2026-10-08). Each module decided "is the season over" alone, so in
October the PROSPX card printed "Hot · L15 OPS .990" for a season whose last MiLB
game was 2026-09-20, the Leaderboards window chips read "Last 7d" for September 14
to 20, and /projections/ and /franchise/ printed "As of the end of the regular
season (2026-10-02)", the BUILD date, for a season that ended 2026-09-27.

Contract pinned here:
  * season_state.build_state gives the phase for 2026-07-15 (regular), 2026-10-02
    (postseason), 2026-12-01 (offseason) and 2027-03-01 (spring) from a fixture
    calendar, with every date field derived from it;
  * the boot block in assets/eephus-config.js is rewritten in place (idempotent,
    the file's own line endings and every other byte kept), and every page that
    loads eephus-ui.js loads the boot file before it;
  * the futures and division stamps print mlb_regular_end, never the build date;
  * EephusSeason (assets/eephus-ui.js) and the PROSPX consumers give the labels and
    defaults the spec names per phase, and the pre-state defaults without a state.
"""
from __future__ import annotations

import inspect
import json
import re
import warnings
from datetime import date
from pathlib import Path

import pytest

import season_state as ss

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
UI = ROOT / "assets" / "eephus-ui.js"

# The StatsAPI /seasons rows as served for 2026 and 2027 (fields this module reads).
MLB = {
    2026: {"seasonId": "2026", "springStartDate": "2026-02-20", "regularSeasonStartDate": "2026-03-25",
           "allStarDate": "2026-07-14", "regularSeasonEndDate": "2026-09-27",
           "postSeasonStartDate": "2026-09-28", "postSeasonEndDate": "2026-10-31"},
    2027: {"seasonId": "2027", "springStartDate": "2027-02-19", "regularSeasonStartDate": "2027-03-25",
           "allStarDate": "2027-07-13", "regularSeasonEndDate": "2027-09-26",
           "postSeasonStartDate": "2027-09-27", "postSeasonEndDate": "2027-10-31"},
}
MILB = {2026: [{"seasonId": "2026", "regularSeasonEndDate": d}
               for d in ("2026-09-20", "2026-09-13", "2026-09-06", "2026-09-06")]}

DATES = {"2026-07-15": "regular", "2026-10-02": "postseason",
         "2026-12-01": "offseason", "2027-03-01": "spring"}


def _state(iso: str) -> dict:
    return ss.build_state(date.fromisoformat(iso), MLB, MILB)


# --------------------------------------------------------------------------
# the writer
# --------------------------------------------------------------------------

@pytest.mark.parametrize("iso,phase", sorted(DATES.items()))
def test_the_phase_for_the_four_registered_dates(iso, phase):
    assert _state(iso)["phase"] == phase


def test_the_fields_come_from_the_calendar():
    s = _state("2026-10-02")
    assert set(s) == set(ss.FIELDS)
    assert s == {
        "phase": "postseason", "season": 2026,
        "mlb_regular_end": "2026-09-27", "mlb_postseason_end": "2026-10-31",
        "milb_last_game": "2026-09-20", "next_opening_day": "2027-03-25",
        "draft_date": "2026-07-12", "j2_open": "2027-01-15",
        "posting_window": ["2026-11-01", "2026-12-15"],
    }
    # spring belongs to the season just played until the next opening day
    sp = _state("2027-03-01")
    assert sp["season"] == 2026 and sp["next_opening_day"] == "2027-03-25"
    # in season the next opening day is next year's
    assert _state("2026-07-15")["next_opening_day"] == "2027-03-25"


def test_a_decided_world_series_ends_the_postseason_early():
    end = ss.build_state(date(2026, 10, 29), MLB, MILB, ws_end="2026-10-28")
    assert end["mlb_postseason_end"] == "2026-10-28" and end["phase"] == "offseason"
    assert ss.build_state(date(2026, 10, 28), MLB, MILB, ws_end="2026-10-28")["phase"] == "postseason"


def test_an_empty_calendar_degrades_to_offseason_without_dates():
    s = ss.build_state(date(2026, 10, 2), {}, {})
    assert s["phase"] == "offseason" and s["mlb_regular_end"] is None and s["milb_last_game"] is None


def test_write_boot_replaces_only_its_block(tmp_path):
    p = tmp_path / "cfg.js"
    head = 'window.EEPHUS_SUPABASE = {\r\n  url: "x"\r\n};\r\n'
    p.write_bytes(head.encode("utf-8"))
    assert ss.write_boot(_state("2026-10-02"), p) is True
    raw = p.read_bytes().decode("utf-8")
    assert raw.startswith(head) and "\n" not in raw.replace("\r\n", "")
    assert ss.read_boot(p)["phase"] == "postseason"
    assert ss.write_boot(_state("2026-10-03"), p) is False, "same dates, same bytes"
    assert ss.write_boot(_state("2026-12-01"), p) is True
    raw2 = p.read_bytes().decode("utf-8")
    assert raw2.startswith(head) and raw2.count(ss.BLOCK_BEGIN) == 1
    assert ss.read_boot(p)["phase"] == "offseason"


def test_the_served_boot_block_parses_and_every_page_loads_it_before_the_reader():
    s = ss.read_boot()
    assert s is not None, "assets/eephus-config.js carries no season block; run python season_state.py"
    assert set(s) == set(ss.FIELDS) and s["phase"] in ss.PHASES
    pages = [p for p in ROOT.rglob("*.html")
             if not any(x in p.parts for x in ("docs", "data", "test_fixtures", "node_modules"))]
    n = 0
    for p in pages:
        html = p.read_text(encoding="utf-8", errors="replace")
        if "/assets/eephus-ui.js" not in html:
            continue
        n += 1
        assert "/assets/eephus-config.js" in html, f"{p}: loads the reader without the boot file"
        assert html.index("/assets/eephus-config.js") < html.index("/assets/eephus-ui.js"), p
    assert n >= 25


def test_the_nightly_writes_the_state_and_never_ends_the_night_on_it():
    import run_monthly
    src = inspect.getsource(run_monthly.run_daily)
    i = src.index("d00b. Site season state")
    block = src[i:src.index("d0. TJStats Live capture")]
    assert "season_state as _sst" in block and "_sst.write_boot(" in block
    assert "except Exception" in block
    assert i < src.rindex("rebuild_only(")


# --------------------------------------------------------------------------
# the two build-date stamps
# --------------------------------------------------------------------------

def test_the_futures_stamp_prints_mlb_regular_end():
    import proj_export as pe
    assert "{mlb_regular_end}" in pe.FUTURES_AS_OF_TEMPLATE and "{build}" not in pe.FUTURES_AS_OF_TEMPLATE
    line = pe.futures_as_of_note("2026-10-02T16:25:25+00:00", "2026-09-27")
    assert line.startswith("As of the end of the regular season (2026-09-27): ")
    assert "2026-10-02" not in line


def test_the_division_stamp_prints_mlb_regular_end():
    import bracket_sim as bs
    assert "{mlb_regular_end}" in bs.DIVISION_COLUMNS_TEMPLATE and "{build}" not in bs.DIVISION_COLUMNS_TEMPLATE
    fu = {"generated_at": "2026-10-02T16:25:25+00:00", "regular_season_end": "2026-09-27",
          "as_of_note": "As of the end of the regular season (2026-09-27): x"}
    note = bs._division_columns_note(fu)
    assert note.startswith("As of the end of the regular season (2026-09-27): ")
    assert "2026-10-02" not in note
    assert bs._division_columns_note({**fu, "regular_season_end": None}) is None
    assert bs._division_columns_note({**fu, "as_of_note": None}) is None


# --------------------------------------------------------------------------
# the reader and the PROSPX consumers
# --------------------------------------------------------------------------

def _fn(src: str, name: str) -> str:
    m = re.search(r"^(?:async )?function %s\([^)]*\)\s*\{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found"
    return m.group(0)


def _reader_src() -> str:
    ui = UI.read_text(encoding="utf-8")
    return ui[ui.index("// ---- EephusSeason"):]


PX_FNS = ("_pxSeason", "_pxSeasonToday", "_pxSeasonLabel", "_pxDraftDefaultYear",
          "_pxIfaDefaultYear", "_pxOverseasDefaultView", "_formBadgeHTML", "_lbWindowDates")


@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    ctx = mr.MiniRacer()
    ctx.eval("""var window = {}; var state = {lbWindow: '7'};
      var DATA = {leaderboard_gamelogs: {as_of: '2026-09-20'}};
      function escapeHtml(s){ return String(s); }
      function _lbFmtDate(s){ return s; }
      var _FORM = {metric:'OPS', val:0.990, season:0.850, delta:0.140, hot:true, cold:false, n:15, isP:false};
      function _recentForm(p){ return _FORM; }""")
    ctx.eval(_reader_src())
    src = PROSPX.read_text(encoding="utf-8")
    for name in PX_FNS:
        ctx.eval(_fn(src, name))
    return ctx


def _set(js, state):
    js.eval("window.EEPHUS_SEASON = %s;" % json.dumps(state))


CLASSES = json.dumps([{"year": y} for y in (2028, 2027, 2026, 2025)])


@pytest.mark.parametrize("iso", sorted(DATES))
def test_prospx_defaults_and_labels_per_phase(js, iso):
    s = _state(iso)
    _set(js, s)
    phase = DATES[iso]
    assert js.eval("window.EephusSeason.phase()") == phase
    # Draft: the next class after the draft date (2026-07-12 in every fixture date)
    assert js.eval(f"_pxDraftDefaultYear({CLASSES}, '{iso}')") == 2027
    # IFA: the class whose signing period is open (j2_open 2027-01-15)
    assert js.eval(f"_pxIfaDefaultYear({CLASSES}, '{iso}')") == (2027 if iso >= "2027-01-15" else 2026)
    # Overseas: Posting Tracker inside 2026-11-01 to 2026-12-15 only
    view = js.eval(f"_pxOverseasDefaultView('{iso}') || 'rankings'")
    assert view == ("posting" if iso == "2026-12-01" else "rankings")
    chip = js.eval("_formBadgeHTML({})")
    std = js.eval("_pxSeasonLabel('standout', 2026)")
    if phase == "regular":
        assert "Hot · L15 OPS .990" in chip and "Final" not in chip
        assert std == ""
    else:
        assert ">Final 15 G OPS .990<" in chip
        assert not re.search(r"Hot|Cold|Steady|▲|▼", chip)
        assert std == "Final two weeks of the 2026 MiLB season"
    # window chips: "Final" once the slice as_of reaches the last MiLB game
    assert js.eval("_pxSeasonLabel('window', '2026-09-20')") == "Final"
    assert js.eval("_pxSeasonLabel('window', '2026-09-19')") == "Last"
    assert js.eval("_lbWindowDates().label") == "Final 7 days"


def test_without_a_state_every_consumer_keeps_its_old_default(js):
    js.eval("window.EEPHUS_SEASON = undefined;")
    assert js.eval("window.EephusSeason.phase()") is None
    assert js.eval(f"_pxDraftDefaultYear({CLASSES}, '2026-10-02') === undefined")
    assert js.eval(f"_pxIfaDefaultYear({CLASSES}, '2026-10-02') === undefined")
    assert js.eval("_pxOverseasDefaultView('2026-12-01') === undefined")
    assert "Hot · L15 OPS .990" in js.eval("_formBadgeHTML({})")
    assert js.eval("_pxSeasonLabel('window', '2026-09-20')") == "Last"
    assert js.eval("_lbWindowDates().label") == "Last 7 days"
    assert js.eval("_pxSeasonLabel('standout', 2026)") == ""


def test_a_class_missing_from_the_export_falls_back(js):
    _set(js, _state("2026-10-02"))
    only_old = json.dumps([{"year": 2026}, {"year": 2025}])
    assert js.eval(f"_pxDraftDefaultYear({only_old}, '2026-10-02') === undefined")


def test_the_prospx_call_sites_read_the_state():
    src = PROSPX.read_text(encoding="utf-8")
    assert "_pxDraftDefaultYear(classes) ?? _draftNewestCompletedYear(classes)" in src
    assert "_pxIfaDefaultYear(classes) ?? classes[0].year" in src
    assert 'state.overseasView = _pxOverseasDefaultView() || "rankings"' in src
    assert "overseasView: null," in src
    assert '_pxSeasonLabel("window", (DATA.leaderboard_gamelogs || {}).as_of)' in src
    ribbon = _fn(src, "renderStandoutPerformances")
    assert '_pxSeasonLabel("standout"' in ribbon
    chip = _fn(src, "_l15OpsChip")
    assert '"Final 15 G"' in chip
    boot = _fn(src, "_bootProspx")
    assert boot.index("DOMContentLoaded") < boot.index("render();")


def test_the_reader_is_small_and_fetches_nothing():
    r = _reader_src()
    assert "fetch(" not in r and "XMLHttpRequest" not in r
    assert len(r.strip().splitlines()) <= 25
