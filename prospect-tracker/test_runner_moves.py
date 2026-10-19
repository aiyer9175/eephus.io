"""tools/build_runner_moves.py: the eBR runner record (docs/ebr-2026-09-30/EBR_GATE.md part 2.2).

Fixture payloads only (baserunning.md 4.5's eight plays, plus the EBR_2A extras): rows
as expected, steals keyed on movementReason, the plate appearance's own state walk,
the postseason skip, the incremental and frozen rules, the re-fetch directory, the
history directory (2011 to 2017 and 2020, read for those seasons only; EBR-Q4 (b)),
its fetcher's receipts, pacing and refusals, and the caches the record must never
write. Nothing here reads the real winProbability cache beyond listing it, and
nothing touches the network.
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import build_runner_moves as brm  # noqa: E402
import prune_cache  # noqa: E402

HERE = Path(__file__).resolve().parent
A, B, C, D, E = 101, 102, 103, 104, 105      # runner / batter ids
AFTER_FREEZE = date(2024, 11, 2)


# ---------------------------------------------------------------------------
# synthetic payload builders
# ---------------------------------------------------------------------------
def _pitch(idx, *, in_play=False, balls=0, strikes=0, hit=None, defense=None):
    ev = {"index": idx, "isPitch": True, "type": "pitch",
          "details": {"isInPlay": in_play, "call": {"code": "X" if in_play else "S"}},
          "count": {"balls": balls, "strikes": strikes}}
    if hit is not None:
        ev["hitData"] = hit
    if defense is not None:
        ev["defense"] = defense
    return ev


def _action(idx, event_type, *, player=None, base=None, sub=False, replaced=None, code=None):
    ev = {"index": idx, "isPitch": False, "type": "action",
          "details": {"eventType": event_type}}
    if player is not None:
        ev["player"] = {"id": player}
    if base is not None:
        ev["base"] = base
    if sub:
        ev["isSubstitution"] = True
    if replaced is not None:
        ev["replacedPlayer"] = {"id": replaced}
    if code is not None:
        ev["position"] = {"code": code}
    return ev


def _entry(rid, start, end, pi, *, reason=None, event_type=None, is_out=False,
           origin="same", out_base=None, credits=()):
    return {"movement": {"originBase": (start if origin == "same" else origin), "start": start,
                         "end": (None if is_out else end), "outBase": out_base,
                         "isOut": is_out, "outNumber": None},
            "details": {"runner": {"id": rid}, "playIndex": pi, "movementReason": reason,
                        "eventType": event_type, "isScoringEvent": end == "score" and not is_out},
            "credits": [{"player": {"id": pid}, "position": {"code": pos}, "credit": cr}
                        for pid, pos, cr in credits]}


def _play(abi, batter, events, runners, *, outs, event_type, inning=1, half="top",
          away=0, home=0, pa=True, year=2024):
    return {"result": {"type": "atBat", "eventType": event_type, "awayScore": away,
                       "homeScore": home},
            "about": {"atBatIndex": abi, "halfInning": half, "inning": inning,
                      "startTime": f"{year}-06-01T18:00:00Z"},
            "count": {"balls": 0, "strikes": 0, "outs": outs},
            "matchup": {"batter": {"id": batter}, "pitcher": {"id": 900}},
            "playEvents": events, "runners": runners,
            "credits": ([{"player": {"id": batter}, "credit": "b_pa"}] if pa else []),
            "atBatIndex": abi}


def _single(abi, batter, *, outs=0, extra=(), loc="8", inning=1, half="top", away=0, home=0):
    return _play(abi, batter, [_pitch(0, in_play=True,
                                      hit={"trajectory": "line_drive", "location": loc,
                                           "coordinates": {"coordX": 130.0, "coordY": 100.0}},
                                      defense={"left": {"id": 7}, "center": {"id": 8},
                                               "right": {"id": 9}})],
                 [_entry(batter, None, "1B", 0, event_type="single")] + list(extra),
                 outs=outs, event_type="single", inning=inning, half=half, away=away, home=home)


def _rows(plays, season=2024):
    diag = {}
    pa, rn = brm.walk_game(plays, game_pk=1, season=season,
                           info={"away_id": 10, "home_id": 20, "venue_id": 30,
                                 "scheduled_innings": 9}, diag=diag)
    return pa, rn, diag


def _of(rn, rid, reason=None):
    return [r for r in rn if r["runner_id"] == rid and (reason is None or r["movement_reason"] == reason)]


# ---------------------------------------------------------------------------
# baserunning.md 4.5's fixture plays
# ---------------------------------------------------------------------------
def test_single_man_on_first_to_third():
    plays = [_single(0, A),
             _single(1, B, extra=[_entry(A, "1B", "3B", 0, reason="r_adv_play", event_type="single")])]
    pa, rn, _ = _rows(plays)
    row = _of(rn, A, "r_adv_play")[0]
    assert (row["start"], row["end"], row["is_out"]) == ("1B", "3B", False)
    assert row["base_before_group"] == 1 and row["base_after_group"] == 5
    assert pa[1]["fp_on_first"] == A and pa[1]["end_on_third"] == A and pa[1]["end_on_first"] == B
    assert pa[1]["bat_team_id"] == 10 and pa[1]["venue_id"] == 30 and pa[1]["hit_location"] == "8"
    assert pa[1]["of_center_id"] == 8


def test_strikeout_with_a_steal_on_the_pitch():
    k = _play(1, C, [_pitch(0), _pitch(1), _pitch(2)],
              [_entry(C, None, None, 2, event_type="strikeout", is_out=True, origin=None),
               _entry(A, "1B", "2B", 2, reason="r_stolen_base_2b", event_type="stolen_base_2b")],
              outs=1, event_type="strikeout")
    pa, rn, _ = _rows([_single(0, A), k])
    st = _of(rn, A, "r_stolen_base_2b")[0]
    assert st["is_final_pitch_group"] and st["play_index"] == 2
    assert st["base_before_group"] == 1 and st["base_after_group"] == 2
    assert st["outs_before_group"] == 0 and st["outs_after_group"] == 1
    assert pa[1]["fp_on_first"] == A and pa[1]["fp_outs"] == 0
    assert brm.record_counts(_df(pa), _df(rn))[A]["sb"] == 1


def test_strikeout_double_play():
    k = _play(1, C, [_pitch(0), _pitch(1)],
              [_entry(C, None, None, 1, event_type="strikeout_double_play", is_out=True, origin=None),
               _entry(A, "1B", None, 1, reason="r_caught_stealing_2b", is_out=True,
                      event_type="strikeout_double_play", out_base="2B")],
              outs=2, event_type="strikeout_double_play")
    pa, rn, diag = _rows([_single(0, A), k])
    assert pa[1]["end_outs"] == 2 and pa[1]["end_on_first"] is None
    assert brm.record_counts(_df(pa), _df(rn))[A]["cs"] == 1
    assert not diag.get("pa_outs_walk_mismatch")


def test_double_steal():
    p2 = _single(1, B, extra=[_entry(A, "1B", "2B", 0, reason="r_adv_force", event_type="single")])
    ds = _play(2, C, [_pitch(0), _action(1, "stolen_base_3b"), _pitch(2, in_play=True,
                                                                     hit={"trajectory": "fly_ball", "location": "9"})],
               [_entry(A, "2B", "3B", 1, reason="r_stolen_base_3b", event_type="stolen_base_3b"),
                _entry(B, "1B", "2B", 1, reason="r_stolen_base_2b", event_type="stolen_base_2b"),
                _entry(C, None, None, 2, event_type="field_out", is_out=True, origin=None)],
               outs=1, event_type="field_out")
    pa, rn, _ = _rows([_single(0, A), p2, ds])
    g = [r for r in rn if r["at_bat_index"] == 2 and r["play_index"] == 1]
    assert {r["runner_id"] for r in g} == {A, B}
    assert all(r["base_before_group"] == 3 and r["base_after_group"] == 6 for r in g)
    cnt = brm.record_counts(_df(pa), _df(rn))
    assert cnt[A]["sb"] == 1 and cnt[B]["sb"] == 1
    states = json.loads(pa[2]["states_json"])
    assert states[0][:5] == [1, B, A, None, 0] and states[0][5:9] == [None, B, A, 0]
    assert pa[2]["fp_on_second"] == B and pa[2]["fp_on_third"] == A


def test_caught_stealing_for_the_third_out():
    cs = _play(1, C, [_pitch(0), _action(1, "caught_stealing_2b")],
               [_entry(A, "1B", None, 1, reason="r_caught_stealing_2b", is_out=True,
                       event_type="caught_stealing_2b", out_base="2B")],
               outs=3, event_type="caught_stealing_2b", pa=False)
    pa, rn, _ = _rows([_single(0, A, outs=2), cs])
    row = _of(rn, A, "r_caught_stealing_2b")[0]
    assert row["outs_before_group"] == 2 and row["outs_after_group"] == 3
    assert pa[1]["is_pa"] is False and pa[1]["end_outs"] == 3


def test_pickoff():
    pk = _play(1, C, [_action(0, "pickoff_1b"), _pitch(1)],
               [_entry(A, "1B", None, 0, reason="r_pickoff_1b", is_out=True,
                       event_type="pickoff_1b", out_base="1B")],
               outs=1, event_type="pickoff_1b", pa=False)
    pa, rn, _ = _rows([_single(0, A), pk])
    row = _of(rn, A, "r_pickoff_1b")[0]
    assert row["is_out"] and row["base_before_group"] == 1 and row["base_after_group"] == 0
    c = brm.record_counts(_df(pa), _df(rn))
    assert c[A]["cs"] == 0 and c[A]["sb"] == 0


def test_batter_out_stretching():
    p = _play(0, A, [_pitch(0, in_play=True, hit={"trajectory": "line_drive", "location": "7"})],
              [_entry(A, None, "1B", 0, event_type="single", origin=None),
               _entry(A, "1B", None, 0, reason="r_out_stretching", is_out=True, event_type="single",
                      out_base="2B")],
              outs=1, event_type="single")
    pa, rn, _ = _rows([p])
    assert len(_of(rn, A)) == 2
    assert pa[0]["end_on_first"] is None and pa[0]["end_outs"] == 1


def test_batter_takes_second_on_the_throw_home():
    p2 = _play(1, B, [_pitch(0, in_play=True, hit={"trajectory": "line_drive", "location": "8"})],
               [_entry(B, None, "1B", 0, event_type="single", origin=None),
                _entry(A, "2B", "score", 0, reason="r_adv_play", event_type="single"),
                _entry(B, "1B", "2B", 0, reason="r_adv_throw", event_type="single")],
               outs=0, event_type="single", away=1)
    p1 = _play(0, A, [_pitch(0, in_play=True, hit={"trajectory": "line_drive", "location": "9"})],
               [_entry(A, None, "2B", 0, event_type="double", origin=None)], outs=0, event_type="double")
    pa, rn, _ = _rows([p1, p2])
    assert pa[1]["runs_fp"] == 1 and pa[1]["end_on_second"] == B and pa[1]["end_on_first"] is None


# ---------------------------------------------------------------------------
# the EBR_2A extras
# ---------------------------------------------------------------------------
def test_safe_runner_under_a_caught_stealing_event_type_is_not_a_cs():
    p = _play(1, C, [_pitch(0), _action(1, "caught_stealing_2b"), _pitch(2)],
              [_entry(A, "1B", "2B", 1, reason="r_adv_play", event_type="caught_stealing_2b")],
              outs=0, event_type="walk")
    pa, rn, _ = _rows([_single(0, A), p])
    c = brm.record_counts(_df(pa), _df(rn))
    assert c[A]["cs"] == 0 and c[A]["sb"] == 0
    assert not brm.is_caught_stealing("r_adv_play")
    assert brm.is_caught_stealing("r_pickoff_caught_stealing_2b")


def test_mid_pa_pinch_runner_takes_the_bag():
    p = _play(1, C, [_pitch(0), _action(1, "offensive_substitution", player=E, base=1, sub=True,
                                                 replaced=A, code="12"), _pitch(2)],
              [_entry(E, "1B", "2B", 2, reason="r_stolen_base_2b", event_type="stolen_base_2b")],
              outs=0, event_type="walk")
    pa, rn, _ = _rows([_single(0, A), p])
    states = json.loads(pa[1]["states_json"])
    assert states[-1][1] == E and states[-1][6] == E


# ---------------------------------------------------------------------------
# I/O: schedule, receipts, postseason skip, incremental, frozen, re-fetch
# ---------------------------------------------------------------------------
def _df(rows):
    import pandas as pd
    return pd.DataFrame(rows)


def _game(year=2024):
    return [_single(0, A, ), _single(1, B, extra=[_entry(A, "1B", "3B", 0, reason="r_adv_play",
                                                         event_type="single")]),
            _play(2, C, [_pitch(0), _action(1, "stolen_base_2b"), _pitch(2)],
                  [_entry(B, "1B", "2B", 1, reason="r_stolen_base_2b", event_type="stolen_base_2b"),
                   _entry(C, None, None, 2, event_type="strikeout", is_out=True, origin=None)],
                  outs=1, event_type="strikeout", year=year)]


def _write_payloads(src: Path, games: dict):
    src.mkdir(parents=True, exist_ok=True)
    for pk, plays in games.items():
        (src / f"{pk}.json").write_text(json.dumps(plays), encoding="utf-8")


def _official(path: Path, lines: dict):
    splits = [{"player": {"id": pid}, "stat": {"stolenBases": c.get("sb", 0),
                                                "caughtStealing": c.get("cs", 0),
                                                "groundIntoDoublePlay": c.get("gidp", 0),
                                                "plateAppearances": c.get("pa", 0)}}
              for pid, c in lines.items()]
    path.write_text(json.dumps({"stats": [{"splits": splits}]}), encoding="utf-8")
    return path


def _sched(pks):
    return [[pk, "2024-06-01", 10, 20, 30, 9, "F"] for pk in pks]


def _hash_dir(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(d).rglob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture
def setup(tmp_path):
    src = tmp_path / "win_prob"
    _write_payloads(src, {11: _game(), 12: _game(), 99: _game()})   # 99: not on the schedule
    off = _official(tmp_path / "lines.json", {A: {"pa": 2}, B: {"sb": 2, "pa": 2}, C: {"pa": 2}})
    return tmp_path, src, off


def test_postseason_payload_skipped_and_receipts(setup):
    tmp, src, off = setup
    out = tmp / "pbp_runners"
    blk = brm.build_season(2024, out_dir=out, source=src, schedule=_sched([11, 12]), workers=1,
                           today=AFTER_FREEZE, official_path=off, allow_refetch=False)
    assert blk["games_present"] == 2 and blk["other_cached_payloads_skipped"] == 1
    pa = brm.read_table(out / blk["files"]["pa"])
    assert set(pa["game_pk"]) == {11, 12}
    rc = blk["receipts"]
    assert rc["I1"]["pass"] and rc["I2"]["pass"] and rc["I3"]["pass"]
    assert rc["I1"]["sb"] == [2, 2] and rc["statsapi_lines"]["sha256"]
    assert blk["frozen"]


def test_incremental_adds_nothing_twice(setup):
    tmp, src, off = setup
    out = tmp / "pbp_runners"
    today = date(2024, 9, 1)                   # live season: not frozen
    b1 = brm.build_season(2024, out_dir=out, source=src, schedule=_sched([11]), workers=1,
                          today=today, official_path=off, allow_refetch=False)
    assert not b1["frozen"] and b1["rows"]["pa"] == 3
    b2 = brm.build_season(2024, out_dir=out, source=src, schedule=_sched([11]), workers=1,
                          today=today, official_path=off, allow_refetch=False)
    assert b2["games_added_this_run"] == 0 and b2["rows"] == b1["rows"]
    assert b2["pa_sha256"] == b1["pa_sha256"]
    b3 = brm.build_season(2024, out_dir=out, source=src, schedule=_sched([11, 12]), workers=1,
                          today=today, official_path=off, allow_refetch=False)
    assert b3["games_added_this_run"] == 1 and b3["rows"]["pa"] == 6
    full = tmp / "full"
    b4 = brm.build_season(2024, out_dir=full, source=src, schedule=_sched([11, 12]), workers=1,
                          today=today, official_path=off, allow_refetch=False)
    assert b4["pa_sha256"] == b3["pa_sha256"] and b4["runners_sha256"] == b3["runners_sha256"]


def test_frozen_season_is_byte_identical_and_guarded(setup):
    tmp, src, off = setup
    out = tmp / "pbp_runners"
    man = brm.build([2024], out_dir=out, source=src, workers=1, today=AFTER_FREEZE,
                    schedules={2024: _sched([11, 12])}, official_paths={2024: off},
                    allow_refetch=False)
    blk = man["seasons"]["2024"]
    assert blk["frozen"]
    pa_p = out / blk["files"]["pa"]
    before = pa_p.read_bytes()
    mtime = pa_p.stat().st_mtime_ns
    _write_payloads(src, {13: _game()})
    man2 = brm.build([2024], out_dir=out, source=src, workers=1, today=AFTER_FREEZE,
                     schedules={2024: _sched([11, 12, 13])}, official_paths={2024: off},
                     allow_refetch=False)
    assert man2["seasons"]["2024"]["pa_sha256"] == blk["pa_sha256"]
    assert pa_p.read_bytes() == before and pa_p.stat().st_mtime_ns == mtime
    pa_p.write_bytes(before + b"x")
    with pytest.raises(brm.FrozenSeasonChanged):
        brm.build([2024], out_dir=out, source=src, workers=1, today=AFTER_FREEZE,
                  schedules={2024: _sched([11, 12])}, official_paths={2024: off})


def test_refetch_writes_only_the_refetch_directory(setup):
    tmp, src, off = setup
    out = tmp / "pbp_runners"
    bad = _official(tmp / "bad.json", {A: {"pa": 2}, B: {"sb": 3, "pa": 2}, C: {"pa": 2}})
    src_hash = _hash_dir(src)
    calls = []

    def fetcher(pk):
        calls.append(pk)
        return json.dumps(_game()).encode("utf-8")
    blk = brm.build_season(2024, out_dir=out, source=src, schedule=_sched([11, 12]), workers=1,
                           today=AFTER_FREEZE, official_path=bad, fetcher=fetcher)
    assert sorted(calls) == [11, 12]
    assert sorted(p.name for p in (out / "refetch").iterdir()) == ["11.json", "12.json"]
    assert blk["refetched_games"] == [11, 12]
    assert blk["receipts"]["I1"]["pass"] is False            # the miss survives: the season blocks
    assert _hash_dir(src) == src_hash


def test_missing_scheduled_game_is_filled_into_refetch_and_cancelled_games_close_i3(setup):
    tmp, src, off = setup
    out = tmp / "pbp_runners"
    sched = _sched([11, 12, 14]) + [[15, "2024-09-29", 10, 20, 30, 9, "C"]]
    blk = brm.build_season(2024, out_dir=out, source=src, schedule=sorted(sched), workers=1,
                           today=AFTER_FREEZE, official_path=tmp / "none.json",
                           fetcher=lambda pk: json.dumps(_game()).encode("utf-8"))
    assert blk["filled_games"] == [14] and (out / "refetch" / "14.json").exists()
    assert not (src / "14.json").exists()
    assert blk["receipts"]["I3"]["pass"] and blk["receipts"]["I3"]["cancelled_no_play"] == [15]


def test_build_leaves_the_corpus_and_win_prob_untouched(setup):
    tmp, src, off = setup
    corpus = HERE / ".cache" / "pbp_corpus"
    wp = HERE / ".cache" / "win_prob"

    def listing(d):
        if not d.exists():
            return None
        return sorted((e.name, e.stat().st_size, e.stat().st_mtime_ns) for e in d.iterdir())
    before = (listing(corpus), _hash_dir(corpus / "plays") if (corpus / "plays").exists() else None,
              (corpus / "manifest.json").read_bytes() if (corpus / "manifest.json").exists() else None,
              len(listing(wp) or ()))
    brm.build([2024], out_dir=tmp / "pbp_runners", source=src, workers=1, today=AFTER_FREEZE,
              schedules={2024: _sched([11, 12])}, official_paths={2024: off}, allow_refetch=False)
    after = (listing(corpus), _hash_dir(corpus / "plays") if (corpus / "plays").exists() else None,
             (corpus / "manifest.json").read_bytes() if (corpus / "manifest.json").exists() else None,
             len(listing(wp) or ()))
    assert before == after
    assert brm.DEFAULT_OUT.name == "pbp_runners" and brm.DEFAULT_OUT != corpus
    src_text = (HERE / "tools" / "build_runner_moves.py").read_text(encoding="utf-8")
    assert "pbp_corpus\" /" not in src_text and "CACHE_DIR" not in src_text


def test_pbp_runners_is_excluded_from_the_pruner():
    assert "pbp_runners" in prune_cache.EXCLUDED
    assert "pbp_runners" not in prune_cache.SAFE_CACHES
    assert "pbp_corpus" in prune_cache.EXCLUDED


def test_milb_copy_from_a_feed(tmp_path):
    feeds = tmp_path / "game_feeds"
    feeds.mkdir()
    plays = _game(year=2025)
    for pl in plays:
        pl.pop("credits", None)                 # /feed/live plays carry no play credits
    feed = {"gameData": {"game": {"pk": 777, "type": "R", "season": "2025"},
                         "status": {"abstractGameState": "Final"},
                         "teams": {"home": {"id": 2, "sport": {"id": 14}}, "away": {"id": 1}},
                         "venue": {"id": 5}},
            "liveData": {"plays": {"allPlays": plays}, "linescore": {"scheduledInnings": 9}}}
    (feeds / "777.json").write_text(json.dumps(feed), encoding="utf-8")
    spring = dict(feed, gameData=dict(feed["gameData"], game={"pk": 778, "type": "S", "season": "2025"}))
    (feeds / "778.json").write_text(json.dumps(spring), encoding="utf-8")
    m = brm.build_milb(out_dir=tmp_path / "pbp_runners", feeds=feeds, workers=1,
                       today=date(2025, 11, 2))
    blk = m["single_a|2025"]
    assert blk["games"] == 1 and blk["counts"]["sb"] == 1 and blk["counts"]["pa"] == 3
    assert blk["frozen"] and (tmp_path / "pbp_runners" / blk["files"]["runners"]).exists()


# ---------------------------------------------------------------------------
# EBR_Q4B: the history directory (2011 to 2017 and 2020) and its fetcher
# ---------------------------------------------------------------------------
import fetch_win_prob_hist as fwh  # noqa: E402


def _hist_setup(tmp_path):
    src = tmp_path / "win_prob"
    hist = tmp_path / "win_prob_hist"
    _write_payloads(src, {11: _game(), 12: _game(), 23: _game(year=2011)})
    _write_payloads(hist, {21: _game(year=2011), 22: _game(year=2011), 13: _game(),
                           31: _game(year=2020), 32: _game(year=2020)})
    off = _official(tmp_path / "lines.json", {A: {"pa": 2}, B: {"sb": 2, "pa": 2}, C: {"pa": 2}})
    return src, hist, off


def test_source_for_season_names_the_history_directory_for_its_seasons_only():
    assert brm.HIST_SEASONS == (2011, 2012, 2013, 2014, 2015, 2016, 2017, 2020)
    assert brm.DEFAULT_HIST_SOURCE.name == "win_prob_hist"
    assert brm.DEFAULT_HIST_SOURCE != brm.DEFAULT_SOURCE
    for s in brm.HIST_SEASONS:
        assert brm.source_for_season(s, Path("a"), Path("h")) == Path("h")
    for s in brm.DEFAULT_SEASONS:
        assert brm.source_for_season(s, Path("a"), Path("h")) == Path("a")
    assert not (set(brm.HIST_SEASONS) & set(brm.DEFAULT_SEASONS))


def test_history_directory_is_read_only_for_its_seasons(tmp_path):
    src, hist, off = _hist_setup(tmp_path)
    out = tmp_path / "pbp_runners"
    b24 = brm.build_season(2024, out_dir=out, source=src, hist_source=hist,
                           schedule=_sched([11, 12, 13]), workers=1, today=AFTER_FREEZE,
                           official_path=off, allow_refetch=False)
    assert b24["source"] == "win_prob"
    assert b24["games_present"] == 2 and b24["payloads_missing"] == 1     # 13 sits in hist only
    assert not b24["receipts"]["I3"]["pass"] and b24["receipts"]["I3"]["missing"] == [13]
    b11 = brm.build_season(2011, out_dir=out, source=src, hist_source=hist,
                           schedule=_sched([21, 22, 23]), workers=1, today=AFTER_FREEZE,
                           official_path=off, allow_refetch=False)
    assert b11["source"] == "win_prob_hist"
    assert b11["games_present"] == 2 and b11["payloads_missing"] == 1     # 23 sits in win_prob only
    assert set(brm.read_table(out / b11["files"]["pa"])["game_pk"]) == {21, 22}
    b20 = brm.build_season(2020, out_dir=out, source=src, hist_source=hist,
                           schedule=_sched([31, 32]), workers=1, today=AFTER_FREEZE,
                           official_path=off, allow_refetch=False)
    assert b20["source"] == "win_prob_hist" and b20["games_present"] == 2
    # the 2024-season payload parked in the history directory is counted and skipped
    assert b11["other_cached_payloads_skipped"] == 0 and b20["other_cached_payloads_skipped"] == 0


def test_history_season_leaves_frozen_seasons_and_both_sources_byte_identical(tmp_path):
    src, hist, off = _hist_setup(tmp_path)
    out = tmp_path / "pbp_runners"
    man = brm.build([2024], out_dir=out, source=src, hist_source=hist, workers=1, today=AFTER_FREEZE,
                    schedules={2024: _sched([11, 12])}, official_paths={2024: off},
                    allow_refetch=False)
    blk = dict(man["seasons"]["2024"])
    assert blk["frozen"]
    pa_p, rn_p = out / blk["files"]["pa"], out / blk["files"]["runners"]
    before = (pa_p.read_bytes(), rn_p.read_bytes(), pa_p.stat().st_mtime_ns, rn_p.stat().st_mtime_ns)
    src_hash, hist_hash = _hash_dir(src), _hash_dir(hist)
    man2 = brm.build([2024, 2011, 2020], out_dir=out, source=src, hist_source=hist, workers=1,
                     today=AFTER_FREEZE,
                     schedules={2024: _sched([11, 12]), 2011: _sched([21, 22]), 2020: _sched([31, 32])},
                     official_paths={2024: off, 2011: off, 2020: off}, allow_refetch=False)
    assert man2["seasons"]["2024"] == blk
    assert (pa_p.read_bytes(), rn_p.read_bytes(), pa_p.stat().st_mtime_ns, rn_p.stat().st_mtime_ns) == before
    assert man2["seasons"]["2011"]["frozen"] and man2["seasons"]["2011"]["receipts"]["I3"]["pass"]
    assert man2["seasons"]["2020"]["frozen"]
    assert man2["hist_seasons"] == list(brm.HIST_SEASONS)
    assert man2["hist_source_cache"] == str(hist) and man2["source_cache"] == str(src)
    assert _hash_dir(src) == src_hash and _hash_dir(hist) == hist_hash


def test_parse_seasons_keeps_2020_only_when_named():
    assert brm._parse_seasons("2011-2017,2020") == [2011, 2012, 2013, 2014, 2015, 2016, 2017, 2020]
    assert brm._parse_seasons("2018-2026") == [2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]
    assert brm._parse_seasons("2018,2019,2021-2026") == list(brm.DEFAULT_SEASONS)
    import build_ebr
    assert build_ebr._parse_seasons("2011-2017,2020") == brm._parse_seasons("2011-2017,2020")
    assert 2020 not in build_ebr._parse_seasons("2018-2026")


def test_history_refetch_paces_a_second_apart_with_the_house_user_agent(tmp_path, monkeypatch):
    src, hist, off = _hist_setup(tmp_path)
    out = tmp_path / "pbp_runners"
    bad = _official(tmp_path / "bad.json", {A: {"pa": 2}, B: {"sb": 3, "pa": 2}, C: {"pa": 2}})
    seen = {"sleeps": [], "headers": []}

    class _Resp:
        content = json.dumps(_game(year=2011)).encode("utf-8")

        def raise_for_status(self):
            return None

    class _Session:
        def get(self, url, headers=None, timeout=None):
            seen["headers"].append(headers)
            return _Resp()
    import feed_cache
    monkeypatch.setattr(feed_cache, "SESSION", _Session())
    monkeypatch.setattr(brm.time, "sleep", lambda s: seen["sleeps"].append(s))
    blk = brm.build_season(2011, out_dir=out, source=src, hist_source=hist, schedule=_sched([21, 22]),
                           workers=1, today=AFTER_FREEZE, official_path=bad)
    assert blk["refetched_games"] == [21, 22]
    assert seen["sleeps"] == [brm.HIST_FETCH_INTERVAL] * 2 and brm.HIST_FETCH_INTERVAL == 1.0
    assert all(h == {"User-Agent": fwh.house_user_agent()} for h in seen["headers"])
    assert sorted(p.name for p in (out / "refetch").iterdir()) == ["21.json", "22.json"]
    assert not (hist / "refetch").exists()


def test_win_prob_hist_is_excluded_from_the_pruner():
    assert "win_prob_hist" in prune_cache.EXCLUDED
    assert "win_prob_hist" not in prune_cache.SAFE_CACHES
    assert "win_prob" in prune_cache.SAFE_CACHES          # the live cache is still pruned


# --- the fetcher -----------------------------------------------------------
def test_fetcher_refuses_the_live_cache_the_corpus_and_the_record(tmp_path):
    import mlb_leverage
    for bad in (tmp_path / "win_prob", tmp_path / "pbp_corpus" / "x", tmp_path / "pbp_runners",
                Path(mlb_leverage.CACHE_DIR)):
        with pytest.raises(RuntimeError):
            fwh.check_out_dir(bad)
    assert fwh.check_out_dir(tmp_path / "win_prob_hist") == tmp_path / "win_prob_hist"
    assert fwh.HIST_DIR.name == "win_prob_hist" and fwh.HIST_DIR != Path(mlb_leverage.CACHE_DIR)
    assert fwh.HIST_SEASONS == brm.HIST_SEASONS
    assert fwh.MIN_INTERVAL >= 1.0
    import pipeline_vintage
    assert fwh.house_user_agent() == pipeline_vintage.USER_AGENT and "eephus" in fwh.house_user_agent()


class _FakeResp:
    def __init__(self, status, body=b""):
        self.status_code = status
        self.content = body


def _complete_plays(n=3):
    plays = _game(year=2011)[:n]
    for p in plays:
        p["homeTeamWinProbability"] = 50.0
    plays[-1]["homeTeamWinProbability"] = 100.0
    return plays


def _fake_session(answers: dict, calls: list):
    class _S:
        def get(self, url, headers=None, timeout=None):
            pk = int(url.rstrip("/").split("/")[-2])
            calls.append((pk, headers, timeout))
            a = answers[pk]
            if isinstance(a, Exception):
                raise a
            return a
    return _S()


def test_fetcher_writes_only_the_history_directory_with_receipts_and_pacing(tmp_path):
    hist = tmp_path / "win_prob_hist"
    complete = json.dumps(_complete_plays()).encode("utf-8")
    partial = json.dumps(_complete_plays()[:-1]).encode("utf-8")
    hist.mkdir()
    (hist / "5.json").write_bytes(complete)                      # already on disk, complete, receipted
    (hist / "6.json").write_bytes(partial)                       # on disk, partial: fetched again
    (hist / "receipts.jsonl").write_text(json.dumps(
        {"game_pk": 5, "season": 2011, "date": "2011-04-03", "status": "ok", "bytes": len(complete),
         "sha256": hashlib.sha256(complete).hexdigest(), "fetched_at": "x", "elapsed_ms": 1}) + "\n",
        encoding="utf-8")
    calls, sleeps = [], []
    answers = {1: _FakeResp(200, complete), 2: _FakeResp(404), 3: _FakeResp(200, partial),
               4: _FakeResp(200, complete), 6: _FakeResp(200, complete),
               7: ConnectionError("boom")}
    sched = {2011: [[1, "2011-04-01"], [2, "2011-04-01"], [3, "2011-04-02"], [4, "2011-04-02"],
                    [5, "2011-04-03"], [6, "2011-04-03"], [7, "2011-04-04"]]}
    clock = {"t": 0.0}
    pacer = fwh.Pacer(1.0, clock=lambda: clock["t"], sleep=lambda s: sleeps.append(s))
    summ = fwh.run([2011], out_dir=hist, session=_fake_session(answers, calls), pacer=pacer,
                   user_agent="ua-test", schedules=sched)
    assert [c[0] for c in calls] == [1, 2, 3, 4, 6, 7]
    assert all(c[1] == {"User-Agent": "ua-test"} for c in calls)
    assert sleeps == [1.0] * 5                                   # one second between requests
    assert sorted(p.name for p in hist.glob("*.json")) == ["1.json", "4.json", "5.json", "6.json",
                                                            "summary.json"]
    assert (hist / "6.json").read_bytes() == complete
    lines = [json.loads(x) for x in (hist / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["game_pk"], r["status"]) for r in lines][1:] == [(1, "ok"), (2, "no_play"), (3, "partial"),
                                                                (4, "ok"), (6, "ok"), (7, "error")]
    assert summ["ok_receipts_before"] == 1 and not list(hist.glob("receipts.jsonl.damaged-*"))
    ok = [r for r in lines if r["status"] == "ok"]
    assert all(r["bytes"] == len(complete) and r["sha256"] == hashlib.sha256(complete).hexdigest()
               and r["fetched_at"] and r["season"] == 2011 and r["date"] for r in ok)
    blk = summ["seasons"]["2011"]
    assert blk == {"scheduled": 7, "present_before": 1, "fetched": 3, "no_play": 1, "partial": 1,
                   "error": 1, "bytes": 3 * len(complete) + len(partial), "present_after": 4,
                   "complete": False}
    assert summ["requests"] == 6 and summ["user_agent"] == "ua-test" and summ["min_interval_s"] == 1.0
    assert not (tmp_path / "win_prob").exists()
    # the second run resumes: complete payloads are skipped, the rest are asked again
    calls2 = []
    answers2 = {2: _FakeResp(404), 3: _FakeResp(200, complete), 7: _FakeResp(200, complete)}
    summ2 = fwh.run([2011], out_dir=hist, session=_fake_session(answers2, calls2), pacer=pacer,
                    user_agent="ua-test", schedules=sched)
    assert [c[0] for c in calls2] == [2, 3, 7]
    blk2 = summ2["seasons"]["2011"]
    assert blk2["present_before"] == 4 and blk2["fetched"] == 2 and blk2["no_play"] == 1
    assert blk2["present_after"] == 6 and blk2["complete"] is True
    assert len((hist / "receipts.jsonl").read_text(encoding="utf-8").splitlines()) == 10


def test_fetcher_heals_damaged_receipts_and_refetches_unreceipted_or_altered_payloads(tmp_path):
    """The 2026-10-14 blue screens: receipts lost for payloads on disk, a receipts
    file with NUL runs and a cut line, a payload zero-filled under an ok receipt."""
    hist = tmp_path / "win_prob_hist"
    hist.mkdir()
    complete = json.dumps(_complete_plays()).encode("utf-8")
    other = json.dumps(_complete_plays(2)).encode("utf-8")
    sha = hashlib.sha256(complete).hexdigest()

    def receipt(pk, **kw):
        r = {"game_pk": pk, "season": 2011, "date": "2011-04-01", "status": "ok", "bytes": len(complete),
             "sha256": sha, "fetched_at": "x", "elapsed_ms": 1}
        r.update(kw)
        return json.dumps(r, sort_keys=True, separators=(",", ":")).encode("utf-8")
    (hist / "1.json").write_bytes(complete)                      # complete, receipted: skipped
    (hist / "2.json").write_bytes(complete)                      # complete, NO receipt: fetched again
    (hist / "3.json").write_bytes(b"\0" * len(complete))         # zero-filled under an ok receipt
    (hist / "4.json").write_bytes(other)                         # complete, bytes differ from the receipt
    (hist / "receipts.jsonl").write_bytes(
        receipt(1) + b"\n" + receipt(3) + b"\n" + receipt(4) + b"\n" + b"\0" * 40 + b"\n"
        + receipt(9)[:30] + b"\n" + receipt(8, status="no_play", sha256=None, bytes=0) + b"\n")
    calls = []
    answers = {pk: _FakeResp(200, complete) for pk in (2, 3, 4)}
    answers[8] = _FakeResp(404)
    pacer = fwh.Pacer(1.0, clock=lambda: 0.0, sleep=lambda s: None)
    sched = {2011: [[pk, "2011-04-01"] for pk in (1, 2, 3, 4, 8)]}
    summ = fwh.run([2011], out_dir=hist, session=_fake_session(answers, calls), pacer=pacer,
                   user_agent="ua", schedules=sched)
    assert [c[0] for c in calls] == [2, 3, 4, 8]
    assert summ["ok_receipts_before"] == 3
    parked = list(hist.glob("receipts.jsonl.damaged-*"))
    assert len(parked) == 1 and b"\0" in parked[0].read_bytes()
    lines = (hist / "receipts.jsonl").read_bytes().split(b"\n")
    assert b"\0" not in (hist / "receipts.jsonl").read_bytes()
    recs = [json.loads(x) for x in lines if x.strip()]
    assert [(r["game_pk"], r["status"]) for r in recs] == [(1, "ok"), (3, "ok"), (4, "ok"), (8, "no_play"),
                                                           (2, "ok"), (3, "ok"), (4, "ok"), (8, "no_play")]
    assert all((hist / f"{pk}.json").read_bytes() == complete for pk in (1, 2, 3, 4))
    blk = summ["seasons"]["2011"]
    assert blk["present_before"] == 1 and blk["fetched"] == 3 and blk["no_play"] == 1 and blk["complete"]
    # a clean file is left alone: the third run heals nothing and fetches nothing but the 404
    calls2 = []
    fwh.run([2011], out_dir=hist, session=_fake_session({8: _FakeResp(404)}, calls2), pacer=pacer,
            user_agent="ua", schedules=sched)
    assert [c[0] for c in calls2] == [8] and len(list(hist.glob("receipts.jsonl.damaged-*"))) == 1
    assert fwh.heal_receipts(tmp_path / "nowhere") == {}


def test_fetcher_keeps_a_tied_official_game_only_when_the_schedule_confirms_the_tie(tmp_path):
    """2016-09-29 Cubs at Pirates ended 1-1 after six innings: its list ends at 50, not 0 or 100."""
    hist = tmp_path / "win_prob_hist"

    def tied(inning=6, home=1, away=1, complete=True):
        plays = _complete_plays()
        plays[-1]["homeTeamWinProbability"] = 50.0
        plays[-1]["about"].update({"inning": inning, "isComplete": complete})
        plays[-1]["result"].update({"homeScore": home, "awayScore": away})
        return json.dumps(plays).encode("utf-8")
    body = tied()
    assert fwh.plays_end_tied(json.loads(body))
    for bad in (tied(inning=4), tied(home=2), tied(complete=False)):
        assert not fwh.plays_end_tied(json.loads(bad))

    def sched(pk, is_tie):
        return _FakeResp(200, json.dumps({"dates": [{"games": [
            {"gamePk": pk, "isTie": is_tie, "status": {"abstractGameState": "Final"}}]}]}).encode("utf-8"))
    calls = []

    class _S:
        def get(self, url, params=None, headers=None, timeout=None):
            calls.append((url, (params or {}).get("gamePk"), headers))
            if params:
                return sched(params["gamePk"], params["gamePk"] == 1)
            return _FakeResp(200, body)
    sleeps = []
    pacer = fwh.Pacer(1.0, clock=lambda: 0.0, sleep=lambda s: sleeps.append(s))
    summ = fwh.run([2016], out_dir=hist, session=_S(), pacer=pacer, user_agent="ua",
                   schedules={2016: [[1, "2016-09-29"], [2, "2016-09-29"]]})
    import mlb_leverage
    assert [(c[0] == mlb_leverage.SCHEDULE_API, c[1]) for c in calls] == [(False, None), (True, 1),
                                                                         (False, None), (True, 2)]
    assert all(c[2] == {"User-Agent": "ua"} for c in calls) and sleeps == [1.0] * 3
    assert (hist / "1.json").read_bytes() == body and not (hist / "2.json").exists()
    recs = [json.loads(x) for x in (hist / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["game_pk"], r["status"], r.get("tie")) for r in recs] == [(1, "ok", True), (2, "partial", None)]
    assert summ["seasons"]["2016"]["fetched"] == 1 and summ["seasons"]["2016"]["partial"] == 1
    # resumed: the receipted tie is kept without a request; with no receipt it is not complete
    assert fwh.payload_complete(hist / "1.json", recs[0]["sha256"]) and not fwh.payload_complete(hist / "1.json")
    calls.clear()
    fwh.run([2016], out_dir=hist, session=_S(), pacer=pacer, user_agent="ua", schedules={2016: [[1, "2016-09-29"]]})
    assert calls == []


def test_fetcher_limit_caps_the_requests_of_one_run(tmp_path):
    hist = tmp_path / "win_prob_hist"
    complete = json.dumps(_complete_plays()).encode("utf-8")
    calls = []
    answers = {pk: _FakeResp(200, complete) for pk in (1, 2, 3)}
    pacer = fwh.Pacer(1.0, clock=lambda: 0.0, sleep=lambda s: None)
    summ = fwh.run([2020], out_dir=hist, session=_fake_session(answers, calls), pacer=pacer,
                   user_agent="ua", limit=2, schedules={2020: [[1, "d"], [2, "d"], [3, "d"]]})
    assert [c[0] for c in calls] == [1, 2] and summ["requests"] == 2
    assert summ["seasons"]["2020"]["present_after"] == 2 and not summ["seasons"]["2020"]["complete"]
    with pytest.raises(SystemExit):
        fwh._parse_seasons("2018")
    assert fwh._parse_seasons("2011-2017,2020") == list(fwh.HIST_SEASONS)
