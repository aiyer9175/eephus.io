from __future__ import annotations

import numpy as np
import pytest
from sklearn.preprocessing import StandardScaler

from eephus_research.validation.fit_transform import FitOnTrain, NotFittedError


def test_transform_before_fit_raises():
    wrapped = FitOnTrain(StandardScaler())
    with pytest.raises(NotFittedError):
        wrapped.transform(np.array([[1.0], [2.0]]))


def test_fit_then_transform_works():
    wrapped = FitOnTrain(StandardScaler())
    train = np.array([[1.0], [2.0], [3.0]])
    wrapped.fit(train)
    out = wrapped.transform(train)
    assert out.shape == train.shape
    assert wrapped.n_rows_fit == 3


def test_fit_transform_applies_train_params_to_other_data():
    wrapped = FitOnTrain(StandardScaler())
    train = np.array([[0.0], [10.0]])
    test = np.array([[5.0]])
    out = wrapped.fit_transform(train, test)
    # mean of train is 5, so test point should transform to ~0
    assert abs(out[0, 0]) < 1e-9
