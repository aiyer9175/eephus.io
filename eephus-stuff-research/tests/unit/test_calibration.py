from __future__ import annotations

import numpy as np

from eephus_research.diagnostics.calibration import calibration_curve, calibration_slope_intercept


def test_perfect_calibration_slope_one_intercept_zero():
    rng = np.random.default_rng(0)
    y_pred = rng.uniform(0, 1, 500)
    y_true = y_pred  # perfectly calibrated by construction
    slope, intercept = calibration_slope_intercept(y_true, y_pred)
    assert abs(slope - 1.0) < 1e-9
    assert abs(intercept - 0.0) < 1e-9


def test_calibration_curve_bin_counts_sum_to_n():
    rng = np.random.default_rng(0)
    y_pred = rng.uniform(0, 1, 200)
    y_true = rng.integers(0, 2, 200).astype(float)
    curve = calibration_curve(y_true, y_pred, n_bins=5)
    assert curve.bin_counts.sum() == 200
