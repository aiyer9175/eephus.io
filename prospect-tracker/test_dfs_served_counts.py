# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Two served DFS defects, and the assertions whose absence let them ship.

1. THE BOARD COUNTED ONE POPULATION AND SERVED ANOTHER (audit L17-F1). The
   integrity panel on the 2026-09-10 slate said "Hitters priced 128" above a
   hitter board of 109. `_slate_integrity` ran before the active-roster filter,
   and 128 - 109 = 19 was exactly `roster_filter.n_removed`. Nothing asserted
   that the counts a reader sees equal the rows the page serves.

   THE TRAP IN THE OBVIOUS FIX. Moving the whole integrity call below the
   roster filter also moves `orgs_without_hitters`, which is the 2026-08-05
   broken-join detector: a club whose every bat was roster-removed would then
   read as a join miss. So the board counts and both collapse guards read the
   served rows, and the join detector keeps reading the priced rows. Both halves
   are pinned below.

2. THE BOARD PRICED A LIVE GAME OFF AN IN-GAME MARKET (audit L14-02). HOU at PHI
   was 2h29m into play when the 19:34 UTC snapshot was taken, and /dfs/ served
   its remaining-game total (3.5 runs, Philadelphia 0.98) on 1 of 5 game cards
   and 22 of 117 player rows, while `vegas_source.n_rejected_on_time` read 0.
   /betting/ had refused the same event off the same snapshot since 2026-08-09.
   The two readers now share one predicate, and a refused game says so.

3. THE BOARD SERVED GAMES NOBODY COULD DRAFT (owner decision 5, 2026-09-11).
   45 of 117 rows on the 2026-09-10 slate sat on games already started or final,
   and the optimizer built lineups out of them. Only a game whose first pitch
   has not been thrown is draftable now; the rest leave `games`, `players` and
   the optimizer and are listed in `excluded_games` with their state, and the
   schedule's cached status is backed by the clock because it can lag by hours.

Pure-builder tests inject every input; the served-artifact laws skip loudly when
data/dfs.json is absent or was built before these fields existed.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


# ---------------------------------------------------------------------------
# Fixtures: two clubs, four bats, two arms. Self-contained on purpose, so this
# file does not pull the JS engine in just to build a Python payload.
# ---------------------------------------------------------------------------
def _corpus() -> dict:
    def hit(mid, name, team, pa):
        return {"mlbam": mid, "name": name, "side": "hit", "pos": "H", "team": team,
                "elig": ["OF"], "skill": {"hem_plus": 110},
                "ros": {"pa": pa, "ab": pa * 0.9, "h": pa * 0.25, "single": pa * 0.16,
                        "double": pa * 0.05, "triple": pa * 0.005, "hr": pa * 0.03,
                        "bb": pa * 0.09, "hbp": pa * 0.01, "so": pa * 0.2,
                        "sb": 2.0, "cs": 0.5, "r": pa * 0.13, "rbi": pa * 0.12}}

    def sp(mid, name, team):
        return {"mlbam": mid, "name": name, "side": "pit", "pos": "SP", "team": team,
                "elig": ["P"], "skill": {"sem_plus": 110},
                "ros": {"role": "SP", "ip": 55.0, "bf": 231.0, "k": 55.0, "bb": 16.0,
                        "hr": 6.0, "hbp": 2.0, "h": 47.0, "er": 21.0, "gs": 10,
                        "qs": 5.0, "w": 3.5, "l": 2.5}}
    return {"season": 2026, "season_fraction": 0.70, "generated_at": "2026-08-05T00:00:00Z",
            "players": [hit(1, "Alpha Bat", "BOS", 260), hit(2, "Bravo Bat", "BOS", 120),
                        hit(3, "Charlie Bat", "NYY", 250), hit(4, "Delta Bat", "NYY", 200),
                        sp(10, "Echo Arm", "BOS"), sp(11, "Foxtrot Arm", "NYY")]}


def _game(pk=1, day="2026-08-05", first_pitch="23:05:00", status="Preview"):
    return {"game_pk": pk, "date": day, "datetime": f"{day}T{first_pitch}Z",
            "status": status, "double_header": False,
            "venue": {"id": 3313, "name": "Yankee Stadium"},
            "home": {"team_id": 147, "team": "New York Yankees", "org": "NYY",
                     "probable": {"mlbam": 11, "name": "Foxtrot Arm"}},
            "away": {"team_id": 111, "team": "Boston Red Sox", "org": "BOS",
                     "probable": {"mlbam": 10, "name": "Echo Arm"}}}


def _build(**over):
    import dfs_export as dx
    kw = dict(day="2026-08-05", fantasy=_corpus(), games=[_game()], positions={},
              park={}, teams_ctx={"BOS": {"offense_plus": 104, "bullpen_plus": 99},
                                  "NYY": {"offense_plus": 102, "bullpen_plus": 101}},
              lineups={})
    kw.update(over)
    return dx.build_payload(**kw)


def _served(p, side):
    return sum(1 for r in p["players"] if r["side"] == side)


# ===========================================================================
# 1. Served counts (L17-F1)
# ===========================================================================
def test_integrity_counts_the_board_it_serves_not_the_pool_it_priced():
    """Two bats off the active roster. The chip counts must equal the rows the
    page renders, and the priced pool and the removals ride beside them."""
    p = _build(active_ids={1, 3, 10, 11})
    g = p["integrity"]
    assert g["n_hitters"] == _served(p, "hit") == 2
    assert g["n_pitchers"] == _served(p, "pit") == 2
    assert g["n_hitters"] + g["n_pitchers"] == p["n_players"] == len(p["players"])
    assert g["n_hitters_priced"] == 4 and g["n_pitchers_priced"] == 2
    assert g["n_hitters_removed_off_roster"] == 2
    assert g["n_pitchers_removed_off_roster"] == 0
    assert (g["n_hitters_removed_off_roster"] + g["n_pitchers_removed_off_roster"]
            == p["roster_filter"]["n_removed"] == len(p["off_roster"]))
    assert g["ok"] is True and p["empty_reason"] is None


def test_the_join_detector_still_reads_the_priced_pool():
    """THE VERIFIER'S TRAP. Every NYY bat is roster-removed. The hitter JOIN
    found them, so NYY is not a join miss, and `orgs_without_hitters` must not
    say it is. The served count still drops to the BOS bats alone."""
    p = _build(active_ids={1, 2, 10, 11})
    g = p["integrity"]
    assert g["orgs_without_hitters"] == [], g["orgs_without_hitters"]
    assert g["n_hitters"] == _served(p, "hit") == 2
    assert {r["team"] for r in p["players"] if r["side"] == "hit"} == {"BOS"}
    assert g["n_hitters_removed_off_roster"] == 2
    assert g["ok"] is True


def test_a_real_join_miss_is_still_reported():
    """The other half of the trap: a club the join genuinely missed is still
    named, with or without a roster filter."""
    corpus = _corpus()
    for r in corpus["players"]:
        if r["side"] == "hit" and r["team"] == "NYY":
            r["team"] = None
    p = _build(fantasy=corpus, active_ids={1, 2, 3, 4, 10, 11})
    assert p["integrity"]["orgs_without_hitters"] == ["NYY"]


def test_no_roster_filter_means_served_equals_priced():
    p = _build(active_ids=None)
    g = p["integrity"]
    assert g["n_hitters"] == g["n_hitters_priced"] == _served(p, "hit") == 4
    assert g["n_hitters_removed_off_roster"] == 0
    assert g["n_pitchers_removed_off_roster"] == 0
    assert p["roster_filter"]["applied"] is False


def test_a_roster_filter_that_removes_every_bat_is_a_collapse_not_a_board():
    """The guard used to read the pre-filter count, so a roster walk that
    removed every bat served a pitchers-only board with integrity.ok True: the
    2026-08-05 defect, one layer down. It now reads the board, and it names the
    roster filter rather than calling it a join or a projection gap."""
    p = _build(active_ids={10, 11})
    g = p["integrity"]
    assert g["n_hitters"] == 0 and g["n_hitters_priced"] == 4
    assert g["ok"] is False and g["kind"] == "collapsed_slate"
    assert "active-roster filter" in g["message"]
    assert "could be matched to a club" not in g["message"]
    assert p["empty_reason_kind"] == "collapsed_slate"


def test_a_board_emptied_by_the_roster_filter_is_not_called_unprojected():
    """Every priced row removed. Those rows HAD projections, so the
    no_projections sentence would be false; the collapse names what happened."""
    p = _build(active_ids={999})
    assert p["n_players"] == 0
    assert p["empty_reason_kind"] == "collapsed_slate", p["empty_reason"]
    assert "rest-of-season projection" not in p["empty_reason"]


def test_a_roster_filter_that_removes_every_starter_is_named():
    """Four announced probables, all priced, all roster-removed: the pitcher
    side collapsed, and the message says it was the roster check."""
    import dfs_export as dx
    games = [_game(pk=1), _game(pk=2, first_pitch="23:40:00")]
    assert dx._MIN_PROBABLES_FOR_COLLAPSE <= 4
    p = _build(games=games, active_ids={1, 2, 3, 4})
    g = p["integrity"]
    assert g["n_pitchers"] == 0 and g["n_pitchers_priced"] == 2
    # Two arms across four announced slots (each arm starts one game in the
    # fixture's doubleheader), so the pitcher guard's threshold is met.
    assert g["n_probables_announced"] == 4
    assert g["ok"] is False and "active-roster filter" in g["message"]


def test_the_build_log_reports_the_served_counts(tmp_path, monkeypatch):
    """The second surface the stale count reached. The log line's hitters and
    starters now sum to its own player count."""
    import dfs_export as dx
    payload = _build(active_ids={1, 3, 10, 11})
    monkeypatch.setattr(dx, "build_payload", lambda **_kw: payload)
    monkeypatch.setattr(dx, "_active_roster_ids", lambda: None)
    monkeypatch.setattr(dx, "_archive_slate", lambda *_a, **_k: None)
    monkeypatch.setattr(dx.fe, "_record_ingest_safe", lambda *_a, **_k: None)
    lines = []
    dx.refresh(log=lines.append, day="2026-08-05", out_path=tmp_path / "dfs.json")
    msg = [ln for ln in lines if "players on the board" in ln]
    assert msg, lines
    m = re.search(r"(\d+) players on the board .* - (\d+) hitters, (\d+) starters", msg[0])
    assert m, msg[0]
    assert int(m.group(1)) == int(m.group(2)) + int(m.group(3)) == payload["n_players"]


# ===========================================================================
# 2. The in-game market (L14-02)
# ===========================================================================
def _snapshot(events, captured_at):
    books = [{"key": bk, "title": bk, "markets": [
        {"key": "h2h", "outcomes": [{"name": "New York Yankees", "price": -150},
                                    {"name": "Boston Red Sox", "price": 130}]},
        {"key": "totals", "outcomes": [{"name": "Over", "price": -110, "point": 9.0},
                                       {"name": "Under", "price": -110, "point": 9.0}]}]}
        for bk in ("a", "b", "c")]
    return {"captured_at": captured_at, "kind": "open", "slate_date": "2026-08-05",
            "events": [{"id": f"e{i}", "commence_time": ct,
                        "home_team": "New York Yankees", "away_team": "Boston Red Sox",
                        "bookmakers": books} for i, ct in enumerate(events)]}


def _serve_snapshot(monkeypatch, wrap):
    import betting_ingest as bi
    monkeypatch.setattr(bi, "latest_snapshot", lambda **_k: wrap)


def test_the_started_predicate_is_inclusive_and_refuses_nothing_it_cannot_read():
    import betting_ingest as bi
    t0 = datetime(2026, 8, 5, 23, 5, tzinfo=timezone.utc)
    ev = {"commence_time": "2026-08-05T23:05:00Z"}
    assert bi.odds_event_started(ev, t0) is True                    # AT first pitch
    assert bi.odds_event_started(ev, t0 + timedelta(hours=2)) is True
    assert bi.odds_event_started(ev, t0 - timedelta(seconds=1)) is False
    # A naive stamp or clock is UTC, which is what both producers write.
    assert bi.odds_event_started({"commence_time": "2026-08-05T23:05:00"}, t0) is True
    assert bi.odds_event_started(ev, t0.replace(tzinfo=None)) is True
    # An unreadable or missing stamp is not called started (team_bets' rule).
    for bad in (None, "", "not a time"):
        assert bi.odds_event_started({"commence_time": bad}, t0) is False
    assert bi.odds_event_started({}, t0) is False


def test_both_readers_of_a_snapshot_share_the_one_started_rule():
    """One definition. A private copy in either module is how the second
    consumer went without the filter for a month."""
    be_src = (ROOT / "betting_export.py").read_text(encoding="utf-8")
    dx_src = (ROOT / "dfs_export.py").read_text(encoding="utf-8")
    body = be_src[be_src.index("def team_bets("):]
    body = body[:body.index("\ndef ")]
    assert "bi.odds_event_started(ev, now)" in body
    assert "t <= now" not in body, "team_bets carries a private copy of the rule"
    assert "bi.odds_event_started(ev, as_of)" in dx_src


def test_a_game_already_under_way_at_capture_gets_no_market(monkeypatch):
    """The 2026-09-10 shape: first pitch 17:05, snapshot 19:34."""
    import dfs_export as dx
    _serve_snapshot(monkeypatch, _snapshot(["2026-08-05T17:06:00Z"],
                                           "2026-08-05T19:34:23+00:00"))
    games = [_game(first_pitch="17:05:00", status="Live")]
    idx, meta = dx._vegas_index("2026-08-05", games)
    assert idx == {}
    assert meta["n_rejected_in_game"] == 1 and meta["in_game_game_pks"] == [1]
    # Its own counter: the different-day refusal means something else.
    assert meta["n_rejected_on_time"] == 0
    assert meta["in_game_basis"] == "snapshot_captured_at"
    assert "after first pitch" in meta["reason"]


def test_the_refusal_is_judged_at_the_capture_stamp_not_the_build_clock(monkeypatch):
    """A price read BEFORE first pitch is the pregame market even when the
    board is built after the game starts, so a backfill judges each snapshot
    the way its own day did. With no readable stamp the build clock decides,
    which can only refuse more."""
    import dfs_export as dx
    games = [_game(first_pitch="23:05:00")]
    late = datetime(2026, 8, 6, 3, 0, tzinfo=timezone.utc)
    _serve_snapshot(monkeypatch, _snapshot(["2026-08-05T23:06:00Z"],
                                           "2026-08-05T19:00:00Z"))
    idx, meta = dx._vegas_index("2026-08-05", games, now=late)
    assert set(idx) == {1} and meta["n_rejected_in_game"] == 0
    assert idx[1]["commence_time"] == "2026-08-05T23:06:00Z"
    _serve_snapshot(monkeypatch, _snapshot(["2026-08-05T23:06:00Z"], "unreadable"))
    idx, meta = dx._vegas_index("2026-08-05", games, now=late)
    assert idx == {} and meta["in_game_basis"] == "build_clock"
    assert meta["n_rejected_in_game"] == 1


def test_a_live_doubleheader_opener_does_not_borrow_the_nightcap_market(monkeypatch):
    """MATCH FIRST, THEN REFUSE. Dropping started events before the match would
    hand game one (under way) game two's pregame market, which sits inside the
    six-hour tolerance."""
    import dfs_export as dx
    _serve_snapshot(monkeypatch, _snapshot(["2026-08-05T17:06:00Z", "2026-08-05T21:11:00Z"],
                                           "2026-08-05T19:34:00Z"))
    games = [_game(pk=1, first_pitch="17:05:00", status="Live"),
             _game(pk=2, first_pitch="21:10:00")]
    idx, meta = dx._vegas_index("2026-08-05", games)
    assert set(idx) == {2}
    assert meta["in_game_game_pks"] == [1] and meta["n_rejected_in_game"] == 1
    assert idx[2]["commence_time"] == "2026-08-05T21:11:00Z"


def test_the_payload_names_a_refused_game_and_moves_no_price(monkeypatch):
    """Through build_payload on its OWN slate (the only path that reads odds):
    a game whose only snapshot was read after its first pitch carries vegas
    null plus the refusal, no row carries its market, the integrity count says
    so, and not one point total moves. The build clock sits BEFORE that first
    pitch (a replay of the pregame build against a later capture), so the game
    is still draftable and the refusal is the only thing that touches it."""
    import dfs_export as dx
    games = [_game(pk=1, first_pitch="17:05:00"),
             _game(pk=2, first_pitch="23:40:00")]
    monkeypatch.setattr(dx, "_schedule_for_day",
                        lambda day, fantasy: (games, {"source": "statsapi",
                                                      "verified_empty": False,
                                                      "stale": False}))
    _serve_snapshot(monkeypatch, _snapshot(["2026-08-05T17:06:00Z", "2026-08-05T23:41:00Z"],
                                           "2026-08-05T19:34:00Z"))
    p = _build(games=None, now=datetime(2026, 8, 5, 17, 0, tzinfo=timezone.utc))
    assert p["excluded_games"] == [] and p["slate_filter"]["n_draftable"] == 2
    by_pk = {g["game_pk"]: g for g in p["games"]}
    assert by_pk[1]["vegas"] is None and by_pk[1]["vegas_refused"] == "in_game"
    assert by_pk[2]["vegas"] and "vegas_refused" not in by_pk[2]
    assert p["integrity"]["vegas_games"] == 1
    assert p["integrity"]["vegas_games_refused_in_game"] == 1
    assert p["vegas_source"]["n_rejected_in_game"] == 1
    for r in p["players"]:
        if r["game_pk"] == 1:
            assert not ({"vegas_itt", "vegas_p_win", "vegas_opp_itt"} & set(r["ctx"])), r
    # Display only: the refusal changes no projection.
    base = _build(games=games, vegas={})
    assert ({(r["mlbam"], r["side"]): r["pts"] for r in p["players"]}
            == {(r["mlbam"], r["side"]): r["pts"] for r in base["players"]})


# ===========================================================================
# 2b. Only draftable games reach the board (owner decision 5)
# ===========================================================================
def test_a_started_or_final_game_leaves_the_board_and_the_optimizer():
    import dfs_export as dx
    games = [_game(pk=1, first_pitch="17:05:00", status="Live"),
             _game(pk=2, first_pitch="18:05:00", status="Final"),
             _game(pk=3, first_pitch="23:40:00")]
    p = _build(games=games)
    assert {g["game_pk"] for g in p["games"]} == {3}
    assert {r["game_pk"] for r in p["players"]} == {3}
    ex = {x["game_pk"]: x for x in p["excluded_games"]}
    assert ex[1]["state"] == "started" and ex[2]["state"] == "final"
    assert ex[1]["basis"] == ex[2]["basis"] == "schedule_status"
    assert (ex[1]["away"], ex[1]["home"]) == ("BOS", "NYY")
    f = p["slate_filter"]
    assert (f["n_scheduled"], f["n_draftable"], f["n_excluded"]) == (3, 1, 2)
    assert f["by_state"] == {"started": 1, "final": 1}
    assert p["n_games"] == 1 and p["n_games_scheduled"] == 3
    # An injected slate reads no clock unless the caller hands it one.
    assert f["clock"] is None
    assert dx.game_state(_game(first_pitch="17:05:00")) == "open"


def test_a_postponed_game_is_labelled_postponed_not_final():
    import dfs_export as dx
    pp = dict(_game(pk=4), status="Final", coded_state="D",
              detailed_state="Postponed", status_reason="Rain")
    for g, want in ((pp, "postponed"),
                    (dict(_game(), status="Live", coded_state="T",
                          detailed_state="Suspended: Rain"), "suspended"),
                    (dict(_game(), status="Final", coded_state="C",
                          detailed_state="Cancelled"), "cancelled"),
                    (dict(_game(), status="Preview", coded_state="P",
                          detailed_state="Delayed Start"), "open"),
                    (dict(_game(), status=None), "open")):
        assert dx.game_state(g) == want, g
    p = _build(games=[pp, _game(pk=5)])
    ex = p["excluded_games"]
    assert [(x["game_pk"], x["state"], x["detailed_state"], x["reason"]) for x in ex] == [
        (4, "postponed", "Postponed", "Rain")]
    assert {r["game_pk"] for r in p["players"]} == {5}


def test_the_clock_locks_a_game_the_cached_status_still_calls_preview():
    """The 2026-09-11 build: PIT at CHC, first pitch 18:20 UTC, still read
    "Preview" off a schedule cached at 17:35 when the board built at 19:55."""
    import dfs_export as dx
    games = [_game(pk=1, first_pitch="17:05:00"), _game(pk=2, first_pitch="23:40:00")]
    clock = datetime(2026, 8, 5, 19, 0, tzinfo=timezone.utc)
    p = _build(games=games, now=clock)
    assert {g["game_pk"] for g in p["games"]} == {2}
    x = p["excluded_games"][0]
    assert (x["game_pk"], x["state"], x["basis"]) == (1, "started", "scheduled_first_pitch")
    assert p["slate_filter"]["clock"] == "2026-08-05T19:00:00Z"
    # AT first pitch is locked; a TBD start (doubleheader game two) is not read.
    at = datetime(2026, 8, 5, 17, 5, tzinfo=timezone.utc)
    assert dx.game_state(_game(first_pitch="17:05:00"), at) == "started"
    tbd = dict(_game(first_pitch="17:05:00"), start_time_tbd=True)
    assert dx.game_state(tbd, clock) == "open"
    # An unreadable time is never excluded on the clock.
    assert dx.game_state(dict(_game(), datetime="not a time"), clock) == "open"


def test_a_slate_with_nothing_left_to_draft_is_slate_closed(tmp_path, monkeypatch):
    import dfs_export as dx
    games = [_game(pk=1, status="Final"), _game(pk=2, first_pitch="18:05:00", status="Live")]
    p = _build(games=games)
    assert p["empty_reason_kind"] == "slate_closed"
    assert p["players"] == [] and p["games"] == []
    assert [x["game_pk"] for x in p["excluded_games"]] == [1, 2]
    assert "nothing is left to draft" in p["empty_reason"]
    # A closed slate is a fact about the day: refresh publishes it rather than
    # carrying an earlier board of the same games forward.
    assert "slate_closed" not in dx._KEEP_PREVIOUS_KINDS
    monkeypatch.setattr(dx, "build_payload", lambda **_kw: p)
    monkeypatch.setattr(dx, "_active_roster_ids", lambda: None)
    monkeypatch.setattr(dx.fe, "_record_ingest_safe", lambda *_a, **_k: None)
    out = tmp_path / "dfs.json"
    out.write_text(json.dumps({"slate_date": "2026-08-05", "players": [{"mlbam": 1}],
                               "n_players": 1}), encoding="utf-8")
    assert dx.refresh(log=lambda *_a, **_k: None, day="2026-08-05", out_path=out,
                      archive_dir=tmp_path / "hist") == 0
    assert json.loads(out.read_text(encoding="utf-8"))["empty_reason_kind"] == "slate_closed"


def test_the_payload_names_its_eligibility_source(monkeypatch):
    """Owner decision 24: eligibility reads the nightly innings feed, and the
    payload's label names the file the one rule ACTUALLY opened, not a constant
    compared with itself."""
    import dfs_export as dx
    p = _build()
    assert p["elig_source"] == "fielding_innings.json"
    opened = []
    real = dx.fe._load_json

    def spy(name, *a, **k):
        opened.append(name)
        return real(name, *a, **k)

    monkeypatch.setattr(dx.fe, "_load_json", spy)
    dx.positions_by_mlbam()
    assert p["elig_source"] in opened, opened
    assert "mlb_fielding_positions.json" not in opened


# ===========================================================================
# 3. The served artifact: laws that hold in any build carrying these fields
# ===========================================================================
def _dfs_payload():
    p = DATA / "dfs.json"
    if not p.exists():
        pytest.skip("data/dfs.json has not been built")
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("empty_reason") or not d.get("players"):
        pytest.skip("data/dfs.json is an empty-slate payload")
    return d


def test_served_dfs_counts_equal_the_served_rows():
    d = _dfs_payload()
    g = d.get("integrity") or {}
    if "n_hitters_priced" not in g:
        pytest.skip("data/dfs.json predates the priced/served split (2026-09-11); "
                    "its n_hitters is the PRE-filter count this file exists to retire")
    assert d["n_players"] == len(d["players"])
    assert g["n_hitters"] == sum(1 for r in d["players"] if r.get("side") == "hit")
    assert g["n_pitchers"] == sum(1 for r in d["players"] if r.get("side") == "pit")
    assert g["n_hitters_priced"] - g["n_hitters"] == g["n_hitters_removed_off_roster"] >= 0
    assert g["n_pitchers_priced"] - g["n_pitchers"] == g["n_pitchers_removed_off_roster"] >= 0
    rf = d.get("roster_filter") or {}
    assert (g["n_hitters_removed_off_roster"] + g["n_pitchers_removed_off_roster"]
            == int(rf.get("n_removed") or 0))


def test_no_served_row_sits_on_a_game_that_cannot_be_drafted():
    d = _dfs_payload()
    if "slate_filter" not in d:
        pytest.skip("data/dfs.json predates the draftable filter (2026-09-11)")
    gone = {x["game_pk"] for x in d.get("excluded_games") or []}
    assert not gone & {g["game_pk"] for g in d["games"]}
    assert not gone & {r["game_pk"] for r in d["players"]}
    f = d["slate_filter"]
    assert f["n_draftable"] == len(d["games"]) == d["n_games"]
    assert f["n_excluded"] == len(gone)
    assert f["n_scheduled"] == f["n_draftable"] + f["n_excluded"]
    clock = f.get("clock")
    for g in d["games"]:
        assert g.get("status") not in ("Live", "Final"), g["game_pk"]
        if clock and g.get("datetime"):
            assert g["datetime"] > clock, (g["game_pk"], g["datetime"], clock)


def test_no_served_market_was_read_after_its_first_pitch():
    d = _dfs_payload()
    src = d.get("vegas_source") or {}
    if "n_rejected_in_game" not in src:
        pytest.skip("data/dfs.json predates the in-game refusal (2026-09-11)")
    if src.get("in_game_basis") != "snapshot_captured_at":
        pytest.skip("the snapshot carried no readable capture stamp")
    cap = datetime.fromisoformat(str(src["captured_at"]).replace("Z", "+00:00"))
    refused = set(src.get("in_game_game_pks") or [])
    for g in d.get("games") or []:
        v = g.get("vegas")
        if v:
            ct = datetime.fromisoformat(str(v["commence_time"]).replace("Z", "+00:00"))
            assert ct > cap, (g["game_pk"], v["commence_time"], src["captured_at"])
            assert g["game_pk"] not in refused
        if g.get("vegas_refused") == "in_game":
            assert g["game_pk"] in refused and not v
    assert (d["integrity"].get("vegas_games_refused_in_game")
            == sum(1 for g in d["games"] if g.get("vegas_refused") == "in_game")
            == src["n_rejected_in_game"])


# ===========================================================================
# 4. The client renders the served counts and the refusal
# ===========================================================================
def _js():
    pytest.importorskip("py_mini_racer")
    import test_fantasy_split as tfs
    return tfs


def _chip(html, label):
    m = re.search(re.escape(label) + r'</span><span class="dfs-kv-v">([^<]*)<', html)
    return m.group(1) if m else None


def test_the_client_labels_the_board_count_and_states_the_removals():
    tfs = _js()
    d = json.loads(tfs._ctx_payload())
    d["integrity"].update({"n_hitters": 6, "n_pitchers": 2,
                           "n_hitters_priced": 8, "n_pitchers_priced": 2,
                           "n_hitters_removed_off_roster": 2,
                           "n_pitchers_removed_off_roster": 0})
    html = tfs._dfs_boot(json.dumps(d)).eval('__go("#section=slate")')
    assert _chip(html, "Hitters on the board") == "6", html[:900]
    assert _chip(html, "Starters on the board") == "2"
    assert _chip(html, "Hitters priced") is None
    assert _chip(html, "Left off, not on an active roster") == "2"
    assert ("We priced 8 hitters and 2 starters. 2 hitters and 0 starters are not on "
            "a current active roster") in html


def test_the_client_keeps_the_old_label_on_an_old_payload():
    """A payload from before the split: its n_hitters IS the priced count, and
    relabelling it as the board would make the old defect a new one."""
    tfs = _js()
    html = tfs._dfs_boot(tfs._ctx_payload()).eval('__go("#section=slate")')
    assert _chip(html, "Hitters priced") == "6"
    assert _chip(html, "Hitters on the board") is None
    assert "Left off, not on an active roster" not in html


def test_the_client_says_a_refused_market_was_refused():
    tfs = _js()
    d = json.loads(tfs._ctx_payload())
    live = json.loads(json.dumps(d["games"][0]))
    live.update({"game_pk": 2, "vegas": None, "vegas_refused": "in_game"})
    live["home"].pop("vegas_itt", None)
    live["away"].pop("vegas_itt", None)
    d["games"].append(live)
    d["n_games"] = 2
    d["vegas_source"].update({"n_matched": 1, "n_rejected_in_game": 1,
                              "in_game_game_pks": [2]})
    d["integrity"]["vegas_games_refused_in_game"] = 1
    html = tfs._dfs_boot(json.dumps(d)).eval('__go("#section=slate")')
    assert html.count("no total: the odds we hold were taken after first pitch") == 1
    assert "1 game on this slate had already started when that snapshot was taken" in html
    assert "total 9" in html                        # the other game keeps its market


# ===========================================================================
# 5. The season check runs before the corpus check (M11-01, 2026-09-24)
# ===========================================================================
# An empty corpus at the end of the season published "Pipeline outage"
# because the no_corpus check ran first, so season_over could never fire; and
# the no_corpus sentence said the corpus "has not been built yet" about a
# corpus that had been built and came out empty.
def test_a_finished_season_reads_season_over_not_an_outage():
    empty_at_end = dict(_corpus(), season_fraction=1.0, players=[])
    assert _build(fantasy=empty_at_end)["empty_reason_kind"] == "season_over"


def test_a_next_season_corpus_is_never_priced_as_a_slate():
    import fantasy_export as fe
    nxt = dict(_corpus(), season_fraction=0.99, mode=fe.MODE_NEXT_SEASON)
    p = _build(fantasy=nxt)
    assert p["empty_reason_kind"] == "season_over"
    assert p["players"] == []


def test_an_empty_corpus_mid_season_says_it_came_out_empty():
    p = _build(fantasy=dict(_corpus(), players=[]))
    assert p["empty_reason_kind"] == "no_corpus"
    assert "has not been built" not in p["empty_reason"]
    missing = _build(fantasy=[])
    assert missing["empty_reason_kind"] == "no_corpus"
    assert "has not been built" in missing["empty_reason"]
