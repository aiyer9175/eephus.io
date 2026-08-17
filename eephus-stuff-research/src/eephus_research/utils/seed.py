"""Centralized determinism control (docs/STATISTICAL_GOVERNANCE.md, Part Z)."""
from __future__ import annotations

import random

import numpy as np


def set_all_seeds(seed: int) -> None:
    """Seed every RNG this repository's stack touches (Python, NumPy).

    Does not guarantee determinism for libraries that parallelize reductions
    internally (e.g. some BLAS-backed operations) -- if a downstream result
    is not reproducible despite calling this, document that limitation next
    to the result rather than assuming this function was insufficient.
    """
    random.seed(seed)
    np.random.seed(seed)


def get_default_seed() -> int:
    """The repository-wide fallback seed.

    This is for exploratory work only. Anything certified must record its
    own seed explicitly in registry/experiments/ -- do not depend on this
    value implicitly for a result that matters.
    """
    return 20260816
