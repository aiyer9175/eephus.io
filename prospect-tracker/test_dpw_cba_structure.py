# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The CBA side of the projected $/WAR path (DESIGN_v2 4.1 regime_break;
docs/dpw-2026-09-25/DPW_PATH_GATE.md 4.3, the prospective REGIME rule).

Every agreement data/cba_rules.json encodes with effective_from after
2026-12-01 must carry the structure keys, so regime_break and the REGIME rule
can be read off the file; both rules are pinned on SYNTHETIC encodings."""

from __future__ import annotations

import json
from pathlib import Path

import dpw_path as dp

ROOT = Path(__file__).resolve().parent

_2022 = {"regime": "cba_2022", "effective_from": "2022-03-10", "effective_to": "2026-12-01"}
_CBT = [{"season": 2026, "threshold_usd": 244_000_000}]


def _new(**over):
    base = {"regime": "cba_2027", "effective_from": "2027-02-01", "effective_to": "2031-12-01",
            "salary_cap": None, "salary_floor": None, "fa_eligibility_changed": False,
            "arb_eligibility_changed": False, "cbt_structure": "unchanged", "stoppage": None}
    base.update(over)
    return base


def test_the_committed_rules_carry_the_structure_keys():
    rules = json.loads((ROOT / "data" / "cba_rules.json").read_text(encoding="utf-8"))
    assert dp.agreements_missing_structure(rules) == []


def test_a_new_agreement_without_the_keys_is_caught():
    bad = {"cba_regimes": [_2022, {"regime": "cba_2027", "effective_from": "2027-02-01"}]}
    missing = dp.agreements_missing_structure(bad)
    assert len(missing) == 1 and "salary_cap" in missing[0]
    assert dp.agreements_missing_structure({"cba_regimes": [_2022, _new()]}) == []


def test_regime_break_on_synthetic_encodings():
    assert dp.regime_break({"cba_regimes": [_2022]}, 2027) is False
    assert dp.regime_break({"cba_regimes": [_2022, _new()]}, 2027) is False
    assert dp.regime_break({"cba_regimes": [_2022, _new(salary_cap=200_000_000)]}, 2027) is True
    assert dp.regime_break({"cba_regimes": [_2022, _new(cbt_structure="restructured")]}, 2027) is True
    assert dp.regime_break({"cba_regimes": [_2022, _new(fa_eligibility_changed=True)]}, 2027) is True
    lockout = _new(stoppage={"from": "2026-12-02", "to": "2027-03-10"})
    assert dp.regime_break({"cba_regimes": [_2022, lockout]}, 2027) is True


def test_the_prospective_regime_rule():
    # W = 2028: its signing period (December 2027) falls under the synthetic new agreement
    cbt = _CBT + [{"season": 2027, "threshold_usd": 244_000_000}]
    rules = {"cba_regimes": [_2022, _new()], "cbt_thresholds": cbt + [{"season": 2028,
                                                                     "threshold_usd": 250_000_000}]}
    assert dp.prospective_regime(rules, 2028) is False
    assert dp.prospective_regime(rules, 2028, dropped_thin=True) is True
    jump = {"cba_regimes": [_2022, _new()], "cbt_thresholds": cbt + [{"season": 2028,
                                                                    "threshold_usd": 275_000_000}]}
    assert dp.prospective_regime(jump, 2028) is True            # more than 10 percent
    cap = {"cba_regimes": [_2022, _new(salary_floor=100_000_000)], "cbt_thresholds": cbt}
    assert dp.prospective_regime(cap, 2028) is True
    lock = {"cba_regimes": [_2022, _new(stoppage={"from": "2027-12-05", "to": "2028-02-20"})],
            "cbt_thresholds": cbt}
    assert dp.prospective_regime(lock, 2028) is True
    # no agreement encoded for the signing period: not scored until it is (the 2022
    # agreement expired on 2026-12-01, so the 2027 winter is not scored yet)
    assert dp.prospective_regime({"cba_regimes": [_2022], "cbt_thresholds": _CBT}, 2027) is None
    assert dp.prospective_regime(rules, 2027) is None
