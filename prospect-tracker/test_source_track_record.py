"""Tests for source_backtest.py — the source-vs-source predictive track record."""
import source_backtest as sb


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


class TestEndToEnd:
    def test_runs_on_real_data(self):
        r = sb.run_source_backtest(write=False)
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
