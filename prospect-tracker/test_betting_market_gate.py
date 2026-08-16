# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The section 7b market-level publishability gate, pre-registered 2026-08-16.

The dispersion exclusion is a THEORY leg: it bars the runline and the total
because their margin model is known to be mis-shaped. This gate is the
EVIDENCE leg: it bars any market whose measured probabilities have RESOLVED
worse than a coin on the calibration ledger's settled canonical-side games,
and it re-opens the market when the trailing sample stops saying so. The rule
lives in docs/diamond-betting.md section 7b and was written there BEFORE the
code; these tests hold the code to that text.

THE THREE PRE-DECLARED MUTATIONS, each provably fatal here:
  * flip the comparison sign in the statistic  -> a losing market stops
    resolving and a winning one starts (the resolved / better-ledger pair);
  * drop the dwell                             -> a market closes on its first
    worse evaluation (the dwell sequence tests);
  * count rows instead of games                -> both sides of one game reach
    the n floor at half the games (the canonical-counting tests).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import betting_export as be
import betting_model as bm
import betting_shadow as bs
from tools import betting_calibration as bc

ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# synthetic ledgers
# ---------------------------------------------------------------------------
def _add_side(events: list, *, slate: str, game_pk: int, market: str,
              side: str, brier: float, point=None) -> None:
    cid = bc.cal_id(slate, game_pk, market, side, point)
    events.append({"cal_id": cid, "phase": bc.PHASE_OPEN, "written_at": "t",
                   "slate_date": slate, "game_pk": game_pk, "market": market,
                   "side": side, "point": point, "model_prob": 0.6})
    events.append({"cal_id": cid, "phase": bc.PHASE_SETTLED, "written_at": "t",
                   "result": "lost", "brier": brier, "settled_at": "t"})


def _ledger(tmp_path: Path, name: str, sides: list[tuple]) -> Path:
    """sides: (market, side, game_pk, brier[, point]) tuples -> a ledger file."""
    p = tmp_path / name
    events: list[dict] = []
    for spec in sides:
        market, side, game_pk, brier = spec[:4]
        point = spec[4] if len(spec) > 4 else None
        _add_side(events, slate="2026-08-01", game_pk=game_pk, market=market,
                  side=side, brier=brier, point=point)
    bc.append(events, path=p)
    return p


def _worse_moneyline(tmp_path: Path, n: int, name: str = "worse.jsonl") -> Path:
    """n canonical moneyline games whose mean Brier is 0.33: worse than a coin
    by 0.08 with a tiny per-game sd, so t is far above 1.645."""
    sides = [("moneyline", "home", i, 0.36 if i % 2 else 0.30)
             for i in range(n)]
    return _ledger(tmp_path, name, sides)


def _better_moneyline(tmp_path: Path, n: int, name: str = "better.jsonl") -> Path:
    """n canonical moneyline games at mean Brier 0.19: better than a coin."""
    sides = [("moneyline", "home", i, 0.16 if i % 2 else 0.22)
             for i in range(n)]
    return _ledger(tmp_path, name, sides)


_UTC = timezone.utc


def _day(d: int) -> datetime:
    return datetime(2026, 9, d, 4, 0, tzinfo=_UTC)


# ---------------------------------------------------------------------------
# the constants are mirrors, not inventions
# ---------------------------------------------------------------------------
def test_the_gate_constants_mirror_their_named_sources():
    """Section 7b: n=100 mirrors MIN_BETS_FOR_SWEEP, 1.645 is Z_95_ONE_SIDED,
    and the dwell of 3 and trailing 200 are POLICY. The copies in the ledger
    module exist so it keeps its single dependency; this is the pin that stops
    them drifting from the originals."""
    assert bc.GATE_MIN_GAMES == bs.MIN_BETS_FOR_SWEEP == 100
    assert bc.GATE_Z == bm.Z_95_ONE_SIDED == 1.645
    assert be.MARKET_GATE_DWELL == 3
    assert be.MARKET_GATE_TRAILING == 200


# ---------------------------------------------------------------------------
# the statistic
# ---------------------------------------------------------------------------
def test_worse_than_coin_resolves_at_n_100(tmp_path):
    p = _worse_moneyline(tmp_path, 120)
    g = bc.market_gate(path=p)["moneyline"]
    assert g["n_games"] == 120
    assert g["brier"] == pytest.approx(0.33, abs=1e-6)
    assert g["delta_vs_coin"] == pytest.approx(0.08, abs=1e-6)
    assert g["t"] >= bc.GATE_Z
    assert g["worse_than_coin_95"] is True


def test_small_samples_stay_unresolved_whatever_the_t(tmp_path):
    """The n floor is part of the verdict: 40 games at t far above the bar is
    still unresolved. The t assertion proves the floor, not the t, is what
    holds the verdict back."""
    p = _worse_moneyline(tmp_path, 40)
    g = bc.market_gate(path=p)["moneyline"]
    assert g["n_games"] == 40
    assert g["t"] >= bc.GATE_Z
    assert g["worse_than_coin_95"] is False


def test_a_better_than_coin_ledger_does_not_resolve(tmp_path):
    """The sign half of the mutation pair: flipping the comparison would make
    this winning ledger resolve worse-than-coin."""
    p = _better_moneyline(tmp_path, 120)
    g = bc.market_gate(path=p)["moneyline"]
    assert g["delta_vs_coin"] < 0
    assert g["worse_than_coin_95"] is False


def test_trailing_restricts_to_the_last_n_games(tmp_path):
    """150 bad games then 200 good ones: the full sample still resolves worse
    (mean 0.267, t about 3.4), the trailing 200 does not. This is the exact
    split the re-open rule reads. The bad half sits at mean 0.37 here rather
    than the helper's 0.33, because 150 at 0.33 plus 200 at 0.19 averages to
    exactly 0.25 and a mixture that IS the coin proves nothing."""
    sides = [("moneyline", "home", i, 0.40 if i % 2 else 0.34)
             for i in range(150)]
    sides += [("moneyline", "home", 1000 + i, 0.16 if i % 2 else 0.22)
              for i in range(200)]
    p = _ledger(tmp_path, "mixed.jsonl", sides)
    full = bc.market_gate(path=p)["moneyline"]
    trail = bc.market_gate(path=p, trailing=200)["moneyline"]
    assert full["n_games"] == 350 and full["worse_than_coin_95"] is True
    assert trail["n_games"] == 200 and trail["worse_than_coin_95"] is False
    assert trail["brier"] == pytest.approx(0.19, abs=1e-6)


# ---------------------------------------------------------------------------
# canonical-side counting: GAMES, never rows
# ---------------------------------------------------------------------------
def test_per_side_rows_do_not_double_count(tmp_path):
    """60 games with BOTH sides settled is 120 worse-than-coin rows and 60
    games. Counting rows would clear the 100 floor and resolve; counting games
    must not. This is the "count rows instead of games" mutation's grave."""
    sides = []
    for i in range(60):
        sides.append(("moneyline", "home", i, 0.36 if i % 2 else 0.30))
        sides.append(("moneyline", "away", i, 0.36 if i % 2 else 0.30))
    p = _ledger(tmp_path, "bothsides.jsonl", sides)
    g = bc.market_gate(path=p)["moneyline"]
    assert g["n_games"] == 60
    assert g["worse_than_coin_95"] is False


def test_two_lines_on_one_game_count_the_game_once(tmp_path):
    """A game settled at two total points is two canonical rows and ONE game.
    The live ledger really holds these (a moved line, a postponed game), which
    is why the dedupe is on game_pk and not on cal_id."""
    p = _ledger(tmp_path, "twolines.jsonl", [
        ("total", "over", 7, 0.30, 8.5),
        ("total", "over", 7, 0.36, 9.5),
        ("total", "over", 8, 0.30, 9.0),
    ])
    g = bc.market_gate(path=p)["total"]
    assert g["n_games"] == 2


def test_the_non_canonical_side_alone_contributes_nothing(tmp_path):
    """An away-side-only ledger holds no canonical games at all: the statistic
    is defined on one fixed side per market, chosen in CANONICAL_SIDES before
    any data was seen."""
    p = _ledger(tmp_path, "away.jsonl",
                [("moneyline", "away", i, 0.36) for i in range(120)])
    g = bc.market_gate(path=p)["moneyline"]
    assert g["n_games"] == 0
    assert g["worse_than_coin_95"] is False


# ---------------------------------------------------------------------------
# the dwell: 3 consecutive nightly evaluations, one per UTC day
# ---------------------------------------------------------------------------
def _eval(cal, state, day, **kw):
    return be.market_gate_evaluate(cal_path=cal, state_path=state,
                                   now=_day(day), **kw)


def test_one_worse_evaluation_does_not_close(tmp_path):
    """THE DWELL, half one: a single resolved-worse evaluation leaves the
    market open at counter 1. Dropping the dwell closes it here."""
    cal = _worse_moneyline(tmp_path, 120)
    state = tmp_path / "state.json"
    t = _eval(cal, state, 1)
    leg = t["markets"]["moneyline"]["ledger_leg"]
    assert leg["worse_than_coin_95"] is True
    assert leg["status"] == "open"
    assert leg["consecutive_worse"] == 1
    assert t["markets"]["moneyline"]["publishable"] is True


def test_three_consecutive_worse_evaluations_close(tmp_path):
    cal = _worse_moneyline(tmp_path, 120)
    state = tmp_path / "state.json"
    _eval(cal, state, 1)
    t2 = _eval(cal, state, 2)
    assert t2["markets"]["moneyline"]["ledger_leg"]["status"] == "open"
    t3 = _eval(cal, state, 3)
    leg = t3["markets"]["moneyline"]["ledger_leg"]
    assert leg["status"] == "ledger_closed"
    assert t3["markets"]["moneyline"]["publishable"] is False
    assert "LEDGER-CLOSED" in t3["markets"]["moneyline"]["reason"]
    assert be.ledger_closed_markets(path=state) == frozenset({"moneyline"})


def test_a_broken_streak_resets_the_dwell(tmp_path):
    """worse, worse, recovered, worse must NOT close: the counter is
    consecutive, not cumulative."""
    bad = _worse_moneyline(tmp_path, 120)
    good = _better_moneyline(tmp_path, 120)
    state = tmp_path / "state.json"
    _eval(bad, state, 1)
    _eval(bad, state, 2)
    t3 = _eval(good, state, 3)
    assert t3["markets"]["moneyline"]["ledger_leg"]["consecutive_worse"] == 0
    t4 = _eval(bad, state, 4)
    leg = t4["markets"]["moneyline"]["ledger_leg"]
    assert leg["status"] == "open"
    assert leg["consecutive_worse"] == 1


def test_two_runs_on_one_day_advance_the_dwell_once(tmp_path):
    """"3 consecutive nightly evaluations" means three NIGHTS. A pipeline that
    runs three times in one afternoon must not close a market in a day."""
    cal = _worse_moneyline(tmp_path, 120)
    state = tmp_path / "state.json"
    for _ in range(3):
        t = _eval(cal, state, 1)
    leg = t["markets"]["moneyline"]["ledger_leg"]
    assert leg["consecutive_worse"] == 1
    assert leg["status"] == "open"


def test_the_reopen_path_needs_three_recovered_evaluations(tmp_path):
    """Close on the bad ledger, hold closed while the trailing sample still
    resolves worse, then re-open only after 3 consecutive evaluations whose
    trailing 200 fail to resolve worse-than-coin."""
    bad = _worse_moneyline(tmp_path, 120)
    good = _better_moneyline(tmp_path, 220)
    state = tmp_path / "state.json"
    for d in (1, 2, 3):
        _eval(bad, state, d)
    assert be.ledger_closed_markets(path=state) == frozenset({"moneyline"})
    # day 4 on the bad ledger: trailing still resolves worse, no recovery
    t4 = _eval(bad, state, 4)
    leg4 = t4["markets"]["moneyline"]["ledger_leg"]
    assert leg4["status"] == "ledger_closed"
    assert leg4["consecutive_recovered"] == 0
    # three recovered evaluations on the good ledger re-open it
    t5 = _eval(good, state, 5)
    assert t5["markets"]["moneyline"]["ledger_leg"]["consecutive_recovered"] == 1
    assert t5["markets"]["moneyline"]["ledger_leg"]["status"] == "ledger_closed"
    _eval(good, state, 6)
    t7 = _eval(good, state, 7)
    leg7 = t7["markets"]["moneyline"]["ledger_leg"]
    assert leg7["status"] == "open"
    assert t7["markets"]["moneyline"]["publishable"] is True
    assert be.ledger_closed_markets(path=state) == frozenset()


def test_a_recovery_streak_resets_on_a_worse_trailing_read(tmp_path):
    """recovered, recovered, worse must not re-open on the next recovery: the
    re-open counter is consecutive too."""
    bad = _worse_moneyline(tmp_path, 120)
    good = _better_moneyline(tmp_path, 220)
    state = tmp_path / "state.json"
    for d in (1, 2, 3):
        _eval(bad, state, d)
    _eval(good, state, 4)
    _eval(good, state, 5)
    t6 = _eval(bad, state, 6)
    assert t6["markets"]["moneyline"]["ledger_leg"]["consecutive_recovered"] == 0
    t7 = _eval(good, state, 7)
    leg = t7["markets"]["moneyline"]["ledger_leg"]
    assert leg["status"] == "ledger_closed"
    assert leg["consecutive_recovered"] == 1


def test_write_false_does_not_persist_the_advance(tmp_path):
    cal = _worse_moneyline(tmp_path, 120)
    state = tmp_path / "state.json"
    _eval(cal, state, 1, write=False)
    assert not state.exists()
    t = _eval(cal, state, 2)
    assert t["markets"]["moneyline"]["ledger_leg"]["consecutive_worse"] == 1


# ---------------------------------------------------------------------------
# the combined table
# ---------------------------------------------------------------------------
def test_the_table_ands_the_two_legs(tmp_path):
    """Moneyline can be barred by the ledger leg alone; runline and total are
    barred by the dispersion leg even while their ledger legs are open. The
    combined `publishable` is the AND, with the failing leg named."""
    cal = _worse_moneyline(tmp_path, 120)
    state = tmp_path / "state.json"
    for d in (1, 2, 3):
        t = _eval(cal, state, d)
    mkts = t["markets"]
    assert mkts["moneyline"]["publishable"] is False
    assert mkts["moneyline"]["dispersion_leg"]["publishable"] is True
    assert mkts["moneyline"]["ledger_leg"]["status"] == "ledger_closed"
    for m in ("runline", "total"):
        assert mkts[m]["publishable"] is False
        assert mkts[m]["dispersion_leg"]["publishable"] is False
        assert mkts[m]["ledger_leg"]["status"] == "open"
        assert "dispersion" in mkts[m]["reason"]
    assert bm.SERVE_RUN_DISPERSION is False, (
        "the dispersion premise moved; re-read these expectations")


def test_the_table_says_it_can_close_nothing_under_the_floor(tmp_path):
    """Section 7b's honesty clause: with every market under 100 canonical
    games the table must say the ledger leg closes nothing, with the counts."""
    p = _ledger(tmp_path, "tiny.jsonl", [("moneyline", "home", 1, 0.36)])
    t = be.market_publishability(cal_path=p, state_path=tmp_path / "none.json")
    assert t["today_note"] is not None
    assert "closes nothing" in t["today_note"]
    assert "moneyline 1" in t["today_note"]
    assert t["markets"]["moneyline"]["ledger_leg"]["verdict"] == "unresolved"
    assert t["policy"]["dwell"] == 3 and t["policy"]["trailing"] == 200
    assert "POLICY" in t["policy"]["basis"]


# ---------------------------------------------------------------------------
# the two seams
# ---------------------------------------------------------------------------
def _board():
    """One game with a huge clearing edge in all three markets, so absence
    means EXCLUDED, not failed-to-clear (the dispersion file's device)."""
    row = lambda side, edge: {          # noqa: E731
        "side": side, "edge": edge, "odds": -110, "book": "testbook",
        "model_prob": 0.60, "market_fair_prob": 0.60 - edge, "kelly_full": 0.2,
    }
    return [{
        "game_pk": 1, "start": "2026-08-16T23:05:00Z",
        "away": {"org": "AAA"}, "home": {"org": "BBB"},
        "moneyline": [row("home", 0.20)],
        "runline": [row("home", 0.30)],
        "total": {"sides": [row("over", 0.40)]},
    }]


def test_seam_1_a_ledger_closed_market_fills_no_slot():
    control = be._floor_clearing_sides(_board(), 0.06, ledger_closed=frozenset())
    assert {c["market"] for c in control} == {"moneyline"}
    cands = be._floor_clearing_sides(_board(), 0.06,
                                     ledger_closed=frozenset({"moneyline"}))
    assert cands == []


def test_seam_1_reads_the_persisted_state_by_default(tmp_path, monkeypatch):
    """No injection: the seam consults the state file the nightly evaluation
    wrote. This is the wiring a slot selection actually runs through."""
    cal = _worse_moneyline(tmp_path, 120)
    state = tmp_path / "state.json"
    for d in (1, 2, 3):
        _eval(cal, state, d)
    monkeypatch.setattr(be, "MARKET_GATE_STATE_PATH", state)
    assert be._floor_clearing_sides(_board(), 0.06) == []
    monkeypatch.setattr(be, "MARKET_GATE_STATE_PATH", tmp_path / "absent.json")
    assert {c["market"] for c in be._floor_clearing_sides(_board(), 0.06)} \
        == {"moneyline"}


def test_seam_2_append_record_refuses_a_ledger_closed_market(tmp_path):
    p = tmp_path / "record.json"
    p.write_text("[]", encoding="utf-8")
    rows = [{"bet_id": "a", "market": "h2h", "side": "home"},
            {"bet_id": "b", "market": "moneyline", "side": "home"}]
    out = be.append_record(rows, path=p, ledger_closed=frozenset({"moneyline"}))
    assert out == []
    assert json.loads(p.read_text(encoding="utf-8")) == []
    control = be.append_record(rows, path=p, ledger_closed=frozenset())
    assert [r["bet_id"] for r in control] == ["a", "b"]


def test_seam_2_dispersion_guard_now_reads_the_feed_vocabulary(tmp_path):
    """THE VOCABULARY REPAIR, pinned. record_row writes `market` as the FEED
    key (h2h / spreads / totals), and the funnel guard used to test that raw
    key against a board-name exclusion list, so "spreads" and "totals" walked
    straight past it. Both legs now see the canonical board name."""
    p = tmp_path / "record.json"
    p.write_text("[]", encoding="utf-8")
    rows = [{"bet_id": "a", "market": "h2h", "side": "home"},
            {"bet_id": "b", "market": "spreads", "side": "home"},
            {"bet_id": "c", "market": "totals", "side": "over"}]
    out = be.append_record(rows, path=p, ledger_closed=frozenset())
    assert [r["bet_id"] for r in out] == ["a"], (
        "a feed-vocabulary runline or total reached the public record past "
        "the dispersion exclusion")


def test_the_shadow_ledger_does_not_consult_the_market_gate():
    """THE NON-CONSULTATION, pinned the way test_betting_dispersion_exclusion
    pins it for the theory leg. The paper ledger and the calibration ledger
    are the only instruments that accumulate the settled evidence a closed
    market needs to ever RE-OPEN; consulting the gate there would freeze every
    closure permanently. Read section 7b before changing this."""
    src = (ROOT / "betting_shadow.py").read_text(encoding="utf-8")
    for token in ("market_gate", "ledger_closed", "market_publishability"):
        assert token not in src, (
            f"betting_shadow.py now mentions {token!r}; extending the market "
            "gate to the paper ledger deletes the evidence that could re-open "
            "a closed market (docs/diamond-betting.md section 7b)")
    cal_src = (ROOT / "tools" / "betting_calibration.py").read_text(encoding="utf-8")
    assert "record_slate" in cal_src and "market_gate" in cal_src, (
        "the calibration ledger must keep recording every market AND carry "
        "the gate statistic; it holds probabilities, not publish decisions")
