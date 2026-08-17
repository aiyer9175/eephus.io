"""Calibration framework (docs/VALIDATION_STANDARD.md, Part AN).

Predictive performance and calibration are different questions -- do not
infer model quality from correlation/discrimination alone.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CalibrationCurve:
    bin_edges: np.ndarray
    predicted_mean: np.ndarray
    observed_mean: np.ndarray
    bin_counts: np.ndarray


def calibration_curve(y_true: np.ndarray, y_pred: np.ndarray, n_bins: int = 10) -> CalibrationCurve:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    edges = np.quantile(y_pred, np.linspace(0, 1, n_bins + 1))
    edges[0] -= 1e-9  # ensure the minimum value falls inside the first bin
    bin_idx = np.digitize(y_pred, edges[1:-1], right=True)

    predicted_mean = np.full(n_bins, np.nan)
    observed_mean = np.full(n_bins, np.nan)
    counts = np.zeros(n_bins, dtype=int)
    for b in range(n_bins):
        mask = bin_idx == b
        counts[b] = int(mask.sum())
        if counts[b] > 0:
            predicted_mean[b] = float(y_pred[mask].mean())
            observed_mean[b] = float(y_true[mask].mean())

    return CalibrationCurve(edges, predicted_mean, observed_mean, counts)


def calibration_slope_intercept(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    """Slope/intercept of observed ~ predicted. Slope 1 / intercept 0 is perfectly calibrated."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    design = np.column_stack([np.ones_like(y_pred), y_pred])
    coeffs, *_ = np.linalg.lstsq(design, y_true, rcond=None)
    intercept, slope = coeffs
    return float(slope), float(intercept)
