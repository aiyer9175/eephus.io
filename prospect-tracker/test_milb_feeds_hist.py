"""tools/fetch_milb_feeds_hist.py and tools/build_runner_moves.build_milb_hist: the
minor-league history units of the runner record (owner answer ETOOLS-SPD-EBR,
2026-10-21: 2021 and 2022 at every level, 2023 at High-A to Triple-A).

Fixture payloads and a fake session only: the fetcher's refusals, receipts, pacing,
resume, healing and nightly-window stop; the history build's refusal on an
incomplete unit, its unit scope, and the frozen units and source caches it must
leave byte-identical. Nothing here touches the network or the real caches.
"""
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import build_runner_moves as brm  # noqa: E402
import fetch_milb_feeds_hist as fmh  # noqa: E402
import fetch_win_prob_hist as fwh  # noqa: E402
import prune_cache  # noqa: E402
from test_runner_moves import _game  # noqa: E402

DAY = lambda: datetime(2026, 10, 22, 20, 0, tzinfo=timezone.utc)  # noqa: E731  outside the window


def _feed(pk, *, season=2021, sport=14, state="Final", plays=None, open_last=False):
    pl = plays if plays is not None else _game(year=season)
    for p in pl:
        p.pop("credits", None)
        p.setdefault("about", {})["isComplete"] = True
    if open_last:
        pl = pl + [{"result": {"type": "atBat", "event": "Game Advisory"},
                    "about": {"atBatIndex": len(pl), "halfInning": "top", "inning": 6,
                              "isComplete": False},
                    "count": {"balls": 0, "strikes": 0, "outs": 0},
                    "matchup": {"batter": {"id": 105}, "pitcher": {"id": 900}},
                    "playEvents": [], "runners": [], "atBatIndex": len(pl)}]
    return {"gameData": {"game": {"pk": pk, "type": "R", "season": str(season)},
                         "status": {"abstractGameState": state},
                         "teams": {"home": {"id": 2, "sport": {"id": sport}}, "away": {"id": 1}},
                         "venue": {"id": 5}},
            "liveData": {"plays": {"allPlays": pl}, "linescore": {"scheduledInnings": 9}}}


class _Resp:
    def __init__(self, status, body=b""):
        self.status_code = status
        self.content = body


def _session(answers, calls):
    class _S:
        def get(self, url, headers=None, timeout=None):
            pk = int(url.split("/game/")[1].split("/")[0])
            calls.append((pk, headers))
            a = answers[pk]
            if isinstance(a, Exception):
                raise a
            return a
    return _S()


def _b(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


def test_units_are_the_owner_named_seasons_and_the_fetcher_refuses_every_other_cache(tmp_path):
    assert set(fmh.HIST_UNITS) == ({(lv, s) for s in (2021, 2022)
                                    for lv in ("aaa", "aa", "high_a", "single_a", "rookie")}
                                   | {("aaa", 2023), ("aa", 2023), ("high_a", 2023)})
    assert len(fmh.HIST_UNITS) == 13
    assert fmh.HIST_SEASONS == brm.MILB_HIST_SEASONS == (2021, 2022, 2023)
    assert fmh.LEVEL_SPORT == {v: k for k, v in brm.MILB_LEVELS.items()}
    assert brm.DEFAULT_MILB_HIST.name == fmh.HIST_DIR.name == "milb_feeds_hist"
    assert brm.DEFAULT_MILB_HIST != brm.DEFAULT_FEEDS
    for bad in ("game_feeds", "pbp_runners", "win_prob", "win_prob_hist", "pbp_corpus"):
        with pytest.raises(RuntimeError):
            fmh.check_out_dir(tmp_path / bad)
        with pytest.raises(RuntimeError):
            fmh.check_out_dir(tmp_path / bad / "x")
    assert fmh.check_out_dir(tmp_path / "milb_feeds_hist") == tmp_path / "milb_feeds_hist"
    assert fmh.MIN_INTERVAL >= 0.5
    import pipeline_vintage
    assert fwh.house_user_agent() == pipeline_vintage.USER_AGENT
    assert "milb_feeds_hist" in prune_cache.EXCLUDED and "milb_feeds_hist" not in prune_cache.SAFE_CACHES


def test_fetcher_receipts_pacing_statuses_and_resume(tmp_path):
    out = tmp_path / "milb_feeds_hist"
    good = {pk: _b(_feed(pk)) for pk in (1, 4, 6, 7)}
    called_early = _b(_feed(5, open_last=True))
    live = _b(_feed(3, state="Live"))
    calls, sleeps = [], []
    answers = {1: _Resp(200, good[1]), 2: _Resp(404), 3: _Resp(200, live), 4: _Resp(200, good[4]),
               5: _Resp(200, called_early), 6: _Resp(500), 7: ConnectionError("boom")}
    sched = {"single_a|2021": [[pk, "2021-05-0%d" % pk] for pk in range(1, 8)]}
    clock = {"t": 0.0}
    pacer = fwh.Pacer(0.5, clock=lambda: clock["t"], sleep=lambda s: sleeps.append(s))
    summ = fmh.run([("single_a", 2021)], out_dir=out, session=_session(answers, calls), pacer=pacer,
                   user_agent="ua-test", schedules=sched, now=DAY)
    assert [c[0] for c in calls] == [1, 2, 3, 4, 5, 6, 7]
    assert all(c[1] == {"User-Agent": "ua-test"} for c in calls)
    assert sleeps == [0.5] * 6
    assert sorted(p.name for p in (out / "feeds").glob("*.json")) == ["1.json", "4.json", "5.json"]
    assert not list(out.glob("*.json.tmp")) and not list((out / "feeds").glob("*.tmp"))
    lines = [json.loads(x) for x in (out / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["game_pk"], r["status"]) for r in lines] == [
        (1, "ok"), (2, "no_play"), (3, "partial"), (4, "ok"), (5, "ok"), (6, "error"), (7, "error")]
    assert all(r["level"] == "single_a" and r["season"] == 2021 and r["date"] for r in lines)
    ok = {r["game_pk"]: r for r in lines if r["status"] == "ok"}
    assert ok[5]["sha256"] == hashlib.sha256(called_early).hexdigest()
    blk = summ["units"]["single_a|2021"]
    assert blk["fetched"] == 3 and blk["no_play"] == 1 and blk["partial"] == 1 and blk["error"] == 2
    assert blk["complete"] is False and summ["stopped"] is None
    assert fmh.unit_status(out, [("single_a", 2021)])["single_a|2021"]["complete"] is False
    # the second run asks only the games without an ok receipt; 404 stays answered
    (out / "schedule").mkdir(exist_ok=True)
    (out / "schedule" / "single_a_2021.json").write_text(json.dumps(sched["single_a|2021"]), encoding="utf-8")
    calls2 = []
    answers2 = {2: _Resp(404), 3: _Resp(200, _b(_feed(3))), 6: _Resp(200, good[6]), 7: _Resp(200, good[7])}
    summ2 = fmh.run([("single_a", 2021)], out_dir=out, session=_session(answers2, calls2), pacer=pacer,
                    user_agent="ua-test", now=DAY)
    assert [c[0] for c in calls2] == [2, 3, 6, 7]
    assert summ2["units"]["single_a|2021"]["present_before"] == 3
    assert summ2["units"]["single_a|2021"]["complete"] is True
    st = fmh.unit_status(out, [("single_a", 2021)])["single_a|2021"]
    assert st == {"scheduled": 7, "present": 6, "no_play": 1, "complete": True}


def test_fetcher_heals_receipts_and_refetches_an_altered_payload(tmp_path):
    out = tmp_path / "milb_feeds_hist"
    (out / "feeds").mkdir(parents=True)
    body = _b(_feed(1))
    (out / "feeds" / "1.json").write_bytes(b"\0" * len(body))           # zero-filled under an ok receipt
    (out / "feeds" / "2.json").write_bytes(_b(_feed(2)))                # on disk, no receipt
    good = json.dumps({"game_pk": 1, "status": "ok", "sha256": hashlib.sha256(body).hexdigest()})
    (out / "receipts.jsonl").write_bytes(good.encode() + b"\n" + b"\0" * 40 + b"\n{\"game_pk\": 9, \"sta")
    calls = []
    answers = {1: _Resp(200, body), 2: _Resp(200, _b(_feed(2)))}
    fmh.run([("aaa", 2021)], out_dir=out, session=_session(answers, calls),
            pacer=fwh.Pacer(0.5, sleep=lambda s: None), user_agent="u",
            schedules={"aaa|2021": [[1, "d"], [2, "d"]]}, now=DAY)
    assert [c[0] for c in calls] == [1, 2]
    assert (out / "feeds" / "1.json").read_bytes() == body
    assert len(list(out.glob("receipts.jsonl.damaged-*"))) == 1


def test_fetcher_stops_inside_the_nightly_window(tmp_path):
    out = tmp_path / "milb_feeds_hist"
    calls = []
    night = lambda: datetime(2026, 10, 23, 7, 30, tzinfo=timezone.utc)  # noqa: E731
    summ = fmh.run([("aaa", 2021)], out_dir=out, session=_session({}, calls),
                   pacer=fwh.Pacer(0.5, sleep=lambda s: None), user_agent="u",
                   schedules={"aaa|2021": [[1, "d"]]}, now=night)
    assert calls == [] and summ["stopped"] == "nightly fetch window"
    assert fmh.in_nightly_window(datetime(2026, 10, 23, 6, 0, tzinfo=timezone.utc))
    assert not fmh.in_nightly_window(datetime(2026, 10, 23, 11, 0, tzinfo=timezone.utc))
    assert not fmh.in_nightly_window(datetime(2026, 10, 23, 5, 59, tzinfo=timezone.utc))


def _hist_dir(tmp_path, games):
    """A finished fetch: payloads under feeds/, schedules and ok receipts."""
    hist = tmp_path / "milb_feeds_hist"
    (hist / "feeds").mkdir(parents=True)
    (hist / "schedule").mkdir()
    rec = []
    for unit, feeds in games.items():
        lv, s = unit
        (hist / "schedule" / f"{lv}_{s}.json").write_text(
            json.dumps([[pk, "2021-06-01"] for pk in feeds]), encoding="utf-8")
        for pk, feed in feeds.items():
            body = _b(feed)
            (hist / "feeds" / f"{pk}.json").write_bytes(body)
            rec.append(json.dumps({"game_pk": pk, "status": "ok", "sha256": hashlib.sha256(body).hexdigest()}))
    (hist / "receipts.jsonl").write_text("\n".join(rec) + "\n", encoding="utf-8")
    return hist


def _tree_hash(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(d)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def test_history_build_scopes_units_freezes_them_and_leaves_frozen_units_and_sources_alone(tmp_path):
    out = tmp_path / "pbp_runners"
    feeds = tmp_path / "game_feeds"
    feeds.mkdir()
    (feeds / "900.json").write_text(json.dumps(_feed(900, season=2023, sport=14)), encoding="utf-8")
    brm.build_milb(out_dir=out, feeds=feeds, workers=1, today=date(2026, 10, 22))
    frozen = dict(brm.load_manifest(out)["milb"]["single_a|2023"])
    assert frozen["frozen"]
    fz = [out / frozen["files"]["pa"], out / frozen["files"]["runners"]]
    before = [p.read_bytes() for p in fz] + [p.stat().st_mtime_ns for p in fz]
    games = {("single_a", 2021): {11: _feed(11, sport=14), 12: _feed(12, sport=14, open_last=True)},
             ("aaa", 2023): {21: _feed(21, season=2023, sport=11)}}
    hist = _hist_dir(tmp_path, games)
    # a stray 2023 Single-A payload in the history directory is outside every history unit
    (hist / "feeds" / "31.json").write_bytes(_b(_feed(31, season=2023, sport=14)))
    src_hash, hist_hash = _tree_hash(feeds), _tree_hash(hist)
    units = [("single_a", 2021), ("aaa", 2023)]
    man = brm.build_milb_hist(out_dir=out, hist_dir=hist, workers=1, today=date(2026, 10, 22), units=units)
    m = man["milb"]
    assert m["single_a|2021"]["games"] == 2 and m["single_a|2021"]["frozen"]
    assert m["single_a|2021"]["source"] == "milb_feeds_hist"
    assert m["aaa|2023"]["games"] == 1 and m["aaa|2023"]["frozen"]
    assert m["single_a|2023"] == frozen and "source" not in m["single_a|2023"]
    assert [p.read_bytes() for p in fz] + [p.stat().st_mtime_ns for p in fz] == before
    assert man["milb_hist"]["single_a|2021"] == {"scheduled": 2, "payloads": 2, "no_play": 0}
    assert man["milb_skipped"] == brm.load_manifest(out)["milb_skipped"]
    assert _tree_hash(feeds) == src_hash and _tree_hash(hist) == hist_hash
    # a second build changes nothing: every history unit is frozen
    snap = _tree_hash(out / "milb")
    brm.build_milb_hist(out_dir=out, hist_dir=hist, workers=1, today=date(2026, 10, 22), units=units)
    assert _tree_hash(out / "milb") == snap


def test_history_build_refuses_an_incomplete_unit_before_writing(tmp_path):
    hist = _hist_dir(tmp_path, {("aa", 2022): {41: _feed(41, season=2022, sport=12)}})
    sched = hist / "schedule" / "aa_2022.json"
    sched.write_text(json.dumps([[41, "d"], [42, "d"]]), encoding="utf-8")
    out = tmp_path / "pbp_runners"
    with pytest.raises(brm.MilbHistIncomplete):
        brm.build_milb_hist(out_dir=out, hist_dir=hist, workers=1, units=[("aa", 2022)])
    assert not out.exists()
    with pytest.raises(brm.MilbHistIncomplete):           # a unit never fetched
        brm.build_milb_hist(out_dir=out, hist_dir=hist, workers=1, units=[("aa", 2021)])


def test_a_cancelled_game_the_schedule_lists_as_final_is_no_play(tmp_path):
    out = tmp_path / "milb_feeds_hist"
    cancelled = _feed(8, plays=[])
    cancelled["gameData"]["status"]["detailedState"] = "Cancelled: Rain"
    calls = []
    summ = fmh.run([("aaa", 2021)], out_dir=out, session=_session({8: _Resp(200, _b(cancelled))}, calls),
                   pacer=fwh.Pacer(0.5, sleep=lambda s: None), user_agent="u",
                   schedules={"aaa|2021": [[8, "d"]]}, now=DAY)
    assert summ["units"]["aaa|2021"]["no_play"] == 1 and summ["units"]["aaa|2021"]["complete"] is True
    assert not (out / "feeds" / "8.json").exists()
    rec = json.loads((out / "receipts.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert rec["status"] == "no_play" and rec["reason"] == "Cancelled: Rain"
