# LiveCalc

The **LiveCalc** tab is a scratchpad calculator that knows about units. Type; the engine evaluates the text on every keystroke and shows it below the history
as Markdown with maths. **Enter** adds it to the history (**Shift+Enter** starts a new line, **↑** on an empty box recalls the last entry, **Esc** clears the box).
The last **200 entries** are kept in this browser (see *Sessions* below to keep more than that, under names); variables carry from one entry to the next, so an entry that defined a variable more than 200 entries ago has
been forgotten along with it. **Show steps** adds the working to every calculation: the expression, the values put in, the conversion to SI and the result. Lines that do their own work are opened up rather than shown as a call: a `calc(...)` library call shows that calculation's own formulas, inputs in SI, numbers put in and unit reduction (the same working as the Calculations tab); a call of your own function shows its definition, arguments and body with the values in; `integrate` and `derivative` show the exact antiderivative or derivative for a plain unitless formula (checked against the numeric answer first) or otherwise the numerical method with its values; `findroot` shows the bracket, the method and the residual; `sumover` lists the terms. Statistics, vector and matrix functions show their definition with the numbers put in: `mean`, `median`, `stdev`/`var` (mean, deviations, squares, divide by n − 1), `percentile`, `dot`, `cross`, `norm`, `trapz`, `interp`, the line fits (`slope`, `intercept`, `rsquared`, `corr`), `det` (2×2, 3×3 expansion, or LU pivots), `inv`, `solve` (Cramer's rule for 2×2), `eigvals` (characteristic equation for 2×2), `cond`, `rank` and the list helpers; physical constants such as `Gnewton` are listed with their values and substituted; `v[2]` shows the list and the entry picked. A function used inside a longer expression is explained first and its result then substituted into the rest. An elementary function that is the whole line (`sqrt`, `sin`, `exp`, `abs` ...) shows what it is and its argument as the function sees it (an angle converted to radians, for example); inside a longer expression it keeps the plain steps. Arithmetic on a list (`[1, 2, 3] m * 2`, `v*2 + 5 kg`) is written out for the first three entries and the last. Complex results show their rectangular and polar forms, and `real`, `imag`, `conj`, `abs`, `arg` and `polar` show their definition with the numbers. `findroot` shows the exact root when the formula has one (`x² − 2 → √2`), and `sumover` the closed form and the exact sum, for formulas without units. Hovering over an entry offers ↺ (edit it again) and × (remove it).

## What a line can be
| You type | You get |
|---|---|
| `5 m + 30 cm` | `5.3 m`. Units are carried through; `5 m + 3 s` is refused. |
| `3 kN * 2 m`, `10 m / 2 s`, `9.81 m/s^2 * 5 kg` | `6 kN·m`, `5 m/s`, `49.05 N` (a result made only of SI base units takes its named unit) |
| `120 km/h to m/s`, `5 cm in in` | a conversion (`to` or `in`; `5 in` is five inches) |
| `20 degC to degF`, `20 degC + 5 K` | offset temperatures: converted, shifted by differences, never multiplied |
| `m = 5 kg`, `a = 9.81 m/s^2`, `F = m*a` | variables; `F` is computed from the others. `ans` is the last result |
| `f(x) = 3*x^2 - 2`, `f(4)`, `g(a, b) = a*b` | functions (evaluated on each call) |
| `F = m*a` while `m` or `a` have no value | an **equation**: shown, not evaluated, and ready to send to My equations |
| `plot sin(x), cos(x) from 0 to 2*pi` | a graph; several curves separated by commas |
| `plot 0.5*m*v^2 for v from 0 m/s to 20 m/s` | a graph with units: the range's unit labels the axis; `for v` names the variable |
| `plot x^2, x^3 from 1 to 1000 loglog` | logarithmic axes: end the line with `logx`, `logy` or `loglog` (a log x axis needs a range above zero; values at or below zero are not drawn on a log y axis) |
| `plot 5 m*x, 3 s*x^2 from 0 to 4 twin` | two units on one graph: `twin` draws the last curve against a second axis on the right |
| `plot parametric 2 m*cos(t), 3 m*sin(t) for t from 0 to 2*pi equal` | `equal` gives both axes the same scale (a circle stays round; both axes need the same unit). Options (`logx logy loglog equal twin`) can be combined at the end in any order |
| `H(s) = 1/(1 + s)` then `plot nyquist H(i*w) for w from 0.01 to 100` | the Nyquist curve of a transfer function: real part across, imaginary part up, equal scales, with the mirror image for negative frequencies of a real system (the critical point is −1 + 0i). Without a range the frequencies run from 0.01 to 100; `logx` spaces them logarithmically (the default without a range). One expression only. A dimensionless transfer function also gets the critical point −1 marked and, where the curve crosses the negative real axis and the unit circle, a **gain margin** (with dB, and a warning when below 1) and a **phase margin**, each refined to the exact crossing frequency (checked against `K/(s(s+1)(s+2))`: gain margin 6/K at w = √2) |
| `plot argand [1 + 2i, -1 + 0.5i, 2 - 1i]` | a complex number, or each number of a list (poles, roots, phasors), as points on the complex plane, equal scales; a unit on the numbers labels both axes |
| `plot parametric 2 m*cos(t), 3 m*sin(t) for t from 0 to 2*pi` | a curve given by x(t) and y(t): exactly two expressions, each with its own unit |
| `# Heading`, `**bold**`, `- item`, `> quote`, `` `code` ``, `$\alpha$` | Markdown text; so is any line that does not read as a calculation |

Functions: `sqrt cbrt exp ln log log10 log2 sin cos tan asin acos atan atan2 sinh cosh tanh abs min max floor ceil round factorial`; constants `pi`, `e`.
`log` is the natural logarithm (as in My equations). Angles: write `30 deg`; a bare number is radians. Write powers with `^` (or `**`).

### Statistics and vector helpers
`sum(a, b, ...)`, `mean`, `median`, `stdev` (sample, n − 1), `hypot(a, b, ...)` (root of the sum of squares), `sign(x)` and `mod(a, b)` take values with the same dimension and keep the unit
of the first (`mean(2 m, 4 m, 9 m)` is `5 m`; `sum(1 m, 2 s)` is refused). Averages of offset temperatures are allowed (`mean(20 degC, 30 degC)` is `25 degC`); sums are not.

### Lists and vectors
`[1, 2, 3] m` is a list: the values share one unit (a unit after the bracket applies to all; `[1 m, 200 cm]` also works). Arithmetic acts on every value (`v*2`, `sqrt(v)`, `v to cm`), and two lists of the same
length combine value by value. `v[2]` is the second value (counting from 1, `-1` is the last). `sum mean median stdev min max hypot` of a single list combine its values (`sum(v*v)`); `len sort reverse cumsum diff prod`,
`range(stop)` / `range(start, stop, step)` (stop not included) and `linspace(a, b, n)` build and reshape lists; `dot(a, b)`, `cross(a, b)` (3 values) and `norm(v)` are the vector products, with units multiplied.
Lists have at most 500 values; a long one is shown as its first five and last three values. `plot data xs, ys` (or `plot data ys` against 1, 2, 3 …, or `plot data xs, ys1, ys2`) draws the points of lists with markers.
Inside a `plot` an array is one value per sample point, so `sum(x)` stays elementwise there.

### Matrices
A list of equal-length lists is a matrix: `A = [[2, 1], [1, 3]]` (up to 500 values, one shared unit, shown in full up to 8 × 8). `A[2, 1]` is one value, `A[1]` or `A[1, :]` a row, `A[:, 2]` a column, `A[1:2, 2:3]` a block; in a list `v[2:4]` takes the second to the fourth value (both ends included, `v[:3]` the first three, `v[-2:]` the last two). `*` and `+` act value by value; `matmul(A, B)` is the matrix product,
`transpose`, `det`, `inv`, `trace`, `identity(n)`, `rows`, `cols`, and `solve(A, b)` solves the linear system A x = b. Units follow: `K = [[200, -100], [-100, 100]] kN/m`, `F = [10, 0] kN`, `solve(K, F)` gives `[0.1, 0.1] m` (the stiffness-matrix example);
`det` raises the unit to the number of rows, `inv` inverts it. A singular matrix is refused with a message instead of a wrong answer; rounding noise (`-5.6e-17` next to a 1) is shown as 0.

**Factorisations.** `qr_q(A)` and `qr_r(A)` give A = Q·R (Q orthonormal, no unit; R upper triangular, the unit of A; any shape). `lu_p(A)`, `lu_l(A)` and `lu_u(A)` give A = P·L·U with partial pivoting (P a permutation, L unit lower triangular with no unit, U upper triangular with the unit of A). `chol(A)` gives the lower-triangular L of A = L·Lᵀ for a symmetric positive-definite matrix and refuses any other; its unit is the square root of A's (`chol([[4 m^2, 2 m^2], [2 m^2, 3 m^2]])` is in m). Multiply back with `matmul` to check.

**3-D lists.** A list of equal-size matrices is a 3-D list: `T3 = [[[1, 2], [3, 4]], [[5, 6], [7, 8]]]` (up to 500 values, one shared unit). Index it `T3[layer, row, column]`, counted from 1 like everything else: `T3[2, 1, 2]` is 6, `T3[2]` is the second matrix, `T3[:, 1, 1]` runs through the layers. It adds, multiplies and takes functions element by element. `shape(x)` gives the size of any list (`[2, 2, 2]`). It is shown in full up to 4 × 4 × 4, otherwise as its size. `det`, `trace`, `inv`, `eigvals`, `rank`, `cond` and `transpose` apply to every layer of a 3-D list and stack the answers (`det(T3)` is a list with one number per layer); other matrix functions need a matrix, so index a layer first. (Do not call it `T`: that is the tesla.)

### Measured data
For lists of measurements: `trapz(xs, ys)` (area under the points joined by straight lines; units multiply, so speed over time is a distance), `cumtrapz(xs, ys)` (the running area), `interp(x, xs, ys)` (reads a value between points, `x` may be a list; the x list must increase and there is no extrapolation),
`slope(xs, ys)`, `intercept(xs, ys)`, `rsquared(xs, ys)` and `corr(xs, ys)` for the least-squares straight line, and `polyfit(xs, ys, n, at)`, the least-squares polynomial of degree 1 to 8 evaluated at `at` (the coefficients have a different unit each, so the fit is returned as values).
`eigvals(A)` and `eigvecs(A)` give the eigenvalues (smallest real part first; they keep the matrix's unit) and the unit-length eigenvectors (the columns of the result) of a square matrix; a real matrix can have complex eigenvalues (`eigvals([[0, 1], [-1, 0]])` is `[-i, i]`).

### Fitting, conditioning and statistics
`lstsq(A, b)` solves an over-determined system (more equations than unknowns) in the least-squares sense, e.g. fitting a plane to measurements; the unit of the answer is that of `b` over `A`. `rank(A)`, `cond(A)` (how much `solve` can amplify errors; above about 1e10 the digits mean nothing),
`pinv(A)` (pseudo-inverse), `svdvals(A)` (singular values) and `outer(a, b)` complete the matrix set. For lists: `var(v)` (sample variance, squared unit) and `percentile(v, p)` (p from 0 to 100, may be a list). These do not take complex numbers.

### Complex numbers
`3 + 4i` (or `4j`; a lone `i` or `j` is the imaginary unit unless you defined a variable of that name). A complex result also shows its polar form as a note (`5 ∠ 53.1301°`). `abs(z)`, `arg(z)` (radians; `to deg`), `real(z)`, `imag(z)`, `conj(z)` and `polar(r, angle)` convert between the forms;
`sqrt exp ln sin cos tan sinh cosh tanh asin acos atan` accept complex arguments; lists and matrices can hold them (`sum mean prod cumsum`, `matmul det inv solve eigvals eigvecs`, `transpose trace`, `dot cross norm`), so a nodal analysis is
`solve(Y, I)` with `Y` in siemens and `I` in amperes. Units go with them: `Z = 10 ohm + 5j ohm`, `V = Z*2 A to V` is `(20 + 10i) V`. Results that come out exactly real after a product or power are plain numbers again.
What does not take complex numbers says so instead of dropping the imaginary part: ordering and rounding (`max min sort median stdev floor mod ...`), plots (plot `abs(f(x))`, `arg(f(x))`, `real(...)` or `imag(...)` instead), calc inputs, and offset temperatures. `sqrt(-4)` of a real number stays an error; write `sqrt(-4 + 0i)` for the complex root.

### Library calculations
Every calculation of the library can be used as a function: `calc("energy.wind.turbine_power", "Pe", rho = 1.225 kg/m^3, Dr = 100 m, v = 10 m/s, Cp = 0.45, eg = 0.94)` → `2034.87 kW`. The first text is the calculation
(its full id, or just its end, `"turbine_power"`, when that is unique), the second the output you want (the first output if left out), then the inputs by name. A **list** for an input gives a list of results, one per value: `w = linspace(3 m/s, 20 m/s, 8)` then `P = calc("turbine_power", "Pe", v = w, ...)` is a sweep that
`plot data w, P` draws, and a function wrapping `calc` can be plotted like any other (`f(v) = calc(..., v = v, ...)`, then `plot f from 3 m/s to 20 m/s`). All the lists must have the same length, at most 400 values. LiveCalc has no `%`: write 0.94 for 94 %. Calculations with differential equations or data tables work too (the time is an input, so a list of times is a response curve), and so do your own *My equations* (`calc("custom.my_beam", ...)`, or just the end of the id). In the search box, matching library calculations appear under **Library calculations** with their inputs and a ready-to-run
line (every one of the library's worked examples runs as a `calc(...)` line; a test samples them).

### Units that are also function names, and unit groups
`min` and `max` are units (minute, and so on) unless called like a function: `20 L/min`, `5 min`, but `min(4, 2)`. A bracketed group of units can follow `/`: `0.2 L/(mg*min)`. A negative temperature keeps its scale: `-56.5 degC to K`. Unit exponents may be decimals or fractions in brackets: `0.02 K/s^0.5`, `0.02 K/s^(1/2)`.

### Calculus on functions you define
Define a function of one value, then use its name: `f(x) = 3*x^2`, `integrate(f, 0, 2)` → `8`; `v(t) = 9.81 m/s^2*t`, `integrate(v, 0 s, 4 s)` → `78.48 m`;
`derivative(f, 2)` → `12` (five-point central difference); `findroot(h, 0, 2)` finds a zero between two limits where the function changes sign; `sumover(f, 1, 100)` adds `f(1) + … + f(100)`
(whole numbers, up to 10 000 terms). Units follow: integrating multiplies by the unit of the variable, differentiating divides. In a `plot` the limits may depend on the variable, so
`plot integrate(f, 0, x), derivative(f, x) from 0 to 3` draws the area function and the slope (up to 400 points). Not available in My equations (a note says so when you send such a line there).

### Physical constants
Named values with units, exact where the SI defines them (CODATA 2018 otherwise): `c0` (speed of light), `g0` (standard gravity), `Gnewton`, `hP`, `hbar`, `kBoltz` (not `kB`, which is the
kilobyte), `NA`, `Rgas`, `qe`, `eps0`, `mu0`, `sigmaSB`, `me`, `mp`. `hP*c0/(500 nm) to eV` gives the energy of a green photon. Defining a variable with the same name (`me = 5 kg`)
takes precedence, as for any name.

### Radians or degrees
The **Angles** switch in the toolbar chooses how a *bare number* is read by `sin`, `cos`, `tan` and by the angle of `polar(r, angle)`, and in which unit `asin`, `acos`, `atan`, `atan2` and `arg` answer. In **Radians** (the default) `sin(pi/6)` is 0.5 and `asin(0.5)` is 0.5236. In **Degrees** `sin(30)` is 0.5 and `asin(0.5)` is `30 deg`
(`sin(pi/6)` is then the sine of 0.52 degrees: a number is a number). An angle that carries its unit (`30 deg`, `0.5 rad`) is never changed by the switch, and `to deg` / `to rad` always convert. The choice applies to the history, the preview, plots (so `plot sin(x) from 0 to 360` draws one period), exports and saved sessions (a session remembers its mode), and is remembered in this browser. My equations always work in radians, so sending an equation
with an angle function from degree mode shows a warning.

### Names and units
* A name **right after a number is a unit** when it is one: `5 m` is five metres even if you defined a variable `m`; to multiply by your variable write `5*m`.
  A note on the line tells you when this shadowed a variable. `/name` after a unit continues the unit (`9.81 m/s^2`, `1000 kg/m^3`); to divide by a variable write `5 m / (t)`.
* In an assignment or equation a bare name is a variable. So in `v^2 = u^2 + 2*a*s` the `s` is a variable, not seconds, but `x = 5*m` multiplies by a variable `m`
  (write `x = 5 m` for metres).
* A plot's independent variable is the one name it uses that has no value (`x` by default). If it could also be a unit (`t` is a tonne, `m` a metre), name it:
  `plot 0.5*a*t^2 for t from 0 s to 4 s`.

## Finding a function
The search box **below the input field** lists the functions, constants and commands you can use. Type a name or a word for what you want (`root`, `angle`, `log`, `convert`, `round`) and the matches appear
as one line each: just the signature (`integrate(f, from, to)`), an **Insert** button and a **More** button. Insert puts the command in the input box with nothing filled in (`sqrt()`, the cursor inside the brackets);
**More** opens the description and **examples that have been run by the engine**, each with its result (`sin(30 deg) → 0.5`, `sqrt(16 m^2) → 4 m`). Click an example to use it: it fills an empty input
box, or goes on a new line below what you have typed. For a library calculation, Insert puts in `calc("id", "output", rho = , Dr = , …)` with every input named, the cursor at the first value. **Browse all** shows everything grouped by topic. The **What can I type?** summary sits under the search box. Functions you have defined yourself appear too, marked *yours*, with an example call.

## Plotting the functions you define
A function defined in the history with **one value** (`f(x) = 3*x^2 - 2`) gets a **2D plot** box, one with **two values** (`h(a, b) = a*b`) a **3D plot** box. Tick it and the function is added to the
**Plot** panel above the history (up to six at once; × on its chip removes it):

* functions of one value are curves on a shared graph (curves with different units get separate graphs);
* functions of two values are surfaces in an interactive 3D view: **drag** to rotate, **scroll** to zoom, **double-click** to reset, arrow keys when it has focus. Surfaces with the same unit share one view;
* the ranges (default −10 to 10 for x, and y for surfaces) are boxes in the panel; write them like quantities if the function needs units, e.g. `0 s` and `4 s`. The first value of a function is x, the second y;
* the plot follows the history: a function that is removed or redefined is re-plotted (the last definition wins), one that cannot be plotted on the range (for example `sqrt(x)` for negative x, or a name with no value yet)
  is reported under the graphs and does not stop the others. Which functions are ticked, and the ranges, are remembered in this browser.

## Where the plots appear
The **Plots** switch in the toolbar chooses between two layouts, and the choice is remembered in this browser:

* **In the history** (default): graphs from `plot` commands sit inside the history lines, and the Plot panel for ticked functions is above the history.
* **On the right**: the history, the preview and the input stay in a column on the left, and every plot moves to a column on the right: the Plot panel for ticked functions (curves and 3D surfaces) and a **Graphs**
  section with the graph of each `plot` command (the line you are typing first, then the history newest first). The history line for such a command keeps its formula and says the graph is shown on the right.
  On a narrow screen the right column drops below the history.

**Pin** (under every graph): keeps a snapshot of that graph in a **Pinned graphs** panel above the history (up to 4, kept in this browser, folded away with its arrow, each removable or *Unpin all*), so it stays in view while you keep working below; it does not follow later edits.

## Sessions, export and import
The **Sessions ▾** menu (first item of the toolbar; it closes when you click elsewhere or press Esc): **Save…** keeps the current history under a name (up to 50 sessions, in this browser) and **Open** it again from the list (replacing the history after a check);
**Markdown** downloads the history as a document, text as typed and every calculation as a display equation with its result (errors are marked; graphs are noted, not drawn); with **Show steps** on, each calculation is followed by its numbered worked steps (`livecalc_export` with `steps: true`);
**Text** downloads the entries exactly as typed, separated by blank lines; **JSON** the same as a file with the session name; **Copy** puts the Markdown on the clipboard.
**Python** downloads a script and **Notebook** a Jupyter notebook that re-run the session with SlideRule's own evaluator (`from sliderule.livecalc import Session`; install with `pip install sliderule`), so units, `calc(...)` library calls and every number are the ones LiveCalc showed; the notebook has one cell per entry, text entries as Markdown cells, and the results already saved in it. They are not a translation into plain Python (a LiveCalc line is not a Python expression), and graphs are not drawn there; a test runs both and compares what they print with the notebook's saved results.
**Import…** reads a `.json` file written by Export or a plain text file (entries separated by blank lines, 500 kB at most) and adds its entries after the current history. A request evaluates at most 200 entries and 1500 lines.

## Sending an equation to My equations
Select an equation (in the input box, or in the history: click-drag over it) and press **Send selection to My equations**, or click **→ My equations** beside a
formula in the history. With nothing selected the line under the cursor is used. The new-equation form opens with:

* the variables found in the equation, with **units and example values taken from the variables you have defined** (the result variable's unit is worked out
  from the right-hand side), the left-hand variable marked as the one to solve for, and the equation text with function names spelled the way My equations
  expects (`abs` -> `Abs`, `ceil` -> `ceiling`);
* a note listing anything it could not fill in (unknown units, unit literals such as `5 N` that My equations does not allow inside an equation, `cbrt`/`round`).

Give it a name, pick a discipline, check the units; the editor's live check has the final word, as for any equation.

## Limits and safety
Nothing is executed as code: the text is parsed by a small parser inside the engine. Lines are limited to 400 characters and 250 tokens, nesting to 40 levels, a request
to 1500 lines; very large results, division by zero and `(-8)^0.5` are reported as errors, and the calculation time limit in ⚙ Settings applies. The history never
leaves the browser (`localStorage`), except that the engine evaluates it each time (the local server or the in-page Pyodide).
