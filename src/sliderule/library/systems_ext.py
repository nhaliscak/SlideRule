from ..core import Calculation, V


CALCS = [
    Calculation(
        id="systems.requirements.volatility_coverage", name="Requirements volatility and verification coverage",
        disciplines=["systems", "computer"], subdisciplines=["Requirements Engineering", "Verification and Validation"],
        description="Change rate of a requirements baseline and the fraction of current requirements covered by verification.",
        variables=[V("N0", "Baseline requirements", "ea", latex=r"N_0"), V("ad", "Added", "ea"), V("md", "Modified", "ea"), V("dl", "Deleted", "ea"), V("vf", "Requirements with verification complete", "ea"),
                   V("Nc", "Current requirement count", "ea", latex=r"N"), V("RV", "Requirements volatility", "%"), V("cov", "Verification coverage", "%")],
        equations=[("Current count", "Nc = N0 + ad - dl"), ("Volatility", "RV = (ad + md + dl)/N0"), ("Coverage", "cov = vf/Nc")], outputs=["Nc", "RV", "cov"], tags=["requirements", "baseline", "change control", "traceability", "scope creep", "metrics"],
        assumptions=["Counts taken at the same review milestone"], references=["INCOSE Systems Engineering Handbook, §2.3"], example={"N0": "240 ea", "ad": "18 ea", "md": "31 ea", "dl": "6 ea", "vf": "180 ea"}),
    Calculation(
        id="systems.requirements.mass_budget_margin", name="Technical budget: growth allowance and margin",
        disciplines=["systems", "aerospace"], subdisciplines=["Requirements Engineering", "Integration Engineering"],
        description="Predicted mass from current best estimate with a maturity-based growth allowance, and the remaining margin against the allocation (the same bookkeeping applies to power and data budgets).",
        variables=[V("CBE", "Current best estimate", "kg"), V("gr", "Growth allowance (maturity based)", "%"), V("Alloc", "Allocation (requirement)", "kg"), V("Pred", "Predicted mass", "kg"), V("mg", "Margin vs allocation", "kg", signed=True), V("mp", "Margin (percent of prediction)", "%", signed=True)],
        equations=[("Predicted mass", "Pred = CBE*(1 + gr)"), ("Margin", "mg = Alloc - Pred"), ("Margin percent", "mp = mg/Pred")], outputs=["Pred", "mg", "mp"], tags=["budget", "margin", "mass properties", "contingency", "technical performance measure", "tpm"],
        validity=[("Alloc > CBE*(1 + gr)", "predicted mass exceeds the allocation")], assumptions=["Single subsystem; growth percentages per AIAA S-120 (5–30 % by maturity)"], references=["AIAA S-120-2006; NASA Systems Engineering Handbook, §6.7"], example={"CBE": "820 kg", "gr": "15 %", "Alloc": "1000 kg"}),
    Calculation(
        id="systems.integration.interface_complexity", name="Interface count and integration effort",
        disciplines=["systems", "computer"], subdisciplines=["Integration Engineering", "Software Systems Engineering"],
        description="Possible and expected interfaces among n components and the integration-test effort they imply (growth is quadratic in n).",
        variables=[V("n", "Number of components", "1"), V("dn", "Interface density (fraction of pairs connected)", "%", latex=r"\rho"), V("he", "Effort per interface", "h"), V("Imax", "Possible interfaces", "1", latex=r"I_{max}"), V("Ie", "Expected interfaces", "1", latex=r"I"),
                   V("Eff", "Integration effort", "h", latex=r"E")],
        equations=[("Possible interfaces", "Imax = n*(n - 1)/2"), ("Expected interfaces", "Ie = dn*Imax"), ("Integration effort", "Eff = Ie*he")], outputs=["Imax", "Ie", "Eff"], tags=["integration", "interfaces", "complexity", "architecture", "n-squared", "interface control"],
        assumptions=["Pairwise interfaces only; mean effort per interface"], references=["Sage & Rouse, Handbook of Systems Engineering and Management"], example={"n": "25", "dn": "30 %", "he": "40 h"}),
    Calculation(
        id="systems.verification.success_run_test", name="Zero-failure reliability demonstration test",
        disciplines=["systems", "industrial"], subdisciplines=["Verification and Validation"],
        description="Number of units (success-run theorem) or test time (exponential life) needed to demonstrate a reliability or MTBF at a confidence level with no failures.",
        variables=[V("Rq", "Reliability to demonstrate", "%", latex=r"R", min=1, max=99.999), V("Cl", "Confidence level", "%", latex=r"C", min=1, max=99.999), V("MTBF", "MTBF to demonstrate", "h"), V("n", "Units to test (no failures)", "1"), V("nc", "Units to test (rounded up)", "1"),
                   V("Tt", "Total test time (no failures)", "h", latex=r"T")],
        equations=[("Success-run theorem", "n = log(1 - Cl)/log(Rq)"), ("Rounded up", "nc = ceiling(n)"), ("Exponential test time", "Tt = -MTBF*log(1 - Cl)")], outputs=["n", "nc", "Tt"], tags=["reliability demonstration", "success run", "qualification", "test planning", "confidence", "mtbf"],
        assumptions=["Pass/fail trials with zero allowed failures; exponential lifetimes for Tt (accumulated unit-hours)"], references=["MIL-HDBK-781A; Ebeling, Reliability and Maintainability Engineering, Ch. 8"], example={"Rq": "95 %", "Cl": "90 %", "MTBF": "5000 h"}),
    Calculation(
        id="systems.software.goel_okumoto_reliability", name="Software reliability growth (Goel–Okumoto)",
        disciplines=["systems", "computer"], subdisciplines=["Software Systems Engineering", "Software Engineering", "Verification and Validation"],
        description="Expected cumulative defects found by test time t, defects remaining and failure intensity for an exponential growth model.",
        variables=[V("a", "Total expected defects", "1"), V("b", "Detection rate", "1/h"), V("t", "Test time", "h"), V("mt", "Expected defects found", "1", latex=r"m(t)"), V("rem", "Expected defects remaining", "1"), V("lt", "Failure intensity", "1/h", latex=r"\lambda(t)")],
        equations=[("Mean value function", "mt = a*(1 - exp(-b*t))"), ("Remaining defects", "rem = a - mt"), ("Failure intensity", "lt = a*b*exp(-b*t)")], outputs=["mt", "rem", "lt"], tags=["software reliability", "defects", "growth model", "release readiness", "testing"],
        assumptions=["NHPP with exponential detection; parameters fitted to test data"], references=["Goel & Okumoto (1979), IEEE Trans. Reliability R-28(3)"], example={"a": "120", "b": "0.004 1/h", "t": "400 h"}),
]
