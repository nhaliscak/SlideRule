"""What LiveCalc can do, as data: the functions, constants and commands available, each with examples that are *run* by the engine.

The editor's function search shows this list. The result next to every example is computed when the list is requested (by the same
code that evaluates what the user types), so an example can never show a value the engine would not produce, and a test fails if one
stops working.
"""

from __future__ import annotations

from .livecalc import CONSTANTS, FUNCTIONS, QCONSTANTS, Session

# (name, category, signature, summary, search words, examples)
_ENTRIES: list[tuple[str, str, str, str, str, list[str]]] = [
    ("sqrt", "Powers and roots", "sqrt(x)", "Square root. Units are halved, so m^2 gives m.", "square root radical",
     ["sqrt(16 m^2)", "sqrt(2)"]),
    ("cbrt", "Powers and roots", "cbrt(x)", "Cube root. Units are divided by three (m^3 gives m).", "cube root",
     ["cbrt(27 m^3)", "cbrt(-8)"]),
    ("^", "Powers and roots", "x^y", "Power (also written **). Units are raised to the power too; the exponent has no unit.", "power exponent square cube squared",
     ["(3 m)^2", "2^10", "9.81 m/s^2 * (2 s)^2 / 2"]),
    ("exp", "Exponentials and logarithms", "exp(x)", "e raised to x. x has no unit.", "exponential growth decay e to the",
     ["exp(1)", "exp(-0.5)"]),
    ("ln", "Exponentials and logarithms", "ln(x)", "Natural logarithm (base e) of a positive, unitless number.", "natural logarithm log base e",
     ["ln(10)", "ln(e^2)"]),
    ("log", "Exponentials and logarithms", "log(x)", "Natural logarithm, the same as ln (this is how My equations spells it).", "natural logarithm ln",
     ["log(e)"]),
    ("log10", "Exponentials and logarithms", "log10(x)", "Logarithm to base 10.", "common logarithm decibel ph order of magnitude",
     ["log10(1000)", "10*log10(200)"]),
    ("log2", "Exponentials and logarithms", "log2(x)", "Logarithm to base 2.", "binary logarithm bits",
     ["log2(8)", "log2(1024)"]),
    ("sin", "Trigonometry", "sin(angle)", "Sine. Write angles with a unit (30 deg); a plain number is in radians.", "sine angle degrees radians trigonometry",
     ["sin(30 deg)", "sin(pi/6)"]),
    ("cos", "Trigonometry", "cos(angle)", "Cosine of an angle (degrees if you write deg, otherwise radians).", "cosine angle degrees radians trigonometry",
     ["cos(60 deg)", "cos(pi)"]),
    ("tan", "Trigonometry", "tan(angle)", "Tangent of an angle.", "tangent slope angle degrees radians trigonometry",
     ["tan(45 deg)", "tan(0.5)"]),
    ("asin", "Trigonometry", "asin(x)", "Inverse sine, for x between -1 and 1. The answer is an angle in radians; add ‘to deg’ for degrees.", "arcsine inverse sine arc",
     ["asin(0.5) to deg", "asin(1)"]),
    ("acos", "Trigonometry", "acos(x)", "Inverse cosine, for x between -1 and 1 (radians; ‘to deg’ converts).", "arccosine inverse cosine arc angle",
     ["acos(0.5) to deg", "acos(0)"]),
    ("atan", "Trigonometry", "atan(x)", "Inverse tangent (radians; ‘to deg’ converts).", "arctangent inverse tangent arc slope angle",
     ["atan(1) to deg", "atan(0.5)"]),
    ("atan2", "Trigonometry", "atan2(y, x)", "Angle of the point (x, y) from the x-axis, in the right quadrant. y and x need the same unit.", "arctangent two argument direction bearing quadrant",
     ["atan2(3 m, 4 m) to deg", "atan2(1, -1) to deg"]),
    ("sinh", "Hyperbolic functions", "sinh(x)", "Hyperbolic sine.", "hyperbolic sine catenary", ["sinh(1)"]),
    ("cosh", "Hyperbolic functions", "cosh(x)", "Hyperbolic cosine.", "hyperbolic cosine catenary", ["cosh(1)", "cosh(0)"]),
    ("tanh", "Hyperbolic functions", "tanh(x)", "Hyperbolic tangent.", "hyperbolic tangent waves", ["tanh(2)"]),
    ("abs", "Rounding and comparison", "abs(x)", "Absolute value; the unit is kept.", "absolute value magnitude modulus",
     ["abs(-5 m)", "abs(3 m - 5 m)"]),
    ("min", "Rounding and comparison", "min(a, b, ...)", "Smallest of two or more values with the same unit.", "minimum smallest lowest least",
     ["min(3 m, 50 cm)", "min(4, 9, 2)"]),
    ("max", "Rounding and comparison", "max(a, b, ...)", "Largest of two or more values with the same unit.", "maximum largest highest greatest",
     ["max(2, 7, 4)", "max(3 m, 50 cm)"]),
    ("floor", "Rounding and comparison", "floor(x)", "Round down to a whole number (in the unit you give).", "round down integer truncate",
     ["floor(2.7)", "floor(-2.1 m)"]),
    ("ceil", "Rounding and comparison", "ceil(x)", "Round up to a whole number.", "ceiling round up integer",
     ["ceil(2.1)", "ceil(7.2 kg)"]),
    ("round", "Rounding and comparison", "round(x)", "Round to the nearest whole number.", "nearest integer rounding",
     ["round(2.567)", "round(7.5 m)"]),
    ("factorial", "Counting", "factorial(n)", "n! for a whole number n from 0 to 170.", "factorial permutations combinations n!",
     ["factorial(5)", "factorial(10) / (factorial(3) * factorial(7))"]),
    ("sum", "Statistics", "sum(a, b, ...)", "Sum of two or more values with the same unit.", "total add up",
     ["sum(2 m, 30 cm, 1 m)", "sum(1, 2, 3, 4)"]),
    ("mean", "Statistics", "mean(a, b, ...)", "Average of two or more values with the same unit.", "average arithmetic mean",
     ["mean(2 m, 4 m, 9 m)", "mean(20 degC, 30 degC)"]),
    ("median", "Statistics", "median(a, b, ...)", "Middle value of two or more values with the same unit.", "middle value",
     ["median(3, 1, 2)", "median(5 kg, 1 kg, 9 kg, 2 kg)"]),
    ("stdev", "Statistics", "stdev(a, b, ...)", "Sample standard deviation (divides by n − 1) of two or more values with the same unit.", "standard deviation spread variance scatter",
     ["stdev(2, 4, 4, 4, 5, 5, 7, 9)", "stdev(10 mm, 12 mm, 11 mm)"]),
    ("hypot", "Powers and roots", "hypot(a, b, ...)", "Square root of the sum of squares: the length of a vector from its components.", "magnitude length pythagoras vector norm resultant",
     ["hypot(3 m, 4 m)", "hypot(1, 2, 2)"]),
    ("sign", "Rounding and comparison", "sign(x)", "−1, 0 or 1 for a negative, zero or positive value.", "signum positive negative",
     ["sign(-3 m)", "sign(0)"]),
    ("mod", "Rounding and comparison", "mod(a, b)", "Remainder of a divided by b (same unit); the result takes the sign of b.", "remainder modulo modulus",
     ["mod(17 m, 5 m)", "mod(-1, 7)"]),
    ("integrate", "Calculus", "integrate(f, from, to)", "Area under a function you defined between two limits. Units multiply: a velocity integrated over time gives a distance.", "integral area under curve quadrature antiderivative",
     ["f(x) = 3*x^2\nintegrate(f, 0, 2)", "v(t) = 9.81 m/s^2*t\nintegrate(v, 0 s, 4 s)"]),
    ("derivative", "Calculus", "derivative(f, x)", "Slope of a function you defined at x. Units divide: a distance differentiated over time gives a velocity.", "slope gradient differentiate rate of change",
     ["f(x) = x^3\nderivative(f, 2)", "s(t) = 0.5*9.81 m/s^2*t^2\nderivative(s, 3 s)"]),
    ("findroot", "Calculus", "findroot(f, low, high)", "A value between low and high where your function is zero. The function must change sign between the limits.", "root solve zero equation bisection",
     ["h(x) = x^2 - 2\nfindroot(h, 0, 2)", "p(x) = cos(x) - x\nfindroot(p, 0, 1)"]),
    ("sumover", "Calculus", "sumover(f, first, last)", "Adds f(first) + f(first+1) + … + f(last) for whole numbers (up to 10 000 terms).", "series sigma summation add terms",
     ["f(k) = 1/k^2\nsumover(f, 1, 100)", "t(n) = n\nsumover(t, 1, 10)"]),
    ("c0", "Physical constants", "c0", "Speed of light in vacuum, 299 792 458 m/s.", "light speed relativity", ["c0", "1 yr * c0 to m"]),
    ("g0", "Physical constants", "g0", "Standard gravity, 9.80665 m/s².", "gravity acceleration earth weight", ["g0", "80 kg * g0"]),
    ("Gnewton", "Physical constants", "Gnewton", "Newtonian constant of gravitation (G).", "gravitation newton universal", ["Gnewton * 5.972e24 kg / (6.371e6 m)^2"]),
    ("hP", "Physical constants", "hP", "Planck constant (h).", "planck quantum photon", ["hP * c0 / (500 nm) to eV"]),
    ("hbar", "Physical constants", "hbar", "Reduced Planck constant (h / 2π).", "planck quantum dirac", ["hbar"]),
    ("kBoltz", "Physical constants", "kBoltz", "Boltzmann constant (kB; written kBoltz because kB is the kilobyte).", "boltzmann thermal energy entropy", ["kBoltz * 300 K to eV"]),
    ("NA", "Physical constants", "NA", "Avogadro constant.", "avogadro mole particles", ["2 mol * NA"]),
    ("Rgas", "Physical constants", "Rgas", "Molar gas constant.", "gas constant ideal gas", ["1 mol * Rgas * 273.15 K / (101325 Pa) to L"]),
    ("qe", "Physical constants", "qe", "Elementary charge.", "electron charge coulomb", ["qe * 1 V to eV"]),
    ("eps0", "Physical constants", "eps0", "Vacuum permittivity.", "permittivity electric constant capacitor", ["eps0"]),
    ("mu0", "Physical constants", "mu0", "Vacuum permeability.", "permeability magnetic constant", ["mu0"]),
    ("sigmaSB", "Physical constants", "sigmaSB", "Stefan–Boltzmann constant.", "stefan boltzmann radiation black body", ["sigmaSB * (5772 K)^4"]),
    ("me", "Physical constants", "me", "Electron mass.", "electron mass", ["me * c0^2 to keV"]),
    ("mp", "Physical constants", "mp", "Proton mass.", "proton mass", ["mp / me"]),
    ("[ ]", "Lists and vectors", "[a, b, c]", "A list of values with the same unit; a unit after the bracket applies to all. Arithmetic works on every value at once, and two lists of the same length combine value by value.", "list vector array values set",
     ["[1, 2, 3] m", "[1, 2, 3] m * 2", "[10, 20, 30] + [1, 2, 3]"]),
    ("v[i]", "Lists and vectors", "v[2] · v[2:4]", "One value of a list, counting from 1 (-1 is the last), or a slice v[2:4] with both ends included; v[:3] is the first three and v[3:] the rest.", "index element item subscript slice part",
     ["v = [10, 20, 30] kg\nv[2]", "[5, 6, 7][-1]", "v = [10, 20, 30, 40, 50]\nv[2:4]"]),
    ("len", "Lists and vectors", "len(v)", "How many values a list has.", "length count size number of", ["len([4, 5, 6])", "len(range(10))"]),
    ("range", "Lists and vectors", "range(stop) · range(start, stop, step)", "Evenly stepped values from start up to, but not including, stop (start 0 and step 1 if left out).", "sequence counting from to step",
     ["range(5)", "range(0 m, 10 m, 2 m)"]),
    ("linspace", "Lists and vectors", "linspace(a, b, n)", "n evenly spaced values from a to b, both included.", "spaced points grid sweep interval",
     ["linspace(0 s, 1 s, 5)", "linspace(0, 10, 3)"]),
    ("sort", "Lists and vectors", "sort(v)", "The list from smallest to largest.", "order ascending", ["sort([3, 1, 2])"]),
    ("reverse", "Lists and vectors", "reverse(v)", "The list backwards.", "backwards flip", ["reverse([1, 2, 3])"]),
    ("cumsum", "Lists and vectors", "cumsum(v)", "Running totals of a list.", "cumulative sum running total", ["cumsum([1, 2, 3, 4])"]),
    ("diff", "Lists and vectors", "diff(v)", "Differences between neighbouring values (one fewer value).", "difference gradient steps", ["diff([1, 4, 9, 16])"]),
    ("prod", "Lists and vectors", "prod(v)", "The product of all the values (the unit is raised to the number of values).", "product multiply all", ["prod([2, 3, 4])"]),
    ("dot", "Lists and vectors", "dot(a, b)", "Dot product of two vectors of the same length; units multiply.", "scalar product inner vector work projection", ["dot([1, 2, 3], [4, 5, 6])", "dot([10, 0] N, [3, 4] m)"]),
    ("cross", "Lists and vectors", "cross(a, b)", "Cross product of two 3-vectors; units multiply.", "vector product moment torque perpendicular", ["cross([1, 0, 0] m, [0, 1, 0] N)"]),
    ("norm", "Lists and vectors", "norm(v)", "Length of a vector: the root of the sum of squares (the same as hypot of its values).", "magnitude length vector size modulus", ["norm([3, 4] m)"]),
    ("matrix", "Matrices", "[[a, b], [c, d]]", "A matrix is a list of rows (all the same length, one shared unit). Index it with A[row, column], A[1] (a row), A[:, 2] (a column) or A[1:2, 2:3] (a block; both ends included).", "matrix rows columns array 2d table grid",
     ["A = [[1, 2, 3], [4, 5, 6]]\nA[2, 3]", "[[1, 2], [3, 4]] m", "A = [[1, 2], [3, 4]]\nA[:, 2]"]),
    ("transpose", "Matrices", "transpose(A)", "Rows become columns.", "swap flip", ["transpose([[1, 2, 3], [4, 5, 6]])"]),
    ("matmul", "Matrices", "matmul(A, B)", "Matrix product (or a matrix times a vector); units multiply. A * B alone multiplies value by value.", "matrix multiply product dot",
     ["matmul([[1, 2], [3, 4]], [1, 1])", "matmul([[2, 0], [0, 2]] m, [1, 3] N)"]),
    ("det", "Matrices", "det(A)", "Determinant of a square matrix (its unit is raised to the number of rows).", "determinant singular", ["det([[2, 1], [1, 3]])"]),
    ("inv", "Matrices", "inv(A)", "Inverse of a square matrix; the unit is inverted. A singular matrix is refused.", "inverse reciprocal", ["inv([[2, 1], [1, 3]])"]),
    ("solve", "Matrices", "solve(A, b)", "The x that satisfies A x = b (a system of linear equations); the unit of x is the unit of b over that of A.", "linear system equations simultaneous stiffness gaussian elimination",
     ["solve([[2, 1], [1, 3]], [3, 5])", "K = [[200, -100], [-100, 100]] kN/m\nF = [10, 0] kN\nsolve(K, F)"]),
    ("identity", "Matrices", "identity(n)", "The n × n identity matrix (n up to 22).", "unit matrix eye", ["identity(3)"]),
    ("rows", "Matrices", "rows(A)", "How many rows a matrix has (len(A) gives the same).", "height size shape", ["rows([[1, 2, 3], [4, 5, 6]])"]),
    ("cols", "Matrices", "cols(A)", "How many columns a matrix has.", "width size shape", ["cols([[1, 2, 3], [4, 5, 6]])"]),
    ("trace", "Matrices", "trace(A)", "Sum of the diagonal of a square matrix.", "diagonal sum", ["trace([[2, 1], [1, 3]])"]),
    ("trapz", "Data", "trapz(xs, ys)", "Area under measured points joined by straight lines (the trapezoid rule); units multiply, so speed against time gives distance.", "integrate data area under curve numerical integration measured",
     ["trapz([0, 1, 2, 3, 4] s, [0, 2, 4, 6, 8] m/s)"]),
    ("cumtrapz", "Data", "cumtrapz(xs, ys)", "Running area under measured points: a list as long as the data, starting at 0.", "cumulative integral running data",
     ["cumtrapz([0, 1, 2, 3, 4] s, [0, 2, 4, 6, 8] m/s)"]),
    ("interp", "Data", "interp(x, xs, ys)", "Value at x read from measured points by straight-line interpolation (x may be a list; xs must increase; no extrapolation).", "interpolate lookup table read between points",
     ["interp(2.5 s, [0, 1, 2, 3, 4] s, [0, 2, 4, 6, 8] m/s)"]),
    ("slope", "Data", "slope(xs, ys)", "Slope of the least-squares straight line through the points; the unit is that of y over x.", "linear regression fit gradient trend line",
     ["slope([0, 1, 2, 3] s, [1, 3, 5, 8] m)"]),
    ("intercept", "Data", "intercept(xs, ys)", "Where the least-squares straight line crosses x = 0; the unit is that of y.", "linear regression fit offset trend line",
     ["intercept([0, 1, 2, 3] s, [1, 3, 5, 8] m)"]),
    ("rsquared", "Data", "rsquared(xs, ys)", "R², how much of the variation in y the straight-line fit explains (1 is a perfect line).", "regression goodness of fit determination coefficient",
     ["rsquared([0, 1, 2, 3], [1, 3, 5, 8])"]),
    ("corr", "Data", "corr(xs, ys)", "Correlation coefficient of two lists, from −1 to 1.", "correlation relationship pearson", ["corr([1, 2, 3, 4], [2, 4, 5, 9])"]),
    ("polyfit", "Data", "polyfit(xs, ys, n, at)", "Least-squares polynomial of degree n (1 to 8) through the points, evaluated at the value or list `at`.", "curve fit regression polynomial quadratic trend predict",
     ["polyfit([0, 1, 2, 3], [1, 3, 7, 13], 2, 4)", "polyfit([0, 1, 2, 3] s, [1, 4, 9, 16] m, 2, [4, 5] s)"]),
    ("eigvals", "Matrices", "eigvals(A)", "Eigenvalues of a square matrix, smallest first (real ones only); they have the matrix's unit: natural frequencies squared from stiffness over mass, principal stresses.", "eigenvalue principal stress natural frequency modes",
     ["eigvals([[2, 1], [1, 2]])"]),
    ("eigvecs", "Matrices", "eigvecs(A)", "Eigenvectors as the columns of a matrix, each of length 1, in the order of eigvals.", "eigenvector mode shape principal directions", ["eigvecs([[2, 1], [1, 2]])"]),
    ("i / j", "Complex numbers", "3 + 4i", "Write a complex number with i or j after a number (4i, 4j) or alone (the imaginary unit), unless you defined a variable of that name. Arithmetic, units (10 ohm + 5j ohm), lists and matrices work with them; the result also shows its polar form.", "complex imaginary phasor impedance ac a+bi",
     ["3 + 4i", "(3 + 4i) * (1 - 2i)", "Z = 10 ohm + 5j ohm\nabs(Z)"]),
    ("real", "Complex numbers", "real(z)", "The real part of a complex number (the unit is kept).", "re component", ["real(3 + 4i)"]),
    ("imag", "Complex numbers", "imag(z)", "The imaginary part of a complex number (the unit is kept).", "im component reactance", ["imag(3 + 4i)"]),
    ("conj", "Complex numbers", "conj(z)", "The complex conjugate: the sign of the imaginary part flips.", "conjugate", ["conj(3 + 4i)"]),
    ("arg", "Complex numbers", "arg(z)", "The angle of a complex number in radians (add ‘to deg’ for degrees); abs(z) is its size.", "angle phase argument phasor", ["arg(3 + 4i) to deg", "arg(1 - 1i) to deg"]),
    ("polar", "Complex numbers", "polar(r, angle)", "The complex number of size r at an angle (radians, or write 30 deg); r keeps its unit.", "phasor polar form magnitude angle rectangular", ["polar(5, 53.13 deg)", "polar(230 V, -30 deg)"]),
    ("lstsq", "Matrices", "lstsq(A, b)", "The x that makes A x as close to b as possible (least squares) when there are more equations than unknowns, for example fitting a line or a plane to measurements; the unit of x is that of b over A.", "least squares overdetermined fit regression normal equations",
     ["lstsq([[1, 1], [1, 2], [1, 3], [1, 4]], [6, 5, 7, 10])"]),
    ("rank", "Matrices", "rank(A)", "The number of independent rows (or columns) of a matrix.", "independent singular dimension", ["rank([[1, 2], [2, 4]])"]),
    ("cond", "Matrices", "cond(A)", "Condition number of a square matrix: how much errors in the data can grow in solve() (1 is ideal; above about 1e10 the answer has no reliable digits).", "ill conditioned sensitivity error amplification", ["cond([[1, 2], [3, 4]])"]),
    ("pinv", "Matrices", "pinv(A)", "The pseudo-inverse of any matrix (the unit is inverted).", "moore penrose inverse generalised", ["pinv([[1, 1], [1, 2], [1, 3]])"]),
    ("svdvals", "Matrices", "svdvals(A)", "The singular values of a matrix, largest first.", "singular value decomposition svd principal gains", ["svdvals([[3, 0], [0, 4]])"]),
    ("qr_q", "Matrices", "qr_q(A)", "The orthonormal factor Q of A = Q·R (QR decomposition); it has no unit. matmul(qr_q(A), qr_r(A)) gives A back.", "qr decomposition orthogonal factorization gram schmidt least squares", ["qr_q([[3, 1], [4, 2]])"]),
    ("qr_r", "Matrices", "qr_r(A)", "The upper-triangular factor R of A = Q·R; it has the unit of A.", "qr decomposition triangular factorization", ["qr_r([[3, 1], [4, 2]])"]),
    ("lu_l", "Matrices", "lu_l(A)", "The unit lower-triangular factor L of P·A = L·U written as A = P·L·U (partial pivoting); it has no unit.", "lu decomposition factorization gaussian elimination", ["lu_l([[4, 3], [6, 3]])"]),
    ("lu_u", "Matrices", "lu_u(A)", "The upper-triangular factor U of A = P·L·U; it has the unit of A.", "lu decomposition factorization gaussian elimination row echelon", ["lu_u([[4, 3], [6, 3]])"]),
    ("lu_p", "Matrices", "lu_p(A)", "The permutation matrix P of A = P·L·U (which rows were swapped).", "lu decomposition pivot permutation", ["lu_p([[4, 3], [6, 3]])"]),
    ("chol", "Matrices", "chol(A)", "The lower-triangular L with A = L·Lᵀ for a symmetric, positive-definite matrix (stiffness, covariance); its unit is the square root of A's.", "cholesky decomposition factorization positive definite covariance", ["chol([[4, 2], [2, 3]])"]),
    ("shape", "Matrices", "shape(A)", "The size of a list, a matrix or a 3-D list as a list: [3] for three values, [2, 3] for a matrix, [2, 2, 2] for two 2 × 2 layers.", "size dimensions length rows columns layers tensor 3d", ["shape([[1, 2, 3], [4, 5, 6]])", "shape([[[1, 2], [3, 4]], [[5, 6], [7, 8]]])"]),
    ("outer", "Matrices", "outer(a, b)", "The matrix of every product a[i]·b[j] of two lists; units multiply.", "outer product tensor", ["outer([1, 2], [3, 4] m)"]),
    ("var", "Statistics", "var(v)", "Sample variance of a list (divides by n − 1); the unit is squared.", "variance spread", ["var([2, 4, 4, 4, 5, 5, 7, 9])"]),
    ("percentile", "Statistics", "percentile(v, p)", "The value below which p percent (0 to 100) of the list lies, interpolating between values; p may be a list.", "quantile median quartile percent rank", ["percentile([1, 2, 3, 4, 5], 50)", "percentile([1, 2, 3, 4, 5], [25, 75])"]),
    ("calc", "Library", "calc(\"id\", \"output\", name = value, ...)", "Solve a library calculation for one output; with Show steps on you get that calculation’s own working (formulas, inputs in SI, the numbers put in, unit reduction). Give the inputs by name; give a list for an input to get a list of results (a sweep). The id can be its end (\"turbine_power\"). Find calculations with the Library box under the search.", "library calculation formula engine call equation sweep parametric study",
     ["calc(\"energy.wind.turbine_power\", \"Pe\", rho = 1.225 kg/m^3, Dr = 100 m, v = 10 m/s, Cp = 0.45, eg = 0.94)", "calc(\"energy.wind.turbine_power\", \"Pe\", rho = 1.225 kg/m^3, Dr = 100 m, v = [5, 10, 15] m/s, Cp = 0.45, eg = 0.94)"]),
    ("pi", "Constants", "pi", "The ratio of a circle's circumference to its diameter (3.14159…).", "circle circumference area",
     ["2*pi*3 m", "pi*(0.5 m)^2"]),
    ("e", "Constants", "e", "Euler's number (2.71828…), the base of natural logarithms.", "euler exponential natural",
     ["e^2", "ln(e)"]),
    ("to", "Commands and syntax", "value to unit", "Convert to another unit (also ‘in’). Offset temperatures convert properly.", "convert conversion unit in to change units",
     ["120 km/h to m/s", "20 degC to degF", "5 cm in in"]),
    ("=", "Commands and syntax", "name = value", "Define a variable; later lines can use it. ans is always the last result.", "variable assign assignment define store",
     ["m = 80 kg\na = 9.81 m/s^2\nF = m*a", "5 m + 3 m\nans * 2"]),
    ("f(x) =", "Commands and syntax", "f(x) = expression", "Define your own function of one or more values, then call it. Tick its box in the history to plot it (one value: a curve; two: a surface).",
     "function define user custom lambda g(a, b)", ["f(x) = 3*x^2 - 2\nf(4)", "g(a, b) = a*b\ng(3 m, 2 m)"]),
    ("plot nyquist", "Commands and syntax", "plot nyquist H(i*w) for w from A to B", "The Nyquist curve of a transfer function: its real part across, imaginary part up, for frequencies A to B (default 0.01 to 100, spaced logarithmically) and, for a real system, their mirror image. The critical point is −1 + 0i.", "nyquist frequency response transfer function stability control complex plane polar", ["H(s) = 1/(1 + s)\nplot nyquist H(i*w) for w from 0.01 to 100"]),
    ("plot argand", "Commands and syntax", "plot argand z", "Draw a complex number, or each number of a list, as a point on the complex plane (real part across, imaginary part up, equal scales).", "argand complex plane phasor roots poles zeros", ["plot argand [1 + 2i, -1 + 0.5i, 2 - 1i]"]),
    ("plot", "Commands and syntax", "plot expression from A to B", "Draw a graph. Separate several curves with commas; give the range a unit for a labelled axis; name the variable with ‘for’. End with logx, logy or loglog for logarithmic axes; start with parametric for a curve (x(t), y(t)); plot data xs, ys draws the points of lists; equal gives both axes the same scale; twin draws the last curve against a second axis on the right.",
     "plot graph chart curve draw 2d", ["plot sin(x), cos(x) from 0 to 2*pi", "plot 0.5*9.81 m/s^2*t^2 for t from 0 s to 4 s", "plot data [1, 4, 9, 16] m", "plot 5 m*x, 3 s*x^2 from 0 to 4 twin", "plot parametric 2*cos(t), sin(t) for t from 0 to 2*pi equal", "f(x) = x^2\nplot f from -3 to 3", "plot x^2, x^3 from 1 to 1000 loglog", "plot parametric 2*cos(t), sin(t) for t from 0 to 2*pi"]),
]


def _run_example(text: str, sig: int) -> dict:
    sess = Session(sig)
    last = None
    for i, line in enumerate(text.split("\n")):
        last = sess.run_line(line, i + 1)
        if last["kind"] == "error":
            break
    out = {"text": text, "ok": bool(last) and last["kind"] != "error"}
    if last is None or last["kind"] == "error":
        out["error"] = (last or {}).get("error", {}).get("message", "no result")
        return out
    if last["kind"] == "plot":
        n = len(last["plot"]["series"])
        out["result_text"] = f"a graph of {n} curve{'s' if n != 1 else ''}"
    elif last["kind"] == "function":
        out["result_text"] = "function defined"
    else:
        out["result_text"] = f"{last.get('value_text', '')} {last.get('unit', '')}".strip()
    out["result_latex"] = last.get("display_latex", "")
    return out


def functions_catalog(sig_figs: int = 6) -> dict:
    """Every function, constant and command LiveCalc knows, with worked examples."""
    sig = max(3, min(12, int(sig_figs)))
    items = []
    for name, category, signature, summary, words, examples in _ENTRIES:
        kind = "constant" if name in CONSTANTS or name in QCONSTANTS else "function" if name in FUNCTIONS else "syntax"
        items.append({"name": name, "kind": kind, "category": category, "signature": signature, "summary": summary,
                      "keywords": words, "examples": [_run_example(t, sig) for t in examples]})
    return {"items": items, "categories": list(dict.fromkeys(i["category"] for i in items))}
