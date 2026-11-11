"""Helpers for the core physics and chemistry tests.

Each calculation is checked against a formula written out again here in plain Python (constants typed out again, not imported from the
library). ``check_case`` reads the inputs of the calculation's worked example in SI units, so the formula does not depend on how the
library converts units on input; the expected values are compared with the engine's SI results.
"""

import math

import pytest

from sliderule.core import solve
from sliderule.core.catalog import default_catalog
from sliderule.core.engine import parse_quantity
from sliderule.units import parse_unit

CAT = default_catalog()

h = 6.62607015e-34
hbar = h / (2 * math.pi)
c = 299792458.0
kB = 1.380649e-23
NA = 6.02214076e23
e = 1.602176634e-19
R = NA * kB
eps0 = 8.8541878128e-12
mu0 = 1.25663706212e-6
G = 6.67430e-11
sSB = 5.670374419e-8
me = 9.1093837015e-31
mp = 1.67262192369e-27
Rinf = 10973731.568160
a0 = 5.29177210903e-11
g = 9.80665
Da = 1.66053906660e-27
F = e * NA
pi = math.pi
deg = pi / 180
atm = 101325.0


def si_inputs(cid, **over):
    calc = CAT.get(cid)
    out = {}
    for key, text in {**calc.example, **over}.items():
        v = calc.by_key[key]
        val, unit = parse_quantity(text)
        out[key] = parse_unit(unit or v.unit, as_delta=v.delta).to_si(val)
    return out


def solved(cid, warnings_ok=False, **over):
    calc = CAT.get(cid)
    s = solve(calc, {**calc.example, **over})
    assert s.ok, [d.message for d in s.diagnostics]
    if not warnings_ok:
        assert not [d for d in s.diagnostics if d.level in ("error", "warning")], [d.message for d in s.diagnostics]
    return {o["key"]: o["si_value"] for o in s.outputs}


def check_case(cid, fn, rel=1e-6, **over):
    x = si_inputs(cid, **over)
    expected = fn(x)
    got = solved(cid, **over)
    missing = set(expected) - set(got)
    assert not missing, f"{cid}: not computed: {missing}"
    for k, v in expected.items():
        assert got[k] == pytest.approx(v, rel=rel, abs=1e-300), (cid, k, got[k], v)
    outputs = set(CAT.get(cid).outputs)
    assert outputs <= set(expected), f"{cid}: outputs without an independent check: {outputs - set(expected)}"
