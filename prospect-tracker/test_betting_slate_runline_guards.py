# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Four guards on the board's two entry seams: which DATE it is, and which
POSTED NUMBER it prices. Audit items L14-04, L14-06, L14-08 and L14-12.

None of these is a pricing change. No probability moves, no edge moves, no
selection moves, and `betting_model.MODEL_VERSION` is untouched: every one of
the four either refuses a case the module had no number for, restores a
denominator, or makes a published sentence say what the code does.

  L14-04  `_slate_is_open` read TWO signals for "this game has started", the
          status and the clock, and excluded postponements from the first one
          only. A postponed game keeps its scheduled `datetime`, so once that
          time passed it counted as started anyway - the exact thing the
          exclusion's own comment forbids. Three postponements and one real
          night game made a live card read as a 0.25 fragment; the mirror case
          gave a 0.75 pregame share to a date with nothing bettable on it.
          A called-off row is now in neither half and leaves the denominator,
          which is published beside the counts.

  L14-06  `team_bets` read only the SIGN of the posted spread point. A posted
          -2.5 would have been labelled "-2.5" and priced with P(margin >= 2),
          and an INTEGER runline - which the feed carries - would have been
          priced with no `p_push` at all, as a market that cannot refund, while
          `betting_settle.grade_side` grades a spread push correctly. What kept
          the served board clean was incidental: every one of the 29 events in
          the cache posted away from +/-1.5 is in progress and dropped upstream
          for an unrelated reason. The guard refuses and says why.

  L14-12  `resolve_slate(on_date)` returned before the started-rows filter, so
          an explicit-date rebuild served rows the filter would have dropped and
          published `started_rows_dropped: null` - the same value the no-slate
          branch writes, so a reader could not tell "no started rows" from "the
          filter never ran". Plan stop-item X5.

  L14-08  `market_publishability.note` stated the both-legs rule
          unconditionally while `policy.slot_market_policy_note` beside it was
          switched on the policy. Under the any-market policy the payload
          carried two contradictory statements of one rule, and the published
          Pick of the Day broke the one stated in `note`.

MEASURED 2026-09-17, so the tests below can be read as regression pins rather
than as claims. Over the 31 cached snapshots in `.cache/odds`, 492 pregame
events carry a two-sided spread view and every one is posted at +/-1.5,
mirrored, with a point on both sides, so the L14-06 guard refuses nothing that
has ever reached a board; the served board's 15 runline pairs all clear it too,
while all 30 in-game spread views posted away from +/-1.5 were already dropped
upstream. The L14-04 case is latent as well: of 1,317 cached schedule rows none
carries a postponed, cancelled or suspended state, so no candidate row's share
moves today either.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

be = pytest.importorskip("betting_export")
bi = pytest.importorskip("betting_ingest")
bm = pytest.importorskip("betting_model")

ROOT = Path(__file__).parent
ODDS_DIR = ROOT / ".cache" / "odds"

NOW = datetime(2026, 9, 10, 23, 30, tzinfo=timezone.utc)
DAY = "2026-09-10"


def _row(status: str, *, hours: float, pk: int = 0, home="SEA", away="TBR") -> dict:
    """One schedule row, `hours` from NOW (negative is behind us)."""
    return {"game_pk": pk, "date": DAY, "status": status,
            "datetime": (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z"),
            "home": {"org": home, "team": home}, "away": {"org": away, "team": away}}


# ===========================================================================
# L14-04: a called-off game is in neither half of the share
# ===========================================================================
def test_a_postponement_behind_the_clock_is_not_a_started_game():
    """CASE B, the defect. Three games postponed hours ago plus one real night
    game still to come. Every postponed row's scheduled first pitch is behind
    us, so the clock signal called the card three quarters played and the board
    fell through to the partial-slate fallbacks, publishing prose that calls a
    live card a fragment."""
    rows = [_row("Postponed", hours=-3, pk=i) for i in range(3)]
    rows.append(_row("Preview", hours=2, pk=9))
    counts: dict = {}
    is_open, why_not = be._slate_is_open(DAY, rows, NOW, counts=counts)
    assert is_open, why_not
    assert why_not is None
    assert counts["n_called_off"] == 3
    assert counts["n_started"] == 0
    assert counts["n_pregame"] == 1
    assert counts["n_playable"] == 1
    assert counts["pregame_share"] == 1.0


def test_a_postponement_ahead_of_the_clock_is_not_a_pregame_game():
    """CASE A, the mirror. One game already under way and three postponements
    whose scheduled time has not arrived: the old rule read a 0.75 pregame
    share on a date with zero bettable games, and `slate_candidates[]` is a
    served field, so that share was a published claim about a card nobody can
    bet."""
    rows = [_row("In Progress", hours=-1, pk=0)]
    rows += [_row("Postponed", hours=3, pk=i) for i in range(1, 4)]
    counts: dict = {}
    is_open, why_not = be._slate_is_open(DAY, rows, NOW, counts=counts)
    assert not is_open
    assert counts["n_called_off"] == 3
    assert counts["n_started"] == 1
    assert counts["n_pregame"] == 0
    assert counts["n_playable"] == 1
    assert counts["pregame_share"] == 0.0
    assert "1 have already started" in why_not
    assert "3 of them called off" in why_not


def test_the_share_denominator_is_the_playable_card():
    """The verdict is a proportion, and the question the proportion answers is
    "of the games that CAN be played, how many are still ahead". Six playable
    games with three still to come is exactly the threshold whatever number of
    postponements sits beside them."""
    playable = ([_row("Final", hours=-4, pk=i) for i in range(3)]
                + [_row("Preview", hours=2, pk=10 + i) for i in range(3)])
    for n_off in range(0, 5):
        rows = playable + [_row("Postponed", hours=-2, pk=100 + i) for i in range(n_off)]
        counts: dict = {}
        is_open, _ = be._slate_is_open(DAY, rows, NOW, counts=counts)
        assert counts["n_playable"] == 6
        assert counts["pregame_share"] == 0.5
        assert is_open is True, n_off


def test_a_date_with_every_game_called_off_is_not_a_board():
    """No card to price, and the reason says that rather than dividing by a
    denominator of zero."""
    rows = [_row("Postponed", hours=-2, pk=i) for i in range(4)]
    counts: dict = {}
    is_open, why_not = be._slate_is_open(DAY, rows, NOW, counts=counts)
    assert not is_open
    assert "every one of them is called off" in why_not
    assert counts["n_playable"] == 0
    assert counts["pregame_share"] is None


def test_every_called_off_state_the_deny_list_carries_is_read_the_same_way():
    """The set is not a second spelling table: every state here is one
    `is_bettable` already refuses, so a called-off row can never reach the board
    through the slate rule."""
    for st in sorted(be.SLATE_CALLED_OFF_STATES):
        g = _row(st, hours=-3)
        assert be._is_called_off(g) is True, st
        assert be._has_started(g, NOW) is False, st
        assert st in be.NOT_BETTABLE_STATES, st
        assert not be.is_bettable(g), st


def test_the_slate_rule_and_the_board_filter_share_one_definition():
    """`_slate_is_open` carried its own inline copy of the two signals, which is
    how the two could disagree about a postponement in the first place."""
    for st, hours, want in (("Preview", 2, False), ("Preview", -2, True),
                            ("In Progress", 3, True), ("Final", 3, True),
                            ("Postponed", -2, False), ("Postponed", 2, False)):
        assert be._has_started(_row(st, hours=hours), NOW) is want, (st, hours)


def test_a_doubleheader_half_played_is_still_exactly_at_the_threshold():
    """The boundary case the share rule was written around, kept shut."""
    rows = [_row("In Progress", hours=-1, pk=0), _row("Preview", hours=3, pk=1)]
    is_open, _ = be._slate_is_open(DAY, rows, NOW)
    assert is_open is True


def test_the_candidate_row_publishes_the_denominator(monkeypatch):
    """`n_called_off` and `n_playable` ride the served candidate row, so the
    share can be checked against the game count beside it instead of inferred."""
    rows = [_row("Postponed", hours=-3, pk=i) for i in range(3)]
    rows.append(_row("Preview", hours=2, pk=9))
    monkeypatch.setattr(be, "_load",
                        lambda name: ({"schedule": {"games": rows}}
                                      if name == "fantasy.json" else None))
    stats: dict = {}
    day, board = be.resolve_slate(now=NOW, stats=stats, priceable={})
    assert day == DAY
    assert len(board) == 1, "the three postponed rows are unbettable"
    cand = stats["slate_candidates"][0]
    assert cand["n_games"] == 4
    assert cand["n_called_off"] == 3
    assert cand["n_playable"] == 1
    assert cand["n_started"] + cand["n_pregame"] == cand["n_playable"]
    assert cand["open"] is True


# ===========================================================================
# L14-12 / X5: the explicit-date path runs the started filter too
# ===========================================================================
def _explicit(monkeypatch, rows):
    monkeypatch.setattr(be, "_load",
                        lambda name: ({"schedule": {"games": rows}}
                                      if name == "fantasy.json" else None))
    stats: dict = {}
    day, board = be.resolve_slate(DAY, now=NOW, stats=stats)
    return day, board, stats


def test_an_explicit_date_build_drops_the_rows_whose_first_pitch_has_passed(monkeypatch):
    """THE DEFECT. A stale-Preview row whose first pitch has passed reached the
    board on this path, and the payload said nothing had been filtered."""
    rows = [_row("Preview", hours=-2, pk=0), _row("Preview", hours=-1, pk=1),
            _row("Preview", hours=2, pk=2), _row("Preview", hours=3, pk=3)]
    day, board, stats = _explicit(monkeypatch, rows)
    assert day == DAY, "the date named is still the date served"
    assert stats["slate_rule"] == "explicit_date"
    assert [g["game_pk"] for g in board] == [2, 3]
    drop = stats["started_rows_dropped"]
    assert drop is not None, "null cannot distinguish 'none dropped' from 'never ran'"
    assert drop["applied"] is True
    assert drop["n"] == 2 and drop["n_on_slate"] == 4
    assert {g["game_pk"] for g in drop["games"]} == {0, 1}


def test_an_explicit_date_build_with_nothing_dropped_still_says_the_filter_ran(monkeypatch):
    """Zero is a measurement and null is an absence. The two cases were
    indistinguishable on the payload, which is half of what made this live."""
    rows = [_row("Preview", hours=2, pk=i) for i in range(3)]
    day, board, stats = _explicit(monkeypatch, rows)
    assert day == DAY and len(board) == 3
    drop = stats["started_rows_dropped"]
    assert drop["n"] == 0 and drop["applied"] is True


def test_an_explicit_date_whose_whole_card_has_started_is_not_blanked(monkeypatch):
    """The walk's own rule, now reached by both paths: a blank page is worse
    than a stale one, and the count still says what happened."""
    rows = [_row("Preview", hours=-2, pk=i) for i in range(3)]
    day, board, stats = _explicit(monkeypatch, rows)
    assert day == DAY and len(board) == 3
    drop = stats["started_rows_dropped"]
    assert drop["applied"] is False and drop["n"] == 3


def test_the_walk_and_the_explicit_date_reach_the_same_filter(monkeypatch):
    """One function, so the two paths cannot drift into disagreeing about which
    games are gone."""
    rows = [_row("Preview", hours=-2, pk=0), _row("Preview", hours=2, pk=1)]
    monkeypatch.setattr(be, "_load",
                        lambda name: ({"schedule": {"games": rows}}
                                      if name == "fantasy.json" else None))
    walk_stats: dict = {}
    _, walk_board = be.resolve_slate(now=NOW, stats=walk_stats, priceable={})
    exp_stats: dict = {}
    _, exp_board = be.resolve_slate(DAY, now=NOW, stats=exp_stats)
    assert [g["game_pk"] for g in walk_board] == [g["game_pk"] for g in exp_board]
    assert walk_stats["started_rows_dropped"]["n"] == exp_stats["started_rows_dropped"]["n"]


# ===========================================================================
# L14-06: the posted runline point
# ===========================================================================
TEAMS = {
    "_scale": {"prev_mu": 100.0, "prev_sd": 10.0},
    "SEA": {"z_off": 0.20, "offense_plus": 104.0, "bullpen_plus": 104.0,
            "rotation_plus": 104.0, "sp_ip_share": 0.60},
    "TBR": {"z_off": -0.10, "offense_plus": 98.0, "bullpen_plus": 99.0,
            "rotation_plus": 101.0, "sp_ip_share": 0.60},
}
PARKS = {"SEA": 0.96}
FIRST_PITCH = datetime(2026, 9, 10, 23, 40, tzinfo=timezone.utc)


def _game() -> dict:
    return {"game_pk": 1, "date": DAY, "status": "Preview",
            "datetime": FIRST_PITCH.isoformat().replace("+00:00", "Z"),
            "double_header": False,
            "home": {"org": "SEA", "team": "SEA"},
            "away": {"org": "TBR", "team": "TBR"}}


def _event(point: float | None, *, away_point: float | None = None) -> dict:
    """One pregame event with a two-sided moneyline and a two-sided spread at
    `point` for the home side. Two books, so the de-vig has a choice to make and
    the spread view is built exactly as it is on a real board."""
    def spread(pt, away_pt, hp, ap):
        cell = {}
        if pt is not None:
            cell["home"] = {"price": hp, "point": pt}
        if away_pt is not None:
            cell["away"] = {"price": ap, "point": away_pt}
        return cell

    ap_point = away_point if away_point is not None else (
        None if point is None else -point)
    return {
        "event_id": "e1",
        "commence_time": FIRST_PITCH.isoformat().replace("+00:00", "Z"),
        "home_team": "SEA", "away_team": "TBR",
        "home_org": "SEA", "away_org": "TBR",
        "books": {
            "fanduel": {"title": "FanDuel", "last_update": "2026-09-10T22:00:00Z",
                        "h2h": {"home": -136, "away": 126},
                        "spreads": spread(point, ap_point, -110, -110)},
            "draftkings": {"title": "DraftKings", "last_update": "2026-09-10T22:00:00Z",
                           "h2h": {"home": -134, "away": 124},
                           "spreads": spread(point, ap_point, -115, -105)},
        },
    }


def _bets(event, now=None):
    stats: dict = {}
    rows = be.team_bets([_game()], [event], teams=TEAMS, parks=PARKS, starters={},
                        now=now or datetime(2026, 9, 10, 22, 0, tzinfo=timezone.utc),
                        stats=stats)
    return rows[0], stats


def test_the_ordinary_runline_is_unchanged_with_the_home_side_favoured():
    """The premise for every refusal below: +/-1.5 still prices, both rows, and
    the labels still come off the posted point."""
    row, stats = _bets(_event(-1.5))
    assert row["runline_refused"] is None
    assert stats["n_runline_refused"] == 0
    labels = [r["label"] for r in row["runline"]]
    assert labels == ["SEA -1.5", "TBR +1.5"]
    assert [r["point"] for r in row["runline"]] == [-1.5, 1.5]
    assert all(r["model_prob"] is not None for r in row["runline"])
    assert all(r["p_push"] is None for r in row["runline"]), (
        "a half point cannot push and must not carry push mass")


def test_the_ordinary_runline_is_unchanged_with_the_away_side_favoured():
    row, _ = _bets(_event(1.5))
    assert row["runline_refused"] is None
    assert [r["label"] for r in row["runline"]] == ["SEA +1.5", "TBR -1.5"]


def test_an_alternate_point_is_refused_rather_than_priced_at_one_and_a_half():
    """THE DEFECT. A posted -2.5 was labelled "-2.5" and priced with
    P(margin >= 2), because only the SIGN of the point was ever read."""
    row, stats = _bets(_event(-2.5))
    assert row["runline"] is None
    assert stats["n_runline_refused"] == 1
    assert "2.5" in row["runline_refused"]
    assert "prices only 1.5" in row["runline_refused"]
    ref = stats["runline_refusals"][0]
    assert ref["game_pk"] == 1 and ref["matchup"] == "TBR at SEA"
    assert ref["home_point"] == -2.5 and ref["away_point"] == 2.5


def test_an_integer_runline_is_refused_because_it_can_push():
    """The feed carries integer spreads. `_priced_side` was called with no
    `p_push`, so the EV of a market that refunds was computed as if every
    non-win were a loss - the exact defect `total_side_probabilities` fixed for
    totals, and `betting_settle.grade_side` grades a spread push correctly, so
    the grader and the pricer disagreed about whether a runline can push."""
    row, stats = _bets(_event(-2.0))
    assert row["runline"] is None
    assert stats["n_runline_refused"] == 1
    assert "pushes" in row["runline_refused"]
    assert "no push mass" in row["runline_refused"]


def test_a_one_run_integer_line_is_refused_too():
    """-1.0 is the nearest integer to the line the model prices and is the most
    tempting thing to wave through. It still pushes."""
    row, _ = _bets(_event(-1.0))
    assert row["runline"] is None


def test_a_spread_with_no_point_on_one_side_is_refused():
    """Which team has to win by two is not stated anywhere in the quote."""
    mv = {"best": {"home": {"point": -1.5}, "away": {"price": -110}}}
    reason = be.runline_point_refusal(mv)
    assert reason and "no point on at least one side" in reason


def test_two_sides_posted_at_different_numbers_are_not_one_bet():
    """Defence in depth: `_market_view` picks one consensus point and mirrors it
    itself (the 2026-08-06 line-mismatch fix), so this cannot fire off the
    shipped path. It is asserted because the pair is what makes the two
    probabilities a pair."""
    mv = {"best": {"home": {"point": -1.5}, "away": {"point": 2.5}}}
    reason = be.runline_point_refusal(mv)
    assert reason and "not one line" in reason


def test_a_game_with_no_spread_posted_at_all_is_not_a_refusal():
    """No spread view is the ordinary quiet case and must not read as a guard
    firing, or the count stops meaning anything."""
    ev = _event(None)
    row, stats = _bets(ev)
    assert row["runline"] is None
    assert row["runline_refused"] is None
    assert stats["n_runline_refused"] == 0


def test_the_refusal_takes_only_the_runline_and_leaves_the_game_priced():
    """A refused spread is not a refused game: the moneyline and the model's own
    numbers still ship, which is the difference between a guard and an outage."""
    row, _ = _bets(_event(-2.5))
    assert row["moneyline"][0]["edge"] is not None
    assert row["model"]["p_home"] is not None
    assert row["odds_event_id"] == "e1"


def test_the_only_point_this_module_prices_is_named_once():
    assert be.RUNLINE_POINT == 1.5
    assert be.runline_point_refusal(
        {"best": {"home": {"point": -be.RUNLINE_POINT},
                  "away": {"point": be.RUNLINE_POINT}}}) is None


@pytest.mark.skipif(not ODDS_DIR.is_dir(), reason="no cached odds snapshots")
def test_the_guard_refuses_nothing_the_cache_has_ever_posted_pregame():
    """THE MEASUREMENT, as a test. Every pregame two-sided spread in every
    cached snapshot is posted at +/-1.5, mirrored, with a point on both sides,
    so this guard costs the board nothing that has ever reached it. The events
    posted away from +/-1.5 are all in progress, which is the incidental
    protection this replaces with a stated one."""
    n_pregame = n_refused = n_started_off_line = 0
    for path in sorted(ODDS_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        cap = be._stamp(raw.get("captured_at") or raw.get("fetched_at"))
        if cap is None:
            continue
        for ev in bi.parse_events(raw) or []:
            mv = be._market_view(ev, "spreads", ("home", "away"))
            if not mv:
                continue
            reason = be.runline_point_refusal(mv)
            if bi.odds_event_started(ev, cap):
                n_started_off_line += 1 if reason else 0
                continue
            n_pregame += 1
            n_refused += 1 if reason else 0
    assert n_pregame >= 400, f"the cache thinned out: {n_pregame} pregame spread views"
    assert n_refused == 0, f"{n_refused} of {n_pregame} pregame spreads refused"
    assert n_started_off_line > 0, (
        "the premise of the finding: the off-line points exist and are in-game")


# ===========================================================================
# L14-08: one rule, one sentence
# ===========================================================================
def _publishability() -> dict:
    """The table off a fixed, empty gate state, so this reads the SENTENCE and
    not the ledger."""
    return be.market_publishability(
        state={"markets": {}, "last_evaluation_date": None},
        full={m: {"n_games": 0, "n_min": 100, "z": 1.645} for m in be.GATED_MARKETS},
        trailing={m: {"n_games": 0} for m in be.GATED_MARKETS})


def test_the_note_and_the_policy_field_state_the_same_rule():
    """THE DEFECT. `note` was written unconditionally while the field beside it
    was switched on the policy, so the payload carried two statements of one
    rule and today's published Pick of the Day broke one of them."""
    table = _publishability()
    note = table["note"]
    pol = table["policy"]
    any_policy = pol["slot_market_policy"] == "any"
    assert ("must clear BOTH legs" in note) is not any_policy
    assert ("may fill a slot" in note) is any_policy
    assert ("may fill a slot" in pol["slot_market_policy_note"]) is any_policy


def test_the_note_switches_with_the_policy_and_is_not_a_constant(monkeypatch):
    """Both branches, so the sentence is pinned to the flag and not to today's
    value of it."""
    monkeypatch.setattr(bm, "SLOT_MARKET_POLICY", "any")
    assert "must clear BOTH legs" not in _publishability()["note"]
    monkeypatch.setattr(bm, "SLOT_MARKET_POLICY", "dispersion_gated")
    assert "must clear BOTH legs" in _publishability()["note"]


def test_the_ledgers_keep_recording_under_either_policy():
    """The one clause that was true either way survives the switch: a closed
    market keeps accruing evidence, because only its own evidence re-opens it."""
    for policy in ("any", "dispersion_gated"):
        import unittest.mock as mock
        with mock.patch.object(bm, "SLOT_MARKET_POLICY", policy):
            note = _publishability()["note"]
        assert "re-open one" in note, policy
        assert "keep recording" in note, policy
