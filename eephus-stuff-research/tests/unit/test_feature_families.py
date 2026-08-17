from __future__ import annotations

import pytest

from eephus_research.validation.feature_families import (
    FEATURE_FAMILIES,
    UnknownFeatureFamilyError,
    ablate,
    tag_features,
)


def test_tag_features_groups_correctly():
    mapping = {"velocity": "VELOCITY", "spin_rate": "SPIN", "count_state": "COUNT"}
    grouped = tag_features(mapping)
    assert grouped["VELOCITY"] == ["velocity"]
    assert grouped["SPIN"] == ["spin_rate"]
    assert all(fam in grouped for fam in FEATURE_FAMILIES)


def test_tag_features_rejects_unknown_family():
    with pytest.raises(UnknownFeatureFamilyError):
        tag_features({"velocity": "MADE_UP_FAMILY"})


def test_ablate_removes_one_family():
    mapping = {"velocity": "VELOCITY", "spin_rate": "SPIN"}
    remaining = ablate(["velocity", "spin_rate"], mapping, drop_family="SPIN")
    assert remaining == ["velocity"]


def test_ablate_rejects_unknown_family():
    with pytest.raises(UnknownFeatureFamilyError):
        ablate(["velocity"], {"velocity": "VELOCITY"}, drop_family="NOT_A_FAMILY")
