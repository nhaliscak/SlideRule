import math
from fractions import Fraction

import pytest

from sliderule.units import Dimension, UnitError, convert, default_registry, parse_unit

reg = default_registry()


@pytest.mark.parametrize("value,src,dst,expected", [
    (1, "kN", "N", 1000),
    (1, "psi", "kPa", 6.894757293168361),
    (1, "ft", "in", 12),
    (1, "mi", "km", 1.609344),
    (1, "atm", "Pa", 101325),
    (1, "bar", "psi", 14.503773773),
    (1, "hp", "kW", 0.74569987158227),
    (1, "Btu", "kJ", 1.05505585262),
    (1, "bbl", "L", 158.987294928),
    (1, "gal", "L", 3.785411784),
    (1, "lbf", "N", 4.4482216152605),
    (1, "lbm", "kg", 0.45359237),
    (60, "rpm", "rad/s", 2 * math.pi),
    (1, "acre", "m^2", 4046.8564224),
    (1, "kip/in^2", "MPa", 6.894757293168361),
    (1, "Btu/(h*ft^2*degF)", "W/(m^2*K)", 5.678263340863),
    (1, "mD", "m^2", 9.869233e-16),
    (10, "ppg", "kg/m^3", 1198.26427),
    (1, "day", "h", 24),
])
def test_conversions(value, src, dst, expected):
    assert convert(value, src, dst) == pytest.approx(expected, rel=1e-8)


@pytest.mark.parametrize("c,f", [(-40, -40), (0, 32), (100, 212), (37, 98.6)])
def test_temperature_scales_are_affine(c, f):
    assert convert(c, "degC", "degF") == pytest.approx(f)
    assert convert(f, "degF", "degC") == pytest.approx(c)
    assert convert(c, "degC", "K") == pytest.approx(c + 273.15)
    assert convert(f, "degF", "degR") == pytest.approx(f + 459.67)


def test_temperature_difference_has_no_offset():
    assert convert(10, "delta_degC", "delta_degF") == pytest.approx(18)
    assert parse_unit("degC", as_delta=True).shift == 0
    assert parse_unit("degC").shift == 273.15
    # inside a compound unit, the scale is a difference
    assert parse_unit("W/(m*degC)").shift == 0


def test_dimension_algebra_and_fractions():
    manning = parse_unit("s/m^(1/3)")
    assert manning.dim == Dimension.of(s=1, m=Fraction(-1, 3))
    assert (manning.dim ** 3).exps[1] == -1
    assert parse_unit("N").dim == parse_unit("kg*m/s^2").dim
    assert parse_unit("J").dim == parse_unit("N*m").dim == parse_unit("W*s").dim


def test_prefixes_and_collisions():
    assert parse_unit("kg").dim == Dimension.of(kg=1)
    assert parse_unit("min").factor == 60          # minute, not milli-inch
    assert parse_unit("mi").factor == pytest.approx(1609.344)   # mile, not milli-?
    assert parse_unit("cd").dim == Dimension.of(cd=1)
    assert parse_unit("um").symbol == "µm"
    assert parse_unit("Mbbl").factor == pytest.approx(1000 * 0.158987294928)
    assert "oilfield" in parse_unit("Mbbl").notes[0]


@pytest.mark.parametrize("bad,fragment", [
    ("lb", "lbm"), ("ton", "ton_US"), ("m2", "m^2"), ("foo", "unknown"),
    ("N m", "'*'"), ("kdegC", "unknown"), ("m/(s", "missing"),
])
def test_bad_units_explain_themselves(bad, fragment):
    with pytest.raises(UnitError) as e:
        parse_unit(bad)
    assert fragment in str(e.value)


def test_dimension_mismatch_in_convert():
    with pytest.raises(UnitError) as e:
        convert(1, "psi", "N")
    assert e.value.code == "DIM_MISMATCH" and "pressure" in str(e.value) and "force" in str(e.value)


def test_system_classification():
    assert parse_unit("psi").systems == {"USC"}
    assert parse_unit("kPa").systems == {"SI"}
    assert {"SI", "USC"} <= parse_unit("lbf/m^2").systems
    assert parse_unit("h").systems == {"any"}


def test_hz_is_per_second_and_rpm_is_angular():
    assert convert(1, "Hz", "1/s") == 1
    assert convert(1, "rpm", "rad/s") == pytest.approx(0.10471975511965977)


def test_unit_picker_lists_are_dimension_correct():
    dim = parse_unit("Pa").dim
    units = [u["symbol"] for u in reg.units_for(dim)]
    assert units[0] == "Pa" and {"psi", "MPa", "bar", "ksi"} <= set(units)
    assert all(parse_unit(u).dim == dim for u in units)
    delta = [u["symbol"] for u in reg.units_for(parse_unit("K").dim, delta=True)]
    assert "°C" not in delta and "Δ°C" in delta


def test_every_compound_unit_in_picker_parses():
    for e in reg._compounds:  # noqa: SLF001
        parse_unit(e)


def test_gauge_pressure_is_an_offset_unit_like_celsius():
    assert parse_unit("psig").to_si(0) == pytest.approx(101325)          # 0 psig is one atmosphere absolute
    assert parse_unit("psig").to_si(100) == pytest.approx(101325 + 100 * 6894.757293168361)
    assert parse_unit("barg").to_si(2) == pytest.approx(3.01325e5)
    assert parse_unit("kPag").from_si(101325 + 5e5) == pytest.approx(500)
    assert parse_unit("psig/ft").shift == 0.0                              # a gauge gradient is a difference: no offset
