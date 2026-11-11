"""Equation-audit fill, industrial and computer engineering: each worked example against a different route (scipy distributions, Markov chains, exhaustive enumeration, minimisation, simulation)."""

import heapq
import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, linalg, optimize, stats

PRE = ""
HOUR, DAY, YEAR = 3600.0, 86400.0, 31557600.0


def weibull(x):
    d = stats.weibull_min(x["be"], scale=x["eta"])
    return {"Rt": d.sf(x["t"]), "ht": d.pdf(x["t"]) / d.sf(x["t"]), "Ft": d.cdf(x["t"]), "mttf": d.mean(), "b10": d.ppf(0.1), "rg": 3.0}


def sampling(x):
    n, c, p, N = int(x["n"]), int(x["c"]), x["p"], x["N"]
    Pa = stats.binom.cdf(c, n, p)
    return {"Pa": Pa, "aoq": p * Pa * (N - n) / N, "ati": n + (1 - Pa) * (N - n)}


def factorial(x):
    r = x["rep"]
    X = np.array([[1, -1, -1, 1], [1, 1, -1, -1], [1, -1, 1, -1], [1, 1, 1, 1]], float)       # columns: mean, A, B, AB at the runs (1), a, b, ab
    ybar = np.array([x["y1"], x["ya"], x["yb"], x["yab"]]) / r
    b = np.linalg.solve(X, ybar)                                                         # coded-variable regression coefficients
    ss = lambda coef: r * 4 * coef ** 2
    A = np.array([[x["n"], x["sx"]], [x["sx"], x["sxx"]]])
    b0, b1 = np.linalg.solve(A, [x["sy"], x["sxy"]])                                     # normal equations
    corr = (x["sxy"] - x["sx"] * x["sy"] / x["n"]) / math.sqrt((x["sxx"] - x["sx"] ** 2 / x["n"]) * (x["syy"] - x["sy"] ** 2 / x["n"]))
    return {"A": 2 * b[1], "B": 2 * b[2], "AB": 2 * b[3], "ssA": ss(b[1]), "FA": ss(b[1]) / x["mse"], "FB": ss(b[2]) / x["mse"], "FAB": ss(b[3]) / x["mse"], "b1": b1, "b0": b0, "r2": corr ** 2}


def inventory(x):
    D, K, h, b = x["D"], x["K"], x["h"], x["bk"]
    tc = lambda v: K * D / v[0] + h * (v[0] - v[1]) ** 2 / (2 * v[0]) + b * v[1] ** 2 / (2 * v[0])         # ordering + holding + backorder cost per year
    res = optimize.minimize(tc, [500, 100], method="Nelder-Mead", options={"xatol": 1e-9, "fatol": 1e-12, "maxiter": 5000})
    cr = x["Cu"] / (x["Cu"] + x["Co"])
    L = x["Lt"] / DAY
    ss = stats.norm.ppf(x["sl"]) * x["sd"] * DAY * math.sqrt(L)
    return {"Q": res.x[0], "Bm": res.x[1], "Tc": res.fun, "cr": cr, "qn": stats.norm.ppf(cr, x["mu"], x["sg"]), "ss": ss, "rop": x["dd"] * x["Lt"] + ss}


def forecast(x):
    Lv = x["al"] * x["At"] + (1 - x["al"]) * (x["L0"] + x["T0"])
    Tr = x["be"] * (Lv - x["L0"]) + (1 - x["be"]) * x["T0"]
    mad = x["sa"] / x["n"]
    return {"Fn": x["al"] * x["At"] + (1 - x["al"]) * x["Ft"], "Lv": Lv, "Tr": Tr, "Fh": Lv + x["hh"] * Tr, "mad": mad, "mape": x["sp"] / x["n"], "ts": x["se"] / mad}


def crash(x):
    sl = (x["Cc"] - x["Cn"]) / (x["Dn"] - x["Dc"])
    return {"sl": sl, "mx": x["Dn"] - x["Dc"], "dtc": x["dd"] * (sl - x["ic"]), "ok": 1.0 if sl < x["ic"] else 0.0}


def economy(x):
    i, n, P0, A, S, k = x["i"], int(round(x["n"] / YEAR)), x["P0"], x["A"] * YEAR, x["S"], int(x["kk"])
    pa = sum((1 + i * YEAR) ** -t for t in range(1, n + 1))                              # discount each annual benefit
    bk = P0
    ddb = 0.0
    for t in range(1, k + 1):
        ddb = bk * 2 / n
        bk -= ddb
    base = P0 - S
    syd = base * (n - k + 1) / (n * (n + 1) / 2)
    assert sum(base * (n - t + 1) / (n * (n + 1) / 2) for t in range(1, n + 1)) == pytest.approx(base)     # the schedule depreciates exactly the cost less salvage
    return {"pa": pa, "cr": 1 / pa / YEAR, "npv": A * pa - P0, "bc": A * pa / P0, "dsl": (P0 - S) / x["n"], "ddb": ddb, "syd": syd}


def emv(x):
    p = np.array([x["p1"], x["p2"], 1 - x["p1"] - x["p2"]])
    a = np.array([x["a1"], x["a2"], x["a3"]])
    b = np.array([x["b1"], x["b2"], x["b3"]])
    ea, eb = p @ a, p @ b
    ep = p @ np.maximum(a, b)
    z = stats.norm.ppf(x["cl"])
    var = z * x["sg"] - x["mu"]
    tail = integrate.quad(lambda q: (q * x["sg"] - x["mu"]) * stats.norm.pdf(q), z, 10)[0] / (1 - x["cl"])      # mean loss beyond the VaR
    return {"p3": p[2], "EA": ea, "EB": eb, "ep": ep, "evpi": ep - max(ea, eb), "var": var, "es": tail}


def faulttree(x):
    names = ["pA", "pB", "pC", "pD", "pE"]
    top = 0.0
    for bits in range(32):
        s = [(bits >> i) & 1 for i in range(5)]
        pr = np.prod([x[nm] if v else 1 - x[nm] for nm, v in zip(names, s)])
        if (s[0] and s[1]) or (s[2] and s[3]) or s[4]:
            top += pr                                                                     # enumerate every combination of basic events
    return {"g1": x["pA"] * x["pB"], "g2": x["pC"] * x["pD"], "Pt": top, "fvE": x["pE"] / top, "rpn": x["sv"] * x["oc"] * x["dt"]}


def markov(x):
    la, mu, t = x["la"], x["mr"], x["t"]
    Q1 = np.array([[-la, la], [mu, -mu]])
    pi1 = linalg.null_space(Q1.T)[:, 0]
    pi1 = pi1 / pi1.sum()
    pt = np.array([1.0, 0.0]) @ linalg.expm(Q1 * t)
    Q2 = np.array([[-2 * la, 2 * la, 0], [mu, -(mu + la), la], [0, mu, -mu]])           # states: both up, one down, both down
    pi2 = linalg.null_space(Q2.T)[:, 0]
    pi2 = pi2 / pi2.sum()
    T = np.array([[-2 * la, 2 * la], [mu, -(mu + la)]])                                  # transient part (state 2 absorbing)
    mttf = np.linalg.solve(-T, np.ones(2))[0]
    return {"As": pi1[0], "At": pt[0], "P0": pi2[0], "P1": pi2[1], "P2": pi2[2], "Ap": pi2[0] + pi2[1], "mt": mttf}


def raid(x):
    la, mu, N = 1 / x["mtbf"], 1 / x["mttr"], int(x["N"])
    def mttdl(rates_up, rates_down):
        n = len(rates_up)
        T = np.zeros((n, n))
        for i in range(n):
            T[i, i] -= rates_up[i]
            if i + 1 < n:
                T[i, i + 1] += rates_up[i]
            if i > 0:
                T[i, i] -= rates_down[i]
                T[i, i - 1] += rates_down[i]
        return np.linalg.solve(-T, np.ones(n))[0]
    m1 = mttdl([2 * la, la], [0, mu])
    m5 = mttdl([N * la, (N - 1) * la], [0, mu])
    m6 = mttdl([N * la, (N - 1) * la, (N - 2) * la], [0, mu, mu])
    bits = (N - 1) * x["cap"]                                                            # capacity in bits (1 TB = 8e12 bits)
    return {"m1": m1, "m5": m5, "m6": m6, "c5": (N - 1) / N, "c6": (N - 2) / N, "pr": -math.expm1(-bits * x["ure"]), "pl": x["pf"] ** x["r"]}


def pipeline(x):
    T = (1 - x["f"]) + x["f"] / x["sp"]
    return {"cpi": 1 + x["st"], "spd": x["ds"] / (1 + x["st"]), "am": 1 / T, "gu": x["np"] - (1 - x["f"]) * (x["np"] - 1), "rl": min(x["pk"], x["bw"] * x["ai"]), "rp": x["pk"] / x["bw"]}


def algorithms(x):
    n, rate = x["n"], x["c"]
    return {"tn": x["cn"] * n * math.log2(n) / rate, "tq": x["cn"] * n * n / rate, "nq": math.sqrt(x["tl"] * rate / x["cn"]), "pc": 1 + x["al"], "ps": 0.5 * (1 + 1 / (1 - x["al"])), "pu": 0.5 * (1 + 1 / (1 - x["al"]) ** 2)}


def huffman_len(p):
    heap = [(q, i, 0.0) for i, q in enumerate(p)]
    heapq.heapify(heap)
    k = len(p)
    total = 0.0
    while len(heap) > 1:
        a = heapq.heappop(heap)
        b = heapq.heappop(heap)
        total += a[0] + b[0]                                                             # each merge adds one bit to every symbol beneath it
        heapq.heappush(heap, (a[0] + b[0], k, 0.0))
        k += 1
    return total


def coding(x):
    p = [x["q1"], x["q2"], x["q3"], x["q4"]]
    H = stats.entropy(p, base=2)
    assert H <= huffman_len(p) <= H + 1                                                  # the actual Huffman code sits within one bit of the entropy
    m, n, k = x["m"], x["n"], x["kh"]
    assert (1 - (1 - 1 / m) ** (k * n)) ** k == pytest.approx((1 - math.exp(-k * n / m)) ** k, rel=1e-4)     # the exact and the exponential forms agree for a large filter
    return {"H": H, "Lh": H + 1, "cr": 8 / H, "fp": (1 - math.exp(-k * n / m)) ** k, "ko": m / n * math.log(2), "bpe": -math.log2(x["pt"]) / math.log(2)}


def network(x):
    bits = x["Lp"]                                                                       # the byte is 8 bits in the unit system, so Lp is already in bits
    per = 1 - (1 - x["ber"]) ** bits
    a = x["tp"] / x["tf"]
    return {"per": per, "a": a, "eta": (1 - per) / (1 + 2 * a), "Ss": x["G"] * math.exp(-x["G"]), "Sp": x["G"] * math.exp(-2 * x["G"]), "Tm": 1 / (1 - per)}


def queues(x):
    A = x["lm"] * x["sv"]
    c = int(x["c"])
    rho = A / c
    # birth-death steady state of M/M/c, truncated far beyond the offered load
    K = 400
    p = np.zeros(K)
    p[0] = 1.0
    for n in range(1, K):
        p[n] = p[n - 1] * A / min(n, c)
    p /= p.sum()
    EC = p[c:].sum()                                                                     # probability an arrival must wait (PASTA)
    q = np.array([A ** n / math.factorial(n) for n in range(c + 1)])
    EB = q[c] / q.sum()                                                                  # M/M/c/c blocking
    Wq = EC * x["sv"] / (c - A)
    rho1 = x["lm"] * x["s1"]
    Lq = rho1 ** 2 * (1 + x["cs"] ** 2) / (2 * (1 - rho1))
    return {"A": A, "rho": rho, "EB": EB, "EC": EC, "Wq": Wq, "sl": 1 - EC * math.exp(-(c - A) * x["tw"] / x["sv"]), "Lq": Lq, "Wg": Lq / x["lm"]}


def rsa(x):
    lnN = x["nb"] * math.log(2)
    work = 1.923 * lnN ** (1 / 3) * math.log(lnN) ** (2 / 3)                             # ln of the NFS work
    return {"lnN": lnN, "sb": work / math.log(2), "eb": x["lg"] * math.log2(x["alp"]), "tb": x["alp"] ** x["lg"] / 2 / x["gr"]}


CASES = {
    "industrial.reliability.weibull_hazard_bathtub": (weibull, 1e-9), "industrial.quality.acceptance_sampling_oc_curve": (sampling, 1e-9), "industrial.experiments.two_level_factorial_anova_regression": (factorial, 1e-9),
    "industrial.inventory.backorder_eoq_newsvendor_rop": (inventory, 1e-4), "industrial.forecasting.exponential_smoothing_holt_errors": (forecast, 1e-9), "industrial.projects.crash_cost_slope_time_cost_tradeoff": (crash, 1e-9),
    "industrial.economics.pv_npv_annuity_depreciation_bc": (economy, 1e-9), "industrial.decisions.emv_evpi_value_at_risk": (emv, 1e-6), "industrial.safety.fault_tree_fmea_rpn": (faulttree, 1e-9),
    "industrial.reliability.markov_availability_repairable": (markov, 1e-9), "computer.storage.raid_mttdl_rebuild_ure": (raid, 2e-3), "computer.architecture.pipeline_amdahl_roofline": (pipeline, 1e-9),
    "computer.algorithms.run_time_hash_load_factor": (algorithms, 1e-9), "computer.coding.entropy_huffman_bloom_filter": (coding, 1e-9), "computer.networks.ber_per_arq_aloha": (network, 1e-9),
    "computer.queueing.erlang_c_mg1_pollaczek_khinchine": (queues, 1e-6), "cybersecurity.cryptography.rsa_strength_password_entropy": (rsa, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_hashing_formulas_agree_with_a_simulation():
    rng = np.random.default_rng(7)
    M, load = 20011, 0.75
    n = int(M * load)
    table = np.full(M, -1)
    probes = []
    for key in rng.integers(0, 2 ** 62, n):
        h = key % M
        c = 1
        while table[h] >= 0:
            h = (h + 1) % M
            c += 1
        table[h] = key
        probes.append(c)
    hit = np.mean(probes)                                                                # average probes for a successful search over the stored keys
    miss = []
    for key in rng.integers(0, 2 ** 62, 4000):
        h, c = key % M, 1
        while table[h] >= 0:
            h = (h + 1) % M
            c += 1
        miss.append(c)
    r = solved("computer.algorithms.run_time_hash_load_factor", al="0.75")
    assert r["ps"] == pytest.approx(hit, rel=0.1) and r["pu"] == pytest.approx(np.mean(miss), rel=0.2)


def test_benchmarks():
    assert solved("computer.networks.ber_per_arq_aloha", G="1")["Ss"] == pytest.approx(1 / math.e)                        # slotted ALOHA peaks at 1/e
    assert solved("computer.networks.ber_per_arq_aloha", G="0.5")["Sp"] == pytest.approx(1 / (2 * math.e))                # pure ALOHA peaks at 1/2e
    assert solved("computer.queueing.erlang_c_mg1_pollaczek_khinchine", cs="1")["Lq"] == pytest.approx(0.6 ** 2 / (1 - 0.6), rel=1e-9)   # exponential service: the M/M/1 queue length
    assert solved("industrial.reliability.weibull_hazard_bathtub", be="1")["ht"] == pytest.approx(1 / 5000 / HOUR)         # constant hazard 1/eta
    assert solved("cybersecurity.cryptography.rsa_strength_password_entropy")["sb"] == pytest.approx(112, abs=8)           # 2048-bit RSA: about 112 bits (NIST)
    assert solved("industrial.projects.crash_cost_slope_time_cost_tradeoff", ic="1000 USD/day")["ok"] == 0
    p = solved("computer.architecture.pipeline_amdahl_roofline", f="100 %", sp="16")["am"]
    assert p == pytest.approx(16)                                                                                         # everything improved: full speedup


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == cid.split(".")[0]
