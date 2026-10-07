# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SCORES_5b_LAUNCH_NAV_HEALTH: the nightly's `scores_job` health row, the nav
leaf and the sitemap row for /scores/.

The health row (SCORES_PLAN 2.5, pipeline_ops.md 1.11): step 9e-post-scores of
run_monthly.run_daily reads the job's store and never imports the job; it files
`_record_ingest("scores_job", ok, n, message)` only on a machine meant to run
the job (EEPHUS_SCORES_HOST=1, or a heartbeat on disk), and it writes nothing
else. The four states on fixture stores, with the two amendments of 2.5: a
refusal counts only when the same file stays refused 6 hours or more, and
per-game fetch failures count apart from job-level fetch_failed.

Hermetic: every store is a tmp_path, the clock is a fixed UTC instant, the
record function is a list; nothing here touches the network, the repo's data/
or a real .cache/scores/.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import build_site
import run_monthly as rm

ROOT = Path(__file__).resolve().parent
UTC = timezone.utc
NOW = datetime(2026, 10, 7, 18, 0, 0, tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store(tmp_path: Path, *, heartbeat_age_min: float | None = 2.0, runs=(), games=(),
           refused=None, slate=True) -> Path:
    """A fixture store in the job's own layout (tools/scores_job.resolve_paths)."""
    st = tmp_path / "store"
    st.mkdir(parents=True, exist_ok=True)
    if heartbeat_age_min is not None:
        (st / "heartbeat.json").write_text(json.dumps({
            "last_run_utc": _iso(NOW - timedelta(minutes=heartbeat_age_min)),
            "action": "idle", "state": "idle", "reason": "fixture", "exit": 0, "requests": 0,
            "counts": None, "out": str(tmp_path / "out"), "last_publish": None,
            "scores_live": True}), encoding="utf-8")
    by_date: dict[str, list[str]] = {}
    for r in runs:
        at = r["at"]
        rec = {"at": _iso(at), "action": r.get("action", "live"), "exit": r.get("exit", 0),
               "requests": 3, "counts": r.get("counts"), "reason": r.get("reason", "fixture")}
        by_date.setdefault(at.date().isoformat(), []).append(json.dumps(rec))
    for d, lines in by_date.items():
        (st / f"runlog-{d}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if slate:
        (st / "slate.json").write_text(json.dumps({
            "fetched_at": _iso(NOW - timedelta(hours=1)), "span": ["2026-10-06", "2026-10-14"],
            "games": [{"pk": 900000 + i, "date": g.date().isoformat(), "start": _iso(g),
                       "state": "final"} for i, g in enumerate(games)]}), encoding="utf-8")
    if refused is not None:
        (st / "state.json").write_text(json.dumps({"refused_files": refused}), encoding="utf-8")
    return st


def _run(store: Path, env=None):
    calls = []
    out = rm._scores_job_health(store=store, env=env if env is not None else {}, now=NOW,
                                record=lambda *a, **k: calls.append((a, k)))
    return out, calls


def _runs(n, *, start_h=23, **kw):
    """n run-log lines spread over the last `start_h` hours."""
    step = timedelta(hours=start_h) / max(n, 1)
    return [{"at": NOW - timedelta(hours=start_h) + step * i, **kw} for i in range(n)]


# --------------------------------------------------------------------------- #
# The watch list and the reader
# --------------------------------------------------------------------------- #
def test_scores_job_is_watched_as_an_export():
    assert "scores_job" in rm.SCHEDULED_EXPORTS
    assert rm._ingest_kind("scores_job") == "export"


def test_the_pipeline_reads_the_store_and_never_imports_the_job():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    imp = re.compile(r"^\s*(?:import|from)\s+[\w.]*scores_job\b|import_module\([^)]*scores_job"
                     r"|__import__\([^)]*scores_job", re.MULTILINE)
    assert imp.search(src) is None, "run_monthly must read the job's store, never import the job"
    assert '/ ".cache" / "scores"' in src and '"heartbeat.json"' in src
    assert "EEPHUS_SCORES_STORE" in src


def test_the_step_sits_after_9e_and_before_9g_with_a_unique_name():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i9e = src.index('_step("9e. Betting odds snapshot')
    istep = src.index('_step("9e-post-scores. Scores / Standings job health (read-only)"')
    i9g = src.index('_step("9g. eFV scoreboard refresh')
    assert i9e < istep < i9g
    assert src.count('_step("9e-post-scores.') == 1
    run_daily = src[src.index("def run_daily("):]
    assert '_step("9e-post-scores.' in run_daily


def test_the_store_resolves_like_the_job(monkeypatch, tmp_path):
    monkeypatch.setenv("EEPHUS_SCORES_STORE", str(tmp_path / "s"))
    assert rm._scores_store() == tmp_path / "s"
    monkeypatch.delenv("EEPHUS_SCORES_STORE")
    assert rm._scores_store() == ROOT / ".cache" / "scores"


# --------------------------------------------------------------------------- #
# Host only
# --------------------------------------------------------------------------- #
def test_no_row_without_the_host_flag_or_a_heartbeat(tmp_path):
    st = _store(tmp_path, heartbeat_age_min=None, runs=_runs(5), games=[NOW - timedelta(hours=3)])
    out, calls = _run(st, env={})
    assert out is None and calls == []
    out, calls = _run(st, env={"EEPHUS_SCORES_HOST": "0"})
    assert out is None and calls == []


def test_the_host_flag_alone_files_the_never_run_red(tmp_path):
    st = _store(tmp_path, heartbeat_age_min=None, slate=False)
    (ok, n, msg), calls = _run(st, env={"EEPHUS_SCORES_HOST": "1"})
    assert ok is False and n == 0
    assert msg.startswith("!!! SCORES RED: the Scores / Standings job (tools/scores_job.py) has never run")
    assert "--selfcheck" in msg
    assert len(calls) == 1 and calls[0][0][:2] == ("scores_job", False)


def test_a_heartbeat_alone_makes_a_host(tmp_path):
    st = _store(tmp_path, runs=_runs(4, counts={"files_written": 2}), games=[])
    (ok, n, msg), calls = _run(st, env={})
    assert ok is True and len(calls) == 1


# --------------------------------------------------------------------------- #
# The four states
# --------------------------------------------------------------------------- #
def test_a_stopped_job_on_a_game_day_is_red(tmp_path):
    st = _store(tmp_path, heartbeat_age_min=61, games=[NOW - timedelta(hours=5)])
    (ok, _n, msg), _ = _run(st)
    assert ok is False and "stopped at 2026-10-07T16:59:00Z" in msg and "1 game(s)" in msg


def test_a_heartbeat_under_an_hour_is_not_stopped(tmp_path):
    st = _store(tmp_path, heartbeat_age_min=59, games=[NOW - timedelta(hours=5)])
    (ok, _n, _msg), _ = _run(st)
    assert ok is True


def test_an_idle_offseason_reads_healthy_even_with_an_old_heartbeat(tmp_path):
    st = _store(tmp_path, heartbeat_age_min=60 * 30, games=[NOW - timedelta(days=3)])
    (ok, n, msg), _ = _run(st)
    assert ok is True and n == 0
    assert msg.startswith("Scores / Standings job: 0 file(s) written in 24 h over 0 game(s)")


def test_an_unreadable_slate_with_a_stale_heartbeat_is_red(tmp_path):
    st = _store(tmp_path, heartbeat_age_min=120, slate=False)
    (ok, _n, msg), _ = _run(st)
    assert ok is False and "an unreadable schedule" in msg


def test_fetch_failed_over_ten_percent_is_red_and_ten_percent_is_not(tmp_path):
    runs = _runs(20, counts={"files_written": 1})
    for r in runs[:3]:
        r["action"], r["reason"] = "fetch_failed", "schedule: HTTP 503"
    (ok, _n, msg), _ = _run(_store(tmp_path / "a", runs=runs, games=[NOW - timedelta(hours=2)]))
    assert ok is False and "running but failing: 3 of 20 run(s) fetch_failed" in msg
    assert "last reason: schedule: HTTP 503" in msg
    runs[2]["action"] = "live"
    (ok, _n, _msg), _ = _run(_store(tmp_path / "b", runs=runs, games=[NOW - timedelta(hours=2)]))
    assert ok is True


def test_any_publish_failed_is_red(tmp_path):
    runs = _runs(30)
    runs[-1]["action"] = "publish_failed"
    (ok, _n, msg), _ = _run(_store(tmp_path, runs=runs))
    assert ok is False and "1 publish_failed" in msg


def test_a_refusal_counts_only_after_six_hours_on_the_same_file(tmp_path):
    five = {"2026-10-07.json": {"n": 40, "since": _iso(NOW - timedelta(hours=5)),
                                "last": _iso(NOW - timedelta(minutes=2)), "rule": "3: stars"}}
    (ok, _n, msg), _ = _run(_store(tmp_path / "a", runs=_runs(10), refused=five))
    assert ok is True and "1 file(s) refused under 6 h" in msg
    six = {"2026-10-07.json": {"n": 70, "since": _iso(NOW - timedelta(hours=6, minutes=2)),
                               "last": _iso(NOW - timedelta(minutes=2)), "rule": "3: stars"}}
    (ok, _n, msg), _ = _run(_store(tmp_path / "b", runs=_runs(10), refused=six))
    assert ok is False and "1 file(s) refused 6 h or more (2026-10-07.json)" in msg
    # a refusal that ended more than 24 hours ago is history, not a red
    old = {"2026-09-30.json": {"n": 90, "since": _iso(NOW - timedelta(days=4)),
                               "last": _iso(NOW - timedelta(days=2)), "rule": "6: budget"}}
    (ok, _n, _msg), _ = _run(_store(tmp_path / "c", runs=_runs(10), refused=old))
    assert ok is True


def test_per_game_failures_count_apart_and_never_redden_the_row(tmp_path):
    runs = _runs(10, counts={"files_written": 3, "game_fetch_failed": 2})
    (ok, n, msg), _ = _run(_store(tmp_path, runs=runs, games=[NOW - timedelta(hours=4)] * 2))
    assert ok is True and n == 30
    assert "0 fetch_failed, 20 per-game fetch failure(s)" in msg


def test_the_healthy_message_counts_the_last_24_hours_only(tmp_path):
    runs = _runs(6, counts={"files_written": 5}) + [
        {"at": NOW - timedelta(hours=30), "action": "fetch_failed", "counts": {"files_written": 99}}]
    (ok, n, msg), calls = _run(_store(tmp_path, runs=runs,
                                      games=[NOW - timedelta(hours=3), NOW - timedelta(hours=26)]))
    assert ok is True and n == 30
    assert msg.startswith("Scores / Standings job: 30 file(s) written in 24 h over 1 game(s); 6 run(s)")
    assert calls[0][0] == ("scores_job", True, 30, msg)


def test_a_crash_inside_the_read_files_a_red_on_a_host(tmp_path, monkeypatch):
    st = _store(tmp_path, runs=_runs(3))
    monkeypatch.setattr(rm, "_scores_read_json", lambda p: 1 / 0)
    (ok, n, msg), calls = _run(st)
    assert ok is False and n == 0 and "health read crashed" in msg and len(calls) == 1


def test_the_health_read_writes_nothing(tmp_path):
    runs = _runs(12, counts={"files_written": 1})
    runs[0]["action"] = "fetch_failed"
    st = _store(tmp_path, runs=runs, games=[NOW - timedelta(hours=2)],
                refused={"latest.json": {"n": 1, "since": _iso(NOW), "last": _iso(NOW)}})
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()}
    _run(st)
    _run(st, env={"EEPHUS_SCORES_HOST": "1"})
    after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after


def test_messages_carry_no_dash_the_copy_rules_ban():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    start = src.index("THE SCORES / STANDINGS JOB'S HEALTH ROW")
    body = src[start:src.index("THE NIGHTLY-GAP SENTINEL (2026-08-19)", start)]
    assert "def _scores_job_health(" in body
    assert "—" not in body and "–" not in body


# --------------------------------------------------------------------------- #
# Nav, icon and sitemap (SC-NAV: second in MLB Modules, after Franchises)
# --------------------------------------------------------------------------- #
def test_the_nav_leaf_sits_directly_after_franchises():
    group = next(it for it in build_site.NAV_ITEMS if isinstance(it, dict) and it["key"] == "mlb")
    assert group["children"][0][0] == "franchise"
    assert group["children"][1] == ("scores", "Scores / Standings", "/scores/")
    assert [k for k, _l, _h in build_site.nav_leaves()].count("scores") == 1


def test_the_nav_and_rail_draw_the_scores_icon():
    assert build_site.ICON_FOR["scores"] == "scores" and "scores" in build_site.ICON_KEYS
    icons = json.loads((ROOT / "assets" / "eephus-icons.json").read_text(encoding="utf-8"))
    assert icons["scores"]["label"] == "Scores / Standings"
    nav = build_site._nav("scores")
    assert re.search(r'<a href="/scores/" role="menuitem" class="is-active"><svg class="ico"[^>]*>'
                     r'<use href="/assets/eephus-icons\.svg\?v=[0-9a-f]+#i-scores"', nav)


@pytest.mark.parametrize("rel", ["prospx/index.html", "collegesavant/index.html",
                                 "collegesavant/pitcher_index.html"])
def test_the_hand_kept_navs_carry_the_leaf_in_the_same_slot(rel):
    html = (ROOT / rel).read_text(encoding="utf-8")
    nav = re.search(r'<nav\s+class="eephus-links">(.*?)</nav>', html, re.DOTALL).group(1)
    hrefs = re.findall(r'<a href="([^"]+)" role="menuitem"', nav)
    assert hrefs[:2] == ["/franchise/", "/scores/"]
    assert re.search(r'<a href="/scores/" role="menuitem"><svg[^>]*><use href="[^"]*#i-scores"[^>]*/></svg>'
                     r'Scores / Standings</a>', nav)


def test_the_sitemap_lists_scores_hourly_once():
    xml = build_site.build_sitemap([])
    rows = re.findall(r"<url><loc>https://eephus\.io/scores/</loc><lastmod>[^<]+</lastmod>"
                      r"<changefreq>([a-z]+)</changefreq><priority>([0-9.]+)</priority></url>", xml)
    assert rows == [("hourly", "0.8")]
