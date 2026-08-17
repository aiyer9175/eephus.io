from __future__ import annotations

import numpy as np
import pytest

from eephus_research.validation.identities import (
    IdentityViolation,
    assert_exact_identity,
    assert_identity,
)


def test_exact_identity_holds():
    assert_exact_identity(5.0, 2.0 + 3.0)


def test_exact_identity_violation_raises():
    with pytest.raises(IdentityViolation):
        assert_exact_identity(5.0, 2.0 + 3.01)


def test_identity_within_tolerance_passes():
    assert_identity(5.0, 5.0000001, tolerance=1e-6)


def test_identity_outside_tolerance_raises():
    with pytest.raises(IdentityViolation):
        assert_identity(5.0, 5.1, tolerance=1e-6)


def test_identity_correlation_is_not_a_substitute_for_reconciliation():
    """A high-correlation-but-offset pair must still fail -- this is the whole point of Part S."""
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b_plus_c = a + 10.0  # correlation with a is 1.0, but the identity is violated by a constant offset
    assert np.corrcoef(a, b_plus_c)[0, 1] > 0.999  # would pass a (wrong) correlation-based check
    with pytest.raises(IdentityViolation):
        assert_identity(a, b_plus_c, tolerance=1e-6)


def test_identity_array_elementwise():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([0.5, 1.0, 1.5])
    c = np.array([0.5, 1.0, 1.5])
    assert_exact_identity(a, b + c)
