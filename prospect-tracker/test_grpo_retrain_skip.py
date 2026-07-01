# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for the GRPO retrain-skip (deferred runtime optimization).

The optimization skips a redundant GRPO retrain when the training data is
byte-identical to the saved model's fingerprint. That is only OUTPUT-NEUTRAL if
training is deterministic, so these tests pin BOTH the determinism assumption and
the fingerprint/skip mechanics:

  - train_grpo_policy is deterministic (same data -> identical predictions),
  - _training_fingerprint is stable for identical data and changes when any
    training row changes,
  - saving a model writes the fingerprint sidecar,
  - the reuse gate fires only on an exact fingerprint match.
"""
import pytest

grpo = pytest.importorskip("grpo_prospect")
pytest.importorskip("sklearn")


def _dataset(bump=0.0):
    """A small synthetic GRPO training set: groups of prospects with an outcome.
    `bump` perturbs one outcome so we can check the fingerprint reacts."""
    rows = []
    for g in range(4):
        for i in range(5):
            rows.append({
                "features": {"fv": 40 + i * 2, "max_ev": 100 + i,
                             "age": 19 + (i % 3), "level_idx": g % 5},
                "outcome": float(i) + (bump if (g == 0 and i == 0) else 0.0),
                "group": f"grp{g}",
            })
    return rows


def _predict_grid(model):
    import numpy as np
    xs = [grpo._feature_vector({"fv": fv, "max_ev": ev})
          for fv in (35, 45, 55) for ev in (95, 105, 115)]
    return [round(float(v), 10) for v in model.predict(np.array(xs, dtype=float))]


def test_training_is_deterministic(tmp_path):
    ds = _dataset()
    m1 = grpo.train_grpo_policy(ds, tmp_path / "a.pkl")
    m2 = grpo.train_grpo_policy(ds, tmp_path / "b.pkl")
    assert m1 is not None and m2 is not None
    # Identical training data -> identical predictions. This is the property the
    # skip relies on: reusing the saved model cannot change any score.
    assert _predict_grid(m1) == _predict_grid(m2)


def test_fingerprint_stable_and_sensitive():
    ds = _dataset()
    assert grpo._training_fingerprint(ds) == grpo._training_fingerprint(_dataset())
    # A single perturbed outcome must change the fingerprint (else a real retrain
    # would be wrongly skipped).
    assert grpo._training_fingerprint(ds) != grpo._training_fingerprint(_dataset(bump=1.0))


def test_saving_model_writes_fingerprint(tmp_path):
    ds = _dataset()
    mp = tmp_path / "grpo_model.pkl"
    grpo.train_grpo_policy(ds, mp)
    fp = grpo._fingerprint_path(mp)
    assert fp.exists()
    assert grpo._read_fingerprint(fp) == grpo._training_fingerprint(ds)


def test_reuse_gate_only_on_exact_match(tmp_path):
    ds = _dataset()
    mp = tmp_path / "grpo_model.pkl"
    grpo.train_grpo_policy(ds, mp)
    fp = grpo._fingerprint_path(mp)

    def matches(dataset):
        return (mp.exists() and fp.exists()
                and grpo._read_fingerprint(fp) == grpo._training_fingerprint(dataset))

    assert matches(ds) is True              # unchanged data -> reuse
    assert matches(_dataset(bump=2.0)) is False  # changed data -> must retrain


def test_export_reuses_model_on_unchanged_data(tmp_path, monkeypatch):
    # End-to-end: two export_grpo_scores(retrain=True) calls on the same data.
    # The second must NOT rewrite the model file (proving the retrain was
    # skipped) and must produce identical scores.
    import os
    ds = _dataset()
    monkeypatch.setattr(grpo, "build_training_dataset", lambda grads, ln=None: ds)
    active = [{"player_key": f"p{i}", "player_name": f"P{i}",
               "position": "SS", "org": "X", "current_level": "A",
               "age": 20, "fv": 45, "max_ev": 108} for i in range(6)]
    mp = tmp_path / "grpo_model.pkl"
    out = tmp_path / "grpo_scores.json"

    r1 = grpo.export_grpo_scores(active, [], out_path=out, model_path=mp, retrain=True)
    mtime1 = os.path.getmtime(mp)
    scores1 = out.read_text(encoding="utf-8")

    r2 = grpo.export_grpo_scores(active, [], out_path=out, model_path=mp, retrain=True)
    mtime2 = os.path.getmtime(mp)
    scores2 = out.read_text(encoding="utf-8")

    assert r1.get("scored") == r2.get("scored")
    assert mtime2 == mtime1, "model file was rewritten — retrain was NOT skipped"
    # Same-day generated_at, deterministic model -> byte-identical scores.
    assert scores1 == scores2
