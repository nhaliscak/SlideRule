"""Unit definitions. Every non-base unit is defined as a multiple of earlier ones, so the
numbers here are the authoritative *definitions* (exact where the standards make them exact)."""

from __future__ import annotations

import math

from .dimension import Dimension
from .registry import UnitRegistry

D = Dimension.of


def populate(r: UnitRegistry) -> None:
    d, b = r.define, r.define_base

    # ---- SI base units (gram is the prefix anchor for mass, so 'kg' parses as k+g)
    b("g", D(kg=1), 1e-3, suggest="mµ", label="gram")
    b("m", D(m=1), suggest="kcmµn", label="metre")
    b("s", D(s=1), suggest="mµn", label="second")
    b("A", D(A=1), suggest="mµk", label="ampere")
    b("K", D(K=1), suggest="m", label="kelvin")
    b("mol", D(mol=1), suggest="kmµ", label="mole")
    b("cd", D(cd=1), label="candela")
    b("USD", D(cur=1), system="any", suggest="kM", label="US dollar (generic currency unit)")

    # ---- dimensionless / angle (radian is exactly 1; the cycle is what carries 2π)
    d("rad", "1", "any", label="radian")
    d("sr", "1", "any", label="steradian")
    d("deg|°", f"{math.pi}/180", "any", label="degree (angle)")
    d("arcmin", f"{math.pi}/(180*60)", "any", label="arcminute")
    d("arcsec", f"{math.pi}/(180*3600)", "any", label="arcsecond")
    d("rev", f"{2 * math.pi}", "any", label="revolution (angle: 2π rad)")
    d("cycle", "1", "any", label="cycle (count)")
    d("%|percent", "0.01", "any", label="percent")
    d("ppm", "1e-6", "any", label="parts per million")
    d("ppb", "1e-9", "any", label="parts per billion")
    d("ea|pcs|each", "1", "any", label="count")
    d("RU", "1", "any", label="response unit (biosensor, arbitrary scale)")
    d("bit", "1", "any", True, "kMG", label="bit")
    d("byte|B", "8*bit", "any", True, "kMGT", label="byte")
    d("KiB", "1024*byte", "any", label="kibibyte")
    d("MiB", "1024*KiB", "any", label="mebibyte")
    d("GiB", "1024*MiB", "any", label="gibibyte")
    d("TiB", "1024*GiB", "any", label="tebibyte")
    d("pps", "1/s", "any", True, "kMG", label="packets per second")
    d("FLOP", "1", "any", True, "kMGTP", label="floating-point operation")
    d("MIPS", "1e6/s", "any", label="million instructions per second")
    d("pcm", "1e-5", "any", label="per cent mille (reactivity)")
    d("dB", "1", "any", note="decibel is a logarithmic level, not a linear unit: it cannot be converted to or mixed with other units", label="decibel")

    # ---- time
    d("min", "60*s", "any", label="minute")
    d("h|hr", "3600*s", "any", label="hour")
    d("day|d", "86400*s", "any", label="day")
    d("week|wk", "7*day", "any", label="week")
    d("bpm", "1/min", "any", label="beats per minute")
    d("rpm", "rev/min", "any", note="rpm is an angular speed (1 rpm = 0.1047 rad/s). For a frequency in cycles per minute use 'cycle/min'", label="revolutions per minute")
    d("yr|year", "365.25*day", "any", label="year (Julian)")
    d("month|mo", "yr/12", "any", label="month (1/12 Julian year)")

    # ---- SI derived (all prefixable)
    d("N", "kg*m/s^2", "SI", True, "kM", label="newton")
    d("Pa", "N/m^2", "SI", True, "kMG", label="pascal")
    d("J", "N*m", "SI", True, "kMG", label="joule")
    d("W", "J/s", "SI", True, "kMGm", label="watt")
    d("Hz", "1/s", "SI", True, "kMG", label="hertz")
    d("C", "A*s", "SI", True, "mµ", label="coulomb")
    d("V", "W/A", "any", True, "kmµ", label="volt")
    d("F", "C/V", "any", True, "µnp", label="farad")
    d("ohm|Ω", "V/A", "any", True, "mkM", label="ohm")
    d("S", "A/V", "any", True, "m", label="siemens")
    d("Wb", "V*s", "any", True, "m", label="weber")
    d("T", "Wb/m^2", "any", True, "mµ", label="tesla")
    d("H", "Wb/A", "any", True, "mµ", label="henry")
    d("VA", "W", "any", True, "kM", label="volt-ampere (apparent power)")
    d("var", "W", "any", True, "kM", label="volt-ampere reactive")
    d("lm", "cd*sr", "SI", True, label="lumen")
    d("lx", "lm/m^2", "SI", True, "k", label="lux")
    d("Wp", "W", "SI", True, "kM", label="watt-peak")
    d("Gy", "J/kg", "SI", True, "m", label="gray (absorbed dose)")
    d("Sv", "J/kg", "SI", True, "mµ", label="sievert (dose equivalent)")
    d("Bq", "1/s", "SI", True, "kMG", label="becquerel")
    d("Da", "1.66053906660e-27*kg", "metric", True, "k", label="dalton")
    d("Wh", "3600*J", "metric", True, "kMG", label="watt-hour")
    d("Ah", "3600*C", "any", True, "m", label="ampere-hour")
    d("eV", "1.602176634e-19*J", "metric", True, label="electronvolt")
    d("L|l", "1e-3*m^3", "metric", True, "m", label="litre")

    # ---- non-SI metric
    d("t|tonne", "1000*kg", "metric", True, "k", label="metric tonne")
    d("bar", "1e5*Pa", "metric", True, "m", label="bar")
    d("atm", "101325*Pa", "metric", label="standard atmosphere")
    d("mmHg", "133.322387415*Pa", "metric", label="millimetre of mercury")
    d("Torr", "101325/760*Pa", "metric", label="torr")
    d("kgf", "9.80665*N", "metric", label="kilogram-force")
    d("cal", "4.184*J", "metric", True, "k", label="calorie (thermochemical)")
    d("M|molar", "mol/L", "metric", True, "mµ", label="molar (mol/L)")
    d("Ci", "3.7e10*Bq", "metric", True, "mµ", label="curie")
    d("rem", "0.01*Sv", "USC", True, "m", label="rem")
    d("gee", "9.80665*m/s^2", "metric", label="standard gravity (g₀)")
    d("tex", "g/(1000*m)", "metric", True, "mk", label="tex (g/km)")
    d("den", "g/(9000*m)", "metric", label="denier (g/9 km)")
    d("bu", "35.23907017*L", "USC", label="US bushel")
    d("dm", "0.1*m", "metric", label="decimetre")
    d("ha", "1e4*m^2", "metric", label="hectare")
    d("Å|angstrom", "1e-10*m", "metric", label="ångström")
    d("AU", "1.495978707e11*m", "metric", label="astronomical unit")
    d("knot|kn", "1852/3600*m/s", "metric", label="knot")
    d("kph", "km/h", "metric", label="kilometres per hour")
    d("P", "0.1*Pa*s", "oilfield", True, "c", label="poise")
    d("St", "1e-4*m^2/s", "metric", True, "c", label="stokes")
    d("D", "9.869233e-13*m^2", "oilfield", True, "mµ", label="darcy (permeability)")
    d("°C|degC", "K", "metric", shift=273.15, label="degree Celsius (absolute scale)")
    d("Δ°C|delta_degC|ΔdegC", "K", "metric", label="Celsius degree (temperature difference)")
    d("Δ°F|delta_degF|ΔdegF", "5/9*K", "USC", label="Fahrenheit degree (temperature difference)")
    d("°R|degR", "5/9*K", "USC", label="degree Rankine")
    d("°F|degF", "5/9*K", "USC", shift=459.67, label="degree Fahrenheit (absolute scale)")

    # ---- US customary / imperial
    d("in", "0.0254*m", "USC", label="inch")
    d("ft", "12*in", "USC", label="foot")
    d("yd", "3*ft", "USC", label="yard")
    d("mi", "5280*ft", "USC", label="mile")
    d("nmi", "1852*m", "USC", label="nautical mile")
    d("mil", "0.001*in", "USC", label="mil (thou)")
    d("ac|acre", "43560*ft^2", "USC", label="acre")
    d("lbm", "0.45359237*kg", "USC", label="pound-mass")
    d("ozm", "lbm/16", "USC", label="ounce (mass)")
    d("slug", "14.59390293720637*kg", "USC", label="slug")
    d("ton_US", "2000*lbm", "USC", label="short ton")
    d("ton_UK", "2240*lbm", "USC", label="long ton")
    d("lbf", "4.4482216152605*N", "USC", label="pound-force")
    d("ozf", "lbf/16", "USC", label="ounce-force")
    d("kip", "1000*lbf", "USC", label="kip (1000 lbf)")
    d("psi", "lbf/in^2", "USC", label="pound-force per square inch")
    # gauge pressure = absolute minus one standard atmosphere (101.325 kPa), exactly like degC is kelvin minus 273.15
    d("psig", "lbf/in^2", "USC", shift=101325 / 6894.757293168361, label="pounds per square inch, gauge (above 1 atm)")
    d("barg", "1e5*Pa", "metric", shift=1.01325, label="bar, gauge (above 1 atm)")
    d("Pag", "Pa", "SI", shift=101325.0, label="pascal, gauge (above 1 atm)")
    d("kPag", "1e3*Pa", "metric", shift=101.325, label="kilopascal, gauge (above 1 atm)")
    d("MPag", "1e6*Pa", "metric", shift=0.101325, label="megapascal, gauge (above 1 atm)")
    d("ksi", "kip/in^2", "USC", label="kip per square inch")
    d("psf", "lbf/ft^2", "USC", label="pound-force per square foot")
    d("inHg", "3386.389*Pa", "USC", label="inch of mercury")
    d("inH2O", "249.08891*Pa", "USC", label="inch of water (4 °C)")
    d("Btu|BTU", "1055.05585262*J", "USC", label="British thermal unit (IT)")
    d("TR", "12000*Btu/h", "USC", label="ton of refrigeration")
    d("MMBtu", "1e6*Btu", "oilfield", note="oilfield convention: MM = million (not SI 'mega-mega')",
      label="million Btu")
    d("hp", "745.69987158227*W", "USC", label="horsepower (mechanical)")
    d("gal", "3.785411784*L", "USC", label="US gallon")
    d("gal_UK", "4.54609*L", "USC", label="imperial gallon")
    d("qt", "gal/4", "USC", label="US quart")
    d("pint_US", "gal/8", "USC", label="US pint")
    d("bbl", "42*gal", "oilfield", label="petroleum barrel (42 US gal)")
    d("Mbbl", "1000*bbl", "oilfield", note="oilfield convention: M = thousand (not SI mega)",
      label="thousand barrels")
    d("MMbbl", "1e6*bbl", "oilfield", note="oilfield convention: MM = million", label="million barrels")
    d("lbmol", "453.59237*mol", "USC", label="pound-mole")
    d("mph", "mi/h", "USC", label="miles per hour")
    d("fps", "ft/s", "USC", label="feet per second")
    d("cfs", "ft^3/s", "USC", label="cubic feet per second")
    d("cfm", "ft^3/min", "USC", label="cubic feet per minute")
    d("gpm", "gal/min", "USC", label="US gallons per minute")
    d("mgd", "1e6*gal/day", "USC", label="million US gallons per day")
    d("Mcf", "1000*ft^3", "oilfield", note="gas volume at standard conditions, thousand cubic feet (M = thousand)", label="thousand cubic feet")
    d("MMcf", "1e6*ft^3", "oilfield", note="gas volume at standard conditions, million cubic feet", label="million cubic feet")
    d("Bcf", "1e9*ft^3", "oilfield", note="gas volume at standard conditions, billion cubic feet", label="billion cubic feet")
    d("Tcf", "1e12*ft^3", "oilfield", note="gas volume at standard conditions, trillion cubic feet", label="trillion cubic feet")
    d("bpd", "bbl/day", "oilfield", label="barrels per day")
    d("ppg", "lbm/gal", "USC", label="pounds-mass per gallon (mud weight)")
    d("pcf", "lbm/ft^3", "USC", label="pounds-mass per cubic foot")
    d("fc", "lm/ft^2", "USC", label="foot-candle")

    # ---- what a dimension is *called* (first entry per dimension is its preferred SI unit)
    k = r.add_kind
    for kind, si in [
        ("dimensionless", "1"), ("length", "m"), ("mass", "kg"), ("time", "s"), ("current", "A"),
        ("temperature", "K"), ("amount of substance", "mol"), ("luminous intensity", "cd"),
        ("currency", "USD"), ("area", "m^2"), ("volume", "m^3"), ("velocity", "m/s"),
        ("acceleration", "m/s^2"), ("force", "N"), ("pressure", "Pa"), ("stress", "Pa"),
        ("energy", "J"), ("work", "J"), ("torque", "N*m"), ("power", "W"), ("frequency", "Hz"),
        ("charge", "C"), ("voltage", "V"), ("capacitance", "F"), ("resistance", "ohm"),
        ("conductance", "S"), ("magnetic flux", "Wb"), ("magnetic flux density", "T"),
        ("inductance", "H"), ("luminous flux", "lm"), ("illuminance", "lx"),
        ("density", "kg/m^3"), ("dynamic viscosity", "Pa*s"), ("kinematic viscosity", "m^2/s"),
        ("volumetric flow rate", "m^3/s"), ("mass flow rate", "kg/s"),
        ("thermal conductivity", "W/(m*K)"), ("specific heat", "J/(kg*K)"),
        ("heat transfer coefficient", "W/(m^2*K)"), ("thermal resistance (R-value)", "m^2*K/W"),
        ("heat flux", "W/m^2"), ("force per length", "N/m"), ("stiffness", "N/m"), ("surface tension", "N/m"),
        ("moment of inertia (area)", "m^4"), ("section modulus", "m^3"),
        ("specific energy", "J/kg"), ("molar mass", "kg/mol"), ("concentration (molar)", "mol/m^3"),
        ("concentration (mass)", "kg/m^3"), ("molar energy", "J/mol"), ("molar heat capacity", "J/(mol*K)"),
        ("permeability", "m^2"), ("specific weight", "N/m^3"), ("pressure gradient", "Pa/m"),
        ("heat capacity", "J/K"), ("rate (1/time)", "1/s"), ("velocity gradient", "1/s"),
        ("thermal expansion coefficient", "1/K"),
        ("momentum", "kg*m/s"), ("angular momentum", "kg*m^2/s"), ("moment of inertia (mass)", "kg*m^2"),
        ("electric field", "V/m"), ("current density", "A/m^2"), ("resistivity", "ohm*m"),
        ("power density", "W/m^3"),
        ("Manning roughness", "s/m^(1/3)"), ("luminous efficacy", "lm/W"),
        ("gravitational parameter", "m^3/s^2"),
    ]:
        k(kind, si)

    # ---- common compound units offered in UI pickers (parsed, so they cannot silently rot)
    for expr in [
        "m/s", "km/h", "mph", "ft/s", "knot", "m/s^2", "ft/s^2", "kg/m^3", "g/cm^3", "lbm/ft^3", "ppg",
        "N/m", "kN/m", "lbf/in", "lbf/ft", "Pa*s", "cP", "lbm/(ft*s)", "m^2/s", "cSt", "ft^2/s", "N*m",
        "kN*m", "lbf*ft", "lbf*in", "kip*ft", "W/(m*K)", "Btu/(h*ft*degF)", "J/(kg*K)", "kJ/(kg*K)",
        "Btu/(lbm*degF)", "W/(m^2*K)", "Btu/(h*ft^2*degF)", "m^2*K/W", "ft^2*h*degF/Btu", "W/m^2",
        "Btu/(h*ft^2)", "m^3/s", "L/s", "L/min", "m^3/h", "gpm", "cfs", "cfm", "bpd", "mgd", "kg/s",
        "kg/h", "lbm/s", "lbm/h", "N/m^3", "kN/m^3", "lbf/ft^3", "mol/L", "mol/m^3", "g/mol", "kg/mol",
        "lbm/lbmol", "J/mol", "kJ/mol", "J/(mol*K)", "1/s", "1/min", "1/h", "1/day", "1/yr", "1/K",
        "1/degC", "1/degF", "m^4", "mm^4", "in^4", "ft^4", "cm^4", "m^3", "mm^3", "in^3", "cm^3", "m^2",
        "mm^2", "cm^2", "in^2", "ft^2", "V/m", "A/m^2", "ohm*m", "ohm*mm^2/m", "Pa/m", "psi/ft", "kPa/m",
        "mD", "lm/W", "m^3/s^2", "km^3/s^2", "s/m^(1/3)", "s/ft^(1/3)", "USD/h", "USD/day", "USD/yr",
        "ea/day", "ea/h", "ea/yr", "ea/min", "USD/ea", "USD/(ea*yr)", "W/m^3", "J/kg", "kJ/kg", "Btu/lbm",
        "m^2/kg", "mg/m^3", "µg/m^3", "mg/L", "kg/(m^2*s)", "lm/m^2", "kW/m^2",
    ]:
        r.add_compound(expr)
