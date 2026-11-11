"""Broad chemistry, part A: quantum chemistry, photochemistry, polymer chemistry."""

from ..core import C, V
from ._common import R_univ, avogadro, c0, eps0, kB, m_e, planck
from ._pc import ATKINS, chem

QC = "Quantum Chemistry"
PHOTO = "Photochemistry"
POLY = "Polymer Chemistry"
PHYS = "Physical Chemistry"
SPEC = "Atomic Structure and Spectroscopy"
KIN = "Chemical Kinetics"

ODIAN = "Odian, Principles of Polymerization"
RUBIN = "Rubinstein & Colby, Polymer Physics"
LOWRY = "Turro, Ramamurthy & Scaiano, Modern Molecular Photochemistry of Organic Molecules"


def dbye() -> "C":
    return C("Dby", "Debye (dipole-moment unit)", 3.33564095e-30, "C*m", latex=r"\mathrm{D}")


CALCS = [
    # ------------------------------------------------------------------ quantum chemistry
    chem("chemistry.quantum.huckel_linear_polyene", "Hückel theory of a linear polyene: HOMO–LUMO gap and π energy", [QC, "Organic Chemistry"],
         "Hückel orbital energies of an N-carbon linear conjugated polyene: HOMO and LUMO energies, the gap and absorption wavelength, the total π energy and the delocalisation energy relative to isolated double bonds.",
         [V("Nc", "Number of carbon atoms (even)", "1", latex=r"N", min=2), V("al", "Coulomb integral α", "eV", latex=r"\alpha", signed=True), V("be", "Resonance integral β (negative)", "eV", latex=r"\beta", signed=True), planck(), c0(), V("th", "Angle π/(N+1)", "rad", latex=r"\theta"),
          V("Eh", "HOMO energy", "eV", latex=r"E_{HOMO}", signed=True), V("El", "LUMO energy", "eV", latex=r"E_{LUMO}", signed=True), V("gap", "HOMO–LUMO gap", "eV", latex=r"\Delta E"), V("lam", "Absorption wavelength", "nm", latex=r"\lambda"), V("Ep", "Total π energy", "eV", latex=r"E_\pi", signed=True),
          V("DE", "Delocalisation energy", "eV", latex=r"DE", signed=True)],
         [("Angle", "th = pi/(Nc + 1)"), ("HOMO", "Eh = al + 2*be*cos(Nc/2*th)"), ("LUMO", "El = al + 2*be*cos((Nc/2 + 1)*th)"), ("Gap", "gap = El - Eh"), ("Wavelength", "lam = hP*c0/gap"),
          ("π energy", "Ep = Nc*al + 4*be*sin(Nc*th/4)*cos((Nc/2 + 1)*th/2)/sin(th/2)"), ("Delocalisation energy", "DE = Ep - Nc*(al + be)")], ["th", "Eh", "El", "gap", "lam", "Ep", "DE"], {"Nc": "6", "al": "0 eV", "be": "-5.0 eV"}, ATKINS + ", Ch. 9",
         "Hückel approximation (σ–π separation, nearest-neighbour β, all α equal); β is empirical: about −2.4 eV for thermochemistry, about −5 eV to reproduce polyene UV spectra", extra=("materials",), tags=["huckel", "polyene", "homo lumo", "conjugation", "uv absorption"]),
    chem("chemistry.quantum.free_electron_polyene_dye", "Free-electron (particle-in-a-box) model of conjugated dyes", [QC, SPEC],
         "Longest-wavelength π–π* absorption of a conjugated chain from the particle-in-a-box model (N π electrons in a box of length (N+1)·b).",
         [V("Ne", "Number of π electrons (even)", "1", latex=r"N", min=2), V("bl", "Mean bond length", "angstrom", latex=r"b"), planck(), c0(), m_e(), V("Lb", "Box length", "nm", latex=r"L"), V("dE", "HOMO→LUMO energy", "eV", latex=r"\Delta E"), V("lam", "Absorption wavelength", "nm", latex=r"\lambda")],
         [("Box length", "Lb = (Ne + 1)*bl"), ("Excitation energy", "dE = hP^2*(Ne + 1)/(8*me*Lb^2)"), ("Wavelength", "lam = hP*c0/dE")], ["Lb", "dE", "lam"], {"Ne": "6", "bl": "1.4 angstrom"}, ATKINS + ", Ch. 8",
         "Free-electron molecular orbital (FEMO) model; qualitative: reasonable for long cyanine dyes, a poor predictor for short polyenes", extra=("materials",), tags=["femo", "particle in a box", "cyanine dye", "absorption", "conjugation"]),
    chem("chemistry.quantum.lcao_two_orbital", "LCAO molecular orbitals of a two-centre bond with overlap", [QC],
         "Bonding and antibonding energies of two atomic orbitals with overlap S from the secular equation, the stabilisation of the bonding orbital and the net energy change for two electrons.",
         [V("al", "Atomic orbital energy α", "eV", latex=r"\alpha", signed=True), V("be", "Resonance integral β (negative)", "eV", latex=r"\beta", signed=True), V("Sv", "Overlap integral", "1", latex=r"S"), V("Eb", "Bonding orbital energy", "eV", latex=r"E_+", signed=True), V("Ea", "Antibonding orbital energy", "eV", latex=r"E_-", signed=True),
          V("sb", "Stabilisation of the bonding orbital", "eV", signed=True), V("da", "Destabilisation of the antibonding orbital", "eV", signed=True), V("E2", "Energy change with two electrons", "eV", signed=True), V("E4", "Energy change with four electrons", "eV", signed=True)],
         [("Bonding orbital", "Eb = (al + be)/(1 + Sv)"), ("Antibonding orbital", "Ea = (al - be)/(1 - Sv)"), ("Stabilisation", "sb = Eb - al"), ("Destabilisation", "da = Ea - al"), ("Two electrons", "E2 = 2*(Eb - al)"), ("Four electrons", "E4 = 2*(Eb - al) + 2*(Ea - al)")], ["Eb", "Ea", "sb", "da", "E2", "E4"],
         {"al": "-13.6 eV", "be": "-9.0 eV", "Sv": "0.4"}, ATKINS + ", Ch. 9", "Two identical atomic orbitals; with S > 0 the antibonding orbital is destabilised more than the bonding one is stabilised (so four electrons repel)", tags=["lcao", "molecular orbital", "overlap", "h2", "secular equation"]),
    chem("chemistry.quantum.mo_bond_order_magnetism", "Molecular-orbital bond order, spin-only moment and bond-length trend", [QC, "General Chemistry"],
         "Bond order from the numbers of bonding and antibonding electrons, whether the molecule is paramagnetic, its spin-only magnetic moment and the Pauling estimate of the bond length from the single-bond length.",
         [V("nb", "Electrons in bonding orbitals", "1", latex=r"n_b", min=0), V("na", "Electrons in antibonding orbitals", "1", latex=r"n_a", min=0), V("nu", "Unpaired electrons", "1", latex=r"n_u", min=0, signed=True), V("d1", "Single-bond length", "angstrom", latex=r"d_1"), C("pc", "Pauling coefficient", 0.6, "angstrom", latex=r"0.60"),
          V("bo", "Bond order", "1", latex=r"BO"), V("mu", "Spin-only magnetic moment (μ_B)", "1", latex=r"\mu_{so}"), V("mg", "Paramagnetic (1) or diamagnetic (0)", "1"), V("dn", "Estimated bond length", "angstrom", latex=r"d_n")],
         [("Bond order", "bo = (nb - na)/2"), ("Spin-only moment", "mu = sqrt(nu*(nu + 2))"), ("Paramagnetism", "mg = Piecewise((1, nu > 0), (0, True))"), ("Bond length", "dn = d1 - pc*log(bo)/log(10)")], ["bo", "mu", "mg", "dn"],
         {"nb": "8", "na": "4", "nu": "2", "d1": "1.48 angstrom"}, "Housecroft & Sharpe, Inorganic Chemistry, Ch. 2", "Valence-orbital counting; O₂ shown (bond order 2, two unpaired electrons, 2.83 μ_B)", validity=[("bo > 0", "Bond order must be positive for a bound molecule")],
         tags=["bond order", "molecular orbital", "paramagnetism", "oxygen", "pauling"]),
    chem("chemistry.quantum.conceptual_dft_descriptors", "Conceptual DFT: electronegativity, hardness and electrophilicity", [QC],
         "Mulliken electronegativity, chemical potential, hardness, softness and electrophilicity index from the ionisation energy and electron affinity, with an approximate conversion to the Pauling scale.",
         [V("IE", "Ionisation energy", "eV"), V("EA", "Electron affinity", "eV"), C("cx", "Mulliken→Pauling slope", 0.336, "1/eV"), C("cz", "Mulliken→Pauling offset", 0.615, "eV"), V("chiM", "Mulliken electronegativity", "eV", latex=r"\chi_M"), V("mu", "Chemical potential", "eV", latex=r"\mu", signed=True), V("eta", "Chemical hardness", "eV", latex=r"\eta"),
          V("sf", "Softness", "1/eV", latex=r"S"), V("om", "Electrophilicity index", "eV", latex=r"\omega"), V("chiP", "Pauling electronegativity (approximate)", "1", latex=r"\chi_P")],
         [("Mulliken electronegativity", "chiM = (IE + EA)/2"), ("Chemical potential", "mu = -chiM"), ("Hardness", "eta = (IE - EA)/2"), ("Softness", "sf = 1/(2*eta)"), ("Electrophilicity", "om = mu^2/(2*eta)"), ("Pauling scale", "chiP = cx*(chiM - cz)")], ["chiM", "mu", "eta", "sf", "om", "chiP"],
         {"IE": "12.97 eV", "EA": "3.61 eV"}, "Parr & Yang, Density-Functional Theory of Atoms and Molecules, Ch. 4", "Finite-difference approximation (chlorine shown); Pauling conversion χ_P ≈ 0.336(χ_M − 0.615)", tags=["electronegativity", "hardness", "electrophilicity", "mulliken", "hsab"]),
    chem("chemistry.quantum.debye_dipole_polarisation", "Dipole moment from the Debye equation (permittivity and refractive index)", [QC, PHYS],
         "Molar polarisation from the relative permittivity, molar refraction from the refractive index, and the permanent dipole moment (in C·m and debye) from their difference at temperature T.",
         [V("er", "Relative permittivity", "1", latex=r"\varepsilon_r"), V("nr", "Refractive index", "1", latex=r"n"), V("Mm", "Molar mass", "g/mol", latex=r"M"), V("rho", "Mass density", "kg/m^3", latex=r"\rho"), V("T", "Temperature", "K"), eps0(), kB(), avogadro(), dbye(), V("Pm", "Molar polarisation", "cm^3/mol", latex=r"P_m"),
          V("Rm", "Molar refraction", "cm^3/mol", latex=r"R_m"), V("mu", "Dipole moment", "C*m", latex=r"\mu"), V("muD", "Dipole moment in debye", "1", latex=r"\mu/\mathrm{D}")],
         [("Molar polarisation", "Pm = (er - 1)/(er + 2)*Mm/rho"), ("Molar refraction", "Rm = (nr^2 - 1)/(nr^2 + 2)*Mm/rho"), ("Dipole moment", "mu = sqrt(9*eps0*kB*T*(Pm - Rm)/NA)"), ("In debye", "muD = mu/Dby")], ["Pm", "Rm", "mu", "muD"],
         {"er": "1.0037", "nr": "1.00044", "Mm": "36.46 g/mol", "rho": "1.49 kg/m^3", "T": "298.15 K"}, ATKINS + ", Ch. 17", "Dilute gas or dilute solution where molecules do not interact (hydrogen chloride vapour shown: 1.05 D against 1.08 D)", tags=["debye equation", "dipole moment", "polarisation", "permittivity", "refractive index"]),

    # ------------------------------------------------------------------ photochemistry
    chem("chemistry.photochem.quantum_yield_actinometry", "Photochemical quantum yield from lamp power and absorbed light", [PHOTO],
         "Photon flux of a monochromatic lamp, the absorbed fraction, the photons absorbed in an irradiation, and the quantum yield from the amount of reactant converted.",
         [V("P", "Lamp power reaching the cell", "mW"), V("lam", "Wavelength", "nm", latex=r"\lambda"), V("tt", "Irradiation time", "min", latex=r"t"), V("Ab", "Absorbance of the solution", "1", latex=r"A"), V("dn", "Reactant converted", "umol", latex=r"\Delta n"), planck(), c0(), avogadro(),
          V("qf", "Photon flux", "umol/s", latex=r"q"), V("fa", "Fraction of light absorbed", "%", latex=r"1-10^{-A}"), V("na", "Photons absorbed (moles)", "umol"), V("Phi", "Quantum yield", "1", latex=r"\Phi")],
         [("Photon flux", "qf = P*lam/(hP*c0*NA)"), ("Absorbed fraction", "fa = 1 - 10^(-Ab)"), ("Photons absorbed", "na = qf*tt*fa"), ("Quantum yield", "Phi = dn/na")], ["qf", "fa", "na", "Phi"], {"P": "5 mW", "lam": "365 nm", "tt": "10 min", "Ab": "1.2", "dn": "8 umol"},
         LOWRY + ", Ch. 4", "Monochromatic light; all absorbed photons are produced by the analyte; quantum yield may exceed 1 for chain reactions", tags=["quantum yield", "actinometry", "photon flux", "einstein", "photoreaction"]),
    chem("chemistry.photochem.excited_state_kinetics", "Excited-state decay: lifetime and fluorescence, intersystem-crossing yields", [PHOTO, KIN],
         "Observed lifetime and the fluorescence, intersystem-crossing and non-radiative quantum yields from the radiative, intersystem-crossing and non-radiative rate constants, with the natural radiative lifetime.",
         [V("kr", "Radiative rate constant", "1/ns", latex=r"k_r"), V("kisc", "Intersystem-crossing rate constant", "1/ns", latex=r"k_{isc}"), V("knr", "Non-radiative (internal conversion) rate constant", "1/ns", latex=r"k_{nr}"), V("tau", "Observed lifetime", "ns", latex=r"\tau"), V("tau0", "Natural radiative lifetime", "ns", latex=r"\tau_0"),
          V("Pf", "Fluorescence quantum yield", "%", latex=r"\Phi_f"), V("Pi", "Intersystem-crossing yield", "%", latex=r"\Phi_{isc}"), V("Pn", "Non-radiative yield", "%", latex=r"\Phi_{nr}")],
         [("Lifetime", "tau = 1/(kr + kisc + knr)"), ("Natural lifetime", "tau0 = 1/kr"), ("Fluorescence yield", "Pf = kr*tau"), ("Intersystem crossing yield", "Pi = kisc*tau"), ("Non-radiative yield", "Pn = knr*tau")], ["tau", "tau0", "Pf", "Pi", "Pn"],
         {"kr": "0.05 1/ns", "kisc": "0.02 1/ns", "knr": "0.03 1/ns"}, LOWRY + ", Ch. 3", "Single excited state decaying by first-order channels; Φ_f + Φ_isc + Φ_nr = 1", tags=["jablonski", "fluorescence", "lifetime", "intersystem crossing", "quantum yield"]),
    chem("chemistry.photochem.forster_energy_transfer", "Förster resonance energy transfer (FRET)", [PHOTO, "Biochemistry"],
         "Transfer efficiency and rate constant at donor–acceptor distance r for a given Förster radius, and the distance implied by a measured efficiency.",
         [V("R0", "Förster radius", "angstrom", latex=r"R_0"), V("rd", "Donor–acceptor distance", "angstrom", latex=r"r"), V("tD", "Donor lifetime without acceptor", "ns", latex=r"\tau_D"), V("Em", "Measured efficiency", "%", latex=r"E_{meas}"), V("E", "FRET efficiency at r", "%"),
          V("kT", "Energy-transfer rate constant", "1/ns", latex=r"k_T"), V("rE", "Distance from the measured efficiency", "angstrom", latex=r"r_E")],
         [("Efficiency", "E = 1/(1 + (rd/R0)^6)"), ("Transfer rate", "kT = (R0/rd)^6/tD"), ("Distance from efficiency", "rE = R0*((1 - Em)/Em)^(1/6)")], ["E", "kT", "rE"], {"R0": "50 angstrom", "rd": "45 angstrom", "tD": "4 ns", "Em": "70 %"}, "Lakowicz, Principles of Fluorescence Spectroscopy, Ch. 13",
         "Point dipoles with random orientation (κ² = 2/3) in the weak-coupling limit; 1–10 nm range", extra=("biomedical",), tags=["fret", "forster", "energy transfer", "molecular ruler", "fluorescence"]),
    chem("chemistry.photochem.marcus_electron_transfer", "Marcus theory of electron-transfer rates", [PHOTO, "Electrochemistry"],
         "Non-adiabatic electron-transfer rate constant from the coupling, reorganisation energy and driving force, the activation free energy, the maximum rate and whether the reaction is in the normal or inverted region.",
         [V("Hab", "Electronic coupling", "meV", latex=r"H_{AB}"), V("lm", "Reorganisation energy", "eV", latex=r"\lambda"), V("dG", "Reaction free energy", "eV", latex=r"\Delta G^\circ", signed=True), V("T", "Temperature", "K"), planck(), kB(), V("dGa", "Activation free energy", "meV", latex=r"\Delta G^\ddagger"),
          V("ket", "Electron-transfer rate constant", "1/s", latex=r"k_{ET}"), V("kmax", "Rate constant at the optimum (−ΔG° = λ)", "1/s", latex=r"k_{max}"), V("rg", "Region (−1 normal, 0 optimum, +1 inverted)", "1", signed=True)],
         [("Activation free energy", "dGa = (dG + lm)^2/(4*lm)"), ("Rate constant", "ket = 4*pi^2*Hab^2/(hP*sqrt(4*pi*lm*kB*T))*exp(-dGa/(kB*T))"), ("Maximum rate", "kmax = 4*pi^2*Hab^2/(hP*sqrt(4*pi*lm*kB*T))"), ("Region", "rg = sign(-dG - lm)")], ["dGa", "ket", "kmax", "rg"],
         {"Hab": "5 meV", "lm": "0.8 eV", "dG": "-0.5 eV", "T": "298.15 K"}, ATKINS + ", Ch. 22", "Classical high-temperature Marcus expression; weak electronic coupling", extra=("biomedical",), tags=["marcus", "electron transfer", "reorganisation energy", "inverted region", "photosynthesis"]),

    # ------------------------------------------------------------------ polymer chemistry
    chem("chemistry.polymer.molar_mass_averages", "Molar-mass averages and dispersity of a polymer sample", [POLY],
         "Number-, weight- and z-average molar masses and the dispersity of a sample made of three chain-length fractions.",
         [V("n1", "Moles of fraction 1", "mmol", latex=r"n_1"), V("M1", "Molar mass of fraction 1", "kg/mol", latex=r"M_1"), V("n2", "Moles of fraction 2", "mmol", latex=r"n_2"), V("M2", "Molar mass of fraction 2", "kg/mol", latex=r"M_2"), V("n3", "Moles of fraction 3", "mmol", latex=r"n_3"),
          V("M3", "Molar mass of fraction 3", "kg/mol", latex=r"M_3"), V("Mn", "Number-average molar mass", "kg/mol", latex=r"M_n"), V("Mw", "Weight-average molar mass", "kg/mol", latex=r"M_w"), V("Mz", "z-average molar mass", "kg/mol", latex=r"M_z"), V("Dp", "Dispersity Mw/Mn", "1", latex=r"\mathcal{D}")],
         [("Mn", "Mn = (n1*M1 + n2*M2 + n3*M3)/(n1 + n2 + n3)"), ("Mw", "Mw = (n1*M1^2 + n2*M2^2 + n3*M3^2)/(n1*M1 + n2*M2 + n3*M3)"), ("Mz", "Mz = (n1*M1^3 + n2*M2^3 + n3*M3^3)/(n1*M1^2 + n2*M2^2 + n3*M3^2)"), ("Dispersity", "Dp = Mw/Mn")], ["Mn", "Mw", "Mz", "Dp"],
         {"n1": "2 mmol", "M1": "10 kg/mol", "n2": "3 mmol", "M2": "50 kg/mol", "n3": "1 mmol", "M3": "200 kg/mol"}, ODIAN + ", Ch. 1", "Discrete distribution; Mn ≤ Mw ≤ Mz", extra=("materials",), tags=["molar mass", "dispersity", "pdi", "gpc", "average"]),
    chem("chemistry.polymer.step_growth_carothers", "Step-growth polymerisation: Carothers and Flory equations", [POLY],
         "Degree of polymerisation and number-average molar mass versus conversion p and stoichiometric ratio r, the conversion needed for a target chain length, the dispersity and the gel point of a branched system.",
         [V("pc", "Extent of reaction", "1", latex=r"p"), V("rs", "Stoichiometric ratio r (≤ 1)", "1", latex=r"r"), V("M0", "Mean mass of a repeat unit", "g/mol", latex=r"M_0"), V("Xt", "Target degree of polymerisation", "1", latex=r"X_{target}"), V("fav", "Average functionality (for gelation)", "1", latex=r"f_{avg}"),
          V("Xn", "Number-average degree of polymerisation", "1", latex=r"X_n"), V("Mn", "Number-average molar mass", "kg/mol", latex=r"M_n"), V("preq", "Conversion required for the target", "%"), V("Dp", "Dispersity 1 + p (r = 1)", "1"), V("pg", "Gel-point conversion 2/f", "%", latex=r"p_c")],
         [("Carothers equation", "Xn = (1 + rs)/(1 + rs - 2*rs*pc)"), ("Molar mass", "Mn = Xn*M0"), ("Required conversion", "preq = (1 + rs)*(1 - 1/Xt)/(2*rs)"), ("Dispersity", "Dp = 1 + pc"), ("Gel point", "pg = 2/fav")], ["Xn", "Mn", "preq", "Dp", "pg"],
         {"pc": "0.99", "rs": "1", "M0": "113 g/mol", "Xt": "100", "fav": "2.2"}, ODIAN + ", Ch. 2", "Equal reactivity of all functional groups; no cyclisation (nylon-6,6 repeat unit shown)", extra=("materials",), tags=["step growth", "carothers", "condensation", "nylon", "gel point"]),
    chem("chemistry.polymer.radical_polymerisation_kinetics", "Free-radical chain polymerisation: rate and kinetic chain length", [POLY, KIN],
         "Initiation and propagation rates, kinetic chain length and number-average degree of polymerisation (termination by combination or disproportionation) in a steady-state radical polymerisation.",
         [V("Mc", "Monomer concentration", "mol/L", latex=r"[M]"), V("Ic", "Initiator concentration", "mol/L", latex=r"[I]"), V("kd", "Initiator decomposition constant", "1/s", latex=r"k_d"), V("fe", "Initiator efficiency", "1", latex=r"f"), V("kp", "Propagation constant", "L/(mol*s)", latex=r"k_p"), V("kt", "Termination constant", "L/(mol*s)", latex=r"k_t"),
          V("Ri", "Rate of initiation", "umol/(L*s)", latex=r"R_i"), V("Rp", "Rate of polymerisation", "umol/(L*s)", latex=r"R_p"), V("nu", "Kinetic chain length", "1", latex=r"\nu"), V("Xc", "Degree of polymerisation (combination)", "1", latex=r"X_n^{comb}"), V("Xd", "Degree of polymerisation (disproportionation)", "1", latex=r"X_n^{disp}")],
         [("Initiation rate", "Ri = 2*fe*kd*Ic"), ("Polymerisation rate", "Rp = kp*Mc*sqrt(fe*kd*Ic/kt)"), ("Kinetic chain length", "nu = kp*Mc/(2*sqrt(fe*kd*kt*Ic))"), ("Combination", "Xc = 2*nu"), ("Disproportionation", "Xd = nu")], ["Ri", "Rp", "nu", "Xc", "Xd"],
         {"Mc": "2 mol/L", "Ic": "0.01 mol/L", "kd": "1e-5 1/s", "fe": "0.6", "kp": "176 L/(mol*s)", "kt": "7e7 L/(mol*s)"}, ODIAN + ", Ch. 3", "Steady-state radicals, long chains, no transfer (styrene with AIBN at 60 °C shown)", extra=("chemical", "materials"),
         tags=["free radical", "kinetic chain length", "aibn", "polystyrene", "rate of polymerisation"]),
    chem("chemistry.polymer.flory_huggins_mixing", "Flory–Huggins theory: free energy of mixing and miscibility", [POLY, "Chemical Thermodynamics"],
         "Free energy of mixing per mole of lattice sites for a polymer solution or blend, the critical interaction parameter and composition, and whether the mixture is miscible at all compositions.",
         [V("N1", "Degree of polymerisation of component 1", "1", latex=r"N_1", min=1), V("N2", "Degree of polymerisation of component 2", "1", latex=r"N_2", min=1), V("p2", "Volume fraction of component 2", "1", latex=r"\phi_2"), V("chi", "Flory–Huggins parameter", "1", latex=r"\chi", signed=True), V("T", "Temperature", "K"), R_univ(),
          V("dGm", "Free energy of mixing per mole of sites", "J/mol", latex=r"\Delta G_{mix}", signed=True), V("chic", "Critical interaction parameter", "1", latex=r"\chi_c"), V("pc", "Critical volume fraction of component 2", "1", latex=r"\phi_{2,c}"), V("mis", "Miscible at all compositions (1 = yes)", "1")],
         [("Free energy of mixing", "dGm = R*T*((1 - p2)/N1*log(1 - p2) + p2/N2*log(p2) + chi*(1 - p2)*p2)"), ("Critical parameter", "chic = (1/sqrt(N1) + 1/sqrt(N2))^2/2"), ("Critical composition", "pc = 1/(1 + sqrt(N2/N1))"), ("Miscibility", "mis = Piecewise((1, chi < chic), (0, True))")],
         ["dGm", "chic", "pc", "mis"], {"N1": "1", "N2": "1000", "p2": "0.2", "chi": "0.45", "T": "298.15 K"}, RUBIN + ", Ch. 4", "Regular-solution lattice model with a composition-independent χ", extra=("materials",), tags=["flory huggins", "polymer solution", "miscibility", "phase separation", "blend"]),
    chem("chemistry.polymer.chain_dimensions", "Polymer chain dimensions: ideal chain, worm-like chain and swollen coil", [POLY],
         "End-to-end distance and radius of gyration of a freely jointed chain, the worm-like chain result for a given persistence length, the contour length and the swollen (Flory) radius in a good solvent.",
         [V("Nk", "Number of Kuhn segments", "1", latex=r"N", min=1), V("bk", "Kuhn length", "nm", latex=r"b"), V("Lp", "Persistence length", "nm", latex=r"\ell_p"), V("Lc", "Contour length", "nm", latex=r"L"), V("Rfj", "rms end-to-end distance (ideal chain)", "nm", latex=r"\langle R^2\rangle^{1/2}"), V("Rg", "Radius of gyration (ideal chain)", "nm", latex=r"R_g"),
          V("Rw", "rms end-to-end distance (worm-like chain)", "nm", latex=r"R_{WLC}"), V("Rf", "Flory radius in a good solvent", "nm", latex=r"R_F")],
         [("Contour length", "Lc = Nk*bk"), ("Ideal chain", "Rfj = bk*sqrt(Nk)"), ("Radius of gyration", "Rg = bk*sqrt(Nk/6)"), ("Worm-like chain", "Rw = sqrt(2*Lp*Lc*(1 - Lp/Lc*(1 - exp(-Lc/Lp))))"), ("Flory radius", "Rf = bk*Nk^(3/5)")], ["Lc", "Rfj", "Rg", "Rw", "Rf"],
         {"Nk": "1000", "bk": "1.8 nm", "Lp": "0.9 nm"}, RUBIN + ", Ch. 2–3", "Long flexible chain; Kuhn length b = 2ℓ_p", extra=("materials", "biomedical"), tags=["random coil", "worm-like chain", "radius of gyration", "kuhn length", "flory"]),
    chem("chemistry.polymer.intrinsic_viscosity_mark_houwink", "Intrinsic viscosity and the Mark–Houwink relation", [POLY, "Colloid and Surface Chemistry"],
         "Intrinsic viscosity at a molar mass from a reference point and the Mark–Houwink exponent, the viscosity-average molar mass from a measured [η], and the hydrodynamic radius (Einstein–Simha).",
         [V("eref", "Reference intrinsic viscosity", "mL/g", latex=r"[\eta]_{ref}"), V("Mref", "Reference molar mass", "kg/mol", latex=r"M_{ref}"), V("ax", "Mark–Houwink exponent", "1", latex=r"a"), V("Mt", "Molar mass of interest", "kg/mol", latex=r"M"), V("em", "Measured intrinsic viscosity", "mL/g", latex=r"[\eta]_{meas}"),
          avogadro(), V("et", "Intrinsic viscosity at M", "mL/g", latex=r"[\eta]"), V("Mv", "Viscosity-average molar mass", "kg/mol", latex=r"M_v"), V("Rh", "Hydrodynamic radius at M", "nm", latex=r"R_h")],
         [("Intrinsic viscosity", "et = eref*(Mt/Mref)^ax"), ("Viscosity-average mass", "Mv = Mref*(em/eref)^(1/ax)"), ("Hydrodynamic radius", "Rh = (3*et*Mt/(10*pi*NA))^(1/3)")], ["et", "Mv", "Rh"], {"eref": "46.4 mL/g", "Mref": "100 kg/mol", "ax": "0.725", "Mt": "250 kg/mol", "em": "75 mL/g"},
         RUBIN + ", Ch. 8", "Dilute solution in a fixed solvent and temperature (polystyrene in THF shown: K = 0.011 mL/g, a = 0.725)", extra=("materials",), tags=["mark houwink", "intrinsic viscosity", "ubbelohde", "molar mass", "hydrodynamic radius"]),
    chem("chemistry.polymer.glass_transition_fox_flory", "Glass transition: Fox equation and Flory–Fox molar-mass dependence", [POLY],
         "Glass-transition temperature of a miscible blend or random copolymer (Fox) and its dependence on number-average molar mass (Flory–Fox).",
         [V("w1", "Weight fraction of component 1", "1", latex=r"w_1"), V("Tg1", "Tg of component 1", "K", latex=r"T_{g1}"), V("Tg2", "Tg of component 2", "K", latex=r"T_{g2}"), V("Tinf", "Tg at infinite molar mass", "K", latex=r"T_{g,\infty}"), V("Kf", "Flory–Fox constant", "K*kg/mol", latex=r"K"), V("Mn", "Number-average molar mass", "kg/mol", latex=r"M_n"),
          V("Tfox", "Tg of the blend (Fox)", "K", latex=r"T_g"), V("TFF", "Tg at molar mass Mn", "K", latex=r"T_g(M_n)")],
         [("Fox equation", "Tfox = 1/(w1/Tg1 + (1 - w1)/Tg2)"), ("Flory–Fox", "TFF = Tinf - Kf/Mn")], ["Tfox", "TFF"], {"w1": "0.3", "Tg1": "373 K", "Tg2": "378 K", "Tinf": "373 K", "Kf": "120 K*kg/mol", "Mn": "10 kg/mol"}, RUBIN + ", Ch. 6; Fox, Bull. Am. Phys. Soc. 1, 123 (1956)",
         "Ideal mixing of free volume (polystyrene K = 1.2·10⁵ K·g/mol shown)", extra=("materials",), tags=["glass transition", "fox equation", "flory fox", "copolymer", "plasticiser"]),
    chem("chemistry.polymer.rubber_elasticity", "Ideal rubber elasticity: crosslink density, shear modulus and stress–stretch", [POLY],
         "Crosslink density, shear and Young's modulus of a rubber network from the molar mass between crosslinks, and the nominal and true stress at a stretch ratio λ (neo-Hookean).",
         [V("rho", "Density", "kg/m^3", latex=r"\rho"), V("Mc", "Molar mass between crosslinks", "kg/mol", latex=r"M_c"), V("T", "Temperature", "K"), V("lm", "Stretch ratio λ = L/L₀", "1", latex=r"\lambda", min=0), R_univ(), V("nuc", "Crosslink (strand) density", "mol/m^3", latex=r"\nu"), V("G", "Shear modulus", "MPa"),
          V("Ey", "Young's modulus (3G)", "MPa", latex=r"E"), V("sn", "Nominal stress", "MPa", latex=r"\sigma_{nom}", signed=True), V("st", "True stress", "MPa", latex=r"\sigma_{true}", signed=True)],
         [("Strand density", "nuc = rho/Mc"), ("Shear modulus", "G = nuc*R*T"), ("Young's modulus", "Ey = 3*G"), ("Nominal stress", "sn = G*(lm - lm^-2)"), ("True stress", "st = G*(lm^2 - 1/lm)")], ["nuc", "G", "Ey", "sn", "st"], {"rho": "920 kg/m^3", "Mc": "5 kg/mol", "T": "298.15 K", "lm": "2"},
         RUBIN + ", Ch. 7", "Affine network of Gaussian chains, incompressible; valid to λ ≈ 2–3", extra=("materials", "mechanical"), tags=["rubber", "elastomer", "crosslink density", "neo hookean", "entropic elasticity"]),
    chem("chemistry.polymer.membrane_osmometry", "Membrane osmometry: number-average molar mass from osmotic pressure", [POLY, PHYS],
         "Number-average molar mass of a polymer from the osmotic pressure of a solution of known concentration, including the second virial coefficient, and the reduced osmotic pressure.",
         [V("Pi", "Osmotic pressure", "Pa", latex=r"\Pi"), V("cg", "Polymer concentration", "g/L", latex=r"c"), V("T", "Temperature", "K"), V("A2", "Second virial coefficient", "mol*mL/g^2", latex=r"A_2"), R_univ(), V("rp", "Reduced osmotic pressure Π/c", "J/kg", latex=r"\Pi/c"), V("Mn", "Number-average molar mass", "kg/mol", latex=r"M_n")],
         [("Reduced osmotic pressure", "rp = Pi/cg"), ("Number-average molar mass", "Mn = R*T/(rp - R*T*A2*cg)")], ["rp", "Mn"], {"Pi": "262 Pa", "cg": "10 g/L", "T": "298.15 K", "A2": "4e-4 mol*mL/g^2"}, RUBIN + ", Ch. 5", "Dilute solution; the series is truncated after A₂", extra=("materials",), tags=["osmometry", "osmotic pressure", "number average", "virial coefficient", "van t hoff"]),
]
