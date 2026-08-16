# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Three ledgers, three questions, three arrival rates - and the rules that stop
them being read as one thing.

data/betting_learning.json is the file that makes "the module improves each day"
a measurement instead of a slogan, and a progress bar is exactly what it would
degrade into without the properties below. These tests are that guarantee.

WHAT THEY HOLD

  1. NO TAG IS EVER POOLED. `graded_bets(slot=...)` conditions on the selection
     rule; the four tags select on four different quantities, so a threshold
     fitted to their union is wrong for each of them separately
     (docs/diamond-betting.md section 7a).
  2. `board_all` DOES NOT WIDEN AN EXISTING TAG. Adding an uncapped tag must not
     reinterpret a single row already on disk, so the three capped budgets are
     unchanged and a legacy row is never folded into the new population.
  3. THE CALIBRATION LEDGER CANNOT BECOME A BET LEDGER. A stake, a bet_id, an
     ROI or a `clv_pct` in a calibration row RAISES. That is what keeps it
     outside the tag rule: it holds probabilities, not positions.
  4. A LATER PHASE CANNOT EDIT AN EARLIER PHASE'S FIELD. A settlement that could
     rewrite a price would make the whole ledger worthless.
  5. days_to_need IS A MEASURED RATE APPLIED FORWARD AND SAYS SO, and it is
     None - not "a long time" - when no arrivals were measured.
  6. HISTORY IS NEVER REWRITTEN. A past row that changed is refused by the
     public record's own check_append_only seam.
  7. A COUNTER THAT GOES BACKWARDS RENDERS BACKWARDS. No high-water marks.
  8. ONE GRADER. betting_settle decides every market for every ledger, so two
     ledgers can never disagree about the same game.
  9. EVERY CATALOG ROW CARRIES `stability`. A row without it kills /sources/ on
     a bare subscript.
"""
from __future__ import annotations

import json

import pytest

bl = pytest.importorskip("betting_learning")
bs = pytest.importorskip("betting_shadow")
bset = pytest.importorskip("betting_settle")
bc = pytest.importorskip("tools.betting_calibration")


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _board(slate="2026-08-06", feed="ok"):
    """A two-game board, 12 priced sides, 8 of them over a 5% floor.

    Deliberately MORE clearing sides than MAX_PER_SLATE, because a board that
    fits inside the cap cannot tell a capped tag apart from an uncapped one and
    every board_all assertion below would pass vacuously."""
    return {
        "slate_date": slate,
        "status": {"odds_feed": feed, "odds_captured_at": f"{slate}T18:00:00+00:00",
                   "team_input_sources": {"offense": {"as_of": "2026-08-05"}}},
        "team_bets": [{
            "game_pk": 900,
            "home": {"org": "PHI"}, "away": {"org": "WSN"},
            "market": {"moneyline_fair_book": "pinnacle", "moneyline_hold_pct": 2.1,
                       "total_fair_book": "pinnacle", "total_hold_pct": 4.0,
                       "runline_fair_book": "pinnacle", "runline_hold_pct": 3.0,
                       "n_books_rejected": {"moneyline": {"on_line": 5}}},
            "moneyline": [
                {"side": "away", "label": "WSN", "edge": 0.10, "odds": 150,
                 "decimal": 2.5, "book": "draftkings", "model_prob": 0.40,
                 "market_fair_prob": 0.30, "ev_per_unit": 0.5},
                {"side": "home", "label": "PHI", "edge": -0.10, "odds": -180,
                 "decimal": 1.55, "book": "draftkings", "model_prob": 0.60,
                 "market_fair_prob": 0.70, "ev_per_unit": -0.07},
            ],
            "runline": [
                {"side": "away", "label": "WSN +1.5", "point": 1.5, "edge": 0.09,
                 "odds": -120, "decimal": 1.83, "book": "draftkings",
                 "model_prob": 0.66, "market_fair_prob": 0.57, "ev_per_unit": 0.2},
                {"side": "home", "label": "PHI -1.5", "point": -1.5, "edge": 0.07,
                 "odds": 140, "decimal": 2.40, "book": "draftkings",
                 "model_prob": 0.34, "market_fair_prob": 0.43, "ev_per_unit": 0.15},
            ],
            "total": {"line": 9.0, "sides": [
                {"side": "under", "label": "Under 9.0", "point": 9.0, "edge": 0.08,
                 "odds": -115, "decimal": 1.87, "book": "draftkings",
                 "model_prob": 0.55, "market_fair_prob": 0.47, "ev_per_unit": 0.1},
                {"side": "over", "label": "Over 9.0", "point": 9.0, "edge": 0.065,
                 "odds": -105, "decimal": 1.95, "book": "draftkings",
                 "model_prob": 0.45, "market_fair_prob": 0.53, "ev_per_unit": 0.08},
            ]},
        }, {
            "game_pk": 901,
            "home": {"org": "SEA"}, "away": {"org": "TBR"},
            "market": {"moneyline_fair_book": "pinnacle", "moneyline_hold_pct": 2.4,
                       "total_fair_book": "pinnacle", "total_hold_pct": 3.8,
                       "runline_fair_book": "pinnacle", "runline_hold_pct": 3.1,
                       "n_books_rejected": {"moneyline": {"on_line": 4}}},
            "moneyline": [
                {"side": "home", "label": "SEA", "edge": 0.061, "odds": -130,
                 "decimal": 1.77, "book": "mybookieag", "model_prob": 0.625,
                 "market_fair_prob": 0.564, "ev_per_unit": 0.06},
                {"side": "away", "label": "TBR", "edge": -0.061, "odds": 110,
                 "decimal": 2.10, "book": "mybookieag", "model_prob": 0.375,
                 "market_fair_prob": 0.436, "ev_per_unit": -0.12},
            ],
            "runline": [
                {"side": "away", "label": "TBR +1.5", "point": 1.5, "edge": 0.0666,
                 "odds": -181, "decimal": 1.5525, "book": "mybookieag",
                 "model_prob": 0.704, "market_fair_prob": 0.638, "ev_per_unit": 0.093},
                {"side": "home", "label": "SEA -1.5", "point": -1.5, "edge": -0.0666,
                 "odds": 150, "decimal": 2.50, "book": "mybookieag",
                 "model_prob": 0.296, "market_fair_prob": 0.362, "ev_per_unit": -0.26},
            ],
            "total": {"line": 8.5, "sides": [
                {"side": "under", "label": "Under 8.5", "point": 8.5, "edge": 0.055,
                 "odds": -110, "decimal": 1.91, "book": "mybookieag",
                 "model_prob": 0.53, "market_fair_prob": 0.475, "ev_per_unit": 0.012},
                {"side": "over", "label": "Over 8.5", "point": 8.5, "edge": -0.055,
                 "odds": -110, "decimal": 1.91, "book": "mybookieag",
                 "model_prob": 0.47, "market_fair_prob": 0.525, "ev_per_unit": -0.10},
            ]},
        }],
    }


def _finals():
    """Both games final. PHI 8, WSN 1 and SEA 2, TBR 3."""
    return [{"game_pk": 900, "home_runs": 8, "away_runs": 1},
            {"game_pk": 901, "home_runs": 2, "away_runs": 3}]


@pytest.fixture
def led(tmp_path):
    return tmp_path / "shadow.json"


@pytest.fixture
def cal(tmp_path):
    return tmp_path / "calibration.jsonl"


@pytest.fixture
def series(tmp_path):
    return tmp_path / "betting_learning.json"


# ---------------------------------------------------------------------------
# 1. no tag is ever pooled
# ---------------------------------------------------------------------------
def test_graded_bets_conditions_on_the_tag_instead_of_pooling(led):
    """Section 7a in as many words: a pooled ROI measures a mixture nobody bet."""
    p = _board()
    # `_row_key` matches on (game_pk, market, side, point), so a slot handed in
    # without `market` matches nothing. That is the payload's own shape.
    slots = {"pick_of_the_day": dict(p["team_bets"][0]["runline"][0],
                                     game_pk=900, market="runline"),
             "longshot_of_the_day": dict(p["team_bets"][0]["moneyline"][0],
                                         game_pk=900, market="moneyline")}
    bs.record_slate(p, min_edge=0.05, slots=slots, include_board_all=True, path=led)
    bs.settle(games=_finals(), path=led)

    pooled = bs.graded_bets(path=led)
    potd = bs.graded_bets(slot="potd_band", path=led)
    board = bs.graded_bets(slot=bs.BOARD_ALL_TAG, path=led)

    assert len(potd) == 1, "the headline slot is one row, not the whole ledger"
    assert len(board) == len(pooled), (
        "board_all is every clearing side, so on a slate where every row was "
        "written it equals the pooled count - and it is still a DIFFERENT "
        "question, which is why it has its own name")
    assert len(potd) < len(board)


def test_an_unknown_tag_returns_nothing_rather_than_everything(led):
    """A typo in a tag name must starve the sweep, never feed it the pool."""
    bs.record_slate(_board(), min_edge=0.05, path=led)
    bs.settle(games=_finals(), path=led)
    assert bs.graded_bets(slot="no_such_tag", path=led) == []
    assert bs.graded_bets(path=led), "the pooled call still returns rows"


def test_sweep_readiness_is_per_tag_and_each_tag_needs_its_own_hundred(led):
    bs.record_slate(_board(), min_edge=0.05, path=led)
    bs.settle(games=_finals(), path=led)
    r = bs.sweep_readiness(path=led)
    assert r, "at least one tag has settled rows"
    for tag, block in r.items():
        assert block["need"] == bs.MIN_BETS_FOR_SWEEP == 100
        assert block["ready"] is (block["n"] >= 100)


# ---------------------------------------------------------------------------
# 2. board_all does not widen an existing tag
# ---------------------------------------------------------------------------
def test_the_capped_budgets_still_sum_to_the_shipped_slate_budget():
    """Adding a fourth tag may not change what the three capped tags mean."""
    capped = [v for k, v in bs.MAX_PER_SLATE_BY_TAG.items() if v is not None]
    assert sum(capped) == bs.MAX_PER_SLATE == 5
    assert bs.MAX_PER_SLATE_BY_TAG[bs.BOARD_ALL_TAG] is None, "board_all is uncapped"


def test_board_all_is_off_by_default_and_changes_nothing_when_off(led):
    """With the flag off the output is identical to before it existed, down to
    the absence of the `tags` key."""
    cands = bs.candidates_from_board(_board(), min_edge=0.05)
    assert len(cands) <= bs.MAX_PER_SLATE
    assert all("tags" not in c for c in cands)
    assert all(c.get("slot") != bs.BOARD_ALL_TAG for c in cands)


def test_board_all_adds_rows_without_retagging_the_capped_ones(led):
    on = bs.candidates_from_board(_board(), min_edge=0.05, include_board_all=True)
    off = bs.candidates_from_board(_board(), min_edge=0.05)
    assert len(on) > len(off), "the uncapped tag reaches sides the cap refused"
    by_slot_off = [c.get("slot") for c in off]
    by_slot_on = [c.get("slot") for c in on[:len(off)]]
    assert by_slot_on == by_slot_off, "a capped row keeps the rule that chose it"
    assert all(bs.BOARD_ALL_TAG in c["tags"] for c in on), (
        "every side on the board is a board_all member, including the capped ones")


def test_a_legacy_row_is_never_folded_into_the_new_tag(led):
    """A row written under the five-a-slate cap is a CENSORED sample. Reading it
    into the uncapped tag would be the pooling defect one level down."""
    bs.record_slate(_board(), min_edge=0.05, path=led)
    rows = bs.load(led)
    rows[0] = {k: v for k, v in rows[0].items() if k not in ("slot", "tags")}
    bs._write(rows, led)
    assert bs.row_tags(bs.load(led)[0]) == {bs.UNTAGGED}
    assert bs.BOARD_ALL_TAG not in bs.row_tags(bs.load(led)[0])


def test_by_tag_overlaps_and_by_slot_partitions(led):
    """Two different questions, two different shapes. by_slot sums to n_rows
    because one rule chose each row; by_tag does not, because membership
    overlaps."""
    bs.record_slate(_board(), min_edge=0.05, include_board_all=True, path=led)
    s = bs.summary(path=led)
    assert sum(v["n_rows"] for v in s["by_slot"].values()) == s["n_rows"]
    assert sum(v["n_rows"] for v in s["by_tag"].values()) > s["n_rows"]
    assert s["by_tag"][bs.BOARD_ALL_TAG]["n_rows"] == s["n_rows"]


# ---------------------------------------------------------------------------
# 3 + 4. the calibration ledger stays a probability ledger
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["stake_units", "bet_id", "roi", "profit_units",
                                 "clv_pct", "shadow_id", "edge"])
def test_a_calibration_row_refuses_anything_that_makes_it_a_bet(cal, bad):
    with pytest.raises(bc.CalibrationLedgerError):
        bc.append([{"cal_id": "x", "phase": "open", **{bad: 1}}], path=cal)


def test_the_closing_move_is_never_called_clv(cal):
    """CLV is a property of a POSITION. This ledger holds none, so the two names
    must stay apart or a later reader will concatenate them."""
    bc.record_slate(_board(), path=cal)
    row = bc.rows(path=cal)[0]
    key = (row["game_pk"], row["market"], row["side"],
           None if row["point"] is None else float(row["point"]))
    bc.append_close({key: {"odds": 120, "decimal": 2.2,
                           "book": row["best_book"]}}, path=cal)
    out = bc.rows(path=cal)[0]
    assert "market_move_pct" in out
    assert "clv_pct" not in out
    assert bc.summary(path=cal)["market_move_pct"]["n"] == 1


def test_a_close_at_a_different_book_is_not_a_move(cal):
    bc.record_slate(_board(), path=cal)
    row = bc.rows(path=cal)[0]
    key = (row["game_pk"], row["market"], row["side"],
           None if row["point"] is None else float(row["point"]))
    res = bc.append_close({key: {"odds": 120, "decimal": 2.2,
                                 "book": "some_other_book"}}, path=cal)
    assert res["n_book_mismatch"] == 1 and res["closed"] == 0


def test_a_settlement_cannot_rewrite_a_price(cal):
    """Each phase owns its own fields. A settle event that carried a price would
    be a ledger that edits its own evidence."""
    bc.record_slate(_board(), path=cal)
    cid = bc.rows(path=cal)[0]["cal_id"]
    with pytest.raises(bc.CalibrationLedgerError):
        bc.append([{"cal_id": cid, "phase": "settled", "result": "won",
                    "best_odds": -10000}], path=cal)


def test_the_calibration_ledger_has_no_floor(cal):
    """A side the model rated below the market is exactly as informative about
    calibration as one it liked. Filtering to the sides it liked would measure
    the curve only where the model disagrees with the market."""
    out = bc.record_slate(_board(), path=cal)
    assert out["written"] == 12, "both sides of three markets on two games"
    edges = [r.get("market_fair_prob") for r in bc.rows(path=cal)]
    assert all(e is not None for e in edges)


def test_calibration_reports_every_bin_including_the_empty_ones(cal):
    bc.record_slate(_board(), path=cal)
    bc.settle(games=_finals(), path=cal)
    bins = bc.summary(path=cal)["bins"]
    assert len(bins) == 10
    assert any(b["n"] == 0 for b in bins), "an empty bin is published, not dropped"
    assert all(b["actual"] is None for b in bins if b["n"] == 0)


def test_a_pooled_hit_rate_over_both_sides_is_not_published_as_a_measurement(cal):
    """Both sides of every binary are in this ledger, so a pooled mean
    probability and a pooled hit rate are 0.5 by arithmetic. They are computed
    on one canonical side per market instead."""
    bc.record_slate(_board(), path=cal)
    bc.settle(games=_finals(), path=cal)
    pooled = bc.summary(path=cal)["pooled"]
    assert "hit_rate" not in pooled and "mean_model_prob" not in pooled
    # Six canonical sides (home, home runline, over, on two games) minus the one
    # that pushed: PHI 8 WSN 1 lands exactly on the 9.0 total, and a push is not
    # a binary outcome so it carries no Brier and no hit.
    assert pooled["canonical_side"]["n"] == 5
    assert pooled["brier"] is not None, "Brier over both sides is still meaningful"


# ---------------------------------------------------------------------------
# 5. days_to_need is measured and says so
# ---------------------------------------------------------------------------
def test_days_to_need_carries_its_rate_and_admits_it_is_a_projection():
    rate = bl.measured_rate({bl._dates_back(3): 14})
    out = bl.days_to_need(10, 100, rate)
    assert out["is_projection"] is True
    assert out["rate"] == rate["per_day"]
    assert "measured" in out["note"].lower()
    assert str(rate["window_days"]) in out["rate_basis"]


def test_a_zero_rate_is_none_days_and_a_blocked_by_not_a_big_number():
    """"never, at the rate actually observed" is the honest answer, and a huge
    integer would read as an estimate."""
    out = bl.days_to_need(10, 100, bl.measured_rate({}))
    assert out["days"] is None
    assert out["blocked_by"] and "absence" in out["blocked_by"]


def test_the_rate_denominator_is_calendar_days_not_days_that_worked():
    """A night the box did not capture is a night the clock did not tick, for
    a series old enough to have seen the whole window."""
    r = bl.measured_rate({bl._dates_back(1): 28}, window=28,
                         series_start=bl._dates_back(60))
    assert r["n_dates_with_arrivals"] == 1
    assert r["per_day"] == 1.0, "28 arrivals over 28 calendar days, not over 1"


def test_a_young_series_divides_by_its_age_not_the_window():
    """The 504-day ETA bug: 19 arrivals over a 4-day-old series divided by 28
    published 0.68 a day against a true ~4.75. A 5-day-old series with 6 a day
    must read ~6, the basis must name the age, and the old figure must stay
    published beside it so the fix cannot read as a speed-up."""
    counts = {bl._dates_back(i): 6 for i in range(5)}
    r = bl.measured_rate(counts, series_start=bl._dates_back(4))
    assert r["series_age_days"] == 5
    assert r["effective_window_days"] == 5
    assert r["per_day"] == 6.0, "30 arrivals over the 5 days the series existed"
    assert r["per_day_28d"] == round(30 / 28, 4), "the full-window figure survives"
    assert "5 day(s) old" in r["basis"], "the basis names the age"


def test_a_requirement_already_met_is_zero_days_and_not_a_projection():
    out = bl.days_to_need(600, 600, bl.measured_rate({}))
    assert out["days"] == 0 and out["is_projection"] is False


# ---------------------------------------------------------------------------
# 5b. the gradable_games clock: the archive itself, toward ~900
# ---------------------------------------------------------------------------
def test_the_gradable_games_clock_counts_the_archive_toward_900():
    """n_graded is the eval window only; the fit window in front of it means
    600 graded games need roughly 900 gradable ones. This clock publishes that
    arithmetic so the runbook's ETA table and the artifact use one source."""
    first, last = bl._dates_back(27), bl._dates_back(0)
    evald = {"vintage": {"n_gradable": 280, "n_graded": 143,
                         "first_graded_date": first,
                         "last_graded_date": last}}
    c = bl._gradable_clock(evald, [])
    assert c["id"] == "gradable_games"
    assert c["have"] == 280
    assert c["need"] == 900, "600 eval-window games plus the 300-game fit window"
    assert "VINTAGE_FIT_TARGET_GAMES" in c["need_derivation"]
    assert c["rate"]["per_day"] == 10.0, "280 games over a 28-day span"
    assert c["eta"]["days"] == 62, "620 short at 10 a day"
    assert c["eta"]["is_projection"] is True


def test_the_gradable_clock_differences_its_own_history_once_it_has_one():
    history = [{"date": bl._dates_back(2), "vintage_n_gradable": 480},
               {"date": bl._dates_back(1), "vintage_n_gradable": 500}]
    c = bl._gradable_clock({"vintage": {"n_gradable": 507}}, history)
    assert c["rate"]["n_in_window"] == 20
    assert "history" in c["rate"]["basis"]
    assert c["direction"] == "up", "507 now against 500 in the last row"


# ---------------------------------------------------------------------------
# the market-move diagnosis walks the real chain
# ---------------------------------------------------------------------------
def test_the_empty_move_block_names_the_real_chain_not_the_clv_sidecar(tmp_path, monkeypatch):
    """The old text blamed data/betting_clv.json, the published record's CLV
    sidecar, which no calibration row is built from; and whenever that file
    existed it asserted a book mismatch nobody had measured. With no heartbeat
    and no attach result the honest diagnosis is: the close job never ran."""
    monkeypatch.setattr(bl, "CLOSE_JOB_HEARTBEAT_PATH", tmp_path / "hb.json")
    monkeypatch.setattr(bl, "CLOSE_ATTACH_RESULT_PATH", tmp_path / "attach.json")
    b = bl._market_move_block({"market_move_pct": {"n": 0}})["blocked_by"]
    assert "betting_clv.json" not in b, "the sidecar is not this ledger's repair"
    assert "never run" in b
    assert "close_events_for_calibration" in b and "append_close" in b
    assert "mismatch" not in b.lower(), (
        "a book mismatch may only be claimed off a persisted attach result")


def test_a_book_mismatch_is_only_claimed_off_a_persisted_attach_result(tmp_path, monkeypatch):
    hb, att = tmp_path / "hb.json", tmp_path / "attach.json"
    monkeypatch.setattr(bl, "CLOSE_JOB_HEARTBEAT_PATH", hb)
    monkeypatch.setattr(bl, "CLOSE_ATTACH_RESULT_PATH", att)
    hb.write_text(json.dumps({"last_run_utc": "2026-08-16T22:00:00+00:00",
                              "reason": "inside the closing window"}),
                  encoding="utf-8")

    # Scheduled but nothing persisted: the job's own state is reported and no
    # mismatch is invented.
    b = bl._market_move_block({"market_move_pct": {"n": 0}})["blocked_by"]
    assert "scheduled" in b and "mismatch" not in b.lower()

    # A persisted attach result that MEASURED mismatches may be cited.
    att.write_text(json.dumps({"slate_date": "2026-08-16", "closed": 0,
                               "n_no_close": 2, "n_book_mismatch": 3,
                               "written_at": "2026-08-16T22:00:05+00:00"}),
                   encoding="utf-8")
    b2 = bl._market_move_block({"market_move_pct": {"n": 0}})["blocked_by"]
    assert "3 book mismatch" in b2
    assert "2026-08-16" in b2, "the claim cites the persisted result"


# ---------------------------------------------------------------------------
# the gate table reads the ledger as it stands, not the eval's frozen copy
# ---------------------------------------------------------------------------
def test_the_gate_table_is_recomputed_not_copied_from_the_eval(tmp_path, monkeypatch):
    """The denominator trap, pinned: on 2026-08-16 the eval artifact's gate
    said board_all had 47 settled rows while the clocks, reading the live
    ledger the same night, said 72. The build must serve the recomputed gate,
    stamp computed_at, and keep the eval's copy as gates_as_of_eval."""
    import betting_model as bm

    stale = {"min_edge": None, "all_gates_open": False,
             "gates": [{"id": "graded_price_history", "have": 47,
                        "have_by_tag": {"board_all": 47}}]}
    fresh = {"min_edge": None, "all_gates_open": False,
             "gates": [{"id": "graded_price_history", "have": 72,
                        "have_by_tag": {"board_all": 72}}],
             "sweep": {"n_rows": 72}, "policy": "p", "odds_snapshot_dates": 9}
    (tmp_path / "betting_model_eval.json").write_text(
        json.dumps({"generated_at": "2026-08-16T18:02:46+00:00",
                    "vintage": {"n_graded": 258, "n_gradable": 507},
                    "min_edge_gate": stale}), encoding="utf-8")
    monkeypatch.setattr(bl, "DATA_DIR", tmp_path)
    monkeypatch.setattr(bm, "min_edge_gate", lambda vb, **kw: fresh)

    gates = bl.build(path=tmp_path / "series.json")["latest"]["gates"]
    served = {g["id"]: g for g in gates["gates"]}["graded_price_history"]
    assert served["have"] == 72, "the served gate counts the ledger as it stands"
    assert gates["computed_at"], "and is stamped with when it was computed"
    assert gates["verbatim_from"] == "betting_model.min_edge_gate"

    kept = {g["id"]: g for g in gates["gates_as_of_eval"]["gates"]}[
        "graded_price_history"]
    assert kept["have"] == 47, "the eval's frozen copy is kept, labelled, beside it"
    assert gates["gates_as_of_eval"]["as_of"] == "2026-08-16T18:02:46+00:00"


# ---------------------------------------------------------------------------
# 6 + 7. history is append-only, and counters may fall
# ---------------------------------------------------------------------------
def test_a_past_row_may_not_be_rewritten():
    past = [{"date": "2026-08-01", "vintage_n_graded": 100}]
    edited = [{"date": "2026-08-01", "vintage_n_graded": 999}]
    with pytest.raises(Exception) as exc:
        bl.merge_history(edited, {"date": "2026-08-02"}, on_disk=past)
    assert "append-only" in str(exc.value)


def test_todays_row_may_be_replaced_because_a_nightly_can_re_run():
    past = [{"date": "2026-08-01", "vintage_n_graded": 100},
            {"date": "2026-08-02", "vintage_n_graded": 110}]
    merged, _ = bl.merge_history(past, {"date": "2026-08-02",
                                        "vintage_n_graded": 118}, on_disk=past)
    assert len(merged) == 2
    assert merged[-1]["vintage_n_graded"] == 118


def test_a_row_appended_by_another_process_is_caught_not_clobbered():
    mine = [{"date": "2026-08-01", "vintage_n_graded": 100}]
    theirs = mine + [{"date": "2026-08-02", "vintage_n_graded": 110}]
    with pytest.raises(Exception):
        bl.merge_history(mine, {"date": "2026-08-03"}, on_disk=theirs)


def test_the_cap_drops_from_the_front_and_is_counted():
    past = [{"date": f"2026-01-{i:02d}", "n": i} for i in range(1, 6)]
    merged, info = bl.merge_history(past, {"date": "2026-02-01"}, cap=3,
                                    on_disk=past)
    assert len(merged) == 3
    assert info["n_dropped_by_cap"] == 3
    assert merged[-1]["date"] == "2026-02-01"


def test_a_counter_that_falls_renders_as_down():
    """The vintage sample shrinks when a refit changes the eligible window. No
    high-water mark, no smoothing, no carry-forward."""
    assert bl._direction(180, 211) == "down"
    assert bl._direction(211, 211) == "flat"
    assert bl._direction(240, 211) == "up"
    assert bl._direction(211, None) == "new"


def test_the_series_refuses_to_read_an_unreadable_file_as_empty(series):
    series.write_text("{not json", encoding="utf-8")
    with pytest.raises(bl.LearningSeriesError):
        bl.load(series)


def test_the_artifact_states_all_three_honesty_properties(series):
    built = bl.build(path=series)
    text = " ".join(built["latest"]["honesty"]).lower()
    assert "measured" in text
    assert "never rewritten" in text
    assert "backwards" in text


def test_the_gate_table_is_copied_verbatim_and_says_where_from(series):
    built = bl.build(path=series)
    assert built["latest"]["gates"]["verbatim_from"] == "betting_model.min_edge_gate"


def test_calibration_says_out_loud_that_it_is_not_gate_one(series):
    built = bl.build(path=series)
    note = built["latest"]["calibration"]["not_gate_1"].lower()
    assert "not" in note and "gate 1" in note


def test_the_closing_move_block_explains_itself_when_empty(series):
    built = bl.build(path=series)
    mm = built["latest"]["market_move"]
    if not mm["n"]:
        assert mm["blocked_by"], "an empty CLV-shaped block reads as 'no edge'"


# ---------------------------------------------------------------------------
# 8. one grader for every ledger
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("market,side,point,hr,ar,want", [
    ("moneyline", "home", None, 5, 3, "won"),
    ("moneyline", "away", None, 5, 3, "lost"),
    ("moneyline", "home", None, 4, 4, "push"),
    ("runline", "away", 1.5, 5, 4, "won"),
    ("runline", "home", -1.5, 5, 4, "lost"),
    ("runline", "home", -1.0, 5, 4, "push"),
    ("total", "over", 8.5, 5, 4, "won"),
    ("total", "under", 8.5, 5, 4, "lost"),
    ("total", "over", 9.0, 5, 4, "push"),
])
def test_one_grader_decides_every_market(market, side, point, hr, ar, want):
    assert bset.grade_side(market=market, side=side, point=point,
                           home_runs=hr, away_runs=ar) == want


def test_an_ungradeable_row_returns_none_rather_than_a_guess():
    assert bset.grade_side(market="total", side="over", point=None,
                           home_runs=5, away_runs=4) is None
    assert bset.grade_side(market="first_five", side="home", point=None,
                           home_runs=5, away_runs=4) is None
    assert bset.grade_side(market="moneyline", side="home", point=None,
                           home_runs=None, away_runs=None) is None


def test_the_shadow_ledger_and_the_calibration_ledger_agree(led, cal):
    """Two ledgers over the same game may never disagree about who covered."""
    games = _finals()
    bs.record_slate(_board(), min_edge=0.05, include_board_all=True, path=led)
    bs.settle(games=games, path=led)
    bc.record_slate(_board(), path=cal)
    bc.settle(games=games, path=cal)

    # game_pk is IN the key: both games carry a "+1.5 away runline" and keying
    # without it would compare two different bets and call them agreement.
    shadow = {(r["game_pk"], r["market"], r["side"], r.get("point")): r["result"]
              for r in bs.load(led) if r.get("result")}
    calib = {(r["game_pk"], r["market"], r["side"], r.get("point")): r["result"]
             for r in bc.rows(path=cal) if r.get("result")}
    common = set(shadow) & set(calib)
    assert common, "the two ledgers priced at least one identical side"
    for k in common:
        assert shadow[k] == calib[k], f"the two ledgers disagree about {k}"


def test_a_push_carries_no_binary_loss_and_a_refunded_stake():
    assert bset.binary_scores(0.55, "push") == {"brier": None, "log_loss": None}
    assert bset.profit_units(result="push", decimal=2.0) == 0.0


def test_a_certain_probability_that_loses_is_capped_not_infinite():
    out = bset.binary_scores(1.0, "lost")
    assert out["log_loss"] is not None and out["log_loss"] < 20


# ---------------------------------------------------------------------------
# 9. the catalog rows exist and carry stability
# ---------------------------------------------------------------------------
def test_every_catalog_row_carries_a_stability_key():
    """build_site subscripts row["stability"] bare at /sources/. A row without
    it does not degrade, it kills the page."""
    import data_catalog as dc
    for a in dc.ARTIFACTS:
        assert a.get("stability") in (dc.STABLE, dc.EXPERIMENTAL), a.get("file")
        assert a.get("group") in {k for k, _ in dc.GROUPS}, a.get("file")
        assert a.get("cadence") in ("daily", "monthly", "on change"), a.get("file")
        assert set(a) == {"file", "group", "title", "what", "cadence",
                          "stability", "pinned_by", "note"}, a.get("file")


def test_the_betting_artifacts_are_catalogued():
    """Only betting.json had a row before 2026-08-09; the other eight shipped to
    the webroot undocumented."""
    import data_catalog as dc
    catalogued = {a["file"] for a in dc.ARTIFACTS}
    for name in ("betting.json", "betting_preview.json", "betting_record.json",
                 "betting_shadow.json", "betting_learning.json",
                 "betting_clv.json", "betting_status.json",
                 "betting_model_eval.json", "betting_model_context.json"):
        assert name in catalogued, name


def test_a_catalogued_file_is_never_one_the_deploy_withholds():
    """A row for an excluded file would advertise a URL that 404s."""
    import data_catalog as dc
    withheld = dc.excluded_files()
    for a in dc.ARTIFACTS:
        if a["file"].startswith("betting"):
            assert a["file"] not in withheld, a["file"]


def test_the_learning_artifact_round_trips(series, tmp_path, monkeypatch):
    """build then run then load, with the history appended once."""
    monkeypatch.setattr(bl, "LEARNING_PATH", series)
    out = bl.run(path=series)
    assert out["n_history"] == 1
    again = bl.run(path=series)
    assert again["n_history"] == 1, "a same-day re-run replaces, never appends"
    assert json.loads(series.read_text(encoding="utf-8"))["latest"]["date"]
