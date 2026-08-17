"""Executable mathematics (docs/MATHEMATICAL_GOVERNANCE.md, Part S).

Where math implies an identity, test the identity directly -- never
substitute a correlation check for reconciliation.
"""
from __future__ import annotations

import numpy as np


class IdentityViolation(AssertionError):
    pass


def assert_identity(
    lhs: float | np.ndarray,
    rhs: float | np.ndarray,
    tolerance: float,
    label: str = "identity",
) -> None:
    """Assert lhs - rhs is within `tolerance` (elementwise for arrays).

    tolerance must come from a named entry in config/research.yaml, not be
    invented inline -- see docs/MATHEMATICAL_GOVERNANCE.md's numerical
    precision section.
    """
    lhs_arr = np.asarray(lhs, dtype=float)
    rhs_arr = np.asarray(rhs, dtype=float)
    diff = np.abs(lhs_arr - rhs_arr)
    max_diff = float(np.max(diff)) if diff.size else 0.0
    if max_diff > tolerance:
        raise IdentityViolation(
            f"{label}: max |lhs - rhs| = {max_diff} exceeds tolerance {tolerance}"
        )


def assert_exact_identity(
    lhs: float | np.ndarray, rhs: float | np.ndarray, label: str = "identity"
) -> None:
    """For accounting identities that must be exact (tolerance = 0.0)."""
    assert_identity(lhs, rhs, tolerance=0.0, label=label)
