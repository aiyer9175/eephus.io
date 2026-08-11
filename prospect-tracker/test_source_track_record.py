"""Tests for source_backtest.py — the source-vs-source predictive track record."""
import pytest

import source_backtest as sb


@pytest.fixture(scope="module")
def backtest():
    """One live recompute for the whole module. run_source_backtest re-reads the
    140MB universe and the eFV OOS grades, so calling it per test would dominate
    the suite's runtime."""
    return sb.run_source_backtest(write=False)


class TestStatsHelpers:
    def test_spearman_monotonic(self):
        x = [1, 2, 3, 4, 5, 6]
        y = [2, 4, 5, 9, 11, 20]            # strictly increasing → rho ~ 1
        assert sb._spearman(x, y) > 0.99

    def test_spearman_inverse(self):
        assert sb._spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) < -0.99

    def test_spearman_handles_ties(self):
        rho = sb._spearman([1, 1, 2, 2, 3, 3], [1, 1, 2, 2, 3, 3])
        assert rho is not None and rho > 0.99

    def test_auc_perfect_separation(self):
        scores = [10, 20, 30, 40]
        labels = [False, False, True, True]
        assert sb._auc(scores, labels) == 1.0

    def test_auc_no_skill_is_half(self):
        # Symmetric: positives at the extremes, negatives in the middle →
        # exactly half the pos/neg pairs are correctly ordered.
        scores = [1, 2, 3, 4]
        labels = [True, False, False, True]
        assert sb._auc(scores, labels) == 0.5

    def test_tier_boundaries(self):
        assert sb._tier_of(62) == "60+"
        assert sb._tier_of(60) == "60+"
        assert sb._tier_of(55) == "55"
        assert sb._tier_of(50) == "50"
        assert sb._tier_of(44) == "<45"


class TestTierTable:
    def _mk(self, fv, war, debuted=True, wpy=None):
        return {"fv": fv, "outcome": {"war": war, "debuted": debuted, "war_per_yr": wpy,
                                      "contributor": war >= 3, "star": war >= 10,
                                      "regular_pace": (wpy is not None and wpy >= 1.5),
                                      "allstar_pace": (wpy is not None and wpy >= 3.0)}}

    def test_aggregates(self):
        rows = [self._mk(60, 12), self._mk(61, 4), self._mk(50, 0, debuted=False)]
        tbl = {t["tier"]: t for t in sb._tier_table(rows)}
        assert tbl["60+"]["n"] == 2
        assert tbl["60+"]["star_rate"] == 0.5          # one of two ≥ 10
        assert tbl["60+"]["contributor_rate"] == 1.0   # both ≥ 3
        assert tbl["50"]["debut_rate"] == 0.0


class TestArchetype:
    """F6 (2026-08-09). `_PITCH_POS` was written against the FanGraphs / MLB Pipeline
    role vocabulary (SIRP / MIRP) and never learned the closer token Baseball America
    types: prospects.db carries 22 snapshot rows at position CP, and 23 rows of the
    pooled common set (6 of the deduped per-player set) were archetyped as BATS."""

    def _p(self, pos, method="draft", year=2021, birth="2000-05-01"):
        return {"position": pos, "birth_date": birth,
                "acquisition": {"method": method, "year": year}}

    def test_closer_tokens_are_arms(self):
        assert "CP" in sb._PITCH_POS
        assert "CL" in sb._PITCH_POS
        assert sb._archetype(self._p("CP")).endswith("_arm")
        assert sb._archetype(self._p("CL")).endswith("_arm")

    def test_catcher_is_still_a_bat(self):
        # The closer tokens must not drag the catcher token in behind them.
        assert "C" not in sb._PITCH_POS
        assert sb._archetype(self._p("C")).endswith("_bat")

    def test_two_way_is_excluded_not_guessed(self):
        # A two-way player is a member of BOTH sides of a bat/arm split, so any
        # assignment is a coin flip a reader would read as a measurement.
        assert sb._archetype(self._p("TWP")) is None

    def test_four_corners_stays_a_bat(self):
        assert sb._archetype(self._p("4C")).endswith("_bat")

    def test_side_fix_does_not_touch_the_hs_college_split(self):
        assert sb._archetype(self._p("CP", year=2018, birth="2000-05-01")) == "hs_arm"
        assert sb._archetype(self._p("CP", year=2021, birth="2000-05-01")) == "college_arm"


class TestConsensusVsInputsGate:
    """F2 (2026-08-09). `consensus_wins` was a bare `cons >= best_input`, so the
    surface rendered "the blend wins" on both legs. Measured on the shipped pooled
    common set (cluster bootstrap by player, B=2000): the AUC delta is +0.0116
    against a 0.0078 floor and IS a result, the Spearman delta is +0.0015 against a
    0.0121 floor and is NOT. These assert the PROPERTY on constructed inputs, so they
    keep holding when the vintage moves the numbers."""

    def _pooled(self, metric, consensus, best_input):
        srcs = list(sb.SCORED_SOURCES)
        pooled = {sb.CONSENSUS_KEY: {metric: consensus}, srcs[0]: {metric: best_input}}
        for s in srcs[1:]:
            pooled[s] = {metric: best_input - 0.05}   # never the argmax
        return pooled

    def test_both_legs_carry_a_floor(self):
        for m in ("spearman", "auc"):
            assert sb.CONSENSUS_VS_INPUTS_MDE95[m] > 0

    def test_exact_tie_is_not_a_win(self):
        for m in ("spearman", "auc"):
            r = sb._beats(self._pooled(m, 0.30, 0.30), m)
            assert r["delta"] == 0
            assert r["resolvable"] is False
            assert r["consensus_wins"] is False

    def test_positive_but_unresolvable_is_not_a_win(self):
        # The exact defect: the blend IS ahead, by less than the backtest can
        # resolve, and the old `>=` published that as a win.
        for m in ("spearman", "auc"):
            mde = sb.CONSENSUS_VS_INPUTS_MDE95[m]
            r = sb._beats(self._pooled(m, 0.30 + mde / 2, 0.30), m)
            assert r["delta"] > 0
            assert r["resolvable"] is False
            assert r["consensus_wins"] is False
            assert r["verdict"] == "not resolvable at this power"

    def test_resolvable_lead_is_a_win(self):
        for m in ("spearman", "auc"):
            mde = sb.CONSENSUS_VS_INPUTS_MDE95[m]
            r = sb._beats(self._pooled(m, 0.30 + mde * 2, 0.30), m)
            assert r["resolvable"] is True
            assert r["consensus_wins"] is True
            assert r["verdict"] == "the blend wins"

    def test_resolvable_deficit_reads_as_a_loss(self):
        for m in ("spearman", "auc"):
            mde = sb.CONSENSUS_VS_INPUTS_MDE95[m]
            r = sb._beats(self._pooled(m, 0.30 - mde * 2, 0.30), m)
            assert r["consensus_wins"] is False
            assert r["verdict"] == "the best input wins"

    def test_missing_leg_claims_nothing(self):
        pooled = {s: {"spearman": None} for s in sb.SCORED_SOURCES}
        pooled[sb.CONSENSUS_KEY] = {"spearman": 0.30}
        r = sb._beats(pooled, "spearman")
        assert r["delta"] is None
        assert r["consensus_wins"] is False


class TestEndToEnd:
    def test_runs_on_real_data(self, backtest):
        r = backtest
        # Resolved window present and conservative.
        assert r["window"]["years"], "expected at least one resolved base year"
        assert all((2026 - y) >= sb.MIN_LAG_YEARS for y in r["window"]["years"])
        assert "prospx_consensus" in r["raters"]
        # Cohort tiers should be (weakly) monotonic in mean WAR for the
        # consensus rater — higher FV tiers produce more, on resolved data.
        tiers = r["cohorts"]["prospx_consensus"]["tiers"]
        by = {t["tier"]: t["mean_war"] for t in tiers}
        assert by.get("60+", 0) > by.get("<45", 0)
        # Accuracy block well-formed.
        acc = r["accuracy"]
        assert acc["common_n"] > 0
        for rater in r["raters"]:
            assert "spearman" in acc["pooled"][rater]
            assert "auc" in acc["pooled"][rater]
        # Newer sources disclosed as unscored.
        assert "espn" in r["insufficient_history"]

    def test_every_rater_declares_the_protocol_behind_its_number(self, backtest):
        """F3. The per-source bars are scored IN SAMPLE on the common set and eFV
        enters with a forward-chained out-of-sample grade. The surface has to mark
        that off a FIELD: keying it off a hardcoded rater name breaks silently the
        day a second out-of-sample model joins the table."""
        acc = backtest["accuracy"]
        for block in ("pooled", "pooled_efv_common"):
            for rater, cell in (acc.get(block) or {}).items():
                assert cell["basis"] == sb._rater_basis(rater), (block, rater)
        assert acc["pooled"]["xfv"]["basis"] == sb.BASIS_OOS
        assert acc["pooled"][sb.CONSENSUS_KEY]["basis"] == sb.BASIS_IN_SAMPLE
        for row in acc["by_archetype"]:
            for block in ("raters", "raters_efv_common"):
                for rater, cell in (row.get(block) or {}).items():
                    assert cell["basis"] == sb._rater_basis(rater), (row["archetype"], rater)

    def test_published_consensus_verdict_never_outruns_its_floor(self, backtest):
        """Whatever the vintage says, a published win has to be positive AND bigger
        than the measured floor. Asserts the invariant, not today's answer."""
        cvi = backtest["accuracy"]["consensus_vs_inputs"]
        for metric in ("spearman", "auc"):
            leg = cvi[metric]
            assert leg["mde95"] == sb.CONSENSUS_VS_INPUTS_MDE95[metric]
            if leg["consensus_wins"]:
                assert leg["delta"] > 0 and abs(leg["delta"]) >= leg["mde95"]
            if leg["delta"] is not None:
                assert leg["resolvable"] == (abs(leg["delta"]) >= leg["mde95"])
