# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Shared test fixtures.

RAW-ENGINE MODULES: the surplus test files below pin the mixture model's
ALGEBRA (mean preservation, role ratios, portfolio additivity, anchor
reconciliation). The WS-6 empirical calibration layer (isotonic-real,
value_framework_config calibration block) sits ON TOP of that algebra via
apply_calibration and intentionally bends levels to match realized
outcomes — so it is disabled for these modules. The layer itself is
tested explicitly in test_value_framework.py::test_calibration_layer_*
and test_backtest.py."""

from __future__ import annotations

import pytest

_RAW_ENGINE_MODULES = (
    "test_config_base_verification",
    "test_debuted",
    "test_pitcher_roles",
    "test_portfolio",
    "test_source_disagreement",
    "test_value_framework_integration",
)


@pytest.fixture(autouse=True)
def _raw_surplus_engine(request):
    if request.module.__name__ not in _RAW_ENGINE_MODULES:
        yield
        return
    import value_framework as vf
    cfg = vf._config().get("calibration", {})
    saved = cfg.get("enabled")
    cfg["enabled"] = False
    try:
        yield
    finally:
        cfg["enabled"] = saved
