# Architecture and design decisions

```
frontend (vanilla ES modules + KaTeX)  ──►  Engine interface: call(method, params)
                                              ├─ HttpEngine     → FastAPI  ┐
                                              └─ PyodideEngine  → Worker   ┴─► sliderule.api.handle() ─► core + units + library
```

## One engine, two deployments
The core is Python with SymPy for the algebra and NumPy/SciPy for linear algebra (the integrators themselves are our own, so events and exact landing on output times work). The local app wraps it in FastAPI; the web app loads the very
same package into Pyodide (CPython compiled to WebAssembly) inside a Web Worker.

| Option | Verdict |
|---|---|
| Re-implement the engine in TypeScript | Two codebases to keep numerically identical; loses SymPy's rearrangement. |
| Require a server for the web version | Not "runs in a browser"; hosting cost for cheap local compute. |
| Pyodide (chosen) | One source of truth. Costs a large first download; the API layer is transport-free so FastAPI is not needed in-browser. |

`sliderule.api` takes/returns plain JSON-compatible data; `handle()` adds an `{ok, result|error}` envelope used by both transports.

## Taxonomy (`core/taxonomy.py`)
Disciplines and sub-disciplines mirror `docs/reference/disciplines.txt`; a test parses that file and fails if the two drift, and another fails if any
sub-discipline has no calculation. A calculation lists its disciplines and the sub-disciplines it serves; tagging a sub-discipline also lists the calculation
under the discipline that owns it. Logarithmic levels (dB) are plain numbers whose variables are restricted to `units=["dB"]`, so they can never be silently
converted to a linear unit.

## Units (`sliderule/units`)
A dimension is a vector of rational exponents over (kg, m, s, A, K, mol, cd, currency); fractions keep `s/m^(1/3)` (Manning) exact.
Units are defined *from other units* in `defs.py` (`psi = lbf/in^2`, `lbf = 4.448… N`), so constants are definitions, not scattered magic numbers.
Temperature scales are affine (`SI = (x + shift)·factor`); inside compound units or for ΔT variables they are differences.
Guard rails: `lb` and `ton` are rejected (gauge pressure `psig`, `barg`, `kPag`... are offset units like °C, referred to one standard atmosphere); implicit multiplication (`N m`) and `m2`-style exponents are rejected.
Convention: Hz = 1/s and radians are dimensionless, so ω = 2πf is written explicitly in formulas. (An earlier draft set Hz = 2π/s, which silently broke non-angular uses such as bandwidth.)

## Calculations (`core/model.py`, `library/`)
A `Calculation` is variables (a default unit fixes each dimension) plus equation strings. At import, equations are parsed with SymPy and
**dimensional homogeneity is checked**; a bad equation fails the test suite, not a user. `validity` conditions produce warnings (e.g. ρ < 1 for M/M/1).

## Solving (`core/engine.py`)
Inputs → coherent SI → *causal ordering* (repeatedly pick an equation with exactly one unknown; the idea behind Modelica's BLT sorting) →
SymPy isolates each unknown → numeric evaluation → output-unit conversion. One mechanism handles forward chains and "solve for an input".
When the ordering stalls because several equations share several unknowns, `core/simul.py` takes over: a maximum matching of equations to unknowns plus the strongly connected components of the resulting graph (Tarjan) give the coupled *blocks*; a block is solved once it is ready (its equations contain no unknowns outside it) and only if the targets need it. A block linear in its unknowns is solved
exactly (`sp.linsolve`, so the closed form appears in the steps; singular systems are reported by an SVD test), otherwise by *tearing* (a tear unknown makes the other equations solvable one after another through `_isolate`, preferring equations linear in their unknown to avoid root-sign ambiguity; the remaining residual is scanned for every sign change on a geometric grid and refined with Brent, rejecting roots that leave another unknown's domain), and failing that by damped Newton with an exact (lambdified) Jacobian, residuals scaled by the size of each equation, unknowns kept to their domain (positive unless signed, min/max, or the user's search range), from a deterministic ladder of
staggered starting points (so a symmetric system is not singular at the start) followed by random log-uniform ones; a few more starts look for a second solution, which is reported (`MULTIPLE_SOLUTIONS`). Equations with numerical nodes (ODE solutions, quadrature) use finite-difference Jacobians. `plan_structure` plans blocks the same way (linear ones always, nonlinear ones with `allow_numeric`).
Steps are recorded as two narratives (symbolic, numeric) of structured LaTeX lines, rendered with KaTeX.

## System Design (`design.py`, `web/js/system.js`)
A *block* is a calculation in which every variable has a role: **input** (arrives on a wire, or is typed in when unwired), **output** (computed; the
equations are rearranged for it, exactly as when you tick "find" in the calculator) or **constant**. `check_block` decides whether a role assignment is
solvable *without any numbers*, using a value-free copy of the solver's causal-ordering loop (`engine.plan_structure`), so the editor can flag an impossible
choice (for example two outputs sharing one equation) the moment it is made.

A *wire* joins an output to an input and is legal only if both ends have the same **type** = physical dimension (absolute temperature and temperature
difference are distinct types), the blocks differ, the input has no other wire, and the graph stays acyclic. The browser applies the rules while dragging
(compatible ports glow, incompatible ones dim, and a refused drop explains why); the server applies them again to every graph it evaluates, so a hand-edited
or loaded file cannot sneak an invalid wire in. `solve_system` evaluates blocks in topological order and passes each wired value downstream in coherent SI,
so unit differences between the two ends are converted automatically.
Dimensionless ports (ratios, angles) are all one type; that is deliberately loose and is the only place two unrelated quantities can be connected.

**Export (`design_export.py`).** `system_model` gives every variable a block-qualified symbol (`x__b1`, shown as x^(b1)), lists each block's equations, and composes
a closed-form expression for each output by chaining the isolated expressions and substituting through the wires, so one expression runs from the free inputs
and constants to the final result. `build_document` turns this into a small document model (headings, paragraphs, display math, tables), rendered by
`render_latex` / `render_markdown` / `render_html` / `render_python` (a self-checking SymPy script: inputs converted to SI with `to_si`, the block equations, closed forms, `evaluate()` for other inputs, and the reference values it must reproduce) (the HTML page embeds KaTeX — script, stylesheet and woff2 fonts as data: URIs, about 0.7 MB — so it renders with no network; `build_web.py` ships those files in the Pyodide bundle, and without them the page falls back to pinned CDN links); the mode picks symbolic, numeric (values and step-by-step substitution from `solve_system`) or both. Tests check the
closed forms against `solve_system` numerically, parse all math with the vendored KaTeX (`throwOnError`), and run pandoc over the files.
Reachable as `design_export` (RPC / Pyodide) and `POST /api/design/export`.

**Math blocks (`design_math.py`).** The toolbar's + − × ÷ chips (drag onto the canvas or click) add blocks that do arithmetic between wires. A math block is turned into an ordinary generated `Calculation` (`y = x1 + x2`, ...) whose port units come from the resolved types, so solving, worked steps, the wire rules and all four exports need no special case. What is special is *typing*, decided by `resolve_types`: an add/subtract block has one type, **locked to the first wire connected to it** (earliest in the graph's wire list, input or output side; chained math blocks are settled by iterating) and released when no wire remains, at which point the editor also clears its typed values; a multiply/divide block takes its input types from the wires (or from the unit typed with a value) and its output type is the product/quotient of the dimensions, so N · m is J, m / s is velocity and N / N is dimensionless. The type rules live only in Python: the editor asks `design_math` (RPC) for every port's type after each edit and draws open ports grey. Unwired inputs take a typed value with any unit of the right dimension; add/multiply can have up to 8 inputs. Math blocks are stored as `{id, kind: "math", op, n, x, y, values, out_units}`.

**Comments.** Any block, calculation or math, can carry a free-text `comment` (up to `MAX_COMMENT` = 2000 characters, validated server-side). The editor shows it under the block's title (two lines, full text on hover), edits it in the inspector, and stores it in the saved graph and the browser's autosave; solving ignores it, and the LaTeX, Markdown and HTML exports print it under the block's heading and the Python script writes it as `#` comment lines under the block's header.

**MATLAB and Excel exports (`design_code.py`).** Besides LaTeX, Markdown, HTML and the SymPy script, a system exports as a MATLAB/Octave script and as an `.xlsx` workbook with live formulas. Both come from one *plan* (a differential equation with a closed-form solution is exported as that formula; a plain initial-value problem becomes an `ode45` call in the MATLAB script; finite `Sum` series become `sum(arrayfun)` / `SUMPRODUCT`; Excel writes Bessel functions as BESSELJ/Y/I/K for integer orders): the free inputs and constants converted to SI (`SI = (value + offset) × factor`, the registry's convention, which matters for offset units such as °F and psig) and, per block in dependency order, one step per computed quantity (the same causal ordering the solver uses, with wires substituted by the quantity that feeds them), each carrying SlideRule's own value so the file checks itself. MATLAB uses sympy's Octave printer (plus `log10`, `log2`, `erfc` and `ellipke`) with element-wise operators written plainly and every `Piecewise` hoisted into an `if/elseif/else` block, because an expression cannot branch. Excel formulas come from a small converter (`_xl`: Excel's precedence, `ATAN2(x, y)` argument order, `IF` for `Piecewise`, `SQRT`, `1/…`) and refer to inputs and results by **defined names** (`=PI()*Dr__b1^2/4`; names are de-duplicated case-insensitively because Excel ignores case); the workbook (Inputs with yellow editable cells, Calculations with value, shown value and a Check column, About with block comments) is written with the standard library only (`zipfile` plus hand-made XML, no new dependency, works in the browser build) and stores cached values, with `fullCalcOnLoad` so Excel recalculates. Blocks that have no formula to write (differential equations, tables, quantities found by root-finding or coupled equations, `Sum`, `uppergamma`, …) are refused with the block named. Verification without Excel or MATLAB: the generated formulas are translated back into Python by an independent test translator and must reproduce SlideRule's results (checked over about 700 library calculations in a one-off sweep and a sample in the suite), and, where LibreOffice is installed, the workbook is recalculated by it from deliberately zeroed cached values.

**Saving a system as an equation (`design_equation.py`).** *Save as equation…* turns the whole graph into one "My equations" calculation. It keeps the complete system of equations (every equation each block needs, from `system_model`) rather than a closed form, so any variable can still be solved for, expressions stay short (the editor limits an expression to 300 characters) and the result works as a block in another system. A wire merges its two ports into one variable (union–find, the input becomes the output feeding it), the same physical constant in two blocks becomes one variable, clashing names are qualified by block id, unwired inputs keep the typed value as their `example`, and every computed quantity is an output unless the user unticks it (an unticked one becomes an input with the value the system computed, so the saved equation stays consistent). Block comments go into the assumptions. The draft is built by `design_to_equation` (RPC; nothing is saved), validated with the same `calc_from_dict` as hand-written equations and test-solved against the system's own results; the editor then saves it with `custom_save`. A differential equation with a closed-form solution (`design_code.closed_solution`: one ordinary equation, no delay or event, solution known for every dependent) is saved as that solution. The blocks' validity limits are renamed to the saved variables without going through the blocks' positive symbols (which would let sympy decide `a + b > 0` is `True`); any the editor rejects, or that mention a quantity the saved equation lacks, are dropped and listed in the assumptions. Refused with a reason: numerically solved differential equations, events and data tables.

Not supported: feedback loops (algebraic loops need a simultaneous solver), several wires into one input, undo/redo, keyboard-only wiring.

## LiveCalc (`livecalc.py`, `web/js/livecalc.js`, `web/js/markdown.js`)
A scratchpad, not a catalogue calculation: each input line is one statement, evaluated in order with the lines before it. `livecalc_eval(entries, draft)` is
**stateless**: the front end sends the last 200 submitted entries plus the text being typed, and the engine replays them in one scope and returns a result per
line. That keeps one code path for the FastAPI server and Pyodide (no session on the server) and costs about 10 ms for 30 entries.

* **No `eval`.** The text is tokenised and parsed by a small recursive-descent parser (`Parser`) into tuples, with limits on length, tokens, nesting and
  number size, and evaluated on `Q(v, dim, unit)`: the value in SI base units (a float, or a numpy array while plotting), a `Dimension`, and the unit to
  *display* it in. Adding checks dimensions; multiplying merges the unit symbolically (`5 m * 3 m` -> `m^2`, `3 kN * 2 m` -> `kN*m`) and a result built only
  from SI base units takes its named unit (`kg*m/s^2` -> `N`). Offset temperatures (°C, °F) are absolute values that may be shifted by differences (K) and
  converted, never multiplied.
* **Names and units.** A name directly after a number is a unit when it parses as one (`5 m`) even if a variable has that name, and `/name` continues a unit
  (`9.81 m/s^2`); the line says so in a note when a variable was shadowed. In lines with `=` a bare name is a variable (`v^2 = u^2 + 2*a*s` keeps `s` a
  variable); in plain expressions it may be a unit (`1/s`). This is a documented trade-off, not an accident: engineers name variables `m`, `t`, `L`.
* **Statement kinds.** value, assignment, function definition (user functions are re-evaluated per call, depth-limited), *equation* (a line with `=` whose names
  have no value yet is kept, not evaluated), plot, and `text`. Lines that do not parse are text (Markdown) unless they contain a number or `=` and have no two
  words in a row; semantic errors (units, division by zero) are always errors.
* **Steps** are produced for every calculation and shown or hidden by the front end. The SI form of a result follows the unit actually used, so a bending
  moment in `kN*m` is `N*m`, not a joule.
* **Plots** sample 300 points; the independent variable is the single unknown name (or named with `for`), its range may carry units, and non-finite points
  become gaps. `web/js/plot.js::xyPlot` draws it.
* **To My equations.** `livecalc_to_equation(text, entries)` evaluates the earlier entries for variable units and examples, rewrites function spellings
  (`abs` -> `Abs`, `ceil` -> `ceiling`), warns about unit literals inside the equation, and returns a draft that `web/js/custom.js` opens in the editor
  (`#/mine/new?draft=1`, passed through `S.customDraft`). The editor's own validation has the final word.
* **Front end.** The window is the history (re-rendered only when entries change, so typing only touches the preview) plus a live preview of the draft.
  `markdown.js` builds DOM nodes (never `innerHTML`) for headings, lists, quotes, code, emphasis, links and `$maths$`.

## Derivatives and integrals (`core/calculus.py`)
`diff(f, t[, n])` and `integrate(f, (x, a, b))` parse to unevaluated `Derivative`/`Integral` objects (variables of an integral that are not declared quantities become dummy real symbols). The equation is
dimension-checked *as written* (`dimcheck.analyze` knows `[d^n f/dx^n] = [f]/[x]^n` and `[∫f dx] = [f][x]`, taking the dummy's dimension from the limits), then evaluated with `doit(manual=True)`
(textbook integration only, which keeps it bounded, under the user's time limit — see below) and checked again.
The result is plain algebra, so `_isolate`, solving in any direction, the unit lines and System Design are unchanged; `Equation.written` keeps the unevaluated sides so steps, the calculator, exports and the
generated Python script can show the equation as entered. `safeparse` allows the two calls with strict shapes (definite integrals only, bounded derivative order, at most 4 calls). Unevaluable or
undefined integrals are reported; an integral with no closed form is kept and integrated numerically (below). Differential equations are a separate mechanism (next section).

Sums: `summation(term, (n, a, b))` (literal limits, ≤ 500 terms, checked in `safeparse`) becomes an unevaluated `sp.Sum`. `dimcheck` gives the index no dimension; `calculus.evaluate` swaps sums for placeholder symbols around `doit` so they
are never expanded, and flags the equation `numeric_integral` (so `_isolate` refuses to rearrange for a symbol inside a sum and numerical inversion takes over). `_evaluate` compiles an expression containing a sum with `lambdify(modules=["math"])` (a Python loop,
cached) and falls back to SymPy's arbitrary-precision `N` on overflow or domain errors.

## Differential equations (`core/ode.py`, `core/numeric_ode.py`)
An `odes` entry is parsed into an `OdeSystem`: the dependent quantities become SymPy functions `y(t)`, derivatives are replaced by state symbols and the system is solved for the highest derivatives (`sp.solve`), giving an
explicit first-order system `s' = f(s, t, params)`. Dimensions are checked on that form, with the friendly names restored in messages. `dsolve` (ICs included) is tried first; an explicit result becomes one ordinary
`Equation` per dependent (`y = closed form`), so `_isolate`, solving in any direction and System Design are unchanged. Otherwise each dependent gets an `Equation` `y = ODE_k(inputs…)` where `ODE_k` is a dynamically created
SymPy `Function` whose `_eval_evalf` runs the numerical integrator, whose `_sliderule_result` gives `dimcheck.analyze` the result's dimension, and which `_isolate` refuses to rearrange. Runs are memoised, and the engine reuses
them to build the plot series and the table (`Solution.series/table`, `ode_times`). `numeric_ode` has its own integrators (NumPy only for dense solves): Dormand–Prince 5(4) with FSAL and exact landing on requested times, and an L-stable implicit-Euler-with-Richardson
solver (numerical Jacobian, Newton, step control) that takes over when RK45 needs more than 20 000 steps; checked against exact solutions, the Robertson stiff benchmark and blow-up detection. Integrals without a closed form stay
as `Integral` nodes that SymPy evaluates by adaptive quadrature (`NonElementaryIntegral` is normalised to `Integral`, which its evaluator recognises). Integrals inside the equations (`_extract_integrals`): those free of the unknowns and `t` are evaluated up front (a closed form is substituted; one without a closed form becomes a parameter symbol evaluated once per run by
SymPy's quadrature), `integrate(f, (s, start, t))` is substituted when closed form exists and otherwise becomes a hidden state `z' = f, z(start) = 0` (the same state is added to the `dsolve` system, which often still succeeds for linear
problems); anything else is refused. Closed forms can be singular at special parameter values, so every closed-form system also owns a numerical node (`fallback`) and the engine (`_ode_fallback`) and the plot (`trajectory`) switch to
numerical integration when the formula cannot be evaluated. Numerical inversion (`_invert_numeric`, `core/rootfind.py`): when `_isolate` fails — or succeeds but its closed form cannot be evaluated — and the unknown is a target (or a second pass finds it is still needed), the engine scans a grid
(geometric between 1e-9 and 1e9 SI, narrowed by the variable's min/max or a user range; both signs for signed variables) for the first sign change of `lhs − rhs`, then runs Brent's method, with each evaluation going through the same `_evaluate`
(so numerical ODE nodes, events and quadrature just work). A `root_x(...)` placeholder function carrying x's dimension stands in the symbolic dependency graph (unit lines, pruning, closed-form substitution), and `plan_structure(allow_numeric=True)`
plans such equations as solvable for System Design role checks and the editor. The scan skips points where the equation is undefined; a sign change that is a pole (residual not small) is refused; the time limit covers every evaluation.
Events (`EventDef`, `numeric_ode.EventSpec`): after each accepted step both solvers compare the sign of `g` at the ends; a crossing in the allowed direction is bracketed by bisection on the cubic Hermite interpolant (y and f at both
ends; for RK45 the FSAL stage gives f for free), then polished by a few secant steps against the real integration from the step start, and the state at the crossing is snapped (components below 1e-13 of the largest read 0). A terminal event ends the
run there. Event outputs are ordinary `Equation`s on numerical function nodes (`event_value`), so the engine, units and steps work unchanged; they force the numerical path. Exports: LaTeX/Markdown/HTML show the ODE as written with its conditions; the Python script re-solves the block with SciPy (`export_support.py` for events, delays and boundary-value problems, `export_pde.py` for the grid kernel) from a plain-data `spec` that `design_export._system_spec` builds, and each result node carries a `_sliderule_role` that says which result of the solution it is.
Boundary-value problems (`boundary` + `end` in the same `odes` entry; `BvpDef`, `core/bvp.py`): `build` reduces the equations to the same first-order system but, instead of initial values, parses `where: condition` strings
into residuals in the state symbols (the highest derivative is replaced through the equation, so any condition is allowed) and checks their dimensions and the position's. `_try_closed_form_bvp` takes `dsolve`'s general solution, substitutes
it into the conditions (derivatives evaluated at the positions) and solves the linear system for the integration constants with `sp.solve`; the result is an ordinary algebraic `Equation`. Otherwise the numerical path is `bvp.solve`:
multiple shooting with nodes at the interval ends, at every condition position and on a uniform subdivision (8 segments, doubled up to 32 if Newton stalls). The unknowns are the state vectors at all nodes; the equations are continuity
(`Y_{i+1} − Φ_i(Y_i) = 0`) and the conditions. `Φ_i` and its Jacobian come from integrating `[y, S]` with `S' = (∂f/∂y) S` (the variational equations; `∂f/∂y` is symbolic, lambdified), so Newton is exact and a linear problem takes
one step. The linear system is solved densely with partial pivoting; a smallest-to-largest pivot ratio below 1e-7 means the problem has no unique solution and is reported as such (also checked at the starting guess, which can
already satisfy a homogeneous problem trivially). Newton is damped by step halving on the scaled residual. The solution at the requested position is obtained by integrating from the nearest node on its left; the plot samples every
segment. `OdeSystem.interval()` gives the span (start → end) used by plots and checks; the node solution is memoised per input vector without the position, so plotting and evaluating reuse it. Closed-form BVP results outside `[start, end]` get a warning; numerical ones an error.

Partial differential equations (`core/pde.py`, `core/banded.py`): an `odes` entry with `time` is routed by `ode.build` to `pde.build`, which expands the equation with SymPy (`doit`, so conservative forms work), swaps the derivatives of the unknown
for symbols, solves for the highest time derivative, turns each end condition into either a value `g(t)` or a slope `G(u, u_t, t)` (a slope condition becomes a ghost node `u_{-1} = u_1 − 2hG`, keeping second order), and checks dimensions. The result
is a `PdeSystem` that duck-types `OdeSystem` (`numeric`, `dependents`, `written_latex`, `condition_latex`, `last_result`, `inputs`), so `eq.ode` machinery, steps, System Design and exports work unchanged; `_make_fn` provides the function node. Numerically, the right-hand
side is lambdified once per parameter set with the parameters folded in; nodes are updated with list comprehensions over slices. First-order equations use `numeric_ode.stiff` with a banded finite-difference Jacobian (three colour groups, so three
evaluations) and `banded.BandedLU` (LAPACK `dgbtrf`/`dgbtrs` through SciPy: factor once, solve for each Newton iteration); second-order ones use `rk45`. Tolerances are relative to the largest value of the field, so tiny tails do not force small steps.
One run lands on 60 evenly spaced times (plus requested ones) and is memoised, serving the value, the profile snapshots, the history and the table; a second run on half the intervals gives the error estimate. `engine._pde_extras` builds the plot series
(`overlay` series: several curves in one figure). `stiff` gained `jacobian=`/`factor=` hooks and no longer shrinks its step size after a step shortened only to land on an output.

Steady 2-D problems (`core/pde2d.py`): an `odes` entry with `second` is routed to `pde2d.build`, which expands the equation, replaces derivatives by symbols, keeps the residual `R(x, y, u, u_x, u_y, u_xx, u_yy) = 0` (no solving for a highest derivative is needed, so
nonlinear equations are fine), and turns each of the four sides into a value `g(coordinate along the side)` or a normal-slope function. Because a value side removes its whole line of nodes (corners included), the unknowns always form a rectangle, so the Jacobian is
banded with half-bandwidth equal to the row length. Residuals use a padded array with ghost nodes at slope sides; the Jacobian is built by finite differences with five colour groups `(i + 2j) mod 5`; Newton uses a banded LU (reused while the step contracts by half or more), step halving
and a convergence test relative to the largest value of the field. A second solve on half the intervals gives the error estimate; `interpolate2d` is a tensor-product cubic. `engine._pde2d_extras` produces the `heatmap` series (down-sampled to about 60 × 60) and two profile
series; `plot.js` draws the heat map as SVG cells with a colour bar.

Unknown parameters in boundary-value problems (eigenvalues, fitted constants): `unknowns` names free variables; they stay out of `inputs` (so the engine does not ask for them) and each gets an `Equation` `p = BVPparam_k(inputs…)` on a function node whose value is
`BvpSolution.theta[k]`. `bvp.solve` appends them to the Newton unknowns; the segment integration carries a third block of sensitivities `P' = (∂f/∂y) P + ∂f/∂θ` (symbolic, lambdified) and the conditions contribute `∂r/∂θ`. Parameters are scaled by
their starting guess (an energy of 1e-21 J would otherwise dominate the tolerances), the linear system is row- and column-equilibrated before the pivot test for uniqueness, and a Newton step that no longer changes anything counts as converged when the residual
sits at the integration-error floor (which a decaying solution amplifies). A guess containing the independent variable becomes a profile: the nodes start at the profile (derivative states by symbolic differentiation) instead of by forward integration of a starting
vector, which blows up for growing solutions. The engine no longer tries to "invert" a numerical ODE node that merely failed to evaluate.

Axes and centres (`r = 0`): a right-hand side that cannot be evaluated at the start of the interval (`_singular_at`: division by zero, nan) is treated as a coordinate singularity. IVPs start from a series (`OdeSystem._series_start`: for each second-order quantity
y = y0 + a d²/2, y' = a d with the curvature a found by a secant iteration on the equation itself, d = 1e-6 of the span); BVPs begin 1e-7 of the interval inside, the start-point conditions moved with it and the axis point labelled correctly in the output; the 1-D PDE evaluates the centre node at
x = 1e-9 L with u_x = u_xx x (the Taylor limit of a zero-slope centre), as does the 2-D steady solver for its axis column. The closed-form BVP route (`_try_closed_form_bvp`) removes constants whose terms are infinite at the singular position and drops the conditions that become identities (the symmetry condition is the regularity condition).

Special functions (`core/special.py`): the SymPy functions are whitelisted by name (`model._FUNCS`); `besselj_zero` and the `eig_*` Heisler roots are SymPy `Function` subclasses whose `_eval_evalf` calls cached SciPy routines (`jn_zeros`; `brentq` on bracketed intervals known from the zeros of J₀ and J₁ or from the branches of tan and cot). Every fast evaluation path (`fast_lambdify`: ODE and PDE right-hand sides,
Jacobians, tearing and Newton, sums) lambdifies to plain Python floats with a SciPy namespace for these functions (`jv`, `yv`, `iv`, `kv`, `ellipk`, `lambertw`, …) instead of the `math` module alone.

## Physics and chemistry (`library/physics*.py`, `library/chemistry*.py`)
Two disciplines for the sciences, added to the taxonomy like `architectural` (requested separately from `docs/reference/disciplines.txt`, so the
reference-file test excludes them). New calculations are written once and listed under every discipline they serve (a blackbody calculation is physics, mechanical
and energy; Henderson–Hasselbalch is chemistry and biomedical). Existing engineering calculations that are also textbook physics/chemistry (projectile range,
Arrhenius, Beer–Lambert, escape velocity ...) are **cross-listed by sub-discipline** through `RETROFIT` instead of being duplicated. Constants (`NA`, `m_e`, the Rydberg
and Wien constants ...) live in `library/_common.py`. Each calculation is checked three ways: the library invariants (dimension check on load, a clean worked
example, unit-choice independence), `tests/test_physics_chemistry.py` (every result recomputed from the textbook formula in plain Python, plus physical identities such
as the virial theorem, Ampère's definition of the ampere and the Wien constant from Planck's law), and the discipline coverage test. Conventions worth knowing: a variable's
`default` only seeds the form, so the worked example must give every input; quantities such as pH use a standard concentration `c0 = 1 mol/L` so logarithms and equilibrium
constants stay dimensionless; and when a result cannot be computed (total internal reflection, v > c) the engine now adds the violated *validity* message as an info
diagnostic (`hint_validity` in `core/engine.py`), so the user sees the physics rather than only "no real-valued result".

The core set (stage 2) is split across `physics_core_a/b/c.py` and `chemistry_core_a/b.py`, built with the `phys()` / `chem()` helpers and shared reference strings in `library/_pc.py`; their tests are `tests/test_pc_a.py` ... `test_pc_e.py`, each recomputing the example in SI with independent constants (`tests/pcutil.py`) and asserting that every output has such a check. Sub-disciplines were extended (fluids, atomic, solid-state, nuclear; chemical thermodynamics, kinetics, electrochemistry, solid-state/inorganic, organic), and every sub-discipline must hold at least one calculation.

Stage 3 (the broad set) adds `physics_broad_a/b.py` (quantum and statistical mechanics; analytical mechanics, plasma, particle physics, astrophysics) and `chemistry_broad_a/b.py` (quantum chemistry, photochemistry, polymers; colloids, biochemistry, atmosphere, organic/inorganic extras), tested by `tests/test_pc_f.py` ... `test_pc_i.py`, and cross-lists about 40 existing calculations under the new sub-disciplines in `library/subdisciplines.py`. Two modelling pitfalls found on the way: a variable is a *positive* symbol unless declared `signed=True`, so a condition such as `nu > 0` inside `Piecewise` silently collapses to true at parse time; and the dimension checker cannot take a dimensional quantity to a variable power, so write `(p/p50)^n` rather than `p^n/(p50^n + p^n)`.

Coverage floor: every sub-discipline has at least three calculations (`test_every_subdiscipline_has_at_least_three_calculations`). The thin-sub-discipline modules `library/thin_a.py` ... `thin_d.py` (built with `_thin.mk`) deepened the newer fields; `thin_e.py` is stage 4 of physics and chemistry (organic mechanisms, thermochemistry, transport, electrochemistry, astrophysics, plasma, particle physics). `scripts/check_duplicates.py` (run by `tests/test_duplicates.py`) flags near-duplicate calculations; reviewed sibling pairs are listed in `tests/duplicates_reviewed.txt`. Variable names must avoid sympy's relational classes (`Lt`, `Gt`, `Le`, `Ge`, `Eq`, `Ne`), which the validity parser uses.

## Time limit (`core/timeout.py`, `settings.py`)
One user setting (default 10 s, 1–3600 s, or off) bounds long calculations. `time_limit(seconds)` abandons the work with a `BaseException` (SymPy's own `except Exception` blocks cannot swallow it): a daemon watchdog timer raises it asynchronously in the calculating thread (zero cost while running — the first design, a `sys.setprofile` hook, slowed SymPy about 8×), or, where threads cannot start (Pyodide), a cheap profile hook checks the clock every 256 calls. Limits are per thread, nest (earliest wins) and `None` adds none, so it works under FastAPI's thread pool and inside Pyodide. `api.limited` wraps
every heavy entry point (solve, checks, saves/imports of equations, System Design solve/validate/export) and turns an overrun into a `TIMEOUT` error (HTTP 408); `custom_validate` reports it as an
ordinary problem with the draft; calculus evaluation of user equations uses the same limit, and built-in library code is exempt so a tiny limit can never stop the catalog loading. The guard acts between
Python calls, so one long native operation can overrun it, and nothing is killed — the work is abandoned by an exception. Switching the limit off requires `acknowledge_risk` in the API, a checkbox in
the dialog and a typed `yes` (or `--yes`) on the command line, each showing the same warning text (`settings.DISABLE_WARNING`). Persistence: `settings.json` beside the equations folder for installed
copies (`sliderule settings`), browser storage for the static site (re-applied at start, before user equations are restored).

## User-defined calculations (`core/custom.py`, `core/safeparse.py`, `usercalcs.py`, `web/js/custom.js`)
A user calculation is a JSON document (`docs/CUSTOM_EQUATIONS.md`). `calc_from_dict` validates every field (types, sizes, identifier rules, unit syntax) and builds an
ordinary `Calculation` with `custom=True`, which sends each equation text through `safeparse.check_expression` (an AST whitelist) *before* SymPy's `eval`-based parser sees it, then runs the
same dimensional-homogeneity check as the library. `usercalcs` keeps the documents, registers them in the live `Catalog` (ids are `custom.*`, so the library cannot be overwritten), and persists them one file
per calculation in a folder when `configure(folder)` is called (CLI/server); the in-browser engine has no folder, so the page mirrors the library into local storage (`custom_export`) and restores it on
start (`custom_import`). API: `custom_validate | save | delete | list | export | import | template` (+ `/api/custom*`). Because it is only a catalog entry, everything downstream — solving, steps,
System Design, all four export formats — works unchanged; exports mark such blocks "user-defined". Tests round-trip all 355 library calculations through the file format.

## Testing
Every library example must solve without warnings; each calculation is re-run with inputs re-expressed in SI and must agree;
selected calculations are checked against independent hand calculations (the oilfield 0.00708, 0.052, 7758 and US Manning 1.486 constants emerge from unit conversion alone).

## Adding a calculation
```python
Calculation(
    id="mechanical.heat.convection_cooling", name="Convection heat transfer", disciplines=["mechanical"],
    description="…",
    variables=[V("h", "Heat transfer coefficient", "W/(m^2*K)"), V("A", "Area", "m^2"),
               V("dT", "Temperature difference", "K", latex=r"\Delta T", delta=True), V("Q", "Heat flow", "W")],
    equations=["Q = h*A*dT"], outputs=["Q"], tags=[…], assumptions=[…], references=[…],
    example={"h": "25 W/(m^2*K)", "A": "2 m^2", "dT": "40 K"},
)
```
Append it to `CALCS` in a library module; the test suite covers the rest.

## Known limits / next steps
No account/sync for shared equations (files only), no equation search by symbol across a user's files, no per-equation versioning; logarithmic units (dB), gauge/absolute pressure, coupled implicit solvers (Colebrook-for-velocity), output unit-system presets, packaged desktop installers.
