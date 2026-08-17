"""Identity-reconstruction audit hook (docs/STATISTICAL_GOVERNANCE.md, Part AL).

This module provides generic, domain-agnostic building blocks. It does NOT
run any audit against a real pitch-quality model -- no such model exists
yet (registry/claims/C-001.yaml) and running this against one is explicitly
out of scope for Program 0. A future Stuff Research Program applies these
functions with `group_col="pitcher_id"` and a real feature/score frame; this
audit is mandatory there, not optional (see docs/CERTIFICATION_STANDARD.md).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import cross_val_score
from sklearn.ensemble import RandomForestClassifier


@dataclass
class VarianceDecomposition:
    within_group_variance: float
    between_group_variance: float
    total_variance: float

    @property
    def intraclass_correlation(self) -> float:
        """Fraction of total variance explained by group membership (ICC-like).

        A high value for value_col="score", group_col="pitcher_id" is a
        warning sign that a score varies mostly *between* pitchers rather
        than *within* a pitcher's own pitches -- consistent with (but not
        proof of) identity reconstruction rather than pitch-level signal.
        """
        if self.total_variance == 0:
            return 0.0
        return self.between_group_variance / self.total_variance


def variance_decomposition(df: pd.DataFrame, group_col: str, value_col: str) -> VarianceDecomposition:
    grand_mean = df[value_col].mean()
    group_means = df.groupby(group_col)[value_col].transform("mean")
    within = float(((df[value_col] - group_means) ** 2).mean())
    between = float(((group_means - grand_mean) ** 2).mean())
    total = float(((df[value_col] - grand_mean) ** 2).mean())
    return VarianceDecomposition(within, between, total)


def predict_group_from_features(
    features: pd.DataFrame, group_labels: pd.Series, seed: int, cv: int = 5
) -> float:
    """Cross-validated accuracy of predicting `group_labels` (e.g. pitcher_id) from `features`.

    High accuracy here, for a model whose features were meant to describe
    pitch quality rather than pitcher identity, is exactly the finding this
    audit exists to surface. Returns mean CV accuracy in [0, 1]; compare
    against 1/n_groups (chance) explicitly rather than judging the raw
    number alone.
    """
    clf = RandomForestClassifier(random_state=seed, n_estimators=100)
    scores = cross_val_score(clf, features, group_labels, cv=cv)
    return float(np.mean(scores))


def permutation_test_group_labels(
    features: pd.DataFrame,
    group_labels: pd.Series,
    seed: int,
    n_permutations: int = 20,
    cv: int = 3,
) -> dict[str, float]:
    """Compare real accuracy against accuracy under `n_permutations` shuffles of group_labels.

    If shuffled-label accuracy is close to real accuracy, whatever the model
    is finding isn't specific to true group identity -- likely a modeling
    artifact rather than genuine identity reconstruction (or the real
    accuracy itself is uninformative).
    """
    rng = np.random.default_rng(seed)
    real_accuracy = predict_group_from_features(features, group_labels, seed, cv)
    shuffled_accuracies = []
    labels_array = group_labels.to_numpy()
    for _ in range(n_permutations):
        shuffled = pd.Series(rng.permutation(labels_array), index=group_labels.index)
        shuffled_accuracies.append(
            predict_group_from_features(features, shuffled, seed, cv)
        )
    return {
        "real_accuracy": real_accuracy,
        "shuffled_accuracy_mean": float(np.mean(shuffled_accuracies)),
        "shuffled_accuracy_max": float(np.max(shuffled_accuracies)),
    }


def known_vs_unseen_group_gap(
    metric_known: float, metric_unseen: float
) -> dict[str, float]:
    """Simple gap report between a metric computed on known-group vs. unseen-group holdouts.

    A large gap (known >> unseen) is evidence a result depends on having
    seen the specific group (e.g. pitcher) before, not on generalizable
    signal -- see the interpretation ladder in docs/STATISTICAL_GOVERNANCE.md.
    """
    return {
        "metric_known": metric_known,
        "metric_unseen": metric_unseen,
        "gap": metric_known - metric_unseen,
    }
