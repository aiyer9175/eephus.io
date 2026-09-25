# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""CLV grading lives BESIDE the record, never inside it.

WHY A SIDECAR. The closing line does not exist when a pick is posted; it lands
hours later. Writing it back into the published row would be exactly the edit
`check_append_only` exists to forbid, and carving out an exception for "only the
CLV fields" would put a hole in the single guarantee that makes a public betting
record worth reading at all. So the record stays immutable and the grade lives in
data/betting_clv.json, keyed by bet_id.

`grade_clv` has existed since the module was written and nothing ever called it.
This is the wiring, and these are its tests.

WHAT THESE PIN
  1. Grading never mutates the record, and the record still passes its own
     append-only check afterwards.
  2. A pick is graded against the BOOK IT WAS TAKEN AT, not the best close
     across books. Grading a DraftKings bet against FanDuel's close invents
     value the bettor never had access to.
  3. A missing close snapshot produces an UNGRADED ENTRY WITH A REASON, not a
     missing row. A pick absent from this file would read as "no bet that day",
     which is the empty-but-valid failure this codebase keeps getting bitten by.
  4. Rates over an empty set are None, not 0.0.
  5. A total is only graded against the same NUMBER. A different line is a
     different bet.
  6. Grading is idempotent.
  7. A SPREAD is graded against the same number too, and can be graded at all.
     Until 2026-08-09 it could not: the board stamps `market` as
     moneyline|runline|total and this grader branches on h2h|spreads|totals, so
     a runline row matched no branch and returned "no closing price" forever.
     The spreads branch also never compared the POINT though the totals branch
     did, so a +1.5 pick would have graded against a -1.5 close - two opposite
     bets, roughly +130 against roughly -160.
  8. Machine fields win and the label is never parsed; a LEGACY label-only row
     still grades exactly as it did.
  9. record_summary joins the sidecars by bet_id. It read `r["beat_close"]` off
     the record, which by construction can never carry it (the record is
     byte-immutable and the close lands hours later), so `n_clv_graded` was 0
     forever and the page printed "not graded yet" over a graded record.
 10. The record's SOURCE OF TRUTH is the untracked append-only JSONL, and the
     chain hash proves today's record extends the one a reader archived.
"""
from __future__ import annotations

import json

import pytest

be = pytest.importorskip("betting_export")
bi = pytest.importorskip("betting_ingest")


DAY = "2026-08-01"

RECORD = [
    {"bet_id": "aaaa1111bbbb2222", "posted_at": f"{DAY}T15:02:00+00:00",
     "slate_date": DAY, "market": "h2h", "selection": "NYM",
     "book": "draftkings", "odds_at_post": -140, "stake_units": 1.0,
     "result": "won"},
    {"bet_id": "cccc3333dddd4444", "posted_at": f"{DAY}T15:01:00+00:00",
     "slate_date": DAY, "market": "totals", "selection": "Under 8.5",
     "book": "fanduel", "odds_at_post": -105, "stake_units": 1.0,
     "result": "lost"},
]

RAW = [{
    "id": "evt1", "commence_time": f"{DAY}T23:10:00Z",
    "home_team": "New York Mets", "away_team": "Atlanta Braves",
    "bookmakers": [
        {"key": "draftkings", "title": "DraftKings",
         "last_update": f"{DAY}T22:55:00Z",
         "markets": [
             {"key": "h2h", "outcomes": [
                 {"name": "New York Mets", "price": -160},
                 {"name": "Atlanta Braves", "price": 140}]},
             {"key": "totals", "outcomes": [
                 {"name": "Over", "price": -110, "point": 8.5},
                 {"name": "Under", "price": -110, "point": 8.5}]}]},
        {"key": "fanduel", "title": "FanDuel",
         "last_update": f"{DAY}T22:56:00Z",
         "markets": [
             {"key": "h2h", "outcomes": [
                 {"name": "New York Mets", "price": -120},
                 {"name": "Atlanta Braves", "price": 100}]},
             {"key": "totals", "outcomes": [
                 {"name": "Over", "price": -125, "point": 8.5},
                 {"name": "Under", "price": -115, "point": 8.5}]}]},
    ],
}]


# A SECOND EVENT CARRYING SPREADS, on both sides of the same number. The close
# posts home -1.5 at -155 and away +1.5 at +130, which is the whole point: a
# grader that ignores the point can read one as the other and invent 285 points
# of price out of nothing.
RAW_SPREADS = [{
    "id": "evt2", "commence_time": f"{DAY}T23:40:00Z",
    "home_team": "Tampa Bay Rays", "away_team": "Boston Red Sox",
    "bookmakers": [
        {"key": "draftkings", "title": "DraftKings",
         "last_update": f"{DAY}T23:30:00Z",
         "markets": [
             {"key": "h2h", "outcomes": [
                 {"name": "Tampa Bay Rays", "price": -135},
                 {"name": "Boston Red Sox", "price": 115}]},
             {"key": "spreads", "outcomes": [
                 {"name": "Tampa Bay Rays", "price": -155, "point": -1.5},
                 {"name": "Boston Red Sox", "price": 130, "point": 1.5}]}]},
    ],
}]


def _spread_row(**over):
    """A record row for the Rays +1.5 - the side the OTHER team's number would
    grade backwards - with machine fields."""
    row = {"bet_id": "sprd0000sprd0000", "posted_at": f"{DAY}T15:00:00+00:00",
           "slate_date": DAY, "market": "spreads", "board_market": "runline",
           "side": "home", "point": -1.5, "selection": "TBR -1.5",
           "book": "draftkings", "odds_at_post": -140, "stake_units": 1.0}
    row.update(over)
    return row


@pytest.fixture
def with_close(monkeypatch):
    monkeypatch.setattr(bi, "closing_snapshot",
                        lambda day: {"events": RAW} if day == DAY else None)


@pytest.fixture
def with_spread_close(monkeypatch):
    monkeypatch.setattr(bi, "closing_snapshot",
                        lambda day: {"events": RAW_SPREADS} if day == DAY else None)


@pytest.fixture
def without_close(monkeypatch):
    monkeypatch.setattr(bi, "closing_snapshot", lambda day: None)


def _by_id(payload):
    return {p["bet_id"]: p for p in payload["picks"]}


def test_grading_does_not_touch_the_record(with_close, tmp_path):
    """The record is the evidence. Grading is derived from it and may never
    write to it."""
    before = json.dumps(RECORD, sort_keys=True)
    be.grade_record_clv(rows=RECORD, write=False)
    assert json.dumps(RECORD, sort_keys=True) == before
    be.check_append_only(RECORD, RECORD)          # still append-only clean


def test_a_pick_is_graded_at_the_book_it_was_taken_at(with_close):
    """THE MEASUREMENT. The Mets bet was posted at -140 on DraftKings, which
    closed -160 there and -120 on FanDuel. Grading against FanDuel would call a
    winner a loser."""
    g = _by_id(be.grade_record_clv(rows=RECORD, write=False))["aaaa1111bbbb2222"]
    assert g["graded"] is True
    assert g["odds_at_close"] == -160, (
        "the close must come from the pick's own book; -120 here means it "
        "grabbed FanDuel and invented value the bettor could not have had")
    assert g["beat_close"] is True
    assert g["clv_pct"] > 0


def test_a_total_is_graded_at_its_own_number(with_close):
    g = _by_id(be.grade_record_clv(rows=RECORD, write=False))["cccc3333dddd4444"]
    assert g["graded"] is True
    assert g["odds_at_close"] == -115, "Under 8.5 on FanDuel closed -115"


def test_a_total_on_a_different_line_is_not_graded(with_close):
    """A moved total is a different bet. Grading 9.5 against the 8.5 close would
    silently compare two different wagers."""
    row = dict(RECORD[1], bet_id="dddd", selection="Under 9.5")
    g = _by_id(be.grade_record_clv(rows=[row], write=False))["dddd"]
    assert g["graded"] is False
    assert "no closing" in g["reason"]


def test_a_missing_close_snapshot_is_named_not_skipped(without_close):
    """THE SILENT-EMPTY GUARD. A pick that vanishes from this file reads as a
    day with no bets."""
    payload = be.grade_record_clv(rows=RECORD, write=False)
    assert payload["n_graded"] == 0
    assert payload["n_ungraded"] == 2, "both picks must still appear"
    for g in payload["picks"]:
        assert g["graded"] is False
        assert "close job did not fire" in g["reason"]
    assert "no closing snapshot" in payload["ungraded_reasons"]


def test_rates_over_an_empty_set_are_none_not_zero(without_close):
    """A 0% beat-close rate over zero graded bets is a lie that looks like a
    measurement."""
    payload = be.grade_record_clv(rows=RECORD, write=False)
    assert payload["beat_close_rate"] is None
    assert payload["avg_clv_pct"] is None


def test_an_empty_record_grades_to_an_empty_report(with_close):
    payload = be.grade_record_clv(rows=[], write=False)
    assert payload["n_rows"] == 0 and payload["picks"] == []
    assert payload["beat_close_rate"] is None


def test_grading_is_idempotent(with_close):
    a = be.grade_record_clv(rows=RECORD, write=False)
    b = be.grade_record_clv(rows=RECORD, write=False)
    assert a["picks"] == b["picks"]


def test_the_sidecar_writes_where_the_page_can_read_it(with_close, tmp_path):
    out = tmp_path / "betting_clv.json"
    be.grade_record_clv(rows=RECORD, write=True, path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["n_graded"] == 2
    assert payload["source"].startswith("derived from")


# ---- D8: spreads could never be graded at all ------------------------------
def test_the_two_market_vocabularies_map_to_each_other():
    """The board says runline, the odds feed says spreads, and nothing
    translated. That mismatch is why no spread ever graded."""
    assert be.feed_market({"market": "runline"}) == "spreads"
    assert be.feed_market({"market": "spreads"}) == "spreads"
    assert be.board_market({"market": "spreads"}) == "runline"
    assert be.board_market({"market": "runline"}) == "runline"
    assert be.feed_market({"market": "moneyline"}) == "h2h"
    assert be.feed_market({"market": "total"}) == "totals"
    assert be.feed_market({"market": "parlay"}) is None


def test_a_board_vocabulary_runline_row_still_grades(with_spread_close):
    """A row stamped `runline` (what the board writes) must reach the spreads
    branch. Before the map it matched nothing and read as a missing price."""
    row = _spread_row(market="runline")
    g = _by_id(be.grade_record_clv(rows=[row], write=False))["sprd0000sprd0000"]
    assert g["graded"] is True
    assert g["odds_at_close"] == -155


def test_a_spread_grades_against_its_own_number(with_spread_close):
    """TBR -1.5 taken at -140 closed -155 at the same book on the same number."""
    g = _by_id(be.grade_record_clv(rows=[_spread_row()], write=False))["sprd0000sprd0000"]
    assert g["graded"] is True
    assert g["odds_at_close"] == -155
    assert g["beat_close"] is True


def test_a_plus_one_five_pick_grades_against_the_plus_one_five_close(with_spread_close):
    """THE MEASUREMENT. The +1.5 side closed +130. Nothing about the -1.5 side
    may reach this row."""
    row = _spread_row(bet_id="plus1500plus1500", side="away", point=1.5,
                      selection="BOS +1.5", odds_at_post=120)
    g = _by_id(be.grade_record_clv(rows=[row], write=False))["plus1500plus1500"]
    assert g["graded"] is True
    assert g["odds_at_close"] == 130, (
        "a +1.5 pick must grade against the +1.5 close; -155 here means it took "
        "the -1.5 side and compared two opposite bets")
    assert g["beat_close"] is False, "backing +120 into a +130 close is negative CLV"


def test_a_plus_one_five_pick_does_not_grade_against_a_minus_one_five_close(monkeypatch):
    """A close that moved off the number is NOT this bet. The book must read as
    having posted no closing price for it, not as having posted the other side."""
    moved = json.loads(json.dumps(RAW_SPREADS))
    for o in moved[0]["bookmakers"][0]["markets"][1]["outcomes"]:
        o["point"] = -1.5 if o["name"] == "Boston Red Sox" else 1.5
    monkeypatch.setattr(bi, "closing_snapshot",
                        lambda day: {"events": moved} if day == DAY else None)
    row = _spread_row(bet_id="plus1500plus1500", side="away", point=1.5,
                      selection="BOS +1.5", odds_at_post=120)
    g = _by_id(be.grade_record_clv(rows=[row], write=False))["plus1500plus1500"]
    assert g["graded"] is False
    assert "no closing" in g["reason"]


def test_the_selection_label_is_never_parsed_when_side_is_present(with_spread_close):
    """`selection` is DISPLAY copy. A row whose label is nonsense but whose
    machine fields are right still grades, which is the guarantee that stops the
    next label change from silently breaking CLV."""
    row = _spread_row(selection="Rays to cover, per the desk")
    g = _by_id(be.grade_record_clv(rows=[row], write=False))["sprd0000sprd0000"]
    assert g["graded"] is True and g["odds_at_close"] == -155


def test_a_legacy_label_only_h2h_row_still_grades(with_close):
    """The fallback exists for rows published before the machine fields did.
    Removing it would silently un-grade every row already on the record."""
    row = {k: v for k, v in RECORD[0].items()}
    assert "side" not in row, "the legacy fixture must carry no machine side"
    g = _by_id(be.grade_record_clv(rows=[row], write=False))["aaaa1111bbbb2222"]
    assert g["graded"] is True and g["odds_at_close"] == -160


def test_a_machine_side_that_is_not_a_side_is_named_not_guessed(with_spread_close):
    row = _spread_row(side="tbr")
    g = _by_id(be.grade_record_clv(rows=[row], write=False))["sprd0000sprd0000"]
    assert g["graded"] is False
    assert "home/away" in g["reason"]


# ---- D10: the summary read fields the record can never carry ---------------
CLV_SIDECAR = {
    "aaaa1111bbbb2222": {"bet_id": "aaaa1111bbbb2222", "graded": True,
                         "beat_close": True, "clv_pct": 8.929, "odds_at_close": -160},
    "cccc3333dddd4444": {"bet_id": "cccc3333dddd4444", "graded": True,
                         "beat_close": False, "clv_pct": -4.0, "odds_at_close": -95},
}
SETTLEMENT_SIDECAR = {
    "aaaa1111bbbb2222": {"bet_id": "aaaa1111bbbb2222", "settled": True, "result": "won"},
    "cccc3333dddd4444": {"bet_id": "cccc3333dddd4444", "settled": True, "result": "lost"},
}
#: The record as it is actually written: a CLAIM, with no result, no beat_close
#: and no clv_pct on it. Those arrive hours later and live in the sidecars.
IMMUTABLE_RECORD = [
    {k: v for k, v in r.items()
     if k not in ("result", "settled_at", "odds_at_close", "beat_close", "clv_pct")}
    for r in RECORD
]


def test_record_summary_reports_nothing_graded_without_the_sidecars():
    """The defect, pinned. A record row carries no CLV field by construction, so
    reading them off the record counts zero however many are graded."""
    r = be.record_summary(IMMUTABLE_RECORD, clv={}, settlement={})
    assert r["n_clv_graded"] == 0
    assert r["n_settled"] == 0 and r["n_open"] == 2


def test_record_summary_joins_the_clv_sidecar_by_bet_id():
    r = be.record_summary(IMMUTABLE_RECORD, clv=CLV_SIDECAR, settlement={})
    assert r["n_clv_graded"] == 2, "both picks are graded in the sidecar"
    assert r["beat_close_rate"] == 0.5
    assert r["avg_clv_pct"] == pytest.approx(2.4645, abs=1e-3)


def test_record_summary_joins_the_settlement_sidecar_by_bet_id():
    """The -140 winner returns 0.7143u and the -105 loser costs 1u, so a 1-1
    record is -0.2857u on 2u risked. None of that is on the record itself."""
    r = be.record_summary(IMMUTABLE_RECORD, clv={}, settlement=SETTLEMENT_SIDECAR)
    assert (r["won"], r["lost"], r["n_settled"], r["n_open"]) == (1, 1, 2, 0)
    assert r["net_units"] == pytest.approx(-0.286, abs=0.002)
    assert r["roi_pct"] == pytest.approx(-14.29, abs=0.02)


def test_the_join_never_writes_back_into_the_record():
    before = json.dumps(IMMUTABLE_RECORD, sort_keys=True)
    be.record_summary(IMMUTABLE_RECORD, clv=CLV_SIDECAR, settlement=SETTLEMENT_SIDECAR)
    assert json.dumps(IMMUTABLE_RECORD, sort_keys=True) == before
    be.check_append_only(IMMUTABLE_RECORD, IMMUTABLE_RECORD)


# ---- C1: the storage seam and the chain hash -------------------------------
def test_the_chain_hash_is_deterministic_and_order_blind():
    reordered = [dict(reversed(list(r.items()))) for r in RECORD]
    assert be.chain_sha(RECORD) == be.chain_sha(reordered)
    assert be.chain_sha([]) == be.CHAIN_GENESIS
    assert be.chain_sha(RECORD) != be.chain_sha(RECORD[:1])


def test_an_append_extends_the_chain_and_a_rewrite_does_not():
    """What a READER can check. check_append_only protects a write inside this
    process; the chain hash is the only thing that lets somebody who archived
    yesterday's file prove today's is the same record, longer."""
    yesterday = be.chain_sha(RECORD[:1])
    assert be.chain_extends(yesterday, RECORD) is True
    edited = [dict(RECORD[0], odds_at_post=-135)] + RECORD[1:]
    assert be.chain_extends(yesterday, edited) is False
    assert be.chain_extends(be.CHAIN_GENESIS, RECORD) is True
    assert be.chain_extends(None, RECORD) is True


def test_the_jsonl_log_round_trips_and_chains(tmp_path):
    # The appended row is a MONEYLINE here on purpose. RECORD[1] is a total,
    # and since 2026-08-16 append_record canonicalizes the feed market name
    # and refuses dispersion-excluded markets at the funnel (the seam-2
    # vocabulary hole fix), so a totals row can no longer land while the
    # correction is unserved. The exclusion itself is pinned by
    # test_betting_dispersion_exclusion.py; this test is about the CHAIN.
    ml_row = dict(RECORD[1], market="h2h", selection="ATL")
    chained = [RECORD[0], ml_row]
    p = tmp_path / "record.jsonl"
    be.write_record(chained[:1], path=p)
    be.append_record([ml_row], path=p)
    # Since 2026-09-05 the funnel stamps the two legs and the slot policy on every
    # kept row (dispersion_sensitive / evidence_closed / market_policy, docs 7d);
    # the chain test is about the rows' identity, so compare with those stripped.
    _POLICY_STAMPS = ("dispersion_sensitive", "evidence_closed", "market_policy")
    loaded = [{k: v for k, v in r.items() if k not in _POLICY_STAMPS} for r in be.load_record(p)]
    assert loaded == chained
    lines = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert [row["seq"] for row in lines] == [0, 1]
    assert lines[0]["prev_sha"] == be.CHAIN_GENESIS
    assert lines[1]["prev_sha"] == lines[0]["chain_sha"]
    # The chain covers the rows AS STORED (with the policy stamps), so the
    # expectation is computed over the loaded rows, not the pre-stamp input.
    assert lines[1]["chain_sha"] == be.chain_sha(be.load_record(p))


def test_an_edited_log_line_raises_rather_than_reading_back_clean(tmp_path):
    """A rewrite in place is the one thing an append-only record may never
    survive silently. The recorded chain hash no longer matches the rows."""
    p = tmp_path / "record.jsonl"
    be.write_record(RECORD, path=p)
    lines = p.read_text(encoding="utf-8").splitlines()
    env = json.loads(lines[0])
    env["row"]["odds_at_post"] = -135
    lines[0] = json.dumps(env)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(be.RecordImmutabilityError):
        be.load_record(p)


def test_the_log_still_refuses_a_shrink_or_an_edit(tmp_path):
    p = tmp_path / "record.jsonl"
    be.write_record(RECORD, path=p)
    with pytest.raises(be.RecordImmutabilityError):
        be.write_record(RECORD[:1], path=p)
    with pytest.raises(be.RecordImmutabilityError):
        be.write_record([dict(RECORD[0], result="lost"), RECORD[1]], path=p)
    assert be.load_record(p) == RECORD


def test_the_derived_json_is_a_render_of_the_log_not_a_second_record(tmp_path):
    """data/betting_record.json is git-tracked and the nightly reverts it. It is
    re-rendered every build from the log, which is why losing it costs nothing
    and why nothing may ever read it as authoritative when a log exists."""
    out = tmp_path / "betting_record.json"
    be.render_record(RECORD, path=out)
    assert json.loads(out.read_text(encoding="utf-8")) == RECORD


# ---- the publish blockers, pre-registered ----------------------------------
def test_every_publish_blocker_is_pre_registered_and_shaped():
    bl = be.record_publish_blockers(payload={"slate_date": DAY, "status": {}},
                                    rows=[], evald={}, health={"n_slates": 0},
                                    settlement={})
    ids = [b["id"] for b in bl]
    # THE LIST MOVES WITH `SERVE_CLV` (owner 2026-09-07) and is derived from it
    # here rather than hardcoded twice, so a future flip cannot leave this test
    # asserting a shape the module no longer builds.
    expected = (["close_snapshot"] if be.SERVE_CLV else ["publish_armed"]) + [
        "odds_slate", "dispersion_gate", "record_storage", "settlement_current"]
    assert ids == expected
    for b in bl:
        assert set(("id", "open", "need", "have", "reason")) <= set(b)
        assert isinstance(b["open"], bool)
    assert be.record_publish_ok(bl) is False


def test_publishing_needs_every_blocker_open():
    assert be.record_publish_ok([{"open": True}, {"open": True}]) is True
    assert be.record_publish_ok([{"open": True}, {"open": False}]) is False
    # An EMPTY list is not a pass. A blocker list that failed to build must not
    # read as "nothing is blocking".
    assert be.record_publish_ok([]) is False


def test_a_missing_close_snapshot_blocks_publication(without_close):
    """Unchanged in substance and skipped while CLV is retired: with SERVE_CLV
    False the module builds no close_snapshot blocker at all, so there is
    nothing to assert. Flipping the switch back re-arms this test."""
    if not be.SERVE_CLV:
        return
    bl = be.record_publish_blockers(payload={"slate_date": DAY, "status": {}},
                                    rows=[], evald={}, health={"n_slates": 0,
                                                               "diagnosis": "x"},
                                    settlement={})
    close = next(b for b in bl if b["id"] == "close_snapshot")
    assert close["open"] is False
    assert "CLV-graded" in close["reason"]


def test_retiring_clv_does_not_silently_arm_the_public_record(monkeypatch):
    """THE DEFECT THIS PINS, which actually happened on 2026-09-07.

    Retiring `close_snapshot` left the pre-registered list four-for-four open
    and the very next build appended the first row the public record had ever
    held. Nobody decided that; it fell out of removing a DIFFERENT gate. A
    pre-registered list that arms itself when one of its own entries is
    withdrawn is not pre-registered, so the withdrawal is represented by an
    explicit decision entry instead of by a gap.

    ARMED 2026-09-25 by the owner, in writing. The pin keeps both halves: the
    flag is the owner's literal decision (never derived from the other
    blockers), and with the flag off the list still refuses and says why.
    """
    if be.SERVE_CLV:
        return
    kw = dict(payload={"slate_date": DAY, "status": {}}, rows=[], evald={},
              health={"n_slates": 0}, settlement={})
    bl = be.record_publish_blockers(**kw)
    armed = next(b for b in bl if b["id"] == "publish_armed")
    assert armed["open"] is be.RECORD_PUBLISH_ARMED
    assert be.RECORD_PUBLISH_ARMED is True, (
        "the owner armed the record on 2026-09-25; disarming it is also an owner call")
    assert "owner decision" in armed["reason"]
    # the defect this pins stays pinned: with the flag off, nothing arms it
    monkeypatch.setattr(be, "RECORD_PUBLISH_ARMED", False)
    bl = be.record_publish_blockers(**kw)
    armed = next(b for b in bl if b["id"] == "publish_armed")
    assert armed["open"] is False
    assert be.record_publish_ok(bl) is False
    # and the reason says WHY, naming the retirement rather than shrugging
    assert "close_snapshot" in armed["reason"]
    assert "realized results" in armed["reason"]


def test_the_provisional_label_reads_its_count_from_the_artifact():
    """N is never hardcoded. A label carrying a frozen count is a false claim
    about how much evidence exists the moment the next vintage lands."""
    evald = {"vintage": {"n_graded": 211, "min_graded_games_for_min_edge": 600}}
    txt = be.provisional_record_label(evald, min_edge=0.06, provisional=True)
    assert "211 of the 600 games the honest backtest needs are graded" in txt
    # "selection", not "pick": Model Watch language (owner decision 2026-08-16)
    # de-picked every prose surface while the gates are closed.
    assert txt.startswith("Provisional. This selection clears a 6.0% floor that was "
                          "chosen as policy, not measured.")
    assert txt.endswith("Recorded before the result.")
    moved = be.provisional_record_label(
        {"vintage": {"n_graded": 212, "min_graded_games_for_min_edge": 600}},
        min_edge=0.06, provisional=True)
    assert "212 of the 600" in moved
    assert be.provisional_record_label(evald, min_edge=0.06, provisional=False) is None


def test_a_missing_artifact_says_so_rather_than_printing_a_number():
    txt = be.provisional_record_label({}, min_edge=0.06, provisional=True)
    assert "does not report how many games" in txt


def test_a_record_row_carries_machine_fields_and_a_display_label():
    slot = {"market": "runline", "side": "away", "point": 1.5, "label": "BOS +1.5",
            "game_pk": 777, "book": "draftkings", "odds": 120, "decimal": 2.2,
            "provisional": True, "min_edge_used": 0.06, "slot": "pick_of_the_day"}
    row = be.record_row(slot, slate_date=DAY, evald={})
    assert row["market"] == "spreads" and row["board_market"] == "runline"
    assert row["side"] == "away" and row["point"] == 1.5
    assert row["selection"] == "BOS +1.5"
    assert row["stake_units"] == be.STAKE_UNITS
    # NO result, NO clv: those arrive hours later and live in the sidecars. A
    # placeholder here invites the in-place edit the record forbids.
    assert "result" not in row and "beat_close" not in row and "clv_pct" not in row
    assert row["label"].startswith("Provisional.")
    # Identity, not price: a moved line may not produce a second row for the
    # same side of the same game.
    assert row["bet_id"] == be.record_row(dict(slot, odds=145),
                                          slate_date=DAY, evald={})["bet_id"]
