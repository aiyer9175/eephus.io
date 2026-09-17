# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The min_edge gate's tripwires: what the third gate is allowed to sweep, and
what its interval is allowed to claim.

TWO FINDINGS, ONE FILE.

L14-05, THE SAMPLER. `min_edge_gate` swept `graded_bets_by_tag`, a sampler
whose own module calls itself a defect: a tag conditions on the selection rule
and nothing else, so one tag holds three markets. Measured on the live ledger
2026-09-06, those three markets returned -27.4% (moneyline), -3.2% (runline)
and -14.6% (total), and on 2026-09-17 the `board_all` tag held 292 settled rows
split 55 / 99 / 138 across them. A threshold fitted to that union is the
pooling defect of docs/diamond-betting.md section 7a re-entering one level down
through a tag name. The per-market cells shipped on 2026-09-06 with no caller
at the gate, so this was an ORDERING accident waiting on a date: gates 1 and 2
are both open (618 vintage-graded games, t 2.298), which leaves gate 3 as the
only thing between a market-pooled sample and a published floor.

L14-09, THE INTERVAL. `sweep_min_edge` divided the profit variance by n and
escaped to `se = 0` when the sample had no spread, so the lower bound was
slightly optimistic always and perfectly certain in the degenerate case. Both
errors point the same way: toward opening the gate.

THE REPAIR CUTS BOTH WAYS, which is the third thing pinned here. Splitting one
pooled tag into three sub-ledgers makes each of them EASIER to clear than their
union was, and the published `min_edge` is a single scalar every market on the
board is filtered against. So the sub-ledger split had to arrive with a
coverage rule, or a 110-row moneyline cell clearing alone would license total
and runline picks on no evidence at all. A repair that opens a gate is not a
repair.

WHAT IS PINNED
  1. The gate sweeps (market, tag) sub-ledgers. A tag is counted, never swept,
     and its census carries the era the count was taken under.
  2. Handing the gate a cross-market sampler CLOSES gate 3 rather than setting
     a floor, and says which check failed. This is the tripwire: it fails the
     day someone points the gate back at the per-tag sampler.
  3. A cell holding rows its market cannot account for closes gate 3 too, which
     is the check that survives a sampler swapped underneath the gate; and a
     census that could not be READ is a third, separately named failure rather
     than an accusation against the cells.
  4. When the tripwire is red the gate publishes NO row count as evidence in
     hand, because the public blocker sentence prints that number.
  5. The gate can still OPEN on honest sub-ledgers. A gate that can only close
     is a constant with extra steps.
  6. The floor is the strictest cleared sub-ledger, and only once every market
     with settled rows has cleared one of its own.
  7. The era the gate names is the era the cells were read under, carried out
     of the same call rather than restated from a constant.
  8. The variance is a sample variance, zero variance is a refusal that says
     which constant it refused, and the looks are counted across every cell.

NOTHING HERE PRICES ANYTHING. These are gates and guards: no moneyline,
runline or total price moves, so MODEL_VERSION does not move either.
"""
from __future__ import annotations

import math

import pytest

bm = pytest.importorskip("betting_model")
bs = pytest.importorskip("betting_shadow")
be = pytest.importorskip("betting_export")

OPEN_VINTAGE = {"n_graded": 10_000,
                "skill_vs_home_base": {"t": 3.0, "beats_baseline_95": True}}


def _winners(n=240, losers=160, edge=0.06, decimal=2.0):
    return ([{"edge": edge, "decimal": decimal, "won": True}] * n
            + [{"edge": edge, "decimal": decimal, "won": False}] * losers)


def _gate3(gate):
    return next(g for g in gate["gates"] if g["id"] == "graded_price_history")


def _census(counts: dict) -> dict:
    """{tag: {market: n}} written out in the census's own shape.

    The real census reports `n_in_era` and `n_all_eras` separately, because the
    cells are filtered to one budget era and the whole history is not. A test
    that wants the two to agree says so by passing one number."""
    return {t: {m: {"n_in_era": n, "n_all_eras": n, "era_split": False}
                for m, n in ms.items()}
            for t, ms in counts.items()}


def _patch(monkeypatch, cells, counts, *, census=..., era=None):
    """Point the gate at a made-up ledger: cells, census and era together.

    They travel together because the gate reads them together, out of one
    call. `census=None` is the ledger-unreadable case, which is a different
    fact from a census with nothing in it."""
    span = _census(counts) if census is ... else census
    read = {"available": span is not None,
            "era": era or bs.PER_MARKET_CAP_ERA,
            "split_date": bs.BUDGET_SPLIT_DATE,
            "cells": cells, "census": span,
            "why": "fixture"}
    monkeypatch.setattr(bm, "_shadow_cells_for_the_gate", lambda: read)
    monkeypatch.setattr(bm, "_shadow_graded_bets",
                        lambda: [r for rws in cells.values() for r in rws])


# ---------------------------------------------------------------------------
# the ledger fixture: a real recorded slate, settled, so the census is checked
# against rows this module wrote rather than rows a test invented.
# ---------------------------------------------------------------------------
@pytest.fixture
def led_rows(tmp_path):
    path = tmp_path / "shadow.json"
    games = [{"game_pk": 700, "home": {"org": "PHI"}, "away": {"org": "WSN"},
              "total": {"line": 9.0, "sides": [
                  {"side": "over", "label": "Over 9", "point": 9.0, "edge": 0.20,
                   "odds": -110, "decimal": 1.91, "book": "dk",
                   "ev_per_unit": 0.9}]}},
             {"game_pk": 800, "home": {"org": "NYM"}, "away": {"org": "ATL"},
              "runline": [{"side": "away", "label": "ATL +1.5", "point": 1.5,
                           "edge": 0.10, "odds": -120, "decimal": 1.83,
                           "book": "dk", "ev_per_unit": 0.20}]},
             {"game_pk": 801, "home": {"org": "LAD"}, "away": {"org": "SDP"},
              "moneyline": [{"side": "away", "label": "SDP", "edge": 0.09,
                             "odds": 150, "decimal": 2.5, "book": "dk",
                             "ev_per_unit": 0.10}]}]
    bs.record_slate({"slate_date": "2026-09-08", "status": {"odds_feed": "ok"},
                     "team_bets": games}, min_edge=0.05, path=path,
                    include_board_all=True)
    bs.settle(games=[{"game_pk": pk, "home_runs": 9, "away_runs": 6}
                     for pk in (700, 800, 801)], path=path)
    return path


# ---------------------------------------------------------------------------
# 1. the sampler (L14-05)
# ---------------------------------------------------------------------------
def test_the_gate_sweeps_sub_ledgers_and_counts_tags(monkeypatch):
    """A tag is a selection rule, not a sub-ledger. The per-tag table survives
    as a CENSUS - how many rows, in which era, across how many markets - and
    the census is exactly the fact that disqualifies it from setting anything."""
    _patch(monkeypatch, {("moneyline", "board_all"): _winners(60, 40),
                         ("total", "board_all"): _winners(60, 40)},
           {"board_all": {"moneyline": 100, "total": 100}})
    g3 = _gate3(bm.min_edge_gate(OPEN_VINTAGE))
    assert set(g3["by_market_tag"]) == {"moneyline", "total"}
    tag = g3["by_tag"]["board_all"]
    assert tag["n_markets"] == 2
    assert tag["swept"] is False
    assert tag["may_set_a_threshold"] is False
    assert "mixture nobody bet" in tag["reason"]


def test_a_single_market_tags_census_says_its_cell_was_swept(monkeypatch):
    """The census booleans are DERIVED, not asserted. A tag holding one market
    is one sub-ledger, its cell is one of the ones the sweep ran on, and a
    hardcoded `swept: False` beside a reason saying the opposite is a false
    statement published in data/betting_model_eval.json."""
    cells = {("moneyline", "longshot"): _winners(60, 40),
             ("moneyline", "board_all"): _winners(60, 40)}
    _patch(monkeypatch, cells,
           {"longshot": {"moneyline": 100}, "board_all": {"moneyline": 100}})
    g3 = _gate3(bm.min_edge_gate(OPEN_VINTAGE))
    assert g3["by_tag"]["longshot"]["swept"] is True
    assert g3["by_tag"]["longshot"]["may_set_a_threshold"] is True
    assert "IS\none sub-ledger" in g3["by_tag"]["longshot"]["reason"].replace(
        " one sub-ledger", "\none sub-ledger")


def test_the_census_and_the_cells_are_counted_in_the_same_era(monkeypatch):
    """One artifact, one quantity, one denominator. The cells are filtered to
    the current budget era and the tag census used to span both, so the same
    tag appeared twice in one block with two different row counts and no era
    label on either. Both tables now carry the era they were counted under."""
    cells = {("total", "ev_rank"): _winners(20, 21)}
    census = {"ev_rank": {"total": {"n_in_era": 41, "n_all_eras": 60,
                                    "era_split": True}}}
    _patch(monkeypatch, cells, {}, census=census)
    g3 = _gate3(bm.min_edge_gate(OPEN_VINTAGE))
    tag = g3["by_tag"]["ev_rank"]
    assert tag["era"] == bs.PER_MARKET_CAP_ERA
    assert tag["n_in_era"] == 41 and tag["n_all_eras"] == 60
    assert g3["have_by_tag"]["ev_rank"] == 41
    assert g3["have_by_tag_all_eras"]["ev_rank"] == 60
    assert g3["census_era"] == bs.PER_MARKET_CAP_ERA


def test_a_cross_market_sampler_closes_gate_three(monkeypatch):
    """THE TRIPWIRE. Point the gate back at the per-tag sampler and gate 3 shuts
    instead of publishing a floor off three markets stacked in one sample.

    The rows handed in here would sweep to a threshold on their own (they are
    60% winners at even money). The refusal is about the SHAPE of the sample,
    which is the only thing that can be judged without the market dimension."""
    _patch(monkeypatch, {"board_all": _winners()},
           {"board_all": {"moneyline": 200, "total": 200}})
    gate = bm.min_edge_gate(OPEN_VINTAGE)
    assert gate["min_edge"] is None
    assert gate["all_gates_open"] is False
    tw = gate["cross_market_tripwire"]
    assert tw["passes"] is False
    assert tw["failures"][0]["check"] == "key_is_a_market_tag_pair"
    g3 = _gate3(gate)
    assert g3["open"] is False
    assert "nothing was swept" in gate["sweep"]["reason"]


def test_a_cell_holding_another_markets_rows_closes_gate_three(monkeypatch):
    """The check that survives a sampler being swapped underneath the gate.

    The key says moneyline; the census says moneyline has 40 settled rows under
    this tag and the cell holds 400. Whatever produced it pooled markets, and
    the cell's own key cannot be the evidence that it did not."""
    _patch(monkeypatch, {("moneyline", "board_all"): _winners()},
           {"board_all": {"moneyline": 40, "runline": 180, "total": 180}})
    gate = bm.min_edge_gate(OPEN_VINTAGE)
    assert gate["min_edge"] is None
    tw = gate["cross_market_tripwire"]
    assert tw["passes"] is False
    assert tw["failures"][0]["check"] == "cell_is_one_market"
    assert "400" in tw["failures"][0]["detail"]
    assert "came from another market" not in tw["failures"][0]["detail"], (
        "the cell and the census disagree; which of them is wrong is not "
        "something this check can know, so it may not name a cause")


def test_a_refused_sample_is_not_published_as_evidence_in_hand(monkeypatch):
    """`have` is the number betting_export.pick_blockers prints behind the
    public gate sentence. Publishing the size of a sample this very block just
    declared contaminated refuses in a field nothing renders and reassures in
    the one the page does."""
    _patch(monkeypatch, {("moneyline", "board_all"): _winners()},
           {"board_all": {"moneyline": 40}})
    gate = bm.min_edge_gate(OPEN_VINTAGE)
    g3 = _gate3(gate)
    assert g3["cross_market_tripwire"]["passes"] is False
    assert g3["have"] is None and g3["have_cell"] is None
    reasons = [b["reason"] for b in be.pick_blockers(
        min_edge=gate.get("min_edge"), odds_priceable=True, gate=gate, evald={})
        if b["id"] == "min_edge"]
    assert reasons, "the min_edge blocker must still be published"
    assert "400 in hand" not in reasons[0]


def test_an_unreadable_census_is_named_and_not_blamed_on_the_cells(monkeypatch):
    """A census that could not be READ is a different fact from a census with
    no rows in it. Swallowing the read failure and defaulting every count to
    zero turns a missing file into a published accusation that the cells hold
    another market's rows, which is the fabricated-diagnosis shape
    betting_export.team_input_failure_reason exists to forbid."""
    _patch(monkeypatch, {("moneyline", "board_all"): _winners()}, {}, census=None)
    gate = bm.min_edge_gate(OPEN_VINTAGE)
    tw = gate["cross_market_tripwire"]
    assert tw["passes"] is False
    assert tw["census_available"] is False
    assert [f["check"] for f in tw["failures"]] == ["census_unavailable"]
    assert "not accused" in tw["failures"][0]["detail"]
    assert gate["min_edge"] is None


def test_the_gate_can_actually_open_on_one_sub_ledger(monkeypatch):
    """A gate that can only ever be closed is a constant with extra steps. One
    honest single-market sub-ledger with a profitable graded history opens it,
    and with only that market holding rows the scalar floor covers the board it
    was measured on."""
    _patch(monkeypatch, {("moneyline", "board_all"): _winners()},
           {"board_all": {"moneyline": 400}})
    gate = bm.min_edge_gate(OPEN_VINTAGE)
    assert gate["all_gates_open"] is True
    assert gate["min_edge"] == pytest.approx(0.005)
    assert gate["min_edge_by_market"] == {"moneyline": 0.005}
    assert gate["min_edge_by_market_tag"] == {"moneyline|board_all": 0.005}
    assert gate["min_edge_by_tag"] == {}


def test_a_market_with_rows_and_no_threshold_holds_the_gate_shut(monkeypatch):
    """THE REPAIR'S OWN FAILURE MODE. Splitting a pooled tag makes each cell
    easier to clear than the union was: 310 pooled rows at a 45% win rate sweep
    to nothing, while the 110-row moneyline slice inside them wins 63.6% and
    clears on its own. `min_edge` is ONE scalar filtering every market on the
    board, so publishing that cell's 0.005 would license total picks on a
    sample measured at 25%. The market with rows and no cleared threshold holds
    gate 3 shut instead, and the block names it."""
    strong = _winners(70, 40, edge=0.06)          # 110 rows, 63.6%
    weak = _winners(50, 150, edge=0.06)           # 200 rows, 25%
    _patch(monkeypatch, {("moneyline", "board_all"): strong,
                         ("total", "board_all"): weak},
           {"board_all": {"moneyline": 110, "total": 200}})
    gate = bm.min_edge_gate(OPEN_VINTAGE)
    assert bm.sweep_min_edge(strong)["min_edge"] == pytest.approx(0.005), (
        "the fixture must actually clear on its own, or this pins nothing")
    assert bm.sweep_min_edge(strong + weak)["min_edge"] is None, (
        "the pooled sample must NOT clear, or the split is not the thing "
        "opening the gate")
    assert gate["all_gates_open"] is False
    assert gate["min_edge"] is None
    g3 = _gate3(gate)
    assert g3["open"] is False
    assert g3["coverage"]["markets_with_evidence"] == ["moneyline"]
    assert g3["coverage"]["markets_without_evidence"] == ["total"]
    assert "cannot be published" in gate["sweep"]["reason"]
    thr, basis, prov = be.resolve_min_edge({"min_edge_gate": gate})
    assert prov is True and basis == "provisional_policy_floor"
    assert thr == be.PROVISIONAL_MIN_EDGE


def test_the_floor_is_the_strictest_cleared_sub_ledger(monkeypatch):
    """Two sub-ledgers disagree about what an edge is worth. One number has to
    serve the board, and the only safe reduction is the largest: a floor above a
    cell's own measured threshold can never be looser than that cell's own
    evidence requires. Both markets clear here, so coverage is satisfied and
    the reduction is the only question left."""
    loose = _winners(240, 160, edge=0.06)
    tight = ([{"edge": 0.01, "decimal": 2.0, "won": True}] * 160
             + [{"edge": 0.01, "decimal": 2.0, "won": False}] * 240
             + _winners(240, 160, edge=0.06))
    _patch(monkeypatch, {("moneyline", "board_all"): loose,
                         ("total", "board_all"): tight},
           {"board_all": {"moneyline": len(loose), "total": len(tight)}})
    gate = bm.min_edge_gate(OPEN_VINTAGE)
    by_cell = gate["min_edge_by_market_tag"]
    assert by_cell["moneyline|board_all"] == pytest.approx(0.005)
    assert by_cell["total|board_all"] == pytest.approx(0.015)
    assert gate["min_edge"] == pytest.approx(0.015)
    assert _gate3(gate)["coverage"]["markets_without_evidence"] == []


def test_a_sub_ledger_that_may_not_set_a_threshold_never_does(monkeypatch):
    """Two exclusions, one rule. `untagged` is the one-slot era, a selection
    rule this site no longer runs. `unknown_market` is the bucket a row with no
    market lands in, and a bucket whose members share no market is the same
    mixture as a pooled tag with a different name. Neither sets a floor, and
    neither holds the coverage rule hostage either."""
    assert bm.cell_may_set_a_threshold("moneyline", "board_all") is True
    assert bm.cell_may_set_a_threshold("moneyline", "untagged") is False
    assert bm.cell_may_set_a_threshold(bs.UNKNOWN_MARKET, "board_all") is False
    assert bs.UNKNOWN_MARKET in bm.MARKETS_THAT_MAY_NOT_SET_A_THRESHOLD, (
        "the literal in betting_model must be betting_shadow.UNKNOWN_MARKET; "
        "it is repeated there because the ledger is imported lazily")
    _patch(monkeypatch, {(bs.UNKNOWN_MARKET, "board_all"): _winners(),
                         ("moneyline", "untagged"): _winners()},
           {"board_all": {bs.UNKNOWN_MARKET: 400}, "untagged": {"moneyline": 400}})
    gate = bm.min_edge_gate(OPEN_VINTAGE)
    assert gate["min_edge"] is None
    g3 = _gate3(gate)
    assert g3["open"] is False
    assert g3["by_market_tag"][bs.UNKNOWN_MARKET]["board_all"]["min_edge"] is None
    assert g3["coverage"]["markets_without_evidence"] == [], (
        "a market that may never set a threshold is not a market waiting on "
        "evidence, so it may not hold a gate shut forever either")


def test_the_gate_reports_the_largest_sub_ledger_not_the_union(monkeypatch):
    """`have` is measured against the 100-row floor, so it has to be the number
    that floor applies to. The union is bigger and always will be: a reader
    comparing it against 100 would read the gate as nearly open on a day when no
    single sample has half the rows it needs."""
    _patch(monkeypatch, {("moneyline", "board_all"): _winners(30, 25),
                         ("total", "board_all"): _winners(40, 38)},
           {"board_all": {"moneyline": 55, "total": 78}})
    g3 = _gate3(bm.min_edge_gate(OPEN_VINTAGE))
    assert g3["have"] == 78
    assert g3["have_cell"] == "total|board_all"
    assert g3["have_pooled"] == 133
    assert "never swept" in g3["pooled_is_not_sweepable"]


def test_the_clock_and_the_gate_count_the_same_quantity(led_rows):
    """ONE ARTIFACT, ONE QUANTITY, ONE DENOMINATOR (docs/diamond-betting.md 5b).

    `sweep_readiness` is what betting_learning renders as clock B, and clock B
    is labelled gate 3's clock. While it counted the tag's pooled rows it read
    292 against a need of 100 and called itself ready, in the same file as a
    gate reporting 138 within one sub-ledger. `n` is now the largest cell, the
    number the floor is actually measured against; `n_pooled` keeps the census
    under its own name and is never compared with `need`."""
    ready = bs.sweep_readiness(path=led_rows)
    cells = bs.sweep_readiness_by_market_tag(path=led_rows)
    assert ready, "the fixture ledger settled nothing"
    for tag, block in ready.items():
        mine = {m: ts[tag]["sweepable_n"] for m, ts in cells.items() if tag in ts}
        assert block["markets"] == mine
        assert block["n"] == (max(mine.values()) if mine else 0)
        assert block["ready"] is (block["n"] >= bs.MIN_BETS_FOR_SWEEP)
        assert block["n_pooled"] >= block["n"]
        assert block["sweep_unit"] == "(market, tag) sub-ledger"
    board = ready["board_all"]
    assert board["n_markets"] == 3, "the fixture board_all tag holds three markets"
    assert board["n"] < board["n_pooled"], (
        "the pooled count is the union of three markets and the sweepable "
        "count is the biggest one of them")
    assert board["largest_cell"].endswith("|board_all")


def test_the_census_accounts_for_every_sweepable_row(led_rows):
    """The tripwire is only as good as the census it checks against, so the
    census has to be the same rows the per-tag sampler hands over, counted one
    dimension further out."""
    span = bs.market_span_by_tag(era=bs.PER_MARKET_CAP_ERA, path=led_rows)
    by_tag = bs.graded_bets_by_tag(path=led_rows)
    assert span, "the fixture ledger settled nothing"
    for tag, rows in by_tag.items():
        counts = [b["n_all_eras"] for b in span.get(tag, {}).values()]
        assert sum(counts) == len(rows), tag


def test_the_census_has_no_value_meaning_both_eras(led_rows):
    """`graded_bets_by_market_tag` refuses an era meaning both, because the cap
    change split the series. A census that answered a question the cells cannot
    would be the same mixture wearing the word census."""
    with pytest.raises(bs.ShadowLedgerError):
        bs.market_span_by_tag(era="both", path=led_rows)
    with pytest.raises(bs.ShadowLedgerError):
        bs.market_span_by_tag(era=None, path=led_rows)


def test_the_gate_reads_the_era_the_selector_runs_under(monkeypatch):
    """The 2026-09-06 allocation changed what an ev_rank cell holds and rows
    already on disk are never retagged, so a cell count with no era beside it is
    a count of two selection rules.

    THE LABEL IS CARRIED, NOT RESTATED. While the era was published from a
    module constant, a sampler pointed at the other era went on publishing
    `per_market_cap`, and nothing could notice. Here the reader is asked for
    the pooled era and the label has to follow it."""
    seen = {}

    def _cells(*, era, **kw):
        seen["cells"] = era
        return {("moneyline", "board_all"): []}

    def _span(*, era, **kw):
        seen["census"] = era
        return {}

    monkeypatch.setattr(bs, "graded_bets_by_market_tag", _cells)
    monkeypatch.setattr(bs, "market_span_by_tag", _span)
    monkeypatch.setattr(bs, "PER_MARKET_CAP_ERA", bs.POOLED_CAP_ERA)
    read = bm._shadow_cells_for_the_gate()
    assert seen["cells"] == bs.POOLED_CAP_ERA, "the reader must be called"
    assert seen["census"] == seen["cells"], (
        "a census counted under a different era than the cells cannot check "
        "them row for row")
    assert read["era"] == bs.POOLED_CAP_ERA
    monkeypatch.setattr(bm, "_shadow_graded_bets", list)
    era = bm.min_edge_gate(OPEN_VINTAGE)["sweep"]["budget_era"]
    assert era["era"] == bs.POOLED_CAP_ERA, (
        "the published era is the one the cells were read under")
    assert era["ledger_available"] is True


def test_a_pooled_tag_dict_cannot_be_swept_as_cells():
    """`tuple("board_all")` is nine one-character strings, so a caller reaching
    for the per-tag dict would otherwise have had a pooled tag swept under a
    shredded key and the answer published as a threshold. The ledger's
    MarketTagCells refuses that on its side; this is the same refusal on the
    sweep's side, where the gate's tripwire is the only other guard."""
    with pytest.raises(ValueError, match="not a .market, tag. sub-ledger"):
        bm.sweep_min_edge_by_market_tag({"board_all": _winners()})


def test_the_per_tag_sampler_is_not_what_the_gate_reads(monkeypatch):
    """`sweep_min_edge_by_tag` and `_shadow_graded_bets_by_tag` are kept because
    docs/diamond-betting.md section 7 still names them as the pre-repair gate-3
    path. They still do what they say; they are simply not what the gate
    consults, and this pins both halves of that sentence."""
    out = bm.sweep_min_edge_by_tag({"board_all": _winners(),
                                    "ev_rank": _winners(3, 2)})
    assert out["board_all"]["min_edge"] == pytest.approx(0.005)
    assert out["ev_rank"]["min_edge"] is None

    called = []
    monkeypatch.setattr(bm, "_shadow_graded_bets_by_tag",
                        lambda: called.append("read") or {})
    monkeypatch.setattr(bm, "sweep_min_edge_by_tag",
                        lambda *a, **k: called.append("swept") or {})
    _patch(monkeypatch, {("moneyline", "board_all"): _winners()},
           {"board_all": {"moneyline": 400}})
    bm.min_edge_gate(OPEN_VINTAGE)
    assert called == [], "the gate must not reach the per-tag path at all"


# ---------------------------------------------------------------------------
# 2. the interval (L14-09)
# ---------------------------------------------------------------------------
def test_the_variance_is_a_sample_variance():
    """n - 1, not n. The settled rows are a sample of the bets the rule can
    produce, not the population of them, and the population divisor understates
    the standard error in the direction that opens the gate."""
    rows = _winners(240, 160)
    out = bm.sweep_min_edge(rows)
    cand = next(c for c in out["candidates"] if c["edge"] == 0.005)
    profits = [1.0] * 240 + [-1.0] * 160
    n = len(profits)
    mu = sum(profits) / n
    var = sum((p - mu) ** 2 for p in profits) / (n - 1)
    lower = mu - bm.Z_95_ONE_SIDED * math.sqrt(var / n)
    assert cand["roi_lower_95"] == pytest.approx(round(lower, 5))
    pop = mu - bm.Z_95_ONE_SIDED * math.sqrt(
        (sum((p - mu) ** 2 for p in profits) / n) / n)
    assert lower < pop, "the sample divisor must be the stricter of the two"
    assert "n - 1" in out["variance_basis"]


def test_zero_variance_is_a_refusal_and_not_a_certainty():
    """150 rows all won at one identical price. The old escape set se = 0, so
    the lower bound equalled the mean and the threshold qualified with no
    uncertainty at all: the degenerate-fan shape of 2026-09-06, a guard reading
    as certainty because its sample has no spread."""
    rows = [{"edge": 0.09, "decimal": 2.0, "won": True}] * 150
    out = bm.sweep_min_edge(rows)
    assert out["min_edge"] is None
    cand = next(c for c in out["candidates"] if c["edge"] == 0.005)
    assert cand["qualified"] is False
    assert cand["roi_lower_95"] is None
    assert bm.ZERO_VARIANCE_REFUSAL in cand["reason"]
    assert "+1.000 units" in cand["reason"]
    assert "certainty" in bm.ZERO_VARIANCE_REFUSAL


def test_a_sample_that_lost_every_bet_is_refused_in_its_own_words():
    """Zero variance twice over: every row LOST. The verdict is the same and
    has to be, but a bare 'no interval can be formed' reads as undecidable
    about a sample that is unambiguously bad, so the constant it returned is
    named."""
    rows = [{"edge": 0.09, "decimal": 2.0, "won": False}] * 150
    cand = next(c for c in bm.sweep_min_edge(rows)["candidates"]
                if c["edge"] == 0.005)
    assert cand["qualified"] is False
    assert "-1.000 units" in cand["reason"]


def test_one_settled_row_carries_no_spread():
    """The n < 2 branch, reachable only when a caller lowers `min_bets`. It
    stays because n - 1 is a division and a one-row sample is the input that
    makes it a zero one."""
    out = bm.sweep_min_edge([{"edge": 0.09, "decimal": 2.0, "won": True}],
                            min_bets=1)
    cand = next(c for c in out["candidates"] if c["edge"] == 0.005)
    assert cand["n"] == 1
    assert cand["qualified"] is False
    assert cand["roi_lower_95"] is None
    assert "no spread" in cand["reason"]


def test_the_multiplicity_of_the_grid_is_stated():
    """Twenty one-sided tests at 95% are not one test at 95%. Taking the
    smallest qualifying threshold is conservative on sample size and says
    nothing about the number of looks, so the count is published."""
    out = bm.sweep_min_edge(_winners())
    assert "20 one-sided tests" in out["multiplicity"]
    assert "no multiplicity correction" in out["multiplicity"]
    assert out["multiplicity"] in out["reason"]
    assert "multiplicity" in bm.sweep_min_edge([])["multiplicity"]
    assert out["n_looks"] == len(bm.MIN_EDGE_GRID) == 20


def test_the_family_of_looks_grows_with_the_sub_ledgers(monkeypatch):
    """The sub-ledgers multiply the sweeps by the markets, so the number of
    independent chances for SOME cell to clear spuriously grows as the cells
    fill. The max reduction is a severity control across cells that already
    agree a floor exists; it is not a multiplicity control, and the block says
    so rather than letting `max` imply it."""
    _patch(monkeypatch, {("moneyline", "board_all"): _winners(30, 25),
                         ("total", "board_all"): _winners(40, 38),
                         ("runline", "board_all"): _winners(10, 9)},
           {"board_all": {"moneyline": 55, "total": 78, "runline": 19}})
    fam = _gate3(bm.min_edge_gate(OPEN_VINTAGE))["multiplicity_family"]
    assert fam["n_cells_swept"] == 3
    assert fam["n_thresholds_per_cell"] == len(bm.MIN_EDGE_GRID)
    assert fam["n_one_sided_looks"] == 3 * len(bm.MIN_EDGE_GRID)
    assert fam["corrected"] is False
    assert "severity control" in fam["note"]
    assert "NOT a multiplicity control" in " ".join(fam["note"].split())


def test_a_thin_sample_still_buys_nothing():
    """Unchanged by either repair, and pinned here because both repairs touch
    the arithmetic underneath it: twenty bets that all won is a streak."""
    out = bm.sweep_min_edge([{"edge": 0.09, "decimal": 2.0, "won": True}] * 20)
    assert out["min_edge"] is None
