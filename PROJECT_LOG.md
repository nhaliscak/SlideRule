# SlideRule — project log

## Related documents
- [README.md](README.md) — description, setup and run instructions
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the engine, API and UI fit together
- [docs/COVERAGE.md](docs/COVERAGE.md) — discipline coverage
- [docs/DATA_AND_STANDARDS_STRATEGY.md](docs/DATA_AND_STANDARDS_STRATEGY.md) — property data, standard sizes and code compliance (§10: what is built)

## 2026-10-28 — Calculation list pane and `serve --reload`

**Goal.** Put the scrolling list of calculations in its own column between the search filters and the calculation
detail, with a button to hide and show it. Then make iterating on the UI easier with an auto-reloading server.

**List pane.** `#listpane` is a new `<aside>` in `index.html`; `.layout` is now three grid columns, with a
`.list-hidden` variant that drops the middle column. The toggle sits at the top of the filter column (first attempt:
bottom of the column, next to "Reset filters" — scrolled out of sight on a normal screen, so moved). The choice is
kept in `localStorage` (`sliderule.listHidden`). At 900px and below everything stacks as before; the pane is hidden
when printing. Max page width went from 1500px to 1700px to fit the extra column.

**`sliderule serve --reload`.** The server mounts `web/` with `StaticFiles`, so HTML/JS/CSS edits already show on a
page refresh; only Python edits need a restart. uvicorn's reloader re-imports the app in a new process, and
`main()` configures settings and the custom-equations folder before running the command, so a plain
`create_app()` would have lost both. `cli._reload_app` is a factory that redoes that setup, and `--equations-dir` is
passed to it through `SLIDERULE_EQUATIONS_DIR`. Checked by touching `server.py`: uvicorn logged a reload and
`/api/meta` kept answering. Not tested: `--reload` together with `--equations-dir`.

**Verification.** Layout and toggle checked in the browser pane; CLI/server tests pass (28). The full suite was not run.

**Dead ends / notes.**
- The browser pane's `preview_start` wants a `.claude/launch.json` at the session root, not the repo; ran the server
  directly instead.
- `sliderule` was not installed anywhere on the machine (no fastapi/uvicorn either); verification used a throwaway
  venv outside the repo. Setup: `pip install -e '.[server]'`.

## 2026-10-28 — Merge System Design into the Calculations tab

**Goal.** One workspace instead of two tabs: the Calculations tab gets a "Single calculation | System" mode switch;
System shows the canvas where the calculation detail was. The canvas must keep its blocks across mode switches until
the user presses Clear.

**What changed.**
- `#design` (the editor host) now lives inside `#view-calc`; the separate System Design tab and `#view-design` are gone.
  `#/design` still works and opens the Calculations tab in System mode; `#/calc/<id>` and `#/` open Single mode.
- The editor's own palette and search box were removed; the shared filters + list feed it. In System mode a card click
  adds the block near the middle of the canvas, and cards are draggable (same `application/x-sliderule-calc` drop type).
  Cards are now `div role="button"` rather than `<button>`: Firefox does not start drags from buttons.
- `system.js` exposes `addCalc(id)`; `refreshPalette()` became `refreshDefinitions()` (re-reads definitions of blocks
  already on the canvas after My equations changes).
- Persistence needed no new code: the editor is built once and only hidden (`hidden`), so state stays in memory, and it
  already saves itself to `localStorage` (`sliderule.design.graph`) on every change. Only Clear empties it.
- Layout: canvas + 360px inspector in the third column; at <=1100px the inspector stacks under the canvas.
- e2e Playwright scripts (`tests/e2e/`) updated to the new selectors. Playwright is not installed here, so they were
  NOT run; the same flows (add by click, add by drag, mode round trip, Clear, wire survival) were driven by hand in the
  browser pane and passed.

**Found, not fixed (pre-existing).** After a full page reload the canvas restores its blocks but draws no wires,
although the saved graph (`localStorage`) still contains them. Reproduced on the code before this change, so it is not
caused by the merge. Switching modes within a session keeps wires fine.

**Notes.** With filters (320px) + list (300px) + inspector (360px) the canvas is narrow below ~1400px wide; the list can
be hidden with the existing toggle.

## 2026-10-28 — Fix: System Design wires missing after page reload

**Goal.** After a full reload the canvas restored its blocks from `localStorage` (`sliderule.design.graph`) but drew no
wires, though the stored graph still held them (e.g. `b1.rho -> b2.rho`). The earlier entry logged this as pre-existing.

**Debugging.** Reproduced with `sliderule serve` in the browser pane: 3 `.node`, 36 `.port`, 0 `g.wire`, no console
errors. Selecting a block (which calls `drawWires()` synchronously) made the wire appear at once, so `drawWires`,
`portPos` and `portEls` were fine (ports were connected, ids matched). Temporary instrumentation of `drawWires` showed
it was never called during load. The pane reported `document.visibilityState === "hidden"`, where
`requestAnimationFrame` never fires. With rAF polyfilled by `setTimeout`, 8 draws ran and the wire appeared. Also not a
dead end: `renderNode`/`portEls` bookkeeping and the `renderAll`/`recheck`/`evaluate` ordering were checked and are
correct.

**Root cause.** Every redraw on the load path (`renderAll`, `refreshNode`, `evaluate`, `changed`, `loadGraph`'s `fit()`
and `onShow`) was deferred with `requestAnimationFrame`. rAF is suspended whenever the page is not being painted
(background or restored tab, hidden pane), so the only redraws never ran and the SVG stayed empty. The deferral was
unnecessary: `portPos` uses `getBoundingClientRect()`, which forces layout synchronously.

**Fix.** `system.js`: replaced `requestAnimationFrame(drawWires)` with `drawWires()`, `requestAnimationFrame(() => fit())`
with `fit()`, and `onShow`'s rAF with a direct call (6 one-line changes, no other logic touched).

**Result.** In the same hidden-tab condition: reload on System -> 1 wire; System -> Single -> System -> 1 wire; reload
on Single, then first switch to System -> 1 wire, path coordinates sane. Not covered: Playwright e2e (not installed
here), and a visible tab already worked before the fix (rAF fires there), so the earlier visible-tab run could not
distinguish the two.

## 2026-10-29 — LiveCalc tab

**Goal.** A separate LiveCalc tab that works as a calculator and plots graphs; text and values shown as Markdown while typing; the last 30 entered
calculations visible; a toggle for showing steps; select a typed equation and send it to My equations.

**Design.** Details in [docs/LIVECALC.md](docs/LIVECALC.md) and the architecture section. The engine part is `src/sliderule/livecalc.py`: a hand-written tokenizer
and recursive-descent parser (no `eval`), a quantity type that keeps SI values plus a display unit, statements for values, variables, functions, equations, `to`
conversions and `plot`. It is **stateless**: the browser sends the last 30 entries plus the draft on each keystroke (~10 ms for 30 entries, 69 KB with six plots),
so the same two API methods (`livecalc_eval`, `livecalc_to_equation`) serve FastAPI and Pyodide. The UI is `web/js/livecalc.js` with a new safe Markdown renderer
(`markdown.js`, DOM nodes only) and `plot.js::xyPlot`; My equations (`custom.js`) accepts a draft through `S.customDraft` (`#/mine/new?draft=1`).

**What went wrong on the way (and how it was resolved).**
* First draft treated any identifier as a variable *or* a unit by scope, so after `m = 5 kg` the `m` of `9.81 m/s^2` became the variable (result in kg²/s²). Rule
  now: a name after a number is a unit, `/name` continues a unit, and a note is attached when a variable was shadowed. Bare names in lines with `=` are variables
  (otherwise `s` in `v^2 = u^2 + 2*a*s` became seconds). Noted trade-off: `10 m / t` with `t = 3 s` reads `t` as tonne (with a note).
* Semantic errors (`F to lbf` with the wrong dimension) were hidden as "text" by a too-eager prose heuristic; only *syntax* errors can now be prose. Prose that
  contains digits or odd characters ("see $w L^2/8$ — span 6 m") was flagged as an error until unknown characters became tokens and the "two words in a row" rule
  was added.
* `5 kg * 9.81 m/s^2` showed `kg*m/s^2`: results built only from SI base units now take the named unit. `N*m` is deliberately **not** turned into `J` (torque).
  Steps for `M to kN*m` first said "54000 J" for a moment: the SI form is now derived from the unit used (`N*m`).
* The formatter hook removed an import (`compose`) I only used later; caught by the tests.
* Literal assignments (`m = 80 kg`) got a pointless one-step "working": suppressed. "→ My equations" is offered only for formulas.

**Verification.** `tests/test_livecalc.py` (arithmetic and units, conversions, offset temperatures, variables/functions/`ans`, prose vs errors, equations, steps,
plots, safety and limits, send-to-My-equations including the editor's own `custom_validate`). In the browser pane: live preview while typing, history across a
reload, the 30-entry cap (37 entered -> newest 30 kept), steps toggle, graph with unit-labelled axes, light and dark themes, and the full path from a typed
equation to a valid prefilled My equations form (`F = m*a` -> unit N/kg/m·s⁻², example 784.8 N). Not run: Playwright e2e (not installed here); no e2e script was
written for LiveCalc.

**Known limits.** Variables defined only in entries older than the last 30 are forgotten. Percent (`%`) and implicit multiplication of two names (`a b`) are not
supported. `x*y` in a plot with several unknown names asks you to give all but one a value.

## 2026-10-29 — Physics and chemistry: pilot set (49 calculations)

**Goal.** "Add all equations in the physics and chemistry domains that are not already present." "All" has no end (thousands of equations, each needing units, a worked
example and a test), so the work was agreed as three stages: **pilot (~40-50), then a core undergraduate set (~150 physics + ~100 chemistry), then a broad set**
(quantum, statistical mechanics, spectroscopy, organic/inorganic). New top-level disciplines **Physics** and **Chemistry**, with the relevant existing engineering
disciplines also listed on each calculation. This entry is stage 1.

**What was added.**
- Taxonomy: `physics` (Classical Mechanics, Thermodynamics and Statistical Physics, Waves and Acoustics, Optics, Electricity and Magnetism, Modern Physics, Gravitation
  and Astrophysics) and `chemistry` (General, Physical, Analytical, Atomic Structure and Spectroscopy). Like `architectural` they are not in
  `docs/reference/disciplines.txt`, so the reference-file test now excludes all three.
- 34 physics + 15 chemistry calculations in `library/physics.py` and `library/chemistry.py` (kinematics, collisions, incline, circular motion, oscillators, rolling,
  angular momentum; blackbody, kinetic theory, heat capacities, adiabatic, entropy; Doppler, standing waves, beats; Snell/Brewster, critical angle, thin lens, slits, grating;
  Coulomb, Gauss, Biot–Savart, cyclotron, induction; photoelectric, de Broglie, Compton, Bohr, relativity, particle in a box; Newtonian gravity, Schwarzschild; solutions,
  stoichiometry, dilution, gas laws, colligative; van der Waals, Gibbs/van 't Hoff, rate laws, Eyring, Clausius–Clapeyron, calorimetry; weak acids/bases, buffers, Ksp;
  diatomic vibration/rotation). New constants in `_common.py`: Avogadro, electron mass, Rydberg, Bohr radius, Wien b.
- **Duplicates were not added.** Projectile range, Carnot, escape velocity, circular orbit, photon energy, Beer–Lambert, Henry's law, Arrhenius, Nernst, Faraday, pendulum
  period, radioactive decay and about 20 more already existed under engineering names; 32 of them are *cross-listed* under the new sub-disciplines through `RETROFIT`.
  Result: Physics 65 calculations, Chemistry 34 (catalogue 441 -> 490, 227 sub-disciplines).

**Verification.** 49/49 examples solved cleanly on the first full run after two fixes. `tests/test_physics_chemistry.py` recomputes every result from the textbook formula in
plain Python with the constants typed out again, plus physical identities (virial theorem, Ampère's definition of the ampere, Wien's constant from Planck's law, energy-momentum
relation, first law at constant pressure, SUVAT consistency, equilibrium expression of a weak acid, the Sun's Schwarzschild radius, HCl's 2990 cm⁻¹ and 10.59 cm⁻¹, H-alpha at
656.11 nm ...). Library invariants (dimension check on load, unit-choice independence), taxonomy and coverage tests pass.

**Problems met and what they taught.**
- Two examples failed because a variable's `default` only seeds the form; `solve` does not apply it. Examples must supply every input (emissivity, transmission coefficient).
- My first tests had three wrong *expectations*, not wrong code: the Planck value is stored per metre (SI) not per nm, the ion product arithmetic was off by 1e-3, and I
  assumed a "flagged" warning where the engine fails the evaluation.
- **Engine improvement.** When physics is impossible (total internal reflection, v > c, a block that cannot slide) the engine said only "no real-valued result" and the
  validity message I had written was never shown, because validity was checked only after a successful evaluation. `hint_validity()` in `core/engine.py` now adds the violated
  validity message as an info diagnostic on those failure paths (additive; the full suite is unchanged). Seen in the browser: "Total internal reflection: no refracted ray exists
  at this angle (violated: n1*sin(th1) <= n2)".
- Solving the van der Waals equation for V needs a search range: the automatic scan meets the pole at V = n·b. Documented in the calculation's assumptions and covered by a test.
- Left unfixed: `Min` in the limiting-reagent calculation makes the extent of reaction non-invertible (solving for a mass from a yield works, solving "which reagent" does not).

**Next.** Stage 2 (core undergraduate set), then stage 3. The pilot is meant to be reviewed first for format, units and quality.

## 2026-10-29 — Physics and chemistry: core undergraduate set (stage 2)

**Goal.** Stage 2 of the physics/chemistry plan: reach roughly 150 physics and 100 chemistry calculations, skipping duplicates of what the app already had.

**What was added.** 117 physics (`physics_core_a/b/c.py`: mechanics, fluids, thermodynamics; waves, optics, electromagnetism; modern, nuclear, solid-state, gravitation) and 85 chemistry
(`chemistry_core_a/b.py`: general, thermodynamics, electrochemistry, kinetics, physical; analytical, spectroscopy, inorganic, organic). Totals: physics 152, chemistry 100, catalogue 693.
New sub-disciplines: Fluid Mechanics, Atomic and Molecular Physics, Solid State Physics, Nuclear and Particle Physics; Chemical Thermodynamics, Chemical Kinetics, Electrochemistry,
Solid-State and Inorganic Chemistry, Organic Chemistry. Shared builders and references live in `library/_pc.py`.

**Verification.** `tests/test_pc_a.py`-`test_pc_e.py` check every example against an independent formula (constants retyped) and fail if any output lacks a check, plus physical
identities and benchmarks (Cu Debye temperature 340 K, Mercury perihelion 42.98″/century, D-T Q 17.589 MeV, argon viscosity, Daniell cell K 1.5e37, ice Clapeyron slope,
LiFePO4 169.9 mAh/g, NaCl lattice energy and Born-Haber cycle, CO bond length 1.128 Å). Full suite on 3.12 plus the new tests on 3.10 and 3.13.

**Problems met.**
- Dimension checking caught hidden constants (331.3 m/s, Julian century, 10 g/L for % w/v), an unused variable, a wrong heat-capacity unit and unknown units (MRayl, urad); all fixed by explicit `C()` constants and units. A Python keyword (`as`) cannot be a variable key.
- Real formula bugs found by review: Bragg angle returned the other branch (now `asin`), Bekenstein-Hawking entropy factor, battery specific capacity converted twice, a displacement-current example 1000x off.
- Dead ends: several batches were first written with placeholder tails (`if False` hacks, half-finished Moseley/Rutherford/Eyring entries) that had to be rewritten; lesson: write complete entries. Several test failures were wrong test expectations (tuple-assignment order, tolerances, SI units of mg/L).
- **Engine gap found by the full suite:** the file-format round-trip validator rejected `acosh` (relativistic rocket). `asinh`, `acosh`, `atanh` added to the function table in `core/model.py`.

**Next.** Stage 3 (the broad set: quantum, statistical mechanics, advanced spectroscopy, organic/inorganic depth) and more `RETROFIT` cross-listing.

## 2026-10-29 — Physics and chemistry: broad set (stage 3)

**Goal.** Stage 3 of the plan: the broad set (quantum and statistical mechanics, advanced classical mechanics, plasma and particle physics, astrophysics, quantum chemistry,
photochemistry, polymers, colloids, biochemistry, atmospheric chemistry, organic/inorganic depth), then cross-listing of what the app already had.

**What was added.** 93 calculations: `physics_broad_a.py` (13 quantum + 12 statistical mechanics), `physics_broad_b.py` (5 analytical mechanics, 6 plasma, 3 particle, 7 astrophysics),
`chemistry_broad_a.py` (6 quantum chemistry, 4 photochemistry, 9 polymer), `chemistry_broad_b.py` (7 colloid, 8 biochemistry, 5 atmospheric, 8 organic/inorganic/physical).
New sub-disciplines: Quantum Mechanics, Statistical Mechanics, Analytical Mechanics, Plasma Physics; Quantum Chemistry, Photochemistry, Polymer Chemistry, Colloid and Surface
Chemistry, Biochemistry, Atmospheric Chemistry. About 40 existing calculations (Michaelis–Menten, Goldman, Lennard-Jones, Stokes–Einstein, Carothers/Flory–Fox, rubber elasticity,
Langmuir adsorption, Scherrer, CO2 forcing, quantum well/oscillator/tunnelling ...) were cross-listed through `RETROFIT` rather than duplicated. Catalogue 693 -> 786
(physics 198 first-listed / 248 including cross-lists; chemistry 147 / 188).

**Duplicates caught late.** I planned a large-amplitude pendulum, Michaelis–Menten, Goldman, CO2 forcing and Scherrer before checking the library; the first was already written and had to
be removed (`mechanical.dynamics.pendulum_large_amplitude_period` exists), the others were dropped before writing. Lennard-Jones, Stokes–Einstein, Carothers and rubber elasticity
overlap partly with existing entries; mine were kept because they add outputs (Boyle temperature and force; rms displacement; stoichiometric imbalance, dispersity and gel point;
stress-stretch), and the originals were cross-listed. Lesson: grep the library for the topic before designing an entry.

**Verification.** `tests/test_pc_f.py`-`test_pc_i.py` (independent formulas, every output checked) plus benchmarks: hydrogen 2p fine structure 10.95 GHz and lifetime 1.6 ns, helium
variational -77.5 eV, CMB 411 photons/cm3, LHC 13 TeV, Z-boson lifetime 2.6e-25 s, Chandrasekhar 1.43 Msun, flat LCDM age 13.8 Gyr, GW150914 chirp mass 28.1 Msun, HD 209458 b K = 85 m/s,
Debye length 3.04 nm at 10 mM, lysine pI 9.74, ATP -53 kJ/mol, rain pH 5.6, 1 DU = 2.69e16 /cm2, cyclopropane strain 115 kJ/mol. Full suite passes on 3.12; new tests on 3.10 and 3.13.

**Problems met.**
- Junk placeholders again slipped into first drafts (`pc_dummy`, `Gyr_dummy` units; an `if False` expression); caught by the unit parser and removed. Missing units (`Mrad`, `Grad`, `kyr`, `dL`) re-expressed.
- **Variables are positive symbols by default**: `Piecewise((1, nu > 0), (0, True))` with `nu` unsigned collapsed to 1 at parse time (a molecule with no unpaired electrons came out paramagnetic).
  Fixed with `signed=True` (also for the Flory-Huggins chi, which may be negative); documented in ARCHITECTURE.md.
- Dimension checker rejected `p^nH` (variable exponent of a dimensional quantity): rewritten as `(p/p50)^nH`. It also caught `Te*qe` where Te was already in eV.
- Physics mistakes found in review: double-pendulum eigenvalue formula (derived (1+mu) +- sqrt(mu(1+mu)) instead of my first guess), LCAO example with beta too small (bonding level above alpha), bare `180` read as radians in a ring-strain angle (use pi).
- The design-export test runs every calculation as a standalone script; `Eq()` inside `Piecewise` is not available there, so equality tests use `Abs(x - 18) < 1/2`.
- Test mistakes (mine): Rabi pi pulse time, positive-N1 Flory-Huggins critical chi for two polymers is ~0 (not 1/2), SI units of mg/L, boundary of Young's equation at exactly |cos| = 1.

**Next.** Possible stage 4: remaining organic reaction mechanisms, thermochemistry tables, transport phenomena, more astrophysics. Nothing is pushed yet: branches
`physics-chemistry-core` (stage 2) and `physics-chemistry-broad` (stage 3, stacked on it) are local.

## 2026-10-29 — Math blocks in the system builder

**Goal.** Drag-and-drop blocks for basic arithmetic in System Design. Add/subtract blocks accept only the unit type of the first (or only) wire connected to them and reset when
no wire is connected; multiply blocks combine or cancel units.

**Design.** Rather than a second kind of evaluation, a math block is converted into an ordinary generated `Calculation` (`design_math.py`), so validation, solving, steps and all four
exports work unchanged (an export of a graph with math blocks also passes the generated script's self-check). The only new logic is typing (`resolve_types`): add/subtract lock to the earliest
wire in the graph's wire list (either side of the block), multiply/divide derive the output dimension from the inputs. Division was added beside multiplication because dividing is how units cancel
(N / N, m / s). Because the rule belongs to the engine, the editor calls a new `design_math` RPC after each edit instead of mirroring the logic in JavaScript, and caches the port types for the
synchronous drag-time checks.

**Editor.** + − × ÷ chips in the canvas toolbar (drag or click), a lock badge on each block, grey "open" ports until a type is known, an inspector with typed values (unit pickers once the type is
locked, free units while open), +/- input buttons for add and multiply (2 to 8), values cleared when a lock changes. Verified in the browser: turbine power + 500 kW feeding the electrolyzer
(kW converted on the wire), a mismatching wire refused with the reason, the lock released after the last wire was removed, 5 N x 2 m shown as 10 J.

**Problems met.**
- `pkill -f` with the pattern also matched my own start command (the same words appear after it in the command line) and killed the shell; the bracket trick only works if the pattern text is not elsewhere in the line.
- A first draft of `port()` in `math_calculation` was a garbled `a or b and (c or d) or e`; rewritten as `a or b or c`.

**Not done.** Output units default to SI (pick another in the inspector); no inference backwards through a multiply (a known product does not fix a missing factor); subtracting two absolute temperatures still yields an absolute temperature.

## 2026-10-29 — Comments on blocks in the system builder

**Goal.** Let a user attach a comment to any block of a system.

**Done.** A `comment` string on every block (calculation or math): a "Comment" panel with a textarea in the inspector, a two-line preview with a speech-bubble under the block's title, saved in the
graph file and the autosave, printed under the block heading in the LaTeX/Markdown/HTML exports, validated in `design._index` (text, at most 2000 characters, else `BAD_BLOCK`). Typing re-renders only the
block, not the inspector, so the textarea keeps focus. Checked in the browser, including survival of a page reload; test added to `tests/test_design.py` (ignored by solving, exported in three formats, validated).

**Decisions.** One comment per block (not threads, no author or time); the Python export first skipped it (the script reproduces numbers); on request it now writes the comment as `#` lines under each block's header in the equations section (line breaks kept, control and line-separator characters turned into spaces so a comment cannot end its own line and inject code; a test executes the script to prove it still runs and reproduces the reference values).

## 2026-10-29 — Save a system as an equation

**Goal.** Let a system built in System Design be saved as an equation of its own (in My equations).

**Design decision.** Two ways to turn a graph into an equation: its closed-form outputs (already computed for the export) or its complete system of equations. Closed forms are compact but
cannot be solved backwards reliably, hit the 300-character expression limit as soon as two blocks are chained, and break on blocks without a closed form. So `design_equation.py` keeps the complete
equations, merges wired ports into one variable and lets the existing engine do the solving in any direction. Results: wind turbine to electrolyzer is 8 equations in 19 variables; solving the saved equation for
the wind speed that yields a given hydrogen mass returns exactly 10 m/s.

**Details.** Same physical constant in two blocks = one variable; clashing keys qualified by block id; all computed quantities are outputs by default, and one that is unticked becomes an input with the value
the system computed (otherwise the saved block would ask for a value nobody has); block comments become assumptions; the draft is checked with `calc_from_dict` and test-solved against the system's results before the
dialog even opens. UI: *Save as equation…* in the canvas toolbar opens a dialog (name, description, outputs, warnings) and links to the saved equation. Verified in the browser (saved, opened in Calculations,
then deleted again; the live server writes to the user's real equations folder, so test artefacts must be removed).

**Problems met.**
- First version made only the unconsumed outputs outputs; the saved calculation then used as a block demanded values for the intermediate quantities (an input with no example). Fixed as above.
- My `pkill`/`ps | grep` start-up commands again matched their own command line and killed the shell (twice more). Find a server by its port (`ss -ltnp`) instead. The running server was the user's own `--reload` one, which had already picked up my changes.
- Test mistakes: expected 1081.2 kg (that figure included a 500 kW add block from an earlier test, the plain example gives 867.9 kg); blocks added by hand need `values` or the system does not evaluate.

**Not done.** ODE/event/table blocks; validity limits; re-saving over an existing equation (each save makes a new id).

## 2026-10-29 — LiveCalc: function search and plotting history functions

**Goal.** (1) A search that shows the functions available in LiveCalc with examples of how to use them. (2) For functions in the history that can be drawn in two or three dimensions, a checkbox that adds them to the plot.

**Function search.** `livecalc_help.py` holds the catalogue as data (31 entries: every built-in function, `pi` and `e`, the power operator, `to`/`in` conversion, assignment, function definition, `plot`),
each with one to three examples. The examples are **run by the engine when the catalogue is requested** (`livecalc_functions` RPC), so the result shown beside `sin(30 deg)` cannot disagree with what
typing it gives, and a test fails if any example stops working or a function is missing from the list. The editor filters client-side on name, signature, description, topic and search words (so `angle`
finds the trigonometric functions, `convert` finds `to`); the user's own functions are added to the results from the live variable list. Clicking an example uses it.

**Plotting.** The history shows a *2D plot* box beside a one-value function and a *3D plot* box beside a two-value function. The ticked names are plotted together by a new `livecalc_plot` RPC (the session is rebuilt
from the history, so the last definition wins and removed functions drop out). Curves share an x range and are split into graphs by unit; surfaces are sampled on a 41 x 41 grid and grouped by unit. Each function that fails is
reported by name without stopping the others. 3D is a small canvas renderer in `plot.js` (painter's algorithm over the quads, drag to rotate, wheel to zoom, keyboard rotate, theme colours read from CSS) because the project
carries no charting library and the browser-only build must stay light.

**Problems met.**
- The browser cached the old module scripts, so the new panel did not appear until the files were re-fetched with `cache: "reload"`; a reminder to check that before suspecting the code.
- Storage keys are namespaced (`sliderule.liveEntries`); my first test seeding used the bare key and silently did nothing.
- First 3D view clipped its own corner labels; scale and centre were adjusted after looking at the picture. The refresh of the plot ran on every keystroke and would have reset the rotation and the range boxes' focus,
  so the plot only refreshes when the history, the ticked functions or the ranges change.
- A test expected two separate 3D views for two functions that both produce areas (they correctly share one).

**Not done.** `sqrt(x)` over a range that includes negative x is reported as an error rather than drawn with a gap (the existing `plot` command behaves the same); no per-function ranges; no export of the 3D view.

## 2026-10-29 — LiveCalc: plots on the right

**Goal.** An option to switch between the current layout (graphs inline in the history) and keeping the plots in a column on the right with the history on the left.

**Done.** A *Plots: In the history / On the right* switch in the toolbar (remembered in `localStorage`). The page body is now two columns (`live-left`: variables, history, preview, input; `live-right`), and the right column is
hidden unless the layout is "side". In side mode the ticked-function Plot panel moves into the right column (the same DOM node is re-parented, so a rotated 3D view keeps its angle), `plot` commands in history and preview
leave a placeholder under their formula, and a Graphs section on the right shows their figures (preview first, then newest first). The page also widens to 1560 px; below 900 px the columns stack. Front-end only, so no new
Python tests; checked in the browser (switching both ways, counts of figures in each column, persistence across a reload).

**Decision.** "The plots" is taken to mean both kinds, the graphs of `plot` commands and the ticked-function plots, so that everything graphical is in one place when the option is on.

## 2026-10-29 — System export to MATLAB and Excel

**Goal.** More export options for a system: MATLAB code, and Excel sheets with the formulas embedded.

**Design.** Both exporters share a plan (`design_code.build_plan`): free inputs and constants in SI plus, per block in dependency order, one step per computed quantity (the solver's own causal ordering, wires substituted),
each with SlideRule's value attached. MATLAB: sympy's Octave printer with plain scalar operators and `Piecewise` hoisted into if/elseif/else blocks. Excel: a purpose-written converter to Excel syntax, formulas referring to
inputs and results by defined names, so a cell reads `=PI()*Dr__b1^2/4` and a wire is simply a reference to the upstream result; Inputs / Calculations / About sheets, yellow editable cells, a Check column. The `.xlsx` is
assembled with `zipfile` and hand-written XML (inline strings, cached values, `fullCalcOnLoad`): no new dependency and it works in the browser build. The browser downloads it from a base64 field.

**How it was checked without MATLAB or Excel.** (1) A back-translator (written separately from the exporter) turns the generated formulas into Python; a one-off sweep over every sixth to third library calculation
(about 700 single-block systems) reproduced SlideRule's value for every exportable quantity; the suite keeps a sample of it. (2) A randomised test compares the Excel converter with sympy on awkward expressions (negatives,
rational coefficients, nested powers, Piecewise, atan2, Min/Max, floor/ceiling). (3) LibreOffice (installed here) recalculates the workbook after every cached value is overwritten with 0, and the Check column reads OK.

**Bugs the checking found.**
- Unit conversion: I wrote `SI = value*factor + offset`; the registry's convention is `(value + offset)*factor`. It only shows with offset units (a constant of 60 degF in a gas-volume-factor block gave 493 K instead of 289 K);
  the sweep caught it, and a regression test uses that block.
- Excel's `ATAN2` takes `(x, y)`, sympy's `atan2` takes `(y, x)`; my first test translator had the same mistake, so it reported a mismatch that was the test's.
- sympy simplifies `atan2` of positive symbols to `atan(y/x)`; fine for positive quantities, and the converter handles real symbols properly.
- `log10`, `log2`, `erfc` are SlideRule functions the stock Octave printer does not know; `elliptic_k` maps to `ellipke`.
- Excel names ignore case (`P` and `p` in one block would collide): de-duplicated case-insensitively.
- A test helper evaluated both arms of an `IF` eagerly and failed on `sqrt` of a negative in the unused arm; Excel's IF is lazy, so the helper now is too.

**Not supported (reported, with the block named).** Differential equations, data tables, quantities found by root-finding or coupled equations, `Sum`, `uppergamma`, `erfinv`, `loggamma` (Excel; MATLAB has some of these but they were not
needed). About 8 percent of single-block library calculations fall in this group. The MATLAB script was not run in MATLAB or Octave (neither is installed); it uses plain scalar syntax, and the translated-back check covers its arithmetic.

## 2026-10-30 — Deepening the thinnest sub-disciplines (89 calculations)

**Goal.** A coverage review found 45 of 245 sub-disciplines with exactly one calculation (mostly the newer fields). The plan was to bring each to at least three with field-specific calculations, and to add a
guard test so the floor cannot silently fall back.

**What was added.** `thin_a.py`, `thin_b.py`, `thin_c.py` (30, 29 and 30 calculations, two per formerly single sub-discipline; shared builder `_thin.py`): additive, agricultural, reinforcement learning, biomedical,
chemical process (corrosion, pulp and paper, textiles), civil (pavements, wind), climate (capture, geoengineering); knowledge and usability engineering, security, data engineering (BI, architecture, warehousing,
streaming), ecology, industrial ecology, composites, electronic materials, welding, robotics and sports; metamaterials, nanomedicine, BCI and neuromorphic, quantum communication, HRI, service and swarm robotics,
smart infrastructure, exoskeletons, smart textiles, soft actuators, space debris. Catalogue 786 -> 875. No sub-discipline is a single calculation any more (the minimum is 2, and 50 sit at exactly 2), and
`test_every_subdiscipline_has_at_least_two_calculations` enforces it. Reaching three everywhere took 50 more (see the 2026-10-29 library-coverage entry).

**How the equations were checked, and what that does not prove.** Every calculation passes the engine's dimension check, has an example that solves cleanly, and has a test that recomputes the example in SI with an
independent re-statement of the formula (`tests/test_thin_a.py`-`c.py`), plus benchmark values and limiting cases (CVSS 9.8 for the textbook case, Nielsen's 85 % with five users, pi/ln2 in the four-point probe,
Rosenthal width near 116 um for 316L, n = -1 giving the same angle, ...). **The independent re-statement comes from the same author with the same knowledge, so it catches slips (units, transcription, positive-symbol
traps) but not a formula remembered wrongly or a reference cited inaccurately.** Not verified: the literature citations (written from memory, no source was opened), the typical parameter values in examples, and
every modelling simplification (each is stated in the calculation's assumptions). A subject-expert review and a pass that opens each cited source is the remaining step.

**A duplicate slipped in.** `Password entropy and brute-force time` already existed (`computer.security.password_entropy`); my version was caught only by the unique-name test in the existing suite, not by checking the library first, and was removed (89 new calculations remain). A tag-overlap scan afterwards found no other duplicate; `data.architecture.replication_availability` overlaps partly with `computer.cloud.composite_availability` (it adds quorums and downtime) and was kept.

**Problems met.** The positive-symbol trap again (`imp <= 0` in the CVSS score collapsed to false until the variable was signed); unit conventions for `h/yr`, `min/yr` and `h/day` constants (they are dimensionless in SI,
so annual and daily quantities must be built from them rather than from hours); `Piecewise` thresholds on percentage quantities (0.4 % is 0.004 in SI); a Webster constant written as `5 s` inside an equation (not allowed:
declare a constant); and examples whose own validity warning fired (consensus step size) or whose numbers were physically silly (a 0.18 W heated garment), found by reading the printed values rather than by any test.
After a review question I corrected two statements that overreached: the BM25 note (the Okapi IDF is smoothed, the one used is ln(N/n)), and four citations I could not stand behind (replaced by ones I am confident of).

## 2026-10-30 — Source check of the 89 new calculations' citations and key claims

**Goal.** After the question "are any of the new equations hallucinated?", open the sources behind the citations and the load-bearing claims instead of relying on memory.

**Method and results.**
- **Journal articles (47 distinct):** looked up in Crossref by journal, volume, first page and year. 44 matched exactly; the other three (Pirandola et al., Mooney et al., Hansen et al.) were found with the right title, journal, volume and year but their pages are article numbers, which Crossref returns differently, and were confirmed on that basis. Every article I cited exists and says roughly what I used it for.
- **Books (43):** looked up in Open Library and Crossref. One was **invented**: "Klein & Lewis, Orbital Debris and Space Debris Mitigation" does not exist (replaced by Klinkrad, *Space Debris: Models and Risk Analysis*, Springer 2006). "Schmidt-Bleek, The MIPS Concept" is not a real title (replaced by *Wieviel Umwelt braucht der Mensch? MIPS*, 1994). Albright's greenhouse book could not be found and was replaced by the ASABE EP406 standard. Pierce (1937) now carries its journal reference.
- **Chapter and section numbers in book citations were removed**: I could not verify any of them, and several were probably wrong. Standards keep their section references (ISO/TS 15066 Annex A, CVSS 3.1 Sec. 7.1, ASCE 7-22 Ch. 26-29, AISC Part 8).
- **Claims checked on the web:** ISO/TS 15066 transient contact force F = v sqrt(k mu) with the reduced mass: confirmed (the example now uses the standard's hand-and-fingers values, 0.6 kg, 75 N/mm, 140 N, instead of an invented 40 kg body region). Critical mean degree 4.512 for 2-D random geometric graphs: confirmed as a numerical estimate (4.5122), not exact (text now says so). Aerosol forcing -25 W/m2 per unit AOD: found in the GISS modelE paper, but later estimates are about -21 and the literature spans -15 to -25; the citation was changed from "Hansen 2002", which I could not tie to the -25 figure, to the modelE paper, and the note gives the range. **Rosenthal melt-pool width:** the search found the underlying thin-plate relation but not my closed form; it is my own limit of that relation (conduction term dropped), so the calculation now says it is derived, and published comparisons show tens of percent error.
- **Not re-checked against a source:** the other formulas and the typical values in the examples (they are textbook-standard as far as I know, e.g. Stern-Geary, Webster, Pcm, Halpin-Tsai, Kelly-Tyson, UARL 18/0.8/25, KLM operator times, BB84 key fraction), and the chapters/pages of the standards. A subject-expert review remains the right last step, and the same source check has not been done for the physics and chemistry calculations from the earlier stages.

**Lesson.** Citations written from memory are the likeliest place for an invented fact: 1 of 43 books and 3 of ~90 attributions were wrong or unverifiable, against 0 of 47 articles that I could check mechanically. Check references while writing, not afterwards.

## 2026-10-29 — Library coverage: every sub-discipline at three or more, and physics/chemistry stage four (71 calculations)

**Goal.** After PR #57 was merged: finish the "library coverage items" — raise the 50 sub-disciplines that had exactly two calculations to three, add a fourth batch of physics and chemistry (organic
mechanisms, thermochemistry tables, transport phenomena, electrochemistry, astrophysics, plasma and particle physics), and guard against duplicates (done earlier: `scripts/check_duplicates.py`).

**What was added.** `library/thin_d.py` (50 calculations, one per sub-discipline that sat at two) and `library/thin_e.py` (21 physics/chemistry calculations), registered in `_MODULES`; tests
`tests/test_thin_d.py` (50 independent-formula cases plus benchmarks) and `tests/test_thin_e.py` (21). Catalogue 875 -> 946. The floor test is now
`test_every_subdiscipline_has_at_least_three_calculations`; `docs/COVERAGE.md` was regenerated.

**Problems met and fixed.**
- A variable called `Lt` (tube length) broke the validity expression `Re < 2300`: the safe parser rewrites `<` into sympy's `Lt(...)`, so a symbol with that name is "not callable". Renamed (avoid `Lt`, `Gt`, `Le`, `Ge`, `Eq`, `Ne`).
- Angular speed in SI is rad/s (`rpm` = 0.1047 rad/s): the extruder drag flow and the journal-bearing Sommerfeld number were off by 2π until the formulas were written for ω (π D² ω h sinφ cosφ / 4; S with N = ω/2π). Caught while writing the independent test, not by the solver.
- Dimension errors at load: ROSI payback multiplied by a "year" constant, and the pulsar field used the Gaussian-unit formula (SI: B = sqrt(3 μ0 c³ I P Ṗ / 8π³R⁶), the polar field); synchrotron loss needs e², not e.
- A variable named `pi` (cloud interruption probability, SpO₂ perfusion index) would shadow the constant: renamed. A variable `I` (current) would be the imaginary unit: renamed.
- Constants typed from memory were corrected against the formula in the test (Murrell's 5 kcal/min = 348.9 W with the IT calorie; resting 104.67 W).
- Examples were read after solving: nuclear migration first gave a 2-million-year travel time and 0 % survival, the sequencing example covered 100 % of the genome, so the inputs were changed to values that show the formulas working.

**Result.** All three duplicate checks report 0 suspect pairs; the full suite passes on 3.12 and the new tests on 3.10 and 3.13; every sub-discipline now has at least three calculations. **Citation check (same day).** Journal articles were looked up in Crossref (volume, first page and year must match): 23 of 27 matched directly; Krantz 2019, Degen 2017, Brønsted & Pedersen 1924 and Wigner 1932 matched by title
and journal with the page recorded as an article number or a page range (all four exist; volume `108U`/`19B` in Crossref). Ranz & Marshall (Chem. Eng. Prog. 48, 141, 1952) is not in Crossref; the paper is real
but this one is unverified. Conference and arXiv papers (SGDR, Goyal et al., Pope et al., BLEU, Böhme et al., Kaul et al., Sonnenreich et al.) were confirmed by web search or Crossref; Sonnenreich et al. is WOSIS/ICEIS 2005,
pp. 239–252 (the log and reference said 2006, which is the later journal version), now corrected. Allen & Eggers NACA Report 1381 (1958) confirmed, including the result that peak deceleration does not depend on the
body. The Cepheid coefficients (a = −4.05, slope −2.43 in M_V = a + b(log P − 1)) were read in the Benedict et al. paper (arXiv astro-ph/0612465). 49 of 54 book titles matched in Open Library; the five misses
(Szeliski, Haacke, Konz & Johnson, Cussler, Porter's CU Boulder chapter) were found with a looser search, Porter via the CU Boulder record. Chapter numbers that could not be verified were removed from every reference.
Not verified: the IPCC AR6 table number for the GWP values (reference now names Chapter 7 and Supplementary Table 7.SM.7, and the assumption says to check the table; methane 27.9 versus 27.0 non-fossil is
unresolved), and the standards (ASTM C1074, ASTM G102, EN 1998-1, ITU-T G.114, ETSI TS 102 687), which are cited from memory. The IAEA SSG-14 reference was dropped (it concerns geological disposal facilities, not
radionuclide transport). The formulas are tested against independent re-implementations by the same author; that is a check of the code, not of the physics. Nothing pushed; PR still to be opened on request.

## 2026-10-29 — System builder / export gaps: differential equations, series and validity limits

**Goal.** Close the gaps the earlier exports had left: blocks with differential equations or series could not be exported to MATLAB/Excel or saved as an equation, and a saved system dropped its blocks' validity limits.

**Measuring first.** A sweep put every one of the 946 calculations in a one-block system and tried MATLAB, Excel and save-as-equation (`scratchpad/sweep.py`, reasons grouped by message). Before: 80 / 91 / 85 refused. The largest group was 44 blocks with differential equations
or PDEs (30 ODE systems, 9 multi-species PDEs, 4 PDE systems, 3 + 3 2-D and flux systems, 2 SDEs, 1 fractional), then 6 `Sum` series, 3 data tables. The remaining ~12 refusals per format are sweep artefacts (the example omits an input that is derived).

**What changed.**
- `closed_solution()` (design_code): ten ODE blocks have a closed form (tank, cooling, beam and fin profiles, pipe/channel flow, annular fin with Bessel functions). Export and save-as-equation now write that formula; the saved equation can then be solved backwards (time from a concentration), which the differential equation cannot. Excel gets `BESSELJ/Y/I/K` for integer orders.
- `plain_ivp()` + `_matlab_ivp()`: plain initial-value problems (damped oscillator, falling body with drag, RLC step, PI control with its integral state) become an `ode45` call in the MATLAB script (tight tolerances, same reference check as everything else). Excel says why it cannot. Lane–Emden is excluded on purpose (0/0 at the centre; SlideRule starts from a series, `ode45` would not).
- Finite `Sum` series (4 calculations): `sum(arrayfun(@(k) ..., 1:N))` and `SUMPRODUCT(... ROW(INDIRECT("1:N")))`; checked in a real spreadsheet engine.
- Validity limits are carried into the saved equation, renamed to its variables. First attempt produced `True` for 12 conditions: mapping through the blocks' positive symbols lets sympy decide `a + b > 0` itself. Fixed by mapping straight to plain symbols; limits the editor rejects (`Ne(...)` was written as `!=`) or that mention a quantity the saved equation lacks are dropped and listed in the assumptions. Result over the 160 calculations with limits: 172 limits carried, 1 dropped.

**Still not possible (reported with the block named).** Boundary-value problems, events, delays, PDE and SDE blocks, data tables (3), eigenvalue-based series, open-limit sums; numerically solved blocks cannot be saved as equations. The fin profile with a convective tip is a closed form but its saved equation exceeds the editor's 300-character limit.

## 2026-10-29 — LiveCalc improvements, part 1: constants, statistics and calculus

**Goal.** "Start on the LiveCalc improvements" (unspecified): the calculator had no physical constants, no way to average a list or integrate a function you defined, so the first slice is the engine's numerical vocabulary. History/export features are the planned second slice.

**What was added (`livecalc.py`, `livecalc_help.py`, tests in `tests/test_livecalc_numerics.py`).**
- 14 physical constants with units (`c0 g0 Gnewton hP hbar kBoltz NA Rgas qe eps0 mu0 sigmaSB me mp`), checked against each other (R = N_A k, μ0 ε0 c² = 1, σ from h, c, k). A variable of the same name takes precedence. `kB` was rejected as a name: it is the kilobyte, and `5 kB` must stay that.
- `sum mean median stdev hypot sign mod` (same-dimension values, unit of the first kept; offset temperatures may be averaged but not added).
- `integrate(f, a, b)`, `derivative(f, x)`, `findroot(f, lo, hi)`, `sumover(f, i, j)` on user-defined one-value functions, with units (integration multiplies, differentiation divides). Limits that are arrays (while plotting) are evaluated point by point, so `plot integrate(f, 0, x) from 0 to 3` works (400 points maximum).
- The first argument is the *name* of a function, so `names_in` skips it (otherwise `F = integrate(f, 0, 2)` was classed as an equation with an unknown `f`). My-equations drafts warn that these functions are not available there.
- All 25 new names are in the function search with engine-run examples; the in-app help text and docs/LIVECALC.md were updated.

**Not done yet.** Larger history and named sessions, copy/export of the history (Markdown, Python), calling library calculations from LiveCalc, parametric/log-axis plots, vectors and lists.

## 2026-10-29 — LiveCalc improvements, part 2: history, sessions, export, log and parametric plots

**Goal.** The planned-next items after part 1: a longer history with named sessions, export/import, and more plot types. (Lists/vectors and calling library calculations from LiveCalc are not started.)

**What changed.**
- History 30 -> 200 entries (client `MAX_ENTRIES`, server `MAX_ENTRIES` 200, `MAX_LINES` 400 -> 1500). The engine is stateless and replays the history on every keystroke; 200 two-line entries took 0.14 s, 30 took 0.015 s, so no caching was added.
- Sessions panel: save the history under a name (50 kept in `localStorage`), open, delete; export as Markdown (`livecalc_export`, RPC), plain text, JSON; copy Markdown; import `.json`/`.txt`. Checked in the browser (save, export, import through a real file input).
- `plot ... logx|logy|loglog`: x sampled geometrically, values <= 0 not drawn on a log y axis, decade ticks and a "log scale" label in `xyPlot`.
- `plot parametric x(t), y(t) for t from a to b`: one curve, two expressions with their own units; `parametric` is only a keyword when it is not a variable.

**Mistake worth recording.** The first rewrite of `xyPlot` sliced from a marker string that also occurs earlier in the file (`onePlot`), duplicating a block of `plot.js`; `node --check` caught it (the browser would have shown a blank page). The file was restored and the replacement redone with the search started after the function head.

**Still open.** Lists/vectors, calling library calculations from LiveCalc, equal-aspect option for parametric plots, plots with a second y axis.

## 2026-10-29 — LiveCalc improvements, part 3: lists, vectors and library calculations

**Goal.** "Lists and vectors with library calcs": values with many numbers, and the library's 946 calculations callable from LiveCalc, so a sweep (a calculation over a list of inputs) can be computed and plotted.

**Design.** A list is a `Q` whose value is a 1-D numpy array, so arithmetic, unit conversion and broadcasting already worked (plots had used arrays all along). What had to be added: `[ ]` and quoted-text tokens, list and index nodes in the parser, display of arrays (first five and last three of a long list), no step-by-step working for lists, and list-aware functions. A single array argument to `sum/mean/median/stdev/min/max/hypot` means "reduce the list", but while plotting an array is one value per sample point, so `Scope.plotting` keeps those elementwise (otherwise a plotted `mean(x)` would collapse to one number).
`calc("id", "output", name = value, ...)` solves the library calculation for that output with `core.solve`; list inputs are broadcast and solved one by one (400 at most; 300 points of a plot take under a second for the wind-turbine calculation). The id can be its end or a unique name match; ambiguity lists the candidates. `livecalc_library(query)` (RPC, built on `Catalog.search`) feeds a Library section in the function search, each result with an example line that was run by the engine.

**Bugs found while doing it (all pre-existing, all fixed).**
- `5 min` and `20 L/min` did not work: `min`/`max` were reserved as function names, so they could not be units. They are units unless followed by `(`.
- `0.2 L/(mg*min)`: a bracketed unit group after `/` was not understood (an equation was shown instead of a value). Added, with a check that a number inside the brackets is an exponent, not a quantity (`5 m/(2 s)` is still 2.5 m/s).
- `-56.5 degC` was refused (negating an offset temperature); a negative literal now keeps its scale.
- An `=` inside brackets made the line "an equation with two ‘=’": only a top-level `=` counts.
- A `[`-started line was always Markdown; now only `[text](` is (so `[1, 2, 3] m` is a list).
- LaTeX of the text arguments rendered as red source because of `_` in `\text{}`; escaped.
- numpy's broadcast error for lists of different lengths leaked as a Python message; now "These lists have different lengths".

**Measured.** 882 of 891 library calculations without differential equations or tables run their worked example as a `calc(...)` line (before the unit fixes: 765); the 9 left use fractional-power units (`m^(7/2)/kg^(1/2)`) or `min` after `*` in an assignment.

**Not done.** Matrices, 2-D lists, `calc` for ODE/table calculations, calling the user's own "My equations" from `calc`, slicing (`v[2:4]`), a second y axis.

## 2026-10-29 — LiveCalc: search below the input, empty commands

**Request.** Move the function/library search below the calculation entry field, and offer an empty command instead of only the fully populated example.

**Done (front end only, `livecalc.js` + CSS).** The search row and its results panel now sit under the input (in the left column, so they follow the "plots on the right" layout too); the panel is capped at 36 % of the viewport so the history keeps room. Each function gets an *empty* button that inserts `name()` with the cursor inside the brackets; a library calculation gets `calc("id", "output", rho = , Dr = , …)` with every input named and the cursor at the first value (long lists of inputs are abbreviated on the button but inserted in full). Both go on a new line if the box already has text. Checked in the browser, including the cursor positions.

**Noted.** With the panel open in a small window the history area becomes short; that is the cost of putting the results under the input.

## 2026-10-29 — LiveCalc: compact sessions bar

**Request.** Make the sessions bar at the top of LiveCalc as compact as possible. **Done.** The Sessions panel no longer takes its own row: it is the first item of the toolbar, a small "Sessions (n) ▾" button whose menu (save, Markdown, text, JSON, copy, import, saved list) opens over the page and closes on an outside click or Esc. The toolbar buttons are small, the title is smaller and the header padding is reduced (header height 122 px in a 600 px window). The session buttons are shortened (Save…, Markdown, Text, JSON, Copy, Import…), and "Send selection to My equations" became "Send to My equations". Checked in the browser: open, outside click closes.

## 2026-10-29 — LiveCalc: minimal catalogue rows, help moved, full-width layout

**Request.** (1) Move "What can I type?" down with the formula browser. (2) Make the catalogue minimal: `integrate` should show just `integrate(f, from, to)` and a button to get more. (3) Use the full screen: with the plots on the right there was empty space left of the history and right of the plots.

**Done.** (1) The summary is now the last item under the search box. (2) Each row is the signature, a badge, **Insert** (the empty command, as before) and **More**; More opens the description, the examples (run by the engine) and, for library calculations, the inputs, outputs and example. Constants insert their name; syntax entries have no Insert. (3) Cause of the empty space: `.live-page` had `max-width: 1100px` (1560px with plots on the right) and the page is centred. LiveCalc now has no maximum width and no side margin; at 1900 px the header, history column and plot column span 14 px to 1871 px (checked in the browser at that size).

**Noted.** The branch is built on the unmerged compact-sessions branch (the Sessions dropdown); merge that first or together.

## 2026-10-29 — LiveCalc improvements, part 4: slices, matrices, plot options, calc coverage

**Goal.** The remaining items from the part 3 list: matrices, slicing, a second y axis, equal-aspect plots, and `calc` for differential-equation, table and user ("My equations") calculations.

**Found already working.** `calc` on differential-equation and table calculations needed no change: the solver takes the time as an input, so `calc("…newton_cooling_transient", "T", …, t = linspace(0 min, 20 min, 5))` is a response curve (checked against the closed form), and the user's equations are in the same catalog (`custom.*`, found by the end of the id). Only the documentation and tests were added.

**Added.**
- Slices `v[2:4]`, `v[:3]`, `v[-2:]` (counted from 1, **both ends included**, as in MATLAB; stated in the help). Index specs are a list, so `A[1:2, 2:3]`, `A[:, 2]` work.
- Matrices: a list of equal-length lists (500 values at most; the display is a bmatrix, in full up to 8 × 8 and as "r × c matrix" beyond). `transpose matmul det inv trace identity rows cols solve(A, b)`, with unit algebra (`det` to the n-th power, `inv` inverted, `solve` = unit of b over unit of A). Singular systems are refused (condition number above 1e13). Results are compared with numpy on random 2/3/5-dimensional systems; rounding noise below 1e-13 of the largest entry is shown as 0.
- Plot options at the end of a `plot` line, in any order: `logx logy loglog equal twin`. `equal` widens the shorter range so one x unit is as long as one y unit (both axes need the same unit; not with log axes); `twin` draws the last expression against a second axis on the right (own unit, own ticks, own readout).
- `0.1/min` and `3 min`: a bare `min`/`max` is a unit unless called (this was only half fixed in part 3: `/min` after a number still failed).

**Mistakes noticed.** The matrix test first failed because a 5 × 5 line is longer than LiveCalc's 400-character limit; the assignment error was hidden because the unknown `A` then read as the ampere unit. The tests now use short numbers.

**Not done.** 3-D lists, eigenvalues/decompositions, complex numbers, `calc` for partial-differential-equation calculations that need a position grid (not tried).

## 2026-10-29 — LiveCalc improvements, part 5: measured data, eigenvalues, fractional unit exponents

**Checked first.** Whether `calc` works for the partial-differential-equation, flux, fractional and stochastic calculations (part 4 had not tried): all 53 differential-equation and table calculations run their worked example as a `calc` line except the 2 stochastic ones, and those failed for a different reason (below).

**Bug.** `0.02 K/s^0.5` was read as `(0.02 K/s)^0.5`: a unit exponent had to be a whole number, so the `^0.5` was applied to the whole quantity and the unit became `K^(1/2)/s^(1/2)`. Unit exponents may now be decimals or `(a/b)`. With that, **946 of 946** library examples run as `calc(...)` lines (882 after part 3, 937 before this fix).

**Added.** `trapz cumtrapz interp slope intercept rsquared corr polyfit(xs, ys, n, at)` (units follow; interpolation does not extrapolate; fitted values that are rounding noise next to the data become 0), and `eigvals`/`eigvecs` (symmetric matrices with `eigh`, other real ones with `eig`; complex eigenvalues are refused with a reason). Tests compare against numpy on random data and check A v = λ v for every eigenvector.

**Left out on purpose.** Complex numbers (every function, unit rule and plot would need a complex path; the cases that need them, such as complex eigenvalues, say so instead), 3-D lists (no use case beyond matrices came up), decompositions (QR, SVD). These can be added if a use appears.

## 2026-10-29 — LiveCalc improvements, part 6: complex numbers

**Why now.** It was the last item left out in part 5 ("every function, unit rule and plot would need a complex path"). The cost turned out to be manageable once the safety rule was settled: a function either handles complex numbers properly or says it cannot; none may drop the imaginary part silently.

**How.** Values stay `Q` with a numpy array/scalar that may be complex. `i`/`j` after a number (4i) or alone is the imaginary unit unless the user defined a variable of that name (so existing sessions that use `i` as a variable keep working). A global replacement turned every `np.asarray(x, dtype=float)` into `_real(x)`, which raises "needs real numbers" for complex input (numpy would otherwise discard the imaginary part with only a warning); the functions that do support complex use `_num(x)` instead. A whitelist (`COMPLEX_OK`) at the call site refuses everything else with "name() does not work with complex numbers". Supported: `+ - * / ^`, `sqrt exp ln log sin cos tan sinh cosh tanh asin acos atan abs`, new `real imag conj arg polar`, complex lists/matrices with `sum mean prod cumsum transpose trace matmul det inv solve norm dot cross eigvals eigvecs`. Display `3 + 4i` with a "Polar form: 5 ∠ 53.1301°" note, `(10 + 5i) ohm` with units; results that are exactly real after a product or power are real again (not after a sum, so `sqrt(-4 + 0i)` still works); rounding noise (`exp(i*pi)` = −1 with a 1e-16 imaginary part) is shown as real.

**Checked against.** `cmath` for the elementary functions and numpy for complex `solve`, `det`, `inv`, `matmul`; a series RLC branch at 50 Hz and a two-node admittance network with units (`solve(Y, I)` in A/S).

**Found on the way.** `plot abs(f) from 0 to 5` with `f` a function treated `f` as the plot variable and plotted |x| without a word; it now says "‘f’ is a function: write f(w)". `eigvals` of a rotation matrix used to be refused; it now returns `[-i, i]`.

**Still not done.** 3-D lists, QR/SVD decompositions, complex numbers in plots (use abs/arg/real/imag) and as calc inputs.

## 2026-10-29 — LiveCalc improvements, part 7: least squares, conditioning, percentiles

**What was left.** After complex numbers: 3-D lists, QR/SVD decompositions, complex numbers in plots and calc inputs. The first and last have no use that is not already served (lists of lists are matrices; plots take abs/arg/real/imag), so they stay out. The useful part of the decompositions is what they are used for: `lstsq(A, b)` (over-determined fits; refuses columns that are not independent), `rank`, `cond` (the check that tells when `solve` can be trusted), `pinv`, `svdvals`, `outer`, plus `var` and `percentile`. Units follow (`lstsq` = unit of b over A, `pinv` inverted, `var` squared). Compared with numpy on random systems (up to 9 × 3) and data.

**Mistakes in the tests, not the code.** A 12 × 4 matrix in a test line exceeded the 400-character limit (again); and a matrix that is singular only to rounding has a condition number of 5e16, not infinity, so only an exactly singular matrix raises.

**Remaining.** Nothing planned. Candidates if a need appears: QR/LU factors as results, 3-D lists, complex plots (Argand diagrams, Nyquist), exporting LiveCalc sessions to Python.

## 2026-10-29 — Classical mechanics audit: 26 calculations added

**Question.** "Is the full list of equations from classical mechanics represented in the library?" Honest answer was no (36 Classical and 11 Analytical Mechanics calculations covering the common textbook topics, with gaps).

**Audit.** A topic list built from the contents of Taylor's *Classical Mechanics*, Halliday–Resnick–Walker and Kleppner–Kolenkow was matched to the library by id and by keyword search (`rocket`, `parallel axis`, `two-dimensional collision`, `variable mass`, ...). Result in [docs/CLASSICAL_MECHANICS_AUDIT.md](docs/CLASSICAL_MECHANICS_AUDIT.md): 46 topics, 26 of them missing or only touched on. The audit is by topic: it does not check every formula inside a covering calculation.

**Added (`library/mechanics_gaps.py`, 26 calculations, `tests/test_mechanics_gaps.py`).** Newton's second law in 2-D; work–energy with friction; bungee energy; 2-D inelastic and elastic (lab/CM angles) collisions; centre of mass of several bodies; two-cable equilibrium; projectile on a slope; rotor-ride friction; flywheel dynamics; capstan friction; simple machines; falling chain and conveyor belt (variable mass); gravity tunnel; accelerating-frame apparent gravity; rotating liquid; free-decay logarithmic decrement; Kepler's equation; brachistochrone; Kapitza pendulum; Duffing backbone; pendulum separatrix; hard-sphere scattering; principal moments of a planar body; Euler rotation stability; cubic-well escape.

**How they were checked.** Each against a separately written computation that does not reuse the library's formula where a different route exists: the bungee extension by root finding on the energy balance, the elastic collision by solving momentum and energy in the lab frame, the cables by a 2 × 2 linear solve, the work–energy stopping distance by stepping the motion, the principal moments by the eigenvalues of the inertia tensor, Euler stability by the eigenvalues of the linearised equations, the rotating-liquid surface by integrating its volume, Kepler's equation and the brachistochrone by `brentq`, and the Duffing backbone against a numerical integration of the equation of motion (within 1 %: it is a first-order result). The two implicit equations (Kepler's, the brachistochrone) are solved by the engine's numerical solver with bounds on the unknown.

**Mistakes on the way.** Validity conditions cannot contain units (`al + be < 180 deg` failed to parse; written as `< pi`). The first Duffing and Euler examples were poor (a 58 % frequency shift is not "weak nonlinearity"; I2 ≈ I3 hides the intermediate-axis effect) and were changed after reading the printed values. The 1 % Duffing agreement is the real limit of the formula, not a loose tolerance.

**Not added, and why.** Hamilton's equations as a general formalism, chaos measures, Noether's theorem: not formulas to evaluate without a chosen system (listed in the audit).

## 2026-10-29 — Hamiltonian mechanics and chaos: 11 calculations and a new sub-discipline

**Request.** Add the missing Hamiltonian and chaos calculations named in the classical-mechanics audit.

**Scope decision.** Hamilton's equations, canonical transformations and Poisson brackets are structure, not formulas; what can be a calculation is a specific Hamiltonian system, the quantities built from it, and the standard results of chaos theory. Added `library/hamiltonian_chaos.py`:
Hamiltonian — Hamilton's equations for the pendulum (numerical flow with the energy check), canonical momentum and the Hamiltonian of a charged particle in a magnetic field, action variable and Bohr–Sommerfeld level of an oscillator, the Laplace–Runge–Lenz vector, the Kepler problem in action variables (hydrogen n = 2, ℓ = 1 shown).
Chaos (new sub-discipline *Nonlinear Dynamics and Chaos*, added to the taxonomy) — Lorenz trajectory with a tangent-space Lyapunov exponent, Lorenz fixed points / Hopf threshold / Kaplan–Yorke dimension, logistic-map cycles with Feigenbaum scaling, the Melnikov threshold for the driven double-well Duffing oscillator, predictability horizon, bifurcation normal forms.

**Independent checks (`tests/test_hamiltonian_chaos.py`).** Pendulum and Lorenz against `solve_ivp` (DOP853, 1e-12); the oscillator area and the Kepler radial action by quadrature (with a substitution that removes the square-root edges; first attempt with plain `quad` was 4e-5 off and looked like a bug in the formula); the Runge–Lenz vector by 3-D cross products, its eccentricity against the closest and farthest approach of a numerically integrated orbit; the Hopf threshold as the root of the largest real part of the Jacobian eigenvalue; the 2-cycle by iterating the map and its Lyapunov exponent by averaging log|f'| over 2e5 iterations; the Melnikov threshold by numerical integration along the homoclinic orbit with the amplitude searched over the phase; the Lorentz force recovered from −∂H/∂r by finite differences; the Kaplan–Yorke dimension 2.062 and the Hopf value 24.737 against the textbook values.

**Findings worth keeping.**
- The Lorenz finite-time Lyapunov exponent from (1, 1, 1) is 0.34 at t = 20 and 0.74 at t = 40, slowly approaching 0.906: the calculation says so. And x(t) itself is only reproducible for about 25 time units: at t = 40 the engine and `solve_ivp` disagree completely (x = 16.8 against −11.5) — not an error, a demonstration; a test shows a 1e-9 change of the start does nothing at t = 10 and everything at t = 40.
- A validity condition cannot hold units, and an engine ODE calculation can have algebraic outputs that depend on its dependents (the pendulum energy), which made the energy-conservation check possible.
- The Runge–Lenz vector has unit kg²·m³/s² (it is built from m·p·L), not kg·m³/s² as first written; the dimension check caught it.

**Still not covered** (listed in the audit): canonical transformations and Poisson brackets as calculations, general Noether, Poincaré sections and the Hénon/standard maps, fractal dimensions from data.

**Found while adding them — a bug in the system exports (fixed).** The exports (MATLAB, Excel, Python script, save-as-equation) rebuild every block's expressions on plain symbols that were all created *positive*. For a quantity declared signed this is wrong: sympy simplifies `Abs(E0)` to `E0` the moment the substitution happens, so the exported check `|E − E0| < 1e-6|E0|` became `1e-6·E0 > |E0 − E|`, false for a negative energy. The pendulum calculation's own conservation flag (1 in SlideRule) was 0 in the generated MATLAB. Symbols for signed variables are now `real=True` in the plan, the script's `rename` map and the script's `sym()` helper. The same trap had already bitten validity limits (`a + b > 0` became `True`, part 4 of the system-builder work); this is the general fix.

**Also found.** (1) A variable that is neither an input nor an output has no value in a system block ("no wire and no value"), so the Lorenz tangent vector had to become an output and the pendulum's energy drift became a 1/0 conservation flag; an energy drift of −5.6e-8 J is integration noise that two integrators cannot reproduce, a flag can be. (2) Steps of one block are now exported in dependency order: an algebraic equation can use a differential equation's result (the pendulum's energy) and the reverse. (3) A chaotic example cannot be cross-checked by an exported script beyond about 10 time units (the script and the solver disagree at t = 20 by 1e-4 and the script's check says so), so the Lorenz example stops at t = 10, where the finite-time exponent is a poor 0.06; the description says that and gives 0.34 and about 0.7 for t = 20 and 40, and a separate test compares t = 20 with an independent integration to 5e-4.

## 2026-10-29 — LiveCalc radians/degrees switch; the rest of the classical-mechanics items

**LiveCalc angle mode.** A toolbar switch *Angles: Radians | Degrees* (stored in the browser, saved with sessions and JSON exports). In degree mode a bare number given to `sin`, `cos`, `tan` or the angle of `polar()` is read as degrees, and `asin`, `acos`, `atan`, `atan2`, `arg` answer in `deg`; an angle that carries a unit (`30 deg`, `0.5 rad`) is never changed. Implemented in the engine (`Scope.angle`, `_call_in_degrees`) so it holds in user functions, lists and plots (`plot sin(x) from 0 to 360` is one period); passed to every RPC (`livecalc_eval`, `_plot`, `_export`, `_to_equation`); My equations always use radians, so sending an equation with an angle function from degree mode warns. Checked in the browser (`sin(30)` −0.988 → 0.5 and `asin(0.5)` 0.5236 → `30 deg` on a click, plot redrawn).

**Remaining classical-mechanics items** (the audit's "still not covered" list), `library/mechanics_formalism.py`, 9 calculations: 3-D inertia tensor (principal moments by the trigonometric solution of the cubic) and the angular momentum and kinetic energy of a body with a general tensor, linear canonical transformation (bracket test and transformed oscillator Hamiltonian), action–angle transformation of the oscillator, Hamilton–Jacobi for the oscillator, Noether's theorem (anisotropic 2-D oscillator), the Chirikov standard map, the Hénon map, fractal dimension.

**Checks (`tests/test_mechanics_formalism.py`).** The inertia tensor against `numpy.linalg.eigvalsh` and `T @ ω`, and a tensor rotated about z; the bracket by finite differences of the map; the action–angle motion against `solve_ivp`, with {q, p}_{J,φ} by finite differences; W, p and t of Hamilton–Jacobi by quadrature, then p = dW/dq and t = dW/dE by differencing the library's own W; the 2-D oscillator against `solve_ivp` (conserved iff kx = ky); the standard map's Jacobian trace and rotation angle by finite differences, its Lyapunov exponent at K = 10 by iterating the tangent map, its diffusion by an ensemble; the the Hénon Lyapunov exponents by QR iteration (λ₁ = 0.42, λ₁ + λ₂ = ln b); a Cantor set built level by level.

**Mistakes the independent tests caught.** The determinant in the trigonometric eigenvalue solution had `+2 Ixy Ixz Iyz` where the tensor's off-diagonal entries are −I, giving `−2 …`: the largest moment came out 0.2536 instead of 0.2570 (the dimension check cannot see a sign). The quasilinear diffusion K²/4 is not the real diffusion at K = 10 (about 0.65 of it, from correlated kicks): the calculation now says so and the test checks the ratio rather than equality. An output that is exactly zero in the worked example (the Q·P coefficient) cannot be compared with floating-point noise, so the example was changed.

**What is still not a calculation** (see the audit): a general Poisson bracket of arbitrary functions, general Noether, long iterations (Poincaré sections, Lyapunov spectra, correlation dimension) — better done in LiveCalc.

## 2026-10-29 — Calculation list: Basic, Advanced, Custom and Favorites

**Request.** Add basic, advanced, custom filters and favorites to the calculation listing: basic limited to classical mechanics, advanced everything, custom the user's own groupings, favorites a shortlist.

**Design.** A *Show* switch at the top of the Calculations sidebar. **Basic** = the calculations tagged *Classical Mechanics* (53 of 992; *Analytical Mechanics* — Lagrangian and Hamiltonian topics, chaos — stays Advanced; the choice is stated on the page and in the README). **Advanced** is the old behaviour and the default. **Favorites** and **Custom** are lists of ids kept in the browser (`calcFavorites`, `calcGroups`, `calcGroup`, `calcLevel` in `localStorage`; up to 50 groups of 1000 ids), so they work the same for the Python server and the in-page Pyodide build and include the user's own equations. Stars on every card (★ beside the title in the detail view), a *Groups* menu beside the title (tick the groups a calculation belongs to, or start a new one), and in the Custom level a group picker with New / Rename (merging into an existing name asks first) / Delete (the calculations stay).
Server side: `list_calculations` gained `level` ("basic" | "advanced") and `ids` (restrict to these; an empty list means no results, not everything), also on `GET /api/calculations` and `sliderule list --level`; `meta` reports the level sizes. The search, discipline, variable and sub-discipline filters still apply inside every level, and the discipline chip counts follow the level (they showed stale numbers before).

**A bug caught by the tests before it shipped.** The first version added "Classical Mechanics" to the sub-discipline filter list, but that filter is an *or* over its entries, so Basic plus a sub-discipline the user had typed gave the union (74) instead of the intersection (0). Basic is now a separate filter applied after the search.

**Checked.** API, HTTP (`/api/calculations`, `/api/rpc`) and command line (`tests/test_calc_levels.py`, 7 tests: every classical-mechanics calculation is in Basic and nothing else is; Basic combines with search, discipline and sub-discipline; id lists ignore unknown ids, respect search and level, and cap at 3000; user equations can be in a group; a bad level is a 400); in the browser: the four levels, starring from the list and the detail view, a new group made from the Groups menu, counts and stored state.

**Not done.** Export/import of groups to share them (they live in one browser), drag-and-drop ordering inside a group, a Basic level for other fields.

## 2026-10-29 — Discipline chips follow the "Show" set

**Goal.** With Basic, Favorites or a Custom group selected, most discipline chips showed "0" and cluttered the sidebar.

**Change.** `refreshList` in `web/js/app.js` already received per-discipline counts for the current Show level and filters; it now hides every chip whose count is 0 unless the user has it selected (so it can still be deselected), and hides the "Emerging and interdisciplinary fields" fold when all its chips are hidden. No engine change. Counts ignore the discipline filter itself, so selecting one discipline does not hide its siblings.

**Checked.** In the browser across Basic, Advanced, Favorites (empty and starred) and a Custom group.

**Extended to every filter (same day).** `api.list_calculations` now counts each facet over what all the *other* filters leave (search, level or id list, source, discipline, sub-discipline, has-variables, can-solve-for). It returns `subdisciplines` with counts, and `variables` and `solves` as suggestion lists, alongside the discipline counts. The page hides zero-count discipline chips and rebuilds the three auto-complete lists from them. A facet ignores its own filter, so the siblings of a chosen option stay on offer. Example: Basic + Physics leaves 5 sub-disciplines and 329 variable suggestions, against 246 and 2,473 for Advanced. `tests/test_calc_levels.py::test_every_facet_follows_the_other_filters`. Full suite passes (3.12).

**Limit.** The sub-discipline filter matches by substring, but suggestions are exact names, so a typed fragment can still match calculations that no suggestion corresponds to.

## 2026-10-29 — Basic level includes college-level chemistry

**Goal.** Basic listed classical mechanics only (53); the user asked for college-level chemistry in it too.

**Decision.** "College-level" is a judgement call, so it is a short list in `api.BASIC_CHEMISTRY`: General, Analytical, Kinetics, Thermodynamics, Electrochemistry, Atomic Structure and Spectroscopy, Organic. A calculation is Basic when it is tagged Classical Mechanics, or is a chemistry calculation in one of those sub-disciplines (`api.is_basic`). Physical, quantum, polymer, colloid, solid-state, bio- and atmospheric chemistry stay Advanced; they are upper-division or specialist. Moving a sub-discipline in or out is a one-line edit.

**Result.** Basic is 181 calculations (was 53); `api.meta()["levels"]["basic"]` now also lists `subdisciplines`. Page text, README and CLI help updated. The existing tests needed three corrections, not the code: the optics and polymer-chemistry "must be empty" checks now match chemistry calculations cross-listed there (used Nanomaterials instead), and the physics count under Basic is 74, since chemistry calculations are cross-listed under physics.

## 2026-10-29 — Quality-of-life pass, part 1: the calculation list

**Goal.** The user asked for the improvements I had listed, section by section, each ending in a merged PR; this is the first section, the calculation list.

**Done.** (1) Favorites, groups, recent list and the custom Basic choice can be exported to `sliderule-lists.json` and imported (merge: nothing is removed). (2) A **Recent** level, newest first (30 kept). (3) Order inside a single group, ▲ ▼ on each card, kept in the group's id list; a search ranking takes over when a query is typed. (4) Keyboard: `/` to search, ↓ from search into the list, ↑ ↓ Home End between cards, `f` to star. (5) The filters (search text, disciplines, sub-disciplines, variables, solves-for, only-mine) are saved and restored. (6) "Change what Basic includes": the user picks the sub-disciplines; `api.list_calculations(basic=[...])` and `GET /api/calculations?basic=` replace the default list (exact sub-discipline names, at most 300; the default is untouched; the button shows ✎ when customised).

**Checked.** `tests/test_calc_levels.py::test_users_own_basic_replaces_the_default_list`; in the browser: recent order, a group reordered with ▼ and the stored order, `f` and arrow keys, `/` focusing the search box, importing a file (favorites, a new group, the Basic choice), and the filters surviving a reload.

**Not done / limits.** The lists are still per browser (the file is the way across). The default Basic uses the chemistry-only rule but a custom Basic matches sub-discipline names alone.

## 2026-10-29 — Quality-of-life pass, part 2: solving a calculation

**Goal.** Second section of the list the user approved: share/save a worked case, remembered units, compare/sweep, an "I have / I need" picker.

**Done.** (1) `api.sweep` (and `POST /api/calculations/{id}/sweep`): one call solves a calculation at 2–200 values of one input and returns every requested result, with `None` where a point has no answer; the page graphs one result with the existing `xyPlot`, with linear or log spacing and CSV download. (2) Unit memory: choosing a unit for a quantity kind stores it; on opening a calculation the example is converted by the engine (`convert`) to the remembered unit (5 kN shows as 1124.0447 lbf after choosing lbf), results just take the unit. (3) *Copy as text*, *Save case*, *Open case* beside the existing *Copy link* (which already carried inputs in the address, updated on every solve). (4) The filters are renamed "I have" and "I need to find" and show up to eight one-click quantity chips drawn from the same facets that trim the suggestion lists, so they offer only what the other filters leave.

**Checked.** `tests/test_sweep.py` (the cantilever formula P·L³/3EI at five loads, equal to single solves; bounds and validation; gaps; HTTP and RPC; 60 points under 15 s). In the browser: sweep plot, unit memory round trip, opening a saved case (2 kN, 3 m, 200 GPa, 10⁷ mm⁴ gives 9 mm, as by hand).

**A mistake of mine, caught by testing.** My first hand-written case file listed only one unknown; the page then correctly asked for values of the other two results (an unknown is a choice, not a default), which looked like a bug. Files the page saves list every quantity.

**Not done.** Sweeping two inputs; sweeps of differential-equation calculations (they already plot against time).

## 2026-10-29 — Quality-of-life pass, part 3: the system builder

**Goal.** Third section: undo/redo on the canvas, auto-layout, snapping, and a suggested connection when types match.

**Done (all in `web/js/system.js`, no engine change).** (1) Undo/redo as snapshots of the saved graph (`toGraph`), capped at 100; every edit already ends in `changed()`, so one hook records them; a burst of typing in a value box is merged into one step (`changed("edit")`, 1.5 s); restoring goes through `loadGraph(…, {keepView: true})` so the zoom does not jump; what was restored from the browser at start is step zero, so undo cannot erase the saved canvas. (2) **Tidy**: columns by longest feeding chain, rows ordered by the mean height of the feeders, block heights measured from the DOM; one undo step. (3) Alignment guides while dragging: the block's left edge snaps to another block's, its top to another's top or to just above or below it (8 screen px, so the pull is the same at any zoom), Alt disables it; the existing 10 px grid snap stays. (4) **Suggested connections**: for the selected block (or the whole system when nothing is selected) every output and unwired input of the same physical type that `canConnect` accepts, ranked by equal symbol, equal label, and an input still waiting for a value; six shown, one click wires.

**Checked in the browser** (the wind-turbine to electrolyzer example): Tidy moved the second block from (520, 60) to (400, 40); undo and redo restored each; Ctrl+Z and Ctrl+Shift+Z worked from the page body; after unwiring, the suggestion listed the turbine power to electrolyzer power connection and Connect restored the wire; a real mouse drag of 3 px near an aligned top snapped it to y = 40.

**Dead end avoided.** Deleting a wire by dispatching synthetic events failed because wires select on a real pointer sequence; the test used the block's Unwire button instead.

**Not done.** Multi-select, copy and paste of blocks, snapping to wire ports.

## 2026-10-29 — Quality-of-life pass, part 4: trust and polish

**Goal.** Fourth section: say which citations are unverified, stop stale scripts from hiding new features, and make an accessibility pass.

**Done.** (1) `library/reference_status.py`: eight calculations whose references the citation check could not confirm (Ranz–Marshall, the IPCC AR6 GWP table, ASTM C1074, ASTM G102 in two calculations, EN 1998-1, ITU-T G.114, ETSI TS 102 687) each carry a note; `get_calculation` returns them as `unverified_references`; the page shows a notice under the title, a badge on "References", and the note under the reference itself. `tests/test_reference_status.py` fails if an entry no longer matches a reference (so correcting a citation means deleting its entry). It is a Python module, not a data file, so the in-browser (Pyodide) bundle carries it. (2) An About section "How far to trust a result" states what is and is not checked (the same-author caveat from the logs). (3) The server now sends `Cache-Control: no-cache` with an ETag for the page, scripts and styles (a 304 when unchanged) and a day's `max-age` for the vendored libraries; this was the cause of "I don't see the switch", twice, when the browser kept an old `app.js`. (4) Accessibility. Contrast was measured from the CSS tokens rather than judged by eye: the light theme's accent failed (white on #b86f0f is 3.95:1, and the accent as text on the page 3.62:1), so it is now #a26109 (4.94:1 and 4.53:1); borders of form controls were 1.3:1 in both themes, so they use a new `--line-strong` (3.4:1 light, 3.8:1 dark); every other text pair already passed. The section tabs now have a roving tab stop and arrow, Home and End keys; a skip link; the level buttons have descriptive labels; the result count is a polite live region; and the star and the group arrows moved out of the card (a `role=button` must not contain buttons: found 992 such nests, now 0).

**Not done.** A screen-reader run (only the structure and contrast were checked by script), contrast of the plot palette and of the system canvas's port colours, and verifying the eight references (needs the standards' text, which is paywalled).

## 2026-10-29 — Quality-of-life pass, part 5: LiveCalc

**Goal.** Last section: export a session to Python, QR and LU factors, 3-D lists, Argand and Nyquist plots, pin a plot.

**Done.** (1) `qr_q qr_r lu_p lu_l lu_u chol` with units (R and U keep the unit of A, Q, L, P have none, the Cholesky factor has the square root); LU through `scipy.linalg.lu`, the rest through numpy. (2) 3-D lists: a list of equal-size matrices; `T3[layer, row, column]` with the same 1-based, slice and negative-index rules, element-wise arithmetic, shown in full up to 4 × 4 × 4 (otherwise "2 × 2 × 6 array"), and `shape()`. (3) `plot argand z` (points on the complex plane) and `plot nyquist H(i*w) for w from a to b` (the real-system mirror image added; the critical point −1 noted in the steps; default range 0.01 to 100, logarithmic). The plot component got a points-only mode and a y-axis label (Re and Im). (4) Pin: a snapshot of any graph is kept in a collapsible panel above the history (up to 4, persisted). (5) `livecalc_export` gained `python` and `notebook`: they replay the entries with `Session.run_block` (new; handles ``` fences) and a shared `result_line` formatter, and the notebook is saved with its outputs.

**Checked.** `tests/test_livecalc_extras.py` (9 tests): Q·R and P·L·U reproduce the matrix and equal numpy and scipy (three LU cases including one that needs pivoting); Cholesky against numpy and its two refusals; 3-D indexing, arithmetic, display, errors; the Argand points and units; the Nyquist curve of 1/(1 + jw) lies on the circle |H − 1/2| = 1/2 to 2·10⁻⁶ (limited by the 7 digits the plot data keeps), mirrors correctly, and a pole at the origin starts far down the imaginary axis; the exported script, run with `exec`, prints the same lines as the notebook's stored outputs, and running the notebook's code cells in order prints them again. In the browser: both plot types drew, a graph was pinned and persisted, the Python and Notebook buttons appeared.

**Mistakes on the way.** I first wrote the transfer function as `H(1i*w)`; LiveCalc's imaginary unit is a bare `i` and real and imaginary parts are `real()` and `imag()`, not `re()`/`im()`; the examples in the help catalogue (each is run by a test) caught nothing here, but my first try at the Nyquist example failed with "Unexpected (". A 3-D test variable named `T` was read as the tesla; the docs now say so.

**Not done.** Nyquist critical-point marker and gain/phase-margin read-out, matrix functions applied layer by layer, a true Python translation of a session (LiveCalc lines are not Python expressions, so the export replays them).

## 2026-10-30 — Remaining items from the quality-of-life pass

**Goal.** Do the items the five sections had left as "not done".

**Done.** (1) Sweep panel: *Also vary* a second input over up to six values, one curve each (client side: one `sweep` call per value). (2) System canvas: Shift-click to choose several blocks, Ctrl+A for all, group drag, Ctrl+C and Ctrl+V (blocks and the wires between them, new ids, offset by 40 px per paste), group delete; one undo step each. (3) Nyquist: the critical point −1 is drawn (plot components take `marks`), and gain and phase margins are reported, each refined with a root finder on the exact expression rather than read off the 300 samples. (4) Matrix functions on 3-D lists, layer by layer (`det trace inv eigvals rank cond transpose`).

**Checked.** For G = K/(s(s+1)(s+2)) the gain margin is 6/K at w = √2: LiveCalc gives 3 (9.542 dB) for K = 2 and 0.6, flagged unstable, for K = 10; the phase margin 32.61° for K = 2 equals 90° − atan w − atan(w/2) at the unit-gain frequency from an independent `brentq`. The layer functions equal numpy on each layer and keep their units (det of an m matrix is m²). In the browser: three curves with their legends, a bad value list refused with a message, a two-block selection pasted as four blocks and two wires, deleted together and restored by undo.

**Two slips.** My first plot.js edit used a line that occurs three times in the file (the assertion caught it before anything was written to that file, but the Python half had already been saved, so the second half was redone by line number); and a tolerance: `det([[1,2],[3,4]])` is −2.0000000000000004, which broke an exact comparison in my own test.

**Still not done, and why.** Snapping to wire ports; a screen-reader run and the contrast of the plot palette and port colours (needs a person or tool I do not have here); checking the eight unverified references (the standards are paywalled); general Poisson brackets, canonical transformations and long map iterations (better done in LiveCalc than as library entries); favorites and groups shared across browsers beyond the export file.

## 2026-10-30 — The rest of the not-done list: references, contrast, wire snapping, lists on disk

**Goal.** Take every remaining item that could be done from here.

**References (web search, 2026-10-30; the standards themselves are paywalled, so these are confirmed against secondary sources that quote them, not against the text).** Ranz & Marshall is Part I, Chem. Eng. Prog. 48(3), 141–146 (1952) (EPA HERO and several citing papers): reference corrected, flag removed. EN 1998-1 §3.2.2.2: the four branches, η = max(√(10/(5+ξ)), 0.55) and the Type 1 table (A 1.00/0.15/0.40/2.0 … B 1.20/0.15/0.50/2.0 … C 1.15/0.20/0.60/2.0) match the calculation; **a real error found:** the example said "ground type C-like parameters" for S = 1.2, T_B = 0.15, T_C = 0.5, which is ground type B. Fixed. ITU-T G.114: the 150 ms guideline and the 400 ms network-planning limit confirmed (2003 edition) and the calculation's note now says the 150 ms is a planning guide, not a pass mark. ASTM C1074: **a second wrong statement:** the note said "datum −10 °C is typical for Type I cement"; the standard's default is 0 °C for Type I cement cured between 0 and 40 °C (−10 °C is the original Nurse–Saul value, still used in the example). Fixed. ASTM G102 (title, equivalent weight and Faraday's law; current edition G102-23) and ETSI TS 102 687 (ITS-G5 decentralised congestion control, channel busy ratio) exist and say what the calculations use. **IPCC AR6, partly wrong:** 29.8 (fossil) and 27.0 (non-fossil) are the GWP-100 values in Table 7.15 and include the CO₂ from methane oxidation; 27.9 is the value without it (Supplementary Table 7.SM.7 per one source, 7.SM.6 per another), so the old text listing "methane 27.9, fossil methane 29.8" mixed the two. The example now uses 29.8 and the text names all three. One flag remains: the report itself was not opened and the supplementary table number is disputed between sources. Seven of the eight flags are gone.

**Contrast.** Plot curve colours and port colours were measured, not judged: the light theme's green curve was 2.90:1 on the page, port rings failed 3:1 across much of the hue circle (yellow-green to cyan in the light theme, blue-violet in the dark); curve colours are now per-theme tokens (`--c1`…`--c5`) and port lightness is a theme variable (32 % light, 64 % dark), which keeps every hue at or above 3:1 on all three background tones (computed over all 360 hues).

**Wire snapping.** A wire dropped within 28 px of a port it could legally connect to snaps to it (and is drawn snapped while dragging); an exact hover still wins, an illegal target still explains why. Checked with a synthetic drag 17 px off the port.

**Lists on disk.** `userlists.py`, `lists_get`/`lists_set` (and `GET`/`PUT /api/lists`): the installed app keeps favorites, groups, recent and the Basic choice in `~/.sliderule/lists.json`; the page pushes after each change (debounced) and at start adopts whichever copy has the larger `updated`, as a whole (merging would resurrect deletions). An older copy is never stored over a newer one. A fresh browser (empty storage) showed the favorite saved by another. The test run of this on the real server wrote a file into the user's `~/.sliderule`; I deleted it and restarted the server's state afterwards (nothing was there before).

**Accessibility.** An automated audit of the six views (names on every control, duplicate ids, `aria-pressed` on non-buttons, unlabelled SVGs, heading jumps, landmarks) found only the missing page-level heading; a visually hidden `h1` was added. This is still not a screen-reader session.

**Still not done.** A person using a screen reader; the IPCC table number; general Poisson brackets and canonical transformations (LiveCalc rather than the library).

## 2026-10-30 — Equation audit across all disciplines

**Goal.** Find standard equations that were never added to the library, in every discipline and sub-discipline; and note the deferred items (done first, in [docs/ROADMAP.md](docs/ROADMAP.md)).

**What was tried.** (1) Printed the whole catalogue by primary discipline and sub-discipline (992 calculations, 246 sub-disciplines) and read it. (2) Wrote a checklist of 548 standard topics across twelve groups of fields (`scripts/equation_audit.py`), each with search phrases. (3) First run with the library's own search: 396 "found", 152 "missing". **That was wrong:** the search matches descriptions, and hits were accidents ("rankine" found the Rankine power cycle instead of earth pressure, "pile" a wave-force calculation, "liquefaction" the Joule–Thomson coefficient, "johnson" a noise calculation, "affinity" a biosensor, "retaining wall" nothing at all). (4) Restricted matching to name, id, tags and equation titles: 344 "found" and 204 "missing", still many spurious. (5) Read every one of the 344 hits and recorded a verdict (covered, partly covered with what exists, or gap), then re-read all 237 gaps against the looser search; about 40 were really partly covered (for example Manning's equation exists without Chézy, Gaussian plume without Briggs plume rise) and were moved.

**Result.** 548 topics: 81 covered, 112 partly covered, 355 missing. No existing calculation was found wrong by this audit (it checks presence, not correctness). The gaps are not evenly spread: there is no calculation for Mohr's circle, trusses, retaining walls, soil phase relations, hydraulic jumps, culverts, water hammer, unit hydrographs, normal and oblique shocks, Bode plots, Routh–Hurwitz, root locus, Thevenin, transformer equivalent circuits, antennas, the radar equation, Butterworth filters, Rachford–Rice flash, McCabe–Thiele, Thiele modulus, non-Newtonian pipe flow, laminate theory, Larson–Miller, bi-elliptic transfers, orbital elements, two-compartment pharmacokinetics, Windkessel or Starling forces, SIR epidemics, Fick cardiac output, Havlena–Odeh, Buckley–Leverett, point reactor kinetics, Erlang C, Weibull reliability or the daylight factor. Chemistry is the best covered (only 2 missing), civil and aerospace the least. The 3-calculation floor (the earlier coverage rule) shows 129 of the 246 sub-disciplines at exactly three calculations; they are listed in the audit.

**Limits.** The checklist is mine, so it has my blind spots (control, geotechnics and process safety are the fields I listed least confidently); a "covered" topic may still be a thin treatment; presence is not correctness. Nothing was added to the library: the next step, if wanted, is to fill the "first batch" in the audit.

**Tests.** `tests/test_equation_audit.py`: topics unique, every verdict prefix refers to a real topic, a "covered" topic has a search hit, a "partial" one says what exists, and the generated document matches the script's current counts.

## 2026-10-30 — Equation-audit fill: 385 new calculations across every discipline

**Goal.** Fill the gaps found by the equation audit (`docs/EQUATION_AUDIT.md`: 548 topics, 81 covered, 112 partly, 355 missing).

**What was done.** 24 library modules `audit_*` (civil, mechanical, control, electrical, chemical, materials, aerospace, biomedical, agriculture/mining, petroleum, nuclear, industrial/computer/cyber, architectural, physics, chemistry/emerging): 992 → 1377 calculations (PRs #82, #83 and the follow-up). Every calculation has a worked example and a test in `tests/test_audit_*.py` that re-derives the result by a different route where one exists (ODE or BVP integration, quadrature, Markov chains, matrix transformations, microstate enumeration, simulation, scipy distributions, geometric vectors), plus limit cases and benchmarks.

**Problems met (and fixes).**
- Python keywords as variable keys (`as`) and sympy names (`pi` used as initial pressure) broke parsing; renamed.
- Dimension checker: `Max(x, 0)` with a dimensioned x, variable exponents on dimensioned bases, `1 day`-style literals inside equations; solved with `Piecewise`, `exp(n*log(x/x0))` and unit constants.
- Wrong formulas caught by the independent tests: bi-elliptic transfer sign, Sneddon width factor (2 vs 4), Way–Wigner coefficient (0.062 vs 0.0622), Brusselator-type conventions, Hohmann/Hall-voltage unit slips, Rutherford limit, Curie constant rounding.
- Library-wide tests that new content tripped: custom-file round trip (ids ≤ 60 chars after `custom.`, names ≤ 120, ≤ 12 equations), design export (noise-only outputs such as `s + t + u − 4m²` and `log(1 − 1e-15)` lose precision in generated scripts), a hard-coded basic-physics count, a search ranking test.
- A half-written draft file was nearly committed with undefined symbols; caught by loading every module and solving every example before testing.

**Honest caveats.** The tests share an author with the formulas; the formulas were typed from memory and the citations were not checked online; empirical correlations (Pries viscosity, Standing, Plitt, Kuz–Ram, Carter–Hayes, Weymouth/Panhandle constants) should be verified against the sources before use in design. Deliberately not done: pinch analysis, gait inverse dynamics, fracture healing, HRV, livestock energetics, LP/transportation, Beggs–Brill, full PMV, smart-city demand response/microgrid, circular slope failure, and the partly-covered chemistry variants (Woodward–Fieser, Pitzer, DLVO, EIS …). The audit's verdict tables describe the library before the fill; a "Fill status" section lists the new modules.

## 2026-10-30 — Verification pass 11: mechanical design, thermo-fluids, manufacturing

Goal: source-check the mechanical fill (docs/VERIFICATION.md, Pass 11, 24 rows).
Result: Lewis, flywheel, Rayleigh, two-DOF, clutch, regenerative Rankine, wet steam, affinity laws, Swamee–Jain, Blasius, Couette–Poiseuille, Merchant, cam, planetary and critical-radius formulas confirmed. One real fault: the notch-sensitivity assumption quoted Peterson's a as 0.25 to 0.8 mm for steels; sources give 0.064 to 0.25 mm (steel) and 0.5 mm (aluminium). Text corrected. Forging friction term differs between Kalpakjian (2μr/3h) and Groover (0.4μD/h); noted in the assumptions.
Dead ends: several searches were rate-limited (transmissibility, Rohsenow, springback, V-belt, Adams constant 4.13, CMY coefficient); those rows are marked "not confirmed online". Full suite passes.

## 2026-10-30 — Verification pass 12: electrical and electronics

Goal: source-check the electrical fill. Result: 12 rows (filter orders, Sallen–Key, 555, Kaiser FIR, BER, IPC-2221, IEC relay curves, Steinmetz, IEEE 80) all agree with sources; no code changes. Not printed in any page read: Friis cascade, dish gain, classical eddy loss. Details in docs/VERIFICATION.md Pass 12.

## 2026-10-30 — Verification pass 13: aerospace, nuclear, petroleum

Goal: source-check the aerospace, nuclear and petroleum fill. Result: 15 rows agree with sources; no code changes. Worth recording: one search summary flagged the buckling pairing as wrong, but that was my own query mixing sphere and cylinder; the library already uses (π/R)² for the sphere and (2.405/R)² + (π/H)² for the cylinder. Still unconfirmed online: Hohmann/bi-elliptic/SOI (no results), Allen–Eggers closed forms, Vogel and Standing coefficients, Corey, the xenon equilibrium formula. See docs/VERIFICATION.md Pass 13.

## 2026-10-30 — Verification pass 14: physics, chemical, materials, retries

Goal: source-check physics, chemical-engineering and materials items and retry the gaps from earlier passes. Result: 20 rows agree with sources, no code changes. Retries that closed: Hohmann and bi-elliptic (11.94 threshold), Vogel IPR, Rohsenow exponent, Cooper–Mikic–Yovanovich contact conductance. Still open: Standing exponent and B_o, Kronig–Penney, Molokanov constants, Kremser, the Pries and NRC recirculation terms. See docs/VERIFICATION.md Pass 14.

## 2026-10-30 — Verification pass 15: agriculture, mining, industrial, computer, architectural, chemistry

Goal: source-check the remaining fill modules. Result: 22 rows agree with sources, no code changes (the Kapustinskii code reproduces a published NaCl value of 746 kJ/mol). Not confirmed online: Christiansen reduction factor, the Plitt constant 50.5, the Priest–Hudson RQD form, Erlang B-to-C, lift probable stops. Several searches hit the rate limit. See docs/VERIFICATION.md Pass 15. Remaining untouched: the quantum, robotics, cybersecurity and data items in `audit_chem_emerge`, and the pass-9 and pass-10 leftovers listed under "Not yet checked".

## 2026-10-30 — Verification pass 16: emerging topics and retries

Goal: finish the last fill module and retry earlier gaps. Result: 12 rows agree with sources; no code changes. Closed by retry: Kronig–Penney, Molokanov constants, Kremser, Standing B_o. One search summary wrongly described the library's Kremser expression as the fraction *not* absorbed; checking the N = 0 and N → ∞ limits showed the code is right (recorded in Pass 16). Still open: the Standing Rs exponent, Plitt constant, Priest–Hudson RQD, Christiansen factor, Pries and NRC recirculation terms, Friis and dish gain, Adams 4.13, springback and V-belt, lift probable stops. See docs/VERIFICATION.md.

## 2026-10-30 — Textbook-check list and README wording

Goal: stop spending web passes on items the search could not print, and make the README honest about what has been checked. Added a "Textbook-check list" (21 rows) to docs/ROADMAP.md with the constants to confirm and the book to check each against; marked the older citation-check section as partly done; rewrote the "Not yet checked" section of docs/VERIFICATION.md; reworded the README work-in-progress note (about 225 of 385 fill formulas checked, about 990 earlier calculations not run through these checks) and the caveat line generated by scripts/equation_audit.py. Docs only.

## 2026-10-30 — Property layer, phase 1a: datapack foundation

**Goal.** Start the property layer from the strategy (docs/DATA_AND_STANDARDS_STRATEGY.md): data outside the code, a source on every number, bad data refused mechanically.

**Built.** `core/datapack.py` (pack format with sha256 seal, fixed property vocabulary with dimension and plausibility range, user packs from `$SLIDERULE_HOME/datapacks`, per-pack refusal with all reasons), API/HTTP/CLI read access, web-bundle and wheel packaging, 21 tests including golden values and an unpacked-bundle load. First pack `materials-typical` v0.1.0: three materials.

**What building the pack showed.** The values I would have typed from memory were not all what the sources say. For Ti-6Al-4V and structural steel the sources agreed within a stated spread, so the pack stores a value plus low and high. For 6061-T6 the pages read gave 240 MPa yield and 260 to 290 MPa ultimate against my 276 and 310; ASM-style data sheets give the higher figures as *typical* and 240 is closer to a specified minimum, but no page stated its basis, so the strengths, conductivity and specific heat were left out and the record says why. Copper C11000 and stainless 304 were dropped for lack of a per-value source (304 numbers found were for 304N/304L or generic austenitic). A search summary also claimed my 276/310 "do not match": the lesson is that a property without a basis (min, typical, design) is not a usable number, which is why `basis` is mandatory in the schema.

**Not done.** Curves (temperature dependence), fluids, the selector in calculations and System, LiveCalc functions, the series type for standard sizes. Next slice proposed: curves plus a water and air pack computed from published correlations with tests against tabulated points.

## 2026-10-31 — Property layer, phase 1b: temperature curves and a water and air pack

**Goal.** Curves against temperature and a first fluids pack computed from published correlations (strategy §3: prefer computed over copied tables), with tests against an independent table.

**Built.** Curve properties in the datapack schema (checked with the table machinery, no extrapolation), a separate fluids vocabulary, `at` and `rel_uncertainty` fields, `data_value` in the API, HTTP and CLI, `scripts/build_fluid_pack.py` and the `fluids-water-air` pack (water 0.01 to 100 degC, dry air -50 to 1000 degC), 50-odd new tests.

**Getting the reference table.** Web searches only returned fragments, and two web-fetch agents came back with the raw PDF bytes (no text). The saved PDFs read fine with `pdftotext -layout`; that gave the full Cengel and Cimbala Tables A-3 and A-9, typed into the tests. Their hand-back messages claimed nothing could be read; the files said otherwise.

**Results against that table** (rows not used to build a curve): water density 0.05 %, viscosity 2.2 % (Vogel fit low at 0 degC), vapour pressure 0.09 %, specific heat 0.03 %, conductivity 0.14 %; air density 0.07 %, viscosity 1.2 %, conductivity 2.4 % (Sutherland constants run high at 20 to 60 degC), specific heat 0.13 %. Stored `rel_uncertainty` values are set a little above these, and a test fails if they are exceeded or are more than three times looser. The IF97 saturation-pressure equation as recalled reproduced the three official verification values (300, 500, 600 K) to 1e-8, which a wrong coefficient could not do by chance; the Kell coefficients were confirmed against a library listing and published densities.

**Dead ends and slips.** Two tests failed on my own mistakes (a loop that started at 0 degC, outside the stored 0.01 degC start; a +5000 degC shift that was still under 6000 K), caught on the first run. A search summary described 276 and 310 MPa as mismatched for 6061-T6 in the previous slice; here the equivalent trap was the Sutherland conductivity constants, which the pages did not confirm and which the table comparison then showed to be 2.4 % high, so the pack says so instead of claiming 1 %.

**Not done.** Selector in calculations and System, LiveCalc functions, pressure dependence, more fluids, the series type.

## 2026-10-31 — Property layer, phase 1c: the picker in calculations

**Goal.** Let a calculation take a material or fluid property, with the source kept.

**Design choice.** Match by dimension and label instead of tagging calculations: `data_options` returns, per input, the datapack properties of the same dimension, label matches first; dimensionless inputs only when the label names the property. One call per opened calculation. A *from data…* link on each such input opens a dialog (property, record, temperature) that previews the value in the input's own unit with basis, uncertainty, source and a *not for design* badge, then fills the input; a line under the input keeps the provenance, flags hand edits and unit changes, and goes into *Copy as text* and *Save case*.

**Bugs found by driving it.** `Element.append(null)` writes the text "null" into the page: my preview and provenance lines passed `null` for optional parts, so "nullnull" appeared in the dialog on the first try. Fixed by filtering the children (the `h()` helper already skips nulls, but `.append()` does not). Everything else worked on the first run: water density at 40 degC 992.216 kg/m3, viscosity at 20 degC 1.00175 mPa s, refusal at 150 degC, edit marker, no console errors.

**Testing gap.** Playwright is not installed here, so `tests/e2e/data_picker.js` is written but not run; the same steps were done by hand in the browser pane. The Python side has 9 new tests.

**Not done.** Several inputs from one record, System blocks, LiveCalc functions, restoring sources on opening a case.

## 2026-10-31 — Worked-solution audit: no opaque function calls in the steps

**Goal.** Check that worked solutions (symbolic and numeric) do not contain steps that just name a function such as `calc(...)`, and that they show proper working.

**Library calculations (Calculations tab).** Solved every example (1377) and scanned every step line for opaque or broken output (`calc(`, `tbl_`, `Function(`, `nan`, `zoo`, `None`, python-style `**`, `sqrt(`, `exp(` ...): no hits; every solve ok. Each output has the 4-line numeric pattern (formula, values substituted with units, unit reduction, result in SI) plus the symbolic governing equations, closed form and unit check. The words `Lambda`, `Error` and `Function` that the pattern also matched are variable names (Λ, "Error-function solution", "Functional units").

**Where the black boxes were: LiveCalc.** Its steps for `calc("id", "out", ...)` were `calc(...)` followed by the result; the same for `integrate`, `derivative`, `findroot`, `sumover`, and a call of your own function (`f(4)`) showed only the call and the result. Fixed (`livecalc_work.py`, hooks in `livecalc.py`):
- `calc(...)`: the line shows the library calculation's own working (name, what is found and given, closed form, inputs to SI, each formula with the numbers and the unit reduction), then the surrounding arithmetic with the result substituted; several calls in one line are numbered; list-valued calls keep the plain steps.
- your own functions: definition, arguments, body with the values in (also when the body calls `calc`).
- `integrate`/`derivative`: the exact antiderivative or derivative evaluated by hand for plain unitless formulas (sympy, compared with the numeric answer before it is shown, so a wrong closed form cannot appear), otherwise the method with its numbers (five-point stencil and its four values, quadrature with evaluation count and error estimate). `findroot`: bracket, Brent's method, iterations, residual. `sumover`: the terms and the total.
- a small pre-existing bug found on the way: a number times a value in "Substitute the values" ran together (`2\,1828.01 kW`); now `2 \cdot 1828.01 kW`.
- The steps must never lose a result: the builder returns nothing (plain steps) on anything it cannot explain; tested by forcing it to raise.

**Inverse solves (found by the scan).** Solving for a different variable than the example's raised exceptions out of the step builder, which the server returned as an unexplained HTTP 500. Scan of about 93 % of the library (14 of 15 interleaved chunks; one chunk wedged on a fractional-ODE calculation and was killed): about 9100 inverse solves, 119 raised (57 calculations): a symbolic exponent (`1/nf`, Weibull m, Peukert k), a log of a dimensioned ratio after rearranging, or an undefined (`nan`) Piecewise branch in the dimension check. Fixed in the engine: undefined Piecewise branches are ignored by the dimension check (22 cases); a dimensionless exponent is replaced by its given value for the unit line, and where that is still impossible the line says the unit is the expected one and was not reduced symbolically (97 cases) instead of failing. 113 of the 119 now solve. Not fixed: `mechanical.heat.melting_front_stefan_problem` (NameError `ODE0_T`, 3 variables), `electrical.comms.ber_digital_modulation` (TypeError, EbN0), `civil.environmental.tracer_wave_in_a_closed_loop` (singular factor), one timeout. `api.handle` now turns any unexpected engine exception into an error message (INTERNAL_ERROR, logged with a traceback) instead of an HTTP 500.

**Not done.** About 100 other LiveCalc functions (statistics, matrices, `hypot`, `mean`, `trapz`, `polyfit` ...) still show Expression and Result only; the markdown export of a LiveCalc session has no steps at all (by design: equation and result); about 126 inverse combinations came back "not ok" in the scan, mostly sign limits caused by my harness feeding negative values, and were not examined; the KaTeX stylesheet is not applied in the in-app browser pane (cross-origin), so the steps looked doubled there; the real page is unaffected.

**Tests.** `tests/test_livecalc_work.py` (17), `tests/test_worked_steps_inverse.py` (15). Full suite passes.

## 2026-10-31 — LiveCalc gaps closed: unexamined inverse results, function steps, export, failing inverse solves

Goal: the items left open by the worked-solution audit, in order.

**1. The 126 "not ok" inverse results.** Classified from the scan (51 calculations): 78 were "X cannot be negative" because a quantity that is legitimately negative in the calculation's own example was not declared `signed` (so its own value could not be typed back in): 12 calculations (Marcus region, double-pendulum ratio, Lorenz contraction, WLF shift, Tsai-Wu F₁ F₁₂ and linear part, C_mα, Fåhræus C, logMAR, factorial effect B, tight-binding energy, damped-oscillator displacement). Fixed, with a library-wide regression test (`tests/test_signed_outputs.py`: every quantity that is negative in an example is signed). The other 48 were "no sign change found"; run again with a search range ±2× around the example value, about 35 recovered the example, so the root was simple and only the automatic range was at fault (below).

**2. Function steps.** The remaining ~100 LiveCalc functions that showed only expression and result now show their definition with the numbers: sum, mean, median, stdev, var (mean, deviations, squares, n − 1), prod, min, max, hypot, norm, mod, factorial, dot, cross, outer, cumsum, diff, sort, reverse, trapz, cumtrapz, interp, the line fits, percentile, polyfit, det (2×2, 3×3, LU), trace, inv, solve (Cramer for 2×2), matmul, eigvals, svdvals, cond, rank, lstsq, linspace, range and the decompositions (definition only). Constants (`Gnewton`, `c0` ...) are listed and substituted; `v[2]` shows the list and the entry. Functions inside longer expressions are explained, then substituted. Elementary functions keep their plain steps by choice. Tests compare the shown numbers with numpy.

**3. Export.** `livecalc_export(fmt="markdown", steps=True)` and the page's Markdown and Copy buttons (when Show steps is on) append each calculation's numbered working as display maths; the other formats are unchanged.

**4. Failing inverse solves.** Root causes and fixes:
- automatic range too narrow: the scan covered 1e-9 to 1e9 in SI, so atomic lengths (3.4e-10 m), picometres and kilograms of planets (6e24) were never bracketed. A second, wide pass (1e-40 to 1e40, 321 points, 4 s budget) runs when the first finds nothing; it is also told to skip a sign change that is a pole or jump and carry on to the next one, instead of giving up at the first.
- a root that only touches zero (a peak or a minimum: Planck peak, optimum of a filter, range maximum): a bounded minimisation of |f| around the smallest value tried, accepted only if it is zero to 1e-9 of the sides of the equation, reported as an info diagnostic saying the equation touches zero there.
- `ber_digital_modulation` EbN0: SymPy leaves `erfcinv(float)` unevaluated, then compared a relation as a boolean; now evaluated with SciPy.
- `melting_front_stefan_problem`: the coupled solver lambdified an expression containing a run-time ODE function (`ODE0_T`) with no namespace entry (NameError); `fast_lambdify` now gives each such function a plain callable.
- `tracer_wave_in_a_closed_loop`: a PDE solver raised "Factor is exactly singular" at a trial value; solver RuntimeErrors and LinAlgErrors inside an evaluation now count as "undefined here" so the scan moves on.
Result on the 245 combinations that failed in the earlier scan: 226 solve, 9 are genuine (multi-valued, discrete or a value never reached), 3 time out at the 10 s default (stefan k and cp, PMV) and 7 could not even run their base example under the scan's 8 s limit while the machine was loaded.

**Behaviour to know about.** When an equation is flat at zero over an interval (a piecewise `Min`, a `Piecewise` with a flat branch) or has several roots, the scan returns the first it meets from the small end, which can be a tiny or arbitrary value (for example a residue-type variable of 1.8e-40 for an amino-acid charge); the diagnostic says it was found numerically and to give a search range if another solution is expected.

**Not done.** Elementary-function steps, complex-number functions and `polar`, list-by-scalar arithmetic and the symbolic derivation of `findroot`/`sumover` remain plain; `stefan` k and cp and PMV need more than 10 s; Lennard-Jones σ at its own minimum and a few similar tangent cases with several equal unknowns were not resolved.

## 2026-10-31 — LiveCalc leftovers

Goal: the items left plain by the previous PR.

- **List arithmetic.** `[1, 2, 3] m * 2`, `v*2 + 5 kg`, `sin([0, 1, 2])`: the expression written out for the first three entries and the last (`livecalc_work._elementwise_steps`); matrices, indexing and aggregate functions are not expanded this way (the aggregate functions have their own steps).
- **Elementary functions** as the whole line show what the function is and the argument as it sees it (an angle in degrees or with a unit converted to radians, `cosh` with its definition). Inside a longer expression they stay plain, on purpose: a stack of one-line explanations for every `sqrt` would hide the arithmetic.
- **Complex numbers.** `real`, `imag`, `conj`, `abs`, `arg` and `polar` show their definition with the numbers, and any complex result shows its rectangular and polar forms.
- **`findroot` and `sumover`, exactly.** For unitless formulas SymPy solves `f(x) = 0` and the root inside the bracket is shown (and checked against Brent's answer); `sumover` shows the closed form in N (for example n²: N(2N² + 3N + 1)/6) and the exact sum (205/144 for Σ 1/n², 1 ≤ n ≤ 4), checked against the numeric total; sums over more than 400 terms and formulas SymPy cannot do keep the term list and the method.
- **Lennard-Jones σ.** Not a tangent case after all: the two roots (x = σ/r = 0.851 and 0.93) lay inside one cell of the 4-points-per-decade scan, so both ends had the same sign. A hidden-root search now looks inside the cells where |f| is smallest for an extremum of the other sign (`_hidden_root`) and finds the lower root. When there is still no root but the equation comes within 5 % of zero at an interior point, the message says where and that the value may just miss a peak or minimum (typed rounded, for instance).
- **PMV.** The 7-minute hang was SymPy's `solve` on `PPD = 1 − 0.95·exp(−0.0335·PMV⁴ − 0.218·PMV²)`: a single uninterruptible arithmetic operation inside `simplify` (the time limit only acts between Python calls). A polynomial of degree 3 or more inside an `exp` or `log` now skips straight to numerical inversion: 0.5 in well under a second.
- **Stefan k and cp** remain slow by nature: every trial value integrates the PDE (about 0.3 s each, roughly a hundred trials). They are correct (ρ solves) but need about 30 s; raise the time limit in Settings.

Tests: `tests/test_livecalc_leftovers.py` (18), with two older tests updated because their subjects are now explained (an exact root replaces the Brent text for x² − 2; elementary functions are explained as a whole line).

## 2026-10-31 — Importing material data from the CRC Handbook (local extract)

**Goal.** Try to extract material properties from the extractor's output of the CRC Handbook (89th ed., 2692 pages, 2176 tables) into a datapack.

**What the extract looks like.** `handbook.elements.jsonl` has typed elements with, for tables, the cell grid (`table_rows`). Many tables are good (one value per cell); several are not: the grid inherits whatever the PDF's cell structure was, and the "Thermal and Physical Properties of Pure Metals" table is one data row whose cells hold a whole column each ("2. 70 6. 68 3. 62 ..."), with entries missing, so the value-to-metal assignment is ambiguous (counts per column: density 35 of 35 metals, but specific heat 34, conductivity 34, expansion 33). The original PDF was not among the files I was pointed to, so no word-position re-extraction was attempted.

**Decision.** Use only tables where the grid keeps rows and columns, and the one complete column of the metals table. A parser that guessed alignments would produce confident wrong rows, which is the worst outcome for reference data. Result: 205 records (15 pure-metal k(T) curves, 36 alloy k(T) curves, 24 element cp(T) curves, 70 densities, 76 insulating/ceramic materials, 17 rare-earth metals with moduli and strengths). Checked against textbook values (Al, Cu, Fe, Ag, Au, W, Pb conductivity and density; Al cp from the molar table vs the Handbook's own J/g K column within 0.2 %).

**Bugs and surprises on the way.**
- Insulator table: two side-by-side blocks, group headings with indented children whose indentation is lost in the text. Solved with the reading order (left block, right block, next page) and a rule (a lower-case entry after a heading is its child, a capitalised one ends the group, one named exception for 'Mica: Canadian'). First attempt treated each block alone and lost the groups ('alosite', '100 mesh', '92 percent' became orphan records).
- Glasses: names wrap over two lines placed beside different data rows (Vycor lost its third point, 'Pyrex type chemically-' / 'resistant borosilicate glasses' were split), so that table was dropped rather than patched.
- Slug collisions ('slate, ⊥' and 'slate, ||' both became 'slate'): orientation marks are now spelled out.
- My own heredoc turned `\t` into a TAB twice while writing LaTeX-containing code earlier today; here the same trap hit nothing, but the datapack test fixtures now isolate `SLIDERULE_HOME`: once the real extract existed in `~/.sliderule/datapacks`, three existing datapack tests failed because they saw it (`no_user_packs` fixture).

**Licence.** The Handbook is © Taylor & Francis. The pack is local only: output to `~/.sliderule/datapacks`, `crc-*` in `.gitignore`, a test that the default path is outside the repo, test fixtures synthetic. Whether any of it may be shipped with a sold product is a question for the publisher; the strategy doc already says not to without a licence.

**Not done.** Re-extracting the flattened tables from the source PDF with word coordinates (would add cp, k and expansion of the 70 metals and the density of various solids); mechanical strengths of engineering alloys (not in this book); `thermal_expansion` (the Handbook's linear expansion tables were not found in a clean form).

## 2026-11-03 — Open-source preparation, first pass: audit, and CI that had never passed

**Goal.** Prepare the repository for a public release. Started with an audit (secrets, private paths, third-party content, tracked tool config, licence and data provenance), then fixed what it found.

**Audit result.** No key-shaped strings in the tree or in any commit's added lines (pattern scan; `gitleaks` is not installed here); no `/home/...` paths or personal addresses in file contents; the CRC Handbook data was never committed (only the importer and its synthetic test); KaTeX is the only vendored code and ships its licence. Findings: `.idea/` and `.claude/settings.json` were tracked; 98 commits carry a personal email address in their metadata; `materials-typical` rests on vendor web pages (one entry's pages unrecorded); no `CONTRIBUTING`, no data-source note.

**A real bug the audit surfaced: CI had failed on every run (30 of 30).** `ci.yml` tested Python 3.10, but `livecalc_funcs.py` uses backslashes inside f-string expressions (41 places), which is a `SyntaxError` before Python 3.12. The package declared `requires-python >=3.10` and CI was red from the start of the matrix; I had been merging on local test runs. Dead end avoided: rewriting 41 f-strings to keep 3.10, which is end-of-life since October 2026 anyway. Fix: `requires-python >=3.12` (Pyodide 0.29 ships 3.13, so the web build is unaffected), ruff `target-version py312`, CI matrix 3.12 and 3.13.

**Lint.** `ruff check .` reported 357 errors under the default rule set (10,652 `E501` line-too-long alone once selected). Narrowed to correctness rules (`E4 E7 E9 F W`; ignore `E731 E741 E702`, which the maths code uses on purpose, and `F841` for 19 leftover unused locals to clean case by case). Auto-fixed 27 unused imports and trailing whitespace in 24 files; ruff is clean.

**Other changes.** CI now has least-privilege `permissions`, a lint job, a package job that builds the wheel and checks it holds the web app and datapacks (verified locally: 179 files, both present), a weekly schedule, pip caching. `pyproject.toml`: SPDX `license = "MIT"` plus `license-files`, authors, classifiers, project URLs. `.idea/` and `.claude/` untracked and ignored. README: Python 3.12 requirement, the Pyodide CDN dependency, a no-warranty/safety-critical note, and a licence-and-data section. New `DATA_SOURCES.md` and `CONTRIBUTING.md`. Repo-local git identity set to the GitHub noreply address so future commits carry no personal email.

**Still to do.** Normalise the history (mailmap rewrite plus force push; GitHub keeps pull-request refs to old commits, see the discussion in chat), re-source `materials-typical` from open references, `CODE_OF_CONDUCT`, `SECURITY`, issue and PR templates, changelog, a secrets scan with a dedicated tool.

## 2026-11-03 — CoolProp fluids pack and a NIST cryogenic importer

**Goal.** Add open-licensed property data: CoolProp, plus public-domain/open sources where scraping is allowed.

**Done.** `scripts/build_coolprop_pack.py` + shipped pack `fluids-coolprop` (59 records, 30 fluids; `CoolProp` added as optional extra `props` and to `dev`). Dead ends on the way: the first version stopped the liquid curve 0.5 K below the boiling point, so the textbook check for liquid nitrogen at 77.35 K failed with "outside the stored range" (the saturated liquid or vapour is now the end point of each phase); air's "liquid" record (a pseudo-pure mixture) is dropped. `scripts/import_nist_cryo.py` (26 pages listed, 23 parsed, 3 skipped for their layout) builds a local pack; robots.txt checked (none on trc.nist.gov; www.nist.gov's does not disallow it). The licence track of those fits (copyrighted SRD or free NIST data) is not stated, so the pack stays local, like the CRC one, until NIST confirms. Materials specific-heat floor lowered from 100 to 0.001 J/(kg K) for cryogenic curves. Values checked against known figures (304 stainless, 6061-T6, lead, molybdenum, Teflon).

**CI had also failed on one slow test** (`test_inverse_fixes` wide scan hit the 10 s watchdog on the runner): the test now sets its own time limit. Details of sources and what was not used: docs/DATA_AND_STANDARDS_STRATEGY.md §14, DATA_SOURCES.md.

## 2026-11-03 — CRC pack: element names for the rare earths, and a silent regression from a re-extracted Handbook

**Symptom (reported).** Offering a pressure input from data, the rare-earth tensile strengths were listed as `γCe`, `αLa`, `Er` and similar, with no element names. **Cause:** the Handbook table names rows by symbol, with a Greek letter for the crystal phase, and the importer used the printed text as the record name. **Fix:** a symbol-to-name table (all elements the importer meets); records are named `Cerium (gamma)` with designation `γ-Ce`, ids `element-cerium-gamma`; Ge and Si, also bare symbols in the metals list, are named.

**A second problem found while verifying.** Re-running the importer gave 131 records instead of 205 (even with my change stashed). The extractor output had been re-generated (file dated after my first import) and now carries proper column grids: the rare-earth table at p.748 became two tables with one column per quantity and a three-row header, and the pure-metals table (p.2082-83) is one metal per row. The old parsers matched neither, so rare-earth rows and all densities vanished **without any message**. Fixes: both parsers read the new layout (the old one is kept as a fallback); the pure-metals table now yields density, thermal expansion and specific heat (25 °C) and conductivity (27 °C) for about 70 metals, which the flattened extract could not give; footnote `b` (value at 100 °C) is dropped and `a` (estimated) is noted; the importer prints a WARNING when a table it depends on gives nothing, so this cannot be silent again. Result: 195 records, rare earths merged with their pure-metal records where there is no phase. Tests: new-layout fixtures, footnote rules, names, phases, the warning.

## 2026-11-05 — NIST cryogenic pack ships; materials-typical sources withdrawn

**Request.** The user quoted NIST's terms (a non-exclusive, royalty-free right to print, publish, distribute and create derivative works of NIST data) and asked that the `materials-typical` reference text be replaced by "citation needed".

**NIST.** Read NIST's licence page for the exact conditions of redistributing non-SRD works: acknowledge NIST, mark changes with their date and nature, include NIST's statement verbatim. The cryogenics pages carry no SRD copyright notice, and the licence page gives no way to classify a dataset, so the pack ships on that basis and is to be removed if NIST says these fits are SRD. `scripts/import_nist_cryo.py` now writes the acknowledgement, the change notice and the statement into the manifest and a `NOTICE.md`, and dates each source by the day its page was fetched (2026-11-03). Built from the cached pages, 23 materials; the earlier local copy in `~/.sliderule/datapacks/nist-cryo` was removed (same pack id). `.gitignore` no longer excludes it.

**materials-typical.** All seven manifest references now read "citation needed"; URLs and access dates removed; the licence and status lines say the sources are uncited. Per-value notes (how a number was chosen) are kept. Tests adjusted: pack list and counts, the 6061 search now also finds the NIST record, and a shipped-pack test checks the NIST notice and values for 304 stainless (15.1 W/(m K) and 470 J/(kg K) at 293 K).

## 2026-11-05 — Community files

**Done.** `SECURITY.md` (scope written from the real attack surface: the restricted equation checker in `core/safeparse.py`, the unauthenticated local server on 127.0.0.1, folders read and written, rendered output; reports through GitHub's private vulnerability reporting), `CODE_OF_CONDUCT.md` (short, written for this project and adapted in spirit from the Contributor Covenant), issue forms (bug, wrong result or formula, data correction with a source required and a "no copyrighted tables" warning), a pull-request template with the formula/data/docs checklist, `CHANGELOG.md`, `CITATION.cff`, `dependabot.yml` (pip and GitHub Actions), and links from README and CONTRIBUTING. **Needs the maintainer:** private vulnerability reporting must be switched on in the repository settings for the report link to work; the response times promised in SECURITY.md (acknowledge within a week, decide within 30 days) and the conduct-report contact (the GitHub profile, no email) are the maintainer's to confirm.

## 2026-11-05 — Native desktop window made to work

**Question.** Is the non-web version still part of the project? It was: `sliderule app` (pywebview around the local server, from the first commit), but README called it "untested" and nothing ran it.

**Tried and found.** Running it: (1) without a GUI toolkit it crashed with a raw `WebViewException` traceback; pywebview needs Qt or GTK and the `desktop` extra did not provide one. (2) With `pywebview[qt]` installed, the window opened on this machine (Linux, Wayland, Qt 6 WebEngine); loading was confirmed through Qt's remote-debugging port (page title and URL of the window) instead of a screenshot of the desktop. (3) Reading the code against pywebview's behaviour found three latent bugs: pywebview blocks downloads by default, and the web app's Export, Save case and CSV buttons are `a[download]` links, so they would have done nothing in the window (not exercised, because a save dialog cannot be driven here; the fix is the documented `ALLOW_DOWNLOADS` setting); the window could be created before the server was up; and the fixed port 8765 would, if busy (for example another `sliderule serve`), show the other server's page in the window.

**Fixes.** The server must report `started` before the window opens (20 s limit with a clear error); default `--port 0` picks a free port; `ALLOW_DOWNLOADS` is on; a missing toolkit prints how to install one and mentions `sliderule serve`; `desktop` extra = `pywebview[qt]` on Linux, plain `pywebview` elsewhere. Tests use a stand-in for pywebview (order of events, free port, downloads flag, both error paths, a busy port). **Dead end in the tests:** the first version fetched `/api/meta` as the readiness check and timed out; that endpoint is slow on its first call because it loads the whole catalogue (about 5 to 8 s), so the test now fetches the page. **Not verified:** Windows and macOS, and the actual save dialog.

## 2026-11-05 — `sliderule app --api`: the desktop app as a local server for other programs

**Request.** An option on the desktop app to turn on the API backend so other applications can run SlideRule functions.

**Design, and why it is not just "expose the port".** The existing server has no authentication and no Host or Origin checks (fine on the window's random private port, where nothing predictable can be aimed at it). Put on a known port it would be reachable from any web page the user visits: DNS rebinding makes the browser treat the page's own name as 127.0.0.1, and a cross-origin simple POST (`text/plain`) is sent without a preflight; the API includes endpoints that write files (`/api/custom`, `/api/lists`) and one that switches off the time limit. So `--api` starts a **second, API-only server** on `--api-port` (default 8765), leaving the window's private server alone, with `server.ApiGuard`: loopback-only `Host`, refusal of any request with a foreign `Origin` (browsers send one; scripts do not), an optional bearer token (`--api-token` or `$SLIDERULE_API_TOKEN`, constant-time compare, the API description stays public), and opt-in CORS (`--api-origin`, repeatable) answered before the checks so a local web app can read its replies. It warns at start-up when no token is set; a busy port fails before the window opens.

**Checked.** Tests for the guard (token, rebinding, `text/plain` cross-site POST, CORS preflight for listed and unlisted origins, unguarded app unchanged) and for the option through the stand-in webview. Then the real app with the real Qt window, called from `curl`: no token gave 401, a conversion and a column-buckling solve (Pcr 1754.6 kN, equal to π²EI/(KL)²) worked with the token, a rebinding Host gave 403 and a cross-site `text/plain` POST gave `BAD_ORIGIN`. Test slips on the way, not code bugs: the convert query parameters are `from` and `to`, and the API port answers 401 before 404 for a page request.

**Not done, worth doing.** `sliderule serve` has the same unguarded exposure on its fixed port 8765 (it is the same server without the guard); the guard could be switched on there for loopback hosts, which needs the browser UI's own requests to pass it (they send the server's own Origin, which the guard allows). The API has no versioning and no rate limit.

## 2026-11-05 — The guard on `sliderule serve`

**Goal.** The follow-up left open by the `--api` work: `sliderule serve` had the same unguarded exposure (fixed port 8765, no Host or Origin checks, endpoints that write files).

**Done.** `serve` (and its `--reload` restart, whose factory runs in a fresh process, so the bound host is passed in `SLIDERULE_SERVE_HOST`) now builds the app with `ApiGuard`: loopback `Host` only and no foreign `Origin`. No token on `serve`, since the bundled page would have to send it. `--host 0.0.0.0` (or any address that is not loopback) is a deliberate opening to the network: the Host rule is dropped (new `ApiGuard.any_host`) because the server is then reached under other names, the Origin rule stays, and a warning is printed. Tests: loopback guarded, the page's own `GET /` and its `fetch()` POST and PUT under `127.0.0.1`, `localhost` and `[::1]`, the network case, the reload factory, which hosts count as loopback.

**Checked in a real browser** (the in-app browser against a real `serve`): the full UI loads under `127.0.0.1` and under `localhost` (1,377 calculations, no console errors, all its `/api/rpc` calls 200), a column-buckling solve through the page's own `fetch` returns 1754.6 kN; with `curl`, a rebinding Host gives 403 and a cross-site `text/plain` PUT trying to switch off the time limit is refused (`BAD_ORIGIN`) and the setting stays on. **Limits:** a non-browser program on the same computer can still use `serve` (no token, by design); the window server of `sliderule app` was left unguarded (random port, same machine).

## 2026-11-06 — Re-sourcing `materials-typical` from open references

**Goal.** Replace the withdrawn vendor references ("citation needed") with open ones.

**What was tried.** Web searches for MIL-HDBK-5J (cancelled 2006; successor MMPDS is not open; no free copy found), then for open government equivalents. Agents with the fetch tool could not read PDFs (scans, binary, or over 10 MB), so I read them myself: the harness saved the PDFs the agents fetched, and `pdftotext` handled the text one while `tesseract` OCR handled the scans. Dead ends: the first NASA PDF a search suggested (ntrs 19720022809) was the handbook for alloy **7075**, not 6061; the DTIC document returned 403; a guessed JRC URL 404'd; NIST NCSTAR 1-3D and the FHWA manuals were over the fetch limit. Running OCR on every page of both handbooks with all cores was far too slow (tesseract threads fought each other: 17 minutes for about 50 pages); the fix was targeted pages with one thread per process and a TOC pass to find chapters (printed page numbers differ from PDF pages by 7 to 9).

**Found.** NASA CR-123772 (6061) and CR-123775 (Ti-6Al-4V), 1972, with abstracts, elastic properties, physical properties and design-strength tables (typical values and A-basis or specification minimums); NISTIR 7401 for mild steel; the Wyoming DOT manual for steel modulus and expansion. OCR digits were verified against the page images for every value used, and the dual units printed beside them agree (for example 7.03e3 kg/mm2 against 10.0e3 ksi; 0.40 cal/(cm s C) against 1160 Btu in/(ft2 h F), both 167 W/(m K)). The Ti-6Al-4V abstract prints thermal conductivity as 0.012 with garbled units, so the NIST fit is used. **Result:** `materials-typical` 0.2.0, built by `scripts/build_materials_typical_pack.py` with printed values and unit factors in the script; the 6061 and Ti rows now have strengths with the printed minimum as `low`; only the steel Poisson's ratio still reads "citation needed". Tests: golden values typed from the pages, low never above typical, only one unsourced value, the shipped pack equals a fresh builder run.

## 2026-11-07 — The steel Poisson's ratio, from a 1946 NBS paper

**Goal.** Close the last "citation needed" in `materials-typical` (steel Poisson's ratio), which needed a download the fetch tool could not do (the file is over 10 MB). With the user's go-ahead, `curl` fetched `jresv37n4p211_A1b.pdf` from nvlpubs.nist.gov (15,950,891 bytes, 12 pages) into its own folder in the scratchpad; it has a text layer, so `pdftotext` read it (no OCR needed this time).

**Found.** NBS Research Paper RP 1742, Stang, Greenspan and Newman, J. Res. NBS 37, 211 to 221 (October 1946). Table 2 (page 216) lists Young's modulus and the elastic-range Poisson's ratio for every specimen (ratio taken as minus axial over transverse strain from the linear parts of the curves). Structural low-carbon steel to ASTM A7-42, direction 0: 0.256, 0.265, 0.270, 0.265, 0.260, 0.271 with E of 29,300 to 30,300 ksi; fully killed carbon steel at room temperature 0.263 to 0.279 over 18 specimens (mean 0.271). The digits were read from a 230 dpi crop of the table, not from the text layer. **The result contradicts the unsourced 0.3 the pack carried**: the measured value is 0.265 (stored with 0.256 and 0.271 as low and high); the paper's own 0.3 appears only in an appendix as an illustrative figure for an idealised material. The pack is 0.2.1, built by the same script, and no value reads "citation needed". Tests: golden value, extremes, no unsourced values. Caveat in the notes: 1940s steels, modern A36 and A992 not tested.
