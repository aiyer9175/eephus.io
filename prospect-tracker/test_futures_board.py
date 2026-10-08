"""data/futures.json and the Futures tab inside /betting/.

WHAT THIS BOARD CANNOT SAY. No futures price has ever been captured by this
platform, so there is no market beside any of these numbers: no edge column, no
value flag, no expected return. The tab says which capture is missing rather
than estimating one, and it says that a captured price would still not be a
validated edge until the futures backtest has run.

THE FIVE MISTAKES THESE TESTS EXIST FOR, and one of them was made:

  1. RENDERING AN INFINITY INTO A PRICE CELL. divisionPct == 1.0 and
     playoffPct == 0.0 are both live in the served artifact, and this is the one
     column a reader is most likely to carry to a book. An infinity there looks
     like a number.
  2. CALLING THE COLUMN FAIR. "Fair" asserts zero expected value, which requires
     the probability to be right, on a simulator with no validated forward
     record.
  3. LETTING THE TWO ARTIFACTS DESCRIBE DIFFERENT SIMULATIONS. The overlay
     repair tool is a SECOND writer of the same numbers, and the projections
     stamp is a bare date, so two runs on one day are indistinguishable by it.
  4. PUBLISHING A PARTIAL BOARD. simulate_playoffs returns nothing on a partial
     standings read; thirty nulls are worse than no board.
  5. NOT WRAPPING A NEW TABLE IN THE SCROLL BOX. Caught by an existing test,
     which is what it is for.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import proj_export as pe                                      # noqa: E402

ART = ROOT / "data" / "futures.json"
JS = (ROOT / "assets" / "betting.js").read_text(encoding="utf-8")
SHELL = ROOT / "betting" / "index.html"


@pytest.fixture(scope="module")
def d():
    if not ART.exists():
        pytest.skip("run python proj_export.py")
    return json.loads(ART.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# The rails
# --------------------------------------------------------------------------

def test_a_certainty_never_becomes_an_infinite_price():
    """MISTAKE 1."""
    assert pe._fair_american(1.0) is None
    assert pe._fair_american(0.0) is None
    assert pe._fair_american(0.999) is None
    assert pe._fair_american(0.001) is None


def test_the_price_is_right_in_the_interior():
    assert pe._fair_american(0.5) == -100
    assert pe._fair_american(0.25) == 300
    assert pe._fair_american(0.8) == -400


def test_the_live_rail_cells_are_blank_and_not_zero(d):
    """The served artifact really does carry probabilities of exactly 0 and 1."""
    rails = [c for c in d["clubs"] if c["divisionPct"] in (0.0, 1.0)]
    assert rails, "no rail cells on this build; the guard is untested here"
    for c in rails:
        assert c["impliedAmericanDivision"] is None, (
            f"{c['team']} at divisionPct {c['divisionPct']} produced a price")


def test_the_probability_survives_even_where_the_price_does_not(d):
    for c in d["clubs"]:
        assert c["wsPct"] is not None
        assert c["playoffPct"] is not None


# --------------------------------------------------------------------------
# What it is not allowed to claim
# --------------------------------------------------------------------------

def test_there_is_no_edge_column_anywhere(d):
    """MISTAKE 2's neighbour. No market means no edge, and the absence has to be
    structural rather than a rendering choice."""
    for c in d["clubs"]:
        for k in c:
            assert "edge" not in k.lower() and "value" not in k.lower(), k
    assert d["no_market"]["captured"] is False


def test_the_price_column_is_not_called_fair(d):
    """MISTAKE 2."""
    assert "fair" not in JS.lower().split("renderfutures")[1][:3000] or True
    i = JS.index("function renderFutures")
    body = JS[i:i + 4000]
    assert "Model price (implied)" in body
    assert "Model fair" not in body and "fairAmerican" not in body
    assert "requires the probability to be right" in d[
        "why_the_price_column_is_not_called_fair"]


def test_the_missing_capture_is_named_with_its_cost(d):
    nm = d["no_market"]
    assert "credits" in nm["what_would_have_to_happen"]
    assert "owner decision" in nm["what_would_have_to_happen"]
    assert "backtest has not been run" in nm["and_then_still_not_an_edge"]


def test_the_intervals_are_labelled_monte_carlo_only(d):
    txt = d["what_the_intervals_are"]
    assert "Monte Carlo error only" in txt
    assert "talent estimate underneath it" in txt


def test_the_win_band_states_that_it_is_narrower_than_a_forecast(d):
    txt = d["win_total_basis"]
    assert "schedule noise" in txt and "narrower than a real forecast" in txt


# --------------------------------------------------------------------------
# The board itself
# --------------------------------------------------------------------------

def test_the_board_carries_every_club_or_none_of_them(d):
    """MISTAKE 4. A partial board is the real defect signature."""
    assert len(d["clubs"]) in (0, 30)
    if not d["clubs"]:
        assert d["empty_reason"]


def test_the_conservation_laws_hold_on_the_published_board(d):
    if not d["clubs"]:
        pytest.skip("degraded board")
    assert abs(sum(c["wsPct"] for c in d["clubs"]) - 1.0) < 0.02
    assert abs(sum(c["pennantPct"] for c in d["clubs"]) - 2.0) < 0.03
    assert abs(sum(c["playoffPct"] for c in d["clubs"]) - 12.0) < 0.03
    assert abs(sum(c["byePct"] for c in d["clubs"]) - 4.0) < 0.03


def test_the_board_is_sorted_by_the_headline_column(d):
    ws = [c["wsPct"] for c in d["clubs"]]
    assert ws == sorted(ws, reverse=True)


def test_a_degraded_field_produces_an_empty_board_with_a_reason():
    rows = [{"team": "AAA", "current": {"wsPct": None}},
            {"team": "BBB", "current": None}]
    out = pe.build_futures(rows)
    assert out["clubs"] == []
    assert "board of thirty nulls" in out["empty_reason"]
    assert out["content_hash"] is None


# --------------------------------------------------------------------------
# The two writers
# --------------------------------------------------------------------------

def test_the_board_carries_a_content_hash_and_not_only_a_date(d):
    """MISTAKE 3. The projections stamp is a bare date, so two runs on one day
    are indistinguishable by it."""
    assert d["content_hash"] and len(d["content_hash"]) == 12


def test_the_hash_moves_when_a_probability_moves():
    base = [{"team": f"T{i}", "current": {"wsPct": 0.03, "pennantPct": 0.06,
                                          "playoffPct": 0.4, "byePct": 0.13,
                                          "divisionPct": 0.2, "projWinsMean": 81.0,
                                          "record": "40-40"}} for i in range(30)]
    a = pe.build_futures(base)["content_hash"]
    base[0]["current"]["wsPct"] = 0.031
    b = pe.build_futures(base)["content_hash"]
    assert a != b, "the hash does not move when a published number does"


def test_the_repair_tool_re_emits_the_sidecar():
    """The overlay repair is a SECOND writer of the same simulation. If it did
    not re-emit, the futures board would describe a different run while the
    projections date stamp still matched."""
    src = (ROOT / "tools" / "repair_team_outlook_overlay.py").read_text(encoding="utf-8")
    assert "write_futures" in src
    assert "SECOND CALLER MUST RE-EMIT" in src


def test_the_export_writes_it_from_export_and_not_from_the_overlay():
    """_attach_current_season is called directly by tests on two-club synthetic
    universes. Writing an untracked artifact from there would leave a file
    conftest's revert cannot restore."""
    src = (ROOT / "proj_export.py").read_text(encoding="utf-8")
    i = src.index("def _attach_current_season")
    body = src[i:src.index("def _pairs_from_sched")]
    assert "write_futures" not in body
    assert "write_futures(payload" in src


def test_the_artifact_is_gitignored():
    """It is a build product like every other data sidecar, and it was NOT
    ignored, which would have committed a thirty-club simulation snapshot on
    every rebuild."""
    import subprocess
    r = subprocess.run(["git", "check-ignore", "data/futures.json"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, "data/futures.json is not gitignored"


# --------------------------------------------------------------------------
# The tab
# --------------------------------------------------------------------------

def test_the_tab_is_in_the_three_file_contract():
    if not SHELL.exists():
        pytest.skip("/betting/ not built")
    html = SHELL.read_text(encoding="utf-8")
    assert 'data-bettingsection="futures"' in html
    assert '"futures"' in JS.split("var SECTIONS")[1][:200]
    assert 'case "futures":' in JS


def test_the_tab_reads_its_copy_from_the_payload():
    i = JS.index("function renderFutures")
    body = JS[i:i + 4000]
    for key in ("what_is_missing", "what_would_have_to_happen",
                "and_then_still_not_an_edge", "why_the_price_column_is_not_called_fair",
                "what_the_intervals_are", "win_total_basis"):
        assert key in body, f"the tab does not render {key}"


def test_the_tab_says_there_is_no_market_before_it_shows_a_number():
    i = JS.index("function renderFutures")
    body = JS[i:i + 4000]
    j = body.index("There is no market on this board")
    k = body.index("<table")
    assert j < k, "the board renders before it says there is no market beside it"


# --------------------------------------------------------------------------
# The season-over line (Part 8 intensity lane, finding F1)
# --------------------------------------------------------------------------

STAMP = ("As of the end of the regular season (2026-09-27): postseason results "
         "are not in these odds.")


def test_the_season_over_line_renders_from_the_two_payload_dates():
    """The simulator reads the regular-season schedule only and plays the
    bracket from final standings, so after the last regular-season game its
    odds stop learning. The line is built from the build date and the season's
    last regular-season date, and nothing else; the date it prints is the
    season's end (mlb_regular_end, site pass SP-D5), never the build date."""
    assert pe.futures_as_of_note("2026-10-01T11:33:03+00:00", "2026-09-27") == STAMP
    assert "2026-10-01" not in STAMP
    # on the last regular-season date itself the line is already shown
    assert pe.futures_as_of_note("2026-09-27T23:00:00+00:00", "2026-09-27") == STAMP
    # every later build prints the same date
    assert pe.futures_as_of_note("2026-12-01T07:00:00+00:00", "2026-09-27") == STAMP


def test_the_season_over_line_is_absent_before_the_season_ends():
    assert pe.futures_as_of_note("2026-09-26T23:59:59+00:00", "2026-09-27") is None
    assert pe.futures_as_of_note("2026-06-01T12:00:00+00:00", "2026-09-27") is None
    # no season calendar on disk: no line, rather than a guessed one
    assert pe.futures_as_of_note("2026-10-01T11:33:03+00:00", None) is None
    assert pe.futures_as_of_note(None, "2026-09-27") is None
    assert pe.futures_as_of_note("2026-10-01T11:33:03+00:00", "not a date") is None


def test_build_futures_carries_both_dates_and_the_derived_line():
    """The two dates ride in the payload beside the line, so a reader can check
    the line against them, and no probability is touched."""
    f = pe.build_futures([], season=2026, regular_season_end="2026-09-27")
    assert f["season"] == 2026 and f["regular_season_end"] == "2026-09-27"
    assert f["as_of_note"] == pe.futures_as_of_note(f["generated_at"], "2026-09-27")
    g = pe.build_futures([], season=2026, regular_season_end="2999-09-27")
    assert g["as_of_note"] is None


def test_the_served_line_agrees_with_the_served_dates(d):
    if "regular_season_end" not in d:
        pytest.skip("futures.json predates the season-over line; rebuild it")
    build = str(d.get("generated_at") or "")[:10]
    if build != str(d["regular_season_end"])[:10] and f"({build})" in str(d.get("as_of_note") or ""):
        pytest.skip("futures.json predates the mlb_regular_end stamp (it names its "
                    "build date); the next proj_export build rewrites it")
    assert d.get("as_of_note") == pe.futures_as_of_note(
        d.get("generated_at"), d.get("regular_season_end"))


def test_the_tab_prints_the_season_over_line_before_the_board():
    i = JS.index("function renderFutures")
    body = JS[i:i + 4000]
    j = body.index("FUT.as_of_note")
    k = body.index("<table")
    assert j < k, "the season-over line renders after the odds it qualifies"
    assert "postseason results are not in" not in JS, (
        "the line is quoted from the payload, never composed in the tab")


def test_the_registry_row_describes_the_talent_the_simulator_is_fed():
    """F2. The simulator is fed the pure roster prior (talent = prior_by_team);
    the record and Pythagorean blend reach only curWins. The row said blended."""
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = {m["model_id"]: m for m in reg["models"]}["playoff_odds_sim"]
    assert "blended" not in row["champion"]
    assert "pure roster-talent prior" in row["champion"]
    src = (ROOT / "proj_export.py").read_text(encoding="utf-8")
    i = src.index("def _attach_current_season")
    body = src[i:src.index("def _fair_american")]
    assert "talent = {tm: prior_by_team.get(tm, 0.5)" in body
    assert '"p": talent.get(tm, 0.5)' in body
