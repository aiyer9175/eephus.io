# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Proprietary and confidential

"""Publication-contract and construction-invariant tests."""

import json
from pathlib import Path

import pandas as pd
import pytest

import contracts

DATA = Path.home() / "advancement_pace" / "data"


@pytest.fixture(scope="module")
def pub():
    return pd.read_parquet(DATA / "advancement_pace_public.parquet")


def test_public_contract_passes(pub):
    assert contracts.validate_public(pub) == []


def test_no_2020_rows(pub):
    assert (pub.season != 2020).all(), "2020 MiLB season was cancelled; no rows may exist"


def test_left_censored_excluded():
    full = pd.read_parquet(DATA / "scores_full.parquet")
    pub = pd.read_parquet(DATA / "advancement_pace_public.parquet")
    censored = set(full.loc[full.left_censored, "player_id"])
    assert not (set(pub.player_id) & censored), "2008-entry (left-censored) players published"


def test_score_centering(pub):
    assert abs(pub.advancement_pace_plus_internal.mean() - 100) < 1.0


def test_margins_flat(pub):
    for key in ["position_group", "entry_pathway", "starting_level"]:
        g = pub.groupby(key).advancement_pace_plus_internal.mean()
        g = g[pub[key].value_counts() >= 200]
        assert (g.sub(100).abs() < 1.5).all(), f"cohort margin not flat for {key}: {g.to_dict()}"


def test_schema_and_manifest_exist():
    schema = json.loads((DATA / "schema.json").read_text())
    assert schema["stat_type"] == "descriptive"
    assert schema["model_eligible"] is False
    man = json.loads((DATA / "provenance_manifest.json").read_text())
    assert man["rows"] > 0 and man["inputs"]


def test_percentile_matches_score_direction(pub):
    q = pub.dropna(subset=["advancement_percentile"])
    r = q.advancement_pace_plus_internal.corr(q.advancement_percentile, method="spearman")
    assert r > 0.95
