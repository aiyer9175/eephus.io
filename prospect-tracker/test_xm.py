# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""xM$ model pins (docs/xm/XM_GATE.md, xm.py, tools/xm_lab.py).

Synthetic fixtures only, apart from the artifact and registry checks at the
end: monotonicity of candidate (c), censoring in candidate (b), no look-ahead
in the $/WAR index, band ordering P10 <= P50 <= P90, deterministic seeds, the
counterfactual support clip, the eFV prospect path and Fair $ reusing
fa_market's rational value.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import xm  # noqa: E402

ART = ROOT / "data" / "xm_eval.json"
REG = ROOT / "data" / "model_registry.json"


# ---------------------------------------------------------------------------
# $/WAR index: one-step random walk, strictly ex ante
# ---------------------------------------------------------------------------

def test_index_reads_only_prior_winters():
    s = {2015: 10e6, 2016: 11e6, 2017: 12e6, 2018: 13e6, 2019: 99e6}
    a = xm.dpw_index(s, 2018)
    s2 = {**s, 2018: 1e6, 2019: 1e9, 2020: 5e6}
    assert xm.dpw_index(s2, 2018) == a
    # random walk with drift: last prior winter times the mean prior log step
    step = (math.log(12e6) - math.log(10e6)) / 2
    assert a == pytest.approx(math.exp(math.log(12e6) + step))


def test_index_one_prior_carries_and_none_falls_back():
    assert xm.dpw_index({2015: 9e6}, 2016) == pytest.approx(9e6)
    assert xm.dpw_index({2016: 9e6}, 2015, flat_usd=7e6) == 7e6
    with pytest.raises(ValueError):
        xm.dpw_index({}, 2015)


# ---------------------------------------------------------------------------
# Bands
# ---------------------------------------------------------------------------

def test_band_ordering_holds_even_for_one_sided_quantiles():
    p = np.array([15.0, 16.0, 17.5])
    for q in ((0.2, 0.9), (-0.9, -0.1), (-0.5, 0.6)):
        lo, hi = xm.apply_band(p, q)
        assert np.all(lo <= p) and np.all(p <= hi)


def test_band_quantiles_need_rows():
    assert xm.band_quantiles([0.1] * 5) == (-1.0, 1.0)
    lo, hi = xm.band_quantiles(np.linspace(-1, 1, 101))
    assert lo == pytest.approx(-0.8) and hi == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Candidate (c): monotone constraints
# ---------------------------------------------------------------------------

def _synthetic(n=600, seed=3):
    rng = np.random.default_rng(seed)
    F = np.zeros((n, len(xm.FEATURES)))
    ix = {k: i for i, k in enumerate(xm.FEATURES)}
    F[:, ix["age"]] = rng.integers(25, 38, n)
    F[:, ix["war_y1"]] = np.clip(rng.normal(1.5, 1.2, n), 0, None)
    F[:, ix["war_3"]] = F[:, ix["war_y1"]] * 2.6
    F[:, ix["war_tot"]] = F[:, ix["war_y1"]] * 5
    F[:, ix["plat_war"]] = F[:, ix["war_y1"]] + rng.normal(0, 0.5, n)
    F[:, ix["war_3y"]] = F[:, ix["plat_war"]] * 2.5
    F[:, ix["log_index"]] = math.log(12e6)
    F[:, ix["log_rational3"]] = np.log(np.maximum(F[:, ix["war_3"]], 0.25) * 12e6)
    yrs = np.clip(np.rint(1 + 1.1 * F[:, ix["war_y1"]] - 0.2 * (F[:, ix["age"]] - 30)
                          + rng.normal(0, 0.6, n)), 1, 10)
    log_aav = math.log(3e6) + 0.5 * F[:, ix["war_y1"]] + rng.normal(0, 0.4, n)
    return F, yrs, log_aav, ix


def test_gbm_more_war_never_lowers_price_and_age_never_lengthens_term():
    F, yrs, la, ix = _synthetic()
    m = xm.GBM().fit(F, yrs, la)
    base = F[:50].copy()
    p0 = m.predict(base)
    for k in xm.WAR_FEATURES:
        up = base.copy()
        up[:, ix[k]] += 1.5
        p1 = m.predict(up)
        assert np.all(p1["years_f"] >= p0["years_f"] - 1e-9), k
    older = base.copy()
    older[:, ix["age"]] += 3
    assert np.all(m.predict(older)["years_f"] <= p0["years_f"] + 1e-9)
    # the AAV stage on its own: more WAR at a fixed term never lowers AAV
    ly = np.log(p0["years_f"])
    up = base.copy()
    up[:, ix["war_y1"]] += 2.0
    a0 = m.m_aav.predict(np.column_stack([base, ly]))
    a1 = m.m_aav.predict(np.column_stack([up, ly]))
    assert np.all(a1 >= a0 - 1e-9)


def test_gbm_is_deterministic_under_its_seed():
    F, yrs, la, _ = _synthetic()
    a = xm.GBM().fit(F, yrs, la).predict(F[:40])
    b = xm.GBM().fit(F, yrs, la).predict(F[:40])
    assert np.array_equal(a["log_total"], b["log_total"])


def test_monotone_vector_matches_the_gate():
    cy = xm.monotone_cst(xm.FEATURES, "years")
    ca = xm.monotone_cst(xm.FEATURES + ("log_years",), "aav")
    for k, c in zip(xm.FEATURES, cy):
        want = 1 if k in xm.WAR_FEATURES else (-1 if k == "age" else 0)
        assert c == want, k
    assert ca[xm.FEATURES.index("age")] == 0 and ca[-1] == 0


# ---------------------------------------------------------------------------
# Candidate (b): censoring, ordinal years, truncated median
# ---------------------------------------------------------------------------

def test_tobit_recovers_a_planted_line_that_least_squares_misses():
    rng = np.random.default_rng(xm.SEED)
    n = 4000
    X = rng.normal(size=(n, 3))
    beta = np.array([1.0, 0.6, -0.4, 0.3])
    mu = beta[0] + X @ beta[1:]
    lat = mu + rng.normal(0, 0.5, n)
    floor = np.full(n, 0.8)
    cens = lat < floor
    assert 0.2 < cens.mean() < 0.6
    bt, s = xm.tobit_fit(X, lat, cens, floor, ridge=0.0)
    assert np.allclose(bt, beta, atol=0.05) and s == pytest.approx(0.5, abs=0.03)
    A = np.column_stack([np.ones(n), X])
    bo, *_ = np.linalg.lstsq(A[~cens], lat[~cens], rcond=None)
    assert np.abs(A @ bo - mu).mean() > 3 * np.abs(A @ bt - mu).mean()


def test_ordered_logit_recovers_planted_cutpoints():
    rng = np.random.default_rng(1)
    n = 3000
    Z = rng.normal(size=(n, 2))
    b = np.array([0.9, -0.4])
    th = np.array([-1.5, -0.5, 0.2, 0.8, 1.5, 2.5])
    P = xm.ordered_probs(Z, b, th)
    y = (np.cumsum(P, 1) < rng.random(n)[:, None]).sum(1).clip(0, 6)
    bh, thh = xm.ordered_logit_fit(Z, y, ridge=0.0)
    assert np.allclose(bh, b, atol=0.08) and np.allclose(thh, th, atol=0.15)
    assert np.all(np.diff(thh) > 0)


def test_truncated_median_matches_monte_carlo():
    rng = np.random.default_rng(5)
    mu, sig, fl = 1.0, 0.7, 1.2
    d = rng.normal(mu, sig, 400_000)
    want = float(np.median(d[d >= fl]))
    assert float(xm.truncated_median(np.array([mu]), sig, np.array([fl]))[0]) == pytest.approx(want, abs=0.01)
    # far above the floor the truncation does nothing
    assert float(xm.truncated_median(np.array([20.0]), 0.5, np.array([1.0]))[0]) == pytest.approx(20.0)


def test_year_categories():
    assert [xm.year_cat(v) for v in (1, 2, 6, 7, 10, 15)] == [0, 1, 5, 6, 6, 6]


# ---------------------------------------------------------------------------
# Scoring and the bootstrap
# ---------------------------------------------------------------------------

def test_cluster_bootstrap_is_seeded_and_paired():
    rng = np.random.default_rng(2)
    a = np.abs(rng.normal(0.6, 0.2, 300))
    c = a - 0.05
    cl = [f"p{i % 120}" for i in range(300)]
    r1 = xm.cluster_lo95(a, c, cl, B=500)
    r2 = xm.cluster_lo95(a, c, cl, B=500)
    assert r1 == r2
    assert r1["delta"] == pytest.approx(0.05) and r1["lo95_one_sided"] == pytest.approx(0.05)
    assert r1["clusters"] == 120



def test_bootstrap_weights_equal_the_add_at_counts():
    # The XM1-Q1 crash fix: one bincount replaces np.add.at with exactly the
    # same counts, so every bound the read prints is the registered one.
    rng = np.random.default_rng(3)
    for B, C in ((4000, 893), (4000, 250), (7, 3), (1, 1)):
        draws = rng.integers(0, C, size=(B, C))
        W = np.zeros((B, C))
        np.add.at(W, (np.repeat(np.arange(B), C), draws.ravel()), 1.0)
        assert np.array_equal(W, xm.bootstrap_weights(draws, C))


def test_resume_gate_check_ignores_only_the_amendments():
    import xm_lab
    body = "# g" + chr(10) + "x" + chr(10) + "## 14. Amendments" + chr(10) + "None." + chr(10)
    amended = body.replace("None.", "2026-10-22: a dated note")
    assert xm_lab._registered_body(body) == xm_lab._registered_body(amended)
    assert xm_lab._registered_body(body) == xm_lab._registered_body(
        body.replace(chr(10), chr(13) + chr(10)))
    assert xm_lab._registered_body(body) != xm_lab._registered_body(body.replace("x", "y"))

def test_metrics_coverage_and_years():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    m = xm.metrics(y, y, y - 0.5, y + 0.5, [1, 2, 3, 5], [1, 2, 4, 2])
    assert m["log_total_mae"] == 0 and m["coverage_p10_p90"] == 1.0
    assert m["years_exact"] == 0.5 and m["years_within_one"] == 0.75


# ---------------------------------------------------------------------------
# Counterfactual extension and Fair $
# ---------------------------------------------------------------------------

def test_clip_to_support_flags_and_scales_down_only():
    box = {"age": [23, 40], "war_y1": [0.0, 8.0], "war_tot": [0.0, 60.0]}
    a, wy, out = xm.clip_to_support(19, [1.0] * 15, box)
    assert out and a == 23 and wy == [1.0] * 15
    a, wy, out = xm.clip_to_support(27, [10.0] * 10, box)
    assert out and max(wy) <= 8.0 + 1e-9 and sum(wy) <= 60.0 + 1e-9
    a, wy, out = xm.clip_to_support(30, [2.0, 1.5, 1.0], box)
    assert not out and wy == [2.0, 1.5, 1.0]


def test_prospect_path_follows_the_gate():
    p = xm.prospect_path(12.0, 2029, 21, winter=2027)
    assert p[:2] == [0.0, 0.0] and p[2:8] == [2.0] * 6
    assert len(p) == 15 and all(v >= 0 for v in p)
    old = xm.prospect_path(6.0, 2027, 29, winter=2027)
    assert old[:6] == [1.0] * 6 and old[7] == pytest.approx(max(0.0, 1.0 - 0.5 * 6))
    assert xm.prospect_path(6.0, None, 22, winter=2027)[0] == 1.0     # no ETA: debut now


def test_fair_value_is_fa_markets_rational_value():
    import fa_market as fm
    path = {"war_by_year": [3.0, 2.6, 2.2, 1.8, 1.4] + [0.0] * 10}
    got = xm.fair_value_usd(path, 4, 2027, 17e6)
    assert got == int(fm.expected_rational_value_usd(path, 4, 2027, 17e6))
    assert got > 0


def test_static_features_read_only_prior_seasons():
    seasons = {2026: {"war": 3.0, "bf": 700, "role": "SP"}, 2025: {"war": 2.0, "bf": 300, "role": "RP"},
               2027: {"war": 50.0, "bf": 900, "role": "SP"}}
    st = xm.static_features(age=30, war_by_year=[2.0, 1.5], side="pit", position="SP/SP2",
                            qo=True, seasons=seasons, il_seasons={2026: (40.0, 1), 2027: (99.0, 2)},
                            winter=2027, demand=18, disc_rate=0.07)
    assert st["plat_war"] == 3.0 and st["war_3y"] == 5.0
    assert st["gs_share"] == pytest.approx(0.7) and st["il_prior1"] == 40.0 and st["il_3y"] == 40.0
    assert st["pos_sp"] == 1.0 and st["qo"] == 1.0


def test_demand_counts_payroll_room():
    assert xm.demand_count({"A": 100e6, "B": 230e6, "C": None, "D": 224e6}, 244e6) == 2


# ---------------------------------------------------------------------------
# The lab's reporting path on the fixture (gate section 13 step 1)
# ---------------------------------------------------------------------------

def test_lab_dry_run_writes_only_where_told(tmp_path):
    import xm_lab
    out = tmp_path / "xm_eval.json"
    before = ART.read_bytes() if ART.exists() else None
    doc = xm_lab.run(xm_lab.fixture_inputs(), out, "2026-10-22", dev=(2016, 2017),
                     hold=(2018,), do_counterfactual=False, B=100)
    assert out.exists() and doc["order"] == ["inputs", "planted", "development", "holdout"]
    assert doc["holdout"]["verdict"] in ("REPLACE", "INCUMBENT", "TIE")
    assert (ART.read_bytes() if ART.exists() else None) == before


def test_holdout_resume_reads_the_persisted_selection(tmp_path):
    import xm_lab
    out = tmp_path / "xm_eval.json"
    full = xm_lab.run(xm_lab.fixture_inputs(), out, "2026-10-22", dev=(2016, 2017),
                      hold=(2018,), do_counterfactual=False, B=100)
    dev_only = json.loads(out.read_text(encoding="utf-8"))
    dev_only["order"] = ["inputs", "planted", "development"]
    dev_only.pop("holdout")
    dev_only["industry_mlbtr"].pop("holdout", None)
    again = xm_lab.holdout_and_after(dev_only, xm_lab.fixture_inputs(), tmp_path / "r.json",
                                     (2018,), False, 100)
    assert again["holdout"]["verdict"] == full["holdout"]["verdict"]
    assert again["holdout"]["paired"]["incumbent_vs_null1"]["delta"] == pytest.approx(
        full["holdout"]["paired"]["incumbent_vs_null1"]["delta"])


# ---------------------------------------------------------------------------
# The read's artifact and the registry row
# ---------------------------------------------------------------------------

def test_artifact_and_registry_agree():
    if not ART.exists():
        pytest.skip("read not run")
    doc = json.loads(ART.read_text(encoding="utf-8"))
    if not doc.get("holdout"):
        pytest.skip("holdout not read yet")
    assert doc["order"][:4] == ["inputs", "planted", "development", "holdout"]
    v = doc["holdout"]["verdict"]
    assert v in ("REPLACE", "INCUMBENT", "TIE")
    reg = json.loads(REG.read_text(encoding="utf-8"))
    row = next(m for m in reg["models"] if m["model_id"] == "xm")
    assert row["eval_artifact"] == "data/xm_eval.json"
    assert row["verdict"] == doc["holdout"]["registry_verdict"]
    if v != "REPLACE":
        assert row["verdict"] != "validated"
        assert row.get("provisional_kind") == doc["holdout"]["provisional_kind"]
    sel = doc["development"]["selection"]
    assert sel["selected"] in ("a_incumbent", "b_hurdle", "c_gbm")
    assert set(doc["holdout"]["scored"]) <= {"a_incumbent", "null1", "const", sel["selected"]}
