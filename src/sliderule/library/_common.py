"""Shared physical constants (CODATA / ISO 80000 values)."""

from ..core import C


def g0() -> "C":
    return C("g", "Standard gravity", 9.80665, "m/s^2", note="exact, by definition (ISO 80000-3)")


def R_univ() -> "C":
    return C("R", "Universal gas constant", 8.314462618, "J/(mol*K)", latex=r"R_u", note="exact since the 2019 SI redefinition")


def kB() -> "C":
    return C("kB", "Boltzmann constant", 1.380649e-23, "J/K", latex=r"k_B", note="exact (SI 2019)")


def planck() -> "C":
    return C("hP", "Planck constant", 6.62607015e-34, "J*s", latex=r"h", note="exact (SI 2019)")


def c0() -> "C":
    return C("c0", "Speed of light in vacuum", 299792458, "m/s", latex=r"c", note="exact")


def qe() -> "C":
    return C("qe", "Elementary charge", 1.602176634e-19, "C", latex=r"q", note="exact (SI 2019)")


def faraday() -> "C":
    return C("Fc", "Faraday constant", 96485.33212, "C/mol", latex=r"F")


def eps0() -> "C":
    return C("eps0", "Vacuum permittivity", 8.8541878128e-12, "F/m", latex=r"\varepsilon_0")


def mu0() -> "C":
    return C("mu0", "Vacuum permeability", 1.25663706212e-6, "H/m", latex=r"\mu_0")


def sigma_sb() -> "C":
    return C("sSB", "Stefan–Boltzmann constant", 5.670374419e-8, "W/(m^2*K^4)", latex=r"\sigma_{SB}")


def G_grav() -> "C":
    return C("Gn", "Gravitational constant", 6.67430e-11, "m^3/(kg*s^2)", latex=r"G")


def avogadro() -> "C":
    return C("NA", "Avogadro constant", 6.02214076e23, "1/mol", latex=r"N_A", note="exact (SI 2019)")


def m_e() -> "C":
    return C("me", "Electron mass", 9.1093837015e-31, "kg", latex=r"m_e")


def rydberg() -> "C":
    return C("Rinf", "Rydberg constant", 10973731.568160, "1/m", latex=r"R_\infty")


def bohr_radius() -> "C":
    return C("a0", "Bohr radius", 5.29177210903e-11, "m", latex=r"a_0")


def wien_b() -> "C":
    return C("bW", "Wien displacement constant", 2.897771955e-3, "m*K", latex=r"b")
