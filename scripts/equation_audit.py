"""Equation audit: a checklist of standard equations per discipline, each looked up in the library.

Usage:
    python scripts/equation_audit.py            # print the gaps
    python scripts/equation_audit.py --write    # also write docs/EQUATION_AUDIT.md

Every topic has one or more alternative search phrases (all words of a phrase must appear in a calculation's name, tags, description,
equation titles or variable labels). A topic is *covered* when any phrase finds a calculation, otherwise it is a *gap*.

The checklist is the author's knowledge of what each field teaches and uses, so it shares the author's blind spots: it shows
what a reader of standard textbooks would expect to find that is missing, not that nothing else is missing. A phrase that
matches loosely can hide a gap (the matched calculation is listed so that it can be read), and a phrase that is too narrow can
report a gap that exists under another name; the gaps were therefore re-checked by hand with broader phrases before they were written up.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sliderule.core.catalog import default_catalog

# (topic, [alternative phrases])
CHECK: dict[str, list[tuple[str, list[str]]]] = {
    "Civil and structural engineering": [
        ("Mohr's circle and principal stresses", ["mohr circle", "principal stress"]),
        ("Fixed-fixed or propped-cantilever beam deflection", ["fixed beam", "propped cantilever", "fixed-end"]),
        ("Continuous beam: three-moment equation", ["three-moment", "continuous beam"]),
        ("Truss member forces (joints or sections)", ["truss"]),
        ("Moment-area or virtual-work deflection (unit load)", ["virtual work", "moment-area", "castigliano"]),
        ("Influence line of a moving load", ["influence line", "moving load"]),
        ("Johnson parabola / inelastic column", ["johnson", "inelastic buckling", "effective length"]),
        ("Section properties of composite and T-sections (parallel axis)", ["parallel axis", "composite section", "t-section"]),
        ("Torsion of thin-walled closed sections (Bredt)", ["bredt", "thin-walled"]),
        ("Combined axial and bending stress / kern", ["eccentric", "kern", "combined stress"]),
        ("Plate buckling", ["plate buckling", "local buckling"]),
        ("Prestressed concrete: stresses and losses", ["prestress"]),
        ("Bolt shear and bearing capacity", ["bolt shear", "bolted connection", "bearing capacity bolt"]),
        ("Reinforced concrete shear design (stirrups)", ["stirrup", "shear reinforcement", "concrete shear"]),
        ("Development length of reinforcement", ["development length", "anchorage"]),
        ("RC column interaction / axial capacity", ["column capacity", "interaction diagram", "reinforced concrete column"]),
        ("Cracked-section deflection of RC (effective moment of inertia)", ["effective moment of inertia", "cracked section", "branson"]),
        ("Timber or masonry member design", ["timber", "masonry"]),
        ("Steel beam: lateral-torsional buckling / plastic moment", ["lateral-torsional", "plastic moment", "shape factor"]),
        ("Rankine and Coulomb earth pressure", ["rankine", "earth pressure", "coulomb wedge"]),
        ("Retaining wall stability (overturning, sliding)", ["retaining wall"]),
        ("Infinite slope stability", ["infinite slope"]),
        ("Boussinesq stress under a load", ["boussinesq", "stress influence", "vertical stress increase"]),
        ("Soil phase relations (void ratio, saturation, unit weights)", ["void ratio", "phase relation", "degree of saturation"]),
        ("Compaction (Proctor, relative density)", ["compaction", "relative density", "proctor"]),
        ("Pile capacity (skin friction and end bearing)", ["pile"]),
        ("Sheet pile / braced excavation", ["sheet pile", "braced"]),
        ("Seepage flow net, piping and uplift", ["flow net", "seepage", "piping"]),
        ("Terzaghi consolidation: time factor and degree", ["time factor", "degree of consolidation", "terzaghi consolidation"]),
        ("Secondary compression", ["secondary compression", "creep settlement"]),
        ("Liquefaction (cyclic stress ratio)", ["liquefaction", "cyclic stress"]),
        ("Elastic settlement of footings", ["elastic settlement", "immediate settlement"]),
        ("Atterberg limits and plasticity / liquidity index", ["atterberg", "plasticity index", "liquidity index"]),
        ("Mohr–Coulomb shear strength / triaxial", ["mohr-coulomb", "triaxial", "shear strength"]),
        ("Darcy–Weisbach with Colebrook / Moody friction factor", ["colebrook", "moody", "darcy-weisbach"]),
        ("Chézy and Manning with compound sections", ["chezy", "chézy"]),
        ("Critical depth and specific energy", ["critical depth", "specific energy"]),
        ("Hydraulic jump (sequent depth, energy loss)", ["hydraulic jump", "sequent depth"]),
        ("Gradually varied flow (standard step, backwater)", ["gradually varied", "backwater", "water surface profile"]),
        ("Culvert hydraulics (inlet control)", ["culvert"]),
        ("Water hammer (Joukowsky surge)", ["water hammer", "joukowsky", "surge"]),
        ("Pump affinity laws and specific speed", ["affinity", "specific speed", "pump scaling"]),
        ("Unit hydrograph / convolution", ["unit hydrograph", "hydrograph"]),
        ("Muskingum flood routing", ["muskingum", "flood routing", "channel routing"]),
        ("Intensity–duration–frequency curves", ["intensity-duration", "idf"]),
        ("Time of concentration (Kirpich, SCS lag)", ["time of concentration", "kirpich"]),
        ("Flood frequency (Gumbel, log-Pearson)", ["gumbel", "log-pearson", "flood frequency"]),
        ("Evapotranspiration (Penman–Monteith, Hargreaves, Thornthwaite)", ["penman", "hargreaves", "evapotranspiration", "thornthwaite"]),
        ("Theis well function / transient drawdown", ["theis", "well function"]),
        ("Traffic signal timing (Webster)", ["webster", "signal timing", "signal cycle"]),
        ("Highway capacity and level of service", ["level of service", "highway capacity"]),
        ("Superelevation and side friction", ["superelevation"]),
        ("Vertical curves (length, K value)", ["vertical curve"]),
        ("Gravity trip distribution / trip generation", ["gravity model", "trip generation", "trip distribution"]),
        ("Surveying: coordinates, area and traverse closure", ["traverse", "coordinate area", "closure"]),
        ("Surveying: levelling, curvature and refraction", ["levelling", "leveling", "curvature and refraction"]),
        ("Critical path method (forward and backward pass, float)", ["critical path", "float"]),
        ("Earned value management", ["earned value"]),
        ("Learning curve (construction and manufacturing)", ["learning curve"]),
        ("Wave shoaling, refraction and breaking", ["shoaling", "wave refraction", "breaking wave", "breaker"]),
        ("Wave run-up and overtopping", ["run-up", "runup", "overtopping"]),
        ("BOD kinetics and ultimate BOD", ["bod", "biochemical oxygen demand"]),
        ("Trickling filter / rotating biological contactor (NRC)", ["trickling filter"]),
        ("Rapid sand filtration headloss", ["filtration headloss", "sand filter", "rapid filter"]),
        ("Coagulant dose / jar test, flocculation G value", ["flocculation", "velocity gradient", "coagulation"]),
        ("Langelier saturation index", ["langelier", "saturation index"]),
        ("Solids retention time (SRT) and sludge production", ["sludge age", "solids retention", "srt"]),
        ("Plume rise (Briggs) and effective stack height", ["plume rise", "briggs", "effective stack"]),
        ("Landfill gas generation", ["landfill"]),
        ("Noise: barrier attenuation, traffic noise", ["noise barrier", "barrier attenuation", "traffic noise"]),
        ("Chlorine contact time (CT) and disinfection", ["chlorine contact", "ct value", "disinfection"]),
        ("Stormwater detention pond sizing", ["detention", "stormwater"]),
        ("Pipe network analysis (Hardy Cross)", ["hardy cross", "pipe network"]),
        ("Open-channel flow: weirs of other shapes (V-notch, Cipolletti, broad-crested)", ["v-notch", "broad-crested", "cipolletti"]),
        ("Scour at bridge piers", ["scour"]),
        ("Soil bearing: Meyerhof / Hansen shape and depth factors", ["meyerhof", "shape factor", "depth factor"]),
        ("Settlement of piles / group efficiency", ["group efficiency", "pile group"]),
        ("Dam: gravity dam stability and uplift", ["gravity dam", "uplift"]),
    ],
    "Mechanical engineering": [
        ("Stress concentration factor", ["stress concentration"]),
        ("Thick-walled cylinder (Lamé)", ["lame", "lamé", "thick-walled"]),
        ("Thin-walled pressure vessel stresses", ["thin-walled pressure", "pressure vessel", "hoop stress"]),
        ("Press fit / interference fit", ["press fit", "interference fit", "shrink fit"]),
        ("Shaft design under combined loading (ASME, Soderberg, Goodman)", ["goodman", "soderberg", "endurance limit", "shaft design"]),
        ("Gear tooth bending stress (Lewis) and contact stress", ["lewis", "gear tooth", "spur gear"]),
        ("Rolling bearing life (L10)", ["bearing life", "l10", "rolling bearing"]),
        ("Belt and chain drives", ["belt drive", "chain drive", "v-belt"]),
        ("Clutches and brakes (disc, drum)", ["clutch", "disc brake", "drum brake"]),
        ("Bolted joint stiffness and preload", ["preload", "joint stiffness", "bolt stiffness"]),
        ("Flywheel energy and speed fluctuation", ["flywheel"]),
        ("Balancing of rotating masses", ["balancing", "unbalance"]),
        ("Vibration isolation / transmissibility", ["transmissibility", "isolation"]),
        ("Critical speed of a shaft / Rayleigh method", ["critical speed", "rayleigh", "whirl"]),
        ("Modal analysis of a multi-degree-of-freedom system", ["modal", "mode shape", "natural frequencies"]),
        ("Forced vibration with base excitation / rotating unbalance", ["base excitation", "rotating unbalance"]),
        ("Dittus–Boelter / Gnielinski internal convection", ["dittus", "gnielinski", "nusselt pipe", "internal flow nusselt"]),
        ("Natural convection correlations (Churchill–Chu, Rayleigh number)", ["rayleigh number", "churchill", "natural convection"]),
        ("External forced convection over a plate or cylinder", ["flat plate", "cylinder cross-flow", "nusselt plate"]),
        ("Radiation view factors and enclosure exchange", ["view factor", "enclosure", "radiosity"]),
        ("Boiling and condensation heat transfer", ["boiling", "condensation", "nukiyama"]),
        ("Thermal resistance network (composite wall, cylinder, sphere)", ["thermal resistance", "composite wall", "cylindrical wall"]),
        ("Critical radius of insulation", ["critical radius", "insulation"]),
        ("Brayton and combined cycles", ["brayton", "gas turbine", "combined cycle"]),
        ("Psychrometrics (humidity ratio, wet bulb, enthalpy)", ["psychrometric", "humidity ratio", "wet bulb"]),
        ("Steam properties / quality / throttling", ["steam quality", "throttling", "enthalpy of steam"]),
        ("Combustion stoichiometry and air–fuel ratio", ["stoichiometric", "air-fuel", "excess air"]),
        ("Compressor and turbine efficiency (isentropic)", ["isentropic efficiency", "isentropic compressor", "turbine efficiency"]),
        ("Compressible flow: choked nozzle, normal shock", ["choked", "normal shock", "converging-diverging"]),
        ("Fanno and Rayleigh flow", ["fanno", "rayleigh flow"]),
        ("Boundary layer thickness and skin friction (Blasius)", ["blasius", "boundary layer", "skin friction"]),
        ("Pump affinity laws, system curve, series and parallel pumps", ["affinity", "system curve"]),
        ("Couette flow and flow between plates", ["couette"]),
        ("Pipe fittings, minor losses and equivalent length", ["minor loss", "equivalent length", "k factor"]),
        ("Flow in non-circular ducts (hydraulic diameter)", ["hydraulic diameter", "duct"]),
        ("Bode plot, gain and phase of a transfer function", ["bode", "frequency response", "transfer function"]),
        ("Routh–Hurwitz stability", ["routh", "hurwitz"]),
        ("Root locus", ["root locus"]),
        ("State-space system (eigenvalues, controllability)", ["state-space", "state space", "controllability"]),
        ("Lead and lag compensators", ["lead compensator", "lag compensator", "compensator"]),
        ("Taylor tool life and cutting economics", ["taylor tool", "tool life"]),
        ("Orthogonal cutting forces (Merchant)", ["merchant", "shear angle", "orthogonal cutting"]),
        ("Sheet-metal bending (bend allowance, springback)", ["bend allowance", "springback", "sheet metal"]),
        ("Forging and rolling force", ["forging", "rolling force", "roll gap"]),
        ("Casting solidification time (Chvorinov)", ["chvorinov", "solidification"]),
        ("Injection moulding / extrusion (clamp force, cooling time)", ["injection moulding", "injection molding", "clamp force", "cooling time"]),
        ("Machining: surface finish, MRR, power", ["material removal rate", "surface roughness", "cutting power"]),
        ("Welding: residual stress / heat-affected zone", ["heat-affected", "haz", "residual stress"]),
        ("Fatigue: Miner's rule and Basquin", ["miner", "basquin", "cumulative damage"]),
        ("Fracture: stress intensity, J-integral, Paris law", ["paris law", "stress intensity", "crack growth"]),
        ("Creep: Larson–Miller / Norton", ["larson", "norton creep"]),
        ("Springs: extension, torsion, Belleville, leaf", ["extension spring", "torsion spring", "leaf spring", "belleville"]),
        ("Power screw and thread stress", ["power screw", "thread"]),
        ("Keys, splines and couplings", ["key", "spline", "coupling"]),
        ("Kinematics: four-bar linkage, slider-crank", ["four-bar", "slider-crank", "linkage"]),
        ("Cam follower motion", ["cam"]),
        ("Gear trains (planetary, compound)", ["planetary", "gear train"]),
        ("Hydrodynamic bearing (Sommerfeld, Petroff)", ["petroff", "journal bearing", "sommerfeld"]),
        ("Heat pipe / thermal contact resistance", ["heat pipe", "contact resistance"]),
        ("Heat sink / extended surface optimisation", ["heat sink", "fin efficiency"]),
        ("Internal combustion engine: mean effective pressure, volumetric efficiency", ["mean effective pressure", "volumetric efficiency", "engine"]),
        ("Refrigerant cycles with real properties; absorption refrigeration", ["absorption refrigeration", "absorption"]),
        ("Turbomachinery velocity triangles, Euler turbine equation", ["euler turbine", "velocity triangle", "euler pump"]),
        ("Hydraulic turbines (Pelton, Francis) and specific speed", ["pelton", "francis", "hydro turbine"]),
        ("Fans: laws, static pressure, duct system", ["fan law", "fan"]),
        ("Open and closed feedwater heaters / regenerative Rankine", ["regenerative", "feedwater", "reheat"]),
    ],
    "Electrical and electronic engineering": [
        ("Thevenin and Norton equivalents; maximum power transfer", ["thevenin", "norton", "maximum power transfer"]),
        ("Nodal and mesh analysis (matrix)", ["nodal", "mesh analysis"]),
        ("Transformer equivalent circuit and voltage regulation", ["transformer regulation", "equivalent circuit transformer", "voltage regulation"]),
        ("Induction motor equivalent circuit", ["induction motor equivalent", "slip torque"]),
        ("Synchronous machine: power angle, V-curves", ["synchronous", "power angle"]),
        ("Symmetrical components and unsymmetrical faults", ["symmetrical component", "unbalanced fault", "sequence"]),
        ("Transmission line: ABCD, lumped models, input impedance", ["abcd", "input impedance", "transmission line"]),
        ("Smith chart / impedance matching (L-match, stub)", ["smith", "impedance matching", "stub"]),
        ("Antenna: dipole, directivity, gain, effective aperture", ["antenna", "directivity", "effective aperture"]),
        ("Friis transmission formula", ["friis"]),
        ("Radar range equation", ["radar"]),
        ("Noise figure and cascaded noise (Friis noise)", ["noise figure", "noise temperature", "cascade"]),
        ("Thermal noise kTB", ["thermal noise", "johnson noise"]),
        ("Butterworth and Chebyshev filter order and response", ["butterworth", "chebyshev", "filter order"]),
        ("Active filter (Sallen–Key) design", ["sallen", "active filter"]),
        ("BJT biasing and small-signal gain", ["bjt", "bipolar", "transistor bias"]),
        ("MOSFET small-signal and amplifier gain", ["small-signal", "transconductance", "common-source"]),
        ("555 timer", ["555", "astable", "monostable"]),
        ("Differential amplifier / CMRR", ["cmrr", "differential amplifier"]),
        ("Op-amp circuits: integrator, differentiator, summing, comparator", ["integrator", "summing amplifier", "comparator", "schmitt"]),
        ("Oscillators (Wien bridge, crystal, LC)", ["oscillator", "wien"]),
        ("Phase-locked loop", ["phase-locked", "pll"]),
        ("Digital logic delay and fan-out; setup and hold", ["propagation delay", "setup time", "fan-out", "hold time"]),
        ("Power flow of a two-bus system / voltage drop", ["power flow", "load flow"]),
        ("Overcurrent protection: IDMT relay curve, fuse", ["idmt", "relay", "fuse", "inverse time"]),
        ("Cable ampacity and derating", ["ampacity", "derating"]),
        ("Battery: state of charge, internal resistance, Peukert", ["peukert", "state of charge", "internal resistance"]),
        ("Motor starting and torque–speed (DC, series, shunt)", ["motor starting", "dc motor", "series motor"]),
        ("Maxwell: Poynting vector, wave impedance, reflection at a dielectric", ["poynting", "wave impedance", "intrinsic impedance"]),
        ("Inductance and capacitance of transmission lines and wires", ["two-wire", "inductance of", "partial inductance"]),
        ("Magnetic circuits: reluctance, flux, inductance of a coil", ["reluctance", "magnetic circuit", "inductance coil"]),
        ("Eddy-current and hysteresis losses", ["eddy", "hysteresis loss", "core loss", "steinmetz"]),
        ("Waveguide modes and cutoff", ["waveguide", "cutoff"]),
        ("Microstrip / coax impedance", ["microstrip", "characteristic impedance"]),
        ("DFT, windowing, filter design (FIR length, IIR)", ["window", "fir", "dft"]),
        ("Z-transform / digital filter response", ["z-transform", "digital filter", "iir"]),
        ("Bit error rate vs Eb/N0 for BPSK/QPSK", ["bit error rate", "ber", "bpsk", "qpsk"]),
        ("Error-correcting codes (Hamming, code rate, coding gain)", ["hamming", "code rate", "coding gain", "crc"]),
        ("Information entropy and channel capacity of discrete channels", ["entropy", "mutual information"]),
        ("Antenna array factor / beamwidth", ["array factor", "beamwidth"]),
        ("Optical link budget / fibre attenuation and dispersion", ["fibre attenuation", "dispersion", "fiber loss"]),
        ("Laser: threshold, gain, cavity modes", ["laser threshold", "cavity mode", "free spectral range"]),
        ("Photodetector: responsivity, noise, NEP", ["responsivity", "noise equivalent", "photodiode"]),
        ("Solar cell I–V, fill factor, efficiency", ["fill factor", "solar cell", "open-circuit voltage"]),
        ("LED: efficacy, luminous flux, junction temperature", ["efficacy", "luminous flux", "junction temperature"]),
        ("Power electronics: inverter, PWM harmonics, THD", ["inverter", "thd", "harmonic distortion", "pwm"]),
        ("Flyback / forward / buck-boost converters", ["flyback", "buck-boost", "forward converter"]),
        ("Thyristor / controlled rectifier firing angle", ["thyristor", "firing angle", "controlled rectifier"]),
        ("Grounding, touch and step voltage", ["touch voltage", "step voltage", "earthing", "grounding"]),
        ("Lightning protection / surge arrester", ["lightning", "arrester", "surge"]),
        ("Power quality: flicker, voltage sag", ["flicker", "voltage sag", "power quality"]),
        ("Sensors: thermocouple, strain (have), LVDT, capacitive", ["thermocouple", "lvdt", "capacitive sensor"]),
        ("Electrostatics: capacitor energy and force, method of images", ["method of images", "capacitor energy", "electrostatic force"]),
        ("Magnetostatics: Ampère's law, Biot–Savart, mutual inductance", ["mutual inductance", "ampere", "biot"]),
        ("Cross-talk and signal integrity", ["crosstalk", "signal integrity", "rise time"]),
        ("PCB trace width and current", ["trace width", "pcb"]),
        ("Electromagnetic compatibility / shielding effectiveness", ["shielding effectiveness", "emc"]),
    ],
    "Chemical and process engineering": [
        ("Flash calculation (Rachford–Rice) and bubble/dew point", ["rachford", "flash", "bubble point", "dew point"]),
        ("Raoult's and modified Raoult's law; relative volatility", ["raoult", "relative volatility"]),
        ("McCabe–Thiele, Fenske, Underwood, Gilliland", ["mccabe", "fenske", "underwood", "gilliland", "minimum reflux"]),
        ("Absorption and stripping (Kremser)", ["kremser", "absorption factor", "stripping"]),
        ("Humidification and cooling towers", ["cooling tower", "humidification", "merkel"]),
        ("Drying: constant and falling rate", ["drying rate", "drying time", "constant rate"]),
        ("Filtration (Ruth / cake) and centrifugation", ["cake filtration", "ruth", "centrifuge"]),
        ("Cyclone (Lapple) and settling chamber efficiency", ["cyclone", "lapple", "cut size"]),
        ("Fluidisation: minimum velocity and expansion", ["minimum fluidization", "minimum fluidisation", "fluidization", "fluidisation"]),
        ("Agitation: power number, mixing time", ["power number", "mixing time", "impeller"]),
        ("Residence time distribution", ["residence time distribution", "rtd", "tanks in series"]),
        ("Thiele modulus and effectiveness factor", ["thiele", "effectiveness factor"]),
        ("Damköhler number", ["damk", "damkohler"]),
        ("Adiabatic reactor and heat-of-reaction temperature rise", ["adiabatic reactor", "adiabatic temperature rise"]),
        ("Batch reactor design (time to conversion)", ["batch reactor"]),
        ("Catalyst deactivation", ["deactivation", "catalyst decay"]),
        ("Two-film theory and overall mass-transfer coefficient", ["two-film", "overall mass transfer", "film theory"]),
        ("Packed column height (HTU/NTU, HETP)", ["htu", "ntu mass", "hetp", "packed column"]),
        ("Pressure relief valve sizing (API 520)", ["relief valve", "api 520", "safety valve"]),
        ("Multistage compression and intercooling", ["multistage compress", "intercool"]),
        ("Fugacity and cubic equations of state (Peng–Robinson, SRK)", ["peng-robinson", "redlich", "fugacity", "soave"]),
        ("Activity coefficient models (Margules, Wilson, NRTL, van Laar)", ["margules", "wilson", "nrtl", "van laar"]),
        ("Heat of mixing, excess properties", ["heat of mixing", "excess"]),
        ("Process control tuning (Cohen–Coon, IMC)", ["cohen", "imc", "internal model"]),
        ("Capital cost scaling and economic indicators", ["six-tenths", "capital cost", "annuity", "payback"]),
        ("Pipe flow of non-Newtonian fluids (power law, Bingham)", ["power-law", "power law", "bingham", "non-newtonian"]),
        ("Two-phase flow: Lockhart–Martinelli, void fraction", ["lockhart", "void fraction", "two-phase"]),
        ("Pumps: NPSH (have), cavitation, power", ["cavitation"]),
        ("Gas–liquid mass transfer: kLa (have partly)", ["kla", "gas-liquid"]),
        ("Crystallisation: supersaturation, growth rate, population balance", ["crystallis", "crystalliz", "supersaturation", "population balance"]),
        ("Membrane separation: flux, rejection, osmotic pressure", ["membrane", "reverse osmosis", "rejection"]),
        ("Ion exchange and adsorption breakthrough curves", ["breakthrough", "ion exchange"]),
        ("Liquid–liquid extraction stages (Kremser for extraction)", ["extraction stage", "distribution coefficient"]),
        ("Evaporators: multiple effect economy", ["evaporator", "multiple effect"]),
        ("Heat exchangers: fouling, pressure drop (shell and tube, Kern, Bell–Delaware)", ["fouling", "kern", "shell-and-tube", "shell and tube"]),
        ("Pinch analysis / heat integration", ["pinch"]),
        ("Combustion kinetics / flame speed / adiabatic flame (have)", ["flame speed", "ignition"]),
        ("Safety: explosion (TNT equivalent), BLEVE, dispersion (Pasquill)", ["tnt equivalent", "bleve", "explosion", "pasquill"]),
        ("Safety: HAZOP / SIL / probability of failure on demand", ["pfd", "sil", "hazop", "layer of protection"]),
        ("Pneumatic conveying / slurry transport", ["slurry", "pneumatic conveying"]),
        ("Sedimentation thickener design (Kynch, Coe–Clevenger)", ["thickener", "kynch", "coe"]),
        ("Gas absorption into a reacting liquid (enhancement factor, Hatta)", ["hatta", "enhancement factor"]),
    ],
    "Materials, metallurgy and nano": [
        ("True stress and strain; necking; Ramberg–Osgood; Hollomon", ["true stress", "ramberg", "hollomon", "strain hardening"]),
        ("Larson–Miller creep parameter", ["larson"]),
        ("Nucleation and growth: Avrami (JMAK) kinetics", ["avrami", "jmak", "nucleation"]),
        ("Scheil solidification / segregation", ["scheil", "segregation"]),
        ("Orowan strengthening / dislocation density", ["orowan", "dislocation"]),
        ("Lamina stiffness and classical laminate theory (ABD)", ["laminate", "lamina", "abd"]),
        ("Thermal expansion mismatch and thermal stress", ["thermal stress", "thermal mismatch", "bimetal"]),
        ("Weibull statistics of strength", ["weibull"]),
        ("Hyperelasticity (neo-Hookean, Mooney–Rivlin)", ["neo-hookean", "mooney", "hyperelastic"]),
        ("Viscoelasticity: Maxwell, Kelvin–Voigt, standard linear solid; WLF", ["kelvin-voigt", "standard linear solid", "wlf", "maxwell model"]),
        ("Dielectric relaxation (Debye) and loss", ["dielectric loss", "debye relaxation", "loss tangent"]),
        ("Semiconductor: intrinsic carrier concentration, Fermi level, effective mass", ["intrinsic carrier", "fermi level", "effective mass"]),
        ("Schottky barrier and contacts", ["schottky"]),
        ("Magnetic materials: Curie–Weiss, hysteresis, saturation", ["curie", "hysteresis", "coercivity"]),
        ("Corrosion: Pourbaix, galvanic series, pitting resistance (PREN)", ["pourbaix", "galvanic", "pren", "pitting"]),
        ("Oxidation kinetics (parabolic rate, Pilling–Bedworth)", ["parabolic oxidation", "pilling", "oxidation rate"]),
        ("Phase diagrams: Gibbs phase rule (have), eutectic composition", ["eutectic", "phase rule"]),
        ("Diffusion: Kirkendall, interdiffusion, error-function solution (have)", ["interdiffusion", "kirkendall", "error function"]),
        ("Powder metallurgy: sintering, density", ["sintering", "green density"]),
        ("Ceramic: Weibull modulus, thermal shock parameter", ["thermal shock", "modulus of rupture"]),
        ("Hardness conversions and indentation (Vickers, Brinell, Knoop)", ["vickers", "brinell", "rockwell", "indentation"]),
        ("Impact: Charpy ductile–brittle transition", ["charpy", "ductile-brittle"]),
        ("Wear and friction (have Archard); coefficient of friction", ["adhesive wear", "coefficient of friction"]),
        ("Nano: Hamaker / van der Waals force, capillary force, Young–Laplace", ["hamaker", "van der waals force", "young-laplace"]),
        ("Nano: quantum dot size vs emission (have), surface-to-volume (have), Coulomb blockade (have)", ["emission wavelength", "particle size"]),
        ("Nano: Debye–Scherrer (have); AFM cantilever spring constant, resonance", ["afm", "cantilever spring"]),
        ("Thin films: stress (Stoney), deposition rate, thickness by interference", ["stoney", "deposition rate", "film stress"]),
        ("Composite: Halpin–Tsai (have), failure criteria (Tsai–Wu, max stress)", ["tsai-wu", "tsai-hill", "failure criterion"]),
        ("Sandwich panel stiffness and shear", ["sandwich"]),
        ("Fibre pull-out / critical fibre length", ["critical fibre length", "critical fiber length", "pull-out"]),
        ("Heat treatment: hardenability, tempering parameter (Hollomon–Jaffe), Jominy", ["jominy", "hardenability", "tempering"]),
        ("Grain growth kinetics", ["grain growth"]),
        ("Thermal conductivity of materials: Wiedemann–Franz (have), phonon, composites", ["effective thermal conductivity", "phonon"]),
        ("Porosity: Gibson–Ashby foams, density", ["gibson", "foam", "cellular"]),
        ("Electrical conductivity of alloys: Matthiessen, resistivity vs temperature", ["matthiessen", "resistivity"]),
        ("Piezoelectric and magnetostrictive constants", ["piezoelectric", "magnetostrictive"]),
    ],
    "Aerospace and space": [
        ("ISA stratosphere (isothermal layer) and altitude relations", ["stratosphere", "geopotential", "density altitude"]),
        ("Thin airfoil theory / lift slope / finite-wing correction", ["thin airfoil", "lift slope", "lift curve"]),
        ("Prandtl lifting-line theory / Oswald efficiency", ["lifting line", "oswald", "elliptical"]),
        ("Normal shock relations", ["normal shock"]),
        ("Oblique shock and θ–β–M", ["oblique shock", "wedge"]),
        ("Prandtl–Meyer expansion", ["prandtl-meyer", "expansion fan"]),
        ("Nozzle area–Mach relation and thrust coefficient", ["area ratio", "area-mach", "thrust coefficient"]),
        ("Vis-viva and orbital energy", ["vis-viva", "specific orbital energy"]),
        ("Bi-elliptic transfer / plane change", ["bi-elliptic", "plane change", "inclination change"]),
        ("Classical orbital elements, state vector conversion", ["orbital elements", "state vector", "true anomaly"]),
        ("J2 nodal regression, sun-synchronous orbit", ["j2", "sun-synchronous", "nodal regression"]),
        ("Gravity assist / sphere of influence", ["sphere of influence", "gravity assist", "patched conic"]),
        ("Atmospheric entry heating (Sutton–Graves), g-loads", ["sutton", "stagnation heating", "entry heating"]),
        ("Range and endurance of propeller aircraft", ["endurance", "propeller", "breguet propeller"]),
        ("Climb rate, ceiling, excess power", ["rate of climb", "climb", "ceiling", "excess power"]),
        ("Turn rate, load factor, V–n diagram", ["load factor", "turn rate", "v-n", "bank angle"]),
        ("Take-off and landing distance", ["takeoff", "take-off", "landing distance"]),
        ("Propeller momentum / actuator disk theory", ["actuator disk", "propeller momentum", "momentum theory"]),
        ("Turbojet/turbofan cycle thrust and TSFC", ["turbojet", "turbofan", "tsfc", "specific fuel consumption"]),
        ("Ramjet / scramjet", ["ramjet", "scramjet"]),
        ("Longitudinal static stability, neutral point, trim", ["neutral point", "static margin", "trim"]),
        ("Short-period and phugoid approximations", ["short period", "short-period", "phugoid"]),
        ("Wing structure: bending, torsion, shear flow", ["wing bending", "shear flow", "wing box"]),
        ("Skin-stringer panel buckling", ["stringer", "skin buckling"]),
        ("Rocket staging and delta-v budget (multi-stage)", ["staging", "multi-stage", "delta-v budget"]),
        ("Gravity turn / launch trajectory losses", ["gravity turn", "gravity loss"]),
        ("Rendezvous: Clohessy–Wiltshire / Hill's equations", ["clohessy", "hill's equations", "rendezvous"]),
        ("Attitude: Euler angles, quaternions, torque-free (have), gravity gradient", ["quaternion", "gravity gradient", "euler angles"]),
        ("Spacecraft thermal balance (equilibrium temperature)", ["spacecraft thermal", "equilibrium temperature"]),
        ("Link budget (have); Doppler shift; antenna pointing loss", ["doppler shift", "pointing loss"]),
        ("Radiation environment: dose behind shielding, total ionising dose", ["total ionising", "total ionizing", "shielding dose"]),
        ("Ground track and coverage swath, revisit time", ["ground track", "swath", "revisit", "coverage"]),
        ("Eclipse duration, beta angle", ["eclipse", "beta angle"]),
        ("Solar sail, tether, electric propulsion (Tsiolkovsky with Isp)", ["solar sail", "tether"]),
        ("Pressure vessel / tank mass for spacecraft", ["tank mass", "propellant tank"]),
        ("Helicopter rotor: momentum theory, figure of merit, tip speed", ["rotor", "figure of merit", "helicopter"]),
        ("Wind tunnel corrections / dynamic similarity", ["wind tunnel", "blockage"]),
        ("Flutter / aeroelastic divergence speed", ["flutter", "divergence"]),
    ],
    "Biomedical and health": [
        ("Two-compartment pharmacokinetics; multiple dosing; oral absorption (Bateman)", ["two-compartment", "multiple dose", "bateman", "oral absorption", "accumulation"]),
        ("Michaelis–Menten (saturable) pharmacokinetics", ["saturable", "phenytoin", "michaelis-menten elimination"]),
        ("Creatinine clearance (Cockcroft–Gault) and eGFR", ["cockcroft", "creatinine", "egfr", "glomerular"]),
        ("Body surface area and BMI; BMR (Harris–Benedict, Mifflin)", ["body surface area", "mosteller", "bmi", "basal metabolic"]),
        ("Fick principle: cardiac output, oxygen consumption", ["fick", "cardiac output"]),
        ("Pressure gradient across a stenosis (Bernoulli, Gorlin)", ["stenosis", "gorlin", "valve area"]),
        ("Poiseuille resistance of vessels, blood viscosity, Fåhræus–Lindqvist", ["vascular resistance", "blood viscosity", "poiseuille blood"]),
        ("Windkessel model of the arterial system", ["windkessel", "arterial compliance"]),
        ("Starling forces / capillary filtration", ["starling", "capillary filtration", "oncotic"]),
        ("Henderson–Hasselbalch acid–base (blood gas)", ["blood gas", "bicarbonate", "henderson"]),
        ("Alveolar gas equation, oxygen content, shunt fraction", ["alveolar", "oxygen content", "shunt"]),
        ("Lung mechanics: compliance, resistance, time constant", ["compliance", "airway resistance", "lung"]),
        ("Laplace law for vessels / alveoli / heart wall", ["laplace law", "wall tension", "law of laplace"]),
        ("Bioheat (Pennes) equation and thermal dose (CEM43)", ["pennes", "bioheat", "cem43", "thermal dose"]),
        ("Specific absorption rate (SAR) of RF exposure", ["sar", "specific absorption"]),
        ("Ultrasound: reflection, attenuation, Doppler blood velocity, mechanical index", ["doppler blood", "mechanical index", "ultrasound attenuation", "ultrasound"]),
        ("Hodgkin–Huxley and FitzHugh–Nagumo neuron", ["hodgkin", "fitzhugh", "action potential"]),
        ("Cable theory (have), Rall, membrane time constant", ["membrane time constant", "length constant"]),
        ("Bone mechanics: Wolff, stress shielding (have), fracture risk", ["bone", "wolff"]),
        ("Gait and joint mechanics: inverse dynamics of a limb", ["inverse dynamics", "gait", "ground reaction"]),
        ("Muscle: Hill force–velocity, length–tension", ["hill muscle", "force-velocity", "muscle"]),
        ("Radiation therapy: BED, linear-quadratic, TCP/NTCP", ["biologically effective", "linear-quadratic", "bed", "fractionation"]),
        ("Radiopharmaceuticals: effective half-life, MIRD dose", ["effective half-life", "mird", "biological half-life"]),
        ("Dialysis: clearance, urea kinetics (Kt/V)", ["dialysis", "kt/v", "urea"]),
        ("Epidemiology: SIR model, R0, doubling time, herd immunity", ["sir model", "basic reproduction", "r0", "herd immunity", "epidemic"]),
        ("Diagnostic statistics: sensitivity, specificity, likelihood ratio (have), ROC AUC", ["roc", "likelihood ratio", "auc"]),
        ("Population growth: logistic, Gompertz (tumour growth)", ["gompertz", "tumor growth", "tumour growth"]),
        ("Drug-receptor binding: Emax, Hill (have), Scatchard", ["emax", "scatchard", "dose-response", "receptor"]),
        ("Hemodynamics: mean arterial pressure, pulse pressure, Reynolds in arteries", ["mean arterial", "pulse pressure"]),
        ("Pulse wave velocity (Moens–Korteweg)", ["moens", "pulse wave velocity"]),
        ("Oxygen transport: Hill equation for haemoglobin, Bohr effect", ["haemoglobin", "hemoglobin", "oxygen dissociation", "bohr effect"]),
        ("Biomedical signals: ECG heart rate variability, QT correction (Bazett)", ["bazett", "qt", "heart rate variability"]),
        ("Cell culture: doubling time, growth rate, seeding", ["doubling time", "cell culture", "seeding"]),
        ("Tissue engineering: oxygen diffusion limit (have), Krogh cylinder", ["krogh"]),
        ("Biomaterials: degradation kinetics, drug release (Higuchi, Korsmeyer–Peppas)", ["higuchi", "korsmeyer", "degradation"]),
        ("Orthopaedic: fracture healing, screw pull-out", ["pull-out", "screw"]),
        ("Stent / vascular graft mechanics (Laplace, hoop stress)", ["stent", "graft"]),
        ("Hearing: loudness, dB SPL, audiometry; vision: acuity, accommodation", ["loudness", "accommodation", "visual acuity", "audiometry"]),
        ("Electrophysiology: Goldman (have), Nernst–Planck, Donnan equilibrium", ["donnan"]),
    ],
    "Agricultural, mining, petroleum and nuclear": [
        ("Green–Ampt / Horton infiltration", ["green-ampt", "horton", "infiltration"]),
        ("Crop yield–water production function (Stewart, FAO)", ["yield response", "water production function", "crop yield"]),
        ("Fertiliser rate / nutrient balance", ["fertili", "nutrient"]),
        ("Furrow irrigation, border irrigation advance", ["furrow", "border irrigation"]),
        ("Soil water: field capacity, available water, matric potential (van Genuchten)", ["van genuchten", "available water", "matric", "soil water"]),
        ("Pump and pipeline for irrigation: sprinkler lateral friction (Christiansen)", ["christiansen", "lateral"]),
        ("Grain bin aeration, drying equilibrium moisture (Henderson)", ["equilibrium moisture", "aeration"]),
        ("Livestock: heat production, feed conversion, water demand", ["feed conversion", "livestock"]),
        ("Havlena–Odeh / oil material balance", ["havlena", "oil material balance"]),
        ("Well testing: skin, Horner, wellbore storage", ["horner", "skin factor", "wellbore storage", "well test"]),
        ("Buckley–Leverett fractional flow", ["buckley", "fractional flow", "waterflood"]),
        ("Relative permeability (Corey) and capillary pressure (Leverett J)", ["corey", "relative permeability", "leverett", "capillary pressure"]),
        ("PVT correlations (Standing, Vasquez–Beggs), gas Z-factor", ["standing", "z-factor", "z factor", "bubble point pressure", "pvt"]),
        ("Gas pipeline flow (Weymouth, Panhandle)", ["weymouth", "panhandle", "gas pipeline"]),
        ("Multiphase pipe flow (Beggs–Brill, Hagedorn–Brown)", ["beggs", "hagedorn", "multiphase"]),
        ("Gas lift and ESP design, nodal analysis", ["gas lift", "esp", "nodal analysis"]),
        ("Hydraulic fracturing: PKN/KGD width, net pressure", ["pkn", "kgd", "hydraulic fractur"]),
        ("Drilling: torque and drag, bit hydraulics, kick tolerance", ["torque and drag", "bit hydraulics", "kick", "bit nozzle"]),
        ("Cementing: slurry volume, displacement", ["cement"]),
        ("Rock mechanics: Mohr–Coulomb, point load, RQD, RMR, Q-system", ["rqd", "rmr", "q-system", "point load", "rock mass rating"]),
        ("Blast fragmentation (Kuz–Ram), powder factor, ground vibration (PPV)", ["kuz", "powder factor", "ppv", "ground vibration"]),
        ("Haulage: cycle time (have), rolling resistance, grade", ["rolling resistance", "haul grade", "tyre"]),
        ("Slope stability: Bishop, circular failure", ["bishop", "circular failure", "wedge failure"]),
        ("Mineral processing: screening efficiency, hydrocyclone, jig, thickener", ["screening", "hydrocyclone", "screen efficiency"]),
        ("Mine ventilation: Atkinson (have), natural ventilation pressure", ["natural ventilation", "atkinson"]),
        ("Mine dewatering pumps / pit slope water", ["dewater"]),
        ("Nuclear: point reactor kinetics, delayed neutrons, period", ["point kinetics", "reactor period", "delayed neutron"]),
        ("Neutron diffusion: diffusion length, buckling, criticality of a bare reactor", ["diffusion length", "buckling", "criticality"]),
        ("Bateman decay chain (have), activation / saturation activity", ["activation", "saturation activity", "bateman"]),
        ("Xenon-135 poisoning", ["xenon"]),
        ("Thermal hydraulics: subchannel, DNBR, fuel centreline temperature", ["dnbr", "centreline", "centerline", "fuel temperature", "critical heat flux"]),
        ("Fission yield / energy release per fission", ["fission yield", "energy per fission"]),
        ("Gamma shielding buildup factor (have point source)", ["buildup"]),
        ("Neutron shielding / removal cross-section", ["removal cross", "neutron shield"]),
        ("Dosimetry: absorbed, equivalent, effective dose conversions, LET, quality factor", ["effective dose", "equivalent dose", "quality factor", "let"]),
        ("Criticality safety: k_eff of arrays, safe mass", ["safe mass", "criticality safety"]),
        ("Enrichment: separative work (have), cascade, tails", ["separative work", "swu", "cascade"]),
        ("Radioactive waste: repository heat, canister", ["repository", "canister"]),
    ],
    "Industrial, systems, computer, architectural": [
        ("M/M/c and Erlang C queue; M/G/1 (Pollaczek–Khinchine)", ["m/m/c", "erlang c", "m/g/1", "pollaczek"]),
        ("Weibull reliability and hazard rate; bathtub", ["weibull", "hazard rate", "bathtub"]),
        ("Maintenance: MTTR, preventive replacement, age replacement", ["mttr", "replacement", "preventive maintenance"]),
        ("Acceptance sampling and OC curve", ["acceptance sampling", "oc curve"]),
        ("Design of experiments / ANOVA / regression", ["anova", "factorial", "regression"]),
        ("Linear programming / transportation problem", ["linear program", "transportation problem", "simplex"]),
        ("Forecasting: moving average, exponential smoothing, MAPE", ["exponential smoothing", "forecast", "mape"]),
        ("Inventory with shortages / (s,S) / ABC", ["backorder", "shortage", "abc analysis"]),
        ("Line balancing and cycle time (have takt)", ["line balancing", "cycle time"]),
        ("Facility layout / material handling cost", ["layout", "material handling"]),
        ("Project crashing (time–cost trade-off)", ["crashing", "time-cost"]),
        ("Engineering economics: interest, annuity, IRR, depreciation, B/C", ["irr", "annuity", "depreciation", "present worth", "interest rate"]),
        ("Value at risk, expected monetary value, decision tree", ["expected monetary", "decision tree", "value of information"]),
        ("Fault tree and FMEA risk priority number", ["fault tree", "fmea", "rpn", "risk priority"]),
        ("Markov availability (repairable systems)", ["markov", "repairable"]),
        ("RAID reliability, replication factor, MTTDL", ["raid", "mttdl"]),
        ("Cache hit rate / memory hierarchy (have AMAT), Roofline model", ["roofline", "cache miss", "arithmetic intensity"]),
        ("Pipeline hazards and speedup", ["pipeline speedup", "branch penalty", "pipeline"]),
        ("Big-O / algorithm run time estimates; sorting; hashing load factor", ["load factor hash", "hash table", "big-o", "sorting"]),
        ("Huffman coding / compression ratio / entropy coding", ["huffman", "compression ratio"]),
        ("Bloom filter false-positive rate", ["bloom"]),
        ("CAP/consensus: Paxos/Raft quorum, availability of replicated systems", ["quorum", "replication", "raft"]),
        ("Queueing for web servers: Little (have), utilisation law, response time", ["utilisation law", "utilization law", "response time"]),
        ("Network: BER and packet error, ARQ throughput, CSMA, Aloha", ["aloha", "csma", "arq", "stop-and-wait", "sliding window"]),
        ("Machine learning: bias–variance, learning curves, precision/recall (have), F1", ["f1", "bias-variance", "cross-validation", "gradient descent"]),
        ("Information retrieval: TF-IDF (have), PageRank", ["pagerank"]),
        ("Cryptography: RSA key sizes, birthday bound (have), entropy of keys, DH", ["rsa", "key size", "diffie"]),
        ("Daylight factor and daylighting", ["daylight factor", "daylight"]),
        ("Thermal comfort: PMV/PPD, operative temperature", ["pmv", "ppd", "thermal comfort", "operative temperature"]),
        ("Dew point and condensation risk in walls (Glaser)", ["glaser", "condensation risk", "dew point wall", "vapour"]),
        ("Egress: evacuation time, stair flow, fire resistance rating", ["egress", "evacuation", "fire resistance"]),
        ("Solar geometry: sun position, shading, solar angles", ["sun position", "solar altitude", "solar angle", "declination"]),
        ("HVAC: heating and cooling load, duct sizing, equal friction", ["duct sizing", "cooling load", "heating load", "equal friction"]),
        ("Building energy: degree-days, annual heating demand", ["degree-day", "degree day", "heating demand"]),
        ("Structural preliminary sizing (span-to-depth ratios), floor vibration", ["span-to-depth", "floor vibration", "span to depth"]),
        ("Acoustics: STC, NRC, flanking, speech intelligibility", ["stc", "nrc", "speech intelligibility", "noise criteria"]),
        ("Lifts / elevator traffic: round-trip time, handling capacity", ["elevator", "lift traffic", "round trip time"]),
        ("Plumbing: drainage fixture units, pipe sizing, hot-water demand", ["fixture unit", "plumbing", "drainage"]),
        ("Fire: smoke control, sprinkler water demand (have), egress width", ["smoke", "zone model"]),
    ],
    "Physics": [
        ("Wien displacement and Stefan–Boltzmann (blackbody)", ["wien", "stefan"]),
        ("Maxwell's equations: Poynting vector and energy density", ["poynting", "energy density"]),
        ("Lens maker's equation; compound lens systems; ray-transfer (ABCD) matrices", ["lens maker", "lensmaker", "ray transfer", "abcd matrix", "matrix optics"]),
        ("Rayleigh and Abbe diffraction limits", ["rayleigh criterion", "abbe", "resolving power"]),
        ("Optical resonators and Fabry–Pérot", ["fabry", "resonator", "finesse"]),
        ("Interference of N sources; coherence length", ["coherence", "n-slit"]),
        ("Fermi's golden rule; perturbation theory", ["golden rule", "perturbation", "first-order energy"]),
        ("Variational method", ["variational"]),
        ("WKB approximation", ["wkb"]),
        ("Scattering: Born approximation, partial waves, cross section of a potential", ["born approximation", "partial wave"]),
        ("Spin-½, Pauli matrices, Bloch sphere; density matrix", ["pauli", "bloch sphere", "density matrix", "spin-1/2", "spin one-half"]),
        ("Clebsch–Gordan / angular momentum addition", ["clebsch", "angular momentum addition"]),
        ("Lorentz transformation and velocity addition", ["lorentz transformation", "velocity addition"]),
        ("Relativistic energy–momentum, collisions, decay (have)", ["relativistic energy", "energy-momentum"]),
        ("Geodesics / precession of Mercury / Shapiro delay", ["precession of", "perihelion", "shapiro"]),
        ("Vorticity, circulation, potential flow (Kutta–Joukowski)", ["vorticity", "circulation", "kutta", "potential flow"]),
        ("Boundary layer / Navier–Stokes exact solutions (Couette, Poiseuille have)", ["couette", "stokes flow"]),
        ("Rayleigh–Bénard / Rayleigh–Taylor / Kelvin–Helmholtz instabilities", ["rayleigh-benard", "rayleigh-taylor", "kelvin-helmholtz", "instability"]),
        ("Capillary waves, dispersion relations (have water waves)", ["capillary wave", "dispersion relation", "group velocity"]),
        ("Maxwell relations, Gibbs–Duhem, thermodynamic potentials", ["maxwell relation", "gibbs-duhem", "thermodynamic potential", "helmholtz free energy"]),
        ("Clausius inequality, third law, chemical potential", ["chemical potential", "third law"]),
        ("Van der Pol oscillator; limit cycle", ["van der pol", "limit cycle"]),
        ("Lotka–Volterra and predator–prey; Rössler", ["lotka", "predator", "rossler", "rössler"]),
        ("Lyapunov exponent", ["lyapunov"]),
        ("BCS gap, London penetration depth, Josephson relations", ["bcs", "london", "josephson", "coherence length"]),
        ("Kronig–Penney and tight-binding bands; Brillouin zone", ["kronig", "tight-binding", "tight binding", "brillouin"]),
        ("Semiconductor transport: diffusion length, continuity, mobility", ["diffusion length", "continuity equation", "minority carrier"]),
        ("MOS capacitor and threshold voltage", ["mos capacitor", "threshold voltage"]),
        ("Magnetism: Curie–Weiss, Heisenberg exchange, Brillouin function (have paramagnet)", ["curie-weiss", "brillouin function", "exchange"]),
        ("Gravitational: Newton shell theorem, potential of a sphere, escape (have)", ["shell theorem", "gravitational potential"]),
        ("Orbital perturbations; three-body Lagrange points", ["lagrange point", "three-body"]),
        ("Electromagnetic radiation: dipole radiation pattern, Thomson/Rayleigh scattering, Cherenkov", ["cherenkov", "thomson scattering", "rayleigh scattering", "bremsstrahlung"]),
        ("Magnetohydrodynamics: Hartmann number, magnetic Reynolds number", ["hartmann", "magnetic reynolds", "mhd"]),
        ("Plasma: Debye length, plasma frequency (have), gyrofrequency, drift velocities", ["debye length", "gyrofrequency", "drift", "larmor radius"]),
        ("Atomic physics: Rydberg formula, fine structure (have), Lamb shift, selection rules", ["rydberg", "selection rule", "lamb shift"]),
        ("Molecular physics: rotational, vibrational (have); Franck–Condon, Morse potential", ["morse", "franck-condon"]),
        ("Nuclear: liquid-drop / semi-empirical mass formula (have binding), shell model, alpha decay Geiger–Nuttall, beta spectrum", ["geiger", "semi-empirical", "alpha decay", "gamow"]),
        ("Particle physics: Mandelstam variables, cross sections, luminosity", ["mandelstam", "luminosity", "rapidity"]),
        ("Cosmology: redshift–distance (have ΛCDM), CMB temperature, big-bang nucleosynthesis, inflation", ["cmb", "nucleosynthesis", "recombination", "horizon"]),
        ("Astrophysics: Eddington luminosity, virial theorem, Kelvin–Helmholtz time, accretion", ["eddington", "virial", "accretion", "bondi"]),
        ("Dimensional analysis: Buckingham π, similarity numbers", ["buckingham", "similarity", "dimensionless number"]),
        ("Error analysis, Gaussian/Poisson/binomial distributions, chi-square", ["poisson distribution", "binomial", "chi-square", "chi square", "gaussian distribution"]),
        ("Rotational mechanics: moment of inertia theorems, parallel/perpendicular axis (have shapes)", ["parallel axis", "perpendicular axis"]),
        ("Elasticity: Hooke's law tensors, Young's, shear and bulk moduli relations, Poisson's ratio", ["poisson's ratio", "bulk modulus", "elastic constants", "shear modulus"]),
        ("Waves: dispersion, phase/group velocity, reflection and transmission at a boundary (strings)", ["phase velocity", "group velocity", "transmission coefficient"]),
        ("Acoustics: Mach cone, shock waves, ultrasonic attenuation, radiation impedance", ["mach cone", "radiation impedance", "ultrasonic"]),
        ("Thermal physics: diffusion equation solutions, thermal conductivity of gases (have), heat kernel", ["heat kernel", "diffusion equation", "random walk"]),
        ("Fluids: Reynolds transport, Euler equation, Bernoulli (have), Stokes law (have), Prandtl number", ["prandtl number", "euler equation", "peclet", "reynolds transport"]),
        ("Surface physics: contact angle, Young equation, capillary rise (have Kelvin), Marangoni", ["young equation", "capillary rise", "marangoni", "laplace pressure"]),
        ("Electrochemistry-physics: Nernst–Planck, Debye–Hückel (have), Gouy–Chapman (have)", ["nernst-planck"]),
    ],
    "Chemistry": [
        ("Hess's law and enthalpy of formation", ["hess", "enthalpy of formation", "formation enthalpy"]),
        ("Le Chatelier / van 't Hoff equation for K(T)", ["van't hoff", "van 't hoff", "le chatelier"]),
        ("Kohlrausch law, ionic mobility, transport numbers", ["kohlrausch", "transport number", "ionic mobility", "molar conductivity"]),
        ("Rydberg and hydrogen spectral series", ["rydberg", "balmer", "lyman"]),
        ("NMR chemical shift and n+1 splitting; Karplus equation", ["karplus", "chemical shift", "spin-spin", "coupling constant"]),
        ("UV–vis: Woodward–Fieser, extinction coefficient (Beer–Lambert have)", ["woodward", "extinction coefficient", "molar absorptivity"]),
        ("Freundlich and BET isotherms", ["freundlich", "bet"]),
        ("Debye–Hückel (have), Pitzer, mean ionic activity coefficient", ["pitzer", "mean ionic"]),
        ("Born–Oppenheimer, Franck–Condon, term symbols, Hund's rules", ["term symbol", "hund"]),
        ("Electronegativity (Pauling, Mulliken); formal charge; bond order", ["electronegativity", "formal charge", "pauling"]),
        ("Madelung constant / Kapustinskii equation", ["madelung", "kapustinskii"]),
        ("Rate laws: pseudo-first-order, steady-state, pre-equilibrium approximations", ["steady-state approximation", "pre-equilibrium", "pseudo-first", "rate-determining"]),
        ("Michaelis–Menten (have), Lineweaver–Burk, Eadie–Hofstee", ["lineweaver", "eadie", "hanes"]),
        ("Oscillating reactions: Lotka, Brusselator, autocatalysis", ["brusselator", "autocatalysis", "oscillating reaction"]),
        ("Chain reactions and explosion limits", ["chain reaction", "explosion limit", "branching"]),
        ("Transition-state theory with tunnelling (have Wigner); RRKM", ["rrkm"]),
        ("Gas kinetic theory: collision frequency, mean free path, effusion", ["mean free path", "collision frequency", "effusion"]),
        ("Phase equilibria: Gibbs–Duhem, Clausius–Clapeyron (have), azeotropes, partial molar volumes", ["azeotrope", "partial molar", "gibbs-duhem"]),
        ("Osmotic pressure (van 't Hoff), osmolarity", ["osmotic pressure", "osmolarity"]),
        ("Electrode potentials: Latimer diagrams, Frost, Pourbaix; Nernst (have)", ["latimer", "frost diagram", "pourbaix"]),
        ("Electrolysis: Faraday (have), current efficiency; electroplating (have)", ["current efficiency"]),
        ("Acid–base: polyprotic distribution, ampholyte, titration curves (have), indicator", ["ampholyte", "indicator", "alpha fraction", "distribution diagram"]),
        ("Complexation: stepwise formation constants (have), chelate effect, EDTA titration", ["edta", "chelate", "stability constant"]),
        ("Solubility: common-ion effect (have Ksp), amphoteric, salting out", ["common-ion", "common ion", "salting"]),
        ("Gas laws: compressibility factor (have virial), partial pressures (have), real gas fugacity", ["compressibility factor"]),
        ("Thermochemistry: bomb calorimetry, heat capacity ratio, Kirchhoff's law", ["kirchhoff", "bomb calorimeter", "heat capacity ratio"]),
        ("Statistical thermodynamics: partition functions (have), equilibrium constant from Q, heat capacity of diatomics", ["equilibrium constant from partition", "einstein function"]),
        ("Quantum chemistry: particle on a ring/sphere, rigid rotor, Morse potential, helium", ["particle on a ring", "rigid rotor", "morse", "variational helium"]),
        ("Molecular orbital theory: bond order (have), HOMO–LUMO gap, Hückel (have)", ["homo", "lumo"]),
        ("Crystallography: unit cells, density, Bragg (have), packing fraction, Miller indices", ["packing fraction", "miller", "unit cell", "crystal density"]),
        ("Organic: pKa and Henderson–Hasselbalch for drugs (have partly), Taft equation, LFER", ["taft", "linear free energy", "swain-scott"]),
        ("Organic: Beer–Lambert (have), IR frequency from force constant (have), mass-spec isotope patterns", ["isotope pattern", "m+1", "nitrogen rule"]),
        ("Polymer: Carothers (have), Flory–Stockmayer gelation, Fox equation, WLF", ["gelation", "gel point", "fox equation", "wlf", "flory-stockmayer"]),
        ("Colloids: DLVO, Stokes sedimentation (have), Debye length, zeta potential (have), Hamaker", ["dlvo", "hamaker", "sedimentation"]),
        ("Surface: Gibbs adsorption isotherm, contact angle (have), spreading coefficient", ["spreading coefficient", "gibbs adsorption"]),
        ("Electrochemical impedance: Randles circuit, Warburg", ["randles", "warburg", "impedance"]),
        ("Environmental chemistry: Henry (have), octanol–water partition, bioconcentration, hydrolysis half-life", ["octanol", "bioconcentration", "kow", "hydrolysis"]),
        ("Atmospheric: photolysis (have), OH reaction lifetime, ozone depletion, aerosol growth", ["oh radical", "aerosol", "ozone depletion", "photostationary"]),
        ("Analytical: limit of detection, signal-to-noise, resolution (have chromatography), ICP, titration error", ["limit of detection", "signal-to-noise", "detection limit", "lod"]),
        ("Isotope chemistry: radioactive decay (have), isotope fractionation, kinetic isotope (have)", ["fractionation", "delta notation"]),
        ("Green chemistry metrics: atom economy, E-factor (have partly), process mass intensity", ["atom economy", "e-factor", "mass intensity"]),
        ("Biochemistry: Henderson–Hasselbalch (have), Gibbs of ATP (have), Hill (have), protein folding (have), Scatchard", ["scatchard", "dixon", "gibbs of binding", "nernst of membrane"]),
        ("Thermodynamics of mixing: ideal solutions (have), Flory–Huggins (have), regular solution (have), Gibbs of mixing", ["gibbs energy of mixing", "entropy of mixing"]),
    ],
    "Emerging fields": [
        ("Quantum computing: Bloch rotations, gate unitaries, VQE energy, quantum volume", ["bloch", "unitary", "vqe", "quantum volume", "gate"]),
        ("Quantum communication: teleportation fidelity, entanglement swapping, Bell/CHSH value", ["chsh", "teleportation", "bell inequality", "entanglement"]),
        ("Machine learning: loss functions, backprop FLOPs (have training compute), batch size/learning-rate scaling", ["cross-entropy", "backpropagation", "scaling law", "chinchilla"]),
        ("Reinforcement learning: Bellman equation, discounted return, policy gradient", ["bellman", "discounted return", "policy gradient"]),
        ("Robotics: forward/inverse kinematics (have 2-link), Jacobian, DH parameters, dynamics", ["jacobian", "denavit", "inverse kinematics", "dh parameters"]),
        ("Robotics: PID/trajectory (have), path planning cost, SLAM covariance, Kalman filter", ["kalman", "particle filter", "covariance", "slam"]),
        ("Cybersecurity: key entropy (have), risk matrices, CVSS (have), attack tree probability", ["attack tree", "risk matrix", "exploit probability"]),
        ("Data engineering: sharding, replication, compression, CAP; Zipf's law", ["zipf", "sharding", "consistent hashing"]),
        ("Nanotech: nanoparticle plasmon (Mie), diffusion (have), Brownian (have), Coulomb blockade (have)", ["mie", "plasmon", "mie scattering"]),
        ("Synthetic biology: Hill (have), toggle switch, repressilator, growth-rate dependence, codon usage", ["toggle switch", "repressilator", "codon"]),
        ("Climate: energy balance (have forcing), Planck feedback, ice-albedo, carbon cycle box model, sea-level rise", ["ice-albedo", "carbon cycle", "sea level", "climate sensitivity", "planck feedback"]),
        ("Smart cities: traffic flow (have), digital twin (have), demand response, microgrid", ["demand response", "carsharing", "bus headway"]),
        ("Neuro: Hodgkin–Huxley, LIF (have), Izhikevich, synaptic models, EEG forward problem", ["izhikevich", "synaptic", "eeg", "fitzhugh"]),
        ("Energy: PV (have), wind (have), battery degradation, LCOE (have), capacity factor, heat pump, pumped hydro", ["pumped hydro", "capacity factor", "battery degradation", "compressed air", "geothermal"]),
        ("Hydrogen: electrolyser (have), fuel cell (have), storage density, compression work, Joule–Thomson", ["hydrogen storage", "compression work", "boil-off"]),
        ("Health informatics: queueing for clinics, sensitivity (have), survival analysis (Kaplan–Meier)", ["kaplan", "survival", "hazard ratio"]),
        ("Additive manufacturing: laser energy density (have), layer time, thermal gradient, porosity, residual stress", ["energy density", "layer time", "lack of fusion", "keyhole"]),
        ("Space: debris (have), solar sail, tether, orbital lifetime (have), radiation shielding, life support", ["life support", "oxygen consumption", "radiation shielding"]),
        ("Metamaterials: effective index (have), photonic crystal band edge, transformation optics, cloak", ["photonic crystal", "bragg stack", "cloak", "negative refraction", "transformation optics"]),
        ("Green: embodied energy, carbon payback, circularity (have), water footprint", ["embodied", "carbon payback", "water footprint", "energy payback"]),
        ("Soft robotics: pneumatic actuators (have), hyperelastic, bending of a bilayer, gripper force", ["bilayer", "gripper", "hyperelastic"]),
        ("Holography: fringe spacing (have), diffraction efficiency, Kogelnik coupled-wave", ["kogelnik", "diffraction efficiency", "coupled-wave"]),
    ],
}


# ---- the reviewed verdicts -------------------------------------------------------------------------------------------------
# A keyword hit is only a candidate: ‘johnson’ found a noise calculation, ‘affinity’ a biosensor, ‘pile’ a wave-force one. Every hit was read
# (2026-10-30) and the topic below is *covered* only when a calculation of that name really does the job. A topic that is neither listed here
# nor missing from the search is a spurious hit and counts as a gap.

COVERED = (
    "Darcy–Weisbach with Colebrook", "Traffic signal timing", "Superelevation and side", "Solids retention time", "Chlorine contact time",
    "Compressor and turbine efficiency", "Brayton and combined cycles", "Taylor tool life", "Machining: surface finish", "Fatigue: Miner",
    "Hydrodynamic bearing", "Heat sink / extended", "Smith chart", "Friis transmission formula", "Differential amplifier", "Maxwell: Poynting",
    "Waveguide modes", "Photodetector: responsivity", "Magnetostatics: Ampère", "Electrostatics: capacitor energy", "Raoult's and modified",
    "Pumps: NPSH", "Gas–liquid mass transfer", "Liquid–liquid extraction stages", "Weibull statistics of strength", "Hyperelasticity",
    "Semiconductor: intrinsic", "Phase diagrams: Gibbs", "Diffusion: Kirkendall", "Nano: quantum dot", "Fibre pull-out", "Piezoelectric",
    "Prandtl lifting-line", "Vis-viva", "Cable theory (have)", "Cell culture: doubling", "Biomaterials: degradation", "Mine ventilation: Atkinson",
    "Enrichment: separative", "Line balancing", "CAP/consensus", "Queueing for web servers", "Machine learning: bias", "Wien displacement",
    "Maxwell's equations: Poynting", "Lens maker", "Rayleigh and Abbe", "Variational method", "Lorentz transformation", "Relativistic energy",
    "BCS gap", "Plasma: Debye length", "Atomic physics: Rydberg", "Molecular physics", "Nuclear: liquid-drop", "Capillary waves, dispersion",
    "Rotational mechanics", "Waves: dispersion, phase", "Thermal physics: diffusion", "Surface physics", "Hess's law", "Le Chatelier", "Kohlrausch",
    "Rydberg and hydrogen", "Osmotic pressure", "Crystallography", "Organic: pKa", "Organic: Beer", "Surface: Gibbs adsorption", "Atmospheric: photolysis",
    "Green chemistry metrics", "Thermodynamics of mixing", "Gas kinetic theory", "Molecular orbital theory", "Reinforcement learning", "Metamaterials",
    "Green: embodied", "Soft robotics", "Holography", "Lorentz", "Electrolysis: Faraday", "Statistical thermodynamics", "Gas laws: compressibility",
    "Debye–Hückel (have)", "Michaelis–Menten (have)", "Phase equilibria", "Complexation", "Acid–base", "Solubility: common-ion",
    "Thermochemistry", "Chain reactions", "Quantum chemistry: particle", "Electrode potentials", "Rate laws", "UV–vis",
)

# topic prefix -> what the library has of it
PARTIAL = {
    "Flood frequency": "return period, design life and exceedance risk; no Gumbel or log-Pearson fit",
    "Theis well function": "Cooper–Jacob (the large-time approximation); no well function W(u)",
    "Evapotranspiration": "crop water requirement from a given ET₀; no Penman–Monteith, Hargreaves or Thornthwaite for ET₀",
    "Critical path method": "PERT duration and completion probability; no forward and backward pass",
    "BOD kinetics": "inside Streeter–Phelps; no stand-alone BOD exertion L₀(1−e^−kt)",
    "Section properties of composite": "parallel-axis theorem and standard shapes (physics); no composite or T-section",
    "Mohr–Coulomb shear": "Hoek–Brown rock-mass strength; no soil Mohr–Coulomb or triaxial",
    "Truss member forces": "1-D bar finite elements; no truss joint or section analysis",
    "Thermal resistance network": "three-layer wall U-value; no cylinder, sphere or network",
    "Bolted joint stiffness": "bolt tightening torque only",
    "Flywheel energy": "torque on a flywheel (rotational dynamics); no energy storage or speed fluctuation",
    "Pipe fittings": "friction-factor pipe flow; no minor-loss K or equivalent-length calculation",
    "Induction motor equivalent": "speed, slip and torque; no equivalent circuit",
    "Transmission line: ABCD": "line power transfer; no ABCD, lumped models or input impedance",
    "Antenna: dipole": "free-space link budget with given gains; no directivity, aperture or pattern",
    "Thermal noise kTB": "electrode thermal noise only",
    "MOSFET small-signal": "square-law drain current; no gm, ro or amplifier gain",
    "Battery: state of charge": "EV range and charging; no Peukert or state-of-charge model",
    "Motor starting": "permanent-magnet DC motor operating point; no series or shunt motor",
    "Magnetic circuits": "C-core electromagnet gap flux and pull; no general reluctance circuit",
    "DFT, windowing": "sampling, FFT resolution and aliasing; no window functions or FIR/IIR design",
    "Information entropy": "Shannon–Hartley capacity, binary entropy, password entropy; no discrete-channel capacity",
    "Optical link budget": "fibre NA and V-number; no attenuation or dispersion budget",
    "LED: efficacy": "photometry (flux, efficacy); no junction temperature",
    "Fugacity and cubic": "van der Waals, virial and critical-constant equations of state; no Peng–Robinson or SRK",
    "Heat exchangers: fouling": "LMTD duty and ε–NTU; no fouling, Kern or Bell–Delaware",
    "Thermal expansion mismatch": "mirror thermal mismatch only; no bimetal or coating stress",
    "Viscoelasticity": "Maxwell stress relaxation and polymer creep; no Kelvin–Voigt, standard linear solid or WLF",
    "Dielectric relaxation": "dielectric capacitor loss; no Debye relaxation",
    "Nano: Hamaker": "Lennard-Jones potential; no Hamaker, capillary or Young–Laplace force",
    "Thermal conductivity of materials": "Wiedemann–Franz and solid heat capacity; no phonon or effective-medium conductivity",
    "Classical orbital elements": "Kepler's equation; no element ↔ state-vector conversion",
    "Radiation environment": "gamma point-source dose with shielding; no space dose-depth",
    "Link budget (have)": "Doppler shift in the mobile-radio calculation; no pointing loss",
    "Ultrasound": "acoustic impedance, reflection and transmission; no attenuation, Doppler velocity or mechanical index",
    "Henderson–Hasselbalch acid–base": "general buffer equation; no blood-gas form",
    "Hodgkin–Huxley": "Nernst and Goldman potentials; no ion-channel dynamics",
    "Poiseuille resistance": "Hagen–Poiseuille flow; no vascular resistance or blood viscosity",
    "Bone mechanics": "implant–bone load sharing; no Wolff's law or fracture risk",
    "Gait and joint": "prosthesis stride energy; no inverse dynamics",
    "Diagnostic statistics": "diagnostic test and confusion-matrix metrics; no ROC AUC",
    "Oxygen transport": "Hill equation for oxygen delivery; no Bohr effect",
    "Hearing": "sound level and intensity; no loudness or audiometry",
    "Biomaterials: degradation": "resorbable implant mass loss; Higuchi not separate",
    "Blast fragmentation": "Konya bench blast design; no Kuz–Ram or ground vibration",
    "Haulage": "vehicle road load and power; no mine haul grade resistance",
    "Dosimetry": "committed effective dose from ingestion; no external dose conversion or quality factors",
    "Radioactive waste": "decay heat and radionuclide migration; no repository thermal model",
    "Maintenance": "MTBF and availability; no replacement policy",
    "Acoustics: STC": "single-leaf wall mass-law transmission loss; no STC, NRC or flanking",
    "M/M/c and Erlang C": "Erlang B blocking and M/M/1; no Erlang C or M/G/1",
    "Flash calculation": "bubble-point of an ideal binary solution; no Rachford–Rice flash",
    "Diagnostic": "",
    "Magnetism: Curie–Weiss": "Brillouin-function paramagnet; no Curie–Weiss or exchange",
    "Particle physics: Mandelstam": "centre-of-mass energy; no Mandelstam variables or luminosity",
    "Cosmology: redshift": "flat ΛCDM and photon gas; no CMB temperature history or nucleosynthesis",
    "Gravitational: Newton shell": "moments of inertia (physics); no shell theorem or sphere potential",
    "Lyapunov": "",
    "Nuclear": "",
    "NMR chemical shift": "NMR Larmor frequency, shift and multiplicity; no Karplus equation",
    "Freundlich and BET": "BET isotherm; no Freundlich",
    "Electronegativity": "bond polarity and percent ionic character; no Pauling or Mulliken scale",
    "Madelung constant": "Born–Landé lattice energy; no Kapustinskii",
    "Colloids: DLVO": "electrical double layer; no DLVO energy barrier",
    "Electrochemical impedance": "cyclic voltammetry (Randles–Ševčík); no impedance or Warburg",
    "Analytical: limit of detection": "nano-biosensor detection limit; no general LOD from calibration",
    "Quantum computing": "",
    "Machine learning: loss": "language-model loss; no general loss functions or scaling laws",
    "Synthetic biology": "Hill-function regulation; no toggle switch or repressilator",
    "Energy: PV": "wind annual energy; no capacity factor model, degradation or storage",
    "Hydrogen": "electrolyser and fuel cell; no storage or compression work",
    "Space: debris": "gamma shielding dose; no solar sail, tether or life support",
    "Cryptography": "",
    "Maintenance: MTTR": "",
}
PARTIAL.update({
    # found by re-reading every gap with a loose search: something related exists
    "Nodal and mesh analysis": "three-node resistor network by nodal analysis; no general matrix nodal or mesh analysis",
    "Chézy and Manning": "Manning's equation; no Chézy or compound sections",
    "Wear and friction": "Archard wear, friction on inclines and belt friction; no general friction-coefficient or wear-map calculation",
    "Steam properties": "saturation temperature from steam-table data; no quality, throttling or superheat properties",
    "Electrical conductivity of alloys": "resistivity versus temperature; no Matthiessen's rule",
    "Microstrip / coax impedance": "coaxial line; no microstrip",
    "Inductance and capacitance of transmission lines": "coaxial line and long solenoid; no two-wire or partial inductance",
    "Cache hit rate": "average memory access time; no roofline model",
    "Rock mechanics": "Hoek–Brown rock-mass strength; no RQD, RMR, Q or point-load index",
    "Slope stability: Bishop": "planar slope failure; no circular or wedge failure",
    "Cryptography: RSA": "hash collision (birthday) bound; no RSA or key-size calculation",
    "Bateman decay chain": "parent–daughter decay chain; no activation or saturation activity",
    "Climate: energy balance": "radiative forcing and equilibrium warming; no feedbacks, carbon cycle or sea level",
    "Robotics: forward/inverse kinematics": "two-link planar arm; no general Jacobian or DH parameters",
    "Neuro: Hodgkin": "leaky integrate-and-fire neuron; no Hodgkin–Huxley, Izhikevich or synapse models",
    "Biochemistry: Henderson": "buffers, ATP hydrolysis, Hill binding and protein unfolding; no Scatchard or Dixon plots",
    "Environmental chemistry: Henry": "Henry's law gas solubility; no octanol–water partitioning or bioconcentration",
    "Nanotech: nanoparticle plasmon": "Brownian motion and nanoparticle diffusion; no Mie or plasmon resonance",
    "Health informatics": "sensitivity and predictive values; no queueing for clinics or survival analysis",
    "Additive manufacturing": "powder-bed fusion energy density and melt pool; no layer time, porosity or thermal gradient",
    "Nano: Debye–Scherrer": "XRD Scherrer crystallite size; no AFM cantilever calculation",
    "Composite: Halpin–Tsai": "Halpin–Tsai and rule of mixtures; no Tsai–Wu or maximum-stress failure criterion",
    "Combustion kinetics": "adiabatic flame temperature; no flame speed or ignition",
    "Tissue engineering": "scaffold oxygen-limited thickness; no Krogh cylinder",
    "Electrophysiology": "Nernst and Goldman potentials; no Donnan equilibrium",
    "Sensors: thermocouple": "strain-gauge bridge and platinum RTD; no thermocouple, LVDT or capacitive sensor",
    "Transition-state theory": "Wigner tunnelling correction and Lindemann–Hinshelwood; no RRKM",
    "Isotope chemistry": "radioactive decay and the primary kinetic isotope effect; no isotope fractionation",
    "Michaelis–Menten (have)": "Michaelis–Menten with inhibition; no Lineweaver–Burk or Eadie–Hofstee linearisation",
    "Electrode potentials": "Nernst and standard cell potentials; no Latimer, Frost or Pourbaix diagrams",
    "Debye–Hückel (have)": "Debye–Hückel in ionic strength and activity coefficients; no Pitzer or mean ionic activity coefficient",
    "Statistical thermodynamics": "molecular partition functions (rotation, vibration); no equilibrium constant from Q or Einstein function",
    "Gas laws: compressibility": "virial equation and van der Waals; no generalised compressibility chart",
    "Phase equilibria": "Gibbs phase rule, Clausius–Clapeyron and the lever rule; no azeotropes or partial molar properties",
    "Complexation": "1:1 metal–ligand complex formation; no EDTA titration or chelate effect",
    "Solubility: common-ion": "solubility product and molar solubility; no amphoteric solubility or salting out",
    "Thermochemistry": "calorimetry and reaction enthalpies; no Kirchhoff's law or bomb calorimetry",
    "Rate laws": "integrated rate laws, initial rates, consecutive and parallel reactions; no steady-state or pre-equilibrium approximation",
    "Quantum chemistry: particle": "rotational spectrum and free-electron box model; no particle on a ring or sphere",
    "UV–vis": "Beer–Lambert and two-component absorbance; no Woodward–Fieser rules",
    "Polymer: Carothers": "Carothers, Flory–Fox and Fox glass transition; no gel point (Flory–Stockmayer)",
    "Plume rise": "Gaussian plume ground-level concentration; no Briggs plume rise",
    "Pump affinity laws, system curve": "pump operating point from a pump curve; no affinity laws or pumps in series and parallel",
    "Gear tooth bending": "gear pair speed and torque; no tooth stress",
    "Radiation environment": "gamma point-source dose with shielding; no space dose-depth",
    "Economics": "",
})
PARTIAL = {k: v for k, v in PARTIAL.items() if v}


def status(topic: str, hit) -> tuple[str, str]:
    """("covered" | "partial" | "gap", note)."""
    for k, note in PARTIAL.items():
        if topic.startswith(k):
            return "partial", note
    if hit is not None and any(topic.startswith(k) for k in COVERED):
        return "covered", ""
    return "gap", ""


def _haystack(c) -> str:
    """Name, id, tags and equation titles (not the long description, which matches by accident: ‘pile’ in ‘compile’, ‘Rankine’ in a cycle)."""
    return " ".join([c.name, c.id.replace(".", " ").replace("_", " "), *c.tags, *(e.title for e in c.parsed)]).lower()


_HAY: dict = {}


def search(cat, phrase: str):
    """Calculations whose name, id, tags or equation titles contain every word of the phrase."""
    if not _HAY:
        _HAY.update({c.id: (c, _haystack(c)) for c in cat})
    words = phrase.lower().replace("-", " ").split()
    return [c for c, h in _HAY.values() if all(w in h.replace("-", " ") for w in words)]


def run() -> dict:
    cat = default_catalog()
    out: dict = {}
    for field, items in CHECK.items():
        rows = []
        for topic, phrases in items:
            hit = None
            for ph in phrases:
                res = search(cat, ph)
                if res:
                    hit = (ph, res[0].id, len(res))
                    break
            rows.append((topic, phrases, hit))
        out[field] = rows
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    res = run()
    from collections import Counter

    total = sum(len(v) for v in res.values())
    tot = Counter(status(t, h)[0] for v in res.values() for t, ph, h in v)
    print(f"{total} topics checked: {tot['covered']} covered, {tot['partial']} partly, {tot['gap']} missing")
    for field, rows in res.items():
        miss = [t for t, ph, h in rows if status(t, h)[0] == "gap"]
        print(f"\n{field}: {len(miss)} missing")
        for t in miss:
            print(f"  - {t}")
    if a.write:
        write_doc(res)
    return 0


FIRST_BATCH = [
    ("Civil", "Mohr's circle and principal stresses; fixed-end and propped beams, continuous beams (three moments); truss analysis; RC shear (stirrups), column capacity and development length; bolt shear and bearing"),
    ("Civil (geotechnical)", "phase relations, Atterberg limits, Rankine/Coulomb pressure and retaining walls, Boussinesq stress, Terzaghi consolidation time, pile capacity, infinite slope, liquefaction (CSR)"),
    ("Civil (water)", "critical depth and specific energy, hydraulic jump, gradually varied flow, culverts, water hammer, unit hydrograph, Muskingum routing, IDF and time of concentration, Gumbel flood frequency, Penman–Monteith/Hargreaves, Theis"),
    ("Civil (transport, construction, environment)", "vertical curves, level of service, CPM and earned value, wave shoaling, BOD kinetics, sand filtration, flocculation G, trickling filter, noise barrier"),
    ("Mechanical", "stress concentration, thin-walled and thick-walled (Lamé) pressure vessels, Goodman/Soderberg shaft fatigue, bearing L10 life, Lewis gear stress, belts, clutches and brakes, transmissibility, critical speed, springs, four-bar linkage"),
    ("Thermal-fluid", "Dittus–Boelter and external convection, natural convection, view factors, boiling, psychrometrics, combustion stoichiometry, choked flow and normal shock, Blasius boundary layer, regenerative Rankine, pump affinity laws, fittings and minor losses"),
    ("Control", "Bode plot, Routh–Hurwitz, root locus, lead/lag compensators, state-space (these have no calculation at all)"),
    ("Electrical", "Thevenin and maximum power transfer, transformer equivalent circuit and regulation, synchronous machine, symmetrical components, transmission-line ABCD, antennas and the radar equation, noise figure, Butterworth/Chebyshev filters, BJT bias, op-amp circuits, BER, cable ampacity, flyback converter, THD, thyristors, touch and step voltage"),
    ("Chemical", "Rachford–Rice flash, Fenske–Underwood–Gilliland, Kremser, Thiele modulus, Damköhler, batch and adiabatic reactors, RTD, two-film theory and HTU, drying, cake filtration, fluidisation, relief-valve sizing, Peng–Robinson, NRTL/Wilson, non-Newtonian pipe flow"),
    ("Materials", "true stress–strain and Ramberg–Osgood, classical laminate theory, Avrami kinetics, Orowan strengthening, Larson–Miller, Charpy transition, hardness, Scheil segregation, Schottky barrier, Curie–Weiss"),
    ("Aerospace", "normal and oblique shocks, Prandtl–Meyer, nozzle area ratio, plane change and bi-elliptic transfer, orbital elements, J2 and sun-synchronous orbits, propeller range and endurance, climb, turn and V–n, take-off distance, Sutton–Graves heating, staging, Clohessy–Wiltshire"),
    ("Biomedical", "two-compartment and oral pharmacokinetics, Cockcroft–Gault, BSA and BMR, Fick cardiac output, stenosis, Windkessel, Starling forces, alveolar gas equation, Pennes bioheat, SIR epidemic model, Hodgkin–Huxley, biologically effective dose"),
    ("Petroleum, mining, nuclear, agriculture", "Havlena–Odeh, Buckley–Leverett, Corey permeability, PVT correlations, Weymouth, Horner plot; point kinetics, diffusion length and bare-reactor criticality, xenon poisoning; Kuz–Ram, RMR/Q; Green–Ampt, Penman–Monteith"),
    ("Industrial, computer, architectural", "Erlang C and M/M/c, Weibull reliability, forecasting, engineering economics (IRR, depreciation), linear programming, RAID/MTTDL, Bloom filter, daylight factor, PMV/PPD, Glaser condensation"),
    ("Physics", "Fermi's golden rule and perturbation theory, spin-½ and Bloch sphere, Born approximation, Maxwell relations, van der Pol and Lotka–Volterra, Kronig–Penney bands, Josephson, Cherenkov, Lagrange points, statistics for error analysis, Hooke's-law constants"),
]

HEADER = """# Equation audit: which standard equations the library does not have

Generated by `python scripts/equation_audit.py --write` from a checklist of {total} standard topics (the script holds the checklist and the verdicts). Date of the review: 2026-10-30.
The library at that date had {n} calculations in 36 disciplines and 246 sub-disciplines.

## How it was done, and what it cannot show

1. **A checklist.** For each field I wrote down what an undergraduate or practising engineer would expect to find: {total} topics, each with one or more search phrases.
2. **A search.** A phrase finds a calculation when every word is in its name, id, tags or equation titles.
3. **A reading of every hit.** A keyword hit is only a candidate. ‘Johnson’ found a noise calculation, ‘affinity’ a biosensor, ‘pile’ a wave-force one, ‘rankine’ the Rankine *cycle* (not earth pressure). Every hit and every miss was read, and a topic counts as **covered** only if a calculation of that name really does the job, **partly covered** if something related exists (what exists is stated), and a **gap** otherwise. The 237 gaps that a looser description search still matched were read again; about 40 of them turned out to be partly covered and were moved.
4. **The limit.** The checklist is one author's idea of the field and it shares that author's blind spots: it can show that something standard is missing, never that nothing else is. A topic that is "covered" may still be a thin version of the textbook treatment, and the formulas in the library are tested against independent code written by the same author, not against the standards. A topic in a field I know less well (control, geotechnics, process safety) will be under-listed, not over-listed.

The checklist is broad on purpose, so most of it is **not** in a 992-calculation library (before the fill; 1377 after) and a high gap count is expected: it is a map of what could be added, not a list of mistakes.

"""


def write_doc(res: dict) -> None:
    from collections import Counter

    cat = default_catalog()
    total = sum(len(v) for v in res.values())
    lines = [HEADER.format(total=total, n=len(cat))]
    summary, body = [], []
    tot = Counter()
    for field, rows in res.items():
        st = [(t, *status(t, h)) for t, ph, h in rows]
        c = Counter(x[1] for x in st)
        tot += c
        summary.append(f"| {field} | {len(rows)} | {c['covered']} | {c['partial']} | {c['gap']} |")
        body.append(f"## {field}\n")
        gaps = [t for t, k, _ in st if k == "gap"]
        part = [(t, n) for t, k, n in st if k == "partial"]
        body.append("**Missing** (" + str(len(gaps)) + "):\n")
        body += [f"- {t}" for t in gaps] or ["- none"]
        if part:
            body.append("\n**Partly covered** (" + str(len(part)) + "), what exists:\n")
            body += [f"- {t}: {n}" for t, n in part]
        body.append("")
    lines.append("## Summary\n\n| Field | Topics | Covered | Partly | Missing |\n|---|---|---|---|---|")
    lines += summary
    lines.append(f"| **All** | **{total}** | **{tot['covered']}** | **{tot['partial']}** | **{tot['gap']}** |\n")
    import importlib

    from sliderule.library import _MODULES

    fill = []
    for m in _MODULES:
        if m.startswith("audit_"):
            calcs = importlib.import_module("sliderule.library." + m).CALCS
            fill.append((m, calcs))
    lines.append("## Fill status\n")
    lines.append(f"The verdict tables below are the state of the library **before** the fill: the matcher looks for topic names, and the {sum(len(c) for _, c in fill)} calculations added by the fill (modules `audit_*`, each with independent-route tests in `tests/test_audit_*.py`) use more specific names. They are listed here by module.\n")
    lines.append("| Module | Calculations | First disciplines |\n|---|---|---|")
    for m, calcs in fill:
        lines.append(f"| `{m}` | {len(calcs)} | {', '.join(sorted({c.id.split('.')[0] for c in calcs}))} |")
    lines.append("")
    lines.append("Topics deliberately **not** filled: pinch analysis, gait inverse dynamics, fracture healing, heart-rate variability, livestock energetics, linear programming and the transportation problem, Beggs–Brill multiphase flow, full Fanger PMV, smart-city demand response and microgrid dispatch, mine slope circular failure, and the remaining partly-covered chemistry variants (Woodward–Fieser, Pitzer, DLVO, EIS, etc.). Source checks so far (about 225 formulas and constants, two errors fixed) are recorded in [VERIFICATION.md](VERIFICATION.md). Caveats: the tests share an author with the formulas and the formulas were typed from memory; the source checks above cover part of the fill, and the items the web could not settle are listed in [ROADMAP.md](ROADMAP.md).\n")
    lines.append("## Suggested first batch\n\nThe topics most often taught or used first, by field (a field here groups the headings below):\n")
    lines += [f"- **{f}**: {t}" for f, t in FIRST_BATCH]
    lines.append("")
    lines += body
    # sub-disciplines at the floor of three calculations
    thin: dict[str, list[str]] = {}
    counts: Counter = Counter()
    for c in cat:
        for sd in c.subdisciplines:
            counts[sd] += 1
    from sliderule.core.taxonomy import SUBDISCIPLINES

    for sd, n in counts.items():
        if n <= 3 and sd in SUBDISCIPLINES:
            thin.setdefault(SUBDISCIPLINES[sd][0], []).append(f"{sd} ({n})")
    lines.append("## Sub-disciplines at or below the floor of three calculations\n")
    lines.append("Every sub-discipline has at least three calculations; these have no more, so each is a place where one more calculation changes its coverage a lot. (Sub-disciplines are grouped under their first discipline.)\n")
    for d, items in sorted(thin.items()):
        lines.append(f"- **{d}**: " + "; ".join(sorted(items)))
    lines.append("")
    Path(__file__).resolve().parents[1].joinpath("docs", "EQUATION_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote docs/EQUATION_AUDIT.md")


if __name__ == "__main__":
    sys.exit(main())
