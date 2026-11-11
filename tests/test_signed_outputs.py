"""A quantity that comes out negative in a calculation's own example must be declared signed: otherwise its value cannot be typed back in
(the engine refuses a negative number for an unsigned quantity), so the inverse problem can never be posed with the example's own numbers."""

from sliderule import api
from sliderule.core.catalog import default_catalog


def test_outputs_that_are_negative_in_the_example_are_declared_signed():
    bad = []
    for c in default_catalog():
        r = api.solve(c.id, dict(api.get_calculation(c.id)["example"]), sig_figs=6)
        byk = {v.key: v for v in c.variables}
        for rec in r.get("outputs", []) + r.get("intermediates", []):
            v = byk.get(rec["key"])
            if v is not None and not v.signed and not v.is_constant and rec["si_value"] < 0:
                bad.append((c.id, rec["key"], rec["value"]))
    assert bad == []
