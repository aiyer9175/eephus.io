# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Three client repairs and one owner decision, all on /betting/ (2026-09-18).

WHAT THESE PIN, and why each one is a sentence rather than a field.

1. THE BOTH-LEGS COPY IS TRUE UNDER EVERY POLICY VALUE, not just the one
   shipped today. `betting_model.SLOT_MARKET_POLICY` has three registered
   values plus a fail-closed reading of an unregistered string, and the page
   used to take its branch from one comparison against "any". Under
   "ledger_gated" it therefore printed "Clearing one leg does not reopen the
   market" for a market whose LEDGER leg alone bars it, where clearing that leg
   does reopen it. The page now reads `ledger_leg_bars` / `dispersion_leg_bars`
   off the payload. The table below drives all four combinations of those two
   booleans plus the payload that carries neither, and asserts the copy is true
   in each, because a branch nobody renders is a branch nobody has read.

2. THE CENSUS COUNTS WHAT IT SAYS IT COUNTS. `n_floor_clearing_sides` is
   policy-filtered at seam 1; the sentence printed it under the words "cleared
   the floor". The unfiltered `n_floor_clearing_sides_before_policy` is served
   for this read and is now the number under those words.

3. THE BADGE IS THE EDGE FLOOR ALONE. The badge is an unfiltered surface (7d,
   measured), so "the bar the picks use" is true only where no leg bars.

4. OWNER DECISION 2026-09-18: the validation tab renders the starter basis
   beside the vintage Brier and the skill t. The substance it has to carry is
   that the backtest grades on the FINAL feed's probable while the served board
   prices the probable listed at the nightly build, and that this is a
   difference in INFORMATION and not an outcome leak, because who starts is
   fixed before first pitch. The tab may not imply a leak.

5. THE SERVED VINTAGE BLURB IS REPAIRED AT THE DOOR THE PAGE READS.
   `betting_export.MODE_MEANING` is copied into data/betting.json by the
   nightly export, so repairing the constant alone would have left the old
   sentence on the tab, directly above the panel that contradicts it, until the
   next 03:10 ET build. `assets/betting.js` carries the current text too and
   prefers it; the tests below pin the two byte for byte and render a payload
   holding the OLD sentence to prove which door wins.

NO NUMBER MOVES, AND THE THREE POLICY SENTENCES DO NOT MOVE EITHER. Under a
policy where neither leg bars, which is HEAD, the census sentence, the
best-value badge note and the both-legs market note render BYTE-IDENTICALLY to
the way they read before this change, receipt and all;
`test_the_census_is_byte_identical_where_no_leg_bars` and
`test_the_no_bars_head_is_byte_identical_to_the_shipped_sentence` are that
claim as tests. What DOES change on the served page is the vintage blurb, which
is the repair, and the new basis panel, which is the owner decision.

Offline: the module's own synthetic payloads through py_mini_racer, plus one
headless Chromium pass over the served page. No network, no odds request.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).resolve().parent
JS_PATH = ROOT / "assets" / "betting.js"
JS = JS_PATH.read_text(encoding="utf-8")

tb = pytest.importorskip("test_betting")


def _ctx(payload: dict, **aux):
    routes = {"main": json.dumps(payload)}
    for k, v in aux.items():
        routes[k] = json.dumps(v)
    return tb._ctx(tb._fetch_js(**routes))


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def _base() -> dict:
    return json.loads(tb.LIVE_PAYLOAD)


# ---------------------------------------------------------------------------
# 1. the both-legs copy, under every state the two booleans can take
# ---------------------------------------------------------------------------
def _with_closed_total(ledger_bars, dispersion_bars, policy="any"):
    """A board whose TOTAL is closed by both legs, with the policy's two legs
    set as the server would publish them. `None` for either means the payload
    predates the fields, which is the fifth state."""
    d = _base()
    pol = {"slot_market_policy": policy, "n_min": 100, "z": 1.645}
    if ledger_bars is not None:
        pol["ledger_leg_bars"] = ledger_bars
        pol["dispersion_leg_bars"] = dispersion_bars
    d["market_publishability"] = {
        "policy": pol,
        "markets": {"total": {
            "both_legs": True,
            "dispersion_leg": {"publishable": False,
                               "reason": "the margin-shape exclusion bars this market"},
            "ledger_leg": {"status": "closed", "brier": 0.26301,
                           "n_games": 118, "t": 1.767}}}}
    return d


def _gate_copy(ledger_bars, dispersion_bars, policy="any") -> str:
    c = _ctx(_with_closed_total(ledger_bars, dispersion_bars, policy))
    return _text(c.eval("__show('potd')"))


def test_where_both_legs_bar_the_market_is_watch_only_and_one_leg_is_not_enough():
    copy = _gate_copy(True, True, "dispersion_gated")
    assert "watch-only for two independent reasons" in copy
    assert "Clearing one leg does not reopen the market" in copy


def test_where_only_the_ledger_leg_bars_clearing_it_reopens_the_market():
    """THE DEFECT, EXACTLY. Under "ledger_gated" the old copy printed
    "Clearing one leg does not reopen the market", which is false: the ledger
    leg is the only one that bars, so clearing it reopens the market.

    MUTATION: restore `var anyPolicy = pol.slot_market_policy === "any"` and
    the two-branch head/tail. This test fails on the sentence."""
    copy = _gate_copy(True, False, "ledger_gated")
    assert "Clearing one leg does not reopen the market" not in copy
    assert "Clearing the evidence leg reopens it" in copy
    assert "evidence leg bars it" in copy
    # the policy is NAMED from the payload, never assumed
    assert "under the ledger_gated slot market policy" in copy
    # the leg that does not bar is stated as disclosure, not as a bar
    assert "rides a published row as disclosure and bars nothing here" in copy


def test_where_only_the_theory_leg_bars_the_sentence_is_the_mirror_image():
    """No registered value produces this pair today. The copy is written for it
    anyway, because the booleans are DATA and a fourth value would arrive as
    data, not as a code change here."""
    copy = _gate_copy(False, True, "some_future_value")
    assert "theory leg bars it" in copy
    assert "Clearing the theory leg reopens it" in copy
    assert "under the some_future_value slot market policy" in copy


def test_where_neither_leg_bars_the_market_is_eligible_and_both_legs_disclose():
    copy = _gate_copy(False, False, "any")
    assert "carries two independent cautions; eligible under the any-market policy" in copy
    assert "Both ride any published row on this market as disclosure" in copy
    assert "Clearing one leg does not reopen the market" not in copy


NOTE_ANY = ("any: every priced market may fill a slot and reach the record; the "
            "dispersion and ledger legs below are disclosure on the row (owner "
            "decision 2026-09-05, docs/diamond-betting.md 7d)")


def test_the_no_bars_head_is_byte_identical_to_the_shipped_sentence():
    """THE HOUSE RULE AS A TEST, on the one sentence this repair could most
    easily have reworded while it was in there fixing the branch. HEAD printed
    a hand-written head under `slot_market_policy === "any"`. The branch is now
    taken from the two booleans, but the words are reproduced exactly, with the
    policy NAME read off `slot_market_policy` and the date parsed off the
    served `slot_market_policy_note`.

    MUTATION: reword the else branch at all, or drop the receipt. This fails."""
    d = _with_closed_total(False, False, "any")
    d["market_publishability"]["policy"]["slot_market_policy_note"] = NOTE_ANY
    copy = _text(_ctx(d).eval("__show('potd')"))
    assert ("The total market carries two independent cautions; eligible under "
            "the any-market policy (2026-09-05).") in copy


def test_the_receipt_is_read_off_the_served_note_and_not_typed_in():
    """A date printed from memory is a claim about a decision nobody re-read.
    The note carries the date of whichever value is in force, so a different
    value prints a different date and a note with no date prints none."""
    d = _with_closed_total(False, False, "later_value")
    d["market_publishability"]["policy"]["slot_market_policy_note"] = (
        "later_value: whatever it does (owner decision 2027-03-04, section 7d)")
    copy = _text(_ctx(d).eval("__show('potd')"))
    assert "eligible under the later_value-market policy (2027-03-04)" in copy
    assert "2026-09-05" not in copy

    bare = _text(_ctx(_with_closed_total(False, False, "any")).eval("__show('potd')"))
    assert "eligible under the any-market policy." in bare
    assert "(20" not in bare


def test_the_receipt_rides_the_gated_sentences_too():
    d = _with_closed_total(True, False, "ledger_gated")
    d["market_publishability"]["policy"]["slot_market_policy_note"] = (
        "ledger_gated: a LEDGER-CLOSED market fills no slot (owner decision "
        "2026-09-17, docs/diamond-betting.md 7d)")
    copy = _text(_ctx(d).eval("__show('potd')"))
    assert "under the ledger_gated slot market policy (2026-09-17)" in copy


def test_a_payload_without_the_fields_says_which_legs_are_closed_and_stops():
    """A payload written before 2026-09-17 carries the two CLOSED legs but not
    which of them bars. The page may state the first and must not guess the
    second: guessing is how the wrong sentence got here in the first place."""
    copy = _gate_copy(None, None, "any")
    assert "is closed on both legs" in copy
    assert "does not say which leg can refuse a slot" in copy
    assert "Clearing one leg does not reopen the market" not in copy
    assert "reopens it" not in copy


def test_the_numbers_in_that_copy_are_still_read_off_the_payload():
    """Every state above prints the same measured leg statistics, and none of
    them is typed into this file's branch logic."""
    for legs in ((True, True), (True, False), (False, True), (False, False), (None, None)):
        copy = _gate_copy(legs[0], legs[1])
        assert "0.26301" in copy and "118" in copy and "1.767" in copy, legs
        assert "the n of 100 floor" in copy and "1.645 one-sided bar" in copy, legs


def test_the_client_reads_the_pick_meta_pair_when_the_table_block_is_absent():
    """TWO DOORS, ONE ANSWER. The server publishes the legs on
    `market_publishability.policy` AND on `pick_meta.market_policy_legs`. A
    payload that carries only the second must reach the same sentence."""
    d = _with_closed_total(None, None, "ledger_gated")
    d["pick_meta"]["market_policy_legs"] = {"ledger_bars": True,
                                            "dispersion_bars": False}
    copy = _text(_ctx(d).eval("__show('potd')"))
    assert "Clearing the evidence leg reopens it" in copy


def _one_leg_board(ledger_bars, dispersion_bars, policy, publishable=False):
    """A board whose RUNLINE is closed on the theory leg alone: its evidence
    leg is open, so `both_legs` is False and the block above never sees it.
    `publishable` is the server's answer with the policy already folded in."""
    d = _base()
    d["market_publishability"] = {
        "policy": {"slot_market_policy": policy, "n_min": 100, "z": 1.645,
                   "ledger_leg_bars": ledger_bars,
                   "dispersion_leg_bars": dispersion_bars},
        "markets": {"runline": {
            "both_legs": False, "publishable": publishable,
            "reason": "excluded while the dispersion correction is unserved "
                      "(section 11a)",
            "dispersion_leg": {"publishable": False,
                               "reason": "the margin-shape exclusion bars this market"},
            "ledger_leg": {"status": "open"}}}}
    return _text(_ctx(d).eval("__show('potd')"))


def test_a_market_barred_by_one_leg_is_disclosed_under_a_gated_policy():
    """THE COVERAGE GAP, WHICH WAS NOT ON THE NAMED LIST. `marketGateNotes`
    returned early unless BOTH legs had closed a market, so under a gated
    policy a market barred by one leg filled no slot and the page said nothing
    about it at all. On the 2026-09-18 payload that market is the runline.

    MUTATION: restore `if (!m.both_legs) return;` as the only pass. This
    fails."""
    copy = _one_leg_board(True, True, "dispersion_gated")
    assert "The runline market fills no" in copy
    assert "its theory leg bars it" in copy
    assert "Its evidence leg is open" in copy
    # the served reason verbatim, through the page's own sentence-caser
    assert "Excluded while the dispersion correction is unserved" in copy


def test_that_disclosure_prints_nothing_where_no_leg_bars():
    """HEAD's policy. `publishable` is true for every market under "any", and
    the pass is guarded by the legs as well, so this moves no served copy."""
    copy = _one_leg_board(False, False, "any", publishable=True)
    assert "fills no" not in copy
    copy2 = _one_leg_board(False, False, "any", publishable=False)
    assert "fills no" not in copy2


def test_that_disclosure_names_the_leg_that_bars_and_not_the_other_one():
    """Under "ledger_gated" the theory leg does not bar, so a theory-closed
    market whose evidence leg is open is NOT barred and gets no line. Printing
    one would be the mirror of the defect this step repaired."""
    copy = _one_leg_board(True, False, "ledger_gated", publishable=True)
    assert "fills no" not in copy


# ---------------------------------------------------------------------------
# 2. the census reads the unfiltered count
# ---------------------------------------------------------------------------
def _census(before=None, filtered=6) -> str:
    d = _base()
    for k in ("pick_of_the_day", "longshot_of_the_day"):
        d[k] = None
    d["pick_meta"]["n_floor_clearing_sides"] = filtered
    if before is not None:
        d["pick_meta"]["n_floor_clearing_sides_before_policy"] = before
    else:
        d["pick_meta"].pop("n_floor_clearing_sides_before_policy", None)
    return _text(_ctx(d).eval("__show('potd')"))


def test_the_census_puts_the_unfiltered_count_under_the_words_cleared_the_floor():
    """`n_floor_clearing_sides` is policy-filtered at seam 1, so under a gated
    value it counts "cleared the floor AND the policy lets it fill a slot".
    Printed under "cleared the floor" it overstates the filter and understates
    the board.

    MUTATION: read `meta.n_floor_clearing_sides` for the floor clause. The
    first assertion fails."""
    copy = _census(before=11, filtered=6)
    assert "11 cleared the 6.0% floor" in copy
    assert "6 of those are on a market the slot policy lets fill a" in copy
    assert "and none of those are inside" in copy


def test_the_census_is_byte_identical_where_no_leg_bars():
    """THE HOUSE RULE, AS A TEST. Where the two counts agree, which is every
    board under a policy whose legs both disclose, the sentence renders exactly
    as it did before this change: no served number moves."""
    copy = _census(before=6, filtered=6)
    assert "6 cleared the 6.0% floor, and none of those are inside" in copy
    assert "slot policy lets fill" not in copy


def test_the_census_falls_back_to_the_filtered_count_on_an_older_payload():
    """A payload with no unfiltered count is the payload the old sentence was
    written for; it prints what it has rather than a blank."""
    copy = _census(before=None, filtered=6)
    assert "6 cleared the 6.0% floor, and none of those are inside" in copy


# ---------------------------------------------------------------------------
# 3. the best-value badge is the edge floor alone
# ---------------------------------------------------------------------------
def _badge_note(ledger_bars, dispersion_bars) -> str:
    d = _base()
    if ledger_bars is not None:
        d["pick_meta"]["market_policy_legs"] = {"ledger_bars": ledger_bars,
                                                "dispersion_bars": dispersion_bars}
    else:
        d["pick_meta"].pop("market_policy_legs", None)
    return _text(_ctx(d).eval("__show('teams')"))


def test_where_no_leg_bars_the_badge_bar_is_the_bar_the_slots_use():
    # The noun is Model Watch's or the pick board's, per `selNounPl`, so the
    # assertion allows either rather than pinning the module's watch state.
    copy = _badge_note(False, False)
    assert re.search(r"the bar the (picks|selections) use", copy), copy


def test_where_a_leg_bars_the_badge_is_named_as_the_edge_floor_alone():
    """7d measured that the badge is an UNFILTERED surface: three rows on the
    cached 2026-09-18 board carry a best-value badge on the ledger-closed
    total under all three policy values. So under a gated value "the bar the
    picks use" claims an agreement that does not hold.

    MUTATION: drop the `policyLegs` read and restore the flat sentence. This
    fails."""
    copy = _badge_note(True, False)
    assert not re.search(r"the bar the (picks|selections) use", copy), copy
    assert "the edge floor alone" in copy
    assert "a badge is not a claim of eligibility" in copy


def test_an_older_payload_says_it_does_not_know_rather_than_claiming_agreement():
    copy = _badge_note(None, None)
    assert not re.search(r"the bar the (picks|selections) use", copy), copy
    assert re.search(r"does not say whether the (picks|selections) apply a "
                     r"further market rule", copy), copy


# ---------------------------------------------------------------------------
# 4. the starter basis, rendered on the validation tab
# ---------------------------------------------------------------------------
STARTER_BASIS = {
    "source": "final feed probablePitchers",
    "field": "completed_games.home_sp / away_sp",
    "doors": {"agreement": {"sides_compared": 4576, "differ": 0, "n_games": 2288,
                            "measured_on": "2026-09-17"}},
    "counts": {"n_games": 2294, "both_sides_named": 2292},
    "equals_first_pitcher_used": {
        "sides_compared": 4392, "equal": 4385, "differ": 7,
        "sides_without_a_probable": 2, "measured_on": "2026-09-11",
        "denominator_note": "frozen, and NOT the counts block in this same disclosure"},
    "served_board_reads": "the probable listed at the nightly build, which is not this field",
    "copy_repair_owed": "named 2026-09-17, owed",
    "note": "the backtest's starter is the FINAL feed's probable",
}


def _validation(evald: dict | None = None, payload: dict | None = None) -> str:
    d = payload or _base()
    c = _ctx(d, evald=(evald if evald is not None else {"starter_basis": STARTER_BASIS}))
    return c.eval("__show('validation')")


def test_the_validation_tab_renders_the_starter_basis():
    """OWNER DECISION 2026-09-18. The block shipped in the artifact on
    2026-09-17 and was not rendered; placement was the open question and the
    answer is the validation tab, beside the vintage Brier and the skill t."""
    copy = _text(_validation())
    assert "What the graded sample was priced on" in copy
    assert "final feed" in copy
    assert "completed_games.home_sp / away_sp" in copy
    assert "4385 of 4392" in copy or "4,385 of 4,392" in copy
    assert "4576 sides across 2288 games, 0 differences" in copy or \
           "4,576 sides across 2,288 games, 0 differences" in copy


def test_the_tab_states_the_information_distinction_and_does_not_imply_a_leak():
    """THE SENTENCE THE PANEL EXISTS FOR. A reader told the backtest used the
    final feed must be able to tell which of the two this is. Both halves ride
    together: the board reads a different pitcher, AND who starts is fixed
    before first pitch, so the difference is information and not a leak.

    MUTATION: delete either half of the lead sentence. This fails."""
    copy = _text(_validation())
    assert "prices the probable listed at the nightly build" in copy
    assert "fixed before first pitch" in copy
    assert "difference in information" in copy
    assert "not an outcome leak" in copy


def test_the_tab_does_not_render_the_internal_owed_marker():
    """`copy_repair_owed` names a repair that landed on 2026-09-18. It is an
    internal marker in an artifact this step does not own, so it is read by
    nobody on the page rather than served as a stale claim."""
    copy = _text(_validation())
    assert "copy_repair_owed" not in copy
    assert "owed" not in copy.lower().split("priced on")[-1][:400]


def test_the_park_basis_renders_beside_it_off_the_payloads_own_block():
    d = _base()
    d.setdefault("model", {}).setdefault("validation", {})["vintage"] = {
        "park_basis": {"source": "mixed", "n_games_vintage_park": 936,
                       "n_games_neutral_park": 11, "n_eval_games_neutral_park": 11,
                       "note": "the park index is read from each game's own vintage record"}}
    copy = _text(_validation(payload=d))
    assert "The park index" in copy
    assert "936" in copy and "11" in copy


def test_the_dark_columns_render_under_a_heading_that_says_they_priced_nothing():
    """`feature_basis` counts schema-3 dark capture. Rendering it under "what
    priced the sample" without that qualifier would be the false half of an
    honest panel."""
    copy = _text(_validation(evald={
        "starter_basis": STARTER_BASIS,
        "vintage": {"feature_basis": {
            "xwoba_14": {"n_eval_games": {"populated": 205, "null_stated": 194,
                                          "predates_column": 243}},
            "note": "schema-3 dark capture only; nothing served reads these columns"}}}))
    assert "The dark columns, which priced nothing" in copy
    assert "xwoba_14" in copy
    assert "205" in copy and "194" in copy and "243" in copy
    assert "nothing served reads these columns" in copy


def test_the_panel_says_so_rather_than_drawing_a_blank_when_the_artifact_is_absent():
    copy = _text(_validation(evald={}))
    assert "Starter basis: not measured yet" in copy
    assert "carries no starter_basis block" in copy


def test_the_panel_sits_between_the_validation_state_and_the_calibration_panel():
    """Placement is the decision, so placement is pinned. The owner asked for
    it beside the vintage Brier and the skill t, which `honestResult` prints at
    the top of this tab."""
    html = _validation()
    i_val = html.index("Is the model validated?")
    i_new = html.index("What the graded sample was priced on")
    assert i_val < i_new, "the basis panel must follow the validation panel"
    if "Reliability" in html:
        assert i_new < html.index("Reliability"), \
            "the basis panel must precede the calibration panel"


# ---------------------------------------------------------------------------
# 5. the vintage blurb, repaired at the door the page reads
# ---------------------------------------------------------------------------
def _client_mode_meaning() -> dict:
    """The client table, read out of the file rather than re-typed here."""
    m = re.search(r"\n  var MODE_MEANING = \{\n(.*?)\n  \};\n", JS, re.S)
    assert m, "assets/betting.js carries no MODE_MEANING table"
    out = {}
    for part in re.split(r",\n(?=    \w+: )", m.group(1)):
        key, _, rest = part.partition(":")
        out[key.strip()] = "".join(
            json.loads(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"', rest))
    return out


def test_the_client_mode_meaning_is_the_server_constant_byte_for_byte():
    """TWO DOORS, ONE SENTENCE. The client copy exists only because the served
    payload is a day behind the source constant; the moment the two could say
    different things it would be a second opinion instead of a fresher copy.

    MUTATION: change either string. This fails."""
    be = pytest.importorskip("betting_export")
    assert _client_mode_meaning() == dict(be.MODE_MEANING)


def test_the_page_prefers_the_current_text_over_a_stale_payload():
    """THE DEFECT THIS CLOSES. data/betting.json carries the sentence the
    export wrote last night, and the repaired sentence reaches it only at the
    next build. Until then the tab would have printed the old one directly
    above the new panel saying the opposite.

    MUTATION: render `v.mode_meaning.vintage` again. This fails."""
    be = pytest.importorskip("betting_export")
    stale = ("Every game is priced on a leaderboard snapshot whose knowledge "
             "cutoff is strictly before that game: team offense, team run "
             "prevention, the listed probable and the park index all come out "
             "of that snapshot.")
    d = _base()
    d["model"]["validation"]["mode_meaning"] = {"contaminated": "stale contaminated",
                                                "vintage": stale}
    copy = _text(_ctx(d).eval("__show('validation')"))
    assert "the listed probable and the park index" not in copy
    assert be.MODE_MEANING["vintage"] in copy


def test_a_payload_with_no_mode_meaning_still_renders_nothing_there():
    """The client table is a fresher copy of a served string, never the only
    copy of one: a payload that predates the field prints no blurb, exactly as
    it did before."""
    be = pytest.importorskip("betting_export")
    d = _base()
    d["model"]["validation"].pop("mode_meaning", None)
    copy = _text(_ctx(d).eval("__show('validation')"))
    assert be.MODE_MEANING["vintage"] not in copy
    assert "Vintage mode." not in copy


def test_the_repaired_blurb_names_both_halves_and_refuses_the_leak_reading():
    be = pytest.importorskip("betting_export")
    blurb = be.MODE_MEANING["vintage"]
    assert "SEM+ ratings" in blurb
    assert "completed-game row" in blurb
    assert "nightly build" in blurb
    assert "information and not an outcome leak" in blurb
    assert "the listed probable and the park index" not in blurb


# ---------------------------------------------------------------------------
# 6. three blocks, three pools
# ---------------------------------------------------------------------------
def test_the_panel_names_the_graded_sample_and_each_block_names_its_own_pool():
    """THREE DENOMINATORS UNDER ONE HEADING is how a reader gets the park
    count confused with the Brier's sample. The park rows walk the GRADABLE
    pool, fit half included; the dark columns walk the graded sample; the
    starter counts walk the completed-game cache, which is not a grading pool.

    MUTATION: drop any of the three pool labels. This fails."""
    d = _base()
    d["model"]["validation"]["vintage"] = {
        "n_graded": 642, "n_gradable": 947, "n_fit_games": 305,
        "park_basis": {"source": "mixed", "n_games_vintage_park": 936,
                       "n_games_neutral_park": 11,
                       "n_eval_games_neutral_park": 11}}
    copy = _text(_validation(payload=d))
    assert "sample of 642 graded games" in copy
    assert "947 gradable games (305 fitted, 642 graded)" in copy
    assert "completed-game cache, which is not the graded sample" in copy


def test_the_pool_lines_degrade_rather_than_invent_a_denominator():
    """An artifact with no pool counts must print the rows without a pool
    rather than a guessed one."""
    d = _base()
    d["model"]["validation"]["vintage"] = {
        "park_basis": {"source": "mixed", "n_games_vintage_park": 936,
                       "n_games_neutral_park": 11}}
    copy = _text(_validation(payload=d))
    assert "every gradable game" in copy
    assert "graded games." not in copy.split("priced on")[1][:200]


# ---------------------------------------------------------------------------
# 7. the rendered result, in a real browser, at three widths
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("width,height", [(1280, 900), (1440, 900), (390, 844)])
def test_the_validation_tab_fits_its_box_at_every_width(width, height):
    """No sideways page scroll, every panel inside the viewport, the new table
    inside its own scrollport, and no console error. Measured on the served
    page, not on a fixture."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from conftest import serve_site
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:                              # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page(viewport={"width": width, "height": height})
        errs = []
        page.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
        page.on("console", lambda m: errs.append("console." + m.type + ": " + m.text)
                if m.type == "error" else None)
        page.goto(base + "betting/index.html#section=validation",
                  wait_until="load", timeout=60_000)
        try:
            page.wait_for_function(
                "() => !![...document.querySelectorAll('.bt-panel-hd')]"
                ".find(e => /What the graded sample was priced on/.test(e.textContent))",
                timeout=60_000)
        except Exception:
            browser.close()
            pytest.skip("the basis panel did not render on this checkout "
                        "(no betting payload or no eval artifact)")
        res = page.evaluate("""() => {
          const doc = document.scrollingElement;
          const hd = [...document.querySelectorAll('.bt-panel-hd')]
            .find(e => /What the graded sample was priced on/.test(e.textContent));
          const mine = hd.closest('.bt-panel');
          const panels = [...document.querySelectorAll('.bt-panel')].map(el => {
            const r = el.getBoundingClientRect();
            return { right: Math.round(r.right), left: Math.round(r.left) }; });
          const tables = [...mine.querySelectorAll('.bt-scroll')].map(el => ({
            tableW: Math.round(el.firstElementChild.scrollWidth),
            portW: Math.round(el.clientWidth) }));
          return { pageScrollW: doc.scrollWidth, pageClientW: doc.clientWidth,
                   inner: window.innerWidth, panels, tables }; }""")
        browser.close()
    assert not errs, errs
    assert res["pageScrollW"] <= res["pageClientW"] + 1,         f"sideways page scroll at {width}: {res}"
    for pn in res["panels"]:
        assert pn["left"] >= -1 and pn["right"] <= res["inner"] + 1, (width, pn)
    assert res["tables"], "the basis panel drew no table"
    for t in res["tables"]:
        assert t["tableW"] <= t["portW"] + 1, (width, t)


@pytest.mark.parametrize("width", [1280, 1440])
def test_a_bounded_scrollport_still_holds_its_sticky_header(width):
    """THE VALIDATION TAB HAS NO BOUNDED SCROLLPORT, at any of the three widths
    measured: every table on it is short enough to fit, so a sticky-header
    assertion made there would pass over an empty list. This exercises the
    mechanism where it actually engages, on the Team Bets board leaderboard,
    so the guard is not vacuous. The new table uses the same wrapper classes
    (`bt-scroll mlbstats-scroll` around `bt-table mlbstats-table`), which is
    what makes this the same header rule."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from conftest import serve_site
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:                              # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page(viewport={"width": width, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
        page.goto(base + "betting/index.html#section=teams",
                  wait_until="load", timeout=60_000)
        try:
            page.wait_for_function(
                "() => !!document.querySelector('[data-teamview=\"board\"]')",
                timeout=60_000)
        except Exception:
            browser.close()
            pytest.skip("no board view on this checkout")
        page.evaluate(
            "() => document.querySelector('[data-teamview=\"board\"]').click()")
        page.wait_for_timeout(300)
        res = page.evaluate("""() => {
          const doc = document.scrollingElement;
          const ports = [...document.querySelectorAll('.bt-scroll')]
            .filter(el => el.scrollHeight > el.clientHeight + 1
                          && el.querySelector('thead th'))
            .map(el => {
              const th = el.querySelector('thead th');
              el.scrollTop = 120;
              const d = Math.round(th.getBoundingClientRect().top
                                   - el.getBoundingClientRect().top);
              el.scrollTop = 0;
              return d; });
          return { ports, pageScrollW: doc.scrollWidth,
                   pageClientW: doc.clientWidth }; }""")
        browser.close()
    assert not errs, errs
    assert res["pageScrollW"] <= res["pageClientW"] + 1, res
    if not res["ports"]:
        pytest.skip("no bounded scrollport on this checkout's board")
    for offset in res["ports"]:
        assert abs(offset) <= 2,             f"a sticky table header came unstuck at {width}: offset {offset}"
