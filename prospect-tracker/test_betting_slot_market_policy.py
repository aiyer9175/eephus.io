# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The THIRD slot market policy value: the ledger leg bars, the dispersion leg
discloses (owner decision 2026-09-17, O15; docs/diamond-betting.md 7d).

WHAT WAS WRONG WITH TWO VALUES. `SLOT_MARKET_POLICY` had "any" and
"dispersion_gated", and every seam read it as ONE BIT: `gated =
SLOT_MARKET_POLICY != "any"` turned BOTH legs on together. Two registered
sections asked for the missing third state by name and could not have it:

  5k   "slots come from publishable markets only, so the total stays out of the
       slots and badges while its ledger leg is closed ... No SLOT_MARKET_POLICY
       value does that today; a ledger-leg value is to be built."
  7e-D "Under its default (publishable markets only; the policy value is to be
       built), the ledger-closed total cannot fill a slot."

Under "dispersion_gated" the total does leave the slots, but so does the
RUNLINE, whose ledger leg is open and which is barred only by the dispersion
correction the site has decided to DISCLOSE rather than enforce (2026-09-05,
7d). The owner's answer needs one leg to bar and the other to speak, and one
bit cannot carry that.

WHAT THIS FILE PINS.
  1. The default is OFF: HEAD is still "any" and nothing here flips it. The
     value is built and registered; selecting it is the owner's commit.
  2. Each policy value's two legs, including the fail-closed reading of an
     unregistered value (both legs bar, exactly as `!= "any"` did).
  3. THE NAMED PROPERTY: under "ledger_gated" the dispersion leg can never by
     itself refuse a slot, at either seam, on any board.
  4. The two OLDER values are byte-for-byte what they were, measured against a
     re-implementation of the old one-bit rule over a grid of boards.
  5. The served sentences: the policy note, the table note and the slot meta
     say the same rule as the fields beside them, under every value.
  6. The slot lock (R4-1a) and the policy do not fight: a row published under
     one policy keeps serving after a flip, with the flip disclosed through
     `since_published`, because a publication is not un-published by a later
     rule.

Every write here goes to `tmp_path` or an in-memory fake: nothing in this file
writes a betting artifact (plan stop-item X6).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

be = pytest.importorskip("betting_export")
bm = pytest.importorskip("betting_model")

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "diamond-betting.md"

ANY = "any"
DISP = "dispersion_gated"
LEDGER = "ledger_gated"
DAY = "2026-09-17"


@pytest.fixture(autouse=True)
def _unserved_dispersion(monkeypatch):
    """The premise of every expectation below: the dispersion correction is
    unserved, so the theory leg has something to say about runline and total.
    Pinned rather than assumed, and restored after each test."""
    monkeypatch.setattr(bm, "SERVE_RUN_DISPERSION", False)
    yield


def _policy(monkeypatch, value):
    monkeypatch.setattr(bm, "SLOT_MARKET_POLICY", value)


def _board():
    """One game carrying a clearing side in all three markets, so a market that
    is absent downstream is absent because it was REFUSED and not because it
    failed to clear. Same shape as test_betting_dispersion_exclusion._board."""
    def row(side, edge):
        return {"side": side, "edge": edge, "odds": -110, "book": "testbook",
                "model_prob": 0.60, "market_fair_prob": 0.60 - edge,
                "kelly_full": 0.2}
    return [{
        "game_pk": 1, "start": "2026-09-17T23:05:00Z",
        "away": {"org": "AAA"}, "home": {"org": "BBB"},
        "moneyline": [row("home", 0.20)],
        "runline": [row("home", 0.30)],
        "total": {"sides": [row("over", 0.40)]},
    }]


def _markets(closed=frozenset(), extra=None):
    return {c["market"] for c in
            be._floor_clearing_sides(_board(), 0.06, ledger_closed=closed,
                                     extra_rows=extra)}


def _table(policy_state=None, *, closed=()):
    """The publishability table off a FIXED gate state, so these tests read the
    sentence and the flags and never the live ledger."""
    state = policy_state or {
        "markets": {m: {"status": "ledger_closed" if m in closed else "open"}
                    for m in be.GATED_MARKETS},
        "last_evaluation_date": None}
    return be.market_publishability(
        state=state,
        full={m: {"n_games": 0, "n_min": 100, "z": 1.645}
              for m in be.GATED_MARKETS},
        trailing={m: {"n_games": 0} for m in be.GATED_MARKETS})


# ===========================================================================
# 1. the value ships OFF, and the three values are the registered three
# ===========================================================================
def test_the_head_policy_is_still_any_so_the_third_value_ships_off():
    """DEFAULT OFF. The registration (7d) says HEAD is "any"; building a value
    is not selecting it, and selecting it is the owner's own commit."""
    assert bm.SLOT_MARKET_POLICY == ANY
    legs = be.slot_market_policy_legs()
    assert legs["dispersion_bars"] is False and legs["ledger_bars"] is False


def test_the_code_registers_exactly_three_values():
    assert be.SLOT_MARKET_POLICIES == (ANY, DISP, LEDGER)
    assert be.SLOT_POLICY_ANY == ANY
    assert be.SLOT_POLICY_DISPERSION_GATED == DISP
    assert be.SLOT_POLICY_LEDGER_GATED == LEDGER


@pytest.mark.parametrize("value,dispersion,ledger", [
    (ANY, False, False),
    (DISP, True, True),
    (LEDGER, False, True),
])
def test_each_registered_value_says_which_leg_bars(value, dispersion, ledger):
    legs = be.slot_market_policy_legs(value)
    assert legs["dispersion_bars"] is dispersion
    assert legs["ledger_bars"] is ledger
    assert legs["known"] is True


@pytest.mark.parametrize("value", ["ledger-gated", "LEDGER_GATED", "Any", "",
                                   "dispersion", "publishable_only",
                                   " any", "any ", "\tany", " ledger_gated"])
def test_an_unregistered_value_bars_both_legs(value):
    """FAIL CLOSED, exactly as `!= "any"` did. A typo in the constant must not
    be the thing that opens the slots to a market two legs closed.

    THE PADDED VALUES ARE THE POINT OF THE LAST FOUR. The first cut stripped
    the constant before comparing it, so " any" opened BOTH legs where
    `!= "any"` closed both, and the table published `registered_policy: true`
    beside it. A stray space is a typo, and the one value a fail-closed rule
    may not fail open on is the one a typo produces.

    MUTATION: put `.strip()` back in `slot_market_policy_legs`. The four padded
    parameters fail and the six unpadded ones do not."""
    legs = be.slot_market_policy_legs(value)
    assert legs["dispersion_bars"] is True and legs["ledger_bars"] is True
    assert legs["known"] is False
    assert "not a registered slot market policy" in legs["note"]
    # The comparison this reproduces, on the same value.
    assert value != be.SLOT_POLICY_ANY


def test_the_policy_is_read_at_call_time_and_not_at_import(monkeypatch):
    """Every seam calls the helper per build. A value captured at import would
    make a mid-run flip invisible, which is how a policy stops being a policy."""
    _policy(monkeypatch, LEDGER)
    assert be.slot_market_policy_legs()["ledger_bars"] is True
    _policy(monkeypatch, ANY)
    assert be.slot_market_policy_legs()["ledger_bars"] is False


def test_no_seam_reads_the_policy_as_one_bit():
    """THE REGRESSION PIN, read off the syntax tree so a comment or a docstring
    cannot satisfy it. `bm.SLOT_MARKET_POLICY` may be STAMPED on a row; it may
    not be COMPARED anywhere, because a comparison is the one-bit reading the
    third value broke. New seams go through `slot_market_policy_legs`."""
    tree = ast.parse((ROOT / "betting_export.py").read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for side in [node.left] + list(node.comparators):
            if (isinstance(side, ast.Attribute)
                    and side.attr == "SLOT_MARKET_POLICY"):
                bad.append(getattr(node, "lineno", None))
    assert not bad, f"the policy is compared as one bit at line(s) {bad}"


def test_no_client_side_one_bit_read_of_the_policy_survives():
    """THE PIN ABOVE WALKS ONE FILE, so it cannot see the reader that is NOT in
    it. assets/betting.js used to compare the served policy string to "any" and
    print a both-legs sentence off the result; under "ledger_gated" that
    sentence ("clearing one leg does not reopen the market") is false, because
    clearing the LEDGER leg does reopen it.

    WHEN THIS PIN WAS WRITTEN (2026-09-17) the client belonged to another track
    and the boundary of the known state was "exactly ONE such comparison
    exists". The repair landed on 2026-09-18, so the boundary is now ZERO, and
    the two booleans the page reads instead are asserted here in place of the
    comparison it replaced. A new comparison appearing fails here rather than
    reaching a page under a policy value nobody has read the copy against.

    COMMENTS ARE STRIPPED FIRST, FOR BOTH HALVES. This walks source lines, and
    a comment that quotes the old expression to explain why it is gone is
    documentation, not a read. The same cut applies to the field names: the
    block of comments that replaced the old branch names all five of them, so a
    pin that searched the whole file would pass on the comments alone after
    every real read had been deleted."""
    js = ROOT / "assets" / "betting.js"
    if not js.exists():
        pytest.skip("the client is not in this tree")
    src = js.read_text(encoding="utf-8", errors="replace")
    code = [ln for ln in src.splitlines() if not ln.lstrip().startswith("//")]
    assert code, "assets/betting.js is comments all the way down"
    hits = [ln for ln in code if "slot_market_policy" in ln
            and ("===" in ln or "!==" in ln or "==" in ln)]
    assert hits == [], hits
    # ... and the page reads the pair the server derives, from either block.
    body = "\n".join(code)
    for field in ("ledger_leg_bars", "dispersion_leg_bars",
                  "market_policy_legs", "ledger_bars", "dispersion_bars"):
        assert field in body, f"the client no longer reads {field}"
    # The fields it reads are the ones the server publishes.
    assert "ledger_leg_bars" in (ROOT / "betting_export.py").read_text(
        encoding="utf-8")
    if DOC.exists():
        doc = DOC.read_text(encoding="utf-8", errors="replace")
        assert "NAMED FOLLOW-UPS IN assets/betting.js" in doc
        assert "marketGateNotes" in doc and "bestValueSide" in doc
        assert "LANDED 2026-09-18" in doc


def test_the_runbook_does_not_claim_the_badge_is_gated():
    """THE BADGE IS A CLIENT-SIDE SURFACE AND THE POLICY DOES NOT REACH IT.
    5k and 7e-D say "slots and badges" and the badge half has never been true
    of any policy value; the registration this change adds must not repeat it.

    MUTATION: put "wins no value badge" back in the 7d paragraph. This fails,
    and so does the page, three times, on the cached board."""
    if not DOC.exists():
        pytest.skip("the runbook is not in this tree")
    doc = DOC.read_text(encoding="utf-8", errors="replace")
    assert "wins no value badge" not in doc
    assert "bestValueSide" in doc and "UNFILTERED surface" in doc


# ===========================================================================
# 2. THE NAMED PROPERTY: the dispersion leg alone never refuses a slot
# ===========================================================================
def test_the_fixture_would_publish_all_three_markets(monkeypatch):
    """NON-VACUITY FIRST. All three markets clear the floor, so an absent
    market in any test below is a refusal and not a failure to clear."""
    _policy(monkeypatch, ANY)
    assert _markets() == {"moneyline", "runline", "total"}


def test_the_dispersion_leg_can_never_by_itself_refuse_a_slot(monkeypatch):
    """THE PROPERTY THE THIRD VALUE EXISTS FOR, at seam 1.

    For every subset of markets the LEDGER leg has closed, the candidate list
    under "ledger_gated" is exactly the markets whose ledger leg is open. The
    dispersion leg is false for runline and total throughout (pinned below) and
    removes nothing.

    MUTATION: restore `if legs["dispersion_bars"] ...` to `if gated ...` in
    `_floor_clearing_sides` and the runline and total rows disappear here."""
    assert bm.market_theory_ok("runline") is False
    assert bm.market_theory_ok("total") is False, "the premise moved"
    _policy(monkeypatch, LEDGER)
    all_three = {"moneyline", "runline", "total"}
    for closed in ([], ["total"], ["runline"], ["moneyline"],
                   ["runline", "total"], ["moneyline", "runline", "total"]):
        assert _markets(frozenset(closed)) == all_three - set(closed), closed


def test_under_the_new_value_a_dispersion_barred_market_wins_the_slot(monkeypatch):
    """The whole point, end to end: the runline is the best side on this board,
    its ledger leg is open, and it takes the headline slot carrying the Poisson
    caveat as disclosure."""
    _policy(monkeypatch, LEDGER)
    board = _board()
    board[0]["total"]["sides"][0]["odds"] = 600      # out of the POTD band
    board[0]["runline"][0]["model_prob"] = 0.70      # the most confident side
    slots, _reason, meta = be.provisional_picks(board, odds_priceable=True)
    potd = slots["pick_of_the_day"]
    assert potd["market"] == "runline"
    assert potd["caveat"] == be.POISSON_CAVEAT
    assert "evidence_caveat" not in potd
    assert potd["market_policy"] == LEDGER
    assert meta["market_policy_legs"] == {"dispersion_bars": False,
                                          "ledger_bars": True}


def test_under_the_new_value_a_ledger_closed_market_fills_no_slot(monkeypatch):
    """The other half: the leg that DOES bar, bars. Same board, same floor."""
    _policy(monkeypatch, LEDGER)
    assert _markets(frozenset({"total"})) == {"moneyline", "runline"}
    assert _markets(frozenset({"runline", "total"})) == {"moneyline"}


def test_props_follow_the_ledger_leg_under_the_new_value(monkeypatch):
    """Props are not in DISPERSION_SENSITIVE_MARKETS (7c), so the dispersion
    leg never had anything to say about them; the ledger leg is their whole
    gate under every value, including this one."""
    _policy(monkeypatch, LEDGER)
    prop = [{"market": "props_pitcher_strikeouts", "player": "Some Arm",
             "game_pk": 1, "matchup": "AAA at BBB", "start": "x",
             "label": "Some Arm Over 6.5", "side": "over", "point": 6.5,
             "edge": 0.50, "odds": -115, "book": "testbook", "model_prob": 0.80,
             "market_fair_prob": 0.30, "ev_per_unit": 0.4, "kelly_full": 0.3}]
    assert "props_pitcher_strikeouts" in _markets(frozenset(), extra=prop)
    assert "props_pitcher_strikeouts" not in _markets(
        frozenset({"props_pitcher_strikeouts"}), extra=prop)


def test_the_dispersion_leg_alone_never_refuses_a_record_row(monkeypatch, tmp_path):
    """THE SAME PROPERTY AT SEAM 2, in the FEED vocabulary (h2h / spreads /
    totals), which is the vocabulary the 2026-08-16 repair exists for."""
    _policy(monkeypatch, LEDGER)
    p = tmp_path / "record.json"
    p.write_text("[]", encoding="utf-8")
    rows = [{"bet_id": "a", "market": "h2h", "side": "home"},
            {"bet_id": "b", "market": "spreads", "side": "home"},
            {"bet_id": "c", "market": "totals", "side": "over"}]
    out = be.append_record(rows, path=p, ledger_closed=frozenset())
    assert [r["bet_id"] for r in out] == ["a", "b", "c"]
    by = {r["bet_id"]: r for r in out}
    assert by["b"]["dispersion_sensitive"] is True, "spreads is the runline"
    assert by["c"]["dispersion_sensitive"] is True
    assert all(r["market_policy"] == LEDGER for r in out)

    # and the ledger leg still refuses, on the board name, through the feed one
    p2 = tmp_path / "record2.json"
    p2.write_text("[]", encoding="utf-8")
    out2 = be.append_record(rows, path=p2, ledger_closed=frozenset({"total"}))
    assert [r["bet_id"] for r in out2] == ["a", "b"]


# ===========================================================================
# 3. the two older values did not move
# ===========================================================================
def _old_one_bit_markets(policy, closed):
    """The rule as it stood before the third value: one bit, both legs."""
    gated = policy != ANY
    out = set()
    for m in ("moneyline", "runline", "total"):
        if gated and not bm.market_theory_ok(m):
            continue
        if gated and m in closed:
            continue
        out.add(m)
    return out


@pytest.mark.parametrize("policy", [ANY, DISP])
def test_the_two_older_values_select_exactly_what_they_used_to(policy, monkeypatch):
    """A GRID, not one board: every subset of closed markets, both old values,
    compared against a re-implementation of the one-bit rule."""
    _policy(monkeypatch, policy)
    for closed in ([], ["total"], ["runline"], ["moneyline"],
                   ["runline", "total"], ["moneyline", "runline", "total"]):
        got = _markets(frozenset(closed))
        assert got == _old_one_bit_markets(policy, set(closed)), (policy, closed)


@pytest.mark.parametrize("policy", [DISP, LEDGER, "typo"])
def test_market_is_publishable_still_answers_its_own_question(policy, monkeypatch):
    """THE ASSUMPTION THE NARROWING RESTS ON, pinned. The seams now ask
    `market_theory_ok` (the leg) instead of `market_is_publishable` (the leg
    with the policy folded in). For every non-"any" value the two agree, so the
    two older values cannot have moved. If betting_model ever changes that,
    this fails rather than the slots quietly changing."""
    _policy(monkeypatch, policy)
    for m in ("moneyline", "runline", "total", "props_batter_home_runs"):
        assert bm.market_is_publishable(m) is bm.market_theory_ok(m), m


def test_under_any_market_is_publishable_is_true_and_the_leg_is_not(monkeypatch):
    """The other side of the same seam: under "any" the folded answer is True
    for a market the leg bars, which is exactly why the seams stopped asking
    it."""
    _policy(monkeypatch, ANY)
    assert bm.market_is_publishable("total") is True
    assert bm.market_theory_ok("total") is False


# ===========================================================================
# 4. the served sentences say the same rule as the fields beside them
# ===========================================================================
@pytest.mark.parametrize("policy", [ANY, DISP, LEDGER, "typo"])
def test_the_policy_note_and_the_leg_fields_state_one_rule(policy, monkeypatch):
    _policy(monkeypatch, policy)
    table = _table(closed=("total",))
    pol = table["policy"]
    legs = be.slot_market_policy_legs(policy)
    assert pol["slot_market_policy"] == policy
    assert pol["dispersion_leg_bars"] is legs["dispersion_bars"]
    assert pol["ledger_leg_bars"] is legs["ledger_bars"]
    assert pol["registered_policy"] is legs["known"]
    # L14-08: the phrase that means "nothing bars" appears only when nothing
    # bars, in BOTH sentences.
    nothing_bars = not (legs["dispersion_bars"] or legs["ledger_bars"])
    assert ("may fill a slot" in pol["slot_market_policy_note"]) is nothing_bars
    assert ("may fill a slot" in table["note"]) is nothing_bars
    both_bar = legs["dispersion_bars"] and legs["ledger_bars"]
    assert ("must clear BOTH legs" in table["note"]) is both_bar


def test_the_two_older_sentences_are_reproduced_verbatim(monkeypatch):
    """A policy that did not move must not publish a sentence that did."""
    _policy(monkeypatch, ANY)
    assert _table()["policy"]["slot_market_policy_note"] == (
        "any: every priced market may fill a slot and reach the record; the "
        "dispersion and ledger legs below are disclosure on the row (owner "
        "decision 2026-09-05, docs/diamond-betting.md 7d)")
    _policy(monkeypatch, DISP)
    assert _table()["policy"]["slot_market_policy_note"] == (
        "dispersion_gated: a market must clear BOTH legs to fill a slot or "
        "reach the public record")


def test_the_table_publishes_the_new_value_as_an_override_not_a_bar(monkeypatch):
    """Under "ledger_gated" a dispersion-barred market with an OPEN ledger leg
    is publishable, and the reason sentence keeps both legs' own words."""
    _policy(monkeypatch, LEDGER)
    t = _table(closed=("total",))
    rl = t["markets"]["runline"]
    assert rl["publishable"] is True and rl["policy_override"] is True
    assert "ledger-gated slot policy" in rl["reason"]
    assert "dispersion correction is unserved" in rl["reason"]
    assert rl["dispersion_leg"]["publishable"] is False
    tot = t["markets"]["total"]
    assert tot["publishable"] is False and tot["policy_override"] is False
    assert tot["both_legs"] is True
    ml = t["markets"]["moneyline"]
    assert ml["publishable"] is True and ml["policy_override"] is False


@pytest.mark.parametrize("policy,expect", [
    (ANY, {"moneyline": True, "runline": True, "total": True}),
    (DISP, {"moneyline": True, "runline": False, "total": False}),
    (LEDGER, {"moneyline": True, "runline": True, "total": False}),
    ("typo", {"moneyline": True, "runline": False, "total": False}),
])
def test_publishable_follows_the_legs_that_bar(policy, expect, monkeypatch):
    """One table, four policies, the total ledger-closed. This is the whole
    decision in one grid."""
    _policy(monkeypatch, policy)
    t = _table(closed=("total",))
    for m, ok in expect.items():
        assert t["markets"][m]["publishable"] is ok, (policy, m)


def test_the_slot_meta_sentence_switches_with_the_policy(monkeypatch):
    _policy(monkeypatch, LEDGER)
    _slots, _why, meta = be.provisional_picks(_board(), odds_priceable=True)
    assert "whose ledger leg is open" in meta["markets_eligible"]
    assert meta["market_policy_legs"]["dispersion_bars"] is False
    _policy(monkeypatch, DISP)
    _slots, _why, meta = be.provisional_picks(_board(), odds_priceable=True)
    assert meta["markets_eligible"].startswith("moneyline while the dispersion")
    assert meta["market_policy_legs"] == {"dispersion_bars": True,
                                          "ledger_bars": True}


# ===========================================================================
# 5. the lock and the policy do not fight
# ===========================================================================
def test_a_locked_row_survives_a_policy_flip_and_the_flip_is_disclosed(
        tmp_path, monkeypatch):
    """R4-1a MEETS O15. A slot published under one policy is a claim that was
    made; a later build under a stricter policy does not un-make it, it serves
    it and says the current board would not select it. 7e-D writes the same
    rule for a pricer flip: "a slate whose slots were already locked keeps
    them"."""
    _policy(monkeypatch, ANY)
    row = {"game_pk": 1, "matchup": "AAA at BBB", "market": "total",
           "side": "over", "point": 8.5, "label": "Over 8.5", "book": "testbook",
           "odds": -110, "edge": 0.40, "model_prob": 0.60,
           "start": "2026-09-17T23:05:00Z", "slot": "pick_of_the_day",
           "min_edge_used": 0.06, "provisional": True}
    meta = {"slots": {s: {"slot": s, "present": True, "reason": "the rule"}
                      for s in be.SLOT_LABELS}}
    be.apply_slot_lock({"pick_of_the_day": dict(row),
                        "longshot_of_the_day": None},
                       meta, slate_date=DAY, pick_reason="the rule",
                       root=tmp_path)

    # THE FLIP: the total's ledger leg closes and the policy now bars on it,
    # so this build would select nothing for the slot.
    _policy(monkeypatch, LEDGER)
    slots = {"pick_of_the_day": None, "longshot_of_the_day": None}
    meta2 = {"slots": {s: {"slot": s, "present": False, "reason": "no side"}
                       for s in be.SLOT_LABELS}}
    _reason, state = be.apply_slot_lock(slots, meta2, slate_date=DAY,
                                        pick_reason="no side",
                                        root=tmp_path)
    served = slots["pick_of_the_day"]
    assert state["served_from_lock"] == ["pick_of_the_day"]
    assert served["label"] == "Over 8.5" and served["odds"] == -110
    since = served["since_published"]
    assert since["status"] == "no_longer_selected"
    assert "published" in (served.get("caveat") or "").lower()


# ===========================================================================
# 5b. the census carries both of its denominators
# ===========================================================================
@pytest.mark.parametrize("policy,cleared,barred", [
    (ANY, 3, 0),
    (LEDGER, 2, 1),
    (DISP, 1, 2),
])
def test_the_census_publishes_the_count_before_the_policy_too(
        policy, cleared, barred, monkeypatch):
    """TWO POPULATIONS, TWO NAMES. `n_floor_clearing_sides` is
    policy-filtered at seam 1, and the page renders it under the words "cleared
    the floor" beside its own unfiltered count of priced sides. Under either
    gated value that label is wrong about the number under it.

    The seam counts the barred sides AFTER the floor test rather than skipping
    the market before it, so the two counts share a denominator and their
    difference is exactly what the policy took out.

    MUTATION: skip the market before the floor test again.
    `n_floor_clearing_sides_before_policy` then equals the filtered count under
    every value."""
    _policy(monkeypatch, policy)
    stats: dict = {}
    cands = be._floor_clearing_sides(_board(), 0.06, stats=stats,
                                     ledger_closed=frozenset({"total"}))
    assert len(cands) == cleared
    assert stats["n_policy_barred_sides"] == barred
    # And the pair reaches the payload block the census renders.
    monkeypatch.setattr(be, "ledger_closed_markets",
                        lambda *a, **k: frozenset({"total"}))
    _, _, meta = be.provisional_picks(_board(), odds_priceable=True, evald={})
    assert meta["n_floor_clearing_sides"] == cleared
    assert meta["n_floor_clearing_sides_before_policy"] == cleared + barred
    # The unfiltered count does not move with the policy: that is the point.
    assert meta["n_floor_clearing_sides_before_policy"] == 3


# ===========================================================================
# 6. the registration and the code agree
# ===========================================================================
@pytest.mark.skipif(not DOC.exists(), reason="the runbook is not in this tree")
def test_the_runbook_registers_the_value_the_code_implements():
    """A policy value is a registered thing. 7d is where the other two are
    registered and it is where this one has to be."""
    doc = DOC.read_text(encoding="utf-8", errors="replace")
    for value in be.SLOT_MARKET_POLICIES:
        assert f'SLOT_MARKET_POLICY = "{value}"' in doc, value
    assert "slot_market_policy_legs" in doc
    assert "ledger_gated" in doc
