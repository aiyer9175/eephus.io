# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Four guards on the board's two entry seams: which DATE it is, and which
POSTED NUMBER it prices. Audit items L14-04, L14-06, L14-08 and L14-12.

None of these is a pricing change. No probability moves and no edge moves, and
`betting_model.MODEL_VERSION` is untouched: every one of the four either refuses
a case the module had no number for, restores a denominator, or makes a
published sentence say what the code does. Selection is untouched on any board
that carries no refusal, which is every board to date; a refusal does take two
runline candidates out of the slot pool, which is what a refusal is for.

  L14-04  `_slate_is_open` read TWO signals for "this game has started", the
          status and the clock, and excluded postponements from the first one
          only. A postponed game keeps its scheduled `datetime`, so once that
          time passed it counted as started anyway - the exact thing the
          exclusion's own comment forbids. Three postponements and one real
          night game made a live card read as a 0.25 fragment. The mirror case,
          three postponements still ahead of the clock, published a 0.75 pregame
          share on a date with nothing bettable; it chose no board, because
          every reader of the verdict is gated on a bettable row, so that half
          is a disclosure defect. A called-off row is now in neither half and
          leaves the denominator, which is published beside the counts.

          AND THE SIGNAL IS ONE THIS PRODUCER EMITS. The status strings
          ("postponed", "cancelled") are not in data/fantasy.json:
          `fantasy_schedule.fetch_probables` writes `abstractGameState` alone,
          where a postponement reads "Final", so a set keyed on those strings
          would have left case B exactly where it was. The coded and detailed
          states are in the raw schedule document the same fetch cached, which
          `called_off_game_pks` reads and `dfs_export._annotate_states` already
          read for the same reason. No request is made on either path.

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
than as claims.

L14-06: over the 31 cached snapshots in `.cache/odds`, 492 pregame events carry
a two-sided spread view and every one is posted at +/-1.5, mirrored, with a
point on both sides, so the guard refuses nothing that has ever reached a board,
while all 30 in-game spread views posted away from +/-1.5 were already dropped
upstream. The served board is deliberately not pinned in this file: it is
rebuilt several times a day and any count of it written into a test goes stale
by the next build, while the snapshot cache is append-only and reproduces.

L14-04: `.cache/fantasy_schedule` holds 160 files, of which 128 are schedule
windows (the rest are the lineup and team documents, which are named
differently and are skipped by shape). Those 128 carry 6,857 game rows and 899
distinct gamePk. `abstractGameState` across all of them is only "Preview"
(6,285), "Final" (271) and "Live" (301), and no row is postponed or cancelled on
any of the three status fields, so nothing on today's board moves. The pin that
the read is load-bearing rather than dead is
`test_without_the_producer_signal_the_same_card_walks_a_day_forward`, which
serves a different date when the document is taken away.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

be = pytest.importorskip("betting_export")
bi = pytest.importorskip("betting_ingest")
bm = pytest.importorskip("betting_model")

ROOT = Path(__file__).parent
ODDS_DIR = ROOT / ".cache" / "odds"
SCHED_DIR = ROOT / ".cache" / "fantasy_schedule"
#: The schedule WINDOW documents in that directory, by the same name shape
#: `_schedule_cache_documents` uses. The lineup and team documents share the
#: directory and are not schedules; an empty list means a pruned or unbuilt
#: cache, which skips the measurement rather than failing it.
SCHED_DOCS = sorted(
    p for p in (SCHED_DIR.glob("*_*_*.json") if SCHED_DIR.is_dir() else [])
    if len(p.stem.split("_")) == 3 and len(p.stem.split("_")[0]) == 10
    and p.stem[4] == "-")

NOW = datetime(2026, 9, 10, 23, 30, tzinfo=timezone.utc)
DAY = "2026-09-10"
DAY2 = "2026-09-11"


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """`called_off_game_pks` pointed at a directory this test owns, with the
    per-day memo cleared going in AND coming out, so no test can inherit another
    test's answer or the repo's own cache."""
    d = tmp_path / "fantasy_schedule"
    d.mkdir()
    monkeypatch.setattr(be, "SCHEDULE_CACHE_DIR", d)
    be._CALLED_OFF_BY_DAY.clear()
    yield d
    be._CALLED_OFF_BY_DAY.clear()


def _raw_game(pk: int, *, coded: str = "S", detailed: str = "Scheduled",
              abstract: str = "Preview", day: str = DAY) -> dict:
    """One game as the RAW StatsAPI schedule document carries it: the three
    status fields, of which data/fantasy.json keeps only the first."""
    return {"gamePk": pk, "officialDate": day,
            "status": {"abstractGameState": abstract, "codedGameState": coded,
                       "detailedState": detailed}}


def _write_schedule_doc(cache_dir: Path, blocks: dict, *, start: str, end: str,
                        mtime: float | None = None) -> Path:
    """One cached raw /schedule document, named the way fantasy_schedule names
    them. `blocks` is {date: [raw game, ...]}."""
    path = cache_dir / f"{start}_{end}_R.json"
    path.write_text(json.dumps(
        {"dates": [{"date": d, "games": g} for d, g in sorted(blocks.items())]}),
        encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _postponed_doc(cache_dir: Path, pks, *, day: str = DAY, **kw) -> Path:
    return _write_schedule_doc(
        cache_dir,
        {day: [_raw_game(pk, coded="D", detailed="Postponed", abstract="Final",
                         day=day) for pk in pks]},
        start=kw.pop("start", day), end=kw.pop("end", day), **kw)


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
    "of the games this date will actually stage, played and still to come, how
    many are still ahead". Six staged games with three of them still to come is
    exactly the threshold whatever number of postponements sits beside them."""
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


def test_the_two_slate_halves_partition_the_deny_list():
    """A STATE ADDED TO ONE LIST MUST LAND IN A HALF. The three sets are today an
    exact, disjoint partition, and nothing but this says so: add "rescheduled" to
    NOT_BETTABLE_STATES alone, the way a StatsAPI vocabulary change would arrive,
    and it is in neither slate half, so `_has_started` falls through to the clock
    and four future-dated unbettable rows read as a whole pregame card. That is
    the L14-04 shape reintroduced by a one-line edit somewhere else."""
    assert be.SLATE_STARTED_STATES | be.SLATE_CALLED_OFF_STATES == be.NOT_BETTABLE_STATES
    assert not (be.SLATE_STARTED_STATES & be.SLATE_CALLED_OFF_STATES)


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
# L14-04, the other half: the signal the producer actually emits
# ===========================================================================
def test_a_postponement_this_producer_reports_as_final_is_still_called_off(
        cache_dir, monkeypatch):
    """THE CASE THE STRING SET CANNOT REACH. `fetch_probables` writes
    `abstractGameState`, and StatsAPI reports a postponement there as "Final" on
    this feed, so the row arrives as "final": in SLATE_STARTED_STATES, counted as
    started, audit case B untouched. The first half of this test is that defect,
    reproduced with an empty cache; the second half is the same rows with the
    document the fetch already wrote sitting beside them."""
    rows = [_row("Final", hours=-3, pk=i) for i in range(3)]
    rows.append(_row("Preview", hours=2, pk=9))

    counts: dict = {}
    is_open, why_not = be._slate_is_open(DAY, rows, NOW, counts=counts)
    assert not is_open, "with nothing on disk the status string is all there is"
    assert counts["n_started"] == 3 and counts["n_called_off"] == 0
    assert counts["pregame_share"] == 0.25
    assert "fragment" in why_not

    _postponed_doc(cache_dir, range(3))
    be._CALLED_OFF_BY_DAY.clear()
    counts2: dict = {}
    is_open2, why2 = be._slate_is_open(DAY, rows, NOW, counts=counts2)
    assert is_open2, why2
    assert counts2["n_called_off"] == 3
    assert counts2["n_started"] == 0
    assert counts2["n_playable"] == 1
    assert counts2["pregame_share"] == 1.0


def test_either_status_field_is_enough_and_suspended_is_not_called_off(cache_dir):
    """Two fields, read independently, because a vocabulary change in one of
    them must not take the guard with it. SUSPENDED IS NOT HERE: a suspended
    game has started, which is the distinction `anchors_close_window` turns on
    and the reason it is in SLATE_STARTED_STATES instead."""
    _write_schedule_doc(cache_dir, {DAY: [
        _raw_game(1, coded="D", detailed="Scheduled"),
        _raw_game(2, coded="S", detailed="Postponed"),
        _raw_game(3, coded="C", detailed="Scheduled"),
        _raw_game(4, coded="S", detailed="Cancelled"),
        _raw_game(5, coded="U", detailed="Suspended"),
        _raw_game(6, coded="T", detailed="Suspended"),
        _raw_game(7),
    ]}, start=DAY, end=DAY)
    assert be.called_off_game_pks(DAY) == {
        1: "postponed", 2: "postponed", 3: "cancelled", 4: "cancelled"}


def test_the_freshest_document_wins(cache_dir):
    """A game called off and then reinstated must not be read off the stale
    copy, and a postponement announced at four o'clock is not in the noon
    window."""
    _postponed_doc(cache_dir, [1], start="2026-09-09", end="2026-09-11", mtime=1000.0)
    _write_schedule_doc(cache_dir, {DAY: [_raw_game(1)]},
                        start="2026-09-10", end="2026-09-12", mtime=2000.0)
    assert be.called_off_game_pks(DAY) == {}

    be._CALLED_OFF_BY_DAY.clear()
    _write_schedule_doc(cache_dir, {DAY: [
        _raw_game(1, coded="D", detailed="Postponed", abstract="Final")]},
        start="2026-09-08", end="2026-09-14", mtime=3000.0)
    assert be.called_off_game_pks(DAY) == {1: "postponed"}


def test_only_the_date_asked_for_is_read_out_of_a_multi_day_document(cache_dir):
    """The windows overlap by design (a three-day forward pull, every night), so
    a row is read for the date it is listed on and not for the file it is in."""
    _write_schedule_doc(cache_dir, {
        DAY: [_raw_game(1, coded="D", detailed="Postponed", abstract="Final")],
        DAY2: [_raw_game(2, coded="D", detailed="Postponed", abstract="Final",
                         day=DAY2)],
    }, start=DAY, end=DAY2)
    assert be.called_off_game_pks(DAY) == {1: "postponed"}
    assert be.called_off_game_pks(DAY2) == {2: "postponed"}


def test_a_missing_or_pruned_cache_degrades_to_the_status_string(tmp_path, monkeypatch):
    """tools/prune_cache.py prunes this directory, so an empty one is a real
    state. It puts the module back exactly where it was rather than blanking a
    board on a file that is not there."""
    monkeypatch.setattr(be, "SCHEDULE_CACHE_DIR", tmp_path / "not-here")
    be._CALLED_OFF_BY_DAY.clear()
    try:
        assert be.called_off_game_pks(DAY) == {}
        assert be._is_called_off(_row("Postponed", hours=-2, pk=1)) is True
        assert be._is_called_off(_row("Final", hours=-2, pk=1)) is False
    finally:
        be._CALLED_OFF_BY_DAY.clear()


def test_a_corrupt_cache_file_is_not_a_verdict(cache_dir):
    """An unreadable file says nothing, in either direction."""
    (cache_dir / f"{DAY}_{DAY}_R.json").write_text("{not json", encoding="utf-8")
    assert be.called_off_game_pks(DAY) == {}


def test_a_row_with_no_game_pk_is_not_looked_up(cache_dir):
    """The lookup is keyed on gamePk, so a row without one falls back to the
    string and must not raise on the way there."""
    _postponed_doc(cache_dir, [1])
    g = {"date": DAY, "status": "Preview", "datetime": None}
    assert be._is_called_off(g) is False
    assert be._is_called_off({"game_pk": "not-a-number", "date": DAY,
                              "status": "Preview"}) is False


def test_the_called_off_read_never_makes_a_request():
    """NO STATSAPI CALL ON THE BETTING PATH. `fantasy_schedule._cached_schedule`
    would refetch a window past its three-hour TTL, which would put a network
    round trip inside `_slate_is_open`; this opens the files that fetch already
    wrote and nothing else.

    Read off the COMPILED names rather than the source text, so the prose in the
    docstrings above, which has to name `_cached_schedule` to say why it is not
    called, cannot satisfy or break the check."""
    forbidden = {"_cached_schedule", "fetch_probables", "SESSION", "requests",
                 "urlopen", "feed_cache", "fantasy_schedule"}
    for fn in (be.called_off_game_pks, be._schedule_cache_documents,
               be._called_off_label, be._is_called_off):
        assert not (set(fn.__code__.co_names) & forbidden), fn.__name__
    assert not hasattr(be, "fantasy_schedule"), (
        "betting_export does not import the schedule fetcher at all")


@pytest.mark.skipif(not SCHED_DOCS, reason="no cached schedule documents")
def test_the_producer_cannot_say_called_off_in_the_field_it_publishes():
    """THE MEASUREMENT, as a test. Counted 2026-09-17: 128 schedule documents,
    6,857 game rows, 899 distinct gamePk, `abstractGameState` only ever
    "Preview" / "Live" / "Final", and no row postponed or cancelled on any
    field, which is why no served number moves today.

    The assertion is the DURABLE half, and it is vacuous only until the first
    postponement is cached: whenever a row IS called off, the field
    data/fantasy.json keeps cannot say so, so the string set alone would miss
    it. That is the finding, held against the real cache rather than asserted."""
    n_docs = n_rows = n_off = 0
    pks = set()
    for path in SCHED_DOCS:
        n_docs += 1
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for block in doc.get("dates") or []:
            for raw in block.get("games") or []:
                n_rows += 1
                pks.add(raw.get("gamePk"))
                st = raw.get("status") or {}
                if not be._called_off_label(st):
                    continue
                n_off += 1
                abstract = str(st.get("abstractGameState") or "").strip().lower()
                assert abstract not in be.SLATE_CALLED_OFF_STATES, (
                    f"{raw.get('gamePk')} is {st.get('detailedState')} and the "
                    f"producer's own field says {abstract!r}")
    assert n_docs >= 100, f"the schedule cache thinned out: {n_docs} documents"
    assert n_rows >= 6000, f"the schedule cache thinned out: {n_rows} rows"
    assert len(pks) >= 800, f"the schedule cache thinned out: {len(pks)} games"


# ===========================================================================
# L14-04: what the chosen date lost, published
# ===========================================================================
def _walk(monkeypatch, rows, **kw):
    monkeypatch.setattr(be, "_load",
                        lambda name: ({"schedule": {"games": rows}}
                                      if name == "fantasy.json" else None))
    stats: dict = {}
    day, board = be.resolve_slate(now=NOW, stats=stats, priceable={}, **kw)
    return day, board, stats


def _gutted_card() -> list[dict]:
    """Ten games listed today: six postponed (arriving as "Final", the way this
    producer reports one), two really final, two still to come. Twelve whole
    games tomorrow."""
    rows = [_row("Final", hours=-3, pk=i) for i in range(6)]
    rows += [_row("Final", hours=-4, pk=10 + i) for i in range(2)]
    rows += [_row("Preview", hours=2, pk=20 + i) for i in range(2)]
    rows += [{**_row("Preview", hours=26, pk=30 + i), "date": DAY2}
             for i in range(12)]
    return rows


def test_a_card_gutted_by_postponements_wins_the_walk_and_says_why(
        cache_dir, monkeypatch):
    """THE CONSEQUENCE OF THE DENOMINATOR, pinned rather than discovered later.
    Six of today's ten are called off, so the share is read over the four the
    date will stage and today opens on a two-game board. That is the right
    board - those two games are tonight and the books are posting them - and it
    must not be the silent one, because the payload otherwise says ten games on
    the date and ships two rows."""
    _postponed_doc(cache_dir, range(6))
    day, board, stats = _walk(monkeypatch, _gutted_card())
    assert day == DAY
    assert [g["game_pk"] for g in board] == [20, 21]
    off = stats["slate_called_off"]
    assert off["slate_date"] == DAY
    assert off["n_called_off"] == 6
    assert off["n_games_on_date"] == 10
    assert off["n_playable"] == 4
    assert off["n_bettable"] == 2
    assert "6 of the 10" in off["reason"]
    assert {g["game_pk"] for g in off["games"]} == set(range(6))
    cand = stats["slate_candidates"][0]
    assert cand["pregame_share"] == 0.5 and cand["open"] is True


def test_without_the_producer_signal_the_same_card_walks_a_day_forward(
        cache_dir, monkeypatch):
    """THE PIN THAT THE READ IS LOAD-BEARING. Same rows, same clock, no cached
    document: the six postponements read as started, today is a 0.2 fragment and
    the board is tomorrow's twelve games. If `called_off_game_pks` ever stops
    finding what it finds, this test goes green and the one above goes red."""
    day, board, stats = _walk(monkeypatch, _gutted_card())
    assert day == DAY2
    assert len(board) == 12
    assert stats["slate_called_off"] is None
    assert stats["slate_candidates"][0]["pregame_share"] == 0.2


def test_a_board_with_nothing_called_off_publishes_null_and_not_a_zero_block(
        cache_dir, monkeypatch):
    """Null means the date lost nothing. A block with n 0 would read as a date
    that had postponements and recovered them."""
    rows = [_row("Preview", hours=2, pk=i) for i in range(4)]
    day, board, stats = _walk(monkeypatch, rows)
    assert day == DAY and len(board) == 4
    assert stats["slate_called_off"] is None
    assert stats["called_off_rows_dropped"]["n"] == 0


def test_a_bettable_row_the_document_calls_off_leaves_the_board(
        cache_dir, monkeypatch):
    """THE REGRESSION THE DENOMINATOR FIX WOULD OTHERWISE HAVE OPENED. A row
    whose cached document says postponed while data/fantasy.json still says
    "Preview" is bettable by the status string, and it is no longer started
    either, so without a bucket of its own it would sit on the board with a
    price cell for a game nobody will play."""
    _postponed_doc(cache_dir, [0])
    rows = [_row("Preview", hours=2, pk=0), _row("Preview", hours=3, pk=1)]
    day, board, stats = _walk(monkeypatch, rows)
    assert [g["game_pk"] for g in board] == [1]
    off = stats["called_off_rows_dropped"]
    assert off["n"] == 1 and off["n_on_slate"] == 2
    assert off["games"][0]["game_pk"] == 0
    assert stats["started_rows_dropped"]["n"] == 0
    assert stats["started_rows_dropped"]["applied"] is True


def test_the_never_blank_fallback_does_not_restore_a_called_off_row(
        cache_dir, monkeypatch):
    """A blank page is worse than a stale one, and a called-off game is not
    stale: it was never played. The fallback hands back the started rows and
    leaves the postponement out."""
    _postponed_doc(cache_dir, [0])
    rows = [_row("Preview", hours=2, pk=0), _row("Preview", hours=-2, pk=1)]
    day, board, stats = _walk(monkeypatch, rows)
    assert [g["game_pk"] for g in board] == [1]
    assert stats["started_rows_dropped"]["applied"] is False
    assert stats["called_off_rows_dropped"]["n"] == 1


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


def test_an_explicit_date_with_no_bettable_row_still_says_the_filter_ran(monkeypatch):
    """`applied: false` is documented to mean the never-blank fallback fired, so
    an empty board must not publish it: "nothing to filter" and "the filter
    refused to blank the board" are the two states this field exists to keep
    apart, and a rebuild of a fully postponed date hit the second label with the
    first fact."""
    rows = [_row("Postponed", hours=-2, pk=i) for i in range(4)]
    day, board, stats = _explicit(monkeypatch, rows)
    assert day == DAY and board == []
    drop = stats["started_rows_dropped"]
    assert drop["n"] == 0 and drop["n_on_slate"] == 0
    assert drop["applied"] is True


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
    assert "no push term" in row["runline_refused"]


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


def test_a_point_that_is_not_a_finite_number_is_refused():
    """NaN PASSES EVERY OTHER TEST, because each one is an inequality and every
    comparison with NaN is False: it would fall through as priceable, be read for
    its sign as not-favourite, and print as "nan" on the board. `json.loads`
    accepts a bare NaN literal, so a snapshot can really carry this shape."""
    nan = float("nan")
    assert "finite" in (be.runline_point_refusal(
        {"best": {"home": {"point": nan}, "away": {"point": nan}}}) or "")
    assert "finite" in (be.runline_point_refusal(
        {"best": {"home": {"point": float("inf")},
                  "away": {"point": float("-inf")}}}) or "")
    parsed = json.loads('{"home": {"point": NaN}, "away": {"point": NaN}}')
    assert "finite" in (be.runline_point_refusal({"best": parsed}) or "")


def test_a_refused_runline_publishes_no_runline_market_beside_its_null():
    """ONE ROW MUST NOT ASSERT A MARKET THE ROW BESIDE IT REFUSED. With the
    spread refused, `market` was still publishing the runline's fair book, its
    hold and its book counts next to `runline: null`, which reads as "no spread
    was posted" rather than "a spread was posted and this model has no number
    for it"."""
    row, _ = _bets(_event(-2.5))
    assert row["runline"] is None and row["runline_refused"]
    mk = row["market"]
    assert mk["runline_fair_book"] is None
    assert mk["runline_hold_pct"] is None
    assert "runline" not in mk["n_books_rejected"]
    assert "runline" not in mk["max_book_lag_minutes"]
    assert mk["moneyline_fair_book"], "the priced markets are untouched"
    assert "moneyline" in mk["n_books_rejected"]


def test_a_priced_runline_still_publishes_its_market_disclosure():
    """The other half of the pair: the gate is the refusal and nothing else."""
    row, _ = _bets(_event(-1.5))
    mk = row["market"]
    assert mk["runline_fair_book"]
    assert mk["runline_hold_pct"] is not None
    assert "runline" in mk["n_books_rejected"]
    assert "runline" in mk["max_book_lag_minutes"]


def test_the_refusal_reason_names_the_dict_and_not_the_model():
    """`betting_model.margin_distribution` returns the whole margin PMF, which
    IS the push mass. What is missing is a push term in the dict
    `game_probabilities` hands back, and the served reason has to say the second
    thing, because the first one would send a reader looking for a model that is
    already there."""
    reason = be.runline_point_refusal(
        {"best": {"home": {"point": -2.0}, "away": {"point": 2.0}}})
    assert "game_probabilities returns no push term" in reason
    assert "margin model" not in reason
    assert hasattr(bm, "margin_distribution")


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
