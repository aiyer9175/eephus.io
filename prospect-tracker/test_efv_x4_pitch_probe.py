# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the eFV X4 StatsAPI pitch probe (tools/efv_x4_pitch_probe.py; registration
docs/efv-x4-pitch-probe/REGISTRATION.md).

1. The producer's constants are the registration's.
2. The sample is deterministic: the first home game on or after May 15 and Aug 1, a
   fallback to the latest earlier home game, a repeated pick counted once.
3. The per-game field shares and the 80 percent tracked rule; balls in play are the
   launch fields' denominator.
4. The coverage rule: VELO-COVERED and FULL-COVERED at half the sampled games; coverage
   REAL only from a sub-AAA cell of 2021 to 2023; the extra pixel field enters no rule.
5. The zone rule, the aggregate's swing codes, and the no-look-ahead assertion.
6. Bans: no served module imports the producer; no grouping by consensus-FV level; no
   reserved list vintage; no em-dash. The artifact, when present, is development only.
No test touches the network or the database.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_vintage_frame as F  # noqa: E402
import efv_x4_pitch_probe as P  # noqa: E402

SRC = ROOT / "tools" / "efv_x4_pitch_probe.py"
TEST_SRC = Path(__file__)


def test_registration_declares_the_producer_constants():
    doc = P.GATE_DOC.read_text(encoding="utf-8")
    assert "Registration status: REGISTERED" in doc
    assert "seed 20261015" in doc and "lambda = 10" in doc and "B = 2000" in doc
    assert "at least 80" in doc and "at least 50" in doc
    assert P.SPORTS == {11: "AAA", 12: "AA", 13: "A+", 14: "A"}
    assert P.SUB_AAA == (12, 13, 14)
    assert P.SEASONS == (2021, 2022, 2023, 2024, 2025, 2026)
    assert P.LABEL_SEASONS == (2021, 2022, 2023)
    assert (P.EARLY_MMDD, P.LATE_MMDD) == ("05-15", "08-01")
    assert P.GAME_TRACKED_SHARE == 0.80 and P.CELL_COVERED_SHARE == 0.50
    assert P.LAMBDA == 10.0 and P.FOLDS == 5 and P.SEED == 20261015 and P.B_DEFAULT == 2000
    assert P.PROBE_WORKERS == 2 and P.FULL_WORKERS == 4 and P.REQUEST_PAUSE == 0.25
    assert list(P.BLACKOUT_UTC_HOURS) == [6, 7, 8, 9, 10]
    assert (P.PIT_MIN_PITCHES, P.HIT_MIN_PA, P.MIN_FB, P.MIN_BIP, P.MIN_SWINGS) == (100, 50, 25, 15, 30)
    assert P.CLEAN_COHORTS == (2021,)


def test_sample_takes_first_home_game_after_each_cut_with_fallback():
    sched = [
        {"gamePk": 1, "date": "2023-04-10", "home": 7},
        {"gamePk": 3, "date": "2023-05-15", "home": 7},
        {"gamePk": 2, "date": "2023-05-15", "home": 7},
        {"gamePk": 4, "date": "2023-08-02", "home": 7},
        {"gamePk": 5, "date": "2023-04-20", "home": 8},
        {"gamePk": 6, "date": "2023-05-01", "home": 8},
    ]
    picks = P.sample_games(sched, 2023)
    got = {(g["home"], g["half"]): g["gamePk"] for g in picks}
    assert got[(7, "early")] == 2 and got[(7, "late")] == 4
    # home 8 has no game after either cut: the latest earlier game stands in, once
    assert got[(8, "early")] == 6 and (8, "late") not in got
    assert len(picks) == 3


def _pitch(speed=None, spin=None, inplay=False, ls=None, la=None, xy=True, zone=None, ptype=None):
    pd = {"breaks": {}, "coordinates": {}}
    if speed is not None:
        pd["startSpeed"] = speed
        pd["extension"] = 6.2
        pd["coordinates"].update({"pX": 0.1, "pZ": 2.4})
    if spin is not None:
        pd["breaks"].update({"spinRate": spin, "breakVerticalInduced": 15.0, "breakHorizontal": -6.0})
    if xy:
        pd["coordinates"].update({"x": 110.0, "y": 160.0})
    if zone is not None:
        pd["zone"] = zone
    det = {"isInPlay": inplay, "call": {"code": "X" if inplay else "C"}}
    if ptype:
        det["type"] = {"code": ptype}
    ev = {"isPitch": True, "details": det, "pitchData": pd}
    if inplay:
        ev["hitData"] = {k: v for k, v in (("launchSpeed", ls), ("launchAngle", la)) if v is not None}
    return ev


def _feed(events):
    return {"gameData": {"venue": {"id": 1, "name": "Park"}, "teams": {"home": {"id": 9, "name": "Club"}},
                         "datetime": {"officialDate": "2023-05-20"}},
            "liveData": {"plays": {"allPlays": [{"playEvents": events}]}}}


def test_game_coverage_shares_and_the_tracked_rule():
    ev = [_pitch(speed=93.0, spin=2300.0, ptype="FF") for _ in range(8)]
    ev += [_pitch() for _ in range(2)]                                   # 8 of 10 tracked
    ev += [_pitch(speed=90.0, inplay=True, ls=95.0, la=12.0), _pitch(speed=90.0, inplay=True)]
    c = P.game_coverage(_feed(ev))
    assert c["pitches"] == 12 and c["bip"] == 2
    assert c["share"]["startSpeed"] == pytest.approx(10 / 12, abs=1e-4)
    assert c["tracked"]["startSpeed"] is True
    assert c["share"]["spinRate"] == pytest.approx(8 / 12, abs=1e-4) and c["tracked"]["spinRate"] is False
    assert c["share"]["launchSpeed"] == pytest.approx(0.5) and c["tracked"]["launchSpeed"] is False
    assert c["tracked"]["xy"] is True and c["venue"] == "Park"
    # an untracked feed: every registered field 0, only the stringer's pixels present
    c0 = P.game_coverage(_feed([_pitch() for _ in range(5)]))
    assert all(c0["share"][f] == 0.0 for f in P.FIELDS if f not in P.EXTRA_FIELDS and f not in P.BIP_FIELDS)
    assert c0["share"]["launchSpeed"] is None


def _game(level, sport, season, venue, tracked):
    t = {f: (f in tracked) for f in P.FIELDS}
    return {"level": level, "sport": sport, "season": season, "venue": venue, "home": venue,
            "pitches": 300, "tracked": t}


def test_coverage_rule_and_reality_come_from_sub_aaa_label_seasons_only():
    full = set(P.FULL_SET)
    games = [_game("AAA", 11, 2022, "a", full), _game("AAA", 11, 2022, "b", full),
             _game("AA", 12, 2024, "c", {"startSpeed"}), _game("AA", 12, 2024, "d", {"startSpeed"}),
             _game("A+", 13, 2022, "e", {"startSpeed", "xy"}), _game("A+", 13, 2022, "f", {"xy"}),
             _game("A", 14, 2021, "g", {"xy"}), _game("A", 14, 2021, "h", {"xy"})]
    cov = P.coverage_tables(games)
    cells = {(c["level"], c["season"]): c for c in cov["cells"]}
    assert cells[("AAA", 2022)]["velo_covered"] and cells[("AAA", 2022)]["full_covered"]
    assert cells[("AA", 2024)]["velo_covered"] and not cells[("AA", 2024)]["full_covered"]
    assert cells[("A+", 2022)]["velo_covered"]                       # one of two games: half
    assert not cells[("A", 2021)]["velo_covered"]                    # pixels alone count for nothing
    assert cov["coverage_real"] is True
    assert P.covered_cells(cov) == [(13, 2022)]
    # AAA and a 2024 sub-AAA cell alone do not make coverage real
    cov2 = P.coverage_tables(games[:4] + games[6:])
    assert cov2["coverage_real"] is False and P.covered_cells(cov2) == []


def test_zone_rule():
    assert P._in_zone({"zone": 5}) is True
    assert P._in_zone({"zone": 12}) is False
    pd = {"coordinates": {"pX": 0.5, "pZ": 2.5}, "strikeZoneTop": 3.4, "strikeZoneBottom": 1.6}
    assert P._in_zone(pd) is True
    pd["coordinates"]["pX"] = 1.2
    assert P._in_zone(pd) is False
    # the stringer's pixel coordinates are never read as a location
    assert P._in_zone({"coordinates": {"x": 100.0, "y": 150.0}, "strikeZoneTop": 3.4,
                       "strikeZoneBottom": 1.6}) is None


def test_swing_codes():
    assert P.WHIFF == {"S", "W", "M", "Q"}
    assert P.WHIFF < P.SWING and "T" in P.SWING and "T" not in P.WHIFF
    assert not ({"B", "*B", "C", "H", "I", "P", "V", "A"} & P.SWING)


def test_candidate_metrics_need_every_contributing_cell():
    cov = {"cells": [{"sport": 12, "season": 2023, "tracked_game_share": {f: 1.0 for f in P.FIELDS}},
                     {"sport": 13, "season": 2023, "tracked_game_share": dict({f: 1.0 for f in P.FIELDS}, spinRate=0.2)}]}
    out = P.candidate_metrics(cov, [(12, 2023), (13, 2023)])
    assert "fb_spin" not in out["pit"]["metrics"] and "fb_spin" in out["pit"]["dropped"]
    assert "fb_velo_p95" in out["pit"]["metrics"] and "ev_p90" in out["hit"]["metrics"]


def test_build_rows_rejects_look_ahead(monkeypatch):
    agg = {"pit": {(5, 2021, "AA"): {"fb_velo_p95": 95.0, "_max_date": "2022-03-01"}}, "hit": {}}
    cons = {(5, 2021): {"fv": 50.0, "player_key": "k5"}}
    with pytest.raises(AssertionError):
        P.build_rows("pit", agg, ["fb_velo_p95"], mlb={}, war={}, cons=cons)
    agg["pit"][(5, 2021, "AA")]["_max_date"] = "2021-09-10"
    rows = P.build_rows("pit", agg, ["fb_velo_p95"], mlb={}, war={}, cons=cons)
    assert len(rows) == 1 and rows[0]["as_of"] == "2022-01-01" and rows[0]["spent"] is False


def test_build_rows_takes_the_highest_level():
    agg = {"hit": {(5, 2022, "A+"): {"ev_p90": 100.0, "_max_date": "2022-06-01"},
                   (5, 2022, "AA"): {"ev_p90": 101.0, "_max_date": "2022-09-01"}}, "pit": {}}
    cons = {(5, 2022): {"fv": 45.0, "player_key": "k5"}}
    rows = P.build_rows("hit", agg, ["ev_p90"], mlb={5: {2024}}, war={(5, 2024): 1.5}, cons=cons)
    assert rows[0]["level"] == "AA" and rows[0]["reach3"] == 1.0 and rows[0]["rate3"] == 1.5
    assert rows[0]["spent"] is True


def test_bans():
    src = SRC.read_text(encoding="utf-8")
    for text in (src, TEST_SRC.read_text(encoding="utf-8"), P.GATE_DOC.read_text(encoding="utf-8")):
        assert chr(0x2014) not in text and chr(0x2013) not in text
    assert not re.compile(r"(by|per|group)_?(fv|consensus|grade)").search(src)
    assert not re.search(r"fv_cell|fv_tier|fv_bucket", src)
    for banned in ("import backtest", "run_backtest", "import efv_export", "import proj_export",
                   "train_proj_models", "import efv_score", "import storage"):
        assert banned not in src, banned
    assert set(P.CONSENSUS_VINTAGES).isdisjoint(F.RESERVED_LV)
    assert P.CONSENSUS_VINTAGES == (2022, 2023, 2024)
    assert str(P.CACHE).replace("\\", "/").endswith(".cache/efv_x4_pitch")
    for p in list(ROOT.glob("*.py")) + [ROOT / "build_site.py"]:
        if p.name.startswith("test_"):
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            assert "efv_x4_pitch_probe" not in line, (p.name, line)


@pytest.fixture(scope="module")
def artifact():
    if not P.OUT_PATH.exists():
        pytest.skip("no artifact")
    return json.loads(P.OUT_PATH.read_text(encoding="utf-8"))


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def test_artifact_is_development_only(artifact):
    assert artifact["role"] == "development" and artifact["served"] is False and artifact["ships"] is False
    assert artifact["registration"]["doc"] == "docs/efv-x4-pitch-probe/REGISTRATION.md"
    for s in _strings(artifact):
        assert chr(0x2014) not in s
        assert not re.search(r"\bFV (45|50|55|60|65)\b", s), s


def test_artifact_coverage_verdict_matches_its_own_cells(artifact):
    cov = artifact["coverage"]
    real = any(c["velo_covered"] for c in cov["cells"] if c["sport"] in P.SUB_AAA and c["season"] in P.LABEL_SEASONS)
    assert cov["coverage_real"] is real
    for c in cov["cells"]:
        assert c["velo_covered"] is (c["tracked_game_share"]["startSpeed"] >= P.CELL_COVERED_SHARE)
    if not real:
        assert "status" in (artifact.get("read") or {"status": "absent"})
