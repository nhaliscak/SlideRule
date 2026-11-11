# Data sources

SlideRule ships four datapacks under `src/sliderule/datapacks/`. All are marked `design_use: false`: they are for hand
calculations and learning, **not for design**. Every number carries its `source` id, `basis` and, where known, its uncertainty;
the full references, links and access dates are in each pack's `manifest.json`. These packs are released under this repository's
MIT licence: the values are physical facts or computed from published formulas, and no table is copied.

## `fluids-water-air` (water and dry air against temperature)

| Property | Origin |
|---|---|
| Water density | Kell (1975), a published correlation, computed |
| Water viscosity | Vogel-form fit, checked against an IAPWS-based table |
| Water saturation pressure | IAPWS R7-97(2012) (IF97) saturation equation, computed |
| Air density | Ideal-gas law, R = 287.05 J/(kg K) |
| Air viscosity and conductivity | Sutherland's law with the constants quoted by F. M. White, *Viscous Fluid Flow* |
| Reference points for water and air specific heat and conductivity | Facts read from tables A-3 and A-9 of Cengel and Cimbala, *Fluid Mechanics* (3 values each, cited as a source, not reproduced as a table) |

The curves are checked against a reference table; see `scripts/build_fluid_pack.py` and the `rel_uncertainty` of each property.

## `materials-typical` (structural steel, aluminium 6061-T6, Ti-6Al-4V)

Typical values, with the printed minimum as the low end where there is one, read from open sources and converted to SI by `scripts/build_materials_typical_pack.py`
(each printed number and unit is in the script, so nothing is converted by hand). Page numbers are the printed ones.

| Material | Properties | Source |
|---|---|---|
| Aluminium 6061-T6 | density, E (typical 10.0e3 ksi, design 9.9e3), Poisson's ratio 0.33, expansion, conductivity (T6), specific heat, typical and A-basis yield and ultimate strength | R. F. Muraca and J. S. Whittick, *Materials Data Handbook: Aluminum Alloy 6061* (2nd ed.), NASA CR-123772, May 1972: abstract p. iv, section 7.2 p. 39, Table 7.4111 p. 43, section 9 p. 75 |
| Ti-6Al-4V annealed | density, E (typical 16.5e3 ksi, design 16.0e3), Poisson's ratio 0.342, expansion, specific heat, typical annealed strengths and the specification minimums | same authors, *Materials Data Handbook: Titanium 6Al-4V*, NASA CR-123775, May 1972: abstract p. iv, section 7.2 p. 39, Table 7.4111 p. 42 |
| Ti-6Al-4V annealed | thermal conductivity at 293 K | NIST cryogenic fit (see `nist-cryo`) |
| Structural steel | density, conductivity and specific heat at 26.85 degC | D. P. Bentz and K. R. Prasad, NISTIR 7401 (NIST, Feb. 2007), section 3.1.2 and Table 5 (the values were collected for NIST's World Trade Center investigation) |
| Structural steel | modulus (29,000,000 psi) and expansion (6.5e-6 per degF) | Wyoming DOT Bridge Design Manual, chapter 1 (revised Jan. 2022), p. 1-4: values the manual prescribes, so basis `design` |
| Structural steel | Poisson's ratio 0.265 (0.256 to 0.271) | A. H. Stang, M. Greenspan and S. B. Newman, *Poisson's Ratio of Some Structural Alloys for Large Strains*, J. Res. National Bureau of Standards 37 (1946), RP 1742, Table 2 (p. 216): six specimens of structural low-carbon steel to ASTM A7-42, tested in 1943 to 1946; modern grades (A36, A992) were not tested |

Limits to know: the two NASA handbooks are from 1972 and compile MIL-HDBK-5A, which is superseded (MMPDS replaced it, and is not open), so the minimums shown are that edition's
A-basis or specification values and are not current allowables; the 1972 specific heat of Ti-6Al-4V (0.135 cal/(g degC)) should be checked against a current source; and the 1972
Ti-6Al-4V abstract prints conductivity as 0.012 with garbled units, so the NIST fit is used instead. The two NASA documents carry no copyright notice and are distributed by the NASA
Technical Reports Server; the numbers are physical facts. Grade-specific steel strengths (A36, A992, S355) are not in the pack. No value in this pack currently reads "citation needed".

## `fluids-coolprop` (about 30 common fluids, liquid and gas, against temperature at 101.325 kPa)

Computed with [CoolProp](https://coolprop.org) 8.0.0 (MIT licence) by `scripts/build_coolprop_pack.py`; the pack stores the values, so CoolProp is not a run-time
dependency (`pip install ".[props]"` is only needed to rebuild it, and a test compares the shipped numbers with a fresh run). CoolProp evaluates published
equations of state and transport correlations; each fluid's source in `manifest.json` lists the literature keys CoolProp reports for its equation of state,
viscosity and conductivity (for water: Wagner and Pruss 2002, Huber et al. 2009 and 2012). Cite: I. H. Bell, J. Wronski, S. Quoilin, V. Lemort,
Ind. Eng. Chem. Res. 53(6), 2498 (2014). The `rel_uncertainty` values are generic orders of magnitude, not each model's own stated uncertainty.
Fluids whose CoolProp model has no viscosity or conductivity correlation simply omit that property.

## `nist-cryo` (cryogenic thermal conductivity and specific heat of 23 materials)

Source: National Institute of Standards and Technology (NIST), Cryogenic Technologies Group, Cryogenic Material Properties,
https://trc.nist.gov/cryogenics/materials/materialproperties.htm (aluminium alloys, stainless steels, brass, Inconel, Invar, lead, molybdenum, platinum, polymers, G-10
and more, 4 K to room temperature). NIST permits copying, modification and redistribution of its works that are not Standard Reference Data, provided NIST is
acknowledged, a change notice is given and its statement is included (https://www.nist.gov/open/license). All three are in the pack's `manifest.json` and
`NOTICE.md`. **Change notice:** NIST publishes polynomial fit coefficients; `scripts/import_nist_cryo.py` evaluates each fit at 60 log-spaced temperatures
inside the range covered by NIST's data and equation, rounds to 6 significant figures and stores a curve (pages read 2026-11-03; pack built 2026-11-05). The pages
carry no Standard Reference Data copyright notice; if NIST says otherwise, the pack will be removed. The stored `rel_uncertainty` is NIST's curve-fit error against
its own data, not a measurement uncertainty. Beryllium, OFHC copper and sapphire use a different table layout and are not included. To rebuild:
`python scripts/import_nist_cryo.py --cache DIR --out src/sliderule/datapacks/nist-cryo` (one request every 2 s, identifying User-Agent; `trc.nist.gov` has no
`robots.txt` and `www.nist.gov`'s does not disallow these paths).

## Not shipped, local importers

* **CRC Handbook** (copyrighted compilation): see below.
### CRC Handbook

(The importer names every element and keeps crystal phases, e.g. `Cerium (gamma)`.)

The CRC Handbook of Chemistry and Physics is a copyrighted compilation. `scripts/import_crc_materials.py` can build a pack from a
copy you own into `~/.sliderule/datapacks/`, outside the repository; `.gitignore` excludes `crc-*` packs and a test checks the default
output location. User packs are marked custom in the picker.

## Third-party code

KaTeX 0.16 (MIT, Khan Academy and contributors), vendored in `src/sliderule/web/vendor/katex/` with its licence. Pyodide is loaded
at run time from the jsDelivr CDN (Mozilla Public License 2.0); it is not stored here.
