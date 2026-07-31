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
# P1 V2 - provisional pedigree prior (bounded upward-only pull + mixture baseline;
# docs/efv-provisional-prior/GATES.md V2, shipped 2026-07-23)
# --------------------------------------------------------------------------- #
def _force_p1(monkeypatch, enabled=True, **over):
    import efv_score  # noqa: F401 (ensure module import path)
    cfg = dict(vf._config())
    cfg["efv_provisional_prior"] = {**cfg.get("efv_provisional_prior", {}),
                                    "enabled": enabled, **over}
    monkeypatch.setattr(vf, "_config", lambda: cfg)


def test_p1_off_is_identity(monkeypatch):
    import efv_score as es
    # flag off -> prior == cons_war, no factors (the byte-identical OFF contract)
    _force_p1(monkeypatch, enabled=False)
    w, f = es._provisional_prior_war(3.0, 5, 2_000_000)
    assert w == 3.0 and f == []


def test_p1_shipped_flags_and_cap():
    # V2 shipped state: flag ON, frozen cap 1.9, IFA step wired at 1.917/0.25/$1M
    cfg = vf._config().get("efv_provisional_prior") or {}
    assert cfg.get("enabled") is True
    assert abs(float(cfg.get("pull_cap_war")) - 1.9) < 1e-9
    assert cfg.get("ifa_step_enabled") is True
    assert abs(float(cfg.get("ifa_step_war")) - 1.917) < 1e-9
    assert int(cfg.get("ifa_step_bonus_usd")) == 1_000_000


def test_p1_ifa_sub_1m_stays_consensus(monkeypatch):
    import efv_score as es
    _force_p1(monkeypatch)   # shipped config: ifa_step wired
    # sub-$1M IFA -> bit-identical consensus (the ifa_pedigree ledger's finding)
    w, f = es._provisional_prior_war(3.0, None, 900_000)
    assert w == 3.0 and f == []
    # step disabled -> even a huge bonus stays consensus
    _force_p1(monkeypatch, ifa_step_enabled=False)
    w, f = es._provisional_prior_war(3.0, None, 5_000_000)
    assert w == 3.0 and f == []


def test_p1_ifa_step_bounded_upward(monkeypatch):
    import efv_score as es
    _force_p1(monkeypatch, ifa_step_enabled=True, ifa_step_war=1.917)
    # >= $1M IFA with a LOW consensus: prior rises by w_ifa * pull, never above
    # cons + 0.2 * pull_cap; a HIGH consensus gets pull 0 (posted-pro guard)
    w, f = es._provisional_prior_war(0.0, None, 2_000_000)
    assert 0.0 < w <= 0.2 * 1.9 + 1e-9
    w_hi, f_hi = es._provisional_prior_war(6.0, None, 2_000_000)
    assert w_hi == 6.0 and f_hi == []


def test_p1_top_pick_pull_is_capped(monkeypatch):
    import efv_score as es
    import storage
    _force_p1(monkeypatch)
    slot5 = storage._pick_slot_expected_war(5)               # 8.492 >> cons + cap
    cons = 3.0
    ped = 0.8 + math.log10(2_000_000 / 10_000) * 0.5
    w_exp = ped / (ped + 1.0)
    # V2: prior = cons + w * clip(slot - ref, 0, 1.9); no cons_fv here -> ref = cons
    exp = cons + w_exp * min(slot5 - cons, 1.9)
    w, f = es._provisional_prior_war(cons, 5, 2_000_000)
    assert abs(w - exp) < 1e-6
    assert w > cons and f and f[0]["dir"] == "up"


def test_p1_late_pick_does_not_move(monkeypatch):
    import efv_score as es
    import storage
    _force_p1(monkeypatch)
    # V2 upward-only pull: slot(200) = 0.65 < cons 3.0 -> pull 0 -> identity
    assert storage._pick_slot_expected_war(200) < 3.0
    w, f = es._provisional_prior_war(3.0, 200, None)
    assert w == 3.0 and f == []


def test_p1_pedigree_capped(monkeypatch):
    import efv_score as es
    _force_p1(monkeypatch)
    # absurd bonus -> pedigree caps at 3.0 -> weight 0.75; pull caps at 1.9
    w, _ = es._provisional_prior_war(3.0, 1, 500_000_000)
    assert abs(w - (3.0 + 0.75 * 1.9)) < 1e-6


def test_p1_mixture_baseline_kills_tiny_slot_pull(monkeypatch):
    import efv_score as es
    import storage
    _force_p1(monkeypatch)
    # V1 defect B cell: FV 37.66 hitter, cons_war floored to 0, pick 110 slot 0.776.
    # The bucket-mixture baseline (~1.17 six-yr WAR) exceeds the slot leg -> pull 0.
    assert storage._pick_slot_expected_war(110) < 1.1
    w, f = es._provisional_prior_war(0.0, 110, 350_000,
                                     cons_fv=37.66, is_pitcher=False)
    assert w == 0.0 and f == []
    # the same row WITHOUT the baseline inputs degrades to capped-V1 and would move:
    w_deg, _ = es._provisional_prior_war(0.0, 110, 350_000)
    assert w_deg > 0.0


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
