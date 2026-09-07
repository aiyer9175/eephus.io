"""Schema-4 dark-capture builders (docs/diamond-betting.md 5d).

Every test here is about whether the BUILDER produces the number it claims to.
None of them relate a captured value to a game outcome, because 5c rule 1
disqualifies a candidate measured before its clock, and the schema-4 clock does
not open until ~2026-10-06.
"""
import json
from pathlib import Path

import pytest

import betting_usage as bu


# ---------------------------------------------------------------- wind parsing
@pytest.mark.parametrize("raw,mph,out", [
    ("9 mph, Out To CF", 9.0, 9.0),
    ("12 mph, In From CF", 12.0, -12.0),
    ("10 mph, Out To LF", 10.0, 7.0),
    ("10 mph, In From RF", 10.0, -7.0),
    ("7 mph, L To R", 7.0, 0.0),
    ("1 mph, Calm", 1.0, 0.0),
    ("0 mph, None", 0.0, 0.0),
])
def test_wind_parses_to_a_signed_out_component(raw, mph, out):
    """Out is positive because that is the direction that adds runs, and a
    lateral wind is a measured zero rather than a null."""
    assert bu.parse_wind(raw) == (mph, out)


def test_varies_has_a_speed_but_no_direction():
    """A stated absence of a direction is not a calm day. Zero would be a
    claim; None is the truth."""
    mph, out = bu.parse_wind("11 mph, Varies")
    assert mph == 11.0
    assert out is None


def test_unparseable_wind_is_null_and_never_zero():
    assert bu.parse_wind("") == (None, None)
    assert bu.parse_wind(None) == (None, None)
    assert bu.parse_wind("breezy") == (None, None)


# ------------------------------------------------------------ availability
def _led(rows):
    """rows as (org, date, mlbam, pitches, is_start)."""
    return [{"org": o, "date": d, "mlbam": m, "pitches": p, "outs": 3,
             "is_start": s} for o, d, m, p, s in rows]


DAY = "2026-09-07"
Y1, Y2 = "2026-09-06", "2026-09-05"


def test_two_days_in_a_row_makes_an_arm_unavailable():
    """THE OWNER'S RULE, in his words: "if a reliever is used 2 days in a row,
    they usually never pitch the next day"."""
    out = bu.unavailable_arms("TEX", DAY, _led([
        ("TEX", Y1, 100, 12, False),
        ("TEX", Y2, 100, 15, False),
    ]))
    assert 100 in out
    assert "each of the 2 prior days" in out[100]


def test_one_day_of_work_leaves_an_arm_available():
    out = bu.unavailable_arms("TEX", DAY, _led([("TEX", Y1, 100, 12, False)]))
    assert out == {}


def test_a_heavy_outing_yesterday_makes_an_arm_unavailable():
    out = bu.unavailable_arms("TEX", DAY, _led([("TEX", Y1, 101, 34, False)]))
    assert 101 in out and "34 pitches" in out[101]


def test_the_heavy_threshold_is_the_published_constant():
    at = bu.unavailable_arms("TEX", DAY, _led([("TEX", Y1, 1, bu.HEAVY_PITCHES, False)]))
    under = bu.unavailable_arms("TEX", DAY, _led([("TEX", Y1, 1, bu.HEAVY_PITCHES - 1, False)]))
    assert 1 in at and under == {}


def test_starters_are_not_judged_by_the_bullpen_rule():
    """A starter's rest is a different question with a different answer, and
    counting him here would leave every club a man short the day after every
    game."""
    out = bu.unavailable_arms("TEX", DAY, _led([
        ("TEX", Y1, 200, 95, True), ("TEX", Y2, 200, 95, True)]))
    assert out == {}


def test_another_club_s_usage_never_touches_this_club():
    out = bu.unavailable_arms("TEX", DAY, _led([
        ("BOS", Y1, 300, 12, False), ("BOS", Y2, 300, 12, False)]))
    assert out == {}


def test_the_org_join_survives_a_spelling_difference():
    """THE DEFECT THIS CLOSES. bullpen_leaderboards spells seven clubs
    differently from the completed-games cache (AZ/ARI, KC/KCR, TB/TBR and four
    more). Joining raw strings gave 7 of 30 clubs an empty depth list, which
    reads downstream as "this club has no bullpen" rather than as a failed
    join."""
    led = _led([("KCR", Y1, 400, 12, False), ("KCR", Y2, 400, 12, False)])
    assert 400 in bu.unavailable_arms("KC", DAY, led)
    assert 400 in bu.unavailable_arms("KCR", DAY, led)


# --------------------------------------------------------- pen_plus_avail
DEPTH = [
    {"key": "1", "rem_plus": 150, "ip": 60.0, "role": "Closer"},
    {"key": "2", "rem_plus": 100, "ip": 60.0, "role": "Setup"},
    {"key": "3", "rem_plus": 50, "ip": 60.0, "role": "Middle"},
]


def test_pen_plus_avail_is_the_bullpen_minus_the_arms_that_cannot_pitch():
    """Innings-weighted over AVAILABLE arms only, which is the servable form of
    the ask: it drops straight into game_prevention_z where bullpen_plus sits."""
    led = _led([("TEX", Y1, 1, 12, False), ("TEX", Y2, 1, 12, False)])
    a = bu.team_availability("TEX", DAY, DEPTH, led)
    assert a["pen_arms_avail"] == 2
    assert a["pen_plus_avail"] == pytest.approx(75.0)      # (100 + 50) / 2


def test_losing_a_bad_arm_raises_the_available_bullpen():
    """The feature is not a fatigue COUNT wearing a quality label. Losing the
    worst arm makes the available pen better, and a candidate that could only
    ever move one way would be measuring workload, not availability."""
    led = _led([("TEX", Y1, 3, 12, False), ("TEX", Y2, 3, 12, False)])
    a = bu.team_availability("TEX", DAY, DEPTH, led)
    assert a["pen_plus_avail"] == pytest.approx(125.0)     # (150 + 100) / 2


def test_a_full_bullpen_reproduces_its_own_weighted_mean():
    a = bu.team_availability("TEX", DAY, DEPTH, [])
    assert a["pen_plus_avail"] == pytest.approx(100.0)
    assert a["pen_b2b_arms"] == 0 and a["n_unavailable"] == 0


def test_an_unreadable_depth_row_is_skipped_not_guessed():
    depth = DEPTH + [{"key": "not-an-id", "rem_plus": 999, "ip": 999.0}]
    a = bu.team_availability("TEX", DAY, depth, [])
    assert a["n_depth"] == 3
    assert a["pen_plus_avail"] == pytest.approx(100.0)


def test_an_empty_depth_list_is_a_null_and_never_a_zero():
    """Zero is a value on this scale. None is the absence of one, which is what
    a club with no resolvable depth actually has."""
    a = bu.team_availability("TEX", DAY, [], [])
    assert a["pen_plus_avail"] is None
    assert a["pen_arms_avail"] is None


# ------------------------------------------------------------------ rest
GAMES = [
    {"date": "2026-09-01", "home_org": "TEX", "away_org": "BOS", "game_pk": 1},
    {"date": "2026-09-05", "home_org": "TEX", "away_org": "BOS", "game_pk": 2},
    {"date": "2026-09-06", "home_org": "BOS", "away_org": "TEX", "game_pk": 3},
]


def test_rest_days_counts_from_the_last_game_played():
    assert bu.schedule_rest("TEX", "2026-09-07", GAMES)["rest_days"] == 1
    assert bu.schedule_rest("TEX", "2026-09-08", GAMES)["rest_days"] == 2


def test_a_doubleheader_reads_zero_rest():
    g = GAMES + [{"date": "2026-09-07", "home_org": "TEX", "away_org": "BOS",
                  "game_pk": 4}]
    assert bu.schedule_rest("TEX", "2026-09-07", g)["rest_days"] == 0


def test_a_club_with_no_prior_game_has_no_rest_number():
    assert bu.schedule_rest("SEA", "2026-09-07", GAMES)["rest_days"] is None


def test_games_in_l7_counts_the_seven_days_before_and_not_today():
    """The window is the seven dates BEFORE the slate, so 09-01 through 09-06
    all count for a 09-07 board and the board's own date never does."""
    assert bu.schedule_rest("TEX", "2026-09-07", GAMES)["games_in_l7"] == 3
    today = GAMES + [{"date": "2026-09-07", "home_org": "TEX",
                      "away_org": "BOS", "game_pk": 5}]
    assert bu.schedule_rest("TEX", "2026-09-07", today)["games_in_l7"] == 3
    # and a game that falls out of the window stops counting
    assert bu.schedule_rest("TEX", "2026-09-09", GAMES)["games_in_l7"] == 2


def test_rest_joins_across_the_org_spelling_difference():
    g = [{"date": "2026-09-06", "home_org": "KCR", "away_org": "BOS", "game_pk": 9}]
    assert bu.schedule_rest("KC", "2026-09-07", g)["rest_days"] == 1


def test_starter_rest_is_none_on_a_first_appearance():
    led = _led([("TEX", Y1, 500, 95, True)])
    assert bu.starter_rest(500, DAY, led) == 1
    assert bu.starter_rest(999, DAY, led) is None
    assert bu.starter_rest(None, DAY, led) is None


# ----------------------------------------------------------- climatology
def _wx_feed(tmp: Path, pk: int, venue: int, temp: int, wind: str):
    (tmp / f"{pk}.json").write_text(json.dumps({
        "gameData": {"venue": {"id": venue},
                     "weather": {"temp": str(temp), "wind": wind,
                                 "condition": "Sunny"}}}), encoding="utf-8")


def test_climatology_is_a_trailing_window_that_stops_before_the_game(tmp_path):
    """STRICTLY BEFORE the game being priced, which is the only thing that makes
    a weather feature servable at all. The observed weather of tonight's game is
    not knowable tonight."""
    games = []
    for i in range(6):
        pk = 10 + i
        _wx_feed(tmp_path, pk, 1, 70, "5 mph, Out To CF")
        games.append({"date": "2026-09-0%d" % (i + 1), "game_pk": pk})
    # the game being priced, blazing hot, must NOT enter its own climatology
    _wx_feed(tmp_path, 99, 1, 200, "50 mph, Out To CF")
    games.append({"date": "2026-09-07", "game_pk": 99})
    c = bu.venue_climatology(1, "2026-09-07", games, feed_dir=tmp_path)
    assert c["n_games"] == 6
    assert c["wx_temp_climo"] == pytest.approx(70.0)
    assert c["wx_wind_out_climo"] == pytest.approx(5.0)


def test_a_thin_window_publishes_no_number_and_says_how_thin(tmp_path):
    games = []
    for i in range(2):
        pk = 20 + i
        _wx_feed(tmp_path, pk, 1, 70, "5 mph, Calm")
        games.append({"date": "2026-09-0%d" % (i + 1), "game_pk": pk})
    c = bu.venue_climatology(1, "2026-09-07", games, feed_dir=tmp_path)
    assert c["wx_temp_climo"] is None
    assert c["n_games"] == 2
    assert str(bu.WX_MIN_GAMES) in c["basis"]


def test_another_venue_never_enters_this_venue_s_climatology(tmp_path):
    games = []
    for i in range(6):
        pk = 30 + i
        _wx_feed(tmp_path, pk, 2, 30, "5 mph, In From CF")
        games.append({"date": "2026-09-0%d" % (i + 1), "game_pk": pk})
    c = bu.venue_climatology(1, "2026-09-07", games, feed_dir=tmp_path)
    assert c["wx_temp_climo"] is None and c["n_games"] == 0


def test_a_game_with_no_venue_gets_a_stated_null(tmp_path):
    c = bu.venue_climatology(None, "2026-09-07", [], feed_dir=tmp_path)
    assert c["wx_temp_climo"] is None
    assert "no venue id" in c["basis"]


# ---------------------------------------------------------- policy constants
def test_the_policy_constants_are_the_ones_the_document_pre_registered():
    """5d names these before any measurement. Tuning either against outcomes
    before the gate runs would be fitting the feature to the eval window."""
    assert bu.B2B_DAYS == 2
    assert bu.HEAVY_PITCHES == 30
    assert bu.WX_WINDOW_DAYS == 30
    assert bu.WX_MIN_GAMES == 4
