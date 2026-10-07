# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The MLB Scores fences (SCORES_PLAN 9; SCORES_2_JOB_AND_DEPLOY).

On the syntax tree and on a recorded run: no scores module imports a pricer, a
dark module or the lineup job, and no pricer imports a scores module; the
stores the plan names are never read; the house getters are never called; the
only fetch host is statsapi.mlb.com; every write lands under the job's store or
its OUT and never under data/, .cache/win_prob, .cache/win_prob_post or
.cache/game_feeds; neither deploy consumer names /data/scores. Hermetic: the
recorded run uses test_scores_job's fake StatsAPI and temp directories.

SCORES_6 (the pregame block): the job reads the served Sports Betting board
through a key-path allowlist pinned here and recorded key by key; every copied
value is byte-equal to the board's; a Preview card alone carries the block,
and it is gone once the game leaves Preview; a stale board copies no model
number; the served Diamond gate switches the read to the preview slice; no
forbidden key, no key containing dv or decision, rides in a pre block; the
management read touches no decision key; data/xfv.json is parsed only when its
mtime moves.
"""
from __future__ import annotations

import ast
import builtins
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import scores_job as job  # noqa: E402
from test_scores_job import (FakeAPI, FakeClock, NOW, _game, base_games, base_payloads, env,  # noqa: E402,F401
                             load, run_once, schedule_of, seed_state)

SCORES_FILES = (ROOT / "scores_core.py", ROOT / "tools" / "scores_job.py")
PRICERS = ("betting_model", "betting_export", "betting_ingest", "betting_credits", "betting_shadow",
           "betting_settle", "betting_learning", "betting_usage", "betting_weather", "betting_props_dark",
           "leaderboard_vintages")
DARK_PREFIXES = ("mgmt_", "management", "betting_dugout", "betting_lineup_job", "betting_")
HOUSE = ("feed_cache", "mlb_leverage", "requests")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
    return out


@pytest.mark.parametrize("path", SCORES_FILES, ids=lambda p: p.name)
def test_no_scores_module_imports_a_pricer_a_dark_module_the_lineup_job_or_the_house_getters(path):
    imported = _imports(path)
    for name in imported:
        assert name not in PRICERS, (path.name, name)
        assert not name.startswith(DARK_PREFIXES), (path.name, name)
        assert name not in HOUSE, (path.name, name)


def test_no_pricer_imports_a_scores_module():
    pricers = [ROOT / f"{n}.py" for n in PRICERS if (ROOT / f"{n}.py").exists()]
    pricers += sorted((ROOT / "tools").glob("betting_*.py"))
    assert (ROOT / "betting_model.py") in pricers
    for p in pricers:
        names = _imports(p)
        assert not {"scores_core", "scores_job"} & names, p.name


def test_no_module_outside_the_tests_imports_the_job():
    pat = re.compile(r"^\s*(?:import\s+scores_job|from\s+scores_job\s+import|from\s+tools(?:\.scores_job)?\s+import"
                     r"\s+scores_job)|import_module\(\s*['\"](?:tools\.)?scores_job['\"]", re.M)
    offenders = []
    for p in list(ROOT.glob("*.py")) + list((ROOT / "tools").glob("*.py")):
        if p.name.startswith("test_") or p.name in ("scores_job.py", "conftest.py"):
            continue
        if pat.search(p.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(p.name)
    assert offenders == []


def _code_only(path: Path) -> str:
    """The module's code with comments and docstrings removed, so naming a
    store in prose (the docstrings say at length what the job stays away from)
    is not confused with reaching it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


@pytest.mark.parametrize("path", SCORES_FILES, ids=lambda p: p.name)
def test_the_named_stores_are_never_read_and_the_house_getters_never_called(path):
    text = _code_only(path)
    for s in ("lineup_captures", "weather_forecasts", "leaderboard_vintages", "completed_games", "win_prob_post",
              "the-odds-api", "odds_api", "eephus-nightly", "nightly.lock", "prospects.db"):
        assert s not in text, (path.name, s)
    assert not re.search(r"\.cache[/\\]+(odds|betting)\b", text), path.name
    assert not re.search(r"\"\.cache\"\s*/\s*\"(odds|betting)\"", text), path.name
    tree = ast.parse(text)
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | \
            {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "get_game_feed" not in names and "get_win_probability" not in names
    assert "atomic_write_json" not in names and "SESSION" not in names


def test_the_only_host_in_the_job_is_statsapi():
    text = (ROOT / "tools" / "scores_job.py").read_text(encoding="utf-8")
    assert job.HOST == "statsapi.mlb.com"
    hosts = set(re.findall(r"https?://([A-Za-z0-9.-]+)", text))
    # the User-Agent names our own page; the docstring names nothing else
    assert hosts <= {"eephus.io"}, hosts
    assert "f\"https://{HOST}" in text


def test_neither_deploy_consumer_names_data_scores():
    for name in ("publish_paths.txt", "data_exclude.txt", "nightly-build.sh"):
        text = (ROOT / "deploy" / name).read_text(encoding="utf-8")
        assert "/data/scores" not in text and "data/scores" not in text, name
    # the page ships from the flip (SCORES_5a); its data never ships from the app tree
    assert re.search(r"^\s*scores\s*$", (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8"), re.M)


def test_a_recorded_run_fetches_statsapi_only_and_writes_only_its_own_store(env, monkeypatch):
    writes = []
    real_open, real_os_open, real_replace = builtins.open, os.open, os.replace

    def spy_open(file, mode="r", *a, **k):
        if any(c in str(mode) for c in "wax+"):
            writes.append(Path(file))
        return real_open(file, mode, *a, **k)

    def spy_os_open(path, flags, *a, **k):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            writes.append(Path(path))
        return real_os_open(path, flags, *a, **k)

    def spy_replace(src, dst, *a, **k):
        writes.append(Path(dst))
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(os, "open", spy_os_open)
    monkeypatch.setattr(os, "replace", spy_replace)
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    assert run_once(env, api, clock)["exit"] == 0
    # a backfill too, with house caches present: read, never written
    cache = env["tmp"] / "house" / "win_prob"
    feeds = env["tmp"] / "house" / "game_feeds"
    cache.mkdir(parents=True)
    feeds.mkdir(parents=True)
    real_open(cache / "849845.json", "w", encoding="utf-8").close()
    writes.clear()
    api2 = FakeAPI(clock, schedule_of(_game(849845, "F")), **base_payloads())
    res = job.backfill("2026-09-29", "2026-09-29", paths=env["paths"],
                       now_fn=lambda: datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc), adapter=api2,
                       clock=clock, sleep=clock.sleep)
    assert res["exit"] == 0, res
    assert writes
    store = env["paths"]["store"]
    for p in writes:
        assert job._inside(p, store), p
        assert not job._inside(p, ROOT / "data") and not job._inside(p, ROOT / ".cache"), p
        assert not job._inside(p, env["tmp"] / "house"), p
    for u, _t in api.calls + api2.calls:
        assert u.startswith("https://statsapi.mlb.com/api/"), u
        # SCORES_4a reads /game/{pk}/content on statsapi; a media, poster or
        # frame URL is stored for the page and never requested by the job
        for media in ("mlb-cuts-diamond", "bdata-producedclips", "img.mlbstatic", "streamable", "mlb.com/video"):
            assert media not in u, u


def _payload_strings(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _payload_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _payload_strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def test_media_and_embed_urls_live_only_inside_clip_objects(env):
    """SCORES_4a: on a recorded run with content reads, every media, poster,
    frame or MLB.com video URL in any written payload sits inside a game file's
    clip object (the one gameday link and index.json's copyright line apart),
    and no highBit, trickplay or portrait rendition appears anywhere."""
    from test_scores_clips import pickoff_item
    import copy as _copy
    clock = FakeClock()
    content = _copy.deepcopy(load("content_849845.json"))
    content["highlights"]["highlights"]["items"].append(pickoff_item())
    api = FakeAPI(clock, schedule_of(*base_games()), content={849845: content,
                                                              849846: load("content_849846_live.json")},
                  **base_payloads())
    seed_state(env, week_date="2026-09-30")
    assert run_once(env, api, clock)["exit"] == 0
    media = re.compile(r"mlb-cuts-diamond|bdata-producedclips|img\.mlbstatic|streamable\.com|mlb\.com/video|"
                       r"\.mp4|\.m3u8|\.vtt", re.I)
    seen = 0
    for p in env["out"].rglob("*.json"):
        doc = json.loads(p.read_text(encoding="utf-8"))
        rel = p.relative_to(env["out"]).as_posix()
        for path, s in _payload_strings(doc):
            for bad in ("highbit", "trickplay", "portrait", "16000k"):
                assert bad not in s.lower(), (rel, path)
            if not media.search(s):
                continue
            if rel == "index.json" and path.startswith("rules.video."):
                assert "/" not in s, (rel, path, s)            # bare host names, never a URL
                continue
            assert rel.startswith("games/") and path.startswith("clips."), (rel, path, s)
            seen += 1
    assert seen > 40, seen


# --------------------------------------------------------------------------- #
# SCORES_6: the pregame block
# --------------------------------------------------------------------------- #
import copy  # noqa: E402

import scores_core as sc  # noqa: E402
from test_scores_render import EFV_ID, pregame_payloads, pregame_served, regular_season_game  # noqa: E402

ALLOW_ROW = ("game_pk", "model.p_home", "model.p_away", "home.probable.mlbam", "away.probable.mlbam")
ALLOW_FILE = ("generated_at", "slate_date", "model.version", "status.model", "status.model_registry_verdict",
              "status.model_verdict_sentence", "status.stale_board")
#: 23:08Z on the fixture date: well after NOW (21:40Z), so the game is Preview.
PRE_START = "2026-09-30T23:08:00Z"


class Rec(dict):
    """A dict that records every key read through it, with its dotted path."""

    def __init__(self, data, path, log):
        super().__init__()
        self._p, self._log = path, log
        for k, v in data.items():
            dict.__setitem__(self, k, _rec(v, f"{path}.{k}" if path else k, log))

    def get(self, k, default=None):
        self._log.add(f"{self._p}.{k}" if self._p else k)
        return dict.get(self, k, default)

    def __getitem__(self, k):
        self._log.add(f"{self._p}.{k}" if self._p else k)
        return dict.__getitem__(self, k)


def _rec(v, path, log):
    if isinstance(v, dict):
        return Rec(v, path, log)
    if isinstance(v, list):
        return [_rec(x, f"{path}[]", log) for x in v]
    return v


def _prefixes(paths):
    out = set()
    for p in paths:
        parts = p.split(".")
        out.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    return out


def test_the_board_allowlist_is_pinned_and_no_other_key_is_read():
    assert sc.BOARD_ROW_PATHS == ALLOW_ROW and sc.BOARD_FILE_PATHS == ALLOW_FILE
    assert sc.BOARD_ROW_LISTS == ("team_bets", "games")
    board = load_board()
    log: set = set()
    ext = sc.board_extract(Rec(board, "", log))
    allowed = _prefixes(ALLOW_FILE) | set(sc.BOARD_ROW_LISTS)
    for lst in sc.BOARD_ROW_LISTS:
        allowed |= {f"{lst}[].{p}" for p in _prefixes(ALLOW_ROW)}
    assert log and log <= allowed, sorted(log - allowed)
    for decoy in ("moneyline", "market", "pick_of_the_day", "record", "slot_lock", "dugout_context", "odds_captured_at",
                  "odds_kind", "odds_slate", "lam_home", "fair_total", "coefficients"):
        assert not any(decoy in k for k in log), decoy
    # every value byte-equal to the board's
    row = board["team_bets"][0]
    got = ext["rows"][row["game_pk"]]
    assert json.dumps(got["model.p_home"]) == json.dumps(row["model"]["p_home"])
    assert json.dumps(got["model.p_away"]) == json.dumps(row["model"]["p_away"])
    assert ext["file"]["status.model_verdict_sentence"] == board["status"]["model_verdict_sentence"]


def load_board():
    return load("betting_board.json")


def _serve(ev, served: dict, *, gating: bool | None = None) -> None:
    for name, doc in served.items():
        (ev["web"] / "data" / name).write_text(json.dumps(doc), encoding="utf-8")
    reg = json.loads((ev["web"] / "data" / "model_registry.json").read_text(encoding="utf-8"))
    have = {m["model_id"] for m in reg["models"]}
    for mid, verdict in (("betting_game_prob", "provisional"), ("sem_plus", "validated"), ("efv_v2", "provisional"),
                         ("mgmt_board_export", "provisional")):
        if mid not in have:
            reg["models"].append({"model_id": mid, "verdict": verdict})
    (ev["web"] / "data" / "model_registry.json").write_text(json.dumps(reg), encoding="utf-8")
    if gating is not None:
        (ev["web"] / "assets").mkdir(exist_ok=True)
        (ev["web"] / "assets" / "diamond-config.js").write_text(
            "// the served gate\nwindow.EEPHUS_DIAMOND = { gating: %s, price_usd_month: 15 };\n"
            % ("true" if gating else "false"), encoding="utf-8")


def _pregame_games(status=None):
    g = regular_season_game(900010, PRE_START)
    if status:
        g["status"] = status
    return [_game(849845, "F"), _game(849846, "I"), g]


def _date_cards(ev, d="2026-09-30"):
    doc = json.loads((ev["out"] / f"{d}.json").read_text(encoding="utf-8"))
    return {c["pk"]: c for c in doc["games"]}, doc


def test_a_recorded_run_copies_the_board_byte_for_byte_onto_the_preview_card_only(env):
    served = pregame_served()
    _serve(env, served)
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*_pregame_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    assert run_once(env, api, clock)["exit"] == 0
    cards, doc = _date_cards(env)
    assert sc.validate_payload("date", doc, name="2026-09-30.json")["ok"]
    pre = cards[900010]["pre"]
    board = served["betting.json"]
    row = next(r for r in board["team_bets"] if r["game_pk"] == 900010)
    for k in ("p_home", "p_away"):
        assert json.dumps(pre["model"][k]) == json.dumps(row["model"][k]), k
    for k, src in (("sentence", "model_verdict_sentence"), ("state", "model"), ("verdict", "model_registry_verdict")):
        assert pre["model"][k] == board["status"][src], k
    assert (pre["model"]["version"], pre["model"]["board_at"], pre["model"]["slate_date"]) == (
        board["model"]["version"], board["generated_at"], board["slate_date"])
    assert pre["model"]["stale_board"] is False and pre["model"]["board"] == "full"
    # the other copies, each equal to its served value
    assert pre["home"]["sem_plus"] == served["starter_leaderboards.json"]["starters"][0]["sem_plus"]
    assert pre["home"]["hook_median_pitches"] == 87.5 and pre["park_runs"] == 102
    assert pre["efv"] == {str(EFV_ID): 51.5}
    # no live or final card carries a pre block, and the index labels the model with the board's state
    assert "pre" not in cards[849846]
    assert all("pre" not in c for c in _date_cards(env, "2026-09-29")[0].values())
    gf = json.loads((env["out"] / "games" / "849846.json").read_text(encoding="utf-8"))
    assert "pre" not in gf["card"]
    idx = json.loads((env["out"] / "index.json").read_text(encoding="utf-8"))
    sentences = {r["model_id"]: r["sentence"] for r in idx["registry"]}
    assert sentences["betting_game_prob"] == "Eephus model, unvalidated, provisional"
    assert sentences["sem_plus"] == "MLB Stats SEM+, validated"
    assert sentences["efv_v2"] == "PROSPX eFV, provisional"
    assert sentences["mgmt_board_export"] == "In-Game Management, provisional"
    # the game starts: the next cycle rebuilds the card without the block
    live = {"abstractGameState": "Live", "codedGameState": "I", "detailedState": "In Progress", "statusCode": "I"}
    api2 = FakeAPI(clock, schedule_of(*_pregame_games(status=live)), **base_payloads())
    assert run_once(env, api2, clock, now=NOW + timedelta(seconds=240))["exit"] == 0
    cards2, _doc = _date_cards(env)
    assert "pre" not in cards2[900010]


def test_a_stale_board_copies_no_model_number(env):
    served = pregame_served()
    served["betting.json"]["status"]["stale_board"] = True
    _serve(env, served)
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*_pregame_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    assert run_once(env, api, clock)["exit"] == 0
    cards, _doc = _date_cards(env)
    assert "model" not in cards[900010].get("pre", {})
    # and a starter the board did not price, a postseason game, another slate
    ext = sc.board_extract(load_board())
    g = regular_season_game(900010, PRE_START)
    assert sc.pre_model(g, ext)["p_home"] == 0.53012
    g2 = copy.deepcopy(g)
    g2["teams"]["home"]["probablePitcher"] = {"id": 1, "fullName": "Someone Else"}
    assert sc.pre_model(g2, ext) == {"absent": "starter"}
    g3 = copy.deepcopy(g)
    g3["teams"]["away"].pop("probablePitcher")
    assert sc.pre_model(g3, ext) == {"absent": "starter"}            # null equals null only
    g4 = dict(g, gameType="F")
    assert sc.pre_model(g4, ext) == {"absent": "season"}
    assert sc.pre_model(dict(g, officialDate="2026-10-01"), ext) is None
    assert sc.pre_model(dict(g, gamePk=1), ext) is None


@pytest.mark.parametrize("gating", [False, True])
def test_the_served_diamond_gate_switches_the_read_to_the_preview_slice(env, monkeypatch, gating):
    served = pregame_served()
    full = served["betting.json"]
    preview = copy.deepcopy(full)
    preview["team_bets"] = preview["team_bets"][:1]
    served["betting_preview.json"] = preview
    _serve(env, served, gating=gating)
    reads = []
    real = job.read_served
    monkeypatch.setattr(job, "read_served", lambda name: (reads.append(name), real(name))[1])
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*_pregame_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    assert run_once(env, api, clock)["exit"] == 0
    cards, _doc = _date_cards(env)
    want, other = ("betting_preview.json", "betting.json") if gating else ("betting.json", "betting_preview.json")
    assert want in reads and other not in reads
    assert cards[900010]["pre"]["model"]["board"] == ("preview" if gating else "full")


def test_the_validator_refuses_a_pre_block_off_preview_or_off_its_allowlist():
    p = pregame_payloads()
    doc = p["2026-09-30.json"]
    assert sc.validate_payload("date", doc, name="2026-09-30.json")["ok"]
    for c in doc["games"]:
        assert sc.find_forbidden_keys(c.get("pre") or {}) == []
        for path, key, _v in sc._walk(c.get("pre") or {}):
            assert key is None or ("dv" not in str(key).lower() and "decision" not in str(key).lower()), path
    bad = pregame_payloads(inject_live=True)["2026-09-30.json"]
    res = sc.validate_payload("date", bad, name="2026-09-30.json")
    assert not res["ok"] and any(r == "12" for r, _m in res["refused"]), res["refused"]
    extra = copy.deepcopy(doc)
    card = next(c for c in extra["games"] if c["pk"] == 900010)
    card["pre"]["model"]["moneyline_fair"] = 0.5
    assert any(r == "12" for r, _m in sc.validate_payload("date", extra, name="2026-09-30.json")["refused"])
    stale = copy.deepcopy(doc)
    card = next(c for c in stale["games"] if c["pk"] == 900010)
    card["pre"]["model"]["stale_board"] = True
    assert any(r == "12" for r, _m in sc.validate_payload("date", stale, name="2026-09-30.json")["refused"])


def test_the_management_read_touches_no_decision_key():
    log: set = set()
    hooks = sc.hook_map(Rec(pregame_served()["management_board.json"], "", log))
    assert hooks[("ATL", 2026)] == 87.5 and ("PHI", 2025) in hooks
    assert log <= {"clubs", "clubs.games_floor", "clubs.rows", "clubs.rows[].hook_median_pitches", "clubs.rows[].games",
                   "clubs.rows[].club", "clubs.rows[].season"}, log
    assert not any("dv" in k or "decision" in k for k in log)


def test_xfv_is_parsed_only_when_its_mtime_moves(env, monkeypatch):
    _serve(env, pregame_served())
    reads = []
    real = job.read_served
    monkeypatch.setattr(job, "read_served", lambda name: (reads.append(name), real(name))[1])
    state: dict = {}
    assert job.efv_map_cached(state) == {str(EFV_ID): 51.5}
    assert job.efv_map_cached(state) == {str(EFV_ID): 51.5}
    assert reads.count("xfv.json") == 1 and reads.count("player_links.json") == 1
    path = env["web"] / "data" / "xfv.json"
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 60))
    assert job.efv_map_cached(state) == {str(EFV_ID): 51.5}
    assert reads.count("xfv.json") == 2
    # the map rides in state.json between invocations
    assert json.loads(json.dumps(state))["xfv"]["map"] == {str(EFV_ID): 51.5}


def test_the_job_names_no_board_key_outside_the_allowlist():
    text = _code_only(ROOT / "tools" / "scores_job.py")
    for s in ("moneyline", "market_fair_prob", "pick_of_the_day", "odds_captured_at", "odds_slate", "runline",
              "slot_lock", "dugout_context", "park_factors_by_hand", "consensus_fv"):
        assert s not in text, s
    assert text.count("betting.json") == 1 and text.count("betting_preview.json") == 1
