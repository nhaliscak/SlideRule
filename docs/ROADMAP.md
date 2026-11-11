# Roadmap: things noted for later

Not started. Each item says why it is waiting. Newest decisions are in [PROJECT_LOG.md](../PROJECT_LOG.md).

| Item | Why it waits |
|---|---|
| A screen-reader session over the main views (calculation list, solving, System canvas, LiveCalc) | Needs a person using a screen reader; the automated audit (names, ids, landmarks, headings, contrast) is clean |
| Confirm the IPCC AR6 supplementary table number for methane GWP-100 without oxidation (27.9) in `green.lca.gwp_co2_equivalent` | The report itself has not been opened; secondary sources say Table 7.SM.7 and 7.SM.6 |
| General Poisson brackets, canonical transformations, general Noether symmetries, long map iterations (Poincaré sections) | Better as LiveCalc functions than as library entries (see [CLASSICAL_MECHANICS_AUDIT.md](CLASSICAL_MECHANICS_AUDIT.md)) |
| Continuous mass and elasticity (waves on strings and rods derived from the continuum, elasticity tensors) | Same audit; needs PDE-level support |
| Read the paywalled standards themselves (ASTM C1074, G102, EN 1998-1, ITU-T G.114, ETSI TS 102 687) | Behind paywalls; checked so far against secondary sources only |
| Gaps found by the all-discipline equation audit | See [EQUATION_AUDIT.md](EQUATION_AUDIT.md) |
| Citation and constant check of the 385 audit-fill calculations (modules `audit_*`) | Partly done: about 225 formulas and constants checked on the web in 16 passes ([VERIFICATION.md](VERIFICATION.md)); the rest are on the textbook-check list below. The tests share an author with the formulas |
| Skipped audit topics (list below) | Each needs either a solver the engine lacks or a source to read first |
| Remaining partly-covered chemistry variants and unmatched audit verdicts | The audit tables still show the pre-fill state; re-run the matcher with the new names |
| Property databases (fluids, gases, steam, refrigerants, materials, soils, standard sections) behind the calculations | Started: datapack format, loader, validation, API/CLI, temperature curves, a three-material pack and a water and air pack ([strategy §10 and §11](DATA_AND_STANDARDS_STRATEGY.md)). The picker in single calculations is built (§12). Still to do: the same in System blocks, filling several inputs from one record, LiveCalc functions, pressure dependence, more fluids and materials. Needs a licensed or open data source (CoolProp, IAPWS, NIST, material handbooks), a decision on bundling versus lookup, and validity ranges per property |
| Code-compliance support (design checks against standards such as Eurocode, ACI 318, AISC 360, NEC/IEC, ASME) with clause references | Standards are copyrighted and paywalled: needs licences or clean-room formulas, a clause-level test set, and clear "not a substitute for the engineer of record" wording |

## Citation check of the audit fill (partly done)

Web checks are recorded in [VERIFICATION.md](VERIFICATION.md): 16 passes, about 225 formulas and constants, two formula errors fixed. What the web could not settle is listed under "Textbook-check list" below; step 2 below is superseded by that list for the items it names.

1. Per module (`src/sliderule/library/audit_*.py`), read the `ref` of each calculation and compare formula, constants and stated validity range with the cited source (book chapter or paper). Record the result in the calculation's `assume` text if a limit was missing, and fix the formula and the test together if wrong.
2. Highest priority, because they are empirical fits whose constants are easy to misremember: Pries viscosity (`audit_bio_b`), Standing, Papay, Weymouth/Panhandle (`audit_petro`), Plitt cyclone, Kuz–Ram, Barton Q and point-load factors (`audit_agri_mine`), Carter–Hayes bone, Hodgkin–Huxley rates, Kinney–Graham, Way–Wigner, Metzner–Reed, Larson–Miller, Heskestad, Sutton–Graves constant, Kapustinskii constants, GNFS exponent, Murray walking force.
3. Second, textbook formulas with many constants: Kaiser window, microstrip, Coulomb pressures, Boussinesq/Newmark, Hunt dispersion, CKD-EPI 2021, Mifflin/Harris–Benedict, Daugirdas Kt/V, Gorlin.
4. Cross-check with a second independent implementation where a library exists (for example `thermo`, `CoolProp`, `pvlib`, `scipy.signal`, `astropy`, `sympy.physics`), and add such a comparison to the test when it agrees.
5. Keep a table in `docs/EQUATION_AUDIT.md` (Fill status) marking each module "checked against source" with the date.

## Textbook-check list (formulas the web checks could not settle)

These were searched and either no page printed the formula or the page was garbled, so each needs the printed source. Check the formula, constants and units in the cited book or paper, then move the row into `docs/VERIFICATION.md` and fix the calculation and its test together if it differs. None is known to be wrong; two earlier real errors (Way–Wigner, microstrip) were found only because a source printed the constant.

| Calculation (module) | What to confirm | Where to look |
|---|---|---|
| Pries in-vitro viscosity term 220 e^(−1.3D) (`audit_bio_b`) | the constants of the in-vitro relative-viscosity fit | Pries, Neuhaus and Gaehtgens (1992), Am. J. Physiol. 263 |
| NRC trickling-filter recirculation factor F = (1 + R)/(1 + R/10)² (`audit_civil_c`) | the form of F | Metcalf and Eddy, trickling filters |
| Hunt dispersion, EurOtop run-up (`audit_civil_c`) | Hunt approximation coefficients; R₂% = H min(1.65 ξ, 4 − 1.5/√ξ) | Fenton and McKee; EurOtop manual |
| AISC L_r, ACI ℓ_d exact expressions (`audit_civil_a`) | the full code equations behind the limits already confirmed | AISC 360 Ch. F; ACI 318 Sec. 25.4 |
| Murray walking force (`audit_arch`) | forcing amplitude and the floor-vibration criterion | AISC Design Guide 11 |
| Archard flash temperature, Goodman/L10 constants (`audit_mat_b`, `audit_mech_a`) | flash-temperature constant; Goodman and bearing life-adjustment factors | Rabinowicz; Shigley Ch. 6 and 11 |
| Papay Z-factor, Havlena–Odeh E_g and E_fw (`audit_petro`) | coefficients and the expansion terms | Ahmed, Reservoir Engineering Handbook |
| Standing R_s exponent 1.2048 (`audit_petro`) | exponent and units (constants 1.4, 18.2, 0.0125, 0.00091 are confirmed) | Standing (1947); Ahmed |
| Plitt cyclone constant 50.5 (`audit_agri_mine`) | constant and units (exponents are confirmed) | Wills, Mineral Processing Technology Ch. 9; Plitt (1976) |
| Priest–Hudson RQD from joint frequency (`audit_agri_mine`) | RQD = 100 e^(−0.1λ)(0.1λ + 1) | Priest and Hudson (1976) |
| Christiansen reduction factor (`audit_agri_mine`) | the lateral reduction factor and its table | Christiansen (1942); Keller and Bliesner |
| Eduljee versus Gilliland distinction (`audit_chem_a`) | which fit the code names | Seader and Henley |
| Transmissibility, V-belt, press fit, sheet-metal springback and bend radius (`audit_mech_a`, `audit_mech_b`) | the standard forms (searches returned nothing) | Rao; Shigley Ch. 7 and 17; Kalpakjian |
| Open-die forging, round form (`audit_mech_b`) | p = σ_f(1 + 2μr/3h) against Groover's 1 + 0.4μD/h | Kalpakjian; Groover Ch. 19 |
| Turbulent flat-plate constants 0.37, 0.0592, 0.074 (`audit_mech_b`) | the one-seventh-power constants | White, Fluid Mechanics Ch. 7 |
| Adams weld peak temperature, constant 4.13 (`audit_mech_b`) | constant and the definition of Y | Adams (1958), Welding Journal 37 |
| Friis cascade, dish gain, classical eddy loss (`audit_elec_a`, `audit_elec_b`) | standard forms, not printed in any page read | Pozar; Balanis; Bertotti |
| Allen–Eggers closed form (`audit_aero_b`) | a_max = V² sin γ/(2eH) at ρ = β sin γ/H (re-derived, not printed) | NACA Report 1381 |
| Xenon-135 equilibrium formula (`audit_nuclear`) | equilibrium concentration against flux | Lamarsh and Baratta Ch. 7 |
| Composite transmission loss, lift probable stops (`audit_arch`) | TL_c = −10 log(Στ_iS_i/ΣS_i); S = N[1 − (1 − 1/N)^P] | Long, Architectural Acoustics; Barney, Elevator Traffic Handbook |
| Erlang B-to-C identity (`audit_ie_cs`) | C = B/(1 − ρ(1 − B)) | Kleinrock; Hillier and Lieberman |

Not yet looked at by any pass: the pre-audit part of the library (about 990 calculations written before the audit fill) and the not-yet-covered modules; the web checks above cover only the fill.

## Audit topics deliberately not filled (to add later)

- Chemical: pinch analysis (heat-exchanger network targeting), fouling dynamics, further partly-covered variants (Woodward–Fieser, Pitzer, DLVO, impedance spectroscopy, Latimer/Frost/Pourbaix diagrams, RRKM, Lineweaver–Burk/Eadie–Hofstee).
- Biomedical: gait inverse dynamics, fracture healing, heart-rate variability, livestock energetics, SIR final-size equation (needs a Lambert-W or implicit solve).
- Industrial/systems: linear programming and the transportation problem, facility layout, ABC analysis, age-replacement policy with an integral.
- Petroleum/mining: Beggs–Brill and Hagedorn–Brown multiphase flow, gas lift design, mine slope circular failure (Bishop) and wedge failure.
- Architectural: full Fanger PMV (iterative clothing temperature), drainage fixture units and pipe sizing by table, highest reversal floor in lift traffic.
- Emerging: smart-city demand response and microgrid dispatch, SLAM covariance, VQE energy, quantum volume, CAP trade-offs beyond the quorum rule, Mie plasmon resonance, toggle switch and repressilator, carbon-cycle box model, Izhikevich neuron.
- Engine support that would unlock several of these: list/table inputs for sums and graphs, and implicit solves with a stated starting range.
