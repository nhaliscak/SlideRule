# Your own equations

The **My equations** tab (and `sliderule custom …` on the command line) lets you add calculations of your own. They behave like the built-in ones:
solve for any variable, worked symbolic/numeric steps with unit conversions, search and filters, System Design blocks and all export formats. They are
marked **custom** everywhere (and "user-defined" in exported documents) because, unlike the library, nobody has reviewed their physics. SlideRule does
check that every equation is dimensionally consistent when you save, exactly as it does for the library.

## Where they live
| Version | Storage |
|---|---|
| Installed (`sliderule serve`, `sliderule app`, CLI) | one JSON file per equation in `~/.sliderule/calculations/` (`$SLIDERULE_HOME/calculations`, or `--equations-dir`) |
| Browser-only website | this browser's local storage; use **Export** to keep a file and **Import** to load it elsewhere |

Files are plain JSON: copy them, e-mail them, keep them in git. Anything in the folder is loaded at start-up (files that fail validation are skipped with a message).

## From a System Design
In **System Design**, *Save as equation…* turns the system on the canvas into one of your equations: the blocks' equations are combined (wired ports become one shared variable, unwired inputs keep the values you typed, block comments go into the assumptions), you choose its name, description and which quantities it computes by default, and it appears in **My equations** like any other. It can be solved in any direction and used as a block in other systems. A differential equation that has a closed-form solution (a first-order tank or cooling model, a beam or fin profile) is saved as that solution, so it can then be solved backwards too. Systems containing numerically solved differential equations, events or data tables cannot be saved this way yet. The blocks' validity limits are carried over under the saved equation's variable names (any that cannot be are listed in the assumptions).

## Sharing
* **Export file** (one equation) or **Export all** writes `*.sliderule.json`. **Import file…** accepts one or several; if an id already exists with different content you choose
  to replace yours or keep both (the imported copy is renamed `custom.name_2`).
* A System Design saved with **Save** embeds the custom equations it uses (`custom_calculations`). Loading that file adds the ones you do not have; if you already have one with the same
  id, yours is kept and you are told.
* Command line: `sliderule custom import FILE…`, `validate FILE…` (dry run), `export [ID…] [-o FILE]`, `list`, `remove ID`, `path`.

## File format
```json
{
  "format": "sliderule-calculation", "version": 1,
  "calculation": {
    "id": "custom.spring_force", "name": "Spring force", "description": "Hooke's law for a linear spring",
    "author": "A. Engineer", "disciplines": ["mechanical"], "subdisciplines": [],
    "variables": [
      {"key": "F", "label": "Force",     "unit": "N"},
      {"key": "k", "label": "Stiffness", "unit": "N/m", "example": "2 kN/m"},
      {"key": "x", "label": "Extension", "unit": "m",   "example": "5 cm"}
    ],
    "equations": [{"title": "Hooke's law", "text": "F = k*x"}],
    "outputs": ["F"],
    "assumptions": ["Linear elastic range"], "references": [],
    "validity": [{"condition": "x > 0", "message": "Extension should be positive"}]
  }
}
```
A bundle is `{"format": "sliderule-calculations", "version": 1, "calculations": [ … ]}`. Variables also accept `latex`, `default`, `min`, `max`, `signed`, `delta`
(temperature difference), `note`, `units` (restrict the unit picker), `constant` (a fixed value in the variable's unit) `shape` (a vector or matrix, see below) and, at the calculation level, `tables`.

Rules enforced on save and on import:
* `id` is `custom.` + lower-case letters, digits, `_`; a custom id can never replace a library calculation.
* Each variable needs a symbol (letter first, ≤ 24 characters), a name and a unit SlideRule can parse (blank means dimensionless). Every variable must appear in an equation.
* Each equation has exactly one `=`; both sides are dimensionally consistent; at least one output.
* At least one discipline (a sub-discipline adds its discipline automatically). Limits: 40 variables, 12 equations, 300 characters per expression.

## Equation syntax and safety
Write ordinary maths (and see calculus below): `+ - * / ^` (or `**`), parentheses, comparisons in validity checks, and the functions `sqrt exp log ln log10 log2 sin cos tan asin acos atan atan2 sinh cosh
tanh Abs Min Max Piecewise erf floor ceiling factorial` and the constant `pi` (a variable named like a function shadows it, as in the library).

### Solving for anything: numerical inversion
Whenever a quantity cannot be isolated by rearranging — a numerically solved differential equation or event, an integral with no closed form, or an implicit relation such as the Colebrook friction-factor equation
`1/sqrt(f) = -2*log10(eps/(3.7*D) + 2.51/(Re*sqrt(f)))` — SlideRule finds it by **root-finding**: it brackets a sign change of `lhs − rhs` and refines it with Brent's method, evaluating the equation (and, for a differential equation, solving it)
at each trial value. It also takes over when a closed form exists but cannot be evaluated (a square root of a negative number, complex intermediates in a cubic).
* **Automatic search** scans magnitudes from 1e-9 to 1e9 (in SI; a variable's declared minimum/maximum narrows it; signed variables are scanned in both directions) and uses the *first* sign change found, preferring small magnitudes.
  A note says so; if the equation has several roots and you want another one, give a **search range** (under each unknown quantity in the app: "search range"; `search` in the API; `--search KEY=LO:HI` on the command line; numbers
  or quantities with units, e.g. `["0.001 1/s", "1 1/s"]`).
* If nothing is found you are told why (no sign change in the range) and asked for a range; a sign change that is only a pole or jump is detected (the residual at the "root" must be small) and refused.
* Accuracy follows the numerical solution it inverts (about 1e-7 for differential equations); every evaluation counts towards the time limit. The steps show the equation, the bracket, the number of evaluations and the residual.
* A chain works too: a value needed for the target can itself be found numerically first. In System Design, a block's output role may be any quantity that can be found this way.

### Simultaneous (coupled) equations
Equations that share several unknowns are solved together; you write them like any others (the Colebrook friction factor and the Darcy–Weisbach equation for the velocity of a given head loss, node-voltage equations, a junction in a pipe network, two heat balances with two unknown temperatures).
The engine orders the equations so that each has one unknown where it can; whatever remains forms *blocks* of n equations in n unknowns, and a block is solved when your chosen outputs need it.
* **Linear in the unknowns:** solved exactly and symbolically (up to 4 unknowns; the steps show each unknown as a formula in the given quantities), larger systems numerically. A singular system (dependent or contradictory equations) is reported with that explanation.
* **Nonlinear:** first by *tearing*: one unknown is treated as known so that the other equations can be solved one after another, which leaves one equation in that unknown; its roots are found by scanning the allowed range for sign changes and refining each with Brent's method (so every solution in the range is found, and roots that put another unknown outside its range are dropped). If no unknown can be torn this way, Newton's method with an exact Jacobian, damped, from many starting points, with each unknown kept in its physical range (positive unless the variable is signed, within its min/max). Up to 12 coupled equations.
* **More than one solution:** a note lists the ones found; the first is used. Give a **search range** for an unknown to choose (as for numerical inversion).
* **No solution found:** you are told, and asked to check the equations or give search ranges. A block with fewer equations than unknowns cannot be solved (missing inputs are named).
* Works in every direction: tick any variables as the unknowns, as long as the number of unknowns matches the number of independent equations. Coupled blocks also work in System Design and in the exports (the Python script re-solves them with SymPy).

### Gauge pressure and decibels

* Gauge pressure units `psig`, `barg`, `kPag`, `MPag` and `Pag` are offset units like °C: the value is the pressure above one standard atmosphere (101.325 kPa), converted on the way in and out. Give a variable's input or output in `psig` and the equations see absolute pressure. A pressure *difference* (or a gradient such as `psig/ft`) carries no offset. If the local barometer is not standard, work in absolute units.
* Decibels are logarithmic levels, not linear units, so they are never converted to anything else. Write the definition in the equation (`L = 10*log10(P/P0)`, with a reference constant `P0`); gains and losses then add as plain numbers, and the level or the linear quantity can be the unknown (`log10` and `log2` are rearranged exactly).

### Your own functions and products

A calculation may define up to eight functions (`functions` in the file, a *Your own functions* panel in the editor): `{"name": "fsj", "args": ["Re", "rel"], "body": "0.25/log10(rel/3.7 + 5.74/Re**0.9)**2"}` and then `f = fsj(Re1, eps/D1)` in as many equations as needed. A function is written out where it is called (its arguments substituted into the body), so every call is dimension-checked, any variable can still be solved for, and exported systems show the expanded equations. A body may use its arguments, the calculation's variables and constants, the built-in functions and earlier functions (no recursion), but no derivatives, integrals or sums.

`product(term, (i, 1, 6))` multiplies the term over a range of whole numbers (up to 50 factors), as `summation` adds.

An unknown that is the root of a polynomial of degree 3 or more (it has several roots) is found numerically within its allowed range rather than taking the first root the algebra returns.

### Infinite series

`summation(term, (n, 1, oo))` sums a series to convergence and says so when it cannot: the terms are added directly (up to 20 000); a series whose terms have vanished by then is done. A slowly or conditionally convergent one (`1/n²`, `(-1)ⁿ/n`, `sin(n)/n`) is accelerated by three independent methods and accepted only where two agree and the answer is consistent with the partial sums, so the harmonic series is refused rather than "summed" to a plausible number, and so are series whose terms do not die away (`2**n`, `n`). Anything the series depends on can be solved for (the unknown inside it is found by root-finding): the plate with a fixed surface temperature, the M/M/1 queue.

* An infinite series is a numerical result: it is not part of a coupled (simultaneous) system, and its closed form is not derived.
* Only the last index may be infinite and the first must be a whole-number literal; a sum nested inside an infinite sum is not supported.

### Tabulated data

A calculation may carry up to six data tables, which equations use as ordinary functions: `H = pump(Q)`. In the file:

```json
"tables": [{"name": "pump", "x_unit": "L/s", "y_unit": "m", "method": "pchip", "outside": "error",
            "x": [0, 10, 20, 30, 40, 50], "y": [52, 50, 45, 36, 22, 4]}]
```

* `x` must increase strictly (2 to 500 points); the units may be offset units such as `degC`. The function's argument must have the dimension of `x_unit` and its value has that of `y_unit`, both checked.
* `method`: `linear` (straight lines), `pchip` (smooth monotone cubic: never overshoots the data) or `loglog` (straight on log-log axes, for power-law data such as S-N curves; positive values only).
* `outside`: `error` (default: asked outside the tabulated range, there is no answer), `clamp` (hold the end value) or `extrapolate` (continue the end segment).
* The function is differentiable (Newton iterations and coupled systems work) and cannot be rearranged, so an unknown inside it, or an operating point where the table meets another curve, is found numerically (bracketed roots, then Newton for coupled systems). The editor has a *Data tables* panel for pasting points. Exported scripts embed the data.
* One-dimensional tables only; a two-way table is written as several one-dimensional ones.

### Vectors and matrices

Give a variable a `shape`, `[3]` for a vector of three components or `[2, 2]` for a 2×2 matrix (1 to 6 per dimension), and it becomes component variables `F_1, F_2, F_3` (matrices: `K_1_1, K_1_2, …`) that all share its unit and options. In equations the name stands for the whole vector or matrix, and the components stay available by name:

```
M = cross(r, F)           # moment of a force            W = dot(F, d)       # work
K*u = f                   # stiffness matrix times displacements, solved as a coupled linear system
R = F1 + F2               # component-wise sum           Rmag = norm(R)      # length of a vector
```

* `dot`, `cross` (3-vectors), `norm`, `det`, `transpose`, `inv`, `trace`, `+`, `-`, `*` (scalar, matrix–vector, matrix–matrix) work on them. A vector or matrix equation is split into one scalar equation per component, each dimension-checked, and then solved like any other, so a component, a whole vector or a matrix entry can be the unknown (a singular or under-determined system is reported).
* In the file, `example` of a vector is the list of its component values in row order. An output may name the whole vector.
* Limits: one unit per vector or matrix (mixed-unit matrices are written as separate variables); at most 6 × 6; vectors are not available in differential equations.

### Complex numbers

`j` is the imaginary unit (a variable called `j` wins, as for any name). Variables stay real: a phasor is carried as a magnitude and an angle (or as real and imaginary parts), and an equation that contains `j` is a *complex equation*, which is split into two real ones: equal real parts and equal imaginary parts. The pair is solved together by the simultaneous-equation machinery, so any of the real quantities can be the unknown.

```
Z*exp(j*th) = R + j*(2*pi*f*L - 1/(2*pi*f*C))      # Z = |Z|, th = phase
Vout*exp(j*ph) = Vin*(-j/(2*pi*f*C))/(R - j/(2*pi*f*C))
P + j*Q = Vrms*Irms*exp(j*phi)
```

* `Abs(z)`, `arg(z)`, `Re(z)`, `Im(z)` and `conjugate(z)` work inside equations; `Abs` and `arg` give a real result, so they need no splitting.
* Dimensions: `j` is dimensionless, so a real and an imaginary term in one sum must have the same dimension (resistance and reactance, say); `arg` and `atan2` need both arguments in one dimension.
* An angle has many solutions (θ and θ + 2π). Give the angle variable bounds (`min`/`max`, such as ±π) so the answer is unique.
* An equation whose imaginary (or real) part is trivially true loses that half; if both halves are trivial it is rejected.
* Complex numbers are not supported inside differential equations or integrals.

### Special functions
Besides the usual functions (`sqrt`, `exp`, `log`, trig, `erf`, `gamma`, …) equations may use:
* **Bessel functions** `besselj(n, x)`, `bessely(n, x)`, `besseli(n, x)`, `besselk(n, x)` (orders may be fractional); **Airy** `airyai(x)`, `airybi(x)`; **Legendre** `legendre(n, x)`; **elliptic integrals** `elliptic_k(m)`, `elliptic_e(m)`, `elliptic_f(phi, m)` (parameter `m = k²`); `expint(n, x)`, `Ei(x)`, `erfc`, `erfi`, `loggamma`, `sinc(x)`, and the **Lambert W function** `LambertW(x)` (solutions of `x·exp(x) = a`, and many delay and diode/transistor equations).
* **Zeros and eigenvalues for series solutions:** `besselj_zero(n, k)` is the k-th positive zero of Jₙ (drum and cylinder modes); `eig_slab(Bi, k)`, `eig_cylinder(Bi, k)`, `eig_sphere(Bi, k)` are the k-th positive roots of the transient-conduction conditions ζ tan ζ = Bi, ζ J₁(ζ) = Bi J₀(ζ), 1 − ζ cot ζ = Bi (Heisler series). Use them inside `summation(…, (n, 1, 40))`.
The arguments of all of these must be dimensionless (checked), SymPy differentiates them (so they work in exact Jacobians and in closed-form differential-equation solutions: the annular fin in `besseli`/`besselk` comes out symbolically), and the numerical engines evaluate them with SciPy. Orders of zeros and eigenvalue numbers must be whole numbers (k up to 200).

### Cylindrical and spherical coordinates
Write the radial equation as it appears in the textbook: `k*(diff(T, r, 2) + diff(T, r)/r) + q = 0` (cylinder) or `... + 2*diff(T, r)/r` (sphere), and in 2-D `diff(T, r, 2) + diff(T, r)/r + diff(T, z, 2)` for an axisymmetric cylinder. The axis or centre `r = 0` is a singular point of those
equations (`T'/r` is 0/0) and is handled for you wherever it is the start of the interval, with the symmetry condition `diff(T, r) = 0` there:
* **Boundary-value problems:** the solution starts a hair inside the axis (1e-7 of the interval), which changes the answer by far less than the solver tolerance. SymPy's closed form is found as well: the terms that are infinite at the axis (`log(r)`, `1/r`) are removed by the symmetry condition, so a solution such as `T = T∞ + q R/(2h) + q (R² − r²)/(4k)` comes out symbolically and any quantity can be solved for.
* **Initial-value problems (Lane–Emden `y'' + 2y'/x + yⁿ = 0`):** the integration starts from the series at the centre, with the curvature found from the equation itself.
* **Time-dependent 1-D problems and steady axisymmetric 2-D problems:** the centre node is evaluated in the limit `u_x/x → u_xx`.
You may ask for the answer at `r = 0` itself.

### Sums and series
`summation(term, (n, first, last))` adds the term for each whole number from `first` to `last` (literals, at most 500 terms; `oo` as the last index is an infinite series, see below): `T = Ts + (Ti - Ts)*summation(4/((2*k - 1)*pi)*sin((2*k - 1)*pi*x/L)*exp(-(2*k - 1)**2*pi**2*a*t/L**2), (k, 1, 80))`
is the Fourier-series solution of transient slab conduction. The index is a dimensionless whole number, so everything in the term is dimension-checked as written (the argument of `exp` must be dimensionless). A sum is shown as a sum, never expanded, and is
added term by term with floating-point arithmetic, switching to arbitrary precision when a term overflows. Quantities outside the sum can be rearranged for as usual; one inside it (the time at which the slab reaches a temperature) is found by [numerical root-finding](#solving-for-anything-numerical-inversion). Derivatives and integrals inside a sum are not supported. Summing a slowly convergent series (the corners of the Laplace solution) needs more terms than you may expect, so check the result against a larger number of terms.

### Differential equations
Add initial-value problems in the **Differential equations** section of the editor, or as `odes` in the file:

```json
"odes": [{
  "title": "Newton cooling", "independent": "t", "start": "0", "method": "auto",
  "equations": ["diff(T, t) = -k*(T - Ta)"],
  "initial": ["T = T0"]
}]
```
* `diff(T, t)` is the derivative of the variable `T` with respect to the variable `t`; `diff(x, t, 2)` is a second derivative (up to 6th order; up to 12 equations and 24 state variables per system). The quantity `T` then means **its value at the time `t`** you supply, so it is
  an output and `t` is an input. Write one equation per differentiated quantity (a system), in any form that can be solved for the highest derivative (`m*diff(x, t, 2) + c*diff(x, t) + k*x = 0` is fine).
* `initial` gives, for each quantity, its value (`T = T0`) and the values of its lower derivatives (`diff(x, t) = v0`) at `start` (a number or a variable, default 0). They may be variables, expressions or numbers (a literal 0 is valid in any unit).
* `method`: `auto` tries SymPy's `dsolve` and falls back to numerical integration; `numeric` always integrates; `symbolic` requires a closed form.
* **Closed form found** (linear and many separable equations): it becomes an ordinary algebraic equation, so you can solve for the time to reach a value, the rate constant, an initial value… and the steps show the equation, the conditions and the solution.
* **No closed form**: integrated numerically by built-in integrators — adaptive Dormand–Prince RK45, switching automatically to an implicit method if the problem is stiff — at relative tolerance 1e-8. Evaluating forward (parameters, initial values and `t` → the state) is direct; any other quantity (a rate constant, `t`, an initial value…) is found by [numerical root-finding](#solving-for-anything-numerical-inversion).
* The result page plots each quantity from the start to `t`, offers a CSV download, and can tabulate the solution at extra times you list. Everything is dimension-checked (`[d^n y/dt^n] = [y]/[t]^n`, initial values must carry the right units).
* **Integrals inside a differential equation** are allowed in three forms: an integral that does not involve the unknowns or `t` (a number, evaluated once; numerically if it has no closed form); `integrate(f, (s, start, t))` of a known function (substituted in closed form when SymPy can); and `integrate(g(y), (s, start, t))` of the unknowns themselves, for example an integral controller (`diff(y, t) = -k*y - ki*integrate(y, (s, 0, t))`), which becomes a hidden extra state `z' = g, z(start) = 0`. A **sliding window** `integrate(g(y), (s, t - a, t - b))` with constant `a` and `b` (a moving average, a distributed delay) is the hidden integral state `z` written `z(t - b) − z(t − a)`, solved as a delay system; the integrand counts as zero before the start. Other variable limits and nested integrals are refused. A closed form can be singular at special values (critical damping gives 0/0): SymPy's result is then replaced automatically by a numerical solution, with a note.
* **Events** stop or mark the integration where a condition crosses zero:

  ```json
  "events": [{"title": "ground", "when": "h = 0", "direction": "falling", "terminal": true, "time": "tf", "values": {"vy": "vi"}}]
  ```
  `when` is an expression (or `lhs = rhs`) in the quantities, their derivatives and parameters; `direction` is `either`, `rising` or `falling`; `terminal` stops the run at the first crossing. `time` names a free variable of the calculation that
  receives the **event time**, and `values` maps quantities to variables that receive their **state at the event** (so “time to hit the ground”, “range at impact” and “time to drain to a level” are ordinary outputs). The crossing is located
  precisely between steps (interpolation, then refinement against the real integration), so the time is accurate to the solver tolerance. The time you enter for `t` is the *longest time to simulate*: if a terminal event occurs earlier the
  quantities are reported there, and a crossing that never happens within `t` is an explicit error. An event that is already true at the start is not an event. Events always use the numerical solver; asking for something other than the event outputs (for example the launch speed that gives a chosen flight time) uses numerical root-finding; up to 3 per system.
  **Impulsive events** make the state jump and carry on: add `"reset": {"diff(h, t)": "-e*diff(h, t)"}` (state → its new value, an expression of the state just before the event, `t` and the parameters; dimension-checked) instead of `terminal`.
  A bouncing ball, an impact oscillator, a relay thermostat (a discrete mode carried as a state with `diff(u, t) = 0`, switched by two events: `{"u": "1"}` and `{"u": "0"}`) and repeated dosing are written this way. The run restarts from the new state after each jump
  (the plot shows the jump as a vertical step); more than 500 jumps are reported as Zeno behaviour (a ball bouncing ever lower toward a finite accumulation time). Choose `direction` so the jump does not re-trigger itself. `diff(u, t) = 0` (a literal zero rate) is valid in any unit.
  In a boundary-value problem an event marks the first position along the solved interval where the condition crosses zero (a maximum deflection where the slope vanishes, a station where a stress reaches a limit); `time` receives that position and `values` the state there. Such an event cannot stop the run or make the state jump.
  Not supported: events defined by integrals.
* **Algebraic constraints (DAEs):** an equation without a derivative that fixes a variable at every instant is listed with `"algebraic": ["i"]` and written among the `equations` (`"C*diff(Vc, t) = i"`, `"i*R = Vs - Vc"`). The constraints are solved symbolically
  together with the differential equations and eliminated, so the system is integrated numerically in the remaining states; the algebraic variable is internal (its value is a function of the states: compute it in an ordinary equation if you need it). A constraint with several solutions (a square root) or one that cannot be solved symbolically is refused.
* **Delays:** `delay(y, tau)` in an equation is the value of the unknown `y` a time `tau` earlier (`"diff(y, t) = -a*delay(y, tau)"`; `tau` is a constant: an expression of the parameters, with the dimension of `t`). Before the start the unknown keeps its initial value (constant history). A delay equation is integrated numerically by the method of steps
  (Dormand–Prince with a Hermite-interpolated history; the step never exceeds the shortest delay and the run stops at `start + k·tau` where the solution's smoothness changes). Several delays, delays in systems and the dependence on the initial value work; delays together with events, in boundary-value problems or on derivative states are not supported, and a state-dependent delay is not either.
* **Fractional derivatives:** `fdiff(y, t, alpha)` is the Caputo derivative of order `alpha` (a number, 0 < alpha ≤ 3; it may be written `0.6` or `3/5`) of `y` with respect to `t`, alone or in a system, possibly with ordinary `diff(y, t)` terms for other unknowns (`"fdiff(y, t, 0.6) = -k*y"`, initial value `y = y0`). The derivative has memory: it depends on the whole history since the start through a power-law kernel, which is how viscoelastic creep, anomalous diffusion and fractional dampers are modelled
  (`D^α y = −k y` gives the Mittag-Leffler function `y0·E_α(−k t^α)`, a power-law tail instead of an exponential). Dimensions: `[D^α y] = [y]/[t]^α`. The Adams–Bashforth–Moulton predictor-corrector sums the whole history at every step (O(N²) work; `nodes` steps, default 800, 50 to 8000); the solution is not smooth at the start (it behaves like `t^α`), so the order of convergence is only about 1 + α and the run is repeated with half the steps for an error estimate.
  **Orders above 1** need one initial value per integer below the order (`ceil(alpha)` in all): order 1.5 takes `y = y0` and `diff(y, t) = v0`, order 2.5 also `diff(y, t, 2) = a0` (`"initial": ["y = y0", "diff(y, t) = v0"]`). Orders between 1 and 2 give oscillation with power-law damping (`D^1.5 y = −k y` has the solution `E_1.5(−k t^1.5)` when `y'(0) = 0`); order 2 is the ordinary oscillator. Each unknown has a single order (no mixed-order Bagley–Torvik terms). Boundary conditions, events and the Python-script export are not supported for fractional equations.
* **Stochastic differential equations:** white-noise terms `xi1`, `xi2`, `xi3` (independent, unit-intensity, Itô; `xi` has the dimension `time^-1/2`, so a noise coefficient has the dimension `[x]/[time]^(1/2)`) make the solution a random variable. Say what to report:

  ```json
  "odes": [{"title": "Ornstein-Uhlenbeck", "independent": "t", "start": "0", "equations": ["diff(x, t) = -theta*(x - mu) + sigma*xi1"], "initial": ["x = x0"],
            "statistics": [{"of": "x", "kind": "mean", "var": "xm"}, {"of": "x", "kind": "std", "var": "xs"},
                           {"of": "x", "kind": "above", "level": "xc", "var": "pexc"}, {"of": "x", "kind": "quantile", "p": "0.95", "var": "x95"}],
            "paths": 20000, "steps": 400, "seed": 12345}]
  ```
  `kind` is `mean`, `std`, `above` / `below` (probability of exceeding / staying under `level`) or `quantile` (`p` between 0 and 1); each value goes to the variable named in `var` (an ordinary output you can also use in other equations). The noise coefficient may depend on the state and time (`sg*S*xi1` is geometric Brownian motion). Euler–Maruyama on `paths` independent paths with a **fixed seed**, so identical inputs give identical numbers; the **sampling error** of each statistic and its **time-discretisation difference** (the same Brownian paths with half the steps) are printed in the diagnostics. The plots show the mean, ±1 standard deviation and five sample paths.
  Statistics cannot be solved for in reverse by rearranging (the engine would need to re-run the simulation for every trial value, and sampling noise makes root-finding on it unreliable): use them in the forward direction. Not supported: boundary conditions, noise inside other equation types.
  **Events on the paths:** `"events": [{"title": "failure", "when": "T = Tlim", "direction": "rising", "terminal": true}]` watches a condition on every path. A **terminal** event absorbs the path where the condition crosses zero (first-passage and barrier problems); `"reset": {"x": "x0"}` instead makes the state jump (renewal, restart); an event with neither is just counted. Crossings between two time steps are detected with the Brownian-bridge probability `exp(−2·g₀·g₁/(σ_g²·dt))`, which removes most of the low bias of checking only at the steps. Event statistics: `{"event": "failure", "kind": "hit_probability", "var": "pf"}` (the fraction of paths that reached it by the evaluation time), `hit_time_mean`, `hit_time_std`, `hit_time_quantile` (with `"p"`) among the paths that did, and `hit_count_mean` (occurrences per path); `event` is the title or its number from 1. An ordinary statistic of an absorbed path uses the state where it was stopped. Hit times are the value of the independent variable; they are interpolated within the step. At most 3 events.
* **Boundary-value problems** (conditions at positions of an interval: beams, fins, channel profiles) use `end` and `boundary` instead of `initial`:

  ```json
  "odes": [{"title": "Fin", "independent": "x", "start": "0", "end": "L",
            "equations": ["diff(T, x, 2) = m**2*(T - Ti)"],
            "boundary": ["start: T = Tb", "end: -k*diff(T, x) = h*(T - Ti)"],
            "guess": ["T = Tb"]}]
  ```
  Each condition is `where: condition`; `where` is `start`, `end` or any expression (a position inside the interval is fine); the condition is any equation in the quantities, their derivatives and parameters, so a value (`y = 0`), a slope
  (`diff(y, x) = 0`) and a Robin condition (`-k*diff(T, x) = h*(T - Ti)`) are all the same thing. There must be exactly one condition per order of the equations (a 4th-order beam needs four). The independent variable (`x`) is then **the position you want
  the answer at**, an input between `start` and `end`; the plot covers the whole interval. SymPy's `dsolve` is tried first (the integration constants are fitted to the conditions), so a closed form can still be solved for any quantity
  (the load that gives a chosen deflection, the position where…); otherwise it is solved numerically by **multiple shooting**: the interval is cut into segments (at every position a condition mentions), each integrated with RK45 together with its
  sensitivities, and Newton's method makes the pieces join up and satisfy the conditions. A linear problem needs one Newton step; for a nonlinear one the optional `guess` (`y = value`, `diff(y, x) = value`) selects among several solutions, since Newton finds the one nearest the guess. A problem with no unique solution
  (for example `y'' = −y` with `y = 0` at both ends of a half period) is reported as such. Events are not supported in a boundary-value problem.
* **Free boundaries:** if `end` is itself one of the `unknowns` (`"end": "L", "unknowns": ["L"]`), the length of the interval is found along with the solution (the problem is solved on a scaled interval `0 ≤ s ≤ 1` with `x = start + (L − start) s`). Give one extra condition for it (the column buckles when `w = 0` again; the body has fallen `H` when `z = H`) and a starting guess for `L`
  (`"guess": ["L = L0"]` with `L0` a variable); the iteration lands on the solution nearest to the guess. Conditions may be placed only at `start` and `end`; positions you ask for must lie within the interval that was found.
* **Unknown parameters in a boundary-value problem: eigenvalues and fitted constants.** List variables in `unknowns`; they are found together with the solution and become outputs of the calculation (add them to `outputs`). Each unknown needs one extra
  condition on top of the one-per-order rule, and a starting guess in `guess`. Examples:

  ```json
  "odes": [{"title": "Column buckling", "independent": "x", "start": "0", "end": "L",
            "equations": ["E*I*diff(y, x, 2) + P*y = 0"], "unknowns": ["P"],
            "boundary": ["start: y = 0", "end: y = 0", "L/2: y = a"],
            "guess": ["P = 1.3*pi**2*E*I/L**2", "y = a*sin(pi*x/L)"]}]
  ```
  An **eigenvalue problem** has non-trivial solutions only for special values of a parameter (buckling load, natural frequency, energy). The mode shape can be scaled freely, so the extra condition is a **normalisation** (`L/2: y = a`); the solution is then
  the eigenvalue together with the mode shape normalised that way. **Fitting** a constant works the same way with a physical extra condition: the horizontal tension `H` of a cable is the number that makes the cable, whose arc length is the integral of
  `sqrt(1 + y'^2)` (written as a second equation `diff(s, x) = sqrt(1 + diff(y, x)**2)`), reach the stated length (`end: s = S`). Newton's method finds the solution *nearest the guess*, which is how a mode is chosen (guess a load or frequency near the one you want), so the
  guess matters: give the parameter a value of the right order of magnitude and, for eigenproblems, a rough shape. A guess that depends on the independent variable (`y = a*sin(pi*x/L)`) is a starting *shape* (its derivatives are filled in from it); a constant
  value (`diff(y, x) = 1`) is a starting value at the start of the interval that is integrated forward. Stiff eigenproblems (for example a Schrödinger equation with a deep well, or high modes) can fail to converge from a poor guess; the problem is reported, not silently wrong. Unknown parameters are
  found numerically only (no closed form), and accurate to about 1e-7 relative.
* **Partial differential equations in one space dimension and time** (heat/diffusion, waves, advection–diffusion) are an entry with a `time` variable besides the space variable:

  ```json
  "odes": [{"title": "Slab", "independent": "x", "start": "0", "end": "L", "time": "t",
            "equations": ["diff(T, t) = a*diff(T, x, 2)"],
            "boundary": ["start: T = Ts", "end: -k*diff(T, x) = h*(T - Ti)"],
            "initial": ["T = Ti + (Ts - Ti)*x/L"], "nodes": 100}]
  ```
  The quantity `T` then means **its value at the position `x` and time `t`** you enter (both inputs). The equation must be solvable for the highest time derivative (first order: diffusion-like; second order: wave-like, which then also needs
  `diff(T, t) = …` in `initial`); it may contain `diff(T, x)`, `diff(T, x, 2)` (also nested, as in the conservative form `diff((1 + T**2)*diff(T, x), x)`), `x`, `t`, parameters and, for second order, `diff(T, t)` (damping). Exactly one
  `start:` and one `end:` condition: a value (`T = Ts`, which may depend on `t`) or anything involving the slope (`diff(T, x) = 0`, `-k*diff(T, x) = h*(T - Ti)`). The initial state may depend on `x`. Everything is dimension-checked.
  Numerics: second-order finite differences on `nodes` intervals (default 100, 10 to 400) and then the method of lines: a banded implicit solver for first-order equations and explicit RK45 for second-order ones. The problem is also solved on half the
  intervals and the difference is reported as an **estimated discretisation error** (a warning appears above 1 %: raise `nodes`). Results between nodes use cubic interpolation; the plots show the profile along `x` at several times and the history at your position,
  and any other quantity (the time to reach a temperature, a diffusivity…) is found by [numerical root-finding](#solving-for-anything-numerical-inversion). Not supported: several coupled unknowns, more than one space dimension, pure first-order-in-space (advection-only) equations,
  mixed derivatives and events. Central differences oscillate when advection dominates (cell Péclet number above 2); sharp initial kinks disperse in wave problems — increase `nodes`. These can take seconds: the time limit applies.
* **Coupled fields, time-dependent problems on a rectangle, periodic domains and point sources** are the same entry with more in it (handled by a vectorised method-of-lines solver that integrates the stiff system with SciPy's BDF method and the stencil's sparsity pattern):

  ```json
  "odes": [{"title": "Reactive slab", "independent": "x", "start": "0", "end": "L", "time": "t",
            "equations": ["diff(A, t) = D*diff(A, x, 2) - k*A", "diff(B, t) = D*diff(B, x, 2) + k*A"],
            "boundary": ["start: A = A0", "end: A = A0", "start: B = 0*A0", "end: B = 0*A0"], "initial": ["A = 0*A0", "B = 0*A0"]}]
  ```
  * **Several fields:** one first-order-in-time equation per field (each solvable for its own `diff(field, t)`; an equation may use every field and its space derivatives), one condition per field on each side, one `initial` per field. Each field is an output; the plots cover every field.
  * **Two space dimensions with time:** add `second`, `second_start`, `second_end` as for steady problems and use the sides `left`, `right`, `bottom`, `top` (`nodes` 8 to 120 per direction, default 40): `"equations": ["diff(T, t) = al*(diff(T, x, 2) + diff(T, y, 2))"]`. The result shows the field at the time you enter as a colour map, profiles through your point and the history at it.
  * **Three space dimensions with time:** add `third`, `third_start`, `third_end` (needs `second`); the sides are `left`, `right`, `bottom`, `top` and `front`, `back` (the ends of the third variable), `nodes` 6 to 40 per direction (default 16), and `"at_third"` positions a point source. The result shows the field on the plane through your z as a colour map, and the history at your (x, y, z). Mixed derivatives are not available in three dimensions.
  * **Mixed derivatives** `diff(u, x, y)` (anisotropic diffusion, cross terms) work in two dimensions when every side is a value condition or periodic.
  * **Periodic domains:** `"periodic": ["x"]` makes every field repeat along `x` (the ends are the same point), so those sides take no conditions: a tracer in a closed loop, a travelling wave.
  * **Point sources:** `"sources": [{"field": "T", "at": "x0", "rate": "P/(rho*c*A)"}]` (and `"at_second"` in two dimensions) adds a concentrated source to the nearest grid node. `rate` has the field's units times length (times length) per time; total content grows by exactly `rate · t`. Values at the source itself depend on the grid.
  * **Axis and centre singularities:** terms such as `diff(T, r)/r` (cylindrical) or `2*diff(T, r)/r` (spherical) are exact at `r = 0` when every field has a slope condition there (`left: diff(T, r) = 0`): that node is evaluated at a tiny radius with `T_r = T_rr·r`. Axisymmetric (r, z) problems on a finite cylinder follow, with the axis as the `left` (or `bottom`) side.
  * **Waves and other second-order-in-time equations** are written as two first-order fields (`diff(u, t) = v`, `diff(v, t) = c**2*diff(u, x, 2)`), which this form handles directly.
  * **Conditions that couple fields at a boundary:** a boundary condition may read the *values* of other fields on that side, for exchange between phases, membranes and surface reactions: `"start: -k*diff(u, x) = h*(v - u)"` (a slope condition for `u` whose driving term is the value of `v` there), `"start: u = v"` (the value of `u` follows `v`), `"left: diff(a, x) = -kr*a*b"`. The field a condition determines is the one whose slope appears, or, for a value, the one written alone on the left side. Only one slope per condition, and two value conditions on one side may not read each other (circular). Continuity of flux between two fields' slopes is not supported.
  * **Moving boundaries (Stefan problems):** `"moving": {"front": "s", "rate": "-k*diff(T, x)/(rho*Lf)"}` lets the end of the interval move: the region is `start … s(t)`, with `s(0)` the `end` expression, and `ds/dt` is the `rate` expression, which may use the fields and their slopes at the front (`diff(T, x)` is the slope there), `x` or `s`, time and parameters. The variable `front` receives the front position at the time you enter (it is a result like the fields); give the end a value or slope condition as usual (`end: T = Tm`). The coordinate is stretched to the moving region, `x = start + ξ (s − start)`, which gives `v_t = F + ξ (s'/L) v_ξ`, and the front is solved with the fields as one more unknown in the stiff integration. One space dimension, no periodic direction or point sources; the run stops with a message if the region vanishes. A solid phase at the melting temperature needs no field of its own (one-phase Stefan problem); start from a short initial region (`end` small) and a profile that matches it, or from the exact similarity solution as the library example does. The plots show each field over the region at your time and the front position against time.
  * **Rectangular cutouts (L-shapes, plates with holes, notched sections):** in two dimensions, `"cutouts": [{"x0": "a/2", "x1": "a", "y0": "b/2", "y1": "b", "boundary": ["left: diff(T, x) = 0", "bottom: T = Ts"]}]` removes up to three rectangles from the region. Each removed rectangle takes a condition for every field on each of its sides that lies *inside* the region (`left`, `right`, `bottom`, `top` of the removed rectangle; sides that coincide with the outer boundary are ignored and the outer conditions apply to the part of the outer side that remains). The same kinds of condition as elsewhere: a value, a slope across the side (the ghost value at the stencil is built from it), a Robin relation, or a slope that reads other fields. The corners are snapped to every second grid line (so the half-resolution error check sees the same shape; the requested corners are reproduced exactly when they fall on those lines, e.g. at the middle of an even number of intervals) and each side must span at least two intervals; cutouts may not overlap. A steady problem is a `second` space variable without `time` and with `cutouts` (residual equations, one per field, Newton's method; `guess` as in three dimensions); a transient one works as usual. Points inside a cutout are refused; the heat map leaves cutouts blank; values within one cell of a cutout face use a smooth continuation inside the cutout for the interpolation. No mixed derivatives, periodic directions or moving boundaries with cutouts. Curved boundaries (a circular hole, a wedge) are not supported: a staircase approximation of a curve is only first-order accurate at best.
  * Not supported: curved (non-rectangular) region boundaries.
* **Conservation laws and shocks** (advection, Burgers' equation, traffic flow, shallow water, gas dynamics): add `"scheme": "conservative"` and write each equation in conservation form, `diff(u, t) + diff(flux, x) = source`:

  ```json
  "odes": [{"title": "Dam break", "independent": "x", "start": "0", "end": "L", "time": "t", "scheme": "conservative", "nodes": 400,
            "equations": ["diff(h, t) + diff(q, x) = 0", "diff(q, t) + diff(q**2/h + g*h**2/2, x) = 0"],
            "boundary": ["start: q = 0*hl*g**0.5", "end: q = 0*hl*g**0.5", "start: diff(h, x) = 0", "end: diff(h, x) = 0"],
            "initial": ["h = Piecewise((hl, x < L/2), (hr, True))", "q = 0*hl*g**0.5"]}]
  ```
  The unknowns are the conserved quantities (one equation each, up to 4). `diff(F, x)` is the divergence of a flux F of the fields (any expression of them, `x`, `t` and parameters); other terms without derivatives are sources, and `diff(u, x, 2)` adds a viscous term. Per field and side: a value (`u = g`: the boundary state; `q = 0` makes a wall reflect), `diff(u, x) = 0` (outflow) or the space variable under `periodic`.
  Finite volumes on `nodes` cells (default 200, 20 to 2000), second-order MUSCL reconstruction with the minmod limiter, the Rusanov flux and SSP Runge–Kutta 3: shocks are captured in about two cells, the total is conserved exactly and no new extrema appear. The speed of the fastest wave comes from the eigenvalues of the flux Jacobian. The half-resolution comparison reports an average (L1) error; the cell values at a shock converge only to first order. Not supported: non-conservative products, more than one space dimension.
  **Dry beds** (shallow water over initially dry ground, a flood front, a dam break onto a dry bed): add `"dry": {"depth": "h", "zero": ["q"], "tol": "1e-6"}`. The depth field is kept non-negative; the fields listed under `zero` (momentum) are set to zero in cells and at interface states where the depth is below `tol` times its largest initial value (default 1e-6); the flux, wave-speed and source formulas are evaluated with the depth floored at that tolerance, so `q**2/h` and friction terms such as `cf*q*Abs(q)/h**2` stay finite; and the time step uses a quarter-cell Courant number so the fluxes cannot make the depth negative. Mass is conserved except for the clipping of round-off negatives. Friction-dominated flows over thin films are stiff for an explicit scheme: raise `tol` (1e-3 is usually enough) to treat thin films as dry. The wet front is first-order accurate (its tip lags the exact position by a few cells); Ritter's solution is the reference in the tests. Bed slopes need a well-balanced source treatment that is not provided: use a flat bed.
* **Steady problems on a rectangle** (Laplace, Poisson, conduction with generation, nonlinear variants) have a second space variable and no time:

  ```json
  "odes": [{"title": "Plate", "independent": "x", "start": "0", "end": "a", "second": "y", "second_start": "0", "second_end": "b",
            "equations": ["k*(diff(T, x, 2) + diff(T, y, 2)) + q = 0"],
            "boundary": ["left: T = T0", "right: diff(T, x) = 0", "bottom: T = T0", "top: -k*diff(T, y) = h*(T - Tinf)"],
            "guess": ["T = 300 K"], "nodes": 40}]
  ```
  The quantity means its value at the point `(x, y)` you enter. The equation may be nonlinear and use the quantity, `diff(T, x)`, `diff(T, y)`, `diff(T, x, 2)`, `diff(T, y, 2)`, `x`, `y` and parameters (no mixed derivatives). Give one condition for each of
  `left`, `right` (the ends of the first interval), `bottom`, `top`: a value, which may depend on the coordinate along that side (`top: T = T0*sin(pi*x/a)`), or a relation with the slope across the side. At least one side must be a value. Numerics: five-point second-order differences
  on `nodes` × `nodes` intervals (default 40, 8 to 100), slope conditions through ghost nodes, Newton's method with a banded Jacobian and banded LU; `guess` (optional, one line, may depend on x and y) matters only for nonlinear equations. As for 1-D problems, a
  half-resolution solve gives an estimated discretisation error. The result page shows a colour map of the field and profiles along both axes through your point; any other quantity (an edge temperature that gives a chosen value at a point…) is found by
  [numerical root-finding](#solving-for-anything-numerical-inversion). Regions with rectangular cutouts (L-shapes, plates with holes) are in the entry on cutouts below; other non-rectangular regions (curved boundaries) are not supported (coupled unknowns and time dependence in 2-D are in the entry above; steady 2-D problems without cutouts stay single-field with no mixed derivatives).
* **Steady problems in three space dimensions (and several fields):** add `third`, `third_start`, `third_end` to a steady problem (a `second` variable, no `time`): `"equations": ["k*(diff(T, x, 2) + diff(T, y, 2) + diff(T, z, 2)) + q = 0"]`, one condition per field on each of the six sides `left`, `right`, `bottom`, `top`, `front`, `back`, and an optional starting guess `"guess": ["T = Ts"]` (zero by default, fine for linear problems). Write each equation as a residual in any form (a residual's terms must have the same dimension); with several fields give one equation per field, in the order the fields first appear. The nodes per direction run from 6 to 28 (default 16). Solved by Newton's method with a finite-difference Jacobian over column groups, a sparse LU factorisation and a damped step; a second solve on half the intervals gives the error estimate. If every side has a slope condition the solution is determined only up to a constant and the run stops with a message saying so. Results: the field on the plane through your third coordinate and profiles through your point. Time-dependent problems in three dimensions are in the entry for transients; mixed derivatives and point sources are not available in the steady form.
* The closed-form search on a user equation is limited to 3 s; everything obeys the time limit in Settings. The Python-script export solves every numerically solved block again with SciPy and checks itself against SlideRule's values ("matches the SlideRule reference values"): initial-value problems, also with **events** (terminal events stop the path, reset events restart it, event times and values are results), **delay equations** (the method of steps with the history interpolated from the segments already computed), **boundary-value problems** (SciPy's collocation solver; unknown parameters, a free end, conditions at interior points by splitting the interval, events along the solution) and **partial differential equations** (the same second-order finite differences as the solver in a compact NumPy kernel: one to three space dimensions, transient with BDF or steady with Newton, coupled fields, periodic directions, point sources, boundary conditions that read other fields, axis singularities, shock-capturing conservation laws including dry beds, moving boundaries, cutouts). The scripts agree to 1e-4 relative (1e-3 for PDEs, whose reference is itself a tolerance-limited time integration); a quantity that is zero by construction (the height at touchdown) is compared to an absolute floor. Fractional and stochastic equations have no standalone script: the export reports that and suggests LaTeX, Markdown or HTML.

### Derivatives and integrals
Equations may contain calculus, evaluated symbolically in closed form:

| Write | Meaning |
|---|---|
| `diff(f, t)` · `diff(f, t, 2)` | first / second derivative of the expression `f` with respect to the variable `t` (order 1–4) |
| `integrate(f, (x, a, b))` | definite integral of `f` over `x` from `a` to `b` (nest them for double integrals) |

```
W = integrate(F0*(1 - x/L), (x, 0, d))        # work of a linearly falling force
i = C*diff(V*(1 - exp(-t/(R*C))), t)          # capacitor current from its voltage
```
* The calculus variable of an **integral** (`x` above) needs no declaration; the limits must be numbers or variables and cannot contain it. The variable of a **derivative** must be one of your
  variables and the expression must actually depend on it (otherwise the derivative is zero and you are told so).
* Only **definite** integrals (a constant of integration would be arbitrary). If SymPy cannot find a closed form by textbook methods, the integral is kept and **integrated numerically** (adaptive quadrature) when the equation is evaluated: you can solve for any quantity *outside* the integral, but not for one inside it or in its limits. Evaluation obeys the time limit in Settings (10 s by default). Limits: 4 derivatives/integrals per expression, nested at most as far as the 300-character cap allows. Not allowed in validity checks.
* **Units are checked on the equation as you wrote it**: `d^n f/dx^n` has the units of `f/x^n`, an integral gains the units of its variable, and the limits must share the dimension of that
  variable. So `integrate(F0*(1 + x), …)` (adding a number to a length) and `diff(d + L^2, d)` are refused even though the evaluated form would look fine.
* Solving works as usual because the evaluated equation is algebraic: solve for the upper limit `d`, for `F0`, for `t`… The worked steps show the equation as written, then the evaluated form.
* Not supported: indefinite integrals and integrating tabulated data. (Differential equations have their own section above.)

SymPy parses equations with Python's `eval`, so text that does not come from the library is first checked by `core/safeparse.py`: it must be a plain expression of numbers, the calculation's
own symbols, those functions and arithmetic/comparison operators. Attribute access, subscripts, strings, lambdas, comprehensions, dunder names, calls to anything else, huge literals and huge constant
powers are refused. A shared file therefore cannot execute code; the worst a malicious file can do is be refused. This is covered by tests (including an attempt to create a file).
Remember that the physics of someone else's equation is theirs: read it before relying on it.

The local server writes these files on request, so keep it on the default `127.0.0.1` (do not expose `--host 0.0.0.0` to people you do not trust): file names come only from validated ids (`custom.[a-z0-9_]+`), so they cannot point outside the equations folder, but anyone who can reach the server can add equations.
