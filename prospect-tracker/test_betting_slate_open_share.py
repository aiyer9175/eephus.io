"""The board served Monday's card at 1:13pm ET on Sunday, with no pick and no
value badges, and it took two independent defects to do it.

BOTH ARE REGRESSIONS OF AN EARLIER FIX, which is why they are pinned here
together. `_slate_is_open` closed a date on its FIRST started game, which was an
overshoot of the 2026-08-08 repair for the opposite failure (one straggler
Preview row won `min(date)` and the board priced one game of fifteen). And the
pick gate asked whether an API key was set rather than whether a market was on
the board, so a box with a full cached snapshot published "no odds feed is
configured, so there is no market price to have an edge against" over eleven
rows carrying nine books a side.

The second one is not cosmetic and the tests below say so: the same flag gates
`provisional_picks`, and the client badge reads `pick_meta.min_edge`, which a
blocked build nulls. One false predicate took the Pick of the Day and every
best-value badge with it.
"""
from datetime import datetime, timedelta, timezone

import betting_export as be


NOW = datetime(2026, 9, 7, 17, 13, tzinfo=timezone.utc)


def _card(day: str, n: int, n_started: int) -> list[dict]:
    """A date's schedule rows, `n_started` of them already under way.

    Started games are stamped in the past AND carry a started status, so the
    fixture does not silently depend on which of the two signals fires.
    """
    out = []
    for i in range(n):
        started = i < n_started
        t = NOW - timedelta(hours=1) if started else NOW + timedelta(hours=3 + i)
        out.append({
            "date": day,
            "datetime": t.isoformat().replace("+00:00", "Z"),
            "status": "In Progress" if started else "Preview",
        })
    return out


def _resolve(games, stats, *, priceable):
    """resolve_slate against an injected schedule and an injected market map.

    Both are injected so the slate rule's tests never depend on what
    `.cache/odds` or `data/fantasy.json` happen to hold when they run.
    """
    import betting_export as _be
    orig = _be._load
    _be._load = lambda name: ({"schedule": {"games": games}}
                              if name == "fantasy.json" else orig(name))
    try:
        return _be.resolve_slate(now=NOW, stats=stats, priceable=priceable)
    finally:
        _be._load = orig


# ---------------------------------------------------------------- the slate rule
def test_a_card_with_most_of_it_left_is_still_a_board():
    """NINE OF ELEVEN PREGAME IS A BOARD. This is the live 2026-09-07 shape:
    a Sunday card whose 1:05 and 1:10 games had started while nine were still to
    come, four of them at night. The old rule closed the date on the first of
    those two and rolled the board to a Monday whose lines the books had not
    posted, so the page priced nothing at all."""
    games = _card("2026-09-07", 11, 2)
    is_open, why_not = be._slate_is_open("2026-09-07", games, NOW)
    assert is_open, why_not
    assert why_not is None


def test_a_card_nine_tenths_played_is_a_fragment():
    """ONE OF FIFTEEN LEFT IS NOT A BOARD. The 2026-08-08 defect, kept shut:
    a single unplayed straggler must not win the board away from a whole card."""
    games = _card("2026-08-08", 15, 14)
    is_open, why_not = be._slate_is_open("2026-08-08", games, NOW)
    assert not is_open
    assert "fragment" in why_not
    assert "15" in why_not and "14" in why_not


def test_the_boundary_is_the_published_share_and_not_a_started_count():
    """The verdict turns on the PROPORTION, at the constant the module names.

    A count of started games cannot separate the two cases above, because both
    have started games. Walking the whole range pins that the rule is the share
    and that the module constant is the one it uses.
    """
    n = 10
    thr = be.SLATE_OPEN_MIN_PREGAME_SHARE
    for started in range(n + 1):
        pregame_share = (n - started) / n
        is_open, _ = be._slate_is_open("2026-09-07", _card("2026-09-07", n, started), NOW)
        assert is_open == (pregame_share >= thr), (started, pregame_share)


def test_the_candidate_row_shows_the_call_rather_than_asserting_it():
    """Both counts and the threshold ride on the served row, so a reader can
    check the verdict instead of taking it."""
    counts: dict = {}
    be._slate_is_open("2026-09-07", _card("2026-09-07", 11, 2), NOW, counts=counts)
    assert counts["n_started"] == 2
    assert counts["n_pregame"] == 9
    assert abs(counts["pregame_share"] - 9 / 11) < 1e-4


def test_an_empty_date_is_not_a_board():
    is_open, why_not = be._slate_is_open("2026-09-07", [], NOW)
    assert not is_open
    assert "no games" in why_not


# ------------------------------------------------------------- the pick gate
def _priced_board() -> list[dict]:
    """One game carrying a real two-sided market with a large edge."""
    return [{
        "game_pk": 1, "start": "2026-09-07T23:10:00Z",
        "home": {"org": "KCR"}, "away": {"org": "ARI"},
        "moneyline": [
            {"side": "home", "label": "KCR", "point": None, "edge": 0.10,
             "odds": -110, "decimal": 1.91, "book": "fanduel", "model_prob": 0.60,
             "ev_per_unit": 0.145, "kelly_full": 0.19},
        ],
    }]


def test_a_cached_market_is_never_reported_as_no_market():
    """THE FALSE SENTENCE. `pick_blockers` said "no odds feed is configured, so
    there is no market to have an edge against" whenever the API key was absent
    from the reading process, including on a board holding a full snapshot."""
    blockers = be.pick_blockers(min_edge=None, odds_priceable=True)
    ids = [b["id"] for b in blockers]
    assert "odds_feed" not in ids, blockers
    # the honest blocker survives: no threshold has been measured
    assert "min_edge" in ids


def test_the_no_market_blocker_still_fires_when_there_is_no_market():
    blockers = be.pick_blockers(min_edge=None, odds_priceable=False)
    feed = next(b for b in blockers if b["id"] == "odds_feed")
    assert feed["have"] == "none"
    assert "snapshot" in feed["reason"]
    assert "configured" not in feed["reason"]


def test_a_priceable_board_publishes_a_pick_and_a_badge_floor():
    """The two symptoms the user saw, pinned to the one flag that caused them.

    `pick_meta.min_edge` is what the client's best-value badge reads, so the
    floor being present here is the badge being present on the page.
    """
    slots, reason, meta = be.provisional_picks(_priced_board(), odds_priceable=True)
    assert slots["pick_of_the_day"] is not None, reason
    assert not meta.get("blocked")
    assert meta["min_edge"] is not None


def test_an_unpriceable_board_publishes_neither():
    slots, reason, meta = be.provisional_picks(_priced_board(), odds_priceable=False)
    assert slots["pick_of_the_day"] is None
    assert meta.get("blocked") is True
    assert "snapshot" in reason


# ------------------------------------------------- the board must price something
def _sched(day, n, n_started):
    return _card(day, n, n_started)


def test_an_open_card_with_no_market_loses_to_a_priced_fragment():
    """THE DEFECT. At 19:04 UTC on 2026-09-07 the board chose 2026-09-08, which
    had fifteen games, none started and NO cached prices, over the five games
    still to come on 2026-09-07 that the snapshot could price for all five. Both
    halves were working as designed: `_slate_is_open` asks whether most of a
    card is still ahead and never asks whether any of it can be priced, and the
    books do not post tomorrow's lines until tomorrow. The page went blank."""
    games = _sched("2026-09-07", 11, 6) + _sched("2026-09-08", 15, 0)
    stats: dict = {}
    day, rows = _resolve(games, stats, priceable={"2026-09-07": 5})
    assert day == "2026-09-07"
    assert stats["slate_rule"] == "earliest_priced_partial_slate"
    assert len(rows) == 5, "only the games still to come"
    ps = stats["partial_slate"]
    assert ps["n_still_to_come"] == 5 and ps["n_priceable"] == 5
    assert "cached market" in ps["reason"]


def test_an_open_priced_card_still_wins_outright():
    """The ordinary case is unchanged: a whole card with a market is the board."""
    games = _sched("2026-09-07", 11, 6) + _sched("2026-09-08", 15, 0)
    stats: dict = {}
    day, rows = _resolve(games, stats, priceable={"2026-09-07": 5, "2026-09-08": 15})
    assert day == "2026-09-08"
    assert stats["slate_rule"] == "first_open_priced_slate"
    assert len(rows) == 15


def test_the_2026_08_08_defect_stays_shut_under_the_new_preference():
    """One of fifteen left must NEVER win the board away from a whole card, even
    when the straggler is the only priced game. That is the failure the slate
    rule was written for, and the priceable preference is ordered so a
    mostly-played card is taken only when the alternative can price nothing."""
    games = _sched("2026-08-08", 15, 14) + _sched("2026-08-09", 15, 0)
    stats: dict = {}
    day, _ = _resolve(games, stats, priceable={"2026-08-08": 1, "2026-08-09": 15})
    assert day == "2026-08-09", "a priced whole card outranks a priced fragment"


def test_no_market_information_degrades_to_the_previous_rule():
    """An empty map is "nothing is known about prices", not "nothing is priced".
    A build with no snapshot must resolve a slate exactly as it did before."""
    games = _sched("2026-09-07", 11, 6) + _sched("2026-09-08", 15, 0)
    stats: dict = {}
    day, _ = _resolve(games, stats, priceable={})
    assert day == "2026-09-08"
    assert stats["slate_rule"] == "first_open_slate"
