# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Window OBP counts HBP and SF, and window FIP counts HBP.

WHY THIS EXISTS (census M02-08, 2026-09-25, verifiers PARTLY and CONFIRMED). The game
feed extractor dropped hitByPitch and sacFlies, so every date-windowed board, the
Splits panel, the 15-game rolling OPS and the L15 OPS chip computed OBP as
(H+BB)/(AB+BB): on the 165 single-level 2026 rows whose AB match the served season
row, full-season window OBP ran 0.0078 low on average (worst 0.045). FIP left out HBP.

Contract pinned here:
  * the extractor carries hbp and sf (hitters) and hbp (pitchers);
  * _lbObp uses (H+BB+HBP)/(AB+BB+HBP+SF) when every game carries them, and falls
    back to the old formula when any game lacks them;
  * on the served slice, full-season single-level window OBP equals the served season
    OBP within 0.002 on every matched row.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


def test_extractor_keeps_hbp_and_sf():
    import statcast_metrics as sm
    hit = [{"date": "2026-09-01", "_level": "AA", "stat": {
        "hits": 1, "atBats": 3, "plateAppearances": 5, "baseOnBalls": 0,
        "hitByPitch": 1, "sacFlies": 1}}]
    g = sm._extract_recent_games(hit, False, limit=5)[0]
    assert g["hbp"] == 1 and g["sf"] == 1
    pit = [{"date": "2026-09-01", "_level": "AA", "stat": {"inningsPitched": "5.0", "hitByPitch": 2}}]
    assert sm._extract_recent_games(pit, True, limit=5)[0]["hbp"] == 2
    bare = [{"date": "2026-09-01", "_level": "AA", "stat": {"hits": 1, "atBats": 3}}]
    g = sm._extract_recent_games(bare, False, limit=5)[0]
    assert g["hbp"] is None and g["sf"] is None


@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = _src()
    m = re.search(r"^const _LB_FIP_CONST = .*?;$", src, re.M)
    ctx = mr.MiniRacer()
    ctx.eval(m.group(0))
    for fn in ("_lbIpOuts", "_lbObp", "_lbFip", "_lbAggHitter", "_lbAggPitcher"):
        ctx.eval(_function_source(src, fn))
    return ctx


def test_obp_formula_and_fallback(js):
    games = [{"d": "2026-09-01", "pa": 5, "ab": 3, "h": 1, "bb": 0, "hbp": 1, "sf": 1},
             {"d": "2026-09-02", "pa": 4, "ab": 3, "h": 1, "bb": 1, "hbp": 0, "sf": 0}]
    obp = js.eval("_lbObp(_lbAggHitter(%s))" % json.dumps(games))
    assert obp == pytest.approx((2 + 1 + 1) / (6 + 1 + 1 + 1))
    games[1].pop("hbp")
    obp = js.eval("_lbObp(_lbAggHitter(%s))" % json.dumps(games))
    assert obp == pytest.approx((2 + 1) / (6 + 1))  # one game lacks hbp: old formula
    pit = [{"d": "2026-09-01", "ip": 6.0, "k": 6, "bb": 2, "hr": 1, "hbp": 1}]
    fip = js.eval("_lbFip(_lbAggPitcher(%s))" % json.dumps(pit))
    assert fip == pytest.approx((13 * 1 + 3 * 3 - 2 * 6) / 6 + 3.10)


def test_served_window_obp_matches_season_obp(js):
    from conftest import load_data_doc
    gl = load_data_doc("leaderboard_gamelogs.json")
    ts = load_data_doc("timeseries.json")
    if not gl or not ts or not gl.get("players"):
        pytest.skip("slice or timeseries not built")
    if not any(g.get("hbp") is not None for e in gl["players"].values() for g in e["games"]):
        pytest.skip("slice predates hbp/sf (rebuild tools/build_leaderboard_gamelogs.py)")
    byk = {p["player_key"]: p for p in ts.get("players") or []}
    n = 0
    for k, e in gl["players"].items():
        if e.get("is_pitcher") or k not in byk:
            continue
        for cs in byk[k].get("career_stats") or []:
            if cs.get("season") != 2026 or cs.get("level") in (None, "MLB") or cs.get("obp") in (None, ""):
                continue
            gs = [g for g in e["games"] if g["lvl"] == cs["level"] and g["d"].startswith("2026")]
            if not gs or sum(g["ab"] or 0 for g in gs) != cs.get("ab") or cs["ab"] < 100:
                continue
            obp = js.eval("_lbObp(_lbAggHitter(%s))" % json.dumps(gs))
            assert obp == pytest.approx(float(cs["obp"]), abs=0.002), (k, cs["level"], obp, cs["obp"])
            n += 1
    assert n >= 50, n
