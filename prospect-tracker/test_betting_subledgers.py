# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The market sub-ledgers: each market opens or closes on its own evidence.

WHAT THIS FILE PINS, and why each pin is worth its line.

THE DEFECT IT CLOSES. The shadow ledger tagged every row with the RULE that
chose it and never with the MARKET it was on, so every read pooled three
markets. Measured on the live ledger 2026-09-06 (255 rows, 223 settled, pooled
ROI -13.1%): moneyline 44 settled at -27.4%, runline 74 at -3.2%, total 105 at
-14.6%, and totals are 121 of the 255 rows. The pooled number is none of the
three and is mostly a statement about totals wearing every market's name.

THE BUDGET HALF OF IT. `ev_rank` ranks the whole board by EV and takes three,
and totals win that race: of its 49 rows, 36 are totals and 4 are moneylines.
Four settled moneyline rows over 16 slate days is a sub-ledger that reaches the
100-row sweep floor in about a decade, so one market was spending another's
budget and two of three markets could never open on their own evidence.

WHAT IS PINNED
  1. Per-market tallies SUM to the pooled tally. A sub-ledger that does not
     reconcile with the whole is a second set of books.
  2. A cross-market pooled sweep is NOT REACHABLE by accident: the cell reader
     is keyed by (market, tag), a tag-only key raises rather than silently
     returning three markets stacked, there is no pooled method, and the budget
     era is a required argument with no value meaning both.
  3. The per-market allocation is ENFORCED, per slate and not per call, and it
     does not cut volume on a board where one market is the only thing offered.
  4. The cap change SPLITS THE SERIES at BUDGET_SPLIT_DATE rather than
     retagging rows already on disk, the split date rides the artifact, and
     only the cells whose membership actually changed carry two populations.
  5. SETTLEMENT IS UNCHANGED. This lane is an additive read layer plus a budget
     change; if it moved a grade or a profit number it would have rewritten
     evidence instead of reading it.
"""
from __future__ import annotations

import pytest

bs = pytest.importorskip("betting_shadow")


@pytest.fixture
def led(tmp_path):
    return tmp_path / "shadow.json"


def _mixed_payload(slate="2026-08-06"):
    """Five totals holding the best EV on the board, one runline, one moneyline.

    This is the shape of the live defect: under a pooled cap the three ev_rank
    seats all go to totals and the other two markets log nothing."""
    games = []
    for i in range(5):
        games.append({"game_pk": 700 + i, "home": {"org": "PHI"},
                      "away": {"org": "WSN"},
                      "total": {"line": 9.0, "sides": [
                          {"side": "over", "label": f"Over {i}", "point": 9.0,
                           "edge": 0.20, "odds": -110, "decimal": 1.91,
                           "book": "dk", "model_prob": 0.60,
                           "market_fair_prob": 0.52,
                           "ev_per_unit": 0.9 - i * 0.01}]}})
    games.append({"game_pk": 800, "home": {"org": "NYM"}, "away": {"org": "ATL"},
                  "runline": [{"side": "away", "label": "ATL +1.5", "point": 1.5,
                               "edge": 0.10, "odds": -120, "decimal": 1.83,
                               "book": "dk", "ev_per_unit": 0.20}]})
    games.append({"game_pk": 801, "home": {"org": "LAD"}, "away": {"org": "SDP"},
                  "moneyline": [{"side": "away", "label": "SDP", "edge": 0.09,
                                 "odds": 150, "decimal": 2.5, "book": "dk",
                                 "ev_per_unit": 0.10}]})
    return {"slate_date": slate, "status": {"odds_feed": "ok"},
            "team_bets": games}


def _one_market_payload(n=8, slate="2026-08-06"):
    """A board where moneyline is the only market offering anything."""
    return {
        "slate_date": slate, "status": {"odds_feed": "ok"},
        "team_bets": [{
            "game_pk": 900 + i, "home": {"org": "PHI"}, "away": {"org": "WSN"},
            "moneyline": [{"side": "away", "label": f"S{i}",
                           "edge": 0.20 - i * 0.005, "odds": 150,
                           "decimal": 2.5, "book": "dk",
                           "ev_per_unit": 0.5 - i * 0.01}],
        } for i in range(n)],
    }


def _settle_all(path, home=9, away=6):
    pks = {r["game_pk"] for r in bs.load(path)}
    return bs.settle(games=[{"game_pk": pk, "home_runs": home, "away_runs": away}
                            for pk in pks], path=path)


# ---------------------------------------------------------------------------
# 1. the sub-ledgers reconcile with the whole
# ---------------------------------------------------------------------------
def test_per_market_tallies_sum_to_the_pooled_tally(led):
    """A sub-ledger that does not reconcile is a second set of books.

    Every row is on exactly one market, so `by_market` is a PARTITION: the row
    counts, the settled counts, the won/lost/push counts and the net units all
    have to add back up to the pooled tally the page already shows."""
    bs.record_slate(_mixed_payload(), min_edge=0.05, path=led)
    _settle_all(led)
    s = bs.summary(path=led)
    bym = s["by_market"]
    assert set(bym) == {"moneyline", "runline", "total"}
    for key in ("n_rows", "n_open", "n_settled", "won", "lost", "push"):
        assert sum(v[key] for v in bym.values()) == s[key], (
            f"by_market {key} does not sum to the pooled {key}")
    assert abs(sum(v["net_units"] or 0 for v in bym.values())
               - (s["net_units"] or 0)) < 1e-6


def test_by_market_by_tag_is_membership_inside_one_market(led):
    """The cell a per-market sweep keys on, and the shape it really has.

    `by_market` partitions. `by_market_by_tag` does NOT, for the same reason
    `by_tag` does not: a capped row is also a board_all row, so the tags inside
    one market overlap. Both facts ride the artifact as notes so a reader cannot
    add up the wrong one."""
    bs.record_slate(_mixed_payload(), min_edge=0.05,
                    include_board_all=True, path=led)
    s = bs.summary(path=led)
    for market, tags in s["by_market_by_tag"].items():
        inside = sum(t["n_rows"] for t in tags.values())
        assert inside >= s["by_market"][market]["n_rows"], (
            "a market's tags cannot hold fewer rows than the market does")
    assert "partition" in s["by_market_note"]
    assert "not a partition" in s["by_market_by_tag_note"]


# ---------------------------------------------------------------------------
# 2. a cross-market pooled sweep is not reachable
# ---------------------------------------------------------------------------
def test_a_cross_market_pooled_sweep_is_not_reachable(led):
    """THE DISCIPLINE PIN. A threshold may never be set from pooled or
    cross-market rows, and this is the structural half of saying so.

    The cell reader is keyed by (market, tag). A tag-only key, which is exactly
    what a reader porting code from `graded_bets_by_tag` would type, RAISES
    instead of quietly handing back one tag stacked over three markets. There is
    no pooled method. MUTATION PROOF: give MarketTagCells a plain dict
    __getitem__ and the tag-only key silently returns None or a pooled list, and
    this test fails."""
    bs.record_slate(_mixed_payload(), min_edge=0.05, path=led)
    _settle_all(led)
    cells = bs.graded_bets_by_market_tag(era=bs.POOLED_CAP_ERA, path=led)
    assert cells, "the fixture settled nothing; the rest of this test is vacuous"
    assert all(isinstance(k, tuple) and len(k) == 2 for k in cells)
    with pytest.raises(bs.ShadowLedgerError):
        cells[bs.DEFAULT_SLOT_TAG]
    with pytest.raises(bs.ShadowLedgerError):
        cells.get(bs.DEFAULT_SLOT_TAG)
    with pytest.raises(bs.ShadowLedgerError):
        cells.pooled()


def test_the_budget_era_has_no_value_meaning_both(led):
    """A sample spanning the cap change mixes two selection rules, which is the
    pooling defect one dimension over. So `era` is required and only the two
    real eras are accepted: there is no default that quietly spans the split."""
    bs.record_slate(_mixed_payload(), min_edge=0.05, path=led)
    with pytest.raises(TypeError):
        bs.graded_bets_by_market_tag(path=led)          # era is required
    for bad in ("both", "all", None, ""):
        with pytest.raises(bs.ShadowLedgerError):
            bs.graded_bets_by_market_tag(era=bad, path=led)


def test_every_cell_row_is_the_shape_sweep_min_edge_consumes(led):
    """The cells are sweepable or they are decoration. Same shaping as the
    pooled reader, because two shaping rules would be two samples wearing one
    name; pushes never enter, which would otherwise understate every cell."""
    bm = pytest.importorskip("betting_model")
    bs.record_slate(_mixed_payload(), min_edge=0.05, path=led)
    _settle_all(led)
    cells = bs.graded_bets_by_market_tag(era=bs.POOLED_CAP_ERA, path=led)
    for key, rows in cells.items():
        assert rows, f"{key} is an empty cell and should not have been listed"
        assert all(set(r) == {"edge", "decimal", "won"} for r in rows)
        out = bm.sweep_min_edge(list(rows))
        assert "min_edge" in out and "reason" in out


# ---------------------------------------------------------------------------
# 3. the per-market allocation
# ---------------------------------------------------------------------------
def test_the_per_market_allocation_is_enforced(led):
    """Totals cannot take a seat another market would have used.

    The fixture board holds the five best EV sides on totals. Under the pooled
    cap all three ev_rank seats go to totals and the moneyline sub-ledger stays
    at zero forever, which is the live defect: 36 totals against 4 moneylines.
    MUTATION PROOF: empty MAX_PER_SLATE_BY_MARKET_TAG and this returns three
    totals."""
    bs.record_slate(_mixed_payload(), min_edge=0.05, path=led)
    got = sorted(bs.market_of(r) for r in bs.load(led))
    assert got == ["moneyline", "runline", "total"], got
    # And the pooled rule really would have done the other thing, so the pin
    # above is measuring the allocation and not the fixture.
    pooled_rule = bs.candidates_from_board(_mixed_payload(), min_edge=0.05,
                                           budget_by_market_tag={})
    assert sorted(bs.market_of(c) for c in pooled_rule) == ["total"] * 3


def test_the_allocation_is_a_reservation_and_not_a_ceiling(led):
    """A seat no market wanted is not a seat any market was denied.

    On a board where moneyline is the only market offering anything, the tag
    still fills its whole per-slate total through the spill pass. A hard ceiling
    would have cut ev_rank from three rows to one there and bought nothing: no
    market was outbid."""
    bs.record_slate(_one_market_payload(), min_edge=0.05, path=led)
    n_ev = sum(1 for r in bs.load(led) if r.get("slot") == bs.DEFAULT_SLOT_TAG)
    assert n_ev == bs.MAX_PER_SLATE_BY_TAG[bs.DEFAULT_SLOT_TAG], (
        f"ev_rank logged {n_ev} rows on a one-market board against a per-slate "
        f"total of {bs.MAX_PER_SLATE_BY_TAG[bs.DEFAULT_SLOT_TAG]}")


def test_the_allocation_is_per_slate_not_per_call(led):
    """The pipeline runs more than once a day. A second pass that got a fresh
    allocation would let one market take its seat twice, off two different
    capture times, and call the pair one selection rule."""
    bs.record_slate(_mixed_payload(), min_edge=0.05, path=led)
    first = len(bs.load(led))
    later = _mixed_payload()
    for i, g in enumerate(later["team_bets"]):
        g["game_pk"] = 5000 + i          # a different board, same slate
    again = bs.record_slate(later, min_edge=0.05, path=led)
    assert len(bs.load(led)) == first, "a second pass bought a second allocation"
    assert "already logged" in again["reason"]


def test_the_tag_total_still_binds_across_markets(led):
    """The allocation is the SECOND budget, not a replacement for the first.
    Three markets at one seat each may not become a bigger slate than the tag's
    declared per-slate total, or the tag's ROI stops being a claim about the top
    of the board."""
    bs.record_slate(_mixed_payload(), min_edge=0.05, include_board_all=True,
                    path=led)
    rows = bs.load(led)
    capped = [r for r in rows
              if bs.MAX_PER_SLATE_BY_TAG.get(r.get("slot")) is not None]
    n_ev = sum(1 for r in capped if r.get("slot") == bs.DEFAULT_SLOT_TAG)
    assert n_ev <= bs.MAX_PER_SLATE_BY_TAG[bs.DEFAULT_SLOT_TAG]
    assert len(capped) <= bs.MAX_PER_SLATE


# ---------------------------------------------------------------------------
# 4. the cap change splits the series, it does not rewrite it
# ---------------------------------------------------------------------------
def test_rows_before_the_split_date_are_counted_separately(led):
    """Rows already on disk were chosen under the pooled cap and are never
    retagged. So the artifact carries the split date and both halves apart."""
    bs.record_slate(_mixed_payload(slate="2026-08-06"), min_edge=0.05, path=led)
    bs.record_slate(_mixed_payload(slate="2026-09-30"), min_edge=0.05, path=led)
    s = bs.summary(path=led)
    split = s["budget_split"]
    assert split["split_date"] == bs.BUDGET_SPLIT_DATE
    assert split["eras"][bs.POOLED_CAP_ERA]["n_rows"] == 3
    assert split["eras"][bs.PER_MARKET_CAP_ERA]["n_rows"] == 3
    assert (split["eras"][bs.POOLED_CAP_ERA]["n_rows"]
            + split["eras"][bs.PER_MARKET_CAP_ERA]["n_rows"] == s["n_rows"])


def test_a_split_cell_never_mixes_the_two_eras(led):
    """The pin the whole split exists for: an ev_rank cell's sweepable sample
    holds ONE selection rule. A row from the other era never appears in it."""
    bs.record_slate(_mixed_payload(slate="2026-08-06"), min_edge=0.05, path=led)
    bs.record_slate(_mixed_payload(slate="2026-09-30"), min_edge=0.05, path=led)
    _settle_all(led)
    old = bs.graded_bets_by_market_tag(era=bs.POOLED_CAP_ERA, path=led)
    new = bs.graded_bets_by_market_tag(era=bs.PER_MARKET_CAP_ERA, path=led)
    for m in bs.TEAM_MARKETS:
        key = (m, bs.DEFAULT_SLOT_TAG)
        assert bs.era_split_applies(*key), "ev_rank is the cell the cap changed"
        assert len(old.get(key, [])) == 1 and len(new.get(key, [])) == 1, (
            f"{key}: one settled row per era was recorded; the cells hold "
            f"{len(old.get(key, []))} and {len(new.get(key, []))}")


def test_only_the_cells_whose_cap_changed_split(led):
    """The exemption is as load-bearing as the split.

    board_all is uncapped on both sides of the date, so its population is
    identical and its rows (185 on the live ledger 2026-09-06) keep accruing
    into ONE sample. The single-pick slot tags have an allocation equal to their
    tag total, so their arithmetic cannot have changed either. Splitting them
    would throw away evidence to protect against a difference that does not
    exist."""
    assert not bs.era_split_applies("total", bs.BOARD_ALL_TAG)
    for tag in bs.SLOT_TAGS.values():
        for m in bs.TEAM_MARKETS:
            assert not bs.era_split_applies(m, tag)
    for t in bs.PROPS_TAGS:
        assert not bs.era_split_applies(t, t), "a props tag is its own market"
    for m in bs.TEAM_MARKETS:
        assert bs.era_split_applies(m, bs.DEFAULT_SLOT_TAG)
    bs.record_slate(_mixed_payload(slate="2026-08-06"), min_edge=0.05,
                    include_board_all=True, path=led)
    s = bs.summary(path=led)
    assert all(t == bs.DEFAULT_SLOT_TAG
               for _, t in s["budget_split"]["cells_that_split"])


def test_an_exempt_cell_returns_its_whole_history_under_either_era(led):
    """A cell that did not split is swept as one sample whichever era is named.
    That is not double counting: every cell is swept on its own and yields its
    own threshold, so a cell is never summed with itself."""
    bs.record_slate(_mixed_payload(slate="2026-08-06"), min_edge=0.05,
                    include_board_all=True, path=led)
    _settle_all(led)
    old = bs.graded_bets_by_market_tag(era=bs.POOLED_CAP_ERA, path=led)
    new = bs.graded_bets_by_market_tag(era=bs.PER_MARKET_CAP_ERA, path=led)
    key = ("total", bs.BOARD_ALL_TAG)
    assert old[key] and old[key] == new[key]


def test_readiness_never_calls_a_split_cell_ready_off_the_old_era(led):
    """A cell whose rule changed may not open on rows the old rule chose. The
    counter says so: `sweepable_n` is the post-split era alone for a split
    cell, and the full history for an exempt one."""
    bs.record_slate(_mixed_payload(slate="2026-08-06"), min_edge=0.05,
                    include_board_all=True, path=led)
    _settle_all(led)
    ready = bs.summary(path=led)["sweep_readiness_by_market_tag"]
    ev = ready["total"][bs.DEFAULT_SLOT_TAG]
    assert ev["era_split"] is True
    assert ev["n"] >= 1 and ev["sweepable_n"] == 0, (
        "a pre-split row may count as evidence but may not be swept under the "
        "new rule")
    ba = ready["total"][bs.BOARD_ALL_TAG]
    assert ba["era_split"] is False and ba["sweepable_n"] == ba["n"]
    assert ev["need"] == bs.MIN_BETS_FOR_SWEEP


def test_the_read_layer_never_writes(led):
    """This lane is additive. Reading the sub-ledgers may not touch a row."""
    bs.record_slate(_mixed_payload(), min_edge=0.05, path=led)
    _settle_all(led)
    before = led.read_text(encoding="utf-8")
    bs.summary(path=led)
    bs.graded_bets_by_market_tag(era=bs.PER_MARKET_CAP_ERA, path=led)
    bs.sweep_readiness_by_market_tag(path=led)
    assert led.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# 5. settlement is unchanged
# ---------------------------------------------------------------------------
def test_settle_behaviour_is_unchanged(led):
    """The grades and the profit numbers are the evidence. A read layer that
    moved one of them would have rewritten the record it exists to report.

    The fixture resolves 9-6: the over cashes, ATL +1.5 loses by three, SDP
    loses outright at +150."""
    bs.record_slate(_mixed_payload(), min_edge=0.05, path=led)
    out = _settle_all(led, home=9, away=6)
    assert out["settled"] == 3 and out["open"] == 0
    got = {r["market"]: r for r in bs.load(led)}
    assert got["total"]["result"] == "won"
    assert got["runline"]["result"] == "lost"
    assert got["moneyline"]["result"] == "lost"
    assert got["total"]["profit_units"] == pytest.approx(0.91, abs=1e-6)
    assert got["moneyline"]["profit_units"] == pytest.approx(-1.0)
    assert got["total"]["final_home_runs"] == 9
    # Idempotent: a second pass leaves every settled row exactly as it was.
    frozen = led.read_text(encoding="utf-8")
    again = _settle_all(led, home=1, away=0)
    assert again["settled"] == 0
    assert led.read_text(encoding="utf-8") == frozen


def test_a_push_is_still_a_push_and_still_out_of_every_cell(led):
    """A push returns the stake. Scoring it as a loss would understate every
    cell's ROI and make each market's gate harder to clear for a reason that
    has nothing to do with skill."""
    p = _mixed_payload()
    p["team_bets"] = [p["team_bets"][0]]
    bs.record_slate(p, min_edge=0.05, path=led)
    _settle_all(led, home=5, away=4)          # 9 runs on a 9.0 total
    rows = bs.load(led)
    assert [r["result"] for r in rows] == ["push"]
    s = bs.summary(path=led)
    assert s["by_market"]["total"]["push"] == 1
    assert s["by_market"]["total"]["n_settled"] == 1
    cells = bs.graded_bets_by_market_tag(era=bs.POOLED_CAP_ERA, path=led)
    assert cells == {}, "a push may not enter a sweepable cell"


def test_a_settled_row_may_still_never_be_revised(led):
    """The append-or-settle rule is untouched by the market dimension."""
    bs.record_slate(_mixed_payload(), min_edge=0.05, path=led)
    _settle_all(led)
    rows = bs.load(led)
    tampered = [dict(r) for r in rows]
    tampered[0]["result"] = "won" if tampered[0]["result"] == "lost" else "lost"
    with pytest.raises(bs.ShadowLedgerError):
        bs.check_append_or_settle(rows, tampered)
    remarketed = [dict(r) for r in rows]
    remarketed[0]["market"] = "moneyline"
    with pytest.raises(bs.ShadowLedgerError):
        bs.check_append_or_settle(rows, remarketed)


def test_a_row_with_no_market_lands_in_a_named_bucket(led):
    """Defensive, and measured: 0 of the 255 live rows lack a market. A
    malformed row must not join a real market's evidence by defaulting."""
    bs.record_slate(_mixed_payload(), min_edge=0.05, path=led)
    rows = bs.load(led)
    rows[0] = {k: v for k, v in rows[0].items() if k != "market"}
    bs._write(rows, led)
    s = bs.summary(path=led)
    assert s["by_market"][bs.UNKNOWN_MARKET]["n_rows"] == 1
    assert sum(v["n_rows"] for v in s["by_market"].values()) == s["n_rows"]
