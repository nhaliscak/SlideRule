"""Equation-audit fill, electrical B: RF, noise, filters, analog and digital electronics, communications, photonics, power electronics, sensors, EMC."""

import cmath
import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize, signal, special, stats

pi = math.pi
c = 299792458.0
kB = 1.380649e-23
mu0 = 1.25663706212e-6
eps0 = 8.8541878128e-12


def line(x):
    Zc, RL, bl = x["Zc"], x["RL"], 2 * pi * x["ln"]
    Zin = Zc * (RL + 1j * Zc * math.tan(bl)) / (Zc + 1j * RL * math.tan(bl))
    G = (RL - Zc) / (RL + Zc)
    return {"co": math.cos(bl), "si": math.sin(bl), "Zr": Zin.real, "Zi": Zin.imag, "Za": abs(Zin), "Gm": G, "sw": (1 + abs(G)) / (1 - abs(G)), "rl": -20 * math.log10(abs(G))}


def antenna(x):
    lam = c / x["f"]
    return {"lam": lam, "Ad": x["ed"] * 1.64 * lam**2 / (4 * pi), "Gd": 10 * math.log10(x["ed"] * 1.64), "Gp": 10 * math.log10(x["ea"] * (pi * x["Dd"] / lam) ** 2), "bw": math.radians(70 * lam / x["Dd"]), "Ae": x["ea"] * pi * x["Dd"] ** 2 / 4}


def radar(x):
    lam = c / x["f"]
    Sm = kB * 290 * x["B"] * x["F"] * x["snr"]
    K = x["Pt"] * x["G"] ** 2 * lam**2 * x["sg"] / (4 * pi) ** 3
    Rm = (K / Sm) ** 0.25
    assert K / Rm**4 == pytest.approx(Sm)                                              # the echo at the maximum range is the minimum detectable signal
    return {"lam": lam, "Sm": Sm, "Rm": Rm, "Pr": K / x["R"] ** 4}


def noise(x):
    F = x["F1"] + (x["F2"] - 1) / x["G1"] + (x["F3"] - 1) / (x["G1"] * x["G2"])
    N = kB * 290 * x["B"]
    return {"Ft": F, "NF": 10 * math.log10(F), "Te": 290 * (F - 1), "Nth": N, "Smin": N * F * x["snr"]}


def filters(x):
    Ap, As, fp, fs = x["Ap"], x["As"], x["fp"], x["fs"]
    nb, _ = signal.buttord(2 * pi * fp, 2 * pi * fs, Ap, As, analog=True)
    nc, _ = signal.cheb1ord(2 * pi * fp, 2 * pi * fs, Ap, As, analog=True)
    fc = fp / (10 ** (Ap / 10) - 1) ** (1 / (2 * nb))
    assert 10 * math.log10(1 + (fp / fc) ** (2 * nb)) == pytest.approx(Ap)                # the passband loss at fp is exactly Ap
    return {"nB": nb, "nC": nc, "fc": fc, "Ab": 10 * math.log10(1 + (fs / fc) ** (2 * nb))}


def sallen(x):
    Q, f0, C2 = x["Qf"], x["f0"], x["C2"]
    C1 = 4 * Q**2 * C2
    R = 1 / (4 * pi * Q * f0 * C2)
    H = lambda f: 1 / ((1j * 2 * pi * f) ** 2 * R**2 * C1 * C2 + 2 * 1j * 2 * pi * f * R * C2 + 1)       # transfer function of the circuit
    assert 1 / (R * math.sqrt(C1 * C2)) == pytest.approx(2 * pi * f0)
    return {"C1": C1, "R": R, "Gq": abs(H(f0))}


def bjt(x):
    Vth = x["Vcc"] * x["R2"] / (x["R1"] + x["R2"])
    Rth = x["R1"] * x["R2"] / (x["R1"] + x["R2"])
    IB = (Vth - 0.7) / (Rth + (x["be"] + 1) * x["RE"])
    IC = x["be"] * IB
    VCE = x["Vcc"] - IC * x["RC"] - (IC + IB) * x["RE"]
    gm = IC / 0.02585
    rp = x["be"] / gm
    assert Vth - IB * Rth - 0.7 - (IC + IB) * x["RE"] == pytest.approx(0, abs=1e-9)         # base-loop KVL
    return {"Vth": Vth, "Rth": Rth, "IB": IB, "IC": IC, "VCE": VCE, "gm": gm, "rp": rp, "Av": -gm * x["RC"] * x["RL"] / (x["RC"] + x["RL"]), "Zi": 1 / (1 / x["R1"] + 1 / x["R2"] + 1 / rp)}


def mosfet(x):
    gm, ro = 2 * x["ID"] / x["Vov"], 1 / (x["la"] * x["ID"])
    par = lambda *r: 1 / sum(1 / v for v in r)
    return {"gm": gm, "ro": ro, "Rout": par(x["RD"], ro), "Av": -gm * par(x["RD"], ro, x["RL"]), "ai": gm * ro}


def timer(x):
    Rc = (x["R1"] + x["R2"]) * x["Ct"]
    # charging toward Vcc from Vcc/3 until the capacitor reaches 2Vcc/3: v(t) = Vcc - (2/3)Vcc exp(-t/RC)
    th = optimize.brentq(lambda t: 1 - 2 / 3 * math.exp(-t / Rc) - 2 / 3, 1e-12, 100 * Rc)
    Rd = x["R2"] * x["Ct"]
    tl = optimize.brentq(lambda t: 2 / 3 * math.exp(-t / Rd) - 1 / 3, 1e-12, 100 * Rd)            # discharging from 2Vcc/3 to Vcc/3
    tm = optimize.brentq(lambda t: 1 - math.exp(-t / (x["Rm"] * x["Ct"])) - 2 / 3, 1e-12, 100 * x["Rm"] * x["Ct"])   # monostable: from 0 to 2Vcc/3
    return {"th": th, "tl": tl, "f": 1 / (th + tl), "dc": th / (th + tl), "tm": tm}


def opamp(x):
    Vth = x["Vs"] * x["Rg"] / (x["Rg"] + x["Rh"])
    return {"Ai": -x["Rf"] / x["Rin"], "An": 1 + x["Rf"] / x["Rin"], "Vo": -x["Rf"] * (x["V1"] / x["Rin"] + x["V2"] / x["R2"]), "sl": -x["Vi"] / (x["Rin"] * x["Ci"]), "Vth": Vth, "hy": 2 * Vth}


def pll(x):
    K = x["Ko"] * x["Kd"]
    # closed loop denominator s^2 + (K t2/t1) s + K/t1: read wn and zeta off the polynomial
    b1, b0 = K * x["t2"] / x["t1"], K / x["t1"]
    wn = math.sqrt(b0)
    ze = b1 / (2 * wn)
    return {"wn": wn, "ze": ze, "wl": 2 * ze * wn, "BL": wn / 2 * (ze + 1 / (4 * ze))}


def timing(x):
    T = x["tcq"] + x["tl"] + x["ts"] + x["tk"]
    return {"Tmin": T, "fmax": 1 / T, "ss": 1 / x["fclk"] - T, "hs": x["tcq"] + x["tm"] - x["th"] - x["tk"]}


def microstrip(x):
    u = x["W"] / x["h"]
    ee = (x["er"] + 1) / 2 + (x["er"] - 1) / 2 * (1 / math.sqrt(1 + 12 / u) + (0.04 * (1 - u) ** 2 if u < 1 else 0))
    Z = 60 / math.sqrt(ee) * math.log(8 / u + u / 4) if u <= 1 else 120 * pi / (math.sqrt(ee) * (u + 1.393 + 0.667 * math.log(u + 1.444)))
    return {"u": u, "ee": ee, "Z0": Z, "lg": c / (x["f"] * math.sqrt(ee)), "td": math.sqrt(ee) / c}


def kaiser(x):
    n, beta = signal.kaiserord(x["A"], x["df"] / (x["fs"] / 2))
    return {"be": signal.kaiser_beta(x["A"]), "Nt": n, "dl": (n - 1) / (2 * x["fs"])}


def iir(x):
    al = 1 - math.exp(-2 * pi * x["fc"] / x["fs"])
    b, a = [al], [1, -(1 - al)]
    w, h = signal.freqz(b, a, worN=[2 * pi * x["f"] / x["fs"]])
    wh = optimize.brentq(lambda w_: abs(signal.freqz(b, a, worN=[w_])[1][0]) - 1 / math.sqrt(2), 1e-6, pi - 1e-6)
    return {"al": al, "Hm": abs(h[0]), "tau": -1 / math.log(1 - al), "fh": wh * x["fs"] / (2 * pi)}


def ber(x):
    e = x["EbN0"]
    return {"Pb": stats.norm.sf(math.sqrt(2 * e)), "Pq": 3 / 8 * special.erfc(math.sqrt(2 / 5 * e)), "Pf": 0.5 * math.exp(-e / 2), "Qv": stats.norm.sf(math.sqrt(2 * e))}


def hamming(x):
    n = 2 ** round(x["r"]) - 1
    k = n - round(x["r"])
    p = x["p"]
    return {"n": n, "k": k, "Rc": k / n, "Pu": 1 - (1 - p) ** k, "Pc": float(stats.binom.sf(1, n, p))}                  # more than one error in n bits


def fibre(x):
    Lt = x["al"] * x["Lk"] + x["nc"] * x["lc"] + x["ns"] * x["ls"]
    Prx = x["Ptx"] * 10 ** (-Lt / 10)
    dt = x["Dc"] * x["Lk"] * x["dl"]
    return {"Lt": Lt, "Prx": Prx, "mg": 10 * math.log10(Prx / x["Rs"]), "dt": dt, "Bm": 0.25 / dt}


def laser(x):
    h, e = 6.62607015e-34, 1.602176634e-19
    am = math.log(1 / (x["R1"] * x["R2"])) / (2 * x["Lc"])
    return {"am": am, "gth": x["ai"] + am, "P": x["ed"] * h * c / (x["lam"] * e) * (x["Id"] - x["Ith"]), "fsr": c / (2 * x["ng"] * x["Lc"])}


def array(x):
    Ne, d, th, b = int(round(x["Ne"])), x["d"], x["th"], x["bs"]
    psi = 2 * pi * d * math.cos(th) + b
    AF = abs(sum(cmath.exp(1j * n * psi) for n in range(Ne))) / Ne                             # direct sum of the element phasors
    return {"ps": psi, "AF": AF, "bw": 0.886 / (Ne * d), "Dr": 10 * math.log10(2 * Ne * d)}


def solar(x):
    Vt = x["n"] * kB * x["T"] / 1.602176634e-19
    Iph, I0 = x["Iph"], x["I0"]
    Voc = Vt * math.log(Iph / I0 + 1)
    Pm = optimize.minimize_scalar(lambda v: -v * (Iph - I0 * (math.exp(v / Vt) - 1)), bounds=(0.1, Voc), method="bounded", options={"xatol": 1e-12}).fun * -1       # maximum power point by search
    return {"Vt": Vt, "Voc": Voc, "FF": Pm / (Voc * Iph), "Pm": Pm, "et": Pm / x["Gi"], "Iq": Iph - I0 * (math.exp(x["Vq"] / Vt) - 1)}


def inverter(x):
    n = np.arange(1, 20001, 2)
    V1 = 4 * x["Vdc"] / (pi * math.sqrt(2))
    amp = V1 / n
    # the infinite-series THD from a long partial sum, and the rms of the square wave from its Parseval sum
    return {"V1": V1, "V3": V1 / 3, "V5": V1 / 5, "V7": V1 / 7, "th3": math.sqrt(sum((V1 / k) ** 2 for k in (3, 5, 7))) / V1, "thi": math.sqrt(np.sum(amp[1:] ** 2)) / V1, "Vp": x["ma"] * x["Vdc"] / math.sqrt(2), "Vr": math.sqrt(np.sum(amp**2))}


def buckboost(x):
    D = x["D"]
    Vbb = x["Vin"] * D / (1 - D)
    # inductor energy balance: average inductor current from the load current referred to the switching interval
    Io = Vbb / x["Rl"]
    return {"Vbb": Vbb, "Vfb": x["Vin"] * D * x["nt"] / (1 - D), "dI": x["Vin"] * D / (x["L"] * x["fs"]), "IL": Io / (1 - D), "Lc": (1 - D) ** 2 * x["Rl"] / (2 * x["fs"]), "cc": 1.0 if x["L"] >= (1 - D) ** 2 * x["Rl"] / (2 * x["fs"]) else 0.0}


def rectifier(x):
    Vm, al = x["Vm"], x["al"]
    full = integrate.quad(lambda th: Vm * math.sin(th), al, pi + al)[0] / pi                    # average of |v| from the firing angle
    half = integrate.quad(lambda th: Vm * math.sin(th), al, pi)[0] / pi                          # one thyristor-controlled half-cycle plus a diode half-cycle
    wave = integrate.quad(lambda th: Vm * math.sin(th), al, pi)[0] / (2 * pi)
    return {"Vf": full, "Vh": half, "Vw": wave, "If": full / x["Rl"], "pf": math.cos(al)}


def sensors(x):
    return {"Vt": x["Sk"] * (x["Tj"] - x["Tr"]), "Tm": x["Tr"] + x["Vm"] / x["Sk"], "Vl": x["sv"] * x["Ve"] * x["x"], "Cp": eps0 * x["er"] * x["Ap"] / x["g"], "Sc": -eps0 * x["er"] * x["Ap"] / x["g"] ** 2}


def emc(x):
    sig = x["sr"] * 5.8e7
    delta = 1 / math.sqrt(pi * x["f"] * mu0 * x["mr"] * sig)
    A = 20 * math.log10(math.e) * x["t"] / delta
    R = 168 - 10 * math.log10(x["mr"] * x["f"] / x["sr"])
    return {"dl": delta, "A": A, "Rl": R, "SE": A + R}


def pcb(x):
    mil2 = 6.4516e-4 * 1e-6                                                                  # one square mil in m^2
    Ar = x["w"] * x["tc"]
    k = x["kx"]
    Im = k * x["dT"] ** 0.44 * (Ar / mil2) ** 0.725
    Aq = mil2 * (x["Id"] / (k * x["dT"] ** 0.44)) ** (1 / 0.725)
    return {"Ar": Ar, "Im": Im, "Aq": Aq, "wq": Aq / x["tc"]}


def crosstalk(x):
    tp = math.sqrt(x["ee"]) / c
    lc = x["tr"] / (6 * tp)
    return {"BW": 0.35 / x["tr"], "tp": tp, "lc": lc, "tl": tp * x["Lt"], "tx": 1.0 if x["Lt"] > lc else 0.0, "Kb": (x["kc"] + x["kl"]) / 4}


def surge(x):
    Vs = x["Is"] * x["Zl"] / 2
    kt = 2 * x["Zt"] / (x["Zl"] + x["Zt"])
    pm = x["BIL"] / x["Vres"] - 1
    assert kt - (1 + (x["Zt"] - x["Zl"]) / (x["Zl"] + x["Zt"])) == pytest.approx(0)       # transmitted wave = incident + reflected
    return {"Vs": Vs, "kt": kt, "kr": (x["Zt"] - x["Zl"]) / (x["Zl"] + x["Zt"]), "Vtr": kt * Vs, "pm": pm, "ok": 1.0 if pm >= 0.2 else 0.0}


def twowire(x):
    D, r = x["D"], x["r"]
    ac = math.acosh(D / (2 * r))
    Le = mu0 * ac / pi
    Cl = pi * eps0 / ac
    return {"ac": ac, "Cl": Cl, "Le": Le, "Lt": Le + mu0 / (4 * pi), "Z0": math.sqrt(Le / Cl)}


CASES = {
    "electrical.rf.lossless_line_input_impedance": (line, 1e-9), "electrical.rf.antenna_dipole_dish": (antenna, 1e-9), "electrical.rf.radar_range_equation": (radar, 1e-9), "electrical.rf.noise_figure_cascade_sensitivity": (noise, 1e-9),
    "electrical.filters.butterworth_chebyshev_order": (filters, 1e-9), "electrical.filters.sallen_key_lowpass": (sallen, 1e-9), "electrical.analog.bjt_bias_small_signal": (bjt, 1e-9), "electrical.analog.mosfet_common_source_gain": (mosfet, 1e-9),
    "electrical.analog.timer_555": (timer, 1e-9), "electrical.analog.opamp_circuits": (opamp, 1e-9), "electrical.analog.pll_second_order": (pll, 1e-9), "electrical.digital.timing_budget": (timing, 1e-9),
    "electrical.rf.microstrip_impedance": (microstrip, 1e-9), "electrical.dsp.kaiser_fir_design": (kaiser, 1e-3), "electrical.dsp.first_order_iir_lowpass": (iir, 1e-5), "electrical.comms.ber_digital_modulation": (ber, 1e-9),
    "electrical.comms.hamming_code": (hamming, 1e-9), "electrical.photonics.fibre_link_budget_dispersion": (fibre, 1e-9), "electrical.photonics.laser_diode_threshold": (laser, 1e-9), "electrical.rf.array_factor_uniform_linear": (array, 1e-9),
    "electrical.energy.solar_cell_iv_fill_factor": (solar, 1.2e-2), "electrical.power_electronics.inverter_harmonics_thd": (inverter, 1e-4), "electrical.power_electronics.buckboost_flyback": (buckboost, 1e-9),
    "electrical.power_electronics.controlled_rectifier": (rectifier, 1e-9), "electrical.instrumentation.thermocouple_lvdt_capacitive": (sensors, 1e-9), "electrical.emc.shielding_effectiveness": (emc, 1e-9),
    "electrical.pcb.trace_current_ipc2221": (pcb, 1e-9), "electrical.signal_integrity.rise_time_crosstalk": (crosstalk, 1e-9), "electrical.power.surge_arrester_margin": (surge, 1e-9), "electrical.em.two_wire_line_parameters": (twowire, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    q = solved("electrical.rf.lossless_line_input_impedance", ln="0.25", RL="100 ohm")
    assert q["Zr"] == pytest.approx(25, rel=1e-9) and abs(q["Zi"]) < 1e-9                                       # quarter wave: Zc^2/RL
    h = solved("electrical.rf.lossless_line_input_impedance", ln="0.5", RL="100 ohm")
    assert h["Zr"] == pytest.approx(100, rel=1e-9)                                                                 # half wave: the load itself
    assert solved("electrical.rf.microstrip_impedance", W="3.0 mm")["Z0"] == pytest.approx(50, abs=2.5)           # FR-4, 1.6 mm: about 50 ohm
    assert solved("electrical.em.two_wire_line_parameters", D="300 mm", r="3 mm")["Z0"] == pytest.approx(120 * math.log(100), rel=1e-3)   # the large-spacing form
    assert solved("electrical.comms.ber_digital_modulation", EbN0="9.1201")["Pb"] == pytest.approx(1e-5, rel=0.1)    # BPSK needs 9.6 dB for 1e-5 (9.12 linear)
    assert solved("electrical.comms.hamming_code", r="3")["Rc"] == pytest.approx(4 / 7) and solved("electrical.comms.hamming_code", r="4")["k"] == 11    # Hamming (7,4) and (15,11)
    assert solved("electrical.power_electronics.inverter_harmonics_thd")["thi"] == pytest.approx(0.4834, abs=1e-3)   # the square wave's 48.3 %
    assert solved("electrical.power_electronics.controlled_rectifier", al="0 deg")["Vf"] == pytest.approx(2 * 325 / pi)
    assert solved("electrical.power_electronics.controlled_rectifier", al="90 deg")["Vf"] == pytest.approx(0, abs=1e-9)
    assert solved("electrical.analog.timer_555")["dc"] > 0.5
    assert solved("electrical.filters.butterworth_chebyshev_order")["nC"] <= solved("electrical.filters.butterworth_chebyshev_order")["nB"]       # Chebyshev never needs more


def test_catalogued_in_their_sub_disciplines():
    for cid in CASES:
        c_ = CAT.get(cid)
        assert c_.subdisciplines and c_.references and c_.example
