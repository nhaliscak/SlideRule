"""Banded linear systems: factor once, solve many times (LAPACK ``dgbtrf``/``dgbtrs`` through SciPy).

A matrix with lower bandwidth ``kl`` and upper bandwidth ``ku`` is given as rows ``rows[i]`` holding the entries of columns
``i-kl .. i+ku`` (``kl + ku + 1`` numbers; entries that fall outside the matrix are ignored).
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy.linalg import lapack


class SingularMatrix(ArithmeticError):
    pass


class BandedLU:
    def __init__(self, n: int, kl: int, ku: int, rows: Sequence[Sequence[float]]):
        self.n, self.kl, self.ku = n, kl, ku
        r = np.asarray(rows, dtype=float).reshape(n, kl + ku + 1)
        ab = np.zeros((2 * kl + ku + 1, n))
        idx = np.arange(n)
        for d in range(kl + ku + 1):                   # entry (i, i - kl + d) goes to row 2 kl + ku - d, column i - kl + d of LAPACK's band storage
            cols = idx - kl + d
            ok = (cols >= 0) & (cols < n)
            ab[2 * kl + ku - d, cols[ok]] = r[ok, d]
        lu, piv, info = lapack.dgbtrf(ab, kl, ku)
        if info > 0 or not np.all(np.isfinite(lu)):
            raise SingularMatrix("the matrix is singular")
        self._lu, self._piv = lu, piv

    def solve(self, b: Sequence[float]) -> list[float]:
        x, info = lapack.dgbtrs(self._lu, self.kl, self.ku, np.asarray(b, dtype=float), self._piv)
        if info != 0:
            raise SingularMatrix("the banded solve failed")
        return x.tolist()
