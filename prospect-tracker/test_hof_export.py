"""The /hof/ payload and the page that renders it.

WHAT THE PAGE IS ALLOWED TO SAY, pinned. Five sections live, three dark, and the dark ones
are dark for DATA reasons rather than modelling ones. The tests below exist because every
one of those three is easy to ship anyway by quietly substituting a number that looks close
enough.

THE BAKE-OFF IS LIVE AND IT REPORTS A LOSS, which is its own kind of discipline: a
benchmark panel that only ships on a win is not a benchmark. Tests pin that every in-house
arm loses to the best public rule, that the loss is attributed to missing awards data
rather than to modelling, and that only the primary label reaches the page.

THE FIVE MISTAKES THESE TESTS EXIST FOR:

  1. PUBLISHING A HALL-SIZED LINE. It needs the count of players inducted AS PLAYERS and no
     field in this data says what a plaque says. Excluding contributors does not fix it:
     dropping a contributor from the ledger does not unlabel him, it makes him a resolved
     zero, and the page would then publish that Joe Torre is above the line and not in the
     Hall of Fame.
  2. LOSING THE NEAR-TERM BALLOT COHORT. Eligible plus Watch leaves out everybody who last
     played in 2022 through 2024, which is Albert Pujols, Zack Greinke, Robinson Cano,
     Miguel Cabrera and Joey Votto. The three bands must PARTITION the ten-plus-season
     population, and the exporter refuses to write a payload where they do not.
  3. RENDERING A BLANK PUBLIC COLUMN AS ZERO. HoF Monitor exists only for players who
     reached an election page. A zero there is an invented number for two thirds of the
     board.
  4. TYPING A FIGURE INTO THE HTML OR THE JS. Every count and every sentence of disclosure
     copy is read from the payload, because a hand-typed number on a page about what we can
     and cannot verify is the exact failure the page exists to avoid.
  5. TWO INDUCTION STATES INSTEAD OF THREE. "In" and "out" would report a player still on
     the ballot as rejected, and would report a manager's plaque as a player induction.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "hof_board.json"
PAGE = ROOT / "hof" / "index.html"
JS = ROOT / "assets" / "hof.js"


@pytest.fixture(scope="module")
def d():
    if not ART.exists():
        pytest.skip("run python hof_export.py")
    return json.loads(ART.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# The bands
# --------------------------------------------------------------------------

def test_the_three_bands_partition_the_ten_plus_season_population(d):
    c = d["counts"]
    assert c["n_eligible"] + c["n_watch"] + c["n_not_yet_eligible"] == c["n_ten_plus_seasons"]
    assert c["bands_partition_the_ten_plus_population"] is True


def test_no_player_appears_in_two_bands(d):
    ids = {}
    for band in ("leaderboard", "watch", "not_yet_eligible"):
        for r in d[band]:
            assert r["id"] not in ids, (
                f"{r['name']} is on both {ids.get(r['id'])} and {band}")
            ids[r["id"]] = band


def test_the_near_term_ballot_cohort_is_on_the_board(d):
    """MISTAKE 2. Without the third band these five are on no board at all, and
    they are the most likely thing a reader opens this page in 2026 to find."""
    names = {r["name"] for r in d["not_yet_eligible"]}
    for who in ("Albert Pujols", "Zack Greinke", "Miguel Cabrera", "Joey Votto"):
        assert who in names, f"{who} is not in the not-yet-eligible band"


def test_the_exporter_refuses_a_payload_whose_bands_do_not_partition():
    src = (ROOT / "hof_export.py").read_text(encoding="utf-8")
    assert "REFUSING" in src and "bands_partition_the_ten_plus_population" in src


# --------------------------------------------------------------------------
# What must stay dark
# --------------------------------------------------------------------------

def test_no_hall_sized_line_is_published(d):
    """MISTAKE 1."""
    assert d["line"]["pooled"] is None
    assert d["line"]["by_class"] is None
    assert d["deserved"] is None
    assert d["sections"]["deserved"]["live"] is False


def test_the_line_says_why_it_is_blocked_and_names_the_lane(d):
    why = d["line"]["blocked_because"]
    assert "inducted AS PLAYERS" in why
    assert "Joe Torre" in why, (
        "the reason must carry the concrete consequence: excluding contributors "
        "turns them into resolved zeros and the page would publish that a "
        "manager is above the line and not in the Hall")
    assert d["sections"]["deserved"]["blocked_on"] == "H-DATA-PLAQUE"


def test_the_by_class_line_names_the_catcher_defect(d):
    why = d["line"]["by_class_blocked_because"]
    assert "catcher" in why.lower() and "1930" in why


def test_the_quantile_ladder_ships_in_its_place(d):
    q = d["line"]["quantiles"]
    assert d["sections"]["quantile_ladder"]["live"] is True
    assert set(q) == {"0.50", "0.75", "0.90", "0.95", "0.99"}
    vals = [q[k] for k in sorted(q)]
    assert all(a <= b for a, b in zip(vals, vals[1:])), "the ladder is not monotone"


def test_every_dark_section_names_a_blocker_and_a_reason(d):
    for k, s in d["sections"].items():
        if s["live"]:
            continue
        assert s.get("blocked_on"), f"{k} is dark with no blocker named"
        assert len(s.get("why", "")) > 80, f"{k} is dark with no reason given"


def test_the_watch_board_carries_no_projection(d):
    w = d["sections"]["watch"]
    assert w["live"] is True and w["projection"] is False
    assert "does not guess" in w["why_no_projection"]
    for r in d["watch"]:
        assert "projection" not in r and "odds" not in r


def test_the_predictor_is_dark(d):
    assert d["sections"]["predictor"]["live"] is False
    assert d["sections"]["predictor"]["blocked_on"] == "H-PRED-3"


# --------------------------------------------------------------------------
# The induction column
# --------------------------------------------------------------------------

def test_induction_has_exactly_three_states(d):
    """MISTAKE 5."""
    seen = {r["induction"] for r in d["leaderboard"]}
    assert seen <= {"player_bbwaa", "route_unverified", "none"}
    assert {"player_bbwaa", "route_unverified", "none"} <= seen


def test_a_writers_election_is_the_only_verified_player_induction(d):
    for r in d["leaderboard"]:
        if r["induction"] == "player_bbwaa":
            assert r["induction_year"], "a verified induction with no year"


def test_the_managers_read_as_unverified_and_not_as_players(d):
    """Connie Mack and Casey Stengel played, so they are in the universe, and
    their plaques are managerial. The page may not call them player
    inductions."""
    by_name = {r["name"]: r for r in d["leaderboard"]}
    for who in ("Connie Mack", "Casey Stengel"):
        if who not in by_name:
            continue
        assert by_name[who]["induction"] == "route_unverified", (
            f"{who} is being published as a verified player induction")


def test_the_induction_disclosure_is_in_the_payload(d):
    txt = d["coverage"]["induction_column"]
    assert "route unverified" in txt and "no Hall line" in txt


# --------------------------------------------------------------------------
# The public columns
# --------------------------------------------------------------------------

def test_a_missing_public_column_is_null_and_not_zero(d):
    """MISTAKE 3."""
    nulls = sum(1 for r in d["leaderboard"] if r["monitor"] is None)
    assert nulls > 1000, (
        "almost every eligible player now carries a HoF Monitor, which means a "
        "blank was filled rather than left blank")
    assert d["coverage"]["n_eligible_with_no_ballot_page"] == nulls


def test_the_js_draws_a_blank_rather_than_a_zero():
    js = JS.read_text(encoding="utf-8")
    assert "function pub(" in js
    assert "hof-blank" in js
    assert "A BLANK PUBLIC CELL IS NOT A ZERO" in js


def test_a_missing_value_sorts_last_in_both_directions():
    js = JS.read_text(encoding="utf-8")
    i = js.index("function sorted(")
    body = js[i:i + 1400]
    assert "A MISSING VALUE SORTS LAST IN BOTH DIRECTIONS" in body
    assert "if (xm) return 1;" in body and "if (ym) return -1;" in body


def test_war_ink_is_disclosed_as_ours_and_not_black_ink(d):
    txt = d["coverage"]["war_ink_is_ours"]
    assert "NOT Bill James" in txt and "Black Ink" in txt


# --------------------------------------------------------------------------
# The reproduction claim
# --------------------------------------------------------------------------

def test_the_reproduction_is_measured_not_asserted(d):
    a = d["reproduction"]["against_the_public_shelf"]
    assert a["n_with_a_published_value"] > 1000
    assert a["n_exact_on_career_war"] > 0
    assert a["n_within_a_tenth"] >= a["n_exact_on_career_war"]
    assert a["mean_absolute_difference"] is not None
    assert d["reproduction"]["hand_checked"]["all_exact"] is True


def test_the_page_calls_it_a_reproduction_and_not_an_improvement(d):
    txt = d["reproduction"]["what_it_means"]
    assert "not an improvement" in txt


def test_the_largest_disagreements_are_named(d):
    w = d["reproduction"]["against_the_public_shelf"]["largest_disagreements"]
    assert w and all(x.get("name") and x.get("difference") is not None for x in w)


# --------------------------------------------------------------------------
# Nothing is typed
# --------------------------------------------------------------------------

def test_no_figure_is_typed_into_the_page_html():
    """MISTAKE 4. The shell may carry prose, but not a count that lives in the
    payload: those go stale silently the day the data moves."""
    h = PAGE.read_text(encoding="utf-8")
    d = json.loads(ART.read_text(encoding="utf-8"))
    for n in (d["counts"]["n_eligible"], d["counts"]["n_watch"],
              d["counts"]["n_not_yet_eligible"],
              d["ledger"]["n_resolved_to_bbref"]):
        assert str(n) not in h, (
            f"the count {n} is typed into hof/index.html and will go stale")


def test_the_js_reads_its_copy_from_the_payload():
    js = JS.read_text(encoding="utf-8")
    for key in ("why_no_projection", "blocked_on", "what_it_means",
                "induction_column", "war_ink_is_ours", "position_basis"):
        assert key in js, f"the page does not render the payload's {key} copy"
    assert "NOT ONE FIGURE IN THIS FILE IS TYPED" in js


def test_the_page_has_no_banned_dash():
    for f in (PAGE, JS, ROOT / "assets" / "hof.css", ROOT / "hof_export.py"):
        txt = f.read_text(encoding="utf-8")
        assert "—" not in txt and "–" not in txt, f"banned dash in {f.name}"


def test_the_payload_round_trips_a_non_ascii_name(d):
    """1,150 career-frame names carry a non-ASCII codepoint, so the payload is
    written ensure_ascii=False and read back as utf-8. A name that came back
    mangled would be a silent corruption on a page full of names."""
    hits = [r for r in d["leaderboard"] if any(ord(c) > 127 for c in r["name"])]
    assert len(hits) > 50, "no non-ASCII names survived the round trip"


# --------------------------------------------------------------------------
# The scaffolding that makes it actually reachable
# --------------------------------------------------------------------------

def test_hof_is_in_the_deploy_publish_list():
    """THE SILENT FAILURE. Omit this line and every test stays green while
    /hof/ 404s in production. That is the 2026-07-14 incident the file header
    records."""
    lines = (ROOT / "deploy" / "publish_paths.txt").read_text(
        encoding="utf-8").splitlines()
    assert "hof" in lines


def test_hof_is_in_the_sitemap():
    assert "/hof/" in (ROOT / "sitemap.xml").read_text(encoding="utf-8")


def test_hof_is_in_the_dash_stripper_targets():
    assert '"hof/index.html"' in (ROOT / "tools" / "strip_emdashes.py").read_text(
        encoding="utf-8")


def test_hof_is_excluded_from_pytest_collection():
    assert "\n    hof\n" in (ROOT / "pytest.ini").read_text(encoding="utf-8")


def test_hof_export_is_a_watched_scheduled_export():
    """hof_export is in the SCHEDULED_EXPORTS tuple, read as a tuple.

    This used to scan a fixed 3,000-character window after the opening line,
    which is a proxy for membership and not membership: adding
    war_leaderboards (2026-09-17) pushed hof_export to offset 3,341 and failed
    a test about the Hall of Fame board for a reason that had nothing to do
    with it. The tuple is parsed now, so it stays true however the list grows.
    """
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = src.index("SCHEDULED_EXPORTS = (")
    block = src[i:src.index(chr(10) + ")", i) + 2]
    watched = re.findall(r'"([a-z_0-9]+)"', block)
    assert "hof_export" in watched, (
        "a silent export failure would leave the page painting an empty state "
        "with nobody told; watched exports are %r" % (watched,))
    assert "6b7b. Hall of Fame board" in src


def test_the_board_is_in_the_data_catalog():
    src = (ROOT / "data_catalog.py").read_text(encoding="utf-8")
    assert '"hof_board.json"' in src


# --------------------------------------------------------------------------
# The bake-off panel, which is live and reports a loss
# --------------------------------------------------------------------------

def test_the_bakeoff_panel_is_live_and_says_it_lost(d):
    """A benchmark panel that only ships on a win is not a benchmark."""
    b = d["sections"]["bakeoff"]
    if not b.get("live"):
        pytest.skip("the bake-off has not been run")
    assert "better than our WAR shelf" in b["headline"]
    assert b["best_public"] == "hof_monitor"


def test_every_in_house_arm_loses_above_its_own_floor(d):
    b = d["sections"]["bakeoff"]
    if not b.get("live"):
        pytest.skip("the bake-off has not been run")
    inhouse = [r for r in b["rows"] if not r["is_public"]]
    assert len(inhouse) >= 5
    for r in inhouse:
        assert r["delta_vs_best_public"] is not None
        assert r["delta_vs_best_public"] < 0, (
            f"{r['arm']} now beats the best public rule, which contradicts the "
            "gate's first prediction and must be confirmed before it is shown")


def test_the_loss_is_attributed_to_missing_data_not_to_modelling(d):
    b = d["sections"]["bakeoff"]
    if not b.get("live"):
        pytest.skip("the bake-off has not been run")
    assert "batting titles" in b["why_it_loses"]
    assert "is in our feature set" in b["why_it_loses"]
    assert "orders Hall of Fame outcomes less well" in b["what_it_does_not_show"], (
        "the panel must separate 'our shelf is wrong' from 'WAR alone orders "
        "these outcomes less well than a rule that also counts awards'")


def test_only_the_primary_label_reaches_the_page(d):
    """label_any's shelf hole is seventeen positives and zero negatives, so its
    pooled comparison is refused upstream. A refused comparison has no business
    on a page."""
    b = d["sections"]["bakeoff"]
    if not b.get("live"):
        pytest.skip("the bake-off has not been run")
    assert b["label"] == "bbwaa"


def test_the_panel_carries_the_population_caveat(d):
    b = d["sections"]["bakeoff"]
    if not b.get("live"):
        pytest.skip("the bake-off has not been run")
    assert "screening committee" in b["population_note"]


def test_the_panel_names_its_frozen_gate(d):
    b = d["sections"]["bakeoff"]
    if not b.get("live"):
        pytest.skip("the bake-off has not been run")
    assert b["gate_doc"] == "docs/HOF_BAKEOFF_GATE.md"
    assert b["gate_frozen"]
