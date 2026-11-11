from ..core import C, Calculation, V
from ._common import kB, qe

DB = ["dB"]

CALCS = [
    # ------------------------------------------------------------------ quantum
    Calculation(
        id="quantum.computing.grover_search", name="Grover search iterations and success probability",
        disciplines=["quantum", "computer"], subdisciplines=["Quantum Computing"],
        description="Optimal number of Grover iterations to find one of M marked items among N, the resulting success probability, and the classical expected query count for comparison.",
        variables=[V("N", "Search-space size", "1"), V("M", "Number of marked items", "1"), V("th", "Rotation angle", "rad", latex=r"\theta"), V("k", "Optimal iterations", "1"), V("Ps", "Success probability", "%", latex=r"P"), V("qc", "Classical expected queries", "1", latex=r"N/2M")],
        equations=[("Rotation angle", "th = asin(sqrt(M/N))"), ("Optimal iterations", "k = floor(pi/(4*th))"), ("Success probability", "Ps = sin((2*k + 1)*th)^2"), ("Classical queries", "qc = N/(2*M)")], outputs=["th", "k", "Ps", "qc"],
        tags=["grover", "quantum search", "oracle", "amplitude amplification", "speedup"], assumptions=["Noiseless oracle and gates; M ≪ N"], references=["Nielsen & Chuang, Quantum Computation and Quantum Information, Ch. 6"], example={"N": "1e6", "M": "1"}),
    Calculation(
        id="quantum.computing.gate_error_budget", name="Quantum circuit fidelity and gate-error budget",
        disciplines=["quantum", "computer"], subdisciplines=["Quantum Computing"],
        description="Circuit fidelity after n gates of error ε, and the maximum circuit depth that meets a target fidelity.",
        variables=[V("eg", "Error per gate", "%", latex=r"\varepsilon", min=0.0000001, max=50), V("ng", "Number of gates", "1", latex=r"n"), V("Ft", "Target fidelity", "%", min=1, max=99.9999), V("F", "Circuit fidelity", "%"), V("nmax", "Maximum gates for target fidelity", "1", latex=r"n_{max}")],
        equations=[("Circuit fidelity", "F = (1 - eg)^ng"), ("Gate budget", "nmax = log(Ft)/log(1 - eg)")], outputs=["F", "nmax"], tags=["nisq", "fidelity", "qubit", "noise", "circuit depth", "error rate"], assumptions=["Independent, uncorrelated gate errors (multiplicative fidelity)"], references=["Preskill (2018), Quantum 2, 79"], example={"eg": "0.1 %", "ng": "500", "Ft": "50 %"}),
    Calculation(
        id="quantum.sensing.nv_magnetometer", name="NV-centre magnetometry: Zeeman splitting and shot-noise sensitivity",
        disciplines=["quantum", "materials"], subdisciplines=["Quantum Sensing"],
        description="Spin-transition frequency shift in a magnetic field for an NV centre and the shot-noise-limited sensitivity of an ensemble measurement.",
        variables=[V("gb", "Gyromagnetic ratio γ/2π", "GHz/T", default=28.024), V("B", "Magnetic field along NV axis", "mT"), V("Ns", "Number of sensing spins", "1"), V("T2", "Coherence time T₂*", "us", latex=r"T_2^*"), V("tm", "Measurement time per shot", "us", latex=r"t_m"),
                   V("fz", "Zeeman shift", "MHz", latex=r"\Delta f"), V("dB", "Single-shot sensitivity", "pT", latex=r"\delta B")],
        equations=[("Zeeman shift", "fz = gb*B"), ("Shot-noise sensitivity", "dB = 1/(2*pi*gb*sqrt(Ns*T2*tm))")], outputs=["fz", "dB"], tags=["nitrogen vacancy", "diamond", "magnetometer", "odmr", "quantum sensor", "zeeman"], assumptions=["Ideal readout contrast 1, Ramsey sequence at optimal τ ≈ T₂*"],
        references=["Taylor et al. (2008), Nature Physics 4; Degen, Reinhard & Cappellaro (2017), Rev. Mod. Phys. 89"], example={"gb": "28.024 GHz/T", "B": "1 mT", "Ns": "1e12", "T2": "1 us", "tm": "1 us"}),
    Calculation(
        id="quantum.communication.bb84_key_rate", name="BB84 secret-key fraction, fibre loss and key rate",
        disciplines=["quantum", "computer", "cybersecurity"], subdisciplines=["Quantum Communication / Cryptography", "Cryptographic Engineering"],
        description="Asymptotic secret fraction 1 − 2h₂(e) from the quantum bit error rate, channel transmission through fibre, and the resulting secret-key rate.",
        variables=[V("fs", "Source pulse rate", "MHz"), V("mu", "Mean photon number per pulse", "1", latex=r"\mu"), V("al", "Fibre attenuation", "dB/km", latex=r"\alpha"), V("Lf", "Fibre length", "km"), V("ed", "Detector efficiency", "%", latex=r"\eta_d"), V("e", "Quantum bit error rate", "%", latex=r"e", min=0.0001, max=49.9),
                   V("Tr", "Channel transmission", "%", latex=r"T"), V("Rd", "Detection rate", "kHz", latex=r"R_{det}"), V("h2", "Binary entropy h₂(e)", "1", latex=r"h_2(e)"), V("fsec", "Secret fraction", "%", latex=r"r", signed=True), V("Rk", "Secret-key rate", "kHz", latex=r"R_{key}", signed=True)],
        equations=[("Transmission", "Tr = 10^(-al*Lf/10)"), ("Detection rate", "Rd = fs*mu*Tr*ed/2"), ("Binary entropy", "h2 = -e*log2(e) - (1 - e)*log2(1 - e)"), ("Secret fraction", "fsec = 1 - 2*h2"), ("Key rate", "Rk = Rd*fsec")], outputs=["Tr", "Rd", "fsec", "Rk"],
        tags=["qkd", "bb84", "quantum key distribution", "fibre", "secret key", "qber"], validity=[("fsec > 0", "QBER too high (> ≈ 11 %): no secret key can be distilled")], assumptions=["Single-photon source approximation (no decoy-state/PNS correction), ideal error-correction efficiency, factor ½ for basis sifting"],
        references=["Shor & Preskill (2000), PRL 85; Scarani et al. (2009), Rev. Mod. Phys. 81"], example={"fs": "100 MHz", "mu": "0.1", "al": "0.2 dB/km", "Lf": "50 km", "ed": "10 %", "e": "2 %"}),
    # ------------------------------------------------------------------ nano
    Calculation(
        id="nanotech.nanoelectronics.mosfet_square_law", name="MOSFET drain current (square law)",
        disciplines=["nanotech", "electrical"], subdisciplines=["Nanoelectronics", "Electronics Engineering"],
        description="Saturation and triode drain current and transconductance of a long-channel MOSFET.",
        variables=[V("mu", "Carrier mobility", "cm^2/(V*s)", latex=r"\mu"), V("Cox", "Gate-oxide capacitance per area", "uF/cm^2", latex=r"C_{ox}"), V("WL", "Aspect ratio W/L", "1"), V("Vgs", "Gate–source voltage", "V", latex=r"V_{GS}"), V("Vt", "Threshold voltage", "V", latex=r"V_T"), V("Vds", "Drain–source voltage (triode)", "V", latex=r"V_{DS}"),
                   V("Ids", "Saturation current", "mA", latex=r"I_{D,sat}"), V("Idt", "Triode current", "mA", latex=r"I_{D,tri}"), V("gm", "Transconductance (saturation)", "mS", latex=r"g_m")],
        equations=[("Saturation current", "Ids = mu*Cox*WL*(Vgs - Vt)^2/2"), ("Triode current", "Idt = mu*Cox*WL*((Vgs - Vt)*Vds - Vds^2/2)"), ("Transconductance", "gm = mu*Cox*WL*(Vgs - Vt)")], outputs=["Ids", "Idt", "gm"], tags=["transistor", "cmos", "mosfet", "nanoelectronics", "drain current", "device"],
        validity=[("Vgs > Vt", "device is in cut-off (V_GS ≤ V_T)"), ("Vds < Vgs - Vt", "V_DS exceeds V_GS − V_T: the device is in saturation, not triode")], assumptions=["Long-channel strong inversion; velocity saturation, DIBL and tunnelling in nanoscale devices are not included"], references=["Sedra & Smith, Microelectronic Circuits, Ch. 5"],
        example={"mu": "300 cm^2/(V*s)", "Cox": "1.7 uF/cm^2", "WL": "10", "Vgs": "1.2 V", "Vt": "0.4 V", "Vds": "0.3 V"}),
    Calculation(
        id="nanotech.nanoelectronics.single_electron_charging", name="Single-electron charging energy and blockade temperature",
        disciplines=["nanotech", "quantum"], subdisciplines=["Nanoelectronics", "Nanomaterials"],
        description="Charging energy of a quantum dot or nanoparticle island, the temperature below which Coulomb blockade is observable, and the gate-voltage period of conductance oscillations.",
        variables=[qe(), kB(), V("Cs", "Island capacitance", "aF", latex=r"C_\Sigma"), V("Cg", "Gate capacitance", "aF", latex=r"C_g"), V("Ec", "Charging energy", "meV", latex=r"E_C"), V("Tb", "Blockade temperature (E_C ≈ 10 k_BT)", "K", latex=r"T_{max}"), V("dVg", "Coulomb-oscillation period", "mV", latex=r"\Delta V_g")],
        equations=[("Charging energy", "Ec = qe^2/(2*Cs)"), ("Blockade temperature", "Tb = Ec/(10*kB)"), ("Oscillation period", "dVg = qe/Cg")], outputs=["Ec", "Tb", "dVg"], tags=["set", "coulomb blockade", "quantum dot", "single electron", "nanoparticle", "capacitance"], assumptions=["Orthodox theory; level spacing neglected"],
        references=["Likharev (1999), Proc. IEEE 87(4)"], example={"Cs": "1 aF", "Cg": "5 aF"}),
    Calculation(
        id="nanotech.nanomedicine.stokes_einstein_transport", name="Nanoparticle diffusion (Stokes–Einstein)",
        disciplines=["nanotech", "biomedical"], subdisciplines=["Nanomedicine", "Nano-biosensors"],
        description="Diffusion coefficient of a spherical nanoparticle in a fluid and the time to diffuse a given distance (e.g. through tissue or across a sensor gap).",
        variables=[kB(), V("T", "Temperature", "K"), V("eta", "Fluid viscosity", "cP", latex=r"\eta"), V("dh", "Hydrodynamic diameter", "nm", latex=r"d_h"), V("xd", "Diffusion distance", "um", latex=r"x"), V("D", "Diffusion coefficient", "um^2/s"), V("td", "Diffusion time", "s", latex=r"t")],
        equations=[("Stokes–Einstein", "D = kB*T/(3*pi*eta*dh)"), ("Diffusion time (1-D)", "td = xd^2/(2*D)")], outputs=["D", "td"], tags=["diffusion", "drug delivery", "nanoparticle", "brownian motion", "dls", "hydrodynamic size"], assumptions=["Dilute dispersion of non-interacting spheres in a Newtonian fluid"],
        references=["Einstein (1905); Berne & Pecora, Dynamic Light Scattering"], example={"T": "37 degC", "eta": "0.69 cP", "dh": "100 nm", "xd": "50 um"}),
    Calculation(
        id="nanotech.nanomaterials.surface_area_dispersion", name="Nanoparticle specific surface area and particle count",
        disciplines=["nanotech", "materials", "chemical"], subdisciplines=["Nanomaterials", "Powder Technology"],
        description="Surface-to-volume ratio, specific surface area, and number of particles per gram for monodisperse spheres.",
        variables=[V("d", "Particle diameter", "nm"), V("rho", "Material density", "g/cm^3", latex=r"\rho"), V("SV", "Surface-to-volume ratio", "1/nm"), V("SSA", "Specific surface area", "m^2/g"), V("Ng", "Particles per gram", "1/g")],
        equations=[("Surface/volume", "SV = 6/d"), ("Specific surface area", "SSA = 6/(rho*d)"), ("Particles per gram", "Ng = 6/(pi*rho*d^3)")], outputs=["SV", "SSA", "Ng"], tags=["bet", "catalyst", "surface area", "nanoparticle", "dispersion", "size effect"], assumptions=["Monodisperse, smooth, non-porous spheres"], references=["Gregg & Sing, Adsorption, Surface Area and Porosity"], example={"d": "20 nm", "rho": "4.23 g/cm^3"}),
    Calculation(
        id="nanotech.nanobiosensors.binding_lod", name="Nano-biosensor binding response and limit of detection",
        disciplines=["nanotech", "biomedical"], subdisciplines=["Nano-biosensors", "Bioinstrumentation"],
        description="Equilibrium Langmuir binding signal, low-concentration sensitivity and the limit of detection from baseline noise (3.3σ/S).",
        variables=[V("Rmax", "Maximum response", "RU", latex=r"R_{max}"), V("KD", "Dissociation constant", "nM", latex=r"K_D"), V("cc", "Analyte concentration", "nM", latex=r"c"), V("sn", "Baseline noise (σ)", "RU", latex=r"\sigma"), V("Req", "Equilibrium response", "RU", latex=r"R_{eq}"),
                   V("Ss", "Low-concentration sensitivity", "RU/nM", latex=r"S"), V("LOD", "Limit of detection", "pM")],
        equations=[("Langmuir binding", "Req = Rmax*cc/(KD + cc)"), ("Sensitivity", "Ss = Rmax/KD"), ("Limit of detection", "LOD = 33*sn/(10*Ss)")], outputs=["Req", "Ss", "LOD"], tags=["spr", "biosensor", "limit of detection", "affinity", "langmuir", "assay"], assumptions=["1:1 binding at equilibrium; mass-transport limitations ignored"],
        references=["ICH Q2(R1); Schasfoort, Handbook of SPR"], example={"Rmax": "120 RU", "KD": "5 nM", "cc": "2 nM", "sn": "0.3 RU"}),
    # ------------------------------------------------------------------ synthetic biology
    Calculation(
        id="synbio.circuits.hill_activation_repression", name="Hill-function gene regulation",
        disciplines=["synbio", "biomedical"], subdisciplines=["Genetic Circuit Design"],
        description="Expression rate of a promoter activated or repressed by a transcription factor with cooperativity n.",
        variables=[V("Vm", "Maximal expression rate", "nM/min", latex=r"\beta"), V("Kh", "Half-activation concentration", "nM", latex=r"K"), V("nh", "Hill coefficient", "1", latex=r"n"), V("x", "Regulator concentration", "nM"), V("ya", "Activated expression rate", "nM/min", latex=r"y_{act}"), V("yr", "Repressed expression rate", "nM/min", latex=r"y_{rep}")],
        equations=[("Activation", "ya = Vm*(x/Kh)^nh/(1 + (x/Kh)^nh)"), ("Repression", "yr = Vm/(1 + (x/Kh)^nh)")], outputs=["ya", "yr"], tags=["promoter", "transcription factor", "toggle switch", "repressilator", "cooperativity", "gene circuit"], assumptions=["Quasi-steady-state binding, no leakiness"], references=["Alon, An Introduction to Systems Biology, Ch. 2"], example={"Vm": "100 nM/min", "Kh": "50 nM", "nh": "2", "x": "80 nM"}),
    Calculation(
        id="synbio.circuits.protein_steady_state", name="Steady-state mRNA and protein levels",
        disciplines=["synbio", "biomedical"], subdisciplines=["Genetic Circuit Design", "Biomanufacturing"],
        description="Steady-state concentrations from transcription, translation, degradation and growth-dilution rates.",
        variables=[V("am", "Transcription rate", "nM/min", latex=r"\alpha_m"), V("dm", "mRNA degradation rate", "1/min", latex=r"\delta_m"), V("ap", "Translation rate per mRNA", "1/min", latex=r"\alpha_p"), V("dp", "Protein degradation rate", "1/min", latex=r"\delta_p"), V("mg", "Growth dilution rate", "1/min", latex=r"\mu"),
                   V("ms", "Steady-state mRNA", "nM", latex=r"m^*"), V("ps", "Steady-state protein", "nM", latex=r"p^*"), V("tm", "Protein response time (half-rise)", "min", latex=r"t_{1/2}")],
        equations=[("mRNA", "ms = am/(dm + mg)"), ("Protein", "ps = ap*ms/(dp + mg)"), ("Response time", "tm = log(2)/(dp + mg)")], outputs=["ms", "ps", "tm"], tags=["expression", "mrna", "protein", "dilution", "kinetics", "chassis"], assumptions=["Linear first-order degradation, constant growth rate"], references=["Alon, Ch. 2; Weiss et al., Genetic Circuit Building Blocks"], example={"am": "5 nM/min", "dm": "0.2 1/min", "ap": "2 1/min", "dp": "0.01 1/min", "mg": "0.01 1/min"}),
    Calculation(
        id="synbio.metabolic.yield_titer_productivity", name="Fermentation yield, titer and productivity",
        disciplines=["synbio", "chemical"], subdisciplines=["Metabolic Engineering", "Biomanufacturing", "Biochemical Engineering"],
        description="Process performance metrics of an engineered strain and fraction of the theoretical maximum yield achieved.",
        variables=[V("S0", "Initial substrate", "g/L", latex=r"S_0"), V("Sf", "Final substrate", "g/L", latex=r"S_f"), V("Pf", "Final product concentration (titer)", "g/L", latex=r"P"), V("tf", "Fermentation time", "h"), V("Ym", "Theoretical maximum yield", "g/g", latex=r"Y_{max}"), V("Y", "Yield on substrate", "g/g", latex=r"Y_{P/S}"),
                   V("Qp", "Volumetric productivity", "g/(L*h)", latex=r"Q_P"), V("fy", "Fraction of theoretical yield", "%")],
        equations=[("Yield", "Y = Pf/(S0 - Sf)"), ("Productivity", "Qp = Pf/tf"), ("Yield fraction", "fy = Y/Ym")], outputs=["Y", "Qp", "fy"], tags=["tir", "titer rate yield", "strain engineering", "bioprocess", "scale-up", "bioproduct"], validity=[("S0 > Sf", "final substrate must be below the initial substrate")],
        assumptions=["Batch operation, product-only accounting (no by-product balance)"], references=["Crater & Lievense (2018), FEMS Microbiol. Lett. 365"], example={"S0": "100 g/L", "Sf": "5 g/L", "Pf": "38 g/L", "tf": "48 h", "Ym": "0.51 g/g"}),
    Calculation(
        id="synbio.biomanufacturing.oxygen_transfer", name="Bioreactor oxygen transfer and required kLa",
        disciplines=["synbio", "chemical"], subdisciplines=["Biomanufacturing", "Biochemical Engineering"],
        description="Oxygen transfer rate, oxygen uptake by cells, and the volumetric mass-transfer coefficient needed to sustain a culture.",
        variables=[V("kLa", "Volumetric mass-transfer coefficient", "1/h", latex=r"k_La"), V("Cs", "Saturation DO", "mg/L", latex=r"C^*"), V("CL", "Dissolved oxygen", "mg/L", latex=r"C_L"), V("X", "Cell density", "g/L"), V("qO2", "Specific oxygen uptake", "mmol/(g*h)", latex=r"q_{O_2}"),
                   C("MO2", "Molar mass of O₂", 32, "g/mol", latex=r"M_{O_2}"), V("OTR", "Oxygen transfer rate", "mmol/(L*h)"), V("OUR", "Oxygen uptake rate", "mmol/(L*h)"), V("kreq", "Required kLa", "1/h", latex=r"k_La_{req}")],
        equations=[("Transfer rate", "OTR = kLa*(Cs - CL)/MO2"), ("Uptake rate", "OUR = qO2*X"), ("Required kLa", "kreq = OUR*MO2/(Cs - CL)")], outputs=["OTR", "OUR", "kreq"], tags=["aeration", "agitation", "kla", "fermenter", "oxygen limitation", "scale-up"], validity=[("OTR > OUR", "oxygen transfer is below uptake: the culture will become oxygen limited")],
        assumptions=["Well-mixed liquid, constant kLa; gas-phase oxygen depletion ignored"], references=["Shuler & Kargi, Bioprocess Engineering, Ch. 10"], example={"kLa": "150 1/h", "Cs": "7.5 mg/L", "CL": "2.5 mg/L", "X": "4 g/L", "qO2": "5 mmol/(g*h)"}),
    Calculation(
        id="synbio.crispr.library_coverage_offtarget", name="CRISPR library coverage and off-target risk",
        disciplines=["synbio", "biomedical"], subdisciplines=["CRISPR Engineering"],
        description="Number of clones/cells needed to cover a pooled guide library with a confidence level, and the probability of at least one off-target edit from per-site cutting probabilities.",
        variables=[V("Lg", "Guides in library", "1", latex=r"L"), V("Pc", "Desired coverage probability per guide", "%", latex=r"P"), V("ns", "Candidate off-target sites", "1", latex=r"n_s"), V("po", "Cutting probability per off-target site", "%", latex=r"p"), V("nc", "Cells required (sampling coverage)", "1", latex=r"n"),
                   V("fold", "Fold-coverage per guide", "1"), V("Po", "Probability of ≥ 1 off-target edit", "%", latex=r"P_{off}")],
        equations=[("Cells required", "nc = log(1 - Pc)/log(1 - 1/Lg)"), ("Fold coverage", "fold = nc/Lg"), ("Off-target risk", "Po = 1 - (1 - po)^ns")], outputs=["nc", "fold", "Po"], tags=["crispr", "cas9", "pooled screen", "guide rna", "off-target", "library"], assumptions=["Equal guide representation, independent off-target events"], references=["Joung et al. (2017), Nature Protocols 12; Hsu et al. (2013), Nature Biotechnol. 31"], example={"Lg": "70000", "Pc": "99 %", "ns": "20", "po": "0.5 %"}),
    # ------------------------------------------------------------------ climate and resilience
    Calculation(
        id="climate.geoengineering.forcing_temperature", name="Radiative forcing and equilibrium warming (CO₂ and albedo)",
        disciplines=["climate", "environmental"], subdisciplines=["Geoengineering", "Climate Adaptation Design"],
        description="CO₂ radiative forcing 5.35·ln(C/C₀), forcing from a planetary albedo change (solar geoengineering), and equilibrium temperature change from a climate-sensitivity parameter.",
        variables=[C("a53", "CO₂ forcing coefficient", 5.35, "W/m^2", latex=r"\alpha"), C("S0", "Solar constant", 1361, "W/m^2", latex=r"S_0"), V("C", "CO₂ concentration", "ppm"), V("C0", "Reference CO₂ concentration", "ppm", latex=r"C_0", default=280), V("da", "Increase in planetary albedo", "1", latex=r"\Delta\alpha", signed=True),
                   V("lam", "Climate sensitivity parameter", "K/(W/m^2)", latex=r"\lambda", default=0.8), V("dFc", "CO₂ forcing", "W/m^2", latex=r"\Delta F_{CO_2}", signed=True), V("dFa", "Albedo forcing", "W/m^2", latex=r"\Delta F_{alb}", signed=True),
                   V("dT", "Equilibrium temperature change", "K", latex=r"\Delta T", delta=True, signed=True)],
        equations=[("CO₂ forcing", "dFc = a53*log(C/C0)"), ("Albedo forcing", "dFa = -S0/4*da"), ("Equilibrium warming", "dT = lam*(dFc + dFa)")], outputs=["dFc", "dFa", "dT"], tags=["climate change", "radiative forcing", "climate sensitivity", "solar geoengineering", "sai", "co2"],
        assumptions=["Global-mean equilibrium response; λ ≈ 0.8 K/(W/m²) corresponds to ≈ 3 K per CO₂ doubling"], references=["Myhre et al. (1998), GRL 25; IPCC AR6 WG1, Ch. 7"], example={"C": "560 ppm", "C0": "280 ppm", "da": "0.01", "lam": "0.8 K/(W/m^2)"}),
    Calculation(
        id="climate.ccs.storage_capacity_cost", name="CO₂ geological storage capacity, injection life and cost",
        disciplines=["climate", "petroleum", "environmental"], subdisciplines=["Carbon Capture and Sequestration", "Reservoir Engineering"],
        description="Volumetric CO₂ storage capacity of a saline aquifer or depleted reservoir, the years of injection at a given annual rate, and the cost of capture and storage.",
        variables=[V("A", "Storage area", "km^2"), V("h", "Net thickness", "m"), V("phi", "Porosity", "%", latex=r"\phi"), V("rco", "CO₂ density at reservoir conditions", "kg/m^3", latex=r"\rho_{CO_2}"), V("Ef", "Storage efficiency factor", "%", latex=r"E"), V("Ra", "Annual injection rate", "Mt/yr"),
                   V("cu", "Capture + transport + storage cost", "USD/t"), V("Mc", "Storage capacity", "Mt", latex=r"M"), V("Ti", "Injection lifetime", "yr"), V("Ct", "Total programme cost over lifetime", "MUSD")],
        equations=[("Capacity", "Mc = A*h*phi*rco*Ef"), ("Injection life", "Ti = Mc/Ra"), ("Total cost", "Ct = Mc*cu")], outputs=["Mc", "Ti", "Ct"], tags=["ccs", "ccus", "saline aquifer", "sequestration", "storage", "net zero"], assumptions=["Static volumetric estimate; dynamic pressure limits and plume migration require reservoir simulation"],
        references=["DOE/NETL Carbon Storage Atlas; Goodman et al. (2011), Int. J. Greenhouse Gas Control 5"], example={"A": "100 km^2", "h": "50 m", "phi": "18 %", "rco": "700 kg/m^3", "Ef": "2 %", "Ra": "1 Mt/yr", "cu": "80 USD/t"}),
    Calculation(
        id="climate.adaptation.clausius_clapeyron_rainfall", name="Warming-adjusted design rainfall (Clausius–Clapeyron scaling)",
        disciplines=["climate", "civil", "environmental"], subdisciplines=["Climate Adaptation Design", "Resilient Infrastructure"],
        description="Extreme-rainfall intensity after a temperature rise using a per-kelvin scaling rate (≈ 7 %/K), and the required increase in drainage capacity.",
        variables=[V("P1", "Present design rainfall intensity", "mm/h"), V("ccr", "Scaling rate per kelvin", "%", latex=r"\kappa", default=7), V("dT", "Temperature rise", "K", latex=r"\Delta T", delta=True), C("k1", "One kelvin", 1, "K", latex=r"1\,\mathrm{K}"), V("P2", "Adjusted design intensity", "mm/h"), V("inc", "Increase in design flow", "%", signed=True)],
        equations=[("Scaled intensity", "P2 = P1*(1 + ccr)^(dT/k1)"), ("Capacity increase", "inc = P2/P1 - 1")], outputs=["P2", "inc"], tags=["climate adaptation", "extreme rainfall", "stormwater", "intensity", "design storm", "clausius-clapeyron"],
        assumptions=["Scaling holds for short-duration convective extremes; some regions show super-CC (≈ 14 %/K) or sub-CC behaviour"], references=["Westra et al. (2014), Rev. Geophys. 52"], example={"P1": "60 mm/h", "ccr": "7 %", "dT": "2 K"}),
    Calculation(
        id="climate.resilience.return_period_risk", name="Return period, design life and exceedance risk",
        disciplines=["climate", "civil"], subdisciplines=["Resilient Infrastructure", "Climate Adaptation Design"],
        description="Probability that an event of return period T is exceeded at least once in n years, and the return period required to hold the risk below a target over a design life.",
        variables=[V("T", "Return period", "yr"), V("n", "Design life", "yr"), V("Rt", "Acceptable risk over design life", "%"), C("y1", "One year", 1, "yr", latex=r"1\,\mathrm{yr}"), V("R", "Risk of at least one exceedance", "%"), V("Treq", "Return period required for target risk", "yr", latex=r"T_{req}")],
        equations=[("Exceedance risk", "R = 1 - (1 - y1/T)^(n/y1)"), ("Required return period", "Treq = y1/(1 - (1 - Rt)^(y1/n))")], outputs=["R", "Treq"], tags=["flood frequency", "risk", "design event", "100-year flood", "probability", "reliability"], assumptions=["Stationary, independent annual maxima (non-stationarity under climate change increases risk)"],
        references=["Chow, Maidment & Mays, Applied Hydrology, Ch. 12"], example={"T": "100 yr", "n": "50 yr", "Rt": "5 %"}),
]
