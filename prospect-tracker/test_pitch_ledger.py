# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""pitch_ledger (docs/ewar/PITCH_LEDGER_GATE.md): the components close on every step, the
shares split the person effects exactly, the cell models are zero-sum, and the ridge fit
recovers a planted catcher while the null comparator stays flat. Synthetic fixtures only."""

from __future__ import annotations

import numpy as np

import pitch_ledger as pl


def test_sigma_is_frozen_from_the_grid():
    assert all(v in pl.SIGMA_GRID for v in pl.SIGMA.values())
    assert set(pl.SIGMA) == set(pl.GROUPS)


def test_called_components_sum_to_the_step():
    rng = np.random.default_rng(1)
    n = 500
    vb = rng.uniform(0.1, 1.5, n)
    vball = vb + rng.uniform(0.0, 0.2, n)
    vstr = vb - rng.uniform(0.0, 0.2, n)
    z = rng.integers(0, 2, n).astype(float)
    s0 = rng.integers(0, 2, n).astype(float)
    s1 = np.where(rng.random(n) < 0.1, 1 - s0, s0)
    d_c, d_p, d_b = (rng.normal(0, 0.02, n) for _ in range(3))
    extra = np.where(rng.random(n) < 0.05, rng.normal(0, 0.3, n), 0.0)
    dre = np.where(s1 >= 0.5, vstr, vball) - vb + extra
    c = pl.called_components(vb, vball, vstr, z, s0, s1, d_c, d_p, d_b, dre)
    assert pl.identity_ok(c, dre).all()
    assert np.allclose(c["x_oth"], extra)
    # a call that matches the rulebook with no person effects leaves no umpire runs
    c2 = pl.called_components(vb, vball, vstr, z, z, z, 0 * d_c, 0 * d_p, 0 * d_b,
                              np.where(z >= 0.5, vstr, vball) - vb)
    assert np.allclose(c2["x_ump"], 0.0) and np.allclose(c2["x_ch"], 0.0)


def test_shares_split_the_effects_exactly_with_their_signs():
    rng = np.random.default_rng(2)
    L0 = rng.normal(0, 2, 1000)
    parts = {g: rng.normal(0, 0.2, 1000) for g in pl.GROUPS}
    sh, tot = pl.shares(L0, parts)
    assert np.allclose(sum(sh.values()), tot, atol=1e-12)
    for g in pl.GROUPS:
        assert (np.sign(sh[g]) == np.sign(parts[g])).all()


def test_rulebook_zone_edges():
    z = pl.rulebook_strike([0.0, 0.82, 0.84, 0.0, 0.0], [2.5, 2.5, 2.5, 1.40, 1.30], [1.5] * 5, [3.4] * 5)
    assert list(z) == [1.0, 1.0, 0.0, 1.0, 0.0]
    assert np.isnan(pl.rulebook_strike([np.nan], [2.0], [1.5], [3.4])[0])


def test_expected_contact_is_zero_sum_over_the_season():
    rng = np.random.default_rng(3)
    n = 3000
    cells = [("t", int(a), int(b), 1) for a, b in zip(rng.integers(0, 5, n), rng.integers(0, 4, n))]
    bo = list(zip(rng.integers(0, 8, n), rng.integers(0, 3, n)))
    dre = rng.normal(0, 0.5, n)
    x, _ = pl.expected_contact(cells, bo, dre)
    assert abs(float((dre - x).sum())) < 1e-9


def _fixture(planted: bool, seed: int = 4):
    rng = np.random.default_rng(seed)
    nc, per = 40, 3000
    cat = np.repeat(np.arange(nc), per)
    L0 = rng.normal(0, 1.2, nc * per)
    true = rng.normal(0, 0.15, nc) if planted else np.zeros(nc)
    if planted:
        true[0] = 0.30
    y = (rng.random(len(L0)) < pl.expit(L0 + true[cat])).astype(float)
    idx = {"catcher": cat, "pitcher": rng.integers(0, 100, len(L0)),
           "batter": rng.integers(0, 200, len(L0)), "umpire": rng.integers(0, 20, len(L0))}
    return L0, y, idx, true


def test_planted_catcher_is_recovered_and_the_null_stays_flat():
    L0, y, idx, true = _fixture(True)
    b0, eff, info = pl.fit_effects(L0, y, idx, pl.SIGMA)
    assert info["converged"]
    assert 0.20 <= eff["catcher"][0] <= 0.40
    assert np.corrcoef(eff["catcher"], true)[0, 1] >= 0.5
    sd_planted = float(np.std(eff["catcher"]))
    L0n, yn, idxn, _ = _fixture(False)
    _, effn, _ = pl.fit_effects(L0n, yn, idxn, pl.SIGMA)
    assert float(np.std(effn["catcher"])) < sd_planted / 3.0


def test_fit_is_calibrated():
    L0, y, idx, _ = _fixture(True, seed=9)
    b0, eff, _ = pl.fit_effects(L0, y, idx, pl.SIGMA)
    L = L0 + b0 + sum(eff[g][idx[g]] for g in pl.GROUPS)
    assert abs(float(pl.expit(L).sum() - y.sum())) < 1e-6


def test_owners_cover_every_component():
    assert set(pl.OWNERS) == set(pl.COMPONENTS)
    assert pl.OWNERS["x_ump"] == ("umpire", "umpire")
    assert pl.OWNERS["x_frm"][1] == "catcher_framing"
