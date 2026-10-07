# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""assets/scores.js executed in V8 (the engine test_data_cache_stamps.py
drives), with no DOM: the pure stale rule and the loader's fetch rules.

scoresStaleState(latest, serverNowMs, viewedDate) (plan 2.4): the rows are
evaluated S4, S3, S2, S0, S1, S1 is the default, the sentences are exact,
"Updates paused" carries no "Live" when nothing on the viewed date is live,
and the clock is the latest.json response's Date header, so a skewed client
clock cannot fake freshness. S2 hides the live-only fields on a card.

The loader (plan 2.3): every scores request carries cache "no-cache";
index.json is fetched once and again only when index_rev moves; a date file
is requested as <file>?v=<rev> and only when its rev moves; the day view
never asks for the player link corpus.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
SRC = (ROOT / "assets" / "scores.js").read_text(encoding="utf-8")

_STUB = r"""
var document = { readyState: "complete", getElementById: function () { return null; },
  addEventListener: function () {} };
var window = { addEventListener: function () {} };
var location = { hash: "" };
function SyncP(v, e) { this.v = v; this.e = e; this.failed = arguments.length > 1; }
SyncP.prototype.then = function (ok, bad) {
  if (this.failed) return bad ? _c(bad, this.e) : this;
  return ok ? _c(ok, this.v) : this;
};
SyncP.prototype.catch = function (bad) { return this.then(null, bad); };
function _c(fn, a) { try { var r = fn(a); return (r instanceof SyncP) ? r : new SyncP(r); }
  catch (err) { return new SyncP(undefined, err); } }
var Promise = { resolve: function (v) { return new SyncP(v); } };
var __fetches = [], __files = {}, __date = null;
function fakeFetch(url, opts) {
  __fetches.push({ url: url, opts: opts === undefined ? null : opts });
  var path = url.split("?")[0].replace("/data/scores/", "");
  var body = __files[path];
  return new SyncP({ ok: body !== undefined, status: body === undefined ? 404 : 200,
    headers: { get: function (k) { return k === "Date" ? __date : null; } },
    json: function () { return new SyncP(JSON.parse(JSON.stringify(body))); } });
}
"""

T0 = 1790000000000            # a fixed instant (2026-09-21T13:33:20Z)
MIN = 60_000


def iso(ms: int) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(scope="module")
def v8():
    mr = pytest.importorskip("py_mini_racer")
    ctx = mr.MiniRacer()
    ctx.eval(_STUB)
    ctx.eval(SRC)
    return ctx


def call(ctx, expr):
    return json.loads(ctx.eval(f"JSON.stringify({expr})"))


def latest(**job):
    j = {"action": "live", "state": "ok", "next_by": iso(T0 + 10 * MIN), "last_ok_at": iso(T0 - MIN),
         "down_after_s": 1800, "poll_live_s": 45, "poll_idle_s": 300, "errors_24h": 0, "refusals_24h": 0}
    j.update(job)
    return {"schema": 1, "generated_at": job.pop("generated_at", iso(T0 - MIN)), "job": j, "index_rev": "ix1",
            "today": "2026-09-21", "next_game_date": None,
            "window": {"2026-09-21": {"rev": "d1", "n": 2, "live": 1, "final": 1, "pre": 0, "off": 0},
                       "2026-09-20": {"rev": "d0", "n": 1, "live": 0, "final": 1, "pre": 0, "off": 0}},
            "live": [{"pk": 1, "date": "2026-09-21"}]}


def stale(ctx, L, now, date="2026-09-21"):
    return call(ctx, f"window.EephusScores.scoresStaleState({json.dumps(L)}, {now}, {json.dumps(date)})")


def clock(ctx, ms):
    return call(ctx, f"window.EephusScores.clock({ms})")


def test_s4_when_latest_is_missing_or_fails_its_schema(v8):
    for bad in (None, {}, {"schema": 2}, {"schema": 1, "generated_at": "x", "job": {}, "today": "2026-09-21"}):
        s = stale(v8, bad, T0)
        assert s["code"] == "S4" and s["sentence"] == "Scores are not available right now.", bad


def test_s3_after_36_hours_wins_over_every_later_row(v8):
    L = latest(state="degraded", generated_at=iso(T0 - 37 * 3600_000), last_ok_at=iso(T0 - 37 * 3600_000))
    L["generated_at"] = iso(T0 - 37 * 3600_000)
    s = stale(v8, L, T0)
    month_day = call(v8, f"window.EephusScores.monthDay({T0 - 37 * 3600_000})")
    assert s["code"] == "S3"
    assert s["sentence"] == f"Scores were last updated {month_day}. They may be out of date."


def test_s2_only_when_a_game_on_the_viewed_date_was_live(v8):
    t_ok = T0 - 31 * MIN
    L = latest(last_ok_at=iso(t_ok), next_by=iso(T0 + MIN))
    s = stale(v8, L, T0)
    assert s["code"] == "S2"
    assert s["sentence"] == f"Live scores are not updating. Showing the last update, from {clock(v8, t_ok)}."
    # the same job state, viewing a date with nothing live: no S2
    s = stale(v8, L, T0, "2026-09-20")
    assert s["code"] == "S0"


def test_s0_normal_and_s1_default_row(v8):
    L = latest()
    s = stale(v8, L, T0)
    assert s["code"] == "S0" and s["sentence"] == f"Updated {clock(v8, T0 - MIN)}"
    # past next_by: S1, worded by whether the viewed date has a live game
    s = stale(v8, L, T0 + 11 * MIN)
    assert s["code"] == "S1" and s["sentence"] == f"Live updates paused. Scores as of {clock(v8, T0 - MIN)}."
    s = stale(v8, L, T0 + 11 * MIN, "2026-09-20")
    assert s["code"] == "S1" and s["sentence"] == f"Updates paused. Scores as of {clock(v8, T0 - MIN)}."
    assert "Live" not in s["sentence"]
    # degraded or backoff inside next_by is S1 too
    for st in ("degraded", "backoff"):
        assert stale(v8, latest(state=st), T0)["code"] == "S1"
    assert stale(v8, latest(state="idle"), T0)["code"] == "S0"


def test_the_date_header_overrides_a_skewed_client_clock(v8):
    """The loader reads the Date header of latest.json; a client clock three
    hours fast must not push a fresh scoreboard into S2."""
    L = latest()
    v8.eval(f"__files = {{'latest.json': {json.dumps(L)}, 'index.json': {{'seasons': []}}}};"
            f"__date = new Date({T0}).toUTCString(); __fetches = [];"
            f"var __skew = {T0 + 3 * 3600_000};"
            "var __L = window.EephusScores.makeLoader(fakeFetch, function () { return __skew; });"
            "__L.latest();")
    s = call(v8, "window.EephusScores.scoresStaleState(__L.state.latest, __L.serverNow(), '2026-09-21')")
    assert s["code"] == "S0", s
    s = call(v8, "window.EephusScores.scoresStaleState(__L.state.latest, __skew, '2026-09-21')")
    assert s["code"] == "S2", "without the header the skewed clock reads the scores as down; the header holds S0"


def test_every_fetch_is_no_cache_and_revs_gate_the_files(v8):
    L = latest()
    v8.eval(f"__files = {{'latest.json': {json.dumps(L)}, 'index.json': {{'seasons': [{{'season': 2026, 'rev': 's1'}}]}},"
            f"'2026-09-21.json': {{'games': []}}, 'index-2026.json': {{'dates': [{{'d': '2026-09-01', 'rev': 'dx'}}]}},"
            f"'2026-09-01.json': {{'games': []}}}};"
            "__date = null; __fetches = [];"
            "var __M = window.EephusScores.makeLoader(fakeFetch, function () { return 0; });"
            "__M.latest(); __M.date('2026-09-21'); __M.latest(); __M.date('2026-09-21');")
    f = call(v8, "__fetches")
    assert all(x["opts"] == {"cache": "no-cache"} for x in f), f
    urls = [x["url"] for x in f]
    assert urls == ["/data/scores/latest.json", "/data/scores/index.json?v=ix1", "/data/scores/2026-09-21.json?v=d1",
                    "/data/scores/latest.json"], urls
    # index_rev moves: the index is fetched again; a date rev moves: that file is fetched again
    L2 = latest()
    L2["index_rev"] = "ix2"
    L2["window"]["2026-09-21"]["rev"] = "d2"
    v8.eval(f"__files['latest.json'] = {json.dumps(L2)}; __fetches = []; __M.latest(); __M.date('2026-09-21');"
            "__M.date('2026-09-01');")
    urls = [x["url"] for x in call(v8, "__fetches")]
    assert urls == ["/data/scores/latest.json", "/data/scores/index.json?v=ix2", "/data/scores/2026-09-21.json?v=d2",
                    "/data/scores/index-2026.json?v=s1", "/data/scores/2026-09-01.json?v=dx"], urls
    assert not any("player_links" in u for u in urls)


def test_s2_hides_the_live_only_fields_on_a_card(v8):
    card = {"pk": 1, "state": "live", "away": {"code": "PHI", "short": "Phillies", "r": 3},
            "home": {"code": "ATL", "short": "Braves", "r": 2}, "line": [[0, 1]],
            "sit": {"inning": 7, "half": "top", "outs": 1, "balls": 2, "strikes": 1, "bases": [True, False, False],
                    "batter": {"id": 2, "name": "Bryce Harper"}, "pitcher": {"id": 3, "name": "Chris Sale", "pitches": 88},
                    "last_text": "Turner single."}, "wp": {"home": 620, "ab": 50}}
    ix = {"registry": [{"model_id": "scores_mlb_wp", "verdict": "provisional", "sentence": "MLB, provisional"}]}
    normal = call(v8, f"window.EephusScores.cardHTML({json.dumps(card)}, {json.dumps(ix)}, {{code: 'S0'}}, false)")
    assert "Count 2-1" in normal and "MLB win probability: ATL 62%" in normal and "Harper" in normal
    s2 = call(v8, f"window.EephusScores.cardHTML({json.dumps(card)}, {json.dumps(ix)}, {{code: 'S2'}}, false)")
    assert "Last update: Top 7, PHI 3, ATL 2" in s2
    for hidden in ("Count", "win probability", "Harper", "sc-bases"):
        assert hidden not in s2, hidden
    # a missing registry row draws no number
    bare = call(v8, f"window.EephusScores.cardHTML({json.dumps(card)}, {{registry: []}}, {{code: 'S0'}}, false)")
    assert "%" not in bare


def test_routes_validate_every_value(v8):
    r = call(v8, "window.EephusScores.parseRoute('#game=849845&tab=box&play=65')")
    assert r["view"] == "game" and r["game"] == 849845 and r["tab"] == "box" and r["play"] == 65
    r = call(v8, "window.EephusScores.parseRoute('#date=2026-13-45&f=bogus&lg=XL&game=abc&tab=<x>')")
    assert r["view"] == "day" and r["date"] is None and r["f"] == "all" and r["lg"] is None
    assert call(v8, "window.EephusScores.parseRoute('#about')")["view"] == "about"
