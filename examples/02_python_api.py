"""SlideRule as a Python library. Run it with:  python examples/02_python_api.py   (after `pip install .`)

Every function takes and returns plain dicts, so the same calls work over HTTP (see 03_http_api.py).
"""

from sliderule import api

# 1. Solve a calculation. Inputs are strings with units (or {"value": 200, "unit": "GPa"}).
r = api.solve(
    "civil.column.euler_buckling",
    {"E": "200 GPa", "I": "8.0e-6 m^4", "L": "3 m", "K": "1"},
    solve_for=["Pcr"],
    output_units={"Pcr": "kN"},
)
pcr = r["outputs"][0]
print(f"Pcr = {pcr['value']:.1f} {pcr['unit']}")                       # Pcr = 1754.6 kN

# 2. The worked solution is data too: a title and a list of LaTeX lines per section.
for section in r["steps"]["numeric"][:3]:
    print("-", section["title"])

# 3. Solve backwards: any variable can be the unknown, the equations are rearranged.
r = api.solve("civil.column.euler_buckling", {"Pcr": "2000 kN", "E": "200 GPa", "L": "3 m", "K": "1"},
              solve_for=["I"], output_units={"I": "mm^4"})
print(f"I = {r['outputs'][0]['value']:.4g} mm^4")                      # I = 9.119e+06 mm^4

# 4. Sweep one input: how does the load change with the column length? (the swept input is given as {"value", "unit"})
s = api.sweep("civil.column.euler_buckling", {"E": "200 GPa", "I": "8.0e-6 m^4", "L": {"value": 3, "unit": "m"}, "K": "1"},
              vary="L", values=[2, 3, 4, 5], solve_for=["Pcr"], output_units={"Pcr": "kN"})
print(f"L ({s['x_unit']}):", s["x"], " Pcr (kN):", [round(v) for v in s["series"][0]["y"]])

# 5. Property data with its source: the modulus of 6061-T6 aluminium, then used in a calculation
e = api.data_value("materials-typical", "aluminium-6061-t6", "youngs_modulus", unit="GPa")
print(f"E = {e['value']} {e['unit']}  [{e['basis']}; {e['pack']} v{e['pack_version']}]")
r = api.solve("civil.column.euler_buckling", {"E": f"{e['value']} GPa", "I": "8.0e-6 m^4", "L": "3 m", "K": "1"},
              solve_for=["Pcr"], output_units={"Pcr": "kN"})
print(f"The same column in 6061-T6 aluminium: Pcr = {r['outputs'][0]['value']:.0f} kN")

# 6. A temperature-dependent property (a curve): water viscosity at 20 degC, with its source
v = api.data_value("fluids-coolprop", "water-liquid", "dynamic_viscosity", 20, "degC", unit="mPa*s")
print(f"water at 20 degC: {v['value']:.4f} {v['unit']}  [{v['basis']}]")

# 7. Unit conversion with the working
c = api.convert(120, "km/h", "m/s")
print(c["value_text"], c["unit"])                                          # 33.3333 m/s
