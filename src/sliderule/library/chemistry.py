"""Chemistry as a science: general, physical and analytical chemistry and atomic/molecular spectroscopy."""

from ..core import C, Calculation, V
from ._common import R_univ, avogadro, c0, kB, planck

GEN = "General Chemistry"
PHYS = "Physical Chemistry"
ANAL = "Analytical Chemistry"
SPEC = "Atomic Structure and Spectroscopy"


def c_std() -> "C":
    return C("c0", "Standard concentration", 1, "mol/L", latex=r"c^\circ", note="reference concentration that makes logarithms and equilibrium constants dimensionless")


CALCS = [
    # ------------------------------------------------------------------ general chemistry
    Calculation(
        id="chemistry.general.solution_concentration", name="Solution concentration: mass fraction, molarity, molality and mole fraction",
        disciplines=["chemistry", "chemical"], subdisciplines=[GEN],
        description="Molarity, molality and the mole fraction of the solute for a solution given its mass fraction, density and the molar masses of solute and solvent.",
        variables=[V("Ms", "Solute molar mass", "g/mol", latex=r"M_s"), V("Mv", "Solvent molar mass", "g/mol", latex=r"M_v", default=18.015), V("w", "Solute mass fraction", "%", min=0, max=100),
                   V("rho", "Solution density", "g/mL", latex=r"\rho"), V("cm", "Molarity", "mol/L", latex=r"c"), V("bm", "Molality", "mol/kg", latex=r"b"), V("xs", "Solute mole fraction", "1", latex=r"x_s")],
        equations=[("Molarity", "cm = w*rho/Ms"), ("Molality", "bm = w/((1 - w)*Ms)"), ("Mole fraction", "xs = (w/Ms)/(w/Ms + (1 - w)/Mv)")], outputs=["cm", "bm", "xs"],
        tags=["molarity", "molality", "mole fraction", "mass percent", "concentration", "solution"], assumptions=["Binary solution; the density is that of the solution at the stated temperature"],
        references=["Brown et al., Chemistry: The Central Science, Ch. 13", "Atkins & de Paula, Physical Chemistry, Ch. 5"], example={"Ms": "36.46 g/mol", "Mv": "18.015 g/mol", "w": "37 %", "rho": "1.18 g/mL"}),
    Calculation(
        id="chemistry.general.limiting_reagent_yield", name="Limiting reagent, theoretical and percent yield",
        disciplines=["chemistry", "chemical"], subdisciplines=[GEN],
        description="For a A + b B → c C: amounts of reagents, the extent of reaction set by the limiting reagent, the theoretical yield of C and the percent yield.",
        variables=[V("mA", "Mass of reagent A", "g", latex=r"m_A"), V("MA", "Molar mass of A", "g/mol", latex=r"M_A"), V("a", "Stoichiometric coefficient of A", "1", min=0),
                   V("mB", "Mass of reagent B", "g", latex=r"m_B"), V("MB", "Molar mass of B", "g/mol", latex=r"M_B"), V("b", "Stoichiometric coefficient of B", "1", min=0),
                   V("c", "Stoichiometric coefficient of C", "1", min=0), V("MC", "Molar mass of C", "g/mol", latex=r"M_C"), V("mact", "Actual mass of C obtained", "g"),
                   V("nA", "Amount of A", "mol", latex=r"n_A"), V("nB", "Amount of B", "mol", latex=r"n_B"), V("xi", "Extent of reaction", "mol", latex=r"\xi"),
                   V("mth", "Theoretical yield of C", "g", latex=r"m_{th}"), V("py", "Percent yield", "%")],
        equations=[("Amount of A", "nA = mA/MA"), ("Amount of B", "nB = mB/MB"), ("Limiting reagent sets the extent", "xi = Min(nA/a, nB/b)"), ("Theoretical yield", "mth = c*xi*MC"), ("Percent yield", "py = mact/mth")],
        outputs=["nA", "nB", "xi", "mth", "py"], tags=["stoichiometry", "limiting reagent", "yield", "reaction", "mole"],
        assumptions=["Single reaction going to completion; the reagent with the smaller n/coefficient is limiting"], references=["Brown et al., Chemistry: The Central Science, Ch. 3"],
        example={"mA": "4.0 g", "MA": "2.016 g/mol", "a": "2", "mB": "24 g", "MB": "31.998 g/mol", "b": "1", "c": "2", "MC": "18.015 g/mol", "mact": "25 g"}),
    Calculation(
        id="chemistry.general.dilution_mixing", name="Dilution and mixing of solutions",
        disciplines=["chemistry", "biomedical"], subdisciplines=[GEN, ANAL],
        description="Concentration after diluting a stock solution (C₁V₁ = C₂V₂), the solvent to add, and the concentration after mixing two solutions of the same solute.",
        variables=[V("Cs", "Stock concentration", "mol/L", latex=r"C_1"), V("Vs", "Stock volume taken", "mL", latex=r"V_1"), V("Vf", "Final volume", "mL", latex=r"V_2"), V("Cf", "Final concentration", "mol/L", latex=r"C_2"),
                   V("Vadd", "Solvent to add", "mL"), V("Ca", "Concentration of solution a", "mol/L", latex=r"C_a"), V("Va", "Volume of solution a", "mL", latex=r"V_a"), V("Cb", "Concentration of solution b", "mol/L", latex=r"C_b"),
                   V("Vb", "Volume of solution b", "mL", latex=r"V_b"), V("Cmix", "Concentration of the mixture", "mol/L", latex=r"C_{mix}")],
        equations=[("Dilution", "Cf = Cs*Vs/Vf"), ("Solvent to add", "Vadd = Vf - Vs"), ("Mixing", "Cmix = (Ca*Va + Cb*Vb)/(Va + Vb)")], outputs=["Cf", "Vadd", "Cmix"],
        tags=["dilution", "c1v1", "mixing", "stock solution", "concentration"], assumptions=["Volumes are additive (true for dilute aqueous solutions)"],
        references=["Brown et al., Chemistry: The Central Science, Ch. 4"], example={"Cs": "12 mol/L", "Vs": "25 mL", "Vf": "500 mL", "Ca": "0.5 mol/L", "Va": "100 mL", "Cb": "0.2 mol/L", "Vb": "150 mL"}),
    Calculation(
        id="chemistry.general.gas_laws_dalton_graham", name="Combined gas law, Dalton's law and Graham's law",
        disciplines=["chemistry", "physics"], subdisciplines=[GEN, "Thermodynamics and Statistical Physics"],
        description="Volume after a change of pressure and temperature (combined gas law), the partial pressure of a component in a mixture (Dalton), and the ratio of effusion rates of two gases (Graham).",
        variables=[V("P1", "Initial pressure", "atm", latex=r"P_1"), V("V1", "Initial volume", "L", latex=r"V_1"), V("T1", "Initial temperature", "K", latex=r"T_1"), V("P2", "Final pressure", "atm", latex=r"P_2"),
                   V("T2", "Final temperature", "K", latex=r"T_2"), V("V2", "Final volume", "L", latex=r"V_2"), V("xi", "Mole fraction of the component", "1", latex=r"x_i", min=0, max=1), V("Pt", "Total pressure", "mmHg", latex=r"P_{tot}"),
                   V("Pi", "Partial pressure of the component", "mmHg", latex=r"P_i"), V("Ma", "Molar mass of the lighter gas", "g/mol", latex=r"M_1"), V("Mb", "Molar mass of the heavier gas", "g/mol", latex=r"M_2"),
                   V("rr", "Effusion-rate ratio (lighter/heavier)", "1")],
        equations=[("Combined gas law", "V2 = P1*V1*T2/(T1*P2)"), ("Dalton's law", "Pi = xi*Pt"), ("Graham's law", "rr = sqrt(Mb/Ma)")], outputs=["V2", "Pi", "rr"],
        tags=["gas laws", "dalton", "graham", "effusion", "partial pressure", "combined gas law"], assumptions=["Ideal gases; a fixed amount of gas for the combined law"],
        references=["Brown et al., Chemistry: The Central Science, Ch. 10"], example={"P1": "1 atm", "V1": "5 L", "T1": "273.15 K", "P2": "2 atm", "T2": "300 K", "xi": "0.21", "Pt": "760 mmHg", "Ma": "2.016 g/mol", "Mb": "32.00 g/mol"}),
    Calculation(
        id="chemistry.general.colligative_properties", name="Colligative properties: Raoult, boiling and freezing points, osmotic pressure",
        disciplines=["chemistry", "chemical", "biomedical"], subdisciplines=[GEN, PHYS],
        description="Vapour pressure of a solution (Raoult), boiling-point elevation, freezing-point depression and osmotic pressure (van 't Hoff) of a dilute solution.",
        variables=[V("iv", "van 't Hoff factor", "1", latex=r"i", min=1), V("bm", "Molality", "mol/kg", latex=r"b"), V("Kb", "Ebullioscopic constant", "K*kg/mol", latex=r"K_b"), V("Kf", "Cryoscopic constant", "K*kg/mol", latex=r"K_f"),
                   V("cm", "Molarity", "mol/L", latex=r"c"), V("T", "Temperature", "K"), R_univ(), V("xv", "Solvent mole fraction", "1", latex=r"x_1", min=0, max=1), V("P0", "Pure-solvent vapour pressure", "kPa", latex=r"P^*"),
                   V("dTb", "Boiling-point elevation", "K", delta=True, latex=r"\Delta T_b"), V("dTf", "Freezing-point depression", "K", delta=True, latex=r"\Delta T_f"), V("Pi", "Osmotic pressure", "atm", latex=r"\Pi"),
                   V("Pv", "Solution vapour pressure", "kPa", latex=r"P"), V("dP", "Vapour-pressure lowering", "kPa", latex=r"\Delta P")],
        equations=[("Boiling-point elevation", "dTb = iv*Kb*bm"), ("Freezing-point depression", "dTf = iv*Kf*bm"), ("Osmotic pressure", "Pi = iv*cm*R*T"), ("Raoult's law", "Pv = xv*P0"), ("Lowering", "dP = P0 - Pv")],
        outputs=["dTb", "dTf", "Pi", "Pv", "dP"], tags=["colligative", "raoult", "osmosis", "van't hoff", "boiling point", "freezing point", "vapour pressure"],
        assumptions=["Dilute, ideal solution of a non-volatile solute; i is the effective number of particles per formula unit"], references=["Atkins & de Paula, Physical Chemistry, Ch. 5", "Brown et al., Chemistry: The Central Science, Ch. 13"],
        example={"iv": "2", "bm": "0.5 mol/kg", "Kb": "0.512 K*kg/mol", "Kf": "1.86 K*kg/mol", "cm": "0.49 mol/L", "T": "298.15 K", "xv": "0.9823", "P0": "3.169 kPa"}),

    # ------------------------------------------------------------------ physical chemistry
    Calculation(
        id="chemistry.physical.van_der_waals", name="Van der Waals real gas",
        disciplines=["chemistry", "chemical", "physics"], subdisciplines=[PHYS, "Thermodynamics and Statistical Physics"],
        description="Pressure of a real gas from the van der Waals equation, the ideal-gas pressure for comparison and the compressibility factor.",
        variables=[V("n", "Amount of gas", "mol"), V("Vg", "Volume", "L", latex=r"V"), V("T", "Temperature", "K"), V("a", "Attraction parameter a", "L^2*bar/mol^2"), V("b", "Excluded-volume parameter b", "L/mol"), R_univ(),
                   V("P", "Pressure (van der Waals)", "bar"), V("Pid", "Pressure if ideal", "bar", latex=r"P_{ideal}"), V("Zc", "Compressibility factor", "1", latex=r"Z")],
        equations=[("Van der Waals equation", "P = n*R*T/(Vg - n*b) - a*n^2/Vg^2"), ("Ideal-gas pressure", "Pid = n*R*T/Vg"), ("Compressibility", "Zc = P*Vg/(n*R*T)")], outputs=["P", "Pid", "Zc"],
        validity=[("Vg > n*b", "The volume must exceed the excluded volume n·b")], tags=["real gas", "van der waals", "compressibility", "non-ideal", "equation of state"],
        assumptions=["Single-phase gas; a and b taken as constants (CO₂: a = 3.640 L²·bar/mol², b = 0.04267 L/mol)", "Solving for V is a cubic with a pole at V = n·b: give a search range above n·b (and pick the gas-like root)"], references=["Atkins & de Paula, Physical Chemistry, Ch. 1"],
        example={"n": "1 mol", "Vg": "1 L", "T": "300 K", "a": "3.640 L^2*bar/mol^2", "b": "0.04267 L/mol"}),
    Calculation(
        id="chemistry.physical.gibbs_equilibrium_vant_hoff", name="Gibbs energy, equilibrium constant and van 't Hoff equation",
        disciplines=["chemistry", "chemical", "physics"], subdisciplines=[PHYS, "Thermodynamics and Statistical Physics"],
        description="Standard Gibbs energy of reaction from ΔH° and ΔS°, the equilibrium constant, and the equilibrium constant at a second temperature (van 't Hoff).",
        variables=[V("dH", "Standard reaction enthalpy", "kJ/mol", latex=r"\Delta H^\circ", signed=True), V("dS", "Standard reaction entropy", "J/(mol*K)", latex=r"\Delta S^\circ", signed=True), V("T", "Temperature", "K"), V("T2", "Second temperature", "K", latex=r"T_2"),
                   R_univ(), V("dG", "Standard Gibbs energy of reaction", "kJ/mol", latex=r"\Delta G^\circ", signed=True), V("K", "Equilibrium constant at T", "1"), V("K2", "Equilibrium constant at T₂", "1", latex=r"K_2")],
        equations=[("Gibbs energy", "dG = dH - T*dS"), ("Equilibrium constant", "K = exp(-dG/(R*T))"), ("van 't Hoff equation", "K2 = K*exp(-dH/R*(1/T2 - 1/T))")], outputs=["dG", "K", "K2"],
        tags=["gibbs", "equilibrium", "van't hoff", "spontaneity", "thermodynamics", "enthalpy", "entropy"], assumptions=["ΔH° and ΔS° independent of temperature over the range"],
        references=["Atkins & de Paula, Physical Chemistry, Ch. 3 and 6"], example={"dH": "-92.4 kJ/mol", "dS": "-198.7 J/(mol*K)", "T": "298.15 K", "T2": "500 K"}),
    Calculation(
        id="chemistry.physical.integrated_rate_laws", name="Integrated rate laws: zero, first and second order",
        disciplines=["chemistry", "chemical"], subdisciplines=[PHYS],
        description="Concentration after a time t and the half-life for zero-, first- and second-order reactions of a single reactant.",
        variables=[V("A0", "Initial concentration", "mol/L", latex=r"[A]_0"), V("t", "Time", "s"), V("k0", "Zero-order rate constant", "mol/(L*s)", latex=r"k_0"), V("k1", "First-order rate constant", "1/s", latex=r"k_1"),
                   V("k2", "Second-order rate constant", "L/(mol*s)", latex=r"k_2"), V("Az", "Concentration (zero order)", "mol/L", latex=r"[A]_0"), V("Af", "Concentration (first order)", "mol/L", latex=r"[A]_1"),
                   V("As", "Concentration (second order)", "mol/L", latex=r"[A]_2"), V("th0", "Half-life (zero order)", "s", latex=r"t_{1/2,0}"), V("th1", "Half-life (first order)", "s", latex=r"t_{1/2,1}"),
                   V("th2", "Half-life (second order)", "s", latex=r"t_{1/2,2}")],
        equations=[("Zero order", "Az = A0 - k0*t"), ("First order", "Af = A0*exp(-k1*t)"), ("Second order", "As = 1/(1/A0 + k2*t)"), ("Half-life, zero order", "th0 = A0/(2*k0)"),
                   ("Half-life, first order", "th1 = log(2)/k1"), ("Half-life, second order", "th2 = 1/(k2*A0)")], outputs=["Az", "Af", "As", "th0", "th1", "th2"],
        validity=[("k0*t <= A0", "A zero-order reactant is used up before this time: the formula no longer applies")], tags=["kinetics", "rate law", "half-life", "order", "concentration"],
        assumptions=["One reactant, irreversible reaction, constant temperature"], references=["Atkins & de Paula, Physical Chemistry, Ch. 22", "Brown et al., Chemistry: The Central Science, Ch. 14"],
        example={"A0": "0.5 mol/L", "t": "120 s", "k0": "0.002 mol/(L*s)", "k1": "0.005 1/s", "k2": "0.01 L/(mol*s)"}),
    Calculation(
        id="chemistry.physical.eyring_transition_state", name="Eyring equation (transition-state theory)",
        disciplines=["chemistry", "chemical"], subdisciplines=[PHYS],
        description="Gibbs energy of activation, the rate constant of a unimolecular step from transition-state theory, and the equivalent Arrhenius activation energy.",
        variables=[V("dHa", "Enthalpy of activation", "kJ/mol", latex=r"\Delta H^\ddagger"), V("dSa", "Entropy of activation", "J/(mol*K)", latex=r"\Delta S^\ddagger", signed=True), V("T", "Temperature", "K"),
                   V("kp", "Transmission coefficient", "1", latex=r"\kappa", default=1, min=0, max=1), kB(), planck(), R_univ(), V("dGa", "Gibbs energy of activation", "kJ/mol", latex=r"\Delta G^\ddagger"),
                   V("k", "Rate constant", "1/s"), V("Ea", "Arrhenius activation energy", "kJ/mol", latex=r"E_a")],
        equations=[("Gibbs energy of activation", "dGa = dHa - T*dSa"), ("Eyring equation", "k = kp*kB*T/hP*exp(-dGa/(R*T))"), ("Arrhenius equivalent", "Ea = dHa + R*T")], outputs=["dGa", "k", "Ea"],
        tags=["eyring", "transition state", "activation", "rate constant", "kinetics"], assumptions=["Unimolecular elementary step in solution or for a gas-phase step with Ea = ΔH‡ + RT"],
        references=["Atkins & de Paula, Physical Chemistry, Ch. 22"], example={"dHa": "75 kJ/mol", "dSa": "-20 J/(mol*K)", "T": "298.15 K", "kp": "1"}),
    Calculation(
        id="chemistry.physical.clausius_clapeyron", name="Clausius–Clapeyron vapour pressure and boiling point",
        disciplines=["chemistry", "chemical", "physics"], subdisciplines=[PHYS, "Thermodynamics and Statistical Physics"],
        description="Vapour pressure at a second temperature and the boiling temperature at a given pressure from one known vapour pressure and the enthalpy of vaporisation.",
        variables=[V("P1", "Known vapour pressure", "kPa", latex=r"P_1"), V("T1", "Temperature of the known pressure", "K", latex=r"T_1"), V("dHv", "Enthalpy of vaporisation", "kJ/mol", latex=r"\Delta H_{vap}"), V("T2", "Temperature of interest", "K", latex=r"T_2"),
                   V("Pt", "Target pressure", "kPa", latex=r"P_t"), R_univ(), V("P2", "Vapour pressure at T₂", "kPa", latex=r"P_2"), V("Tb", "Boiling temperature at the target pressure", "K", latex=r"T_b")],
        equations=[("Vapour pressure", "P2 = P1*exp(-dHv/R*(1/T2 - 1/T1))"), ("Boiling temperature", "1/Tb = 1/T1 - R*log(Pt/P1)/dHv")], outputs=["P2", "Tb"],
        tags=["vapour pressure", "boiling point", "clausius clapeyron", "phase equilibrium", "volatility"], assumptions=["Constant ΔH_vap over the range; ideal vapour; negligible liquid volume"],
        references=["Atkins & de Paula, Physical Chemistry, Ch. 4"], example={"P1": "101.325 kPa", "T1": "373.15 K", "dHv": "40.66 kJ/mol", "T2": "353.15 K", "Pt": "70 kPa"}),
    Calculation(
        id="chemistry.physical.calorimetry", name="Calorimetry: mixing temperature and reaction enthalpy",
        disciplines=["chemistry", "physics", "chemical"], subdisciplines=[PHYS, "Thermodynamics and Statistical Physics"],
        description="Final temperature when two bodies exchange heat, and the molar enthalpy of a reaction measured in a constant-pressure (coffee-cup) calorimeter.",
        variables=[V("m1", "Mass 1", "g", latex=r"m_1"), V("c1", "Specific heat 1", "J/(g*K)", latex=r"c_1"), V("T1", "Initial temperature 1", "degC", latex=r"T_1"), V("m2", "Mass 2", "g", latex=r"m_2"), V("c2", "Specific heat 2", "J/(g*K)", latex=r"c_2"),
                   V("T2", "Initial temperature 2", "degC", latex=r"T_2"), V("Tf", "Final temperature", "degC", latex=r"T_f"), V("ms", "Mass of solution", "g"), V("cs", "Specific heat of solution", "J/(g*K)", default=4.184),
                   V("dTs", "Temperature change of the solution", "K", delta=True, signed=True, latex=r"\Delta T"), V("Cc", "Calorimeter heat capacity", "J/K", latex=r"C_{cal}"), V("nr", "Amount of limiting reactant", "mol"),
                   V("dHr", "Molar reaction enthalpy", "kJ/mol", latex=r"\Delta H_r", signed=True)],
        equations=[("Final temperature", "Tf = (m1*c1*T1 + m2*c2*T2)/(m1*c1 + m2*c2)"), ("Reaction enthalpy", "dHr = -(ms*cs + Cc)*dTs/nr")], outputs=["Tf", "dHr"],
        tags=["calorimetry", "heat", "specific heat", "enthalpy", "mixing", "coffee cup"], assumptions=["No heat loss to the surroundings; constant specific heats"],
        references=["Brown et al., Chemistry: The Central Science, Ch. 5"], example={"m1": "100 g", "c1": "4.184 J/(g*K)", "T1": "80 degC", "m2": "50 g", "c2": "4.184 J/(g*K)", "T2": "20 degC", "ms": "100 g", "cs": "4.184 J/(g*K)", "dTs": "6.5 K", "Cc": "20 J/K", "nr": "0.05 mol"}),

    # ------------------------------------------------------------------ analytical chemistry
    Calculation(
        id="chemistry.analytical.weak_acid_base_ph", name="pH of a weak acid or weak base solution",
        disciplines=["chemistry", "environmental"], subdisciplines=[ANAL, GEN],
        description="Hydrogen-ion concentration, pH, p K_a and percent ionisation of a weak acid from K_a and its formal concentration, and the pH of a weak base from K_b (25 °C).",
        variables=[V("Ka", "Acid dissociation constant", "mol/L", latex=r"K_a"), V("Ca", "Formal concentration of the acid", "mol/L", latex=r"C_a"), V("Kb", "Base dissociation constant", "mol/L", latex=r"K_b"), V("Cb", "Formal concentration of the base", "mol/L", latex=r"C_b"),
                   c_std(), C("pKw", "p K_w at 25 °C", 14.0, "1", latex=r"pK_w"), V("H", "Hydrogen-ion concentration", "mol/L", latex=r"[H^+]"), V("pH", "pH of the acid", "1"), V("pKa", "p K_a", "1", latex=r"pK_a"),
                   V("ion", "Percent ionisation", "%", latex=r"\alpha"), V("OH", "Hydroxide concentration of the base", "mol/L", latex=r"[OH^-]"), V("pHb", "pH of the base", "1", latex=r"pH_b")],
        equations=[("Hydrogen ions (quadratic)", "H = (-Ka + sqrt(Ka^2 + 4*Ka*Ca))/2"), ("pH", "pH = -log(H/c0)/log(10)"), ("p K_a", "pKa = -log(Ka/c0)/log(10)"), ("Percent ionisation", "ion = H/Ca"),
                   ("Hydroxide (quadratic)", "OH = (-Kb + sqrt(Kb^2 + 4*Kb*Cb))/2"), ("pH of the base", "pHb = pKw + log(OH/c0)/log(10)")], outputs=["H", "pH", "pKa", "ion", "OH", "pHb"],
        tags=["ph", "acid", "base", "ka", "kb", "weak acid", "dissociation"], assumptions=["25 °C; activities taken equal to concentrations; autoionisation of water neglected (valid when Ka·Ca ≫ Kw)"],
        references=["Harris, Quantitative Chemical Analysis, Ch. 8–9", "Brown et al., Chemistry: The Central Science, Ch. 16"], example={"Ka": "1.8e-5 mol/L", "Ca": "0.10 mol/L", "Kb": "1.8e-5 mol/L", "Cb": "0.10 mol/L"}),
    Calculation(
        id="chemistry.analytical.henderson_hasselbalch", name="Buffers: Henderson–Hasselbalch equation and strong-acid addition",
        disciplines=["chemistry", "biomedical", "environmental"], subdisciplines=[ANAL],
        description="pH of a buffer from the p K_a and the amounts of conjugate base and acid, and the pH after adding a strong acid.",
        variables=[V("pKa", "p K_a of the acid", "1", latex=r"pK_a"), V("nA", "Amount of conjugate base", "mmol", latex=r"n_{A^-}"), V("nHA", "Amount of weak acid", "mmol", latex=r"n_{HA}"), V("nH", "Strong acid added", "mmol", latex=r"n_{H^+}"),
                   V("pH0", "Buffer pH", "1", latex=r"pH_0"), V("pH1", "pH after adding the acid", "1", latex=r"pH_1")],
        equations=[("Henderson–Hasselbalch", "pH0 = pKa + log(nA/nHA)/log(10)"), ("After adding strong acid", "pH1 = pKa + log((nA - nH)/(nHA + nH))/log(10)")], outputs=["pH0", "pH1"],
        validity=[("nH < nA", "The added acid exceeds the buffer base: the buffer is exhausted")], tags=["buffer", "henderson", "hasselbalch", "ph", "pka", "acid base"],
        assumptions=["Both forms present at moderate concentration; ratio of amounts equals the ratio of concentrations in one solution"], references=["Harris, Quantitative Chemical Analysis, Ch. 9"],
        example={"pKa": "4.76", "nA": "100 mmol", "nHA": "100 mmol", "nH": "20 mmol"}),
    Calculation(
        id="chemistry.analytical.solubility_product", name="Solubility product and molar solubility",
        disciplines=["chemistry", "environmental"], subdisciplines=[ANAL, PHYS],
        description="Molar solubility of a sparingly soluble salt M_a X_b from its K_sp, with an optional common ion already present, and the ion product that tells whether precipitation occurs.",
        variables=[V("Ksp", "Solubility product", "1", latex=r"K_{sp}"), V("a", "Cations per formula unit", "1", min=1), V("b", "Anions per formula unit", "1", min=1), V("cc", "Common-ion (anion) concentration already present", "mol/L", latex=r"c_X", default=0, min=0),
                   c_std(), V("s", "Molar solubility", "mol/L"), V("cM", "Cation concentration in the solution", "mol/L", latex=r"c_M"), V("cX", "Anion concentration in the solution", "mol/L", latex=r"c_X'"),
                   V("Qi", "Ion product of a given solution", "1", latex=r"Q"), V("Cm1", "Cation concentration of the given solution", "mol/L", latex=r"c_M^0"), V("Cx1", "Anion concentration of the given solution", "mol/L", latex=r"c_X^0")],
        equations=[("Solubility equilibrium", "Ksp = (a*s/c0)^a*(b*s/c0 + cc/c0)^b"), ("Cation concentration", "cM = a*s"), ("Anion concentration", "cX = b*s + cc"), ("Ion product", "Qi = (Cm1/c0)^a*(Cx1/c0)^b")],
        outputs=["s", "cM", "cX", "Qi"], tags=["ksp", "solubility", "precipitation", "common ion", "salt", "equilibrium"],
        assumptions=["Activity coefficients equal to 1; no complexation or hydrolysis; Q > Ksp means the solution is supersaturated and precipitates"], references=["Harris, Quantitative Chemical Analysis, Ch. 6", "Brown et al., Chemistry: The Central Science, Ch. 17"],
        example={"Ksp": "1.1e-12", "a": "2", "b": "1", "cc": "0 mol/L", "Cm1": "0.001 mol/L", "Cx1": "0.0005 mol/L"}),

    # ------------------------------------------------------------------ atomic structure and spectroscopy
    Calculation(
        id="chemistry.spectroscopy.diatomic_vibration_rotation", name="Diatomic molecule: vibration and rotation",
        disciplines=["chemistry", "physics"], subdisciplines=[SPEC, "Modern Physics"],
        description="Reduced mass, harmonic vibrational wavenumber, zero-point energy, rotational constant and rotational line position of a diatomic molecule from its atomic masses, force constant and bond length.",
        variables=[V("m1", "Mass of atom 1", "Da", latex=r"m_1"), V("m2", "Mass of atom 2", "Da", latex=r"m_2"), V("kf", "Bond force constant", "N/m", latex=r"k"), V("re", "Equilibrium bond length", "angstrom", latex=r"r_e"), V("J", "Rotational quantum number", "1", min=0),
                   planck(), c0(), avogadro(), V("mu", "Reduced mass", "Da", latex=r"\mu"), V("nu", "Vibrational wavenumber", "1/cm", latex=r"\tilde\nu"), V("zpe", "Zero-point vibrational energy", "kJ/mol", latex=r"E_0"),
                   V("Inr", "Moment of inertia", "kg*m^2", latex=r"I"), V("Bc", "Rotational constant", "1/cm", latex=r"B"), V("FJ", "Rotational term value F(J)", "1/cm", latex=r"F(J)")],
        equations=[("Reduced mass", "mu = m1*m2/(m1 + m2)"), ("Vibrational wavenumber", "nu = sqrt(kf/mu)/(2*pi*c0)"), ("Zero-point energy", "zpe = hP*c0*nu*NA/2"), ("Moment of inertia", "Inr = mu*re^2"),
                   ("Rotational constant", "Bc = hP/(8*pi^2*c0*Inr)"), ("Rotational term", "FJ = Bc*J*(J + 1)")], outputs=["mu", "nu", "zpe", "Inr", "Bc", "FJ"],
        tags=["ir spectroscopy", "microwave", "vibration", "rotation", "force constant", "hcl", "rigid rotor", "harmonic oscillator"],
        assumptions=["Harmonic oscillator and rigid rotor (anharmonicity and centrifugal distortion neglected)"], references=["Atkins & de Paula, Physical Chemistry, Ch. 12", "Harris & Bertolucci, Symmetry and Spectroscopy, Ch. 2"],
        example={"m1": "1.00782503 Da", "m2": "34.96885268 Da", "kf": "516 N/m", "re": "1.275 angstrom", "J": "3"}),
]
