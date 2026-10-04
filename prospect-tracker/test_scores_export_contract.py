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
              "bracket": None}
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
            "sit", "wp", "of_record", "star", "top_play", "videos", "flags", "weather", "makeup", "resume", "updated_at",
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
    assert set(latest) == {"schema", "generated_at", "job", "index_rev", "today", "next_game_date", "window", "live"}
    assert set(latest["job"]) == {"action", "state", "next_by", "last_ok_at", "down_after_s", "poll_live_s",
                                  "poll_idle_s", "errors_24h", "refusals_24h"}
    assert set(latest["window"]) == {f"2026-{d}" for d in ("09-29", "09-30", "10-01", "10-02", "10-03", "10-04",
                                                           "10-05", "10-06", "10-07")}
    assert set(next(iter(latest["window"].values()))) == {"rev", "n", "live", "final", "pre", "off", "clips_matched",
                                                          "clips_of", "stale_since"}
    assert set(index) == {"schema", "generated_at", "seasons", "registry", "accuracy", "rules", "copyright"}
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
