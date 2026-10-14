# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The runner-aware steal split lab (tools/mgmt_steal_runner_split.py, W11 stage 2), pinned.

Fixtures only: no test here reads a corpus season or relates a feature to a real
outcome.

  - each of the eleven features follows its section 2.1 definition, and every blank
    (no runner id, a runner off the leaderboard, a season with no context block, no
    catcher, no pop time, no pitch hand, no score) lands on its documented value;
  - with every coefficient at zero the candidate IS the incumbent;
  - the lambda grid's tie goes to the larger lambda;
  - the bootstrap resamples games, is seeded, and every statistic shares the draws;
  - ER_runner + ER_other = ER, so DV + ER_runner + ER_other = the realized change;
  - the fit is frozen and written before the score frame is read, an empty score
    frame is a NULL on condition 1, and the read refuses to run twice;
  - no served module, page asset or betting file reads the lab.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import mgmt_steal_runner_split as S  # noqa: E402


def _row(**kw):
    r = {"season": "2022", "target": "2B", "game_pk": 1, "at_bat_index": 3,
         "on_first": 101.0, "on_second": float("nan"), "on_third": float("nan"),
         "base_before": 1, "outs_before": 0, "inning": 3, "half": "bottom",
         "score_diff": 0.0, "pitch_hand": "R"}
    r.update(kw)
    return r


BLOCK = {"runners": {"101": [80, 28.5, 40]},
         "catchers": {"501": [1.95, 20, "A"], "502": [None, 3, "B"]},
         "att": {"1:3": 501, "2:3": 502},
         "sprint": {"n_runners": 500}}


def test_runner_terms_follow_the_definition():
    f = S.feature_row(_row(), BLOCK)
    assert f["R1"] == pytest.approx(0.30) and f["R2"] == 0.0 and f["R3"] == 0.0
    f = S.feature_row(_row(season="2023"), BLOCK)
    assert f["R3"] == pytest.approx(0.30)
    # off the leaderboard, no id, and a season with no block: R1 = R3 = 0, R2 = 1
    for r, blk in ((_row(on_first=999.0), BLOCK), (_row(on_first=float("nan")), BLOCK),
                   (_row(), None)):
        f = S.feature_row(r, blk)
        assert (f["R1"], f["R2"], f["R3"]) == (0.0, 1.0, 0.0)


def test_runner_is_read_off_the_origin_base_of_the_target():
    f = S.feature_row(_row(target="3B", on_first=float("nan"), on_second=101.0,
                           base_before=2), BLOCK)
    assert f["_runner_id"] == 101 and f["R2"] == 0.0
    f = S.feature_row(_row(target="HOME", on_first=101.0, on_third=float("nan"),
                           base_before=5), BLOCK)
    assert f["_runner_id"] is None and f["R2"] == 1.0


def test_catcher_terms_and_their_blanks():
    f = S.feature_row(_row(), BLOCK)
    assert f["C1"] == pytest.approx(-0.05) and f["C2"] == 0.0
    f = S.feature_row(_row(game_pk=2), BLOCK)          # catcher on file, no pop time
    assert (f["C1"], f["C2"]) == (0.0, 1.0)
    f = S.feature_row(_row(game_pk=9), BLOCK)          # no catcher named
    assert (f["C1"], f["C2"]) == (0.0, 1.0) and f["_catcher_id"] is None


def test_pitcher_and_state_terms():
    f = S.feature_row(_row(pitch_hand="L"), BLOCK)
    assert (f["P1"], f["P2"]) == (1.0, 1.0)
    f = S.feature_row(_row(pitch_hand="L", target="3B", on_second=101.0, base_before=2), BLOCK)
    assert (f["P1"], f["P2"]) == (1.0, 0.0)
    f = S.feature_row(_row(pitch_hand=None), BLOCK)
    assert (f["P1"], f["P2"]) == (0.0, 0.0) and not f["_hand_known"]
    assert S.feature_row(_row(outs_before=1), BLOCK)["S1"] == 1.0
    assert S.feature_row(_row(outs_before=0), BLOCK)["S1"] == 0.0
    # another runner on: first and third with the runner stealing second
    assert S.feature_row(_row(base_before=5), BLOCK)["S2"] == 1.0
    assert S.feature_row(_row(base_before=1), BLOCK)["S2"] == 0.0
    # score: home minus away, negated in the top half, clipped to [-4, 4] / 4
    assert S.feature_row(_row(score_diff=2.0, half="bottom"), BLOCK)["S3"] == 0.5
    assert S.feature_row(_row(score_diff=2.0, half="top"), BLOCK)["S3"] == -0.5
    assert S.feature_row(_row(score_diff=-9.0, half="bottom"), BLOCK)["S3"] == -1.0
    assert S.feature_row(_row(score_diff=float("nan")), BLOCK)["S3"] == 0.0
    assert S.feature_row(_row(inning=7, score_diff=-1.0), BLOCK)["S4"] == 1.0
    assert S.feature_row(_row(inning=7, score_diff=2.0), BLOCK)["S4"] == 0.0
    assert S.feature_row(_row(inning=6, score_diff=0.0), BLOCK)["S4"] == 0.0
    assert S.feature_row(_row(inning=8, score_diff=float("nan")), BLOCK)["S4"] == 0.0


def test_zero_coefficients_are_the_incumbent():
    lp = np.array([0.6, 0.75, 0.9])
    X = np.ones((3, len(S.FEATURES)))
    p = S.predict(np.zeros(len(S.FEATURES)), X, S.logit(lp))
    assert np.allclose(p, lp, atol=1e-12)


def test_lambda_tie_goes_to_the_larger_lambda():
    y = np.array([1.0, 0.0, 1.0, 1.0])
    X = np.zeros((4, 2))
    o = S.logit(np.full(4, 0.7))
    ch = S.choose_lambda(X, y, o, X, y, o)
    assert ch["lambda"] == max(S.LAMBDA_GRID)


def test_fit_recovers_a_planted_coefficient():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(20000, 1))
    o = np.full(20000, 0.5)
    y = (rng.random(20000) < S.sigmoid(o + 0.8 * x[:, 0])).astype(float)
    f = S.fit(x, y, o, 0.0001)
    assert f["converged"] and f["beta"][0] == pytest.approx(0.8, abs=0.06)


def test_bootstrap_resamples_games_and_is_seeded():
    games = np.repeat(np.arange(40), 3)
    a = np.where(games % 2 == 0, 1.0, -0.2)
    one = S.game_bootstrap(games, {"x": a, "y": -a}, b=300, seed=5)
    two = S.game_bootstrap(games, {"x": a, "y": -a}, b=300, seed=5)
    assert one == two
    assert one["_games"] == 40
    assert one["x"]["point"] == pytest.approx(a.mean())
    # the same draws: y is -x on every draw, so its interval mirrors x's
    assert one["y"]["interval_90"][0] == pytest.approx(-one["x"]["interval_90"][1])
    pos = S.game_bootstrap(games, {"z": np.full(120, 0.01)}, b=200, seed=1)
    assert pos["z"]["resolves"] and pos["z"]["lower_95_one_sided"] == pytest.approx(0.01)


def test_verdict_needs_all_four():
    ok = {"point": 1, "lower_95_one_sided": 0.1, "interval_90": [0.1, 1], "resolves": True}
    no = dict(ok, resolves=False)
    assert S.verdict(2000, {"dLL": ok, "dBrier": ok, "dLL_runner": ok})["result"] == "PASS"
    for k in ("dLL", "dBrier", "dLL_runner"):
        b = {"dLL": ok, "dBrier": ok, "dLL_runner": ok, k: no}
        assert S.verdict(2000, b)["result"] == "NULL"
    assert S.verdict(999, {"dLL": ok, "dBrier": ok, "dLL_runner": ok})["result"] == "NULL"


def test_split_is_additive_and_dv_is_untouched():
    df, ctx = S.fixtures()
    sc = S.frame([S.SCORE_SEASON], ctx, attempts_df=df)
    dv_before = sc["dv"].to_numpy().copy()
    swing = (sc["we_success"] - sc["we_fail"]).to_numpy()
    p_run = S.predict([0.4, -0.1, 0.2], S.matrix(sc, S.RUNNER_TERMS), S.logit(sc["league_p"]))
    er_r, er_o = S.split_er(swing, p_run, sc["league_p"], sc["er"])
    assert np.allclose(er_r + er_o, sc["er"].to_numpy(), atol=1e-15)
    assert np.allclose(sc["dv"] + er_r + er_o, sc["realized_delta"], atol=1e-12)
    assert np.array_equal(sc["dv"].to_numpy(), dv_before)


def test_dry_run_freezes_before_it_reads_the_score_frame(tmp_path):
    df, ctx = S.fixtures()
    fit_df = S.frame(S.FIT_SEASONS, ctx, attempts_df=df)
    tune_df = S.frame([S.TUNE_SEASON], ctx, attempts_df=df)
    seen = {}

    def load():
        seen["frozen_on_disk"] = (tmp_path / S.FROZEN).exists()
        return S.frame([S.SCORE_SEASON], ctx, attempts_df=df)

    out = S.run_read(ctx=ctx, fit_df=fit_df, tune_df=tune_df, load_score=load,
                     out_dir=tmp_path, eval_out=tmp_path / "e.json",
                     meta={"kind": "test"}, say=lambda *_: None)
    assert seen["frozen_on_disk"]
    assert out["verdict"] in ("PASS", "NULL") and out["served"] is False
    disk = json.loads((tmp_path / "e.json").read_text(encoding="utf-8"))
    assert disk["conditions"] == out["conditions"]
    assert set(disk["score"]["bootstrap"]) == {"dLL", "dBrier", "dLL_runner"}
    assert disk["score"]["er_split_identity_max_abs_error"] < 1e-12
    assert len(disk["score"]["calibration_by_decile_of_p"]) == 10
    # the fixture blanks reach the frame: a season with no block, missing ids and hands
    cov = disk["frozen_fit"]["frames"]["fit"]["coverage"]
    assert cov["runner_listed"] < cov["attempts"] and cov["pitch_hand_known"] < cov["attempts"]


def test_an_empty_score_frame_is_a_null_on_condition_one(tmp_path):
    df, ctx = S.fixtures()
    fit_df = S.frame(S.FIT_SEASONS, ctx, attempts_df=df)
    tune_df = S.frame([S.TUNE_SEASON], ctx, attempts_df=df)
    empty = df[df["season"] == "1900"]
    out = S.run_read(ctx=ctx, fit_df=fit_df, tune_df=tune_df,
                     load_score=lambda: S.frame([S.SCORE_SEASON], ctx, attempts_df=empty),
                     out_dir=tmp_path, eval_out=tmp_path / "e.json",
                     meta={"kind": "test"}, say=lambda *_: None)
    assert out["verdict"] == "NULL"
    assert "1_n_scored_at_least_1000" in out["failed_conditions"]


def test_the_read_refuses_a_second_run(tmp_path, monkeypatch):
    ev = tmp_path / "steal_runner_split_eval.json"
    ev.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(S, "EVAL_OUT", ev)
    monkeypatch.setattr(S, "LOOK_DIR", tmp_path / "look")
    with pytest.raises(SystemExit):
        S.look(owner_waived=True)


def test_no_served_path_reads_the_lab():
    names = ("mgmt_steal_runner_split", "ER_runner", "er_runner", "steal_runner_split_eval")
    served = [*ROOT.glob("management.py"), *ROOT.glob("mgmt_*.py"), *ROOT.glob("betting*.py"),
              ROOT / "build_site.py", *ROOT.glob("assets/*.js")]
    for p in served:
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        for n in names:
            assert n not in txt, (p.name, n)


def test_constants_are_the_registered_ones():
    assert S.FIT_SEASONS == ("2018", "2019", "2021", "2022", "2023")
    assert (S.TUNE_SEASON, S.SCORE_SEASON) == ("2024", "2025")
    assert S.LAMBDA_GRID == (0.0001, 0.001, 0.01, 0.1, 1.0)
    assert (S.B, S.SEED, S.MIN_SCORED, S.CLIP, S.TOL) == (2000, 20261020, 1000, 1e-6, 1e-10)
    assert (S.POP_CENTRE, S.PCT_CENTRE, S.MARGIN_CLIP, S.RULES_SEASON, S.LATE_INNING) == (
        2.00, 0.5, 4, 2023, 7)
    assert S.FEATURES == ("R1", "R2", "R3", "C1", "C2", "P1", "P2", "S1", "S2", "S3", "S4")
    assert not math.isnan(S.logit([0.0])[0])
