# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The run distribution, the NB2 machinery, and the gate that kept it out.

THE DEFECT THESE PIN (2026-08-09, measured on all 1,766 cached completed games,
3,532 scoring-side rows). Poisson asserts var = mean. Team runs come in at mean
4.4853 and var 10.4889, so var/mean = 2.3385. The margin is worse because the
error compounds over two sides: observed variance 21.3057 against a
Skellam-implied 8.9714, a ratio of 2.3748. P(|margin| >= 5) is 0.2990 in the
games and 0.1390 in the model that priced them. The module's caveat called this
"probabilities sit too close to the middle" and "the softest of the three
markets", which understates a 2.15x tail error by roughly 5x.

It is not lambda heterogeneity: var(lam) is 0.3755 of the 6.0036 of excess
variance, 6.25%, so 93.75% is within-game clumping.

WHAT SHIPPED, AND WHAT DID NOT. A one-parameter NB2 estimator (var = lam +
alpha*lam^2, pure Python, no gamma function, no scipy) is IN the module and is
NOT served. It was pre-registered against a four-criterion held-out gate
(docs/diamond-betting.md section 11a) and the verdict is INDETERMINATE: under
the amended criterion 2 (both runline sides) it passes at split quantiles 0.6
and 0.7 and misses the t bar at 0.8, and the declared rule is every quantile or
nothing. The mechanism behind the wobble is that NB2 repairs the tail,
P(|margin| >= 5) 0.1390 -> 0.2897 against 0.2986 observed, and OVERCORRECTS the
middle, P(|margin| = 1) 0.2503 -> 0.1917 against 0.2721 observed. Two
independent count distributions cannot represent the walk-off structure that
concentrates real games at one run, and the runline is priced on exactly that
band.

So these tests pin three separate things:

  1. The NB2 primitive is CORRECT (mean, variance, mass, recurrence).
  2. `r=None` recovers Poisson BIT FOR BIT, which is the only reason the gate
     was a true A/B on one flag and the only reason the verdict changed no
     served price by a single bit. The NB branch, separately, is a PROPER
     distribution: it carries its own tail rather than dropping it onto the
     Under or top-coding it into a cell that then means something else.
  3. The gate's shape and its verdict are pinned, including the
     `SERVE_RUN_DISPERSION` flag and the sweep the flag is set from. A future
     edit that flips dispersion on without re-running the sweep fails here.

Fast: everything below runs on constructed lambdas. Nothing reads the game
cache, nothing writes, and no test needs a leaderboard.
"""
import json
import math
from pathlib import Path

import pytest

import betting_model as bm

DATA = Path(__file__).parent / "data"


# ---------------------------------------------------------------------------
# 1. the NB2 primitive
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("lam", [1.5, 4.5, 9.5])
@pytest.mark.parametrize("alpha", [0.1, 0.28425, 1.0])
def test_nb2_pmf_has_the_mean_and_variance_it_claims(lam, alpha):
    """NB2 is parameterized by the MEAN. A version that drifts on either moment
    would still look like a plausible distribution and would silently reprice
    every market, so both are checked to 1e-9 on a support long enough to hold
    the tail (k_max 400, well past the 1e-12 point at lam 9.5)."""
    r = 1.0 / alpha
    p = bm._nb2_pmf(lam, r, 400)
    assert sum(p) == pytest.approx(1.0, abs=1e-12)
    mean = sum(k * v for k, v in enumerate(p))
    var = sum((k - mean) ** 2 * v for k, v in enumerate(p))
    assert mean == pytest.approx(lam, abs=1e-9)
    assert var == pytest.approx(lam + alpha * lam * lam, abs=1e-9)


def test_nb2_recurrence_matches_the_gamma_form():
    """The shipped recurrence is the gamma expression with the ratio telescoped,
    and that is an identity, not an approximation. `math.lgamma` appears HERE
    and nowhere in betting_model: the serving path may not grow a gamma
    dependency, which is the same invariant that keeps scipy out of it."""
    lam, r = 4.7, 1.0 / 0.28425
    p = bm._nb2_pmf(lam, r, 60)
    for k in range(0, 61):
        want = math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                        + r * math.log(r / (r + lam)) + k * math.log(lam / (r + lam)))
        assert p[k] == pytest.approx(want, rel=1e-10, abs=1e-300)


def test_nb2_converges_to_poisson_as_dispersion_vanishes():
    """alpha -> 0 is the Poisson limit. This is a property check, not the switch:
    the module switches on `r is None` precisely because a numerical limit is
    never bit-identical, and an A/B that moved the incumbent by 1e-9 would not
    be an A/B."""
    lam = 4.5
    pois = bm._poisson_pmf(lam, 40)
    near = bm._nb2_pmf(lam, 1.0 / 1e-7, 40)
    assert max(abs(a - b) for a, b in zip(pois, near)) < 1e-6
    assert bm._nb2_pmf(lam, 1.0 / 1e-7, 40) != pois


def test_alpha_to_r_treats_missing_and_non_positive_as_poisson():
    """Every "is dispersion on" decision goes through one helper, so a null in a
    context file, a missing key and an explicit 0.0 cannot disagree."""
    assert bm._alpha_to_r(None) is None
    assert bm._alpha_to_r(0.0) is None
    assert bm._alpha_to_r(-0.5) is None
    assert bm._alpha_to_r("nonsense") is None
    assert bm._alpha_to_r(0.25) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# 2. r=None is Poisson, bit for bit
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("lams", [(4.5, 4.1), (2.0, 9.5), (5.123456, 3.987654),
                                  (1.5, 1.5), (9.5, 9.5)])
def test_r_none_reproduces_the_shipped_skellam_bit_for_bit(lams):
    """Not approx: EQUAL. The dispersion lane rewrote `margin_distribution` and
    `total_distribution` into wrappers over one joint pass, and if that rewrite
    moved any served probability by a single float the whole gate would have
    been comparing two models instead of two distributions."""
    lh, la = lams
    expect = {}
    ph, pa = bm._poisson_pmf(lh, 24), bm._poisson_pmf(la, 24)
    for i, p_i in enumerate(ph):
        if p_i < 1e-12:
            continue
        for j, p_j in enumerate(pa):
            if p_j < 1e-12:
                continue
            expect[i - j] = expect.get(i - j, 0.0) + p_i * p_j
    assert bm.margin_distribution(lh, la) == expect
    # The total keeps its CLOSED FORM under Poisson: the sum of two independent
    # Poissons is Poisson, and spending a grid on it would both cost time and
    # move the last bits.
    assert bm.total_distribution(lh, la) == bm._poisson_pmf(lh + la, 40)


def test_game_probabilities_defaults_to_poisson_when_no_alpha_is_served():
    """The served default. `run_alpha=None` reads the context file, which does
    not carry a positive `run_dispersion_alpha` because the gate did not clear,
    so the board prices exactly as it did before this lane existed."""
    teams = {"AAA": {"z_off": 0.4, "prevention_z": -0.2, "offense_plus": 104},
             "BBB": {"z_off": -0.3, "prevention_z": 0.1, "offense_plus": 96}}
    kw = dict(teams=teams, parks={"AAA": 1.0}, coeffs=dict(bm.LITERATURE_COEFFS),
              tie_home=0.5, home_adj=0.2, diff_shrink=0.8)
    served = bm.game_probabilities("AAA", "BBB", **kw)
    forced = bm.game_probabilities("AAA", "BBB", run_alpha=0.0, **kw)
    assert served is not None and forced is not None
    assert served["p_home"] == forced["p_home"]
    assert served["p_home_minus_1_5"] == forced["p_home_minus_1_5"]
    assert served["run_dispersion_alpha"] is None
    assert bm.run_dispersion_alpha() is None


# ---------------------------------------------------------------------------
# 3. the joint pass
# ---------------------------------------------------------------------------
def test_joint_margin_mass_is_conserved_under_dispersion():
    """The reason `_nb2_side_pmf` renormalizes. NB2's tail is geometric in
    lam/(r+lam) = 0.729 at the lam ceiling, not factorial, so truncating at the
    Poisson support of 24 discards 2.12e-02 of a side's mass against Poisson's
    2.09e-05. The caller computes p_away as 1 - p_home, so every unassigned unit
    silently becomes an away win. Leaked mass is a one-sided error; redistributed
    mass is not."""
    r = 1.0 / 0.28425
    for lh, la in ((4.5, 4.1), (9.5, 9.5), (1.5, 9.5)):
        dist, _ = bm._score_joint(lh, la, r)
        assert sum(dist.values()) == pytest.approx(1.0, abs=1e-9)


def test_joint_margin_mean_is_the_lambda_difference():
    """A distribution can conserve mass and still be shifted. E[margin] pins the
    location the moneyline is read off."""
    r = 1.0 / 0.28425
    for lh, la in ((4.5, 4.1), (6.0, 3.0), (3.0, 6.0)):
        dist, _ = bm._score_joint(lh, la, r)
        assert sum(d * p for d, p in dist.items()) == pytest.approx(lh - la, abs=5e-3)


def test_dispersion_fattens_the_tail_and_thins_the_one_run_band():
    """THE WHOLE FINDING, in one assertion. NB2 moves mass into |margin| >= 5,
    which is the repair the games asked for, AND out of |margin| = 1, which is
    the band the runline is priced on and where the games wanted MORE mass, not
    less. Both directions are pinned: a future correction that claims to fix
    dispersion must not quietly reintroduce the second half."""
    lh, la = 4.6, 4.4
    p_dist, _ = bm._score_joint(lh, la, None)
    n_dist, _ = bm._score_joint(lh, la, 1.0 / 0.28425)

    def band(d, pred):
        return sum(p for k, p in d.items() if pred(k))

    assert band(n_dist, lambda k: abs(k) >= 5) > band(p_dist, lambda k: abs(k) >= 5)
    assert band(n_dist, lambda k: abs(k) == 1) < band(p_dist, lambda k: abs(k) == 1)


def test_two_nb2_sides_do_not_sum_to_an_nb2_unless_the_means_agree():
    """Why the total lost its closed form and had to move onto the joint pass.

    Two NB2s add only when lam/(r+lam) matches, i.e. when the means match. On a
    support long enough that truncation is not in the way (120), the equal-mean
    identity holds to 4.6e-13 and the unequal-mean gap is 9.07e-03 - seven
    orders apart, and the second is the case every real game is in. Pricing the
    total as `_nb2_pmf(lam_h + lam_a, 2r)` would be wrong by a full point of
    probability at a realistic 7.5/1.5 split."""
    r = 1.0 / 0.28425
    closed = bm._nb2_pmf(9.0, 2.0 * r, 120)
    _, tot_eq = bm._score_joint(4.5, 4.5, r, 24, 120)
    assert max(abs(a - b) for a, b in zip(tot_eq, closed)) < 1e-11
    _, tot_ne = bm._score_joint(7.5, 1.5, r, 24, 120)
    assert max(abs(a - b) for a, b in zip(tot_ne, closed)) > 1e-3


def test_the_shipped_total_support_costs_five_orders_under_the_published_digit():
    """EVERY CELL OF THE NB TOTAL MEANS P(total == k), and the price of the
    per-side support of 40 is pinned as a number rather than an assurance.
    Against the exact equal-mean closed form the shipped cells are off by
    4.99e-09, which comes from `_nb2_side_pmf` renormalizing each side over
    [0, 40] and is five orders under the 5th decimal every published
    probability is rounded to.

    THIS IS WHAT RULES OUT TOP-CODING. Writing P(total >= 40) into the last cell
    also makes the array sum to 1, but it makes that cell mean something else,
    and it lands 4.98e-06 away from the closed form at these lambdas. The module
    carries the tail explicitly instead, so this check reaches every cell of the
    shipped support and not just the ones below the top."""
    r = 1.0 / 0.28425
    _, tot = bm._score_joint(4.5, 4.5, r)
    closed = bm._nb2_pmf(9.0, 2.0 * r, 40)
    assert len(tot) > 40, "the NB total must carry its tail, not truncate at 40"
    assert max(abs(a - b) for a, b in zip(tot, closed)) < 5e-8


def test_the_nb_total_is_a_proper_distribution_at_every_lambda_the_board_reaches():
    """THE LEAK THIS CLOSED. `total_side_probabilities` prices a half-point
    Under as `1 - p_over`, so any mass the total pmf fails to account for is
    handed to the Under for free. Dropping the joint cells above 40 left, at
    alpha 0.28425:

        lam 4.50/4.50   residual 4.98e-06
        lam 7.50/1.50   residual 3.02e-05
        lam 9.50/1.50   residual 2.44e-04
        lam 9.50/9.50   residual 1.55e-02

    1.55e-02 is a quarter of the 0.06 provisional edge floor. The NB branch now
    returns the full convolution support, so the residual is the loop's own
    1e-12 prune and nothing else."""
    r = 1.0 / 0.28425
    for lh, la in ((4.5, 4.5), (7.5, 1.5), (9.5, 1.5), (9.5, 9.5)):
        _, tot = bm._score_joint(lh, la, r)
        assert abs(1.0 - math.fsum(tot)) < 1e-11, (lh, la)
        # And the Under of a posted half point is now the honest complement.
        sides = bm.total_side_probabilities(tot, 8.5)
        assert sides["p_over"] + sides["p_under"] == pytest.approx(1.0, abs=1e-12)
        assert sides["p_under"] == pytest.approx(
            math.fsum(tot[:9]), abs=1e-11), (lh, la)


def test_the_poisson_total_keeps_its_own_truncation_on_purpose():
    """The Poisson branch is NOT repaired, and that is a decision rather than an
    oversight. Its truncated closed form is short 8.09e-06 at the lambda ceiling
    of 19.0 total and 6.11e-15 at the league-typical 9.0, and that mass still
    lands on a half-point Under. Both are under the 5th decimal every published
    probability is rounded to, and touching them would cost the bit-for-bit
    identity with the shipped Skellam, which is the only thing that makes the
    section 11 gate a true A/B on one flag. Pinned so the trade is explicit."""
    lo = 1.0 - math.fsum(bm.total_distribution(9.5, 9.5))
    hi = 1.0 - math.fsum(bm.total_distribution(4.5, 4.5))
    assert lo == pytest.approx(8.09e-06, rel=1e-2)
    assert hi < 1e-14
    assert lo < 1e-5, "a Poisson leak this side of the published digit stays"


def test_total_side_probabilities_still_pushes_and_still_conditions():
    """Phase 1's push semantics survive the rewrite. A whole number carries push
    mass and returns the no-push conditional pair; a half point cannot push and
    its two sides still sum to one."""
    r = 1.0 / 0.28425
    _, tot = bm._score_joint(4.6, 4.4, r)
    whole = bm.total_side_probabilities(tot, 9.0)
    assert whole["p_push"] > 0.0
    assert whole["p_over"] + whole["p_under"] == pytest.approx(1.0, abs=1e-9)
    half = bm.total_side_probabilities(tot, 8.5)
    assert half["p_push"] == 0.0
    assert half["p_over"] + half["p_under"] == pytest.approx(1.0, abs=1e-12)


def test_game_probabilities_keeps_the_total_sides_closure_under_dispersion():
    """The Phase 1 closure must keep working on the NB branch, because the
    export reaches for it by name and a None there would price no total at
    all."""
    teams = {"AAA": {"z_off": 0.2, "prevention_z": 0.0, "offense_plus": 102},
             "BBB": {"z_off": -0.1, "prevention_z": 0.0, "offense_plus": 99}}
    gp = bm.game_probabilities("AAA", "BBB", teams=teams, parks={"AAA": 1.0},
                               coeffs=dict(bm.LITERATURE_COEFFS), tie_home=0.5,
                               home_adj=0.2, diff_shrink=0.8, run_alpha=0.28425)
    assert gp is not None
    assert gp["run_dispersion_alpha"] == pytest.approx(0.28425)
    sides = gp["total_sides"](8.0)
    assert sides["p_push"] > 0.0
    assert sides["p_over"] + sides["p_under"] == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 4. the estimator
# ---------------------------------------------------------------------------
def test_fit_run_alpha_recovers_a_planted_dispersion():
    """The MLE must find a dispersion that is actually there. Rows are built by
    quantile inversion of the NB2 cdf at fixed probabilities, so there is no RNG
    stream, no seed to drift, and the same rows every run."""
    lam, alpha = 4.5, 0.30
    r = 1.0 / alpha
    pmf = bm._nb2_pmf(lam, r, 200)
    rows = []
    for i in range(1, 400):
        u, acc, k = i / 400.0, 0.0, 0
        for k, p in enumerate(pmf):
            acc += p
            if acc >= u:
                break
        rows.append((lam, k))
    got, ll_nb, ll_p = bm.fit_run_alpha(rows)
    assert got == pytest.approx(alpha, abs=0.06)
    assert ll_nb > ll_p


def test_fit_run_alpha_returns_none_on_equidispersed_rows():
    """A quantile-inverted POISSON sample has no excess variance, and the honest
    answer is None rather than a token 1e-4 that would switch dispersion on for
    a distribution that does not have any."""
    lam = 4.5
    pmf = bm._poisson_pmf(lam, 60)
    rows = []
    for i in range(1, 400):
        u, acc, k = i / 400.0, 0.0, 0
        for k, p in enumerate(pmf):
            acc += p
            if acc >= u:
                break
        rows.append((lam, k))
    got, _, _ = bm.fit_run_alpha(rows)
    assert got is None or got < 0.05


def test_fit_run_alpha_is_deterministic():
    """Golden section on a fixed interval. Two calls on the same rows return the
    same digits, or the gate is not reproducible."""
    rows = [(4.5, k % 11) for k in range(600)]
    assert bm.fit_run_alpha(rows) == bm.fit_run_alpha(rows)


def test_nb2_loglik_with_alpha_none_is_the_poisson_loglik():
    """One likelihood function, two branches, and the Poisson branch has to be
    the real Poisson likelihood or the +720 nat headline is measured against
    nothing."""
    rows = [(4.5, 3), (5.5, 7), (2.0, 0), (9.5, 12)]
    want = sum(-lam + k * math.log(lam) - math.lgamma(k + 1) for lam, k in rows)
    assert bm._nb2_loglik(rows, None) == pytest.approx(want, rel=1e-12)


# ---------------------------------------------------------------------------
# 5. the gate, and the flag it set
# ---------------------------------------------------------------------------
def test_dispersion_is_not_served_because_the_sweep_is_indeterminate():
    """THE TRIPWIRE, and the reason it names a SWEEP rather than a split.

    The pre-registered 0.7 split, scored under the amended criterion 2 (both
    runline sides), now PASSES all four criteria: runline +0.011738 at
    t = +2.799, total +0.010709 at t = +2.545, runs +0.2190 nats per row,
    moneyline lb95 -0.000383 against a -0.001 bar. It is still not served,
    because the verdict was never one split's to give. `dispersion_gate_
    sensitivity` runs 0.6, 0.7 and 0.8 and the amended criterion holds at
    t = 3.069 and t = 2.799 and then misses at t = 1.224, so the sweep returns
    `indeterminate` and `ship` False.

    Flipping this flag without re-running the SWEEP is the failure mode this
    test exists for. If a later lane gets `ship` True, it changes THIS assertion
    in the same commit that publishes the new `run_dispersion` block, and the
    two move together or not at all."""
    assert bm.SERVE_RUN_DISPERSION is False
    assert bm.run_dispersion_alpha() is None


def test_the_amendment_and_its_robustness_rule_are_pinned_constants():
    """The specification that decides the verdict cannot be a runtime argument
    somebody widens later. Both are module constants and both are pinned here:
    the estimand is BOTH runline sides, and the sweep is exactly 0.6/0.7/0.8.

    This matters because the choice is outcome-changing in both directions. The
    home-only reading fails at all three quantiles; the away-only reading passes
    at all three. Whichever one a later reader prefers, they have to argue for
    it in RUNLINE_SIDE_AMENDMENT and change it here."""
    assert bm.RUNLINE_SIDE_AMENDMENT == "both"
    assert bm.RUNLINE_SIDE_AMENDMENT in bm.RUNLINE_SIDES
    assert bm.DISPERSION_SPLIT_QUANTILES == (0.6, 0.7, 0.8)


def test_the_pre_registration_is_carried_in_code_and_names_all_four_criteria():
    """The doc can be edited after the fact. This string cannot be, without the
    diff showing up beside the artifact that quotes it. V1 is carried unedited
    beside the amendment, because an amendment that overwrites the text it
    amends is not an amendment."""
    c = bm.DISPERSION_GATE_CRITERIA
    for fragment in ("non-inferiority", "-0.001", "1.645", "log-likelihood",
                     "diff_shrink already", "BOTH SIDES", "AMENDED 2026-08-09"):
        assert fragment in c
    v1 = bm.DISPERSION_GATE_CRITERIA_V1
    assert "margin\n>= 2" in v1 or "margin >= 2" in v1
    assert "BOTH SIDES" not in v1


def test_eval_artifact_carries_the_dispersion_block_and_its_verdict():
    """The artifact requirement: a dispersion block INSIDE
    data/betting_model_eval.json, not a new eval file. Skipped on a checkout
    that has never run the backtest.

    `passed` and `verdict` are allowed to DISAGREE and currently do: `passed` is
    the pre-registered single split and is True, `verdict` comes from the sweep
    and is `indeterminate`. What may never disagree is `verdict`/`ship` against
    the served flag, and that is the assertion with teeth here."""
    path = DATA / "betting_model_eval.json"
    if not path.exists():
        pytest.skip("no betting_model_eval.json in this checkout")
    ev = json.loads(path.read_text(encoding="utf-8"))
    rd = ev.get("run_dispersion")
    if not rd or rd.get("status") != "ran":
        pytest.skip("dispersion gate has not run in this checkout")
    assert not (DATA / "betting_dispersion_eval.json").exists(), \
        "the dispersion result belongs inside betting_model_eval.json, not beside it"
    assert rd["served"] is bm.SERVE_RUN_DISPERSION
    assert rd["served_alpha"] == bm.run_dispersion_alpha()
    assert len(rd["checks"]) == 4
    # Criterion 2 is scored on the AMENDED estimand, and the block says so.
    assert rd["runline_side"] == bm.RUNLINE_SIDE_AMENDMENT
    rl = [c for c in rd["checks"] if c["criterion"].startswith("runline")]
    assert len(rl) == 1 and rl[0]["side"] == bm.RUNLINE_SIDE_AMENDMENT
    by = {c["criterion"].split(",")[0]: c for c in rd["checks"]}
    assert by["total (over 9.0)"]["pass"] is True
    # All three readings are published on every run, so the one the gate did not
    # headline is never hidden.
    assert set(rd["runline_by_side"]) == set(bm.RUNLINE_SIDES)
    assert rd["runline_by_side"]["home"]["passes_criterion_2"] is False
    # THE SWEEP IS THE VERDICT, and the served flag follows it.
    sens = rd["sensitivity"]
    assert sens["status"] == "ran"
    assert sens["quantiles"] == [0.6, 0.7, 0.8]
    assert sens["runline_side_shipped"] == bm.RUNLINE_SIDE_AMENDMENT
    assert len(sens["grid"]) == 3
    assert all(set(row["by_side"]) == set(bm.RUNLINE_SIDES) for row in sens["grid"])
    assert sens["verdict"] == rd["verdict"]
    assert sens["ship"] is bm.SERVE_RUN_DISPERSION
    # The two arms must be tuned SEPARATELY or the comparison is rigged. Under
    # Poisson the moneyline needed shrinking toward the middle (0.70); NB2 is
    # already wide enough that the fit wants to expand it past 1.0 (1.08).
    assert rd["poisson_arm"]["diff_shrink"] != rd["nb2_arm"]["diff_shrink"]
    assert rd["nb2_arm"]["alpha"] is not None


def test_a_served_alpha_would_have_to_move_the_runline():
    """Documents the size of what the gate refused, so nobody reads "not served"
    as "not material". On the shape of a typical board game the +1.5 dog side
    drops by about 5 points, which is comfortably larger than the 0.06
    provisional edge floor a published pick has to clear."""
    teams = {"AAA": {"z_off": 0.35, "prevention_z": -0.1, "offense_plus": 104},
             "BBB": {"z_off": -0.25, "prevention_z": 0.1, "offense_plus": 96}}
    kw = dict(teams=teams, parks={"AAA": 1.0}, coeffs=dict(bm.LITERATURE_COEFFS),
              tie_home=0.5, home_adj=0.22, diff_shrink=0.74)
    old = bm.game_probabilities("AAA", "BBB", run_alpha=0.0, **kw)
    new = bm.game_probabilities("AAA", "BBB", run_alpha=0.28425, **kw)
    drop = old["p_away_plus_1_5"] - new["p_away_plus_1_5"]
    assert drop > 0.02, "dispersion must move the dog side of the runline down"
