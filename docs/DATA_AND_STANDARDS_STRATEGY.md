# Strategy: materials, standard sizes and code compliance

Status: phases 1a, 1b and 1c built (see §10 to §12); a local extractor for the CRC Handbook (§13); the rest is proposal. Written 2026-10-30. Roadmap items it serves: *property databases* and *code-compliance support* ([ROADMAP.md](ROADMAP.md)). Not legal advice: every licensing statement below needs a lawyer's confirmation before data or text is shipped or sold.

## 1. What is being added, and why it is three problems

| Layer | Examples | Nature | Main risk |
|---|---|---|---|
| A. Property data | steel yield strength by grade, fluid density and viscosity against T and p, soil and concrete properties, steam tables | Curves and records with uncertainty and a validity range | Quality and provenance; licensing of compiled databases |
| B. Standard sizes and series | NPS and schedule wall thickness, AWG and metric wire, rebar, structural shapes, bolts and threads, preferred numbers, motor and breaker ratings | Discrete rows; many are defined by a formula | Copyright of the published tables; transcription errors |
| C. Code rules | AISC 360, ACI 318, Eurocode, NEC/IEC wiring, ASME B31/VIII, ASCE 7 | Clauses: capacity, demand, utilisation, with editions, amendments and national annexes | Copyright, liability, correctness, upkeep |

What the engine already offers: calculations hold **tables** (`core/tables.py`: x–y points with linear, pchip or log–log interpolation, range handling, inverted numerically, dimension-checked). There is no way to pick a *record* (one row filling several variables), no provenance on data, and no data outside a single calculation.

## 2. Principles

1. **Data lives outside the calculation code**, in versioned *datapacks* with a manifest, so data can be corrected, licensed and sold separately from the formulas.
2. **Every number carries its source**: reference, edition, table or page, date accessed, licence, and the person who entered it. The result shows which datapack and row it used, and the exported report lists them.
3. **Prefer a formula over a table** wherever the standard defines the number by a formula (see §4). A formula is testable, small and free of table copyright.
4. **Never ship text or tables we are not entitled to ship.** Facts and formulas are generally not copyrightable, but the standard's wording, selection and arrangement may be, and database rights apply in some regions. Express clauses in our own words with a clause reference, and obtain licences where a table must be reproduced.
5. **Validate mechanically**: schema, units, monotonic series, range and cross-checks run in CI.
6. **Stay offline-capable**: datapacks load lazily in the browser (Pyodide) and from disk for installs; no data service is required.

## 3. Property data (layer A)

**Three tiers by source**
- *Computed*: use a maintained library where its licence allows it, as a backend behind the same calculation interface: CoolProp (fluids and humid air), IAPWS formulations (steam and water), `thermo`/`chemicals` (pure-component properties), `pvlib` for solar data. Verify each library's licence, that it runs under Pyodide (many have no wasm build) and the size cost; fall back to precomputed tables on a grid with pchip interpolation when it does not.
- *Open reference data*: NIST (US government works are generally public domain; check each page's terms), USGS, NIST JANAF, DOE and ASM open handbooks. Record the exact source per value.
- *Curated handbook values*: typical properties of common engineering materials (ASTM and EN grades, concrete classes, soils, timber species). Enter minimum specified values from the standard where that is the design value, and flag typical values as "typical, not for design". Do not scrape commercial databases (MatWeb, Granta and similar forbid it).

**Data model (per record)**
`id, name, category, standard/grade, properties{name: {value, unit, basis (min/typical/design), temperature, uncertainty, condition}}, source{ref, edition, location, licence}, validity{T range, form, thickness, ...}`.
Temperature-dependent properties are curves using the existing table machinery, not single numbers.

**How a calculation uses it**
- A new *selector* variable kind: the user picks a record (for example "S355J2 steel" or "water at 20 °C"), which fills several variables with units at once and remembers the record id. Individual values stay editable, and edited fields are marked as overridden.
- A function form for properties that depend on state: `rho_water(T, p)` with dimension checking, valid-range warnings and numerical inversion (already supported for tables).
- In **System** diagrams, a *material or fluid source block* with output ports (density, modulus, viscosity ...) wired into calculations, so changing the fluid updates the whole system.
- *My materials* beside *My equations*, so users add their own records; these are flagged as user data.

## 4. Standard sizes and series (layer B)

**Sort each item by how it is defined**
1. *Defined by a formula, so compute it*: AWG (d = 0.127 mm · 92^((36 − n)/39)), preferred-number series R5/R10/R20/R40 and E-series, ISO metric thread dimensions, ISO 286 fits and tolerance grades, hex and bolt proportions, standard thicknesses from a gauge rule. No table licence issue and no transcription errors.
2. *Defined by a table that is a set of nominal sizes*: NPS and DN pairs, rebar bar numbers, standard motor and breaker ratings, fuse and cable sizes. Individual dimensions are facts; cross-check each row against two independent public sources and cite the standard.
3. *Defined by a copyrighted compilation* (ASME B36.10M/B36.19M wall thickness schedules, AISC shape database, NEC ampacity tables, EN profile tables): ship only after a licence or a confirmed public-domain source. Where licences are not available, derive the values from a stated definition (for example ampacity from IEC 60287 or Neher–McGrath heat-transfer equations, already partly in the library) and label them "calculated, not the code table value".

**Mechanics**
- A *series* datapack type with columns and units, plus a *selection rule* ("smallest standard size not less than X": next larger pipe, next breaker, next bar), exposed as a function so a calculation can end with "required 37.2 mm → select DN 40, schedule 40".
- Pickers in the UI next to the variable ("Pick standard size"), with search by nominal size.
- CI checks: units, ascending order, the formula series regenerated and compared with a published sample, and each row's second source recorded.

## 5. Code compliance (layer C)

**Pattern: a *check* is a calculation with a fixed shape**
Inputs → capacity (R) → demand (E) → utilisation (E/R or R/E) → pass or fail → governing clause. Each check is an ordinary library calculation with extra metadata: standard, edition, clause, jurisdiction or annex, resistance or load factors used, and limits of applicability. Results show a green/red utilisation bar and a one-line statement; reports list every clause cited.

**Content rules**
- Own wording plus clause numbers. Formulas may be stated as formulas; no copied paragraphs, tables or figures unless licensed.
- One *edition and amendment set* per check (for example "AISC 360-22", "EN 1992-1-1:2004 with the UK National Annex"). Never mix editions silently; allow a *parameter set* for national annexes and load-factor combinations.
- Applicability guards (slenderness limits, material grades, geometry) are validity checks that block rather than warn when a rule would be used outside its scope.
- *Not a substitute for the engineer of record*: a standing disclaimer in the app and every exported report, with the edition and datapack versions printed.

**Verification (the part that buys trust)**
- Regression set from **published worked examples** (AISC Design Examples, ACI and Eurocode worked examples, PCI, ASME and NEC handbook examples), with the source example number in the test.
- Second implementation by a different route (hand calculation script, or a vetted open library) before a check is marked *verified*.
- Mark each check *draft, reviewed, verified*, with reviewer and date, and show the badge in the UI.

**Suggested first checks (high demand, formula-based, well documented)**
1. Steel (AISC 360 / EN 1993): beam flexure and shear, column compression, bolted connection.
2. Concrete (ACI 318 / EN 1992): beam flexure and shear, column axial, development length (several exist as plain calculations already and would gain clause wrappers).
3. Electrical (NEC / IEC 60364): conductor sizing, voltage drop, short-circuit withstand (formula-based, avoiding the copyrighted ampacity tables).
4. Piping and pressure (ASME B31.3, VIII-1): minimum wall thickness, MAWP, nozzle reinforcement.
5. Loads (ASCE 7 / EN 1991): wind pressure, seismic base shear in simplified forms, load combinations.

**Delivery**
Free tier: formula-only checks that cite the clause. Paid *code packs* per standard and edition, built either under a publisher agreement or from our own independently written clauses, each pack separately versioned and licensed.

## 6. Integration across the product

| Area | Change |
|---|---|
| Calculation list | New filter facets: *has standard size picker*, *code check*, *edition*, *jurisdiction* |
| Calculation page | Source and edition badges, a *pick from standard* control, result lines saying "uses datapack X rev N" |
| System canvas | Material and fluid source blocks, selector blocks, check blocks whose pass/fail output can be wired into a summary |
| LiveCalc | `material("S355").E`, `pipe(nps=2, sch=40).OD`, `awg(10).area`, `select_size("pipe", d_req)` |
| My data | Import and export datapacks (JSON/CSV) with the same schema checks; marked *custom* |
| Export | Reports and generated code (Python, MATLAB, spreadsheet) list datapack ids and versions; spreadsheet export embeds the used rows |
| API and CLI | `sliderule data list|show|validate|install` for installs and CI |

## 7. Datapack format (proposal)

```
datapacks/<name>/
  manifest.json      id, version, title, licence, redistribution, requires, source[], created, checksum
  schema.json        columns, units, keys, validity rules
  data.csv|json      rows
  tests.json         golden rows and cross-checks against the cited source
  NOTICE.md          attributions and licence text
```
Loading: lazy per pack in the browser; verified by checksum; paid packs unlock with a licence key for installs (the licensing model is covered separately).

## 8. Phasing

1. **Foundation** (smallest useful step): datapack schema and loader, *series* type with the *select next size* function, record selector UI, provenance shown in results, CI validation. Ship formula-defined series first (AWG, preferred numbers, ISO threads, fits). Few legal questions, immediate value.
2. **Materials and fluids**: curated open-data pack (common steels, aluminium, concrete, timber, soils, water, air), plus CoolProp/IAPWS backends if they run in Pyodide; material and fluid source blocks in System.
3. **Standard size packs**: pipe, tube, rebar, structural shapes, fasteners, motor and breaker ratings, taking licences where §4 rule 3 applies.
4. **Code checks, first wave**: five families of §5 with verified status and worked-example tests; clause metadata and utilisation display.
5. **Commercial layer**: packs sold per standard and edition, with signed datapacks and a licence key; update channel and change notices (what changed, which results move).
6. **Maintenance**: yearly review calendar per edition, deprecation of old editions, regression diff when a pack updates.

## 9. Open decisions

- Will paid packs be built under publisher licences or written independently? This decides cost, scope and legal risk.
- Which jurisdictions first (US, EU, UK, others)? Each needs its own annexes and load combinations.
- Do CoolProp and IAPWS run in the browser build, or should properties be precomputed grids?
- Who reviews and signs off checks as *verified* (internal staff, outside engineers)?
- How to present liability: wording in the terms, in the app, and in reports.
- How big a download is acceptable for the offline browser build (lazy packs, compression, grid resolution)?

## 10. What is built (phase 1a, 2026-10-30)

The foundation for layer A, backend only. The browser has no picker yet.

- `core/datapack.py`: pack format (`manifest.json` + `data.json`, sha256 seal), a fixed **property vocabulary** (density, Young's modulus, Poisson's ratio, yield and ultimate strength, thermal conductivity, specific heat, thermal expansion) that fixes each property's dimension and a plausibility range, loading from the built-in `src/sliderule/datapacks/` and from `$SLIDERULE_HOME/datapacks/` (user packs, marked custom), and refusal of any pack that fails validation with every reason listed. A bad user pack never hides the good ones.
- Every property carries its **basis** (`min`, `typical`, `design`, `computed`), a **source** id resolved to a reference in the manifest, and optionally the **low** and **high** where sources disagree. A pack states whether it is fit for design (`design_use`); the starter pack says no, and the CLI and API repeat that.
- API (`data_packs`, `data_search`, `data_record`), HTTP (`/api/data`, `/api/data/search`, `/api/data/{pack}/{record}`), and CLI (`sliderule data list | show PACK RECORD | validate | seal | path`). Records come back in the stored unit and in SI with the provenance.
- The web bundle (`scripts/build_web.py`) and the wheel (`pyproject.toml`) include the datapack files; the unpacked bundle was loaded and queried to confirm it works the way Pyodide will see it.
- First pack, `materials-typical` v0.1.0: structural carbon steel, aluminium 6061-T6 and Ti-6Al-4V (annealed), typical values with the spread between the sources read. Strengths and conductivities that the sources disagreed on or did not state a basis for were left out, and the record notes say what is missing and where to get it. Writing this pack showed why: for 6061-T6 the pages read gave 240 MPa yield, another data sheet gives a higher *typical* value, and without a stated basis (minimum or typical) neither is a design number.

Not yet built: temperature-dependent properties (curves, reusing `core/tables.py`), fluids (water, air), the record selector in calculations and in the System canvas, LiveCalc functions such as `material("...")`, user-pack editing in the browser, and the series type of layer B.

Adding a pack: copy a folder under `src/sliderule/datapacks/`, edit `data.json` and `manifest.json`, run `sliderule data seal <folder>` then `sliderule data validate`. CI (`tests/test_datapack.py`) validates every built-in pack and checks stored values against golden values typed from the cited pages.

## 11. Curves and the water and air pack (phase 1b, 2026-10-31)

- **Curves.** A property can be a temperature curve (`{"curve": {"x", "y", "x_unit", "method"}, "unit", "basis", "source"}`) as well as a single value. Curves go through the same interpolators as calculation tables (`linear` or `pchip`, never extrapolated: outside the stored range `data_value` refuses, with the range in the message). Optional `at` (state, for example the pressure) and `rel_uncertainty` (the worst deviation measured against the reference table) travel with the property into every result. Fluids have their own vocabulary (density, dynamic viscosity, thermal conductivity, specific heat, vapour pressure) with plausibility ranges suited to gases and liquids; materials keep theirs, so a g/cm³ slip on a steel is still caught.
- **Access.** `data_value` (API), `GET /api/data/{pack}/{record}/{property}?x=&x_unit=&unit=`, `sliderule data value PACK RECORD PROPERTY --at 20 --at-unit degC --unit "mPa*s"`. Temperature may be given in K, degC or degF.
- **Pack `fluids-water-air` v0.1.0**, generated by `scripts/build_fluid_pack.py` and not for design. Liquid water, 0.01 to 100 degC at 101.325 kPa: density (Kell 1975), viscosity (Vogel three-constant fit), vapour pressure (IAPWS-IF97 saturation-pressure equation), plus specific heat and conductivity as 10 degC reference points from Cengel and Cimbala (2014) Table A-3 because no correlation was checked for them. Dry air at 101.325 kPa, -50 to 1000 degC: density (ideal gas), viscosity and conductivity (Sutherland), specific heat from Table A-9 reference points.
- **How it was checked.** The stored curves are compared at every table row that was not used to build them (water 5 degC steps, air 40 to 60 rows); each property's `rel_uncertainty` must be at least the measured worst deviation and no more than three times it. Measured worst cases: water density 0.05 %, viscosity 2.2 % (the Vogel fit is low at 0 degC), vapour pressure 0.09 %, specific heat 0.03 %, conductivity 0.14 %; air density 0.07 %, viscosity 1.2 %, conductivity **2.4 %** (Sutherland's constants for conductivity run high), specific heat 0.13 %. The IF97 equation reproduces the three official verification values to 1e-8, the Kell formula the published densities at 0, 10, 20, 50 and 100 degC to 1e-4, and a test regenerates the pack from the script and compares it with the stored file.
- **Licensing judgement for review.** The correlations are published formulas. The roughly thirty-five reference points (11 + 11 for water, 13 for air) are facts read from one textbook table; that is a small selection and the pack cites it, but whether it is acceptable for a commercial pack is your call (the alternative is to replace them with a correlation or an open dataset such as the IAPWS formulations).

Not yet built: pressure dependence (gas density scales with pressure by hand for now), further fluids and gases, the selector in calculations and System, LiveCalc functions, and the series type for standard sizes.

## 12. The picker in calculations (phase 1c, 2026-10-31)

- **How an input is matched to data.** By dimension, not by tagging 1377 calculations: `data_options` takes the open calculation's inputs (`key`, `unit`, `label`) and returns, for each, the record properties of the same dimension, with the ones whose hint words appear in the label first (`HINTS` in `core/datapack.py`: "density", "viscosity", "young", "modulus" and so on). A dimensionless input is only offered a property its label names (so "Efficiency" gets nothing and "Poisson's ratio" gets the three Poisson values). A pressure input also sees yield strength and moduli, marked "other", because those share the dimension; the user chooses.
- **Dialog.** Each such input shows a small *from data…* link under its label. The dialog asks for the property, the material or fluid and, for a curve, the temperature (degC, K or degF); it previews the value in the input's own unit with the basis, the measured uncertainty, the source, the state it applies at and a *not for design* badge, and refuses with the stored range when the temperature is outside it. *Use this value* fills the input and keeps it editable.
- **Provenance stays with the value.** A line under the input names the record, property, temperature, value, basis, uncertainty, pack and version. Editing the number or changing its unit by hand adds "edited by hand since"; the × forgets the source; making the input a "find" result drops it. *Copy as text* lists the sources, and *Save case* writes them under `data_sources` (opening a case restores the inputs only for now).
- **Checked.** Driven by hand in the built-in browser on the Swamee-Jain pipe calculation: density from water at 40 degC (992.216 kg/m³), viscosity at 20 degC (1.00175 mPa·s), out-of-range refusal at 150 degC, edit marker, forgetting the source, no console errors. `tests/test_datapack_picker.py` covers the matching rules and that every offer can be fulfilled; `tests/e2e/data_picker.js` repeats the browser flow but was written without Playwright installed and has not been run.

Not yet built: filling several inputs from one record at once, the same picker in System blocks, LiveCalc functions, restoring sources when a case is opened, a unit-aware default temperature taken from a temperature input of the same calculation, and mixing a datapack with the calculation's own `example` values.

## 13. Extracting materials from the CRC Handbook (local, 2026-10-31)

`scripts/import_crc_materials.py PATH_TO_extractor_out/handbook` builds a datapack (`crc-materials`, 205 records) from the 89th Edition (Internet Version 2009) as extracted by `local_pdf_extractor` (`handbook.elements.jsonl`, whose tables carry their cell grid). The pack is written to `~/.sliderule/datapacks/` (a user pack, so it appears in the property picker and `sliderule data`), **not into the repository**: the Handbook is a copyrighted compilation, `.gitignore` excludes `crc-*` packs, and a test checks the default output path is outside the repo. The repository holds the importer and a test on a small synthetic extract in the same shape, never Handbook content.

What was read, and the rule behind it: a table is used only if its cell grid keeps every value in its own row and column, so a value cannot be attached to the wrong material.

| Table (PDF page) | Used for | Records |
|---|---|---|
| Thermal conductivity of metals and semiconductors vs T (2084-2085) | k(T) curves, 100 K upward, W/cm K converted | 15 pure metals |
| Thermal conductivity of alloys vs T (2086) | k(T) curves at 77 to 973 K (group label kept: `Ferrous: stainless steel`) | 36 alloys |
| Heat capacity of selected solids (2081) | cp(T) 200 to 600 K, molar value divided by the IUPAC atomic weight | 24 elements |
| Thermal and physical properties of pure metals (2082-2083) | density at 25 °C (the one column complete in every block) | 70 metals |
| Thermal conductivity of ceramics and insulating materials (2089-2090) | k as a curve or a single value with its temperature, density where printed; group headings and children recognised (`Wood: fir, ⊥`) | 76 materials |
| Room-temperature elastic moduli of the rare earths (748) | E, ν, yield, ultimate strength | 17 metals |

Not used, and why. The pure-metals table prints each column as one cell with all metals in it and some entries missing (specific heat 34 values for 35 metals), so which value belongs to which metal cannot be told; only the complete density column is read. The glasses table (2091) wraps names over two lines that sit beside different data rows. "Density of various solids" (2280) interleaves three blocks in cells. Plastics, woods and the like with only a range of density (2.5-2.7) are not points. Mechanical strengths of engineering alloys are not in the Handbook at all (its mechanical table covers the rare earths), so yield and ultimate strength for steels and aluminium still need a design-basis source.

Checks run on the real extract: aluminium 237 W/(m K) and 2700 kg/m³, copper 401 and 8960, iron 80.2 and 7870, silver 429, gold 317, tungsten 174, lead 35.3 agree with the textbook values; the specific heat of aluminium from the molar table (898.7 J/(kg K)) agrees with the Handbook's own 0.897 J/(g K) column within 0.2 %; the scalar and curve values for stainless steel (16 W/(m K) at 373 K), Sc and Y moduli match the printed rows. The thermal-conductivity plausibility range of the materials vocabulary was widened to 0.001 to 3000 W/(m K) (aerogels and wools below 0.01, cryogenic copper alloys and diamond above 500).

The picker's material list can now hold hundreds of entries, so it has a filter box (type "steel" or "wood").

## 14. CoolProp fluids and NIST cryogenic fits (2026-11-03)

**Which open sources can supply the property data** (checked, not guessed): CoolProp (MIT; computes from published equations of state, so its output is facts and the code's licence is permissive), the NIST Cryogenic Technologies Group fits (US government site; reuse terms depend on whether a dataset is Standard Reference Data, which the pages do not say), IAPWS releases (free documents), Materials Project / AFLOW / OQMD (CC BY 4.0, but they need an API key or registration and hold computed, not measured, values; left for later), Wikidata (CC0, only basic constants). MatWeb forbids bulk reuse and Engineering Toolbox is not openly licensed: not used. Sources that need the user's own credentials or licence stay local-only.

**Built.** `fluids-coolprop` (59 records, 30 fluids, liquid and gas, density, viscosity, conductivity, specific heat, and vapour pressure for liquids, at 101.325 kPa), shipped, with a test against textbook values (water at 20 °C, air at 300 K, liquid nitrogen at its boiling point, methane, helium) and a test that the shipped numbers equal a fresh CoolProp run. `scripts/import_nist_cryo.py` scrapes 26 NIST pages politely and builds a **local** pack from the 23 whose table layout it understands. The pack is checked against values everyone knows: 304 stainless 15.1 W/(m K) and 470 J/(kg K) at 293 K, 6061-T6 154, lead 35.4, molybdenum 139, Teflon 0.27.

**What it taught.** The materials specific-heat range had a floor of 100 J/(kg K), which a cryogenic curve legitimately goes below (a few J/(kg K) at 4 K); the floor is now 0.001. NIST's "fit error" is the fit against NIST's own data, so it is stored with a note saying it is not a measurement uncertainty. Several NIST pages reuse one fit (316 and 304L conductivity equal 304's; 3003, 5083 and 6061 share a specific-heat column), which is NIST's choice and is kept as published.

**Limits.** The fluid curves are at 1 atm only, so gas density at other pressures is not covered (a live CoolProp back-end that takes a pressure would be the next step; it would be an optional dependency). Beryllium, OFHC copper and sapphire pages use another layout and are skipped.

### 13.1 Element names, and a re-extracted Handbook (2026-11-03)

Rare-earth strengths showed only symbols and Greek letters (`γCe`, `αLa`, `Er`) because the Handbook's table names them that way. The importer now maps symbols to element names and keeps the crystal phase in the name and designation (`Cerium (gamma)`, `γ-Ce`, record id `element-cerium-gamma`; two phases of one element stay two records). Germanium and silicon, which also appeared as bare symbols, are named too.

While checking this I found the extractor had been re-run and now keeps real column grids. The unchanged importer silently dropped from 205 to 131 records (all rare-earth rows and the 70 densities were lost, because it read the old one-cell-per-column layout). Fixes: the pure-metals table is now read one metal per row, which gives density, thermal expansion and specific heat at 25 °C and conductivity at 27 °C for about 70 metals (the earlier limitation on those flattened columns is gone), with footnote `b` values (taken at 100 °C) dropped and footnote `a` values marked estimated; the rare-earth table reads both layouts; and the importer now prints a warning when a table it depends on yields nothing. The real pack is 195 records.

### 14.1 Update (2026-11-05)

The NIST cryogenic pack now ships (`nist-cryo`, 23 materials) with NIST's required acknowledgement, change notice and statement, on the basis that NIST allows redistribution of its non-SRD data and its pages carry no SRD copyright notice; it is to be removed if NIST says otherwise. The `materials-typical` source references were replaced by "citation needed" (the web pages they named were not acceptable citations), so that pack is explicitly unverified until it is re-sourced.

### 14.2 Re-sourcing `materials-typical` (2026-11-06)

The vendor and web-page references were withdrawn (14.1) and the pack was rebuilt from open sources. What worked: NASA's 1972 *Materials Data Handbook* series (contractor reports compiled from MIL-HDBK-5A, scanned images on the NASA Technical Reports Server; read by OCR and then checked against the page images) for 6061-T6 and Ti-6Al-4V; NIST's own reports for mild steel (NISTIR 7401); NIST's cryogenic fits for Ti-6Al-4V conductivity. What did not: MMPDS and current MIL-HDBK-5J (not open), the EN 1993-1-2 steel formulas (the standard is paywalled and the only free copies found were lecture slides), ASTM and Aluminum Association data, and the FHWA and NIST NCSTAR PDFs (too large for the fetch tool; fetching them would need a deliberate download). The steel Poisson's ratio was left open here and closed in 14.3. Lesson: government handbooks give open values, but old ones; the pack says so, and a current MMPDS-based source remains the real fix for design use.

### 14.3 The steel Poisson's ratio (2026-11-07)

The one remaining "citation needed" was closed with the 1946 National Bureau of Standards paper (RP 1742, a 16 MB scan with a text layer, downloaded with the user's go-ahead). Table 2 gives the elastic Poisson's ratio, defined from the slopes of the axial-stress against axial and transverse strain lines, for each specimen: structural low-carbon steel to ASTM A7-42 0.256, 0.265, 0.270, 0.265, 0.260, 0.271 (mean 0.2645, stored as 0.265 with the extremes as low and high) and fully killed carbon steel plate 0.263 to 0.279 (mean 0.271 over 18 specimens). These are lower than the round 0.3 the pack carried before, which had no source. The specimens are 1940s steels; the paper's appendix uses 0.3 only as an illustrative number for an idealised material, not as a measurement.
