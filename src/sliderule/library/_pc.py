"""Compact builders and shared references for the core physics and chemistry calculations."""

from ..core import Calculation

HRW = "Halliday, Resnick & Walker, Fundamentals of Physics"
YF = "Young & Freedman, University Physics"
SJ = "Serway & Jewett, Physics for Scientists and Engineers"
TAYLOR = "Taylor, Classical Mechanics"
FOX = "Fox & McDonald, Introduction to Fluid Mechanics"
SCHROEDER = "Schroeder, An Introduction to Thermal Physics"
HECHT = "Hecht, Optics"
GRIFFITHS = "Griffiths, Introduction to Electrodynamics"
KRANE = "Krane, Modern Physics"
KITTEL = "Kittel, Introduction to Solid State Physics"
CARROLL = "Carroll & Ostlie, An Introduction to Modern Astrophysics"
ATKINS = "Atkins & de Paula, Physical Chemistry"
BROWN = "Brown et al., Chemistry: The Central Science"
HARRIS = "Harris, Quantitative Chemical Analysis"
HOUSECROFT = "Housecroft & Sharpe, Inorganic Chemistry"
CLAYDEN = "Clayden, Greeves & Warren, Organic Chemistry"


def _build(discipline, cid, name, subs, desc, variables, equations, outputs, example, ref, assume, extra, tags, validity):
    return Calculation(
        id=cid, name=name, disciplines=[discipline, *extra], subdisciplines=list(subs), description=desc, variables=variables,
        equations=equations, outputs=outputs, tags=list(tags), assumptions=[assume] if isinstance(assume, str) else list(assume),
        references=[ref] if isinstance(ref, str) else list(ref), example=example, validity=list(validity))


def phys(cid, name, subs, desc, variables, equations, outputs, example, ref, assume, *, extra=(), tags=(), validity=()):
    return _build("physics", cid, name, subs, desc, variables, equations, outputs, example, ref, assume, extra, tags, validity)


def chem(cid, name, subs, desc, variables, equations, outputs, example, ref, assume, *, extra=(), tags=(), validity=()):
    return _build("chemistry", cid, name, subs, desc, variables, equations, outputs, example, ref, assume, extra, tags, validity)
