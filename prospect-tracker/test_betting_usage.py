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


# ==========================================================================
# catcher framing (5d-D) and times through the order (5d-E)
# ==========================================================================
def _pitch(px, pz, call, top=3.4, bot=1.6):
    return {"isPitch": True,
            "details": {"call": {"code": call}},
            "pitchData": {"coordinates": {"pX": px, "pZ": pz},
                          "strikeZoneTop": top, "strikeZoneBottom": bot}}


def _play(half, events, batter=1, pitcher=10, side="R"):
    return {"about": {"halfInning": half},
            "matchup": {"batSide": {"code": side},
                        "batter": {"id": batter}, "pitcher": {"id": pitcher}},
            "playEvents": events}


def _feedfile(tmp: Path, pk: int, plays):
    (tmp / f"{pk}.json").write_text(
        json.dumps({"liveData": {"plays": {"allPlays": plays}}}), encoding="utf-8")


def test_only_taken_pitches_count_toward_framing(tmp_path):
    """A swing is not an umpire decision. Counting one would make framing a
    measure of whether the other team swings."""
    _feedfile(tmp_path, 1, [_play("top", [
        _pitch(0.5, 2.5, "C"), _pitch(0.5, 2.5, "B"),
        _pitch(0.5, 2.5, "S"),           # swinging strike
        _pitch(0.5, 2.5, "X"),           # ball in play
        {"isPitch": False, "details": {}},
    ])])
    rows = bu._taken_pitches(1, tmp_path)
    assert len(rows) == 2
    assert [r["is_strike"] for r in rows] == [True, False]


def test_the_catching_club_is_read_off_the_half_inning(tmp_path):
    """In the top half the away team bats, so the HOME team is catching. Exact,
    no roster join, and immune to the mid-inning substitutions that make
    per-catcher attribution hard."""
    _feedfile(tmp_path, 2, [_play("top", [_pitch(0.5, 2.5, "C")]),
                            _play("bottom", [_pitch(0.5, 2.5, "C")])])
    rows = bu._taken_pitches(2, tmp_path)
    assert [r["catching"] for r in rows] == ["home", "away"]


def test_height_is_normalized_to_the_batter_s_own_zone(tmp_path):
    """Binning raw feet would make the expectation a model of batter height. A
    tall batter and a short one, each at the same RELATIVE height, must land in
    the same bin."""
    _feedfile(tmp_path, 3, [
        _play("top", [_pitch(0.2, 2.50, "C", top=3.4, bot=1.6)]),   # mid-zone
        _play("top", [_pitch(0.2, 2.05, "C", top=2.8, bot=1.3)]),   # mid-zone, short
    ])
    rows = bu._taken_pitches(3, tmp_path)
    assert rows[0]["bin"] == rows[1]["bin"]


def test_a_pitch_with_no_zone_is_dropped_rather_than_guessed(tmp_path):
    _feedfile(tmp_path, 4, [_play("top", [
        {"isPitch": True, "details": {"call": {"code": "C"}},
         "pitchData": {"coordinates": {"pX": 0.5, "pZ": 2.5}}},
    ])])
    assert bu._taken_pitches(4, tmp_path) == []


def test_framing_is_measured_against_the_league_in_the_same_bin(tmp_path):
    """The expectation is the league's OWN rate in that bin over the SAME
    window, so a club cannot beat it by playing in a period when everybody did.
    Here every club sees the identical bin, so every rate is zero."""
    games = []
    for i in range(20):
        pk = 100 + i
        _feedfile(tmp_path, pk, [_play("top", [_pitch(0.2, 2.5, "C")] * 30)])
        games.append({"date": "2026-09-0%d" % (i % 6 + 1), "game_pk": pk,
                      "home_org": "TEX" if i % 2 else "BOS", "away_org": "SEA"})
    out = bu.framing_rates(games, "2026-09-10", feed_dir=tmp_path)
    for org, v in out["values"].items():
        assert abs(v) < 1e-9, (org, v)


def test_a_club_that_steals_strikes_scores_above_the_league(tmp_path):
    """One club takes the SAME location and gets it called a strike more often
    than the league does. That is the whole signal, and it must come out
    positive for that club and negative for the one it is measured against."""
    games = []
    pk = 200
    # league baseline: 20 games where the bin is called a strike half the time
    for i in range(20):
        _feedfile(tmp_path, pk, [_play("top", [_pitch(0.9, 2.5, "C")] * 15 +
                                              [_pitch(0.9, 2.5, "B")] * 15)])
        games.append({"date": "2026-09-01", "game_pk": pk,
                      "home_org": "BOS", "away_org": "SEA"})
        pk += 1
    # TEX gets the same pitch called a strike every time
    for i in range(20):
        _feedfile(tmp_path, pk, [_play("top", [_pitch(0.9, 2.5, "C")] * 30)])
        games.append({"date": "2026-09-01", "game_pk": pk,
                      "home_org": "TEX", "away_org": "SEA"})
        pk += 1
    out = bu.framing_rates(games, "2026-09-10", feed_dir=tmp_path)
    assert out["values"]["TEX"] > 0
    assert out["values"]["BOS"] < 0


def test_a_thin_bin_cannot_manufacture_a_difference(tmp_path):
    """A bin under the league floor is dropped from BOTH the actual and the
    expected side, so one club's handful of odd pitches cannot become a rate."""
    games = []
    pk = 300
    for i in range(20):
        _feedfile(tmp_path, pk, [_play("top", [_pitch(0.2, 2.5, "C")] * 15 +
                                              [_pitch(0.2, 2.5, "B")] * 15)])
        games.append({"date": "2026-09-01", "game_pk": pk,
                      "home_org": "TEX", "away_org": "SEA"})
        pk += 1
    # a lone club-specific location, far under FRAME_MIN_BIN, all strikes
    _feedfile(tmp_path, pk, [_play("top", [_pitch(2.9, 0.1, "C")] * 5)])
    games.append({"date": "2026-09-01", "game_pk": pk,
                  "home_org": "TEX", "away_org": "SEA"})
    out = bu.framing_rates(games, "2026-09-10", feed_dir=tmp_path)
    assert abs(out["values"]["TEX"]) < 1e-9
    assert str(bu.FRAME_MIN_BIN) in out["basis"]


def test_a_club_under_the_pitch_floor_gets_no_rate(tmp_path):
    games = []
    _feedfile(tmp_path, 400, [_play("top", [_pitch(0.2, 2.5, "C")] * 10)])
    games.append({"date": "2026-09-01", "game_pk": 400,
                  "home_org": "TEX", "away_org": "SEA"})
    out = bu.framing_rates(games, "2026-09-10", feed_dir=tmp_path)
    assert "TEX" not in out["values"]


# -------------------------------------------------------------------- TTO
def _tto_game(tmp: Path, pk: int, n_batters: int, pitcher=10):
    plays = []
    for i in range(n_batters):
        plays.append(_play("top", [_pitch(0.2, 2.5, "C")],
                           batter=100 + (i % 9), pitcher=pitcher))
    _feedfile(tmp, pk, plays)


def test_tto_counts_the_third_pass_through_the_order(tmp_path):
    """27 batters against a nine-man order is three full passes, so nine of
    them are the third time through."""
    _tto_game(tmp_path, 500, 27)
    games = [{"date": "2026-09-01", "game_pk": 500,
              "home_org": "TEX", "away_org": "SEA"},
             {"date": "2026-09-02", "game_pk": 501,
              "home_org": "TEX", "away_org": "SEA"}]
    _tto_game(tmp_path, 501, 27)
    out = bu.tto_exposure(games, "2026-09-10", feed_dir=tmp_path)
    assert out["values"]["10"] == 9.0


def test_a_short_start_never_reaches_a_third_pass(tmp_path):
    for pk in (600, 601):
        _tto_game(tmp_path, pk, 12)
    games = [{"date": "2026-09-0%d" % i, "game_pk": 599 + i,
              "home_org": "TEX", "away_org": "SEA"} for i in (1, 2)]
    out = bu.tto_exposure(games, "2026-09-10", feed_dir=tmp_path)
    assert out["values"]["10"] == 0.0


def test_only_the_starter_is_measured(tmp_path):
    """A reliever's third time through is a different event with a different
    cause, and counting one would put a starter's exposure on a bullpen arm."""
    plays = [_play("top", [_pitch(0.2, 2.5, "C")], batter=100 + (i % 9), pitcher=10)
             for i in range(27)]
    plays += [_play("top", [_pitch(0.2, 2.5, "C")], batter=100 + (i % 9), pitcher=99)
              for i in range(27)]
    _feedfile(tmp_path, 700, plays)
    _feedfile(tmp_path, 701, plays)
    games = [{"date": "2026-09-0%d" % i, "game_pk": 699 + i,
              "home_org": "TEX", "away_org": "SEA"} for i in (1, 2)]
    out = bu.tto_exposure(games, "2026-09-10", feed_dir=tmp_path)
    assert "10" in out["values"]
    assert "99" not in out["values"], "a reliever must not carry a starter's exposure"


def test_a_pitcher_under_the_start_floor_gets_no_value(tmp_path):
    _tto_game(tmp_path, 800, 27)
    games = [{"date": "2026-09-01", "game_pk": 800,
              "home_org": "TEX", "away_org": "SEA"}]
    out = bu.tto_exposure(games, "2026-09-10", feed_dir=tmp_path)
    assert out["values"] == {}


def test_the_window_stops_before_the_date_being_priced(tmp_path):
    """Strictly before, the same rule every builder in this file follows."""
    for pk in (900, 901):
        _tto_game(tmp_path, pk, 27)
    games = [{"date": "2026-09-10", "game_pk": 900,
              "home_org": "TEX", "away_org": "SEA"},
             {"date": "2026-09-11", "game_pk": 901,
              "home_org": "TEX", "away_org": "SEA"}]
    out = bu.tto_exposure(games, "2026-09-10", feed_dir=tmp_path)
    assert out["values"] == {}


def test_the_framing_and_tto_constants_are_the_pre_registered_ones():
    assert bu.FRAME_X_BIN == 0.1
    assert bu.FRAME_Z_BIN == 0.1
    assert bu.FRAME_MIN_BIN == 40
    assert bu.FRAME_MIN_TEAM_PITCHES == 200
    assert bu.FRAME_WINDOW_DAYS == 30
