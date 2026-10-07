# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for bullpen_export.py - the Bullpen Leaderboards sidecar.

Pure-function tests (IP conversion, the StatsAPI-row -> Reliever build with the
leverage join) run offline. The data-contract test validates the committed
data/bullpen_leaderboards.json shape and skips when it is absent (so the export
is never triggered at test time - no network in the suite).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import bullpen_export as be
import rem_plus

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "bullpen_leaderboards.json"
VERDICTS = {"validated", "provisional", "unvalidated", "deprecated"}


def test_ip_to_float():
    assert be.ip_to_float("42.0") == 42.0
    assert abs(be.ip_to_float("42.1") - (42 + 1 / 3)) < 1e-9   # 42.1 = 42 1/3
    assert abs(be.ip_to_float("42.2") - (42 + 2 / 3)) < 1e-9   # 42.2 = 42 2/3
    assert be.ip_to_float(None) == 0.0
    assert abs(be.ip_to_float(53.333) - 53.333) < 1e-6         # true decimal passes through


def test_build_relievers_joins_leverage_and_swstr():
    rows = [
        {"mlbam": 111, "name": "Ace Reliever", "team": "NYY", "G": 60, "GS": 0,
         "SV": 30, "HLD": 2, "IP": "65.0", "ER": 15, "R": 17, "BB": 15, "SO": 95,
         "HR": 4, "HBP": 3, "BF": 250, "Pit": 1000},
        {"mlbam": 222, "name": "No Lev", "team": "BOS", "G": 40, "GS": 0,
         "SV": 0, "HLD": 5, "IP": "40.0", "ER": 18, "R": 20, "BB": 18, "SO": 42,
         "HR": 6, "HBP": 1, "BF": 175, "Pit": 700},
    ]
    leverage = {111: {"gmli": 1.9, "wpa": 3.2, "wpa_li": 2.1, "sd": 25, "md": 4,
                      "entry_inning": 9.0}}
    swstr = {111: 0.16}
    rels = be.build_relievers(rows, leverage, swstr)
    by = {r.mlbam: r for r in rels}
    assert set(by) == {111, 222}
    ace = by[111]
    assert ace.name == "Ace Reliever" and ace.team == "NYY"
    assert ace.so == 95 and ace.bb == 15 and ace.hr == 4 and ace.hbp == 3
    assert ace.sv == 30 and ace.hld == 2
    assert ace.gmli == 1.9 and ace.sd == 25 and ace.md == 4    # leverage joined
    assert abs(ace.sts - 0.16 * 1000) < 1e-6                   # SwStr% -> count
    # the arm with no leverage row keeps None leverage fields
    assert by[222].gmli is None and by[222].wpa is None


def test_build_relievers_scores_through_the_model():
    import rem_plus
    rows = [{"mlbam": 1000 + i, "name": f"R{i}", "team": "NYY", "G": 55, "GS": 0,
             "SV": 0, "HLD": 3, "IP": "55.0", "ER": 22, "R": 24, "BB": 20, "SO": 55,
             "HR": 6, "HBP": 2, "BF": 230, "Pit": 900} for i in range(12)]
    rels = be.build_relievers(rows, {}, {})
    out = rem_plus.score_pool(rels)
    assert out["relievers"], "no relievers scored"
    assert all(90 <= r["rem_plus"] <= 110 for r in out["relievers"])  # clones ~ 100


@pytest.mark.skipif(not DATA.exists(), reason="bullpen_leaderboards.json not generated")
def test_data_contract():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    for k in ("season", "as_of", "coverage", "verdict", "pool", "relievers", "teams"):
        assert k in d, f"missing top-level key {k}"
    assert d["verdict"] in VERDICTS
    assert isinstance(d["relievers"], list) and d["relievers"]
    assert isinstance(d["teams"], list) and d["teams"]
    # ~30 MLB team pens, not fragmented team codes
    assert 20 <= len(d["teams"]) <= 32, len(d["teams"])
    r0 = d["relievers"][0]
    for k in ("key", "name", "team", "rem_plus", "qualified", "role", "ip", "fip"):
        assert k in r0, f"reliever missing {k}"
    # REM+ is a sane index and the board is REM+-sorted descending
    rems = [r["rem_plus"] for r in d["relievers"] if r["rem_plus"] is not None]
    # REM+ is a RATIO index (100 * pool_mean_FIP / player_FIP, the ERA+/wRC+
    # family), NOT a z-score, so it has no upper bound: an arm whose shrunk skill
    # FIP is half the pool mean scores 200 honestly. The ONLY structural ceiling
    # is rem_plus.fip_skill's max(fip, 1.0) numerical floor.
    #
    # This bound was 40..200 until 2026-07-30, when Mason Miller (SD, closer)
    # crossed it at 203. That is a real number, not a scale break:
    #   - the anchor did not move (pool ERA 3.92 -> 3.91, pool mean FIP
    #     3.89 -> 3.88, pool n 291 -> 296) and rem_plus.py is unchanged;
    #   - he is qualified, not a small sample: 45.7 IP, 172 TBF, 44 G, K% 49.4,
    #     BB% 8.7, ZERO homers, ERA 0.79, SwStr% 21.0, shrunk FIP 1.92;
    #   - three independent estimators agree he is the outlier: 3yr REM+ 156
    #     (100th pct), xREM+ 172 off xwOBA-against .177, WAR/IP+ 126.
    # Compressing him back under 200 would be a display clamp, which is banned
    # (tools/plus_metric_recal_lab.py records REM+ as "none on the served ratio
    # ... ALREADY TRUE-TO-MODEL"), so the CONTRACT widens instead.
    ceiling = 100.0 * d["pool"]["mean_fip"] / 1.0   # the fip_skill floor of 1.0
    assert all(0 < x <= ceiling for x in rems), (min(rems), max(rems), ceiling)
    # ...and here is the invariant the 40..200 band was really groping for, which
    # an honest 203 passes and every scale break fails. build_pool anchors on the
    # IP-weighted mean of the shrunk skill FIP, so the pool average scores exactly
    # 100 by construction; in REM+ units that is the IP-weighted HARMONIC mean
    # over the pool-contributing arms (TBF >= rem_plus.POOL_MIN_TBF). A z-score
    # remap, a doubled constant, or a lost pool re-normalization all move it by
    # tens. Tolerance 1.0 absorbs the served int rounding (measured 100.01).
    pool_rows = [r for r in d["relievers"]
                 if r.get("rem_plus") and (r.get("tbf") or 0) >= rem_plus.POOL_MIN_TBF
                 and (r.get("ip") or 0) > 0]
    assert len(pool_rows) == d["pool"]["n"], (len(pool_rows), d["pool"]["n"])
    anchor = (sum(r["ip"] for r in pool_rows)
              / sum(r["ip"] / r["rem_plus"] for r in pool_rows))
    assert abs(anchor - 100.0) < 1.0, (
        f"REM+ pool anchor is {anchor:.2f}, not 100 - the pool re-normalization "
        "in rem_plus.build_pool is broken or the scale is no longer a ratio index")
    assert rems == sorted(rems, reverse=True), "board not sorted by REM+ desc"
    t0 = d["teams"][0]
    for k in ("team", "bullpen_plus", "n_relievers", "depth"):
        assert k in t0, f"team missing {k}"


def test_join_leverage_consistency(tmp_path, monkeypatch):
    """X-D1 wiring: the artifact's proposed_values stamp gmli_3yr / pct / tag
    onto matching reliever rows by MLBAM; unmatched rows and a missing
    artifact leave the fields absent (column renders blank)."""
    art = {"proposed_values": {"players": {
        "695243": {"name": "Mason Miller", "gmli_3yr": 1.81, "pct": 98,
                   "tag": "established"},
    }}}
    p = tmp_path / "leverage_consistency_eval.json"
    p.write_text(json.dumps(art), encoding="utf-8")
    monkeypatch.setattr(be, "LEVCON_PATH", p)

    rows = [{"mlbam": 695243, "name": "Mason Miller"},
            {"mlbam": 111111, "name": "Unmatched Arm"},
            {"name": "No Id"}]
    n = be._join_leverage_consistency(rows)
    assert n == 1
    assert rows[0]["gmli_3yr"] == 1.81
    assert rows[0]["gmli_3yr_pct"] == 98
    assert rows[0]["gmli_3yr_tag"] == "established"
    assert "gmli_3yr" not in rows[1] and "gmli_3yr" not in rows[2]

    # Missing artifact: a clean no-op, never an exception.
    monkeypatch.setattr(be, "LEVCON_PATH", tmp_path / "nope.json")
    assert be._join_leverage_consistency(rows) == 0


def test_the_scorecard_market_line_is_rem_plus_on_the_regate_pair_set():
    """Census M06-01. The REM+ scorecard printed "market fit rho 0.5157 vs AAV":
    the rho of a damping-0.5 leverage-weighted lab variant, on 271 signings
    joined by normalized name. REM+ itself reads 0.5665 on the 2026-09-18
    re-gate's 232 matched signings, and that stored number is the one the line
    now copies. Nothing here computes a correlation."""
    bt = be._backtest()
    if not bt:
        pytest.skip("data/rem_plus_eval.json absent")
    try:
        regate = json.loads(be.MARKET_PATH.read_text(encoding="utf-8"))["B1_primary"]
    except (OSError, KeyError, ValueError):
        pytest.skip("data/riv_market_regate_eval.json absent")
    assert bt["market_rho"] == regate["v1"]["rho_baseline"]
    assert bt["market_n"] == regate["n_matched_signings"]
    old = json.loads(be.EVAL_PATH.read_text(encoding="utf-8")).get("market_check_aav") or {}
    for k in ("rho_leverage_weighted_vs_aav", "rho_rem_plus_vs_aav"):
        if old.get(k) is not None:
            assert bt["market_rho"] != old[k], k


def test_the_market_line_is_absent_when_the_regate_artifact_is(tmp_path, monkeypatch):
    monkeypatch.setattr(be, "MARKET_PATH", tmp_path / "nope.json")
    assert be._market_line() == {}
    bt = be._backtest()
    if bt:
        assert bt["market_rho"] is None and bt["market_n"] is None


@pytest.mark.skipif(not DATA.exists(), reason="bullpen_leaderboards.json not generated")
def test_pitch_rate_keys_follow_the_serve_flag():
    """P/IP, P/BF and PAR on the relief line (plan Part 8, PM-03). With no
    pitch_rates block (SERVE_PITCH_RATES off) no reliever row or team carries a
    pitch-rate key; with one, every row and team carries all of them, PAR is the
    nearest point of 100 x rate / anchor, and the clubs' team PAR averages 100."""
    import pitch_rates_boards
    d = json.loads(DATA.read_text(encoding="utf-8"))
    assert pitch_rates_boards.check_board(d, "rp") == []
