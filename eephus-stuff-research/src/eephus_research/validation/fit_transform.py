"""Makes accidental full-dataset fitting hard to do by accident (Part AG).

Any learned transformation (mean/SD, imputation values, encoders, PCA, ...)
must be fit on training data only. This wrapper does not, by itself, prove a
given call site avoided leakage -- combine it with
diagnostics.leakage.check_train_test_overlap on whatever indices were
actually used to fit.
"""
from __future__ import annotations

from typing import Any, Protocol


class _SklearnLike(Protocol):
    def fit(self, X: Any, y: Any = None) -> Any: ...
    def transform(self, X: Any) -> Any: ...


class NotFittedError(RuntimeError):
    pass


class FitOnTrain:
    """Wraps a fit/transform-style object and refuses transform() before fit().

    Also records the number of rows seen at fit time, so a caller can assert
    (e.g. in a test) that fit() was called with a training split's row count,
    not the full dataset's.
    """

    def __init__(self, transformer: _SklearnLike):
        self._transformer = transformer
        self._fitted = False
        self.n_rows_fit: int | None = None

    def fit(self, X, y=None) -> "FitOnTrain":
        self._transformer.fit(X, y)
        self._fitted = True
        try:
            self.n_rows_fit = len(X)
        except TypeError:
            self.n_rows_fit = None
        return self

    def transform(self, X):
        if not self._fitted:
            raise NotFittedError(
                "transform() called before fit(). Fit on the training split "
                "only, then transform whichever split you need."
            )
        return self._transformer.transform(X)

    def fit_transform(self, X_train, X_apply=None, y=None):
        self.fit(X_train, y)
        return self.transform(X_apply if X_apply is not None else X_train)
