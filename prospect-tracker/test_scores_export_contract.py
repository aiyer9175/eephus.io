# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The MLB Scores data contract (SCORES_PLAN 8, schema 1): the five file kinds.

The fixture-built half (SCORES_1_CORE_RULES): every kind is assembled from
test_fixtures/scores/ through scores_core's builders (the job's own latest.json
and index.json shapes are assembled here with the plan's keys), then every
file-independent rule of plan 8.5 runs over it. The job half (SCORES_2) runs
tools/scores_job.py once with a fake StatsAPI into a temp store and checks every
kind it writes; the live half reads whatever the job has written under its
resolved OUT and skips loudly when it has not. No test touches the network, the
repo's data/ or a real .cache/scores/.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import scores_core as sc
from test_scores_job import env  # noqa: F401  (the isolated job environment fixture)

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "scores"
GEN = "2026-10-02T12:00:00Z"
KINDS = ("latest", "index", "season_index", "date", "game")


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built():
    lg = load("league_constants_2026.json")
    sched = load("schedule_states.json")
    g_final = next(g for d in sched["dates"] for g in d["games"] if g["gamePk"] == 849845 and g["status"]["codedGameState"] == "F")
    g_live = next(g for g in sched["dates"][1]["games"] if g["gamePk"] == 849846 and g["status"]["codedGameState"] == "I")
    gf = sc.build_game_file(g_final, load("wp_849845_full.json"), load("box_849845.json"), lg,
                            generated_at=GEN, feed=load("feed_849845.json"))
    gf_live = sc.build_game_file(g_live, load("wp_849846_live.json"), None, lg, generated_at=GEN)
    gf_824592 = sc.build_game_file(load("game_824592.json"), load("wp_824592.json"), load("box_824592.json"), lg,
                                   generated_at=GEN)
    cards_0929 = [gf["card"]] + [sc.build_card(g, generated_at=GEN) for g in sched["dates"][1]["games"] if g["gamePk"] != 849846]
    cards_0929.append(gf_live["card"])
    date_0929 = sc.build_date_file("2026-09-29", cards_0929, {849845: gf, 849846: gf_live}, generated_at=GEN)
    date_0531 = sc.build_date_file("2026-05-31", [gf_824592["card"]], {824592: gf_824592}, generated_at=GEN)
    copyright_line = load("box_849845.json")["copyright"]
    season = {"schema": sc.SCHEMA, "season": 2026,
              "dates": [{"d": "2026-05-31", "n": 1, "types": ["R"], "rev": sc.rev_of(date_0531), "flags": []},
                        {"d": "2026-09-29", "n": len(cards_0929), "types": ["F"], "rev": sc.rev_of(date_0929), "flags": []}],
              "bracket": sc.build_bracket(load("postseason_series_2026.json"), season=2026)}
    index = {"schema": sc.SCHEMA, "generated_at": GEN,
             "seasons": [{"season": 2026, "rev": sc.rev_of(season), "n_dates": 2}],
             "registry": [{"model_id": "scores_mlb_wp", "verdict": "provisional", "sentence": "MLB, provisional"}],
             "accuracy": {"mlb_wp": {"feed_brier": None, "base_rate_brier": None, "n_plays": None, "seasons": [],
                                     "pregame_values": {"500": 2}, "artifact_generated_at": None}},
             "rules": {"stars": {"rule": sc.STARS_RULE, "min_outs": sc.MIN_OUTS, "min_coverage": sc.MIN_COVERAGE,
                                 "first_star_winner": sc.FIRST_STAR_WINNER},
                       "plays": {"rule": sc.PLAYS_RULE, "min_swing": sc.MIN_SWING, "n": sc.N_BIG_PLAYS},
                       "video": {"embed": False, "branch": None, "video_hosts": list(sc.VIDEO_HOSTS),
                                 "caption_hosts": list(sc.CAPTION_HOSTS), "poster_host": sc.POSTER_HOST,
                                 "frame_host": sc.FRAME_HOST}},
             "copyright": copyright_line}
    latest = {"schema": sc.SCHEMA, "generated_at": GEN,
              "job": {"action": "live", "state": "ok", "next_by": "2026-10-02T12:08:00Z", "last_ok_at": GEN,
                      "down_after_s": 1800, "poll_live_s": 45, "poll_idle_s": 300, "errors_24h": 0, "refusals_24h": 0},
              "index_rev": sc.rev_of(index), "today": "2026-09-29", "next_game_date": "2026-09-30",
              "window": {"2026-09-29": {"rev": sc.rev_of(date_0929), "n": len(cards_0929), "live": 1, "final": 3,
                                        "pre": 4, "off": 0, "clips_matched": 0, "clips_of": 5, "stale_since": None}},
              "live": [{"pk": 849846, "date": "2026-09-29"}]}
    return {"latest.json": ("latest", latest), "index.json": ("index", index), "index-2026.json": ("season_index", season),
            "2026-09-29.json": ("date", date_0929), "2026-05-31.json": ("date", date_0531),
            "games/849845.json": ("game", gf), "games/849846.json": ("game", gf_live), "games/824592.json": ("game", gf_824592)}


def test_every_file_kind_passes_every_rule(built):
    results = sc.validate_files(built)
    for name, res in results.items():
        assert res["ok"], (name, res["refused"])
        assert res["logged"] == [], (name, res["logged"])
    assert {kind for kind, _obj in built.values()} == set(KINDS)


def test_kinds_resolve_from_names(built):
    for name, (kind, _obj) in built.items():
        assert sc.kind_of_name(name) == kind, name


def test_budgets_on_fixture_payloads(built):
    for name, (kind, obj) in built.items():
        n = len(sc.dumps(obj).encode("utf-8"))
        assert n <= sc.FILE_KINDS[kind]["budget"], (name, n)
        assert sc.FILE_KINDS[kind]["ceiling"] == 4 * sc.FILE_KINDS[kind]["budget"]


def test_plan_8_1_keys(built):
    latest = built["latest.json"][1]
    assert set(latest) == {"schema", "generated_at", "job", "index_rev", "today", "next_game_date", "window", "live"}
    assert set(latest["job"]) == {"action", "state", "next_by", "last_ok_at", "down_after_s", "poll_live_s", "poll_idle_s",
                                  "errors_24h", "refusals_24h"}
    index = built["index.json"][1]
    assert set(index) == {"schema", "generated_at", "seasons", "registry", "accuracy", "rules", "copyright"}
    assert set(index["accuracy"]["mlb_wp"]) == {"feed_brier", "base_rate_brier", "n_plays", "seasons", "pregame_values",
                                                "artifact_generated_at"}
    assert set(index["rules"]["video"]) == {"embed", "branch", "video_hosts", "caption_hosts", "poster_host", "frame_host"}
    season = built["index-2026.json"][1]
    assert set(season) == {"schema", "season", "dates", "bracket"} and "copyright" not in season
    date = built["2026-09-29.json"][1]
    assert set(date) == {"schema", "date", "generated_at", "day_top_plays", "games"}
    assert set(date["day_top_plays"][0]) == {"pk", "ab", "text", "bat_team", "before", "after", "swing", "live"}
    card = date["games"][0]
    want = {"pk", "rev", "type", "state", "reason", "start", "tbd", "dh", "venue", "series", "tv", "away", "home", "line",
            "sit", "end", "wp", "of_record", "star", "top_play", "videos", "flags", "weather", "makeup", "resume", "updated_at",
            "stale_since"}
    assert set(card) == want
    assert set(card["away"]) == {"team_id", "code", "name", "short", "wl", "r", "h", "e", "probable", "lineup_posted"}
    game = built["games/849845.json"][1]
    assert set(game) == {"schema", "pk", "rev", "generated_at", "card", "wp", "plays", "plays_big", "plays_big_reason",
                         "stars", "first_star_note", "stars_reason", "scoring", "box", "lineups", "info", "debuts",
                         "links", "clips"}
    assert set(game["wp"]) == {"pregame_home", "series", "coverage", "unattributed_home"}
    assert set(game["plays"][0]) == {"ab", "inning", "half", "text", "outs", "bases", "away", "home", "wp", "swing", "li",
                                     "clip", "event_clips", "reviews"}
    assert set(game["plays_big"][0]) == {"rank", "ab", "inning", "half", "situation", "text", "bat_team", "before", "after",
                                         "swing", "li", "clip", "clip_state"}
    assert set(game["stars"][0]) == {"rank", "id", "name", "team", "score", "basis", "why", "clip"}
    assert set(game["info"]) == {"umpires", "weather", "wind", "first_pitch", "duration_min", "delay_min", "attendance",
                                 "venue", "abs", "reviews", "mound_visits"}


def test_every_win_probability_quantity_is_an_integer_in_thousandths(built):
    for name, (kind, obj) in built.items():
        for path, key, v in sc._wp_values(obj):
            if v is None or (key == "score" and not path.startswith("stars")):
                continue
            assert isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 1000, (name, path, v)
    game = built["games/849845.json"][1]
    for row in game["wp"]["series"]:
        assert row[4] is None or (isinstance(row[4], int) and -1000 <= row[4] <= 1000)
    for p in game["plays"]:
        assert p["li"] is None or round(p["li"], 2) == p["li"]


def test_forbidden_keys_absent_at_every_depth(built):
    for name, (kind, obj) in built.items():
        assert sc.find_forbidden_keys(obj) == [], name
        assert sc.find_dashes(obj) == [], name


def test_live_game_file_has_no_stars_or_info(built):
    gf = built["games/849846.json"][1]
    assert gf["card"]["state"] == "live" and gf["stars"] == [] and gf["stars_reason"] == sc.REASON_NOT_FINAL
    assert gf["info"] is None and gf["box"] is None and gf["card"]["sit"]["inning"] == 1
    assert gf["wp"]["series"] and gf["wp"]["series"][-1][0] == 8
    assert gf["card"]["wp"] == {"home": 161, "ab": 8}


def test_copyright_only_where_rule_4_allows(built):
    line = load("box_849845.json")["copyright"]
    assert sc.MLB_TERMS_URL in line
    index = dict(built["index.json"][1])
    assert sc.validate_payload("index", index, name="index.json")["ok"]
    for other_key in ("notice", "terms", "mlb"):
        bad = dict(index)
        bad[other_key] = line
        res = sc.validate_payload("index", bad, name="index.json")
        assert not res["ok"] and any(r == "4" for r, m in res["refused"]), other_key
    # the rules.video block names allowlisted hosts, never a URL or a stranger
    bad = json.loads(json.dumps(index))
    bad["rules"]["video"]["frame_host"] = "https://streamable.com/m/x"
    assert any(r == "4" for r, m in sc.validate_payload("index", bad, name="index.json")["refused"])
    bad["rules"]["video"]["frame_host"] = "evil.example.com"
    assert any(r == "4" for r, m in sc.validate_payload("index", bad, name="index.json")["refused"])
    season = dict(built["index-2026.json"][1])
    season["copyright"] = line
    res = sc.validate_payload("season_index", season, name="index-2026.json")
    assert not res["ok"] and any(r == "4" for r, m in res["refused"])
    for name in ("latest.json", "2026-09-29.json", "games/849845.json"):
        kind, obj = built[name]
        bad = dict(obj)
        bad["copyright"] = line
        res = sc.validate_payload(kind, bad, name=name)
        assert not res["ok"] and any(r == "4" for r, m in res["refused"]), name


def test_date_files_hold_no_media_url(built):
    for name in ("2026-09-29.json", "2026-05-31.json", "latest.json", "index-2026.json"):
        assert sc.find_urls(built[name][1]) == [], name
    urls = sc.find_urls(built["games/849845.json"][1])
    assert urls == [("links.gameday", "https://www.mlb.com/gameday/849845")]


def test_revs_in_latest_and_index_match_their_files(built):
    latest = built["latest.json"][1]
    assert latest["window"]["2026-09-29"]["rev"] == sc.rev_of(built["2026-09-29.json"][1])
    assert latest["index_rev"] == sc.rev_of(built["index.json"][1])
    for gf_name in ("games/849845.json", "games/824592.json"):
        gf = built[gf_name][1]
        assert gf["card"]["rev"] == gf["rev"]
    cards = {c["pk"]: c for c in built["2026-09-29.json"][1]["games"]}
    assert cards[849845]["rev"] == built["games/849845.json"][1]["rev"]


# --------------------------------------------------------------------------- #
# The job half (SCORES_2): the job's own artifacts. One run of tools/scores_job.py
# with test_scores_job's fake StatsAPI into a temp store builds every kind; the
# live half reads whatever the job has written under its resolved OUT (inside
# the session temp directory under pytest) and skips loudly when it is empty.
# --------------------------------------------------------------------------- #
def _job_files(root: Path) -> dict:
    files = {}
    for p in root.rglob("*.json"):
        name = p.relative_to(root).as_posix()
        if sc.kind_of_name(name):
            files[name] = json.loads(p.read_text(encoding="utf-8"))
    return files


def test_the_job_writes_every_kind_and_each_passes_every_rule(env):
    from test_scores_job import FakeAPI, FakeClock, base_games, base_payloads, run_once, schedule_of, seed_state
    import scores_job as job
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    assert run_once(env, api, clock)["exit"] == 0
    files = _job_files(env["out"])
    assert {sc.kind_of_name(n) for n in files} == set(KINDS)
    for name, res in sc.validate_files(files).items():
        assert res["ok"], (name, res["refused"])
        kind = sc.kind_of_name(name)
        assert res["bytes"] <= sc.FILE_KINDS[kind]["budget"], (name, res["bytes"])
    latest, index, season = files["latest.json"], files["index.json"], files["index-2026.json"]
    assert set(latest) == {"schema", "generated_at", "job", "index_rev", "today", "next_game_date", "window", "live",
                           "standings"}
    assert set(latest["job"]) == {"action", "state", "next_by", "last_ok_at", "down_after_s", "poll_live_s",
                                  "poll_idle_s", "errors_24h", "refusals_24h"}
    assert set(latest["window"]) == {f"2026-{d}" for d in ("09-29", "09-30", "10-01", "10-02", "10-03", "10-04",
                                                           "10-05", "10-06", "10-07")}
    assert set(next(iter(latest["window"].values()))) == {"rev", "n", "live", "final", "pre", "off", "clips_matched",
                                                          "clips_of", "stale_since"}
    assert set(index) == {"schema", "generated_at", "seasons", "registry", "accuracy", "rules", "copyright",
                          "standings_seasons"}
    # STANDINGS_2: no standings file on disk here, so the block is null and the list empty
    assert latest["standings"] is None and index["standings_seasons"] == []
    assert set(index["accuracy"]["mlb_wp"]) == {"feed_brier", "base_rate_brier", "n_plays", "seasons",
                                                "pregame_values", "artifact_generated_at"}
    assert set(season) == {"schema", "season", "dates", "bracket"}
    assert set(season["dates"][0]) == {"d", "n", "types", "rev", "flags"}
    assert job.verify_revs(job.Writer(env["out"])) == []


def test_live_artifacts_when_present():
    import scores_job as job
    roots = [job.out_dir()]
    if os.environ.get("EEPHUS_SCORES_OUT"):
        roots.append(Path(os.environ["EEPHUS_SCORES_OUT"]))
    files = {}
    for root in roots:
        if root.exists():
            files.update(_job_files(root))
    if not files:
        pytest.skip("live scores artifacts absent: the job has written nothing under its resolved OUT here "
                    "(the session temp directory under pytest); the fixture-built half and the job half ran")
    for name, res in sc.validate_files(files).items():
        assert res["ok"], (name, res["refused"])

# --------------------------------------------------------------------------- #
# The October bracket (SCORES_4b): the season index's `bracket` block, built
# from the postseason-series fixtures (the sample of 2026-09-30 and the one live
# read of 2026-10-07). Series state and results only: no probability anywhere.
# --------------------------------------------------------------------------- #
BRACKET_KEYS = {"season", "first", "last", "done", "rounds"}
ROUND_KEYS = {"type", "name", "series"}
SERIES_KEYS = {"id", "type", "lg", "best_of", "over", "winner_id", "text", "clubs", "games"}
CLUB_KEYS = {"team_id", "code", "name", "wins"}
GAME_KEYS = {"pk", "n", "date", "state", "away_id", "home_id", "away_r", "home_r", "winner_id", "if_necessary"}


def _series(block):
    return {s["id"]: s for r in block["rounds"] for s in r["series"]}


def test_the_bracket_block_from_the_postseason_fixture():
    raw = load("postseason_series_2026.json")
    b = sc.build_bracket(raw, season=2026)
    assert set(b) == BRACKET_KEYS and b["season"] == 2026 and b["done"] is False
    assert (b["first"], b["last"]) == ("2026-09-29", "2026-10-31")
    assert [r["type"] for r in b["rounds"]] == ["F", "D", "L", "W"]
    assert [r["name"] for r in b["rounds"]] == ["Wild Card Series", "Division Series", "Championship Series",
                                               "World Series"]
    assert [[s["id"] for s in r["series"]] for r in b["rounds"]] == [
        ["F_1", "F_2", "F_3", "F_4"], ["D_1", "D_2", "D_3", "D_4"], ["L_1", "L_2"], ["W_1"]]
    for r in b["rounds"]:
        assert set(r) == ROUND_KEYS
        for s in r["series"]:
            assert set(s) == SERIES_KEYS and len(s["clubs"]) == 2
            assert all(set(c) == CLUB_KEYS for c in s["clubs"]) and all(set(g) == GAME_KEYS for g in s["games"])
    ss = _series(b)
    # every game the fixture lists, none invented
    assert sum(len(s["games"]) for s in ss.values()) == raw["totalGames"] == 53
    f1 = ss["F_1"]
    assert (f1["lg"], f1["best_of"], f1["over"], f1["text"]) == ("AL", 3, False, "CHW leads 1-0")
    assert [(c["code"], c["wins"]) for c in f1["clubs"]] == [("HOU", 0), ("CHW", 1)]
    assert f1["games"][0] == {"pk": 849849, "n": 1, "date": "2026-09-29", "state": "final", "away_id": 145,
                              "home_id": 117, "away_r": 6, "home_r": 3, "winner_id": 145, "if_necessary": False}
    assert f1["games"][2]["if_necessary"] is True and f1["games"][2]["away_r"] is None
    # the warmup game 849841 carries 0-0 in MLB's payload but is not under way: no score printed
    assert ss["F_3"]["games"][1]["state"] == "pregame" and ss["F_3"]["games"][1]["away_r"] is None
    # MLB's placeholders: code null, "HOU/CWS" as "Winner of HOU and CWS", the rest verbatim
    d2 = ss["D_2"]
    assert d2["clubs"][0] == {"team_id": 114, "code": "CLE", "name": "Cleveland Guardians", "wins": 0}
    assert d2["clubs"][1] == {"team_id": 5528, "code": None, "name": "Winner of HOU and CWS", "wins": 0}
    assert d2["text"] == "Game 1: October 3"
    assert [c["name"] for c in ss["L_2"]["clubs"]] == ["NL Higher Seed", "NL Lower Seed"]
    assert [c["name"] for c in ss["W_1"]["clubs"]] == ["Higher Seed League Champion", "Lower Seed League Champion"]
    assert ss["W_1"]["lg"] is None and ss["W_1"]["best_of"] == 7
    for s in ss.values():
        for c in s["clubs"]:
            assert (c["code"] is None) == (c["team_id"] not in sc.CLUB_BY_ID)


def test_the_bracket_after_the_wild_card_round_from_the_live_read():
    b = sc.build_bracket(load("postseason_series_2026-10-07.json"), season=2026)
    ss = _series(b)
    assert {k: (s["over"], s["text"], s["winner_id"]) for k, s in ss.items() if s["type"] == "F"} == {
        "F_1": (True, "CHW wins 2-0", 145), "F_2": (True, "NYY wins 2-0", 147),
        "F_3": (True, "ATL wins 2-1", 144), "F_4": (True, "SDP wins 2-0", 135)}
    assert len(ss["F_1"]["games"]) == 2 and len(ss["F_3"]["games"]) == 3
    assert [ss[k]["text"] for k in ("D_1", "D_2", "D_3", "D_4")] == [
        "TBR leads 2-0", "CHW leads 2-0", "MIL leads 2-1", "LAD leads 2-1"]
    assert all(c["code"] for k in ("D_1", "D_2", "D_3", "D_4") for c in ss[k]["clubs"])
    assert b["done"] is False and b["last"] == "2026-10-31"


def _finish(raw, sid, winner_side="home"):
    """Mark a series' first games final for one side until it clinches; leave
    its if-necessary games listed and unplayed, as MLB sometimes does."""
    for s in raw["series"]:
        if s["series"]["id"] != sid:
            continue
        need = max(g["gamesInSeries"] for g in s["games"]) // 2 + 1
        for g in s["games"][:need]:
            g["status"] = {"abstractGameState": "Final", "codedGameState": "F", "detailedState": "Final"}
            for side, tid, name in (("away", 147, "New York Yankees"), ("home", 119, "Los Angeles Dodgers")):
                g["teams"][side]["team"] = {"id": tid, "name": name}
                g["teams"][side]["isWinner"] = side == winner_side
                g["teams"][side]["score"] = 4 if side == winner_side else 1
        for g in s["games"][need:]:
            for side, tid, name in (("away", 147, "New York Yankees"), ("home", 119, "Los Angeles Dodgers")):
                g["teams"][side]["team"] = {"id": tid, "name": name}
    return raw


def test_an_over_series_drops_its_unneeded_games_and_the_finished_bracket_reads_done():
    raw = load("postseason_series_2026-10-07.json")
    for s in raw["series"]:
        _finish(raw, s["series"]["id"])
    b = sc.build_bracket(raw, season=2026)
    ss = _series(b)
    assert all(s["over"] for s in ss.values()) and b["done"] is True
    w = ss["W_1"]
    assert w["text"] == "LAD wins 4-0" and w["winner_id"] == 119
    assert len(w["games"]) == 4 and all(g["state"] == "final" for g in w["games"])
    assert b["last"] == "2026-10-27"           # the unneeded games 5 to 7 are gone, and their dates


def test_placeholder_names_and_an_empty_payload():
    assert sc.placeholder_name("HOU/CWS") == "Winner of HOU and CWS"
    assert sc.placeholder_name("SD/CHC") == "Winner of SD and CHC"
    assert sc.placeholder_name("NL Lower Seed") == "NL Lower Seed"
    assert sc.placeholder_name(None) == "To be decided"
    assert sc.build_bracket({"series": []}, season=2026) is None
    assert sc.build_bracket(load("schedule_states.json"), season=2026) is None


def test_the_bracket_carries_no_probability_and_passes_the_validator():
    for name in ("postseason_series_2026.json", "postseason_series_2026-10-07.json"):
        b = sc.build_bracket(load(name), season=2026)
        text = sc.dumps(b)
        assert "%" not in text and "prob" not in text.lower() and "pct" not in text.lower(), name
        assert sc.find_forbidden_keys(b) == [] and sc.find_dashes(b) == [] and sc.find_urls(b) == [], name
        # a season index of a full season of dates plus the bracket stays inside its budget
        dates = [{"d": f"2026-{m:02d}-{d:02d}", "n": 15, "types": ["R"], "rev": "0123456789abcdef", "flags": []}
                 for m in range(3, 11) for d in range(1, 32)][:221]
        doc = {"schema": sc.SCHEMA, "season": 2026, "dates": dates, "bracket": b}
        res = sc.validate_payload("season_index", doc, name="index-2026.json")
        assert res["ok"] and res["logged"] == [], (name, res)
        assert res["bytes"] <= sc.FILE_KINDS["season_index"]["budget"], res["bytes"]

