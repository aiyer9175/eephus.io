# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""B5 Platt calibration: the fit, the seam, the gate, and the tripwire.

WHAT SHIPPED AND WHAT DID NOT (2026-08-16). The map p' = sigmoid(a*logit(p)+b)
is IN betting_model and is NOT served: SERVE_PROB_CALIBRATION is False. The
gate it must clear was pre-registered in docs/diamond-betting.md section 11b
before the lab existed, and it has TWO arms, both required: the vintage arm
(three date-quantile splits, Brier superiority at t >= 1.645 AND log loss not
worse, all three or nothing) and the ledger arm, which activates only at 100
settled canonical moneyline games and held 49 when the gate was written. The
flag therefore cannot flip today whatever the vintage arm measures.

These tests pin four separate things:

  1. The FIT is correct: a known (a, b) is recovered EXACTLY from fractional
     targets, because the minimizer of expected log loss under fractional
     targets is the generating pair. A swapped (a, b), a broken logit, or a
     sign error all fail here, which is what makes this the mutation net.
  2. The SEAM is scoped: an explicit map moves the moneyline pair only. The
     runline, the total and the fair total price off the uncalibrated margin
     distribution, because those two markets belong to the dispersion gate.
  3. The GATE arithmetic is the pre-registered arithmetic, including the
     all-three-or-nothing arm rule and the ledger arm's hard floor.
  4. The TRIPWIRE: the serve flag is False, identity is actually served, and
     the persisted eval block agrees with the flag. Flipping the flag without
     the gate verdict supporting it fails here, in the same commit-unit
     discipline as SERVE_RUN_DISPERSION.

Fast: everything runs on constructed probabilities. Nothing reads the game
cache, nothing needs a leaderboard, nothing touches the network.
"""
import json
import math
from pathlib import Path

import pytest

import betting_model as bm

DATA = Path(__file__).parent / "data"

ORGS = ("NYM", "PHI", "ATL", "WSN")


def _true_platt(p: float, a: float, b: float) -> float:
    """The map computed INDEPENDENTLY of betting_model's helpers, from the
    formula. The recovery tests generate their targets through this, never
    through bm._logit / bm._sigmoid, so a mutation inside the module's own
    transform cannot silently distort the generator to match itself."""
    x = a * math.log(p / (1.0 - p)) + b
    return 1.0 / (1.0 + math.exp(-x))


def _teams():
    return bm._assemble_team_inputs(
        {"NYM": 108.0, "PHI": 104.0, "ATL": 99.0, "WSN": 93.0},
        {"NYM": 104.0, "PHI": 108.0, "ATL": 97.0, "WSN": 92.0},
        {"NYM": 103.0, "PHI": 99.0, "ATL": 106.0, "WSN": 94.0},
        {"NYM": 560.0, "PHI": 590.0, "ATL": 540.0, "WSN": 520.0},
        {"NYM": 380.0, "PHI": 350.0, "ATL": 400.0, "WSN": 410.0},
    )


# ===========================================================================
# 1. the fit recovers a known distortion, exactly
# ===========================================================================
def test_fit_recovers_a_known_slope_and_intercept_exactly():
    """Targets generated as y = sigmoid(a*logit(p) + b) make the MLE land on
    (a, b) exactly, not statistically: the minimizer of expected log loss
    under fractional targets IS the generating pair. Any confusion of the two
    parameters' roles (a on the intercept, b on the slope), any sign error,
    and any broken logit turns this exact recovery into a miss."""
    a_true, b_true = 1.7, -0.35
    ps = [0.05 + 0.9 * i / 60 for i in range(61)]
    ys = [_true_platt(p, a_true, b_true) for p in ps]
    ab = bm.fit_platt(ps, ys)
    assert ab is not None
    assert ab[0] == pytest.approx(a_true, abs=1e-6)
    assert ab[1] == pytest.approx(b_true, abs=1e-6)
    # And the recovered pair is NOT the swapped pair, which would also be the
    # in-band answer of an implementation that crossed the two gradients.
    assert abs(ab[0] - b_true) > 1.0 and abs(ab[1] - a_true) > 1.0


def test_fit_on_undistorted_data_is_the_identity():
    """a = 1, b = 0 in, (1, 0) out. This is the pre-registered expectation for
    the production fit too, since diff_shrink already absorbs the response
    scale in-sample; an identity here is the instrument agreeing with itself."""
    ps = [0.1 + 0.8 * i / 40 for i in range(41)]
    ab = bm.fit_platt(ps, [_true_platt(p, 1.0, 0.0) for p in ps])
    assert ab[0] == pytest.approx(1.0, abs=1e-6)
    assert ab[1] == pytest.approx(0.0, abs=1e-6)


def test_fit_recovers_a_shrink_from_binary_outcomes():
    """The realistic direction: the model says 0.9 and 0.1, the world comes
    back 0.65 and 0.35. Fitted on hard 0/1 outcomes the map must shrink
    (a < 1) and the calibrated probabilities must land near the observed
    rates. Deterministic construction, no RNG."""
    ps, ys = [], []
    for i in range(200):
        if i % 2 == 0:
            ps.append(0.9)
            ys.append(1 if (i // 2) % 20 < 13 else 0)     # 65% of the 0.9s win
        else:
            ps.append(0.1)
            ys.append(1 if (i // 2) % 20 < 7 else 0)      # 35% of the 0.1s win
    ab = bm.fit_platt(ps, ys)
    assert ab is not None and 0.0 < ab[0] < 1.0
    hi = bm.apply_platt(0.9, *ab)
    lo = bm.apply_platt(0.1, *ab)
    assert hi == pytest.approx(0.65, abs=0.02)
    assert lo == pytest.approx(0.35, abs=0.02)


def test_fit_refuses_degenerate_inputs():
    """No rows, one row, a constant-probability design (singular Hessian in
    the slope) and perfectly separable data (the MLE walks to infinity) all
    return None rather than a number that would then be served."""
    assert bm.fit_platt([], []) is None
    assert bm.fit_platt([0.6], [1]) is None
    # Perfectly separable: every high p won, every low p lost. The likelihood
    # has no finite maximizer and the fit must say so, not serve the iterate.
    ps = [0.7] * 30 + [0.3] * 30
    ys = [1] * 30 + [0] * 30
    assert bm.fit_platt(ps, ys) is None


def test_apply_platt_is_monotone_and_bounded():
    grid = [i / 100 for i in range(1, 100)]
    out = [bm.apply_platt(p, 1.4, 0.2) for p in grid]
    assert all(b > a for a, b in zip(out, out[1:]))
    assert all(0.0 < q < 1.0 for q in out)
    # Identity map really is the identity, inside the clip.
    assert bm.apply_platt(0.37, 1.0, 0.0) == pytest.approx(0.37, abs=1e-9)


# ===========================================================================
# 2. the seam: moneyline only, identity while unserved
# ===========================================================================
def test_an_explicit_map_moves_the_moneyline_and_nothing_else():
    teams = _teams()
    kw = dict(teams=teams, parks={}, tie_home=0.5, home_adj=0.0,
              diff_shrink=1.0, run_alpha=0.0)
    base = bm.game_probabilities("NYM", "WSN", **kw)
    cal = bm.game_probabilities("NYM", "WSN", platt_ab=(0.5, 0.0), **kw)
    assert cal["p_home"] != base["p_home"]
    assert cal["p_home"] + cal["p_away"] == pytest.approx(1.0, abs=1e-9)
    # The two dispersion-gated markets and the fair total do not move.
    for k in ("p_home_minus_1_5", "p_away_minus_1_5", "p_home_plus_1_5",
              "p_away_plus_1_5", "fair_total"):
        assert cal[k] == base[k], k
    assert cal["prob_calibration_ab"] == [0.5, 0.0]
    assert base["prob_calibration_ab"] is None


def test_unserved_means_identity_even_with_a_stray_context_key(tmp_path, monkeypatch):
    """While the flag is False a context file carrying a prob_calibration pair
    must NOT calibrate anything: served_platt checks the flag before it reads
    a byte, so an old or hand-edited artifact cannot switch the model on."""
    ctx = tmp_path / "betting_model_context.json"
    ctx.write_text(json.dumps({"prob_calibration": {"a": 0.5, "b": 0.4}}),
                   encoding="utf-8")
    monkeypatch.setattr(bm, "CONTEXT_PATH", ctx)
    assert bm.SERVE_PROB_CALIBRATION is False
    assert bm.served_platt() is None
    teams = _teams()
    kw = dict(teams=teams, parks={}, tie_home=0.5, home_adj=0.0,
              diff_shrink=1.0, run_alpha=0.0)
    a = bm.game_probabilities("NYM", "WSN", **kw)
    b = bm.game_probabilities("NYM", "WSN", platt_ab=None, **kw)
    assert a["p_home"] == b["p_home"]
    assert a["prob_calibration_ab"] is None


# ===========================================================================
# 3. the gate arithmetic (pre-registered, section 11b)
# ===========================================================================
def test_split_criteria_are_the_pre_registered_pair():
    """Criterion 1 is Brier superiority (delta > 0 AND t >= 1.645); criterion
    2 is log loss non-inferiority at the point estimate. Both deltas are
    identity minus Platt, so positive means the challenger is better."""
    ok = bm._platt_split_verdict({"delta": 0.004, "t": 3.2}, {"delta": 0.001})
    assert ok == {"brier_pass": True, "logloss_pass": True, "pass": True}
    # A positive delta at t below the bar is not a pass.
    assert bm._platt_split_verdict({"delta": 0.004, "t": 1.644},
                                   {"delta": 0.001})["pass"] is False
    # Brier win bought with a log loss loss is not a pass.
    assert bm._platt_split_verdict({"delta": 0.004, "t": 3.2},
                                   {"delta": -1e-6})["pass"] is False
    # Exactly-not-worse log loss passes criterion 2: it is non-inferiority.
    assert bm._platt_split_verdict({"delta": 0.004, "t": 3.2},
                                   {"delta": 0.0})["logloss_pass"] is True
    # Missing stats can never pass.
    assert bm._platt_split_verdict({}, {})["pass"] is False


def test_the_arm_rule_is_all_three_or_nothing():
    assert bm._arm_verdict([{"pass": True}] * 3) == "pass"
    assert bm._arm_verdict([{"pass": True}, {"pass": True},
                            {"pass": False}]) == "indeterminate"
    assert bm._arm_verdict([{"pass": False}] * 3) == "fail"
    assert bm._arm_verdict([]) == "not run"
    # A split that could not run (below floors, fit failed) carries pass False
    # and therefore blocks the arm: an unrunnable split cannot be skipped.
    assert bm._arm_verdict([{"pass": True}, {"status": "below floors",
                                             "pass": False},
                            {"pass": True}]) == "indeterminate"


def test_the_ledger_arm_cannot_count_below_its_floor():
    """49 settled canonical moneyline games (the live count when the gate was
    pre-registered) is below the 100 floor: the arm reports itself inactive,
    cannot pass, and blocks the ship whatever the vintage arm says."""
    rows = [{"model_prob": 0.55, "result": "won"}] * 49
    g = bm.prob_calibration_gate(games=[], teams={"x": 1}, parks={},
                                 starters={}, ledger_rows=rows)
    la = g["ledger_arm"]
    assert la["n_games"] == 49
    assert la["active"] is False
    assert la["pass"] is False
    assert la["verdict"] == "cannot count yet"
    assert g["ship"] is False
    assert g["served"] is bm.SERVE_PROB_CALIBRATION


def test_the_ledger_arm_runs_and_can_pass_at_n_100_plus():
    """The active path, on synthetic rows where the served probabilities are
    plainly overconfident (0.9/0.1 against 65%/35% realized): Platt must win
    both criteria at all three splits, so the ARM passes, and the overall gate
    still does not ship on one arm."""
    rows = []
    for i in range(400):
        if i % 2 == 0:
            rows.append({"model_prob": 0.9,
                         "result": "won" if (i // 2) % 20 < 13 else "lost"})
        else:
            rows.append({"model_prob": 0.1,
                         "result": "won" if (i // 2) % 20 < 7 else "lost"})
    g = bm.prob_calibration_gate(games=[], teams={"x": 1}, parks={},
                                 starters={}, ledger_rows=rows)
    la = g["ledger_arm"]
    assert la["active"] is True and la["status"] == "ran"
    assert len(la["grid"]) == 3
    for row in la["grid"]:
        assert row["pass"] is True, row
        assert row["a"] < 1.0
        assert row["brier_delta"]["t"] >= bm.Z_95_ONE_SIDED
    assert la["verdict"] == "pass" and la["pass"] is True
    # One green arm is recorded, never served: the vintage arm did not run
    # here (no games), so ship stays False and the verdict is not "pass".
    assert g["ship"] is False
    assert g["verdict"] != "pass"


def test_the_gate_criteria_string_is_pinned():
    """The pre-registration travels in code, like DISPERSION_GATE_CRITERIA,
    so the artifact cannot drift from the doc without the diff showing."""
    c = bm.PROB_CALIBRATION_GATE_CRITERIA
    for fragment in ("sigmoid(a*logit(p) + b)", "1.645", "ALL THREE",
                     "n >= 100", "BOTH arms", "moneyline only"):
        assert fragment in c
    assert bm.PROB_CALIBRATION_SPLIT_QUANTILES == (0.6, 0.7, 0.8)
    assert bm.PROB_CALIBRATION_LEDGER_MIN_GAMES == 100


# ===========================================================================
# 4. the serve tripwire (the three-move-together pattern)
# ===========================================================================
def test_serve_flag_is_off_and_moves_only_with_the_gate():
    """SERVE_PROB_CALIBRATION is False. The ledger arm held 49 of 100 settled
    canonical moneyline games when the gate was pre-registered, so the two-arm
    ship rule cannot be satisfied today whatever the vintage arm measured.

    Flipping this flag without that verdict is the failure mode this test
    exists for. If a later lane earns `ship` True on BOTH arms, it changes
    THIS assertion in the same commit that publishes the new prob_calibration
    block, and the three move together or not at all."""
    assert bm.SERVE_PROB_CALIBRATION is False
    assert bm.served_platt() is None


def test_eval_artifact_prob_calibration_block_agrees_with_the_flag():
    """The persisted block and the module flag may never disagree: `served`
    mirrors the flag, and a True flag with `ship` False in the artifact is the
    exact state this assertion exists to make loud. Skipped on a checkout that
    has never run the backtest."""
    path = DATA / "betting_model_eval.json"
    if not path.exists():
        pytest.skip("no betting_model_eval.json in this checkout")
    ev = json.loads(path.read_text(encoding="utf-8"))
    pc = ev.get("prob_calibration")
    if not pc:
        pytest.skip("prob_calibration block not in this artifact yet")
    assert pc["served"] is bm.SERVE_PROB_CALIBRATION
    if bm.SERVE_PROB_CALIBRATION:
        assert pc["ship"] is True, \
            "the flag is on without a shipping verdict in the artifact"
        assert pc["served_ab"]
    else:
        assert pc["served_ab"] is None
    # The two-arm structure is present and the ledger arm states its floor.
    assert pc["ledger_arm"]["need"] == bm.PROB_CALIBRATION_LEDGER_MIN_GAMES
    assert pc["vintage_arm"]["verdict"] in ("pass", "fail", "indeterminate",
                                            "not run")


def test_context_serves_null_while_the_flag_is_off():
    """The context file publishes the fitted pair as a measurement and serves
    null, the run_dispersion_alpha_fitted convention. Skipped where no context
    has been built."""
    path = DATA / "betting_model_context.json"
    if not path.exists():
        pytest.skip("no betting_model_context.json in this checkout")
    ctx = json.loads(path.read_text(encoding="utf-8"))
    if "prob_calibration" not in ctx:
        pytest.skip("context predates the prob_calibration key")
    if not bm.SERVE_PROB_CALIBRATION:
        assert ctx["prob_calibration"] is None
