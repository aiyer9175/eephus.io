"""The /management/ payload and the page that renders it.

THE POINT OF THIS PAGE IS THAT IT HAS NO PLUS METRIC. The gate battery was frozen before
it ran, it came back a BOUNDED null, and the verdict set the scope: a club's decision value
in the running game does not repeat between halves of its own season, so no club may be
ranked by it.

What the null buys is the right to say what the league is doing, and the league result is
the page: 13,973 priced attempts, second stolen at almost exactly its own break-even, third
worth having and home not.

THE SIX MISTAKES THESE TESTS EXIST FOR:

  1. SHIPPING A PLUS METRIC ANYWAY. Summed decision value per club is the obvious column and
     it is a ranking of noise. It must not reach the payload, let alone the page.
  2. QUOTING THE RAW SPLIT-HALF. It is 0.7789 and it looks like a strong repeatable skill.
     Both halves of a club-season sit in the same season, so a league-wide year effect reads
     as agreement: season explains 79.6 percent of the variance and the club 2.2 percent.
  3. PUBLISHING AN UNBOUNDED NULL. A null with no detection floor says nothing. This one
     would have seen 0.0005 wins per attempt, which makes it a ceiling.
  4. LOSING THE EXCLUSIONS. Two-out attempts are excluded because the caught-stealing case
     crosses the half-inning boundary where two estimators meet and nothing calibrates them;
     11,783 attempts leave that way and the count belongs on the page. It read 9,328 until
     2026-09-11, because every caught stealing that ENDED a plate appearance lives only on
     the play's own result and was never read (audit F02-01); the census sentence now shows
     the table closing against the corpus.
  5. TYPING A FIGURE INTO THE HTML OR JS.
  6. LETTING THE MANAGER SECTION LOOK DEFERRED RATHER THAN DECIDED. It is not "coming soon":
     the null says building the manager entity to attribute this family is not worth doing.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "management_board.json"
PAGE = ROOT / "management" / "index.html"
JS = ROOT / "assets" / "management.js"
GATE = ROOT / "docs" / "IN_GAME_MANAGEMENT_GATE.md"


@pytest.fixture(scope="module")
def d():
    if not ART.exists():
        pytest.skip("run python mgmt_export.py")
    return json.loads(ART.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# No plus metric, anywhere
# --------------------------------------------------------------------------

def test_the_club_board_carries_no_decision_value_column(d):
    """MISTAKE 1. The gate allows volume and refuses the plus metric."""
    t = d["teams"]
    if t.get("status") != "built":
        pytest.skip(f"club board not built: {t.get('status')}")
    for r in t["rows"]:
        for k in r:
            assert "dv" not in k and "decision" not in k, (
                f"the club board carries {k}, which is the plus metric the gate "
                "withheld")


def test_the_payload_says_why_there_is_no_plus_metric(d):
    s = d["sections"]["team_style"]
    assert s["plus_metric"] is False
    assert "ranking of noise" in s["why_no_plus_metric"]


def test_the_gate_verdict_travels_with_the_payload(d):
    assert "DESCRIPTIVE ONLY" in d["gate_verdict"]
    assert d["gate_doc"] == "docs/IN_GAME_MANAGEMENT_GATE.md"
    assert d["gate_frozen_at"]


def test_the_page_states_what_it_does_not_claim(d):
    txt = d["what_this_page_does_not_claim"]
    assert "bounded null" in txt and "0.0005" in txt


# --------------------------------------------------------------------------
# The gate, reported honestly
# --------------------------------------------------------------------------

def test_the_split_half_sits_inside_its_null_band(d):
    g = d["gate"]
    lo, hi = g["null_band"]
    assert lo < g["split_half_r"] < hi, (
        "the season-controlled split-half now CLEARS its permutation band, which "
        "would mean club decision value repeats after all. That is a real finding "
        "and the whole page scope changes with it")
    assert g["clears_null"] is False


def test_the_raw_number_is_published_beside_the_controlled_one(d):
    """MISTAKE 2. Publishing only the controlled number invites a reader who finds
    the raw one elsewhere to think it was hidden."""
    g = d["gate"]
    assert g["raw_split_half_r_for_comparison"] > 0.7
    assert g["split_half_r"] < 0.2
    why = g["why_the_raw_number_is_not_the_finding"]
    # The sentence is built from the gate fields beside it, so it must quote them,
    # never a typed figure (it quoted 79.6 for weeks after the field read 78.7).
    assert "same season" in why
    assert f"{100.0 * g['variance_explained_by_season']:.1f}" in why


def test_the_null_is_bounded_by_a_detection_floor(d):
    """MISTAKE 3."""
    g = d["gate"]
    assert g["smallest_detectable_per_attempt_sd"] > 0
    assert "ceiling" in g["detection_floor_reading"]


def test_the_null_construction_is_published(d):
    c = d["gate"]["null_construction"]
    assert "WITHIN season" in c
    assert "attempt count" in c


def test_variance_attribution_is_published(d):
    g = d["gate"]
    assert g["variance_explained_by_season"] > 0.5
    assert g["variance_explained_by_team"] < 0.1


# --------------------------------------------------------------------------
# The league result
# --------------------------------------------------------------------------

def test_the_headline_numbers_come_from_the_running_artifact(d):
    h, bt = d["headline"], d["running_game"]["by_target"]
    assert h["league_steals_second_at"] == bt["2B"]["success_rate"]
    assert h["against_a_breakeven_of"] == bt["2B"]["swing_weighted_breakeven_p"]
    assert h["sum_dv_wins_second"] == bt["2B"]["sum_dv_wins"]


def test_second_is_a_coin_and_third_pays_and_home_does_not(d):
    """The finding, pinned. If any of the three flips sign the page's whole lede
    changes and a human should look at it."""
    bt = d["running_game"]["by_target"]
    assert abs(bt["2B"]["success_rate"] - bt["2B"]["swing_weighted_breakeven_p"]) < 0.01
    assert bt["3B"]["sum_dv_wins"] > 0
    assert bt["HOME"]["sum_dv_wins"] < 0


def test_the_swing_weighted_breakeven_is_the_one_that_predicts_the_sign(d):
    """Three break-evens are published and only one determines the verdict. A
    reader comparing the success rate against the MEDIAN would get the sign
    wrong on steals of second."""
    txt = d["running_game"]["which_breakeven_predicts_the_sign"]
    assert "swing-weighted" in txt
    bt = d["running_game"]["by_target"]["2B"]
    assert bt["median_breakeven_p"] != bt["swing_weighted_breakeven_p"]


def test_the_exclusions_are_published_with_their_counts(d):
    """MISTAKE 4."""
    ex = d["running_game"]["excluded"]
    assert ex["two_outs_crosses_the_boundary"] > 1000
    txt = d["running_game"]["why_two_out_attempts_are_excluded"]
    assert "half-inning" in txt and "boundary" in txt


def test_the_census_sentence_is_read_off_the_payload(d):
    """MISTAKE 4 AGAIN, the way it actually happened (audit F02-01). The page
    said the excluded attempts "are excluded and counted" while 2,455 of them
    were neither, and nothing on the page let a reader check. The census
    sentence puts the corpus count beside the priced and excluded counts, every
    figure interpolated from the same payload the table is drawn from."""
    rg = d["running_game"]
    c = rg.get("attempt_census")
    s = rg.get("attempt_census_sentence")
    assert c and s, "rebuild: python management.py, then python mgmt_export.py"
    ex = sum(rg["excluded"].values())
    for n in (c["total"], c["from_the_events_table"],
              c["from_the_play_result_only"], rg["n_attempts_priced"], ex):
        assert f"{n:,}" in s, f"{n:,} is not in the census sentence: {s}"
    if rg["n_attempts_priced"] + ex == c["total"]:
        assert "one or the other" in s
    else:
        assert "one or the other" not in s, (
            "the sentence says the table closes and the payload says it does not")


def test_a_census_gap_is_said_rather_than_hidden():
    """The sentence reports a gap from the counts themselves, never from a flag,
    so a future loss of the same shape reaches the page as a stated number."""
    import mgmt_export as X
    run = {"n_attempts_priced": 10, "excluded": {"a": 3, "b": 0},
           "attempt_census": {"total": 15, "from_the_events_table": 12,
                              "from_the_play_result_only": 3,
                              "seasons": ["2098", "2099"]}}
    s = X._census_sentence(run)
    assert "2 attempts neither priced nor counted" in s
    assert "one or the other" not in s
    run["attempt_census"]["total"] = 13
    assert "one or the other" in X._census_sentence(run)
    assert X._census_sentence({"n_attempts_priced": 1, "excluded": {}}) is None


def test_the_decision_execution_identity_is_exact(d):
    dec = d["running_game"]["decomposition"]
    assert dec["identity_max_abs_error"] == 0.0
    assert "DV + ER" in dec["identity"]


def test_the_league_average_runner_is_deliberate_and_said_so(d):
    txt = d["running_game"]["why_the_league_average_runner"]
    assert "roster fact" in txt


# --------------------------------------------------------------------------
# The reference tables
# --------------------------------------------------------------------------

def test_the_run_expectancy_matrix_has_all_twenty_four_cells(d):
    re = d["reference"]["run_expectancy"]
    assert len(re) == 24
    assert {r["outs"] for r in re} == {0, 1, 2}
    assert len({r["base_code"] for r in re}) == 8


def test_run_expectancy_falls_with_outs_in_every_base_state(d):
    """The one property a reader would notice if it broke."""
    re = d["reference"]["run_expectancy"]
    by = {}
    for r in re:
        by.setdefault(r["base_code"], {})[r["outs"]] = r["runs"]
    for base, cells in by.items():
        assert cells[0] > cells[1] > cells[2], (
            f"base state {base} does not fall monotonically with outs")


def test_the_bases_are_labelled_and_not_left_as_a_bit_code(d):
    re = d["reference"]["run_expectancy"]
    labels = {r["bases"] for r in re}
    assert "loaded" in labels and "empty" in labels and "1B 3B" in labels


def test_the_win_model_disclosures_travel(d):
    """Three things a reader has to be told about a win model built to be
    differenced: that the base state enters only through run expectancy (which
    is what makes differencing safe), that smoothing costs the ninth-inning
    tails, and that the state deliberately excludes everything that would let a
    manager's roster leak into his grade."""
    ref = d["reference"]
    assert "run expectancy" in ref["monotone_by_construction"]
    assert "positive coefficient" in ref["monotone_by_construction"]
    assert "less sharp" in ref["smoothing_costs_the_tails"]
    assert "ninth" in ref["smoothing_costs_the_tails"]
    assert "park" in ref["state_excludes"] and "batter" in ref["state_excludes"]


def test_every_run_expectancy_cell_carries_its_sample_size(d):
    """A run-expectancy cell is only as good as the plays behind it, and
    bases-loaded-two-out is an order of magnitude thinner than
    bases-empty-none-out."""
    for r in d["reference"]["run_expectancy"]:
        assert r["runs"] is not None, (
            f"base {r['base_code']} outs {r['outs']} came back null; the cells "
            "are dicts and reading one as a scalar gives a matrix of nulls")
        assert r["n"] and r["n"] > 100


# --------------------------------------------------------------------------
# The dark sections
# --------------------------------------------------------------------------

def test_the_manager_section_is_decided_and_not_merely_deferred(d):
    """MISTAKE 6. The null says building the manager entity to attribute THIS
    family is not worth doing. That is a decision, not a queue position."""
    s = d["sections"]["manager_attribution"]
    assert s["live"] is False
    assert "UPPER BOUND" in s["why"]
    assert "not there" in s["why"] or "is not there" in s["why"]


def test_the_other_families_are_explicitly_not_covered(d):
    s = d["sections"]["bullpen_and_lineup"]
    assert s["live"] is False
    assert "have not been measured" in s["why"] or "not been measured" in s["why"]


# --------------------------------------------------------------------------
# Nothing is typed, and the page is reachable
# --------------------------------------------------------------------------

def test_no_figure_is_typed_into_the_page_html(d):
    """MISTAKE 5."""
    h = PAGE.read_text(encoding="utf-8")
    for n in (d["running_game"]["n_attempts_priced"],
              d["gate"]["agent_seasons"],
              d["headline"]["games"]):
        assert str(n) not in h, f"{n} is typed into the page and will go stale"


def test_the_js_reads_its_copy_from_the_payload():
    js = JS.read_text(encoding="utf-8")
    for key in ("why_no_plus_metric", "why_the_raw_number_is_not_the_finding",
                "detection_floor_reading", "why_two_out_attempts_are_excluded",
                "attempt_census_sentence",
                "columns_are_style_not_skill", "what_this_page_does_not_claim"):
        assert key in js, f"the page does not render the payload's {key}"
    assert "NOT ONE FIGURE IN THIS FILE IS TYPED" in js


def test_the_page_has_no_banned_dash():
    for f in (PAGE, JS, ROOT / "assets" / "management.css", ROOT / "mgmt_export.py"):
        txt = f.read_text(encoding="utf-8")
        assert "—" not in txt and "–" not in txt, f"banned dash in {f.name}"


def test_management_is_in_the_deploy_publish_list():
    lines = (ROOT / "deploy" / "publish_paths.txt").read_text(
        encoding="utf-8").splitlines()
    assert "management" in lines, (
        "omit this and every test stays green while /management/ 404s in "
        "production")


def test_management_is_in_the_sitemap():
    assert "/management/" in (ROOT / "sitemap.xml").read_text(encoding="utf-8")


def test_management_is_excluded_from_pytest_collection():
    assert "\n    management\n" in (ROOT / "pytest.ini").read_text(encoding="utf-8")


def test_the_export_is_a_watched_scheduled_export():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = src.index("SCHEDULED_EXPORTS = (")
    assert '"mgmt_export"' in src[i:i + 3200]
    assert "6b7c. In-Game Management board" in src


def test_the_board_is_in_the_data_catalog():
    assert '"management_board.json"' in (ROOT / "data_catalog.py").read_text(
        encoding="utf-8")


def test_the_gate_doc_exists_and_is_frozen():
    assert GATE.exists()
    txt = GATE.read_text(encoding="utf-8")
    assert "2026-09-06" in txt


# --- the two invariants whose absence WAS the defect (audit F07-01, F07-02) ---

def test_every_tied_game_boundary_cell_is_populated_and_carries_its_sample(d):
    """F07-01: the served half-inning-start table shipped 18 of 18 tied-game rows
    BLANK, under copy telling the reader the boundary is priced from exactly this
    table. The numbers existed and were correct in data/win_expectancy.json the
    whole time; the export wrapped them in a shape the renderer could not read,
    and no assertion anywhere compared the two. The absence of this test is the
    whole of the finding, so it is the test that matters more than the fix."""
    his = d["reference"]["half_inning_start"]
    tied = his["tied_game"]
    assert len(tied) == 18, f"expected 18 tied-game rows, got {len(tied)}"
    for r in tied:
        assert r.get("batting_team_win_prob") is not None, (
            f"inning {r.get('inning')} {r.get('half')} serves a blank win "
            "probability; that is F07-01 returning")
        assert 0.0 < r["batting_team_win_prob"] < 1.0
        assert (r.get("n") or 0) > 100, (
            f"inning {r.get('inning')} {r.get('half')} carries n={r.get('n')}; a "
            "served cell must publish the sample it was measured on")


def test_the_last_licks_edge_survives_in_the_served_table(d):
    """The bottom of an inning is worth more than the top of the same inning to
    the batting team, because the home side bats last. A table that lost this
    would be reporting noise."""
    tied = d["reference"]["half_inning_start"]["tied_game"]
    by = {(r["inning"], r["half"]): r["batting_team_win_prob"] for r in tied}
    ninth_top, ninth_bot = by.get((9, "top")), by.get((9, "bottom"))
    assert ninth_top is not None and ninth_bot is not None
    assert ninth_bot > ninth_top, (
        f"bottom of the ninth ({ninth_bot}) must beat the top ({ninth_top})")


def test_the_headline_sentence_agrees_in_sign_with_its_own_number(d):
    """F07-02: the served sentence said the running game was 'worth about one and
    a half wins to the entire league' while the corrected number is NEGATIVE. The
    sentence was TYPED and the number was computed, so nothing could catch the
    disagreement. Both are now derived; this pins that they cannot diverge again.

    The rule is the one the accuracy page already follows: a served number inside
    a string is interpolated from the artifact, never typed."""
    hl = d["headline"]
    net = hl.get("net_dv_all_seasons_wins")
    sentence = hl.get("sentence") or ""
    assert net is not None, "the running game serves no net decision value"
    assert sentence, "the running game serves no headline sentence"
    low = sentence.lower()
    if net < 0:
        assert "cost" in low, (
            f"net is {net} wins but the sentence does not say the running game "
            f"costs anything: {sentence[:160]}")
    else:
        assert ("worth" in low) or ("pay" in low), (
            f"net is {net} wins and the sentence does not say so: {sentence[:160]}")
    nums = [float(x) for x in re.findall(r"(\d+\.?\d*)\s*wins", low)]
    assert any(abs(n - abs(net)) < 0.55 for n in nums), (
        f"the sentence quotes {nums} wins and the artifact says {net}")


def test_the_bunt_sentence_agrees_with_its_own_total(d):
    """Same rule, the other served paragraph. The bunt total moved 26.6 percent
    on the F07-02 repair and the sentence has to move with it."""
    blk = d["sections"]["sacrifice_bunt"]
    sentence = (blk.get("sentence") or "").lower()
    assert sentence, "the bunt section serves no sentence"
    total = None
    for k in ("total_decision_value_wins", "total_dv_wins", "total_wins"):
        if blk.get(k) is not None:
            total = float(blk[k]); break
    if total is None:
        pytest.skip("no machine-readable bunt total on this build")
    nums = [float(x) for x in re.findall(r"(\d+\.?\d*)\s*wins", sentence)]
    assert any(abs(n - abs(total)) < 1.5 for n in nums), (
        f"the bunt sentence quotes {nums} wins against an artifact total of {total}")
    if total < 0:
        assert "cost" in sentence
