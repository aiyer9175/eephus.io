"""Generic, domain-agnostic tests of the identity-reconstruction audit hook (Part AL).

Does not audit any real pitch-quality model -- none exists yet. These tests
just prove the hook's building blocks behave correctly, using synthetic
group labels.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from eephus_research.diagnostics.identity_audit import (
    known_vs_unseen_group_gap,
    permutation_test_group_labels,
    predict_group_from_features,
    variance_decomposition,
)


def test_variance_decomposition_all_between_group_when_no_within_group_noise():
    df = pd.DataFrame({"group": [1, 1, 2, 2, 3, 3], "value": [10, 10, 20, 20, 30, 30]})
    decomp = variance_decomposition(df, "group", "value")
    assert decomp.within_group_variance == 0
    assert decomp.intraclass_correlation > 0.99


def test_variance_decomposition_mostly_within_group_when_groups_share_a_mean():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"group": np.repeat([1, 2, 3], 100), "value": rng.normal(0, 1, 300)})
    decomp = variance_decomposition(df, "group", "value")
    assert decomp.intraclass_correlation < 0.1


def test_predict_group_from_features_beats_chance_when_features_are_informative():
    rng = np.random.default_rng(0)
    n_per_group = 30
    groups = np.repeat(["a", "b", "c"], n_per_group)
    # feature is highly informative of group
    feature = np.where(groups == "a", rng.normal(0, 0.1, len(groups)),
              np.where(groups == "b", rng.normal(5, 0.1, len(groups)), rng.normal(10, 0.1, len(groups))))
    features = pd.DataFrame({"f": feature})
    labels = pd.Series(groups)
    accuracy = predict_group_from_features(features, labels, seed=1, cv=3)
    assert accuracy > 0.9  # well above chance (1/3)


def test_predict_group_from_features_near_chance_when_uninformative():
    rng = np.random.default_rng(0)
    n_per_group = 30
    groups = np.repeat(["a", "b", "c"], n_per_group)
    features = pd.DataFrame({"f": rng.normal(0, 1, len(groups))})  # pure noise, unrelated to group
    labels = pd.Series(groups)
    accuracy = predict_group_from_features(features, labels, seed=1, cv=3)
    assert accuracy < 0.6  # not perfectly at 1/3 due to noise, but well below a strong classifier


def test_permutation_test_shows_real_beats_shuffled_when_signal_is_real():
    rng = np.random.default_rng(0)
    groups = np.repeat(["a", "b"], 40)
    feature = np.where(groups == "a", rng.normal(0, 0.1, 80), rng.normal(5, 0.1, 80))
    features = pd.DataFrame({"f": feature})
    labels = pd.Series(groups)
    result = permutation_test_group_labels(features, labels, seed=1, n_permutations=5, cv=3)
    assert result["real_accuracy"] > result["shuffled_accuracy_mean"]


def test_known_vs_unseen_group_gap_reports_positive_gap_when_overfit():
    result = known_vs_unseen_group_gap(metric_known=0.9, metric_unseen=0.5)
    assert abs(result["gap"] - 0.4) < 1e-9
