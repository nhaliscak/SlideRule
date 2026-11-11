import random

import numpy as np
import pytest

from sliderule.core.banded import BandedLU, SingularMatrix


def build(seed, n, kl, ku):
    rnd = random.Random(seed)
    a = np.zeros((n, n))
    rows = []
    for i in range(n):
        r = []
        for j in range(i - kl, i + ku + 1):
            v = rnd.uniform(-1, 1)
            if 0 <= j < n:
                a[i, j] = v
            r.append(v)
        rows.append(r)
    return a, rows


@pytest.mark.parametrize("seed", range(20))
def test_banded_solve_matches_a_dense_solve(seed):
    rnd = random.Random(seed)
    n, kl, ku = rnd.randint(3, 60), rnd.randint(1, 5), rnd.randint(0, 5)
    a, rows = build(seed, n, kl, ku)
    b = [rnd.uniform(-1, 1) for _ in range(n)]
    x = BandedLU(n, kl, ku, rows).solve(b)
    assert np.allclose(a @ np.array(x), b, atol=1e-9 * (1 + np.abs(x).max()))


def test_one_factorisation_serves_many_right_hand_sides_and_singular_matrices_are_reported():
    a, rows = build(3, 30, 2, 2)
    lu = BandedLU(30, 2, 2, rows)
    for k in range(3):
        b = np.arange(30.0) + k
        assert np.allclose(a @ np.array(lu.solve(b)), b)
    with pytest.raises(SingularMatrix):
        BandedLU(4, 1, 1, [[0.0, 0.0, 0.0]] * 4)
