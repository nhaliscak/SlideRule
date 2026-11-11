from ..core import C, Calculation, V

CALCS = [
    Calculation(
        id="environmental.ecological.wetland_area_kc_star", name="Treatment wetland area (k–C* model)",
        disciplines=["environmental", "civil"], subdisciplines=["Ecological Engineering", "Water and Wastewater Treatment", "Natural Resources Engineering"],
        description="Surface area of a free-water-surface or subsurface-flow wetland to reach a target effluent concentration with a background concentration C*.",
        variables=[V("Q", "Design flow", "m^3/day"), V("k", "Areal rate constant", "m/yr"), V("C0", "Inlet concentration", "mg/L", latex=r"C_0"), V("Cs", "Background concentration", "mg/L", latex=r"C^*"), V("C", "Target outlet concentration", "mg/L"), V("A", "Wetland area", "ha")],
        equations=["A = Q/k*log((C0 - Cs)/(C - Cs))"], outputs=["A"], tags=["wetland", "constructed wetland", "bod", "nutrient removal", "ecological engineering", "treatment"], validity=[("C > Cs", "target must exceed the background concentration C*")],
        assumptions=["Plug flow with first-order area-based removal; k is pollutant and climate specific (BOD ≈ 34 m/yr)"], references=["Kadlec & Wallace, Treatment Wetlands, Ch. 4"], example={"Q": "500 m^3/day", "k": "34 m/yr", "C0": "100 mg/L", "Cs": "10 mg/L", "C": "30 mg/L"}),
    Calculation(
        id="environmental.fire.heat_release_flame_height", name="Fire heat release rate and flame height",
        disciplines=["environmental", "architectural", "chemical"], subdisciplines=["Fire Protection Engineering", "Mine Safety Engineering"],
        description="Heat release rate of a pool or fuel-package fire, Heskestad flame height, and the time for a t² growth fire to reach a given size.",
        variables=[V("mf", "Mass burning flux", "g/(m^2*s)", latex=r"\dot m''"), V("dH", "Heat of combustion", "kJ/kg", latex=r"\Delta H_c"), V("Af", "Fuel surface area", "m^2", latex=r"A_f"), V("chi", "Combustion efficiency", "%", latex=r"\chi", min=1, max=100),
                   C("c1", "Heskestad coefficient", 0.235, "m/kW^(2/5)", latex=r"0.235"), V("Df", "Equivalent fire diameter", "m", latex=r"D"), V("Q", "Heat release rate", "kW", latex=r"\dot Q"), V("Lf", "Mean flame height", "m", latex=r"L_f"),
                   V("al", "Fire growth coefficient", "kW/s^2", latex=r"\alpha"), V("tg", "Time to reach Q (t² fire)", "s", latex=r"t_g")],
        equations=[("Heat release rate", "Q = chi*mf*dH*Af"), ("Equivalent diameter", "Df = sqrt(4*Af/pi)"), ("Heskestad flame height", "Lf = c1*Q^(2/5) - 102/100*Df"), ("Growth time", "tg = sqrt(Q/al)")],
        outputs=["Q", "Df", "Lf", "tg"], tags=["fire", "hrr", "flame height", "heskestad", "design fire", "t-squared"], assumptions=["Pool-like fire, no wind; α = 0.0469 kW/s² (fast), 0.1876 (ultrafast) for NFPA t² fires"], references=["Heskestad, SFPE Handbook of Fire Protection Engineering, Ch. 2-1"],
        example={"mf": "101 g/(m^2*s)", "dH": "44600 kJ/kg", "Af": "1 m^2", "chi": "90 %", "al": "0.0469 kW/s^2"}),
    Calculation(
        id="environmental.fire.sprinkler_discharge", name="Sprinkler discharge and design density",
        disciplines=["environmental", "architectural", "mechanical"], subdisciplines=["Fire Protection Engineering"],
        description="Flow from a sprinkler head with a K-factor and the resulting water density over its coverage area.",
        variables=[V("K", "K-factor", "gpm/psi^(1/2)"), V("p", "Operating pressure", "psi"), V("Ac", "Coverage area per head", "ft^2", latex=r"A_c"), V("q", "Head flow", "gpm"), V("dd", "Application density", "mm/min", latex=r"d")],
        equations=[("Discharge", "q = K*sqrt(p)"), ("Density", "dd = q/Ac")], outputs=["q", "dd"], tags=["sprinkler", "nfpa 13", "k factor", "water density", "suppression"], assumptions=["Single head at the stated pressure"], references=["NFPA 13, Ch. 28"], example={"K": "5.6 gpm/psi^(1/2)", "p": "20 psi", "Ac": "130 ft^2"}),
    Calculation(
        id="environmental.treatment.clarifier_design", name="Clarifier overflow rate, detention time and weir loading",
        disciplines=["environmental", "civil"], subdisciplines=["Water and Wastewater Treatment", "Sanitary Engineering"],
        description="Surface overflow rate, hydraulic detention time and weir loading rate of a settling tank.",
        variables=[V("Q", "Flow", "m^3/day"), V("A", "Surface area", "m^2"), V("h", "Side water depth", "m"), V("Lw", "Effluent weir length", "m", latex=r"L_w"), V("SOR", "Surface overflow rate", "m/day"), V("HRT", "Detention time", "h", latex=r"\theta"), V("WLR", "Weir loading rate", "m^3/(m*day)")],
        equations=[("Overflow rate", "SOR = Q/A"), ("Detention time", "HRT = A*h/Q"), ("Weir loading", "WLR = Q/Lw")], outputs=["SOR", "HRT", "WLR"], tags=["settling", "sedimentation", "primary clarifier", "weir", "overflow rate", "wastewater"], assumptions=["Ideal plug-flow settling tank"], references=["Metcalf & Eddy, Wastewater Engineering, Ch. 5"],
        example={"Q": "5000 m^3/day", "A": "250 m^2", "h": "3.5 m", "Lw": "62.8 m"}),
    Calculation(
        id="environmental.treatment.activated_sludge_fm_srt", name="Activated sludge: F/M ratio, SRT and HRT",
        disciplines=["environmental", "chemical", "civil"], subdisciplines=["Water and Wastewater Treatment", "Sanitary Engineering", "Biochemical Engineering"],
        description="Food-to-microorganism ratio, solids retention time and hydraulic retention time of a complete-mix activated-sludge basin.",
        variables=[V("Q", "Influent flow", "m^3/day"), V("S0", "Influent BOD", "mg/L", latex=r"S_0"), V("V", "Aeration basin volume", "m^3"), V("X", "MLVSS", "mg/L"), V("Qw", "Waste sludge flow", "m^3/day", latex=r"Q_w"), V("Xr", "Return-sludge concentration", "mg/L", latex=r"X_r"),
                   V("FM", "Food-to-microorganism ratio", "1/day", latex=r"F/M"), V("SRT", "Solids retention time", "day", latex=r"\theta_c"), V("HRT", "Hydraulic retention time", "h", latex=r"\theta")],
        equations=[("F/M", "FM = Q*S0/(V*X)"), ("SRT", "SRT = V*X/(Qw*Xr)"), ("HRT", "HRT = V/Q")], outputs=["FM", "SRT", "HRT"], tags=["activated sludge", "f/m", "srt", "aeration", "secondary treatment", "bod"], assumptions=["Effluent solids neglected in the SRT; steady state"], references=["Metcalf & Eddy, Ch. 7"],
        example={"Q": "10000 m^3/day", "S0": "200 mg/L", "V": "3000 m^3", "X": "2500 mg/L", "Qw": "100 m^3/day", "Xr": "8000 mg/L"}),
    Calculation(
        id="environmental.pollution.esp_baghouse", name="Electrostatic precipitator and baghouse sizing",
        disciplines=["environmental", "chemical", "mining"], subdisciplines=["Pollution Control", "Environmental Chemical Engineering"],
        description="Deutsch–Anderson collection efficiency for an ESP and the cloth area required by a fabric filter at a given air-to-cloth ratio.",
        variables=[V("w", "Particle migration velocity", "cm/s"), V("Ap", "Collecting plate area", "m^2", latex=r"A_p"), V("Qg", "Gas flow", "m^3/s", latex=r"Q"), V("act", "Air-to-cloth ratio", "m/min"), V("eta", "ESP collection efficiency", "%", latex=r"\eta"),
                   V("Ac", "Baghouse cloth area", "m^2", latex=r"A_c")],
        equations=[("Deutsch–Anderson", "eta = 1 - exp(-w*Ap/Qg)"), ("Cloth area", "Ac = Qg/act")], outputs=["eta", "Ac"], tags=["particulate", "dust collector", "esp", "baghouse", "fabric filter", "air pollution"], assumptions=["Uniform gas distribution; use effective (not theoretical) migration velocity"],
        references=["Cooper & Alley, Air Pollution Control Engineering, Ch. 6–7"], example={"w": "12 cm/s", "Ap": "2500 m^2", "Qg": "100 m^3/s", "act": "1.2 m/min"}),
    Calculation(
        id="environmental.resources.catchment_water_balance", name="Catchment water balance",
        disciplines=["environmental", "civil", "agricultural"], subdisciplines=["Natural Resources Engineering", "Water Resources Engineering", "Soil and Water Engineering"],
        description="Annual storage change from precipitation, evapotranspiration and measured outflow, and the runoff ratio.",
        variables=[V("P", "Precipitation", "mm/yr"), V("ET", "Evapotranspiration", "mm/yr"), V("Qo", "Mean outflow", "m^3/s"), V("A", "Catchment area", "km^2"), V("Ro", "Runoff depth", "mm/yr"), V("dS", "Storage change", "mm/yr", latex=r"\Delta S", signed=True), V("rr", "Runoff ratio", "%")],
        equations=[("Runoff depth", "Ro = Qo/A"), ("Water balance", "dS = P - ET - Ro"), ("Runoff ratio", "rr = Ro/P")], outputs=["Ro", "dS", "rr"], tags=["water balance", "hydrology", "watershed", "runoff", "evapotranspiration", "storage"], assumptions=["Closed catchment, no inter-basin transfers, groundwater divides match surface divides"],
        references=["Dingman, Physical Hydrology, Ch. 1"], example={"P": "900 mm/yr", "ET": "550 mm/yr", "Qo": "1.8 m^3/s", "A": "250 km^2"}),
    Calculation(
        id="environmental.eia.box_model_air_quality", name="Box-model air quality estimate",
        disciplines=["environmental"], subdisciplines=["Environmental Impact Assessment", "Pollution Control"],
        description="Screening-level pollutant concentration over an area source from emission rate, wind speed, mixing height and background.",
        variables=[V("Qe", "Emission rate", "g/s"), V("u", "Mean wind speed", "m/s"), V("W", "Crosswind width of source area", "m"), V("Hm", "Mixing height", "m", latex=r"H"), V("Cb", "Background concentration", "ug/m^3", latex=r"C_b"), V("C", "Predicted concentration", "ug/m^3")],
        equations=["C = Qe/(u*W*Hm) + Cb"], outputs=["C"], tags=["air quality", "screening", "emissions", "eia", "box model", "dispersion"], assumptions=["Well-mixed box, steady wind, no chemical reaction or deposition — conservative screening only"], references=["Seinfeld & Pandis, Atmospheric Chemistry and Physics, Ch. 18"],
        example={"Qe": "500 g/s", "u": "3 m/s", "W": "2000 m", "Hm": "800 m", "Cb": "20 ug/m^3"}),
]
