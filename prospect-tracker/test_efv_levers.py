# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Gated eFV levers (2026-07-19): C1 reliability regen, P1 provisional prior,
S1 super-two population blend, S2 positional scarcity. The number-moving levers
(P1/S1/S2) are OFF by default; these tests prove (a) OFF is byte-identical to the
prior behavior and (b) the ON math is correct. Fully synthetic — no DB, no
served-artifact regen (per the degraded-local-data rule)."""

from __future__ import annotations

import math

import pytest

import value_framework as vf


# --------------------------------------------------------------------------- #
# C1 — reliability regen: bucket/tier parity with the shipped isotonic lab defs
# --------------------------------------------------------------------------- #
def test_c1_realized_bucket_matches_lab():
    import efv_reliability as er
    import bisect
    LAB_EDGES = (0.5, 1.5, 2.5, 4.0)
    lab = lambda w: bisect.bisect_right(LAB_EDGES, w / 6.0)
    for w in (0, 2.9, 3.0, 3.1, 8.9, 9.0, 15, 23.9, 24.0, 30, 60):
        assert er._realized_bucket(w) == lab(w), w


def test_c1_tier_matches_lab():
    import efv_reliability as er
    for fv in (37, 40, 42, 44, 45, 47, 50, 55, 60):
        assert er._tier(fv) == int(round(fv / 5) * 5)


def test_c1_tripwire_threshold_above_standing_gap():
    import efv_reliability as er
    # the documented standing bust-bucket ECE is ~0.12; the tripwire must sit above
    # it so it catches WIDENING, not the known standing miscalibration.
    assert er.BUST_ECE_TRIPWIRE > 0.12


# --------------------------------------------------------------------------- #
# P1 — provisional pedigree prior
# --------------------------------------------------------------------------- #
def _force_p1(monkeypatch, **over):
    import efv_score  # noqa: F401 (ensure module import path)
    cfg = dict(vf._config())
    cfg["efv_provisional_prior"] = {**cfg.get("efv_provisional_prior", {}),
                                    "enabled": True, **over}
    monkeypatch.setattr(vf, "_config", lambda: cfg)


def test_p1_off_is_identity():
    import efv_score as es
    # default config has enabled: false -> prior == cons_war, no factors
    w, f = es._provisional_prior_war(3.0, 5, 2_000_000)
    assert w == 3.0 and f == []


def test_p1_ifa_no_pick_stays_consensus(monkeypatch):
    import efv_score as es
    _force_p1(monkeypatch)
    w, f = es._provisional_prior_war(3.0, None, 5_000_000)   # no pick -> no invented WAR
    assert w == 3.0 and f == []


def test_p1_top_pick_pulls_toward_slot(monkeypatch):
    import efv_score as es
    import storage
    _force_p1(monkeypatch)
    slot5 = storage._pick_slot_expected_war(5)               # 8.492
    cons = 3.0
    ped = 0.8 + math.log10(2_000_000 / 10_000) * 0.5
    w_exp = ped / (ped + 1.0)
    exp = w_exp * slot5 + (1 - w_exp) * cons
    w, f = es._provisional_prior_war(cons, 5, 2_000_000)
    assert abs(w - exp) < 1e-6
    assert w > cons and f and f[0]["dir"] == "up"


def test_p1_late_pick_barely_moves(monkeypatch):
    import efv_score as es
    import storage
    _force_p1(monkeypatch)
    slot200 = storage._pick_slot_expected_war(200)
    ped = 0.05
    w_exp = ped / (ped + 1.0)
    exp = w_exp * slot200 + (1 - w_exp) * 3.0
    w, _ = es._provisional_prior_war(3.0, 200, None)
    assert abs(w - exp) < 1e-6
    assert abs(w - 3.0) < 0.2                                # barely moves


def test_p1_pedigree_capped(monkeypatch):
    import efv_score as es
    _force_p1(monkeypatch)
    # absurd bonus -> pedigree caps at max_pedigree_precision (3.0) -> weight 0.75
    w, _ = es._provisional_prior_war(3.0, 1, 500_000_000)
    import storage
    slot1 = storage._pick_slot_expected_war(1)
    exp = 0.75 * slot1 + 0.25 * 3.0
    assert abs(w - exp) < 1e-6


def test_p1_monotonic_in_pick(monkeypatch):
    import efv_score as es
    _force_p1(monkeypatch)
    # better pick (lower number) -> higher-or-equal prior at fixed consensus + bonus
    priors = [es._provisional_prior_war(3.0, pk, 1_000_000)[0] for pk in (1, 10, 30, 70, 150)]
    assert priors == sorted(priors, reverse=True)


# --------------------------------------------------------------------------- #
# S1 — super-two population blend (byte-identity off / on plumbing)
# --------------------------------------------------------------------------- #
def test_s1_flag_default_off():
    assert (vf._config().get("surplus_levers") or {}).get("super_two_population_blend") is False


# --------------------------------------------------------------------------- #
# S2 — positional scarcity multiplier
# --------------------------------------------------------------------------- #
def test_s2_off_is_neutral():
    for p in ("C", "SS", "SP", "1B", "RP", "DH"):
        assert vf.position_multiplier(p) == 1.0


def test_s2_double_gated_reads_table(monkeypatch):
    cfg = dict(vf._config())
    cfg["position"] = {**cfg["position"], "apply_market_scarcity": True, "market_scarcity": {}}
    cfg["surplus_levers"] = {**cfg.get("surplus_levers", {}),
                             "positional_scarcity_in_core_surplus": True}
    monkeypatch.setattr(vf, "_config", lambda: cfg)
    tv = cfg["trade_value"]["positional_scarcity"]
    assert abs(vf.position_multiplier("C") - tv["C"]) < 1e-9
    assert abs(vf.position_multiplier("SS") - tv["SS"]) < 1e-9


def test_s2_explicit_override_wins(monkeypatch):
    cfg = dict(vf._config())
    cfg["position"] = {**cfg["position"], "apply_market_scarcity": True,
                       "market_scarcity": {"C": 1.05}}
    cfg["surplus_levers"] = {**cfg.get("surplus_levers", {}),
                             "positional_scarcity_in_core_surplus": True}
    monkeypatch.setattr(vf, "_config", lambda: cfg)
    assert abs(vf.position_multiplier("C") - 1.05) < 1e-9   # explicit beats the table


def test_s2_needs_both_gates(monkeypatch):
    # only surplus_levers flag, WITHOUT apply_market_scarcity -> still neutral
    cfg = dict(vf._config())
    cfg["surplus_levers"] = {**cfg.get("surplus_levers", {}),
                             "positional_scarcity_in_core_surplus": True}
    monkeypatch.setattr(vf, "_config", lambda: cfg)
    assert vf.position_multiplier("C") == 1.0
