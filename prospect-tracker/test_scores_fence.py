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
"""
from __future__ import annotations

import ast
import builtins
import json
import os
import re
import sys
from datetime import datetime, timezone
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
    assert not re.search(r"^\s*scores\s*$", (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8"), re.M)


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


def test_the_job_reads_the_served_board_nowhere_yet():
    # SCORES_6 adds the key-path allowlist; until then the job names no board file
    text = (ROOT / "tools" / "scores_job.py").read_text(encoding="utf-8")
    for s in ("betting.json", "betting_preview.json", "xfv.json", "management_board"):
        assert s not in text, s
