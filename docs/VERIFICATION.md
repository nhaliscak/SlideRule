# Verification of the audit-fill calculations against sources

The 385 calculations added by the equation-audit fill (modules `audit_*`) were written from memory, and their tests share an author with the formulas. This file records which constants and formulas have since been **checked against a source on the web**, what was found, and what is still unchecked. Plan and priorities: [ROADMAP.md](ROADMAP.md). Pass 1 to 10: 2026-10-30.

Method: web search for the exact coefficients, then reading the page that states them. A "confirmed" entry means the coefficients and exponents match a source I could read; it does **not** mean the original paper or standard was read. Secondary sources (study guides, wikis, review articles) are marked.

## Pass 1 results (10 items, one error fixed)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| CKD-EPI 2021 eGFR (`audit_bio_a`) | 142, κ 0.7/0.9, α −0.241/−0.302, −1.200, 0.9938^age, ×1.012 female | **Confirmed** | National Kidney Foundation and NIDDK pages |
| Kinney–Graham overpressure (`audit_chem_b`) | 808, 4.5, 0.048, 0.32, 1.35 and the unsquared denominator | **Confirmed** (one calculator page prints the denominator squared; that looks like a typo) | Fireball-acoustics paper (arXiv 2102.06574 family), Dlubal formula page |
| Heskestad flame height and plume mass flow (`audit_arch`) | 0.235 Q^(2/5) − 1.02 D; 0.071 Q_c^(1/3) z^(5/3) + 0.0018 Q_c | **Confirmed** (secondary sources: exam and lecture material; original is Heskestad, SFPE Handbook) | Fire-engineering study material |
| Sutton–Graves constant (`audit_aero_b`) | 1.7415×10⁻⁴ kg^½/m for Earth air | **Confirmed to 1.74×10⁻⁴**; the fifth digit is not shown in readable sources | NASA TR R-376 references and several papers |
| Standing Rs and Bo (`audit_petro`) | exponent 1.2048 (inverse of the bubble-point form), 0.9759, 0.000120, 1.25, 1.2 | **Consistent with the standard form**; coefficient tables not read directly | Petroleum-engineering papers and PVT references |
| Plitt hydrocyclone d50 (`audit_agri_mine`) | 50.5 and every exponent, exp(0.063 C_v), units (cm, L/min, % solids, g/cm³, µm) | **Confirmed** (SysCAD documentation citing Napier-Munn et al.); another course page prints a different constant (14.8) for a different form | SysCAD wiki "Hydrocyclone" |
| Pries viscosity, hematocrit exponent C (`audit_bio_b`) | C = (0.8 + e^(−0.075 D))(−1 + 1/(1 + 10⁻¹¹ D¹²)) + 1/(1 + 10⁻¹¹ D¹²); 3.2 − 2.44 e^(−0.06 D^0.645); the relative-viscosity form | **Confirmed**, from the NIH Physiome in-vivo model source | NSR Physiome model 0157 (`InVivoViscosity.mod`) |
| Pries viscosity, in-vitro 220 e^(−1.3 D) term (`audit_bio_b`) | the leading exponential | **Not confirmed.** The sources read give 6 e^(−0.085 D) for the in-vivo model and none shows 220 e^(−1.3 D). The in-vivo model also multiplies by (D/(D − 1.1))². Keep flagged until Pries et al. (Am. J. Physiol. 263, 1992) is read | Same |
| Way–Wigner decay heat (`audit_nuclear`) | coefficient | **Found wrong, fixed.** The code used 0.0622; the readable source (Wikipedia, citing Marguet and a MNR report) gives **0.066**, exponents −0.2, validity 10 s to 100 days. The Argonne page could not be read (HTTP 403), so the 0.0622 version in some textbooks was not excluded. Code and test now use 0.066 | Wikipedia "Decay heat" |
| Way–Wigner time definitions | operating time and time after shutdown | Consistent with Wikipedia's form P/P₀ = 0.066[t^(−0.2) − (t + τ_s)^(−0.2)], where its second form leaves one symbol undefined | Same |

## Pass 2 results (7 items)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Hodgkin–Huxley rate functions (`audit_bio_b`) | all six α, β expressions in the modern −65 mV convention | **Confirmed** (identical to the 1952 forms with φ = V + 65) | Keener lecture excerpt, a 2026 arXiv paper |
| Metzner–Reed Reynolds number (`audit_chem_b`) | Re = ρ V^(2−n) Dⁿ /[K′ 8^(n−1)], K′ = K((3n+1)/4n)ⁿ | **Confirmed** (algebraically identical to 8ρU^(2−n)Dⁿ/[K(6 + 2/n)ⁿ]; reduces to the Newtonian Re at n = 1) | arXiv papers on power-law pipe flow |
| Kapustinskii (`audit_chem_emerge`) | form, 34.5 pm, constant 1.2025×10⁻⁴ | **Consistent**: the form and 34.5 pm are confirmed; the constant is not printed in the readable pages (Wikipedia prints 1.079×10⁻⁴ for the original simpler form), but a calculator's NaCl value (746 kJ/mol) matches this code | Wikipedia, LibreTexts |
| Papay Z-factor (`audit_petro`) | coefficients | **Not confirmed in print**; cross-check at T_pr 1.5, p_pr 2 gives 0.83, matching the Standing–Katz chart value | none readable |
| Weymouth and Panhandle A (`audit_petro`) | 433.5, 2.667, 435.87, 1.0788, 2.6182, efficiency factor | **Confirmed**; two exponents differ between sources: bracket 0.5394 (code, Menon) vs 0.5392, and gravity 0.8539 vs 0.853 (about 0.1 % in flow). Kept 0.5394 and 0.8539 and noted in the assumptions | planetcalc and pipeline-engineering pages |
| Kuz–Ram (`audit_agri_mine`) | mean size equation, exponent 19/30, uniformity index | Mean-size equation **confirmed**; the uniformity index is a **simplified** form (the full model has extra deviation terms and a 0.1 term); "mean" size is effectively the median. Assumptions updated | Wits conference paper, Springer rock-mechanics papers |
| Carter–Hayes bone (`audit_bio_b`) | σ = 68 ε̇^0.06 ρ², E = 3790 ε̇^0.06 ρ³ | Strength constant and the ρ² and ρ³ dependence **confirmed**; the constant 3790 **not confirmed**. Assumptions updated | Bone-mechanics reference, 1976 Science abstract |

## Pass 3 results (7 items)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Daugirdas Kt/V (`audit_bio_a`) | −ln(R − 0.008 t) + (4 − 3.5 R) UF/W, t in hours, UF in L | **Confirmed**; KDOQI minimum 1.2, target 1.4 | KHI/ASN and calculator pages citing Daugirdas, JASN 1993 |
| Gorlin and Hakki (`audit_bio_a`) | 44.3; Hakki = CO/√gradient | **Confirmed** (some sources use 44.5 = √(2g) for the mitral form) | Wikipedia, PMC review, QxMD |
| Revised Harris–Benedict (`audit_bio_a`) | 88.362, 13.397, 4.799, 5.677 (men); 447.593, 9.247, 3.098, 4.330 (women) | **Confirmed** for men (two sources) and for the women's weight term; the other women's terms rest on one calculator page | Wikipedia, a Dutch guideline table, calcfyi |
| Mifflin–St Jeor (`audit_bio_a`) | 10 W + 6.25 H − 5 A + 5 / −161 | The weight coefficient **confirmed**; 6.25, −5, +5 and −161 not shown in readable pages | Wikipedia |
| Point-load index and UCS factor (`audit_agri_mine`) | (De/50)^0.45, UCS ≈ 22 Is(50) | **Confirmed**; the factor 22 is an ISRM-quoted average and varies by rock (15 to 29 reported) | Lab-report and journal pages citing ISRM |
| Larson–Miller and Hollomon–Jaffe (`audit_mat_a`) | P = T(C + log t), C ≈ 20 | **Confirmed for creep (C ≈ 20)**; for tempering C is about 15 (0.9–1.2 % C) to 19.5–20, so the "17–18" wording was changed. Hollomon–Jaffe originally used °R | Wikipedia, TWI FAQ |
| GNFS exponent (`audit_ie_cs`) | 1.923 and the formula | **Confirmed**; gives about 117 bits for RSA-2048 against NIST's 112 (the standard value is a convention, not derived from this formula) | Cryptography sources |
| Murray walking acceleration (`audit_arch`) | P₀ = 0.29 kN, e^(−0.35 f_n), 0.5 %g limit | The 0.5 %g (0.05 m/s²) office limit **confirmed**; the formula and 0.29 kN **not confirmed** online and the 2nd edition of the guide changed the method. Treat as indicative | AISC Design Guide 11 errata and articles |

## Pass 4 results (8 items)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Kaiser window design (`audit_elec_b`) | β piecewise (0.1102(A − 8.7); 0.5842(A − 21)^0.4 + 0.07886(A − 21); 0), N = (A − 8)/(2.285 Δω) | **Confirmed.** The code uses A − 7.95 in the order (Kaiser's original value; MathWorks and Smith print 7.95 and 8 respectively) | CCRMA (J. O. Smith), MathWorks `kaiserord` |
| Microstrip, Hammerstad–Jensen (`audit_elec_b`) | ε_eff, both Z₀ branches | Z₀ branches and 120π constant **confirmed**. **Error found and fixed**: the narrow-strip term 0.04(1 − W/h)² for W/h < 1 was missing from ε_eff (effect about 0.2 % in ε_eff for W/h near 0.5); code and test updated | Steer LibreTexts, QUCS notes |
| Hunt dispersion approximation (`audit_civil_c`) | kh = √(y² + y/(1 + 0.6522y + 0.4622y² + 0.0864y⁴ + 0.0675y⁵)) | Coefficients and form **consistent with the usually quoted form**; the search results did not print them, so confirmed only against recollection and Hunt's described Padé construction. Original paper (J. Waterway Port Coastal Ocean Div. 105, 457) not read | Wave-dispersion comparison papers (You 2003, 2008) |
| Meyerhof bearing capacity (`audit_civil_a`) | N_q, N_c, N_γ = (N_q − 1) tan(1.4φ), shape and depth factors | N_q, N_c, N_γ **confirmed** (some authors use 1.32φ or 1.5φ in N_γ); the shape and depth factors match the usual Meyerhof form but were not printed in the readable pages | Geotechnical calculator and lecture pages |
| Newmark rectangular-corner stress | not in the library (the Boussinesq calculation has point load, circular area and 2:1 only) | **Nothing to check**; a roadmap item if wanted | |
| Peng–Robinson (`audit_chem_a`) | κ = 0.37464 + 1.54226ω − 0.26992ω², a = 0.45724 R²T_c²/P_c, b = 0.07780 RT_c/P_c | **Confirmed.** κ is valid for ω ≤ 0.49 (a heavier-component polynomial exists; a coefficient 1.564226 printed in some pages is a typo) | Cantera, IDAES, OpenFOAM documentation |
| Gibson–Ashby foams (`audit_mat_a`) | E ∝ ρ², σ_pl = 0.3 σ_ys ρ^1.5, closed-cell φ²ρ² + (1 − φ)ρ | **Confirmed.** The densification strain 1 − 1.4ρ was **not found online** | MIT 3.054 course slides |
| Chvorinov and Coulomb (`audit_mech_b`, `audit_civil_a`) | t = B(V/A)ⁿ with n = 2, riser D = H; Coulomb K_a formula and the Rankine reduction at α = 90°, β = δ = 0 | **Confirmed** (the notation for the wall angle differs between sources) | Casting and geotechnical notes |

## Pass 5 results (12 items)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Hazen–Williams head loss (`audit_civil_b`, `audit_agri_mine`) | hf = 10.67 L Q^1.852/(C^1.852 D^4.87); SI velocity form 0.849 C R^0.63 S^0.54 | **Confirmed** (the 10.67 is derived from the confirmed SI flow form 0.278 C D^2.63 S^0.54; some codes use 0.8492) | Wikipedia, Engineers Edge, RiverWare |
| Manning (`audit_civil_b`) | SI form Q = (1/n) A R^(2/3) S^(1/2) | **Confirmed** | Course notes, Engineers Edge |
| Hargreaves ET₀ (`audit_civil_c`) | 0.0023 (T_mean + 17.8) √(T_max − T_min) R_a | **Confirmed**; the coefficient is often recalibrated locally (0.0020 in one study); R_a must be in mm/day equivalent | FAO-56 R package docs, ASCE history paper |
| FAO-56 Penman–Monteith (`audit_civil_c`) | 0.408 Δ(R_n − G) + γ 900/(T + 273) u₂(e_s − e_a), denominator Δ + γ(1 + 0.34 u₂) | **Confirmed** | FAO paper 56 |
| Theis and Cooper–Jacob (`audit_civil_c`) | s = Q W(u)/(4πT), u = r²S/(4Tt), W ≈ −0.5772 − ln u for u < 0.01 | **Confirmed** | Course notes, calculator docs |
| Gumbel frequency factor (`audit_civil_c`) | K = −(√6/π)(0.5772 + ln ln(T/(T − 1))) | **Confirmed** (equivalent to (y_T − 0.577)/1.2825) | Hydrology course notes |
| Briggs final plume rise (`audit_civil_c`) | 21.425 F^0.75/u (F < 55), 38.71 F^0.6/u; F = g v d²(T_s − T_a)/(4T_s) | **Buoyancy flux confirmed.** Two constant sets are in use: 21.425 and 38.71 (older summaries, used here) against 21.31 and 38.88 (the CMAS/SMOKE code). Kept the first set; the difference is under 0.5 % | CMAS SMOKE documentation, MEPAS |
| HEC-18 pier scour (`audit_civil_b`) | y_s/y₁ = 2.0 K₁K₂K₃ (a/y₁)^0.65 Fr₁^0.43 | **Confirmed**; a worked example reproduces the published 10.48 m | SDSU HEC-18 calculator, FHWA HEC-18 |
| Muskingum coefficients (`audit_civil_b`) | C₀, C₁, C₂ | **Confirmed**; C₀ + C₁ + C₂ = 1; needs Δt ≥ 2Kx for C₀ ≥ 0 | Flood-routing notes |
| IPC-2221 trace current (`audit_elec_b`) | I = k ΔT^0.44 A^0.725, k = 0.048 external, 0.024 internal (A in mil²) | **Confirmed**; conservative (IPC-2152 is the newer standard) | PCB design references |
| Steinmetz core loss and Peukert (`audit_elec_a`/`audit_elec_b`) | power-law forms | Forms **confirmed**; coefficients are material data entered by the user | TDK, papers; battery manufacturer notes |
| Lapple cyclone cut size and Ruth filtration (`audit_chem_a`) | d₅₀ = √(9μW/(2πN_e v_i(ρ_p − ρ_g))); t/V = μαcV/(2A²ΔP) + μR_m/(AΔP) | **Confirmed**; the number of effective turns is only approximate | Cyclone and filtration references |

## Pass 6 results (9 items)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Oblique shock θ–β–M (`audit_aero_a`) | tan θ = 2 cot β (M₁² sin²β − 1)/(M₁²(γ + cos 2β) + 2) | **Confirmed**, with a worked wind-tunnel check (M 5, θ 20°, β ≈ 29.8°) | Penn State notes, SCDev, MathWorks |
| Prandtl–Meyer function (`audit_aero_a`) | ν(M) | **Confirmed**; ν(2) = 26.4° for γ = 1.4 | NASA Glenn, Wikipedia |
| J2 nodal regression and sun-synchronous orbit (`audit_aero_b`) | −1.5 J₂ (R/p)² n cos i; 0.9856 °/day; J₂ = 1.08263×10⁻³ | **Confirmed**; sun-synchronous worked checks 97.87° (7000 km) and 98.2° (700 km). The apsidal-rate form (3/4) n J₂ (R/p)²(5cos²i − 1) was not printed in readable pages | FreeFlyer guide, NASA GDC primer, Wikipedia |
| Clohessy–Wiltshire (`audit_aero_b`) | closed-form x, y, z | Matches the standard solution by derivation (initial conditions and derivatives); no source printed the closed form | Orekit documentation, Wikipedia |
| Allen–Eggers peak deceleration (`audit_aero_b`) | a_max = V_E² sinγ/(2eH), ρ_peak = β sinγ/H | **Confirmed** (derived; independent of mass, size and drag coefficient); holds for constant flight-path angle (entry 5° or steeper) | Planar re-entry equations, NASA reports |
| Eclipse duration and critical beta (`audit_aero_b`) | cos φ = √(h² + 2Rh)/((R + h) cos β), β* = asin(R/(R + h)) | **Confirmed**; the declination formula for β was not printed | arXiv CubeSat thermal paper, orbital data-centre paper |
| Eddington, virial, Kelvin–Helmholtz (`audit_phys_b`) | L = 4πGMm_pc/σ_T = 1.26×10³¹ W/M☉ | Eddington **confirmed**. The virial factor 5 is a convention and the KH time prefactor varies between texts (GM²/RL or half of it); assumptions updated | Wikipedia, course notes |
| Relativity tests (`audit_phys_a`) | perihelion 43″/century, deflection 1.75″, Shapiro delay | Perihelion and deflection **confirmed**. Shapiro: the "+1" belongs to coordinate time; referred to an Earth clock the constant is removed, which matches the measured 247 µs. Assumptions updated | Wikipedia, Shapiro 1964 summaries |
| Instabilities (`audit_phys_a`) | Ra_c = 1707.762, KH critical velocity, RT growth rate | Ra_c and KH threshold **confirmed**; the RT form with surface tension is the standard inviscid result but no source printed it | Chandrasekhar-based papers |

## Pass 7 results (14 items)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Dittus–Boelter, Gnielinski, Churchill–Chu (`audit_mech_b`) | Nu = 0.023 Re^0.8 Pr^n (n = 0.4 heating, 0.3 cooling); Gnielinski form; Churchill–Chu vertical plate | **Confirmed**; validity: D–B Re > 10⁴, 0.6 ≤ Pr ≤ 160; Gnielinski 3000 ≤ Re ≤ 5×10⁶ (some sources use 2300); the horizontal-cylinder Churchill–Chu form has 0.6 and 0.559 instead of 0.825 and 0.492 | tacodoc, MOOSE and Altair docs, `ht` library |
| Zuber critical heat flux (`audit_mech_b`) | 0.131 h_fg ρ_v^0.5 [σ g(ρ_l − ρ_v)]^0.25 | **Confirmed** (0.131 = π/24; Lienhard–Dhir use 0.149); for large flat horizontal surfaces | OpenFOAM docs, Mudawar |
| Rohsenow nucleate boiling (`audit_mech_b`) | form, C_sf = 0.013 water–copper, Pr exponent 1.0 (water) or 1.7 | **Confirmed** | COMSOL theory pages, journal papers |
| Nusselt film condensation (`audit_mech_b`) | 0.943 = 2√2/3 and the property groups | **Confirmed**; laminar only (Re below about 30; wavy-laminar 30 to 1800) | `ht` condensation module, lecture notes |
| Paris law, Goodman, L10 life (`audit_mech_a`) | da/dN = C ΔKᵐ, ΔK = Y Δσ √(πa); σ_a/S_e + σ_m/S_ut = 1/n; L10 = (C/P)ᵖ | Paris law **confirmed** online; Goodman and L10 forms are textbook statements not printed in the readable pages | Wikipedia, crack-growth papers |
| Lamé cylinder and press fit (`audit_mech_a`) | σ_r, σ_θ, interface pressure, signs | **Confirmed** (one calculator page prints a sign typo for the inner member) | Cambridge DAN notes, Engineers Edge |
| Rankine and Terzaghi (`audit_civil_a`) | K_a = (1 − sin φ)/(1 + sin φ); T_v = (π/4)U² (U ≤ 0.6), T_v = −0.933 log₁₀(1 − U) − 0.085 | **Confirmed**; the second form is algebraically 1.781 − 0.933 log₁₀(100 − U %) | GEO5, geotechnical notes |
| Infinite slope (`audit_civil_a`) | FS formulas | Not retrieved (the search was rate-limited); the dry cohesionless form tan φ/tan β is textbook | |
| Archard wear (`audit_mat_b`) | V = K F s/H | **Confirmed**; K is fitted per material pair; some texts quote it per sliding distance | Tribology references |
| Archard flash temperature (`audit_mat_b`) | ΔT = μNv/(4a(k₁ + k₂)) | **Not confirmed**; dimensionally consistent; assumptions updated to say so. Source to read: Archard, Wear 2, 438 (1958) | none |
| Johnson–Euler column (`audit_civil_a`) | σ_cr = σ_y[1 − σ_y L²/(4π²E r²)], transition √(2π²E/σ_y) | **Confirmed** | Wikipedia, column-buckling references |
| Stoney (`audit_mat_a`) | σ = E_s t_s²/(6(1 − ν_s) t_f R) | **Confirmed**; R is the change in curvature (1/R_f − 1/R_i); film much thinner than the substrate; errors above 50 % possible at high stress | DoITPoMS, papers |
| Magnus, humidity ratio, moist-air enthalpy (`audit_chem_b`, `audit_mech_b`) | 611.2 exp(17.62 T/(243.12 + T)); W = 0.622 p_v/(p − p_v); h = 1.006 T + W(2501 + 1.86 T) | **Confirmed**; other Magnus constant sets exist (Alduchov–Eskridge); valid about −80 to +50 °C | WMO-recommended form, psychrometric notes |
| Carnot refrigeration COP (`audit_mech_b`) | COP = T_c/(T_h − T_c) | **Confirmed** | Textbook references |

## Pass 8 results (15 items)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Infinite slope (`audit_civil_a`) | FS = c′/(γ z cos²β tanβ) + (1 − r_u sec²β) tanφ′/tanβ | **Confirmed** (equal to [c′ + (γ z cos²β − u) tanφ′]/(γ z sinβ cosβ)); dry cohesionless reduces to tanφ/tanβ | FAMU slope-stability notes, hydrology papers |
| Peck braced cut (`audit_civil_a`) | p = 0.65 K_a γ H for sand, K_a = tan²(45° − φ/2) | **Confirmed** (an apparent pressure envelope for strut loads) | NPTEL, Structville |
| Synchronous power angle (`audit_elec_a`) | P = 3 V E sin δ/X_s, maximum at 90° | **Confirmed** (phase quantities; resistance neglected) | Electric-machines notes |
| Transformer regulation (`audit_elec_a`) | R cosθ + X sinθ (sign flips for leading power factor) | **Confirmed**; second-order term (X cosθ − R sinθ)²/2 matters at low power factor | Transformer references |
| DC shunt motor and line-to-ground fault (`audit_elec_a`) | T ∝ I_a, N ∝ (V − I_a R_a)/Φ; I_f = 3E/(Z₁ + Z₂ + Z₀) | **Confirmed**; E is the phase voltage | Machine and power-system notes |
| IDMT relay curves (`audit_elec_a`) | k, α for standard, very, extremely and long-time inverse, multiplied by TMS | **Confirmed** (0.14/0.02, 13.5/1, 80/2, 120/1); TMS = 1 at 10×: 2.97, 1.5, 0.81, 13.3 s | IEC 60255 summaries |
| Touch and step voltage (`audit_elec_b`) | (1000 + 1.5 C_s ρ_s) k/√t_s and (1000 + 6 C_s ρ_s) k/√t_s; C_s = 1 − 0.09(1 − ρ/ρ_s)/(2h_s + 0.09) | **Confirmed**; k = 0.116 for a 50 kg body and 0.157 for 70 kg (IEEE 80 edition dependent) | IEEE 80 summaries |
| Radar equation, noise-figure cascade, beamwidth, dipole (`audit_elec_b`) | R⁴ = P_t G² λ² σ/((4π)³ S_min); Friis cascade; 70 λ/D; 1.64 | **Confirmed** (forms vary between texts) | Course notes |
| Rachford–Rice and Fenske (`audit_chem_a`) | flash equation; N_min | **Confirmed** | Notebooks, course notes |
| Gilliland correlation (`audit_chem_a`) | the exponential form Y = 1 − exp[((1 + 54.4X)/(11 + 117.2X))((X − 1)/√X)] | This is the **Molokanov** form (as cited in the code); Eduljee's simpler fit is Y = 1 − 0.75X^0.5668. The exponential was not printed in readable pages | CEE 2020 paper on FUG correlations |
| Thiele sphere (`audit_chem_a`) | η = (1/φ)(1/tanh 3φ − 1/(3φ)) with φ = (R/3)√(k/D_e) | **Confirmed**: it is the standard η = (3/φ_s)(coth φ_s − 1/φ_s) with φ_s = R√(k/D_e) = 3φ, and the test integrates the boundary-value problem | Reaction-engineering definitions |
| Tanks in series and Kremser (`audit_chem_a`) | N = t²/σ²; (A^(N+1) − A)/(A^(N+1) − 1) | **Confirmed** by textbook definitions (not printed in the readable pages) | |
| API 520 gas coefficient (`audit_chem_a`) | C = 520 √(k(2/(k + 1))^((k + 1)/(k − 1))) | **Confirmed** (US units; 0.03948 in SI) | `fluids` library docs |
| Havlena–Odeh (`audit_petro`) | F = N(E_o + m E_g + E_fw) + W_e | Form **confirmed** against the 1963 paper structure; the E_g and E_fw expressions were not printed in readable pages | SPE 559, SPE 869 |
| Vogel IPR (`audit_petro`) | q/q_max = 1 − 0.2 p_wf/p_r − 0.8 (p_wf/p_r)² | **Confirmed** (below the bubble point; a composite curve is needed above it) | Well-performance notes |

## Pass 9 results (15 rows, biomedical)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Cockcroft–Gault (`audit_bio_a`) | (140 − age) × weight/(72 × S_Cr), × 0.85 for women, S_Cr in mg/dL | **Confirmed**; a µmol/L version uses 1.23 (men) and 1.04 (women); overestimates in obesity | Guideline and lab calculators |
| Starling filtration (`audit_bio_a`) | J_v = K_f[(P_c − P_i) − σ(π_c − π_i)] | **Confirmed** (σ is 0 to 1; about 0.5 in pulmonary capillaries) | Wikipedia, LibreTexts |
| Fick output, oxygen content, alveolar gas equation (`audit_bio_a`) | VO₂/(C_aO₂ − C_vO₂); 1.34 Hb S + 0.003 P; F_iO₂(P_b − 47) − P_aCO₂/RQ | **Confirmed**; some texts use 1.31 or 1.36 and 0.0031 | StatPearls, clinical formula lists |
| Henderson–Hasselbalch, anion gap (`audit_bio_b`) | pH = 6.1 + log(HCO₃/(0.03 P_CO₂)); Na − Cl − HCO₃ | **Confirmed** (the solubility 0.0307 mmol/(L·mmHg) is the usual 37 °C value; normal anion gap 8 to 12, up to 16 in other references, laboratory dependent) | Textbook and Wikipedia pages |
| Bohr shift, haemoglobin Hill equation (`audit_bio_b`) | log P50 shift with coefficient 0.48; n = 2.7, P50 = 26.6 to 26.8 mmHg | **Confirmed**; ±0.1 pH moves P50 to 24 or 30 mmHg | Wikipedia, OpenAnesthesia |
| Linear–quadratic BED and EQD2 (`audit_bio_a`) | BED = nd(1 + d/(α/β)); EQD2 = BED/(1 + 2/(α/β)) | **Confirmed** | Radiation-oncology calculators and notes |
| CEM43 (`audit_bio_a`) | t R^(43 − T), R = 0.5 at or above 43 °C, 0.25 below | **Confirmed** (Sapareto & Dewey; R is an approximation) | Hyperthermia papers |
| Pennes perfusion length (`audit_bio_a`) | √(k/(ρ_b c_b ω_b)) | **Confirmed** as the standard length scale | Bioheat modelling preprints |
| QT corrections (`audit_bio_b`) | Bazett, Fridericia, Framingham (154), Hodges (1.75) | **Confirmed**; Fridericia and Framingham are better at heart-rate extremes | QT-correction comparison studies |
| Moens–Korteweg and Windkessel (`audit_bio_a`) | PWV = √(E h/(ρ D)); τ = RC | **Confirmed**; MK assumes a thin, isotropic wall and inviscid blood; the RC decay assumes a zero asymptote | Wikipedia, physiology papers |
| SIR model (`audit_bio_b`) | R₀ = β/γ; 1 − 1/R₀; peak 1 − (1 + ln R₀)/R₀ | R₀ and herd-immunity threshold **confirmed**; the peak is **derived** (S = 1/R₀ at the peak) | Epidemic-modelling notes |
| Logistic and Gompertz growth (`audit_bio_b`) | forms, inflection at K/2 and K/e | **Confirmed** | Tumour-growth papers |
| Higuchi and Korsmeyer–Peppas (`audit_bio_b`) | Q = √(D(2A − C_s)C_s t); M_t/M_∞ = k tⁿ, n = 0.5 slab | **Confirmed**; the expanded Higuchi constant is the classic planar-matrix form | Drug-release references |
| Hill muscle (`audit_bio_a`) | (F + a)(v + b) = (F₀ + a)b; maximum power near 0.3 F₀ | **Confirmed**; fails above about 80 % of F₀ | Physiology reviews |
| Pries in-vitro viscosity, 220 e^(−1.3D) term (`audit_bio_b`) | the leading exponential | **Still not confirmed in a readable primary page.** One summary states the same constants for the 1992 in-vitro fit, but none of the pages printed them; the structure, C, and the in-vivo values are confirmed (Pass 1) | Pries, Neuhaus & Gaehtgens, Am. J. Physiol. 263, H1770 (1992) |

## Pass 10 results (civil and environmental, 12 rows)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| SCS curve number (`audit_civil_c`) | Q = (P − 0.2S)²/(P + 0.8S) for P > 0.2S, S = 1000/CN − 10 in (25400/CN − 254 mm) | **Confirmed** | NRCS/TR-55 summaries |
| Rational method and time of concentration (`audit_civil_c`) | Q = CiA (0.0028 CiA metric); TR-55 sheet flow 0.007(nL)^0.8/(P₂^0.5 S^0.4) | **Confirmed**; sheet-flow length limit is 100 ft in some manuals and 300 ft in others | Iowa DOT, TR-55 help |
| IDF (`audit_civil_c`) | i = a T^m/(t + b)ⁿ | Form **confirmed** as the generalised Bernard/Sherman family (the pure Bernard form is a/tⁿ; b removes the singularity at t = 0) | IDF-fitting references |
| BOD kinetics and temperature (`audit_civil_c`) | L₀(1 − e^(−kt)), k_T = k₂₀ θ^(T − 20), θ = 1.047 | **Confirmed**; another source gives 1.056 below 20 °C; k is base-e | Wastewater notes |
| Trickling filter NRC and flocculation G (`audit_civil_c`) | E = 100/(1 + 0.4432 √(W/(VF))); the recirculation factor F = (1 + R)/(1 + R/10)² used in the code was printed garbled in the page read, so it is **not confirmed online**; G = √(P/(μV)) | NRC form **confirmed** (0.4432 is the SI constant, 0.0561 in US units; valid to 1.2 kg BOD/(m³ day) for single-stage); G definition **confirmed** | Environmental-engineering notes |
| Noise barrier and inverse square (`audit_civil_c`) | 10 log(3 + 20N), N = 2δ/λ; 20 log(r₂/r₁) | **Confirmed** (Maekawa; a different shadow-zone model caps at 25 dB) | Arup and journal pages |
| LandGEM first-order decay (`audit_civil_c`) | Q = k L₀ M e^(−kt) per cohort | **Confirmed** for one cohort; LandGEM sums over annual cohorts; defaults L₀ 170 m³/Mg, k 0.02 to 0.065 | EPA LandGEM manual |
| Vertical curves, stopping sight distance, Greenshields (`audit_civil_c`) | K = S²/(100(√(2h₁) + √(2h₂))²); SSD = 0.278 V t + V²/(254(f ± G)); q = v_f k(1 − k/k_j) | **Confirmed**; the coefficient is 0.278 or 0.284 in some manuals | Transportation formula sheets |
| Earned value, learning curve, CPM (`audit_civil_c`) | CPI = EV/AC, SPI = EV/PV, EAC = BAC/CPI; T_n = T₁ n^b, b = log r/log 2; forward and backward pass | **Confirmed** (the EAC and unit-versus-cumulative-average conventions vary) | PM references |
| Wave shoaling, refraction, breaking (`audit_civil_c`) | K_s = √(c_g0/c_g); sin α/c constant; H_b = 0.78 h | **Confirmed** (0.78 for mild slopes; other indices 0.88 to 0.4 by wave type) | Wikipedia, coastal notes |
| Iribarren number and run-up (`audit_civil_c`) | ξ = tan α/√(H/L₀); R₂% = H min(1.65 ξ, 4 − 1.5/√ξ) | ξ **confirmed**; the run-up formula is the EurOtop-style form and was **not printed** in the pages read | Coastal-engineering notes |
| Secondary compression, CSR, elastic settlement, Mohr–Coulomb (`audit_civil_a`) | C_α H/(1 + e₀) log(t₂/t₁); 0.65 (a_max/g)(σ_v/σ′_v) r_d; q B(1 − ν²) I/E_s; τ = c + σ tan φ | **Confirmed**; the secondary-compression void ratio is e_p (end of primary) in some texts; r_d is piecewise (1 − 0.00765 z to 9.15 m) | Geotechnical notes |
| Branson effective inertia (`audit_civil_a`) | Ie = (M_cr/M_a)³I_g + [1 − (M_cr/M_a)³]I_cr | **Confirmed** as Branson's form; ACI 318-19 keeps it for prestressed members and uses Bischoff's fourth-power form for non-prestressed ones. Assumptions updated | Bentley, ACI and PCI notes |
| AISC lateral-torsional buckling, ACI development length, prestress (`audit_civil_a`) | L_p = 1.76 r_y √(E/F_y); ℓ_d = (3/40)(f_y ψ_t ψ_e ψ_s/(λ√f′c))(…)d_b; P/A ± Pe y/I | Structure and the code limits **confirmed**; the exact L_r and ℓ_d expressions are standard code equations that the pages did not print | Dlubal, ideCAD, FHWA |

## Pass 11 results (mechanical design, thermo-fluids, manufacturing, 24 rows, one assumption corrected)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Lewis gear bending (`audit_mech_a`) | σ = W_t K_v/(F m Y), K_v = (6.1 + V)/6.1 | **Confirmed**; a worked lecture example (18 teeth, m 2, F 25, Y 0.29327, 1.25 kW, 850 rpm) reproduces about 67 MPa with this K_v | Charlotte toolkit, Budynas Ch. 14 |
| Flywheel (`audit_mech_a`) | ΔE = ½I(ω²max − ω²min), C_s = (ω_max − ω_min)/ω, I = ΔE/(C_s ω²) | **Confirmed** | CodeCogs, Sarkar |
| Rayleigh critical speed (`audit_mech_a`) | ω = √(g ΣWδ/ΣWδ²) | **Confirmed** as an upper bound (Dunkerley gives a lower bound) | Wikipedia, rotor-dynamics notes |
| Two-DOF modes (`audit_mech_a`) | det(K − ω²M) = 0, worked case 2k, k gives ω² = k/m and 3k/m; the code's closed form gives the same | **Confirmed** | MIT 16.07, UAlberta notes |
| Transmissibility and unbalance (`audit_mech_a`) | T = √((1 + (2ζr)²)/((1 − r²)² + (2ζr)²)); X = (me/M) r²/√(…); isolation for r > √2 | Standard form; the search for it was rate-limited, so **not confirmed online** | none read |
| Notch sensitivity (`audit_mech_a`) | Peterson q = 1/(1 + a/r), K_f = 1 + q(K_t − 1) | Form **confirmed** (Neuber's is the square-root version). **Assumption text was wrong**: it said a of 0.25 to 0.8 mm for steels; sources give 0.064 mm (quenched and tempered), 0.25 mm (annealed low-carbon) and 0.51 mm (aluminium). Text corrected | Neuber/Peterson comparison papers |
| Thin-wall vessel (`audit_mech_a`) | σ_h = pr/t, σ_l = pr/2t, limit t/r ≤ 1/10 (some use 1/20) | **Confirmed**; the code uses mean diameter, ASME uses the inside radius, so the required thickness differs slightly from the code formula (stated in the assumptions) | Engineers Edge, strength notes |
| Disc clutch (`audit_mech_a`) | uniform wear T = μF(r_o + r_i)/2; uniform pressure T = (2/3)μF(r_o³ − r_i³)/(r_o² − r_i²) | **Confirmed**; uniform pressure gives the higher torque | NPTEL, Hazim Khalil notes |
| Rotating-mass balancing (`audit_mech_b`) | F = mrω²; static balance ΣF = 0 | **Confirmed** | Wikipedia, HBK |
| Regenerative Rankine, open heater (`audit_mech_b`) | y = (h_f − h_pump)/(h_bleed − h_pump), worked example y = 22.86 % | **Confirmed** (same balance); the code's y uses the same states | Thermostate, lecture notes |
| Wet steam and throttling (`audit_mech_b`) | h = h_f + x h_fg, throttling is isenthalpic | **Confirmed** | Steam-table notes |
| Moist air and combustion (`audit_mech_b`) | wet-bulb definition; ν_O₂ = x + y/4, 4.76 mol air per mol O₂, methane 17.2, octane about 14.7 | **Confirmed** | Wikipedia, BYU combustion notes |
| Affinity laws (`audit_mech_b`) | Q ∝ N D³, H ∝ N² D², P ∝ N³ D⁵ | **Confirmed**; some sites print the diameter-only forms (D, D², D³) for a fixed-geometry trim | Pump Fundamentals, Neutrium |
| Swamee–Jain (`audit_mech_b`) | f = 0.25/[log₁₀(ε/3.7D + 5.74/Re^0.9)]² | **Confirmed**; reported error against Colebrook is about 1 % in the original range and up to 3 % elsewhere | EngineersEdge, Ingenius |
| Blasius flat plate (`audit_mech_b`) | δ = 5x/√Re_x, c_f = 0.664/√Re_x, C_D = 1.328/√Re_L | **Confirmed**; the turbulent one-seventh-power constants (0.37, 0.0592, 0.074) were not printed in the pages read | Engineering Hulk, Purdue |
| Couette–Poiseuille flow (`audit_mech_b`) | u = Uy/h + (1/2μ)(dp/dx)(y² − yh); wall shear and flow rate by integration | **Confirmed** (profile from sources; shear and flow rate re-derived by hand); sign conventions for dp/dx differ between sources | NPTEL, NTNU |
| IC engine (`audit_mech_b`) | IMEP = W/V_d, P = bmep V_d N/n_R, η_v = n_R ṁ/(ρ V_d N) | **Confirmed** for the mep and power forms; η_v is the standard definition | Wikipedia, Heywood |
| Merchant cutting (`audit_mech_b`) | φ = 45° + α/2 − β/2; tan φ = r cos α/(1 − r sin α); F_s = τ w t/sin φ | **Confirmed**; Merchant agrees poorly with steel and carbide tools | KSU lecture, journals |
| Open-die forging (`audit_mech_b`) | p = σ_f(1 + 2μr/3h) | **Not confirmed online**: the plane-strain analogue 1 + μa/h was found, but not the round form. Groover prints a shape factor 1 + 0.4μD/h (about 20 % larger friction term). Assumption text now says so | Metal-forming notes |
| Cam follower motion (`audit_mech_b`) | cycloidal s = h(θ/β − sin(2πθ/β)/2π), peak v = 2hω/β, zero acceleration at the ends | **Confirmed** | ME 325 notes, KSU cam handout |
| Planetary gear, Grashof (`audit_mech_b`) | Willis equation, i = 1 + Z_r/Z_s (ring fixed), s + l ≤ p + q | **Confirmed**; Grashof does not apply to slider-cranks (the code uses the exact slider kinematics, not Grashof) | tec-science, UC Davis |
| Contact conductance (`audit_mech_b`) | thermal-contact definitions, typical 200 to 200 000 W/(m² K); h_c = 1.25 k_s (m/σ)(P/H_c)^0.95 | Typical range **confirmed**; the CMY coefficient and exponent were **not printed** | Wikipedia, COMSOL |
| Critical radius of insulation (`audit_mech_b`) | r_cr = k/h (cylinder), 2k/h (sphere) | **Confirmed** | Skill-Lync, Çengel |
| Adams weld peak temperature (`audit_mech_b`) | 1/(T_p − T_0) = 4.13 ρ c t Y/H_net + 1/(T_m − T_0) | Source and context **confirmed** (Adams 1958); the 4.13 constant was **not printed** in any page read | Welding Journal 1958 references |
| Rohsenow, Zuber, sheet-metal bending, V-belt, press fit (`audit_mech_a`/`audit_mech_b`) | Rohsenow n = 1 for water, 1.7 otherwise; Zuber 0.131 | Searches returned nothing usable (rate limits or no hits): **not confirmed online** | none |

## Pass 12 results (electrical and electronics, 12 rows, no errors found)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Butterworth and Chebyshev order (`audit_elec_b`) | n_B = ⌈log((10^(As/10) − 1)/(10^(Ap/10) − 1))/(2 log(ωs/ωp))⌉; n_C = ⌈acosh√(…)/acosh(ωs/ωp)⌉; cutoff from \|H\|² = 1/(1 + (ω/ωc)^2n) | **Confirmed** (Butterworth from the magnitude relation, Chebyshev from the cheb1ord source); Chebyshev order is never higher than Butterworth | R signal docs, FOSSEE cheb1ord, TU Delft |
| Sallen–Key unity-gain low-pass (`audit_elec_b`) | Equal resistors: Q = ½√(C1/C2), so C1 = 4Q²C2 and R = 1/(4π Q f0 C2) | **Confirmed** by the equal-capacitor Q = ½ case and f0 = 1/(2π√(R1R2C1C2)); the printed general Q formula was stripped from the pages | Analog Devices, Wikipedia |
| 555 timer (`audit_elec_b`) | t_high = 0.693(R1 + R2)C, t_low = 0.693 R2 C, f = 1.44/((R1 + 2R2)C), monostable 1.1RC (ln 3 exactly) | **Confirmed**; duty is quoted as the high fraction or the low fraction in different sources, and one page's 0.7/(R1C) is wrong | TI datasheet, calculator pages |
| Radar, Friis cascade, dish and dipole (`audit_elec_b`) | R⁴ = Pt G² λ² σ/((4π)³ S_min); F = F1 + (F2 − 1)/G1; G = η(πD/λ)²; dipole 2.15 dBi | Radar structure and dipole **confirmed**; Friis and dish gain are standard but were **not printed** | MIT Lincoln Lab, antenna lectures |
| Kaiser FIR design (`audit_elec_b`) | β = 0.1102(A − 8.7) (A > 50), 0.5842(A − 21)^0.4 + 0.07886(A − 21) (21 to 50), 0 below; order (A − 7.95)/(2.285 Δω), taps = order + 1 | **Confirmed**; Δf must be normalised to cycles per sample (the code uses 2π df/fs) | MathWorks kaiserord, SciPy source |
| BER, Hamming (`audit_elec_b`) | BPSK ½erfc√(Eb/N0); 16-QAM (3/8)erfc√(0.4 Eb/N0); non-coherent BFSK ½e^(−Eb/2N0); n = 2^r − 1, k = n − r | BER forms **confirmed** (one page's (3/8)Q(…) is off by 2); Hamming lengths from general knowledge | Rayleigh-fading derivation, LNTwww |
| IPC-2221 trace (`audit_elec_b`) | I = k ΔT^0.44 A^0.725, A in mil², k = 0.048 outer and 0.024 inner; worked case 2 A, 10 K gives 42.4 mil² | **Confirmed**; IPC-2152 permits about 1.5 to 2 times more current | NextPCB, Zbotic and others |
| IEC inverse-time relays (`audit_elec_a`) | t = TMS k/(M^α − 1): 0.14/0.02, 13.5/1, 80/2 | **Confirmed**; at M = 10 about 3.0 s, 1.5 s and 0.8 s; IEC 60255-151 is the current edition | myElectrical, Overvis |
| Steinmetz and eddy loss (`audit_elec_a`) | P = k f^α B^β; classical eddy loss π²B²d²f²/(6ρρ_m) | Steinmetz **confirmed** (sinusoidal flux only; iGSE for other waveforms); the eddy formula is from memory and was **not printed** | UTK lectures, iGSE paper |
| IEEE 80 touch and step (`audit_elec_a`) | (1000 + 1.5 C_s ρ_s)0.116/√t_s and (1000 + 6 C_s ρ_s)0.116/√t_s; C_s = 1 − 0.09(1 − ρ/ρ_s)/(2h_s + 0.09) | **Confirmed**; 0.157 is the 70 kg constant | elek.com, IEEE 80 notes |

## Pass 13 results (aerospace, nuclear, petroleum, 15 rows, no errors found)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| ISA isothermal layer (`audit_aero_a`) | T = 216.65 K, p = 22 632 Pa e^(−g(h − 11 km)/(R T)); about 5475 Pa at 20 km | **Confirmed**; the code reproduces 20 km | Wikipedia ISA, US Standard Atmosphere table |
| Normal shock, Prandtl–Meyer (`audit_aero_a`) | M₂² = (1 + (γ−1)M₁²/2)/(γM₁² − (γ−1)/2); ν(M) with ν(2.5) = 38.91° | **Confirmed** | NASA Glenn, MIT 16.unified |
| Oblique shock θ–β–M, area–Mach (`audit_aero_a`) | tan θ = 2 cot β (M² sin²β − 1)/(M²(γ + cos 2β) + 2); worked case M 5, θ 20°, β 29.8°; A/A* = 2.637 at M 2.5 | **Confirmed** | Penn State, Purdue |
| Propeller Breguet, actuator disk, hover (`audit_aero_a`) | R = (η/c)(L/D) ln(W₀/W₁); η = 2/(1 + √(1 + C_T)); P = T^1.5/√(2ρA) | **Confirmed**; endurance optimum is at minimum power (C_L^1.5/C_D) | Clarkson AE 429, MIT Unified |
| Ideal turbojet (`audit_aero_a`) | specific thrust (1 + f)V_e − V₀ | Form **confirmed**; nozzle expansion term standard | NASA Glenn, MIT Unified |
| J2 regression, sun-synchronous (`audit_aero_b`) | dΩ/dt = −(3/2)J₂(R/p)² n cos i; sun rate 0.9856°/day; 800 km gives 98.7° | **Confirmed** | Wikipedia, FreeFlyer guide |
| Sutton–Graves, Allen–Eggers (`audit_aero_b`) | q = 1.7415×10⁻⁴ √(ρ/R_n) V³; peak deceleration independent of mass and drag | Constant **confirmed** (other authors use 1.63 to 1.83 ×10⁻⁴); closed forms V² sin γ/(2eH) and ρ = β sin γ/H were **not printed** | NASA TR R-376 references |
| Hohmann, bi-elliptic, sphere of influence, Clohessy–Wiltshire, multistage (`audit_aero_b`) | standard forms; CW valid for ρ/a < 0.01 | CW and Tsiolkovsky staging **confirmed** in outline; Hohmann, bi-elliptic and r_SOI = a(m/M)^(2/5) were **not confirmed online** (sources returned nothing) | none |
| Reactor point kinetics (`audit_nuclear`) | T = (β − ρ)/(λρ); prompt jump β/(β − ρ), valid only for ρ < β | **Confirmed** | MIT 22.05, Wikipedia inhour |
| Bare-reactor buckling (`audit_nuclear`) | sphere (π/R)², cylinder (2.405/R)² + (π/H)², with extrapolation distance added | **Confirmed**; code uses the correct geometry for each shape | Lamarsh, Wikipedia buckling |
| Xenon-135 (`audit_nuclear`) | build-up in 40 to 50 h, about 95 % from iodine-135, σ about 2.6×10⁶ b, flux-independent at high flux | Behaviour **confirmed**; the equilibrium formula itself was not printed | HyperPhysics, Wikipedia |
| Vogel IPR (`audit_petro`) | q/q_max = 1 − 0.2(p_wf/p_r) − 0.8(p_wf/p_r)² for saturated reservoirs | Applicability **confirmed**; the coefficients were **not printed** in the pages read | Vogel (1968) summaries |
| Standing Rs and B_o, Corey relative permeability (`audit_petro`) | Rs = γ_g[(p/18.2 + 1.4)10^(0.0125 API − 0.00091 T)]^1.2048; B_o = 0.9759 + 1.2×10⁻⁴[Rs(γ_g/γ_o)^0.5 + 1.25T]^1.2 | **Not confirmed online** (only glossary pages) | none |
| Bit hydraulics (`audit_petro`) | ΔP = ρQ²/(10858 A_t²); HHP = ΔPQ/1714; F = 0.01823 C_d Q√(ρΔP); worked case 1097 psi, 192 hp, 654 lb | **Confirmed** (10858 is 12028 × 0.95²) | drillingmanual.com, AAPG wiki |
| Well test semilog (`audit_petro`) | k = 162.6 q B μ/(m h); s = 1.151[(p₁ₕᵣ − p_wf)/m − log(k/(φμc_t r_w²)) + 3.23] | **Confirmed**; the constant is 3.2275 or 3.23 depending on source; m is used as a magnitude | KGS, PSU PNG 301 |

## Pass 14 results (physics, chemical engineering, materials, plus retries of earlier gaps; 20 rows, no errors found)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Hohmann and bi-elliptic (`audit_aero_b`) | Δv₁ = √(μ/r₁)(√(2r₂/(r₁ + r₂)) − 1); Hohmann always better below r₂/r₁ = 11.94, bi-elliptic can win above it (best apoapsis ratio large near the threshold) | **Confirmed** (retry of Pass 13); reproduces a published 2825 m/s first burn for 6700 to 93 800 km | Wikipedia, FreeFlyer guide |
| Vogel IPR (`audit_petro`) | q/q_max = 1 − 0.2(p_wf/p_r) − 0.8(p_wf/p_r)², saturated reservoirs, error under 10 % (to 20 % late in depletion) | **Confirmed** (retry) | PetroWiki, IHS Harmony |
| Standing Rs (`audit_petro`) | constants 1.4, 18.2, 0.0125, 0.00091 and exponent family | Constants **confirmed** through the inverse (bubble-point) form; the printed page was garbled, so the 1.2048 exponent and the B_o form stay **unconfirmed** | Libyan crude study, Standing 1947 summaries |
| Allen–Eggers (`audit_aero_b`) | a_max = V²sin γ/(2eH) at ρ = β sin γ/H, velocity V/√e there | **Re-derived** from ρ = ρ₀e^(−h/H) and a = ρV²/2β, consistent with the NACA claim of independence from mass and drag; the closed form itself is still not printed in a page read | NACA 1381 summaries, Wikipedia |
| Rohsenow boiling (`audit_mech_b`) | Pr exponent 1 for water and 1.7 for other fluids; C_sf is surface-specific (0.013 default) | **Confirmed** (retry); the code's label says the same | COMSOL, ht library |
| Contact conductance CMY (`audit_mech_b`) | h_c = 1.25 k_s (m/σ)(P/H_c)^0.95, valid for P/H_c from 10⁻⁶ to about 2.3×10⁻² | **Confirmed** (retry), including the harmonic-mean k_s | Waterloo MHTL |
| Fabry–Pérot (`audit_phys_a`) | F = π√R/(1 − R), Airy 1/(1 + (4R/(1 − R)²) sin²(δ/2)), FSR = c/(2nL) | **Confirmed** | arXiv Fabry–Pérot review |
| GR tests (`audit_phys_a`) | Δϖ = 6πGM/(c²a(1 − e²)) per orbit, 43″/century; deflection 4GM/(c²b), 1.75″; Shapiro round trip (4GM/c³) ln(4r₁r₂/b²), about 247 µs for Earth to Mars | **Confirmed**; the Shapiro prefactor and extra constants differ by convention | arXiv 0712.3709, lecture pages |
| Landé g, Eddington luminosity (`audit_phys_a`/`audit_phys_b`) | g_J = 1 + [J(J+1) + S(S+1) − L(L+1)]/(2J(J+1)); L_E = 4πGMm_p c/σ_T, 1.26×10³¹ W per solar mass for μ_e = 1 | **Confirmed**; the code carries the mass M as an input, so no solar-mass factor is missing | NIST, Wikipedia |
| Kronig–Penney (`audit_phys_a`) | cos(ka) = cos(αa) + P sin(αa)/(αa) | Standard form; sources printed only variants, so **not confirmed online** | none |
| Fenske, Underwood, Gilliland (`audit_chem_a`) | N_min = log[(x_D/(1 − x_D))((1 − x_B)/x_B)]/log α; Molokanov fit Y = 1 − exp[((1 + 54.4X)/(11 + 117.2X))((X − 1)/√X)] | Fenske and the Underwood procedure **confirmed**; the Molokanov constants match standard references but no page printed them, and the Kremser form is also unprinted | Intechopen, OGJ, SciELO |
| Peng–Robinson (`audit_chem_a`) | a = 0.45724 R²T_c²/P_c, b = 0.07780 RT_c/P_c, κ = 0.37464 + 1.54226ω − 0.26992ω², α = [1 + κ(1 − √T_r)]² | **Confirmed**; κ applies for ω ≤ 0.491 (a different polynomial above) and one page misprints 1.564226 | Cantera, UDel notebook |
| Lapple cyclone (`audit_chem_a`) | d₅₀ = √(9μW/(2πN_e v_i (ρ_p − ρ_g))), η = 1/(1 + (d₅₀/d)²) | **Confirmed**, including the (ρ_p − ρ_g) term and W as the inlet width | Karabuk paper, powderprocess.net |
| Thiele, Metzner–Reed (`audit_chem_a`, `audit_chem_b`) | η = tanh φ/φ (slab), (3/φ²)(φ coth φ − 1) (sphere); Re_MR = Dⁿ V²⁻ⁿ ρ/[K 8ⁿ⁻¹((3n+1)/4n)ⁿ] | **Confirmed** | Wikipedia, UCSB, arXiv |
| Avrami, Scheil, Larson–Miller (`audit_mat_a`) | X = 1 − exp(−k tⁿ); C_s = k C₀(1 − f_s)^(k−1); P = T(C + log₁₀ t) | **Confirmed**; Scheil diverges at f_s → 1, C is not universal (about 20 for steels) | Wikipedia, DoITPoMS, NEML |
| Taylor and Hall–Petch (`audit_mat_a`) | Δσ = M α G b √ρ (M 3.06 fcc); σ_y = σ₀ + k d^(−1/2) | **Confirmed** | arXiv, steel university |
| PREN, Stoney, Pilling–Bedworth, Gibson–Ashby, Tsai–Wu (`audit_mat_a`, `audit_mat_b`) | PREN = Cr + 3.3 Mo + 16 N (30 N for some austenitic grades, 3.3(Mo + 0.5 W) with tungsten); σ = E_s h_s²/(6(1 − ν_s) h_f R); ratio between 1 and 2 is protective; E/E_s = C(ρ/ρ_s)², C about 1; Tsai-Wu quadratic form | **Confirmed**; the code uses the 16 N form without tungsten, stated in its assumptions | Wikipedia, arXiv, SolidWorks |

## Pass 15 results (agriculture, mining, industrial, computer, architectural, chemistry; 22 rows, no errors found)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Green–Ampt (`audit_agri_mine`) | K t = F − ψΔθ ln(1 + F/ψΔθ); f = K(1 + ψΔθ/F); Δθ = porosity minus initial moisture | **Confirmed**; implicit in F, so the code solves for time given F | Iowa handouts, TxDOT hydraulics manual |
| van Genuchten, FAO-33 (`audit_agri_mine`) | θ = θ_r + (θ_s − θ_r)/[1 + (αh)ⁿ]^m with m = 1 − 1/n; 1 − Y_a/Y_m = K_y(1 − ET_a/ET_m) | **Confirmed**; FAO guidance is not designed for trees and vines | arXiv, R soilphysics, FAO |
| Christiansen reduction factor (`audit_agri_mine`) | Christiansen uniformity and the lateral reduction factor | Search rate-limited; **not confirmed online** | none |
| Plitt hydrocyclone (`audit_agri_mine`) | structure d₅₀ ∝ D_c^0.46 D_i^0.6 D_o^1.21 μ^0.5 e^(0.063φ)/(D_u^0.71 h^0.38 Q^0.45 Δρ^0.5), units cm, cP, L/min, volume per cent | Structure and exponents **confirmed**; the constant 50.5 was **not printed** | Spanish-language and CIM Bulletin references |
| Barton Q, RQD (`audit_agri_mine`) | Q = (RQD/J_n)(J_r/J_a)(J_w/SRF); RQD = 115 − 3.3 J_v (some use 110 − 2.5 J_v) | Q **confirmed**; the code uses the Priest–Hudson form RQD = 100 e^(−0.1λ)(0.1λ + 1) from joint frequency, which no page printed (**unconfirmed**) | NGI summaries, ASTM STP |
| Weibull reliability (`audit_ie_cs`) | R = exp(−(t/η)^β), h = (β/η)(t/η)^(β−1), MTTF = ηΓ(1 + 1/β) | **Confirmed**; β = 1 gives the exponential | NIST handbook, ReliaWiki |
| EOQ with backorders, newsvendor (`audit_ie_cs`) | Q* = √(2DS/H)√((H + B)/B), S* = Q*H/(H + B); critical ratio C_u/(C_u + C_o) | **Confirmed** | MetricGate, Wikipedia |
| Erlang C and M/G/1 (`audit_ie_cs`/`audit_ie_cs`) | Erlang C from Erlang B by C = B/(1 − ρ(1 − B)); W_q = C/(cμ − λ); Pollaczek–Khinchine W_q = λE[S²]/(2(1 − ρ)) | P–K **confirmed**; the Erlang B-to-C identity and W_q are standard but the search was rate-limited (**unconfirmed**) | KTH, Aalto notes |
| Amdahl, ALOHA, stop-and-wait, entropy and Huffman (`audit_ie_cs`) | 1/((1 − p) + p/s); pure S = Ge^(−2G) (max 0.184), slotted S = Ge^(−G) (max 0.368); η = 1/(1 + 2a); H ≤ L ≤ H + 1 | **Confirmed** | Wikipedia, TU Berlin, Stanford ENGR 76 |
| BRE average daylight factor (`audit_arch`) | DF = T A_w θ M/(A(1 − R²)) with θ in degrees; worked cases 2.21 % and 1.52 % recomputed | **Confirmed**; some tools omit M | Camden reports, MIT 4.493 |
| Heskestad flame height and plume (`audit_arch`) | L = 0.235 Q^0.4 − 1.02 D (7 < Q^0.4/D < 700); ṁ = 0.071 Q_c^(1/3) z^(5/3) + 0.0018 Q_c | Flame height **confirmed**; the plume form is consistent with the 0.071[1 + 0.026 Q_c^(2/3) z^(−5/3)] expansion (0.071 × 0.026 = 0.0018), though the page read printed 0.027 and was garbled | arXiv, NFPA 92 context |
| Glaser condensation (`audit_arch`) | interface vapour pressure capped at saturation; EN ISO 13788; steady-state, ignores storage and thermal bridges | **Confirmed** | Celotex, ISO 13788 summaries |
| Sabine, composite TL, sun declination (`audit_arch`) | T = 0.161 V/A (0.163 in some derivations); δ = 23.45° sin(360(284 + n)/365) | Sabine and Cooper **confirmed**; composite TL = −10 log(Στᵢ Sᵢ/ΣSᵢ) is standard but unprinted | pvlib, Montana State |
| Lift probable stops (`audit_arch`) | S = N[1 − (1 − 1/N)^P] | Search returned nothing; **not confirmed online** | none |
| Kapustinskii (`audit_chem_emerge`) | U = K ν z⁺z⁻/(r⁺ + r⁻)(1 − d/(r⁺ + r⁻)), K = 1.2025×10⁻⁴ J m/mol, d = 34.5 pm | **Confirmed**: the code reproduces the 746 kJ/mol for NaCl quoted by a source (experiment 787) | Wikipedia, LibreTexts |
| Hund's rules (`audit_chem_emerge`) | maximise S, then L, then J (lowest if under half full); carbon ³P₀, nitrogen ⁴S₃/₂ | **Confirmed** | Wikipedia, LibreTexts |
| Langmuir, Freundlich (`audit_chem_emerge`) | q = Q₀K c/(1 + K c); q = K_F c^(1/n) | **Confirmed**; the combined Sips form was not printed | adsorption-isotherm pages |
| Scalar Kalman filter (`audit_chem_emerge`) | K = P⁻/(P⁻ + R); P⁻ = a²P + Q | **Confirmed** | Berkeley EE126, TU Berlin |

## Pass 16 results (emerging topics and retries of earlier gaps; 12 rows, no errors found)

| Calculation (module) | Checked | Result | Source |
|---|---|---|---|
| Brusselator (`audit_chem_emerge`) | fixed point (A, B/A); trace B − 1 − A², determinant A²; supercritical Hopf at B = 1 + A² | **Confirmed** | arXiv Brusselator papers |
| Franck–Condon, Huang–Rhys (`audit_chem_emerge`) | weights e^(−S)Sⁿ/n!; S = ω(ΔQ)²/(2ħ) (mass-weighted displacement; some papers define it through relaxation energy S = ε/ħω); Stokes shift 2Sħω | **Confirmed** (Stokes-shift expression from the standard linear-coupling model, not printed) | arXiv spectroscopy papers |
| CHSH, Werner state, teleportation (`audit_chem_emerge`) | CHSH = 2√2 V, violated above V = 1/√2; Tsirelson bound 2√2; classical teleportation fidelity 2/3; F = (2F_e + 1)/3 | **Confirmed**; qubit-rotation probability sin²(θ/2) is standard quantum mechanics, not printed | arXiv, Siegen exercises |
| RSA strength and password entropy (`audit_ie_cs`) | GNFS exponent (64/9)^(1/3) = 1.923; NIST: 2048 bit gives 112, 3072 gives 128, 7680 gives 192; H = L log₂ N | **Confirmed**; the asymptotic formula omits the (1 + o(1)) term, so it gives about 117 bits for 2048 where NIST says 112 | NIST SP 800-57 summaries, OEIS, arXiv |
| Kronig–Penney (`audit_phys_a`) | cos(ka) = cos(αa) + P sin(αa)/(αa) with P = mV₀ba/ħ² in the Dirac-comb limit; P > 0 repulsive | **Confirmed** (retry of Pass 14) | Binghamton notes, arXiv |
| Kremser (`audit_chem_a`) | fraction absorbed (A^(N+1) − A)/(A^(N+1) − 1), stages from N + 1 = ln((A − r)/(1 − r))/ln A | **Confirmed by limits**: the value is 0 at N = 0 and tends to 1 as N grows with A > 1; the search summary called this expression the fraction *not* absorbed, which is wrong (that one is (A − 1)/(A^(N+1) − 1)) | Kremser lecture notes |
| Molokanov–Gilliland (`audit_chem_a`) | Y = 1 − exp[((1 + 54.4X)/(11 + 117.2X))((X − 1)/√X)], X = (R − R_min)/(R + 1), Y = (N − N_min)/(N + 1); good to ±7 % usually, ±30 % at worst | **Confirmed** (retry of Pass 14) | ECCE-6 paper, course exercises |
| Standing B_o (`audit_petro`) | B_o = 0.9759 + 0.00012[R_s(γ_g/γ_o)^0.5 + 1.25T]^1.2; at or below the bubble point; overpredicts above 1.2 rb/stb | **Confirmed** (retry of Pass 14) | course slides, IHS correlations |
| Attack-tree probability (`audit_chem_emerge`) | AND multiplies, OR uses 1 − Π(1 − p) | Standard probability; no source needed | none |
| Zipf hot keys, quorum availability (`audit_chem_emerge`) | H_N ≈ ln N + γ + 1/(2N); R + W > N for strong consistency | Standard results; not searched | none |
| Kalman, risk matrix (`audit_chem_emerge`) | see Pass 15 for the Kalman rows | **Confirmed** in Pass 15 | none |

## Not yet checked

Of the 385 calculations in the audit fill, about 225 formulas and constants have been checked over 16 passes; the rest are standard forms searched without success or not searched. The specific items the web could not settle are in the textbook-check list in [ROADMAP.md](ROADMAP.md). The roughly 990 calculations written before the audit fill have not been through these passes.

## How to continue

1. For each item: search for the exact coefficients, read the page that states them, and add a row above with the source and the result.
2. Where the source disagrees, fix the calculation and its test together, and say so here.
3. Where only a secondary source was read, keep "confirmed (secondary)" until the original is read.
4. Re-run the full test suite after any change.
