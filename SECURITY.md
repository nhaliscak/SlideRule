# Security policy

## Supported versions

SlideRule is pre-1.0. Only the latest release and the `main` branch receive fixes.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private reporting instead: on the repository's **Security** tab choose
**Report a vulnerability**. Include what you found, how to reproduce it, and what you think the impact is. You can expect an acknowledgement within a
week and a fix or a decision within 30 days; reporters are credited in the changelog unless they prefer not to be.

## What is in scope

SlideRule evaluates mathematical text, so these are the areas that matter:

* **Equation text from users or shared files.** Typed equations, "My equations" JSON files, LiveCalc input and datapacks are untrusted input.
  Equation text is checked by `src/sliderule/core/safeparse.py` (plain expressions, a short list of functions, no attribute access, lambdas, strings or
  dunder names) before SymPy evaluates it. A way around that check, or code execution from a shared file, is a vulnerability.
* **The local server.** `sliderule serve` binds to `127.0.0.1` by default, answers only to loopback host names and refuses cross-site requests (a foreign `Origin`). Anything that lets another site, another user on the machine, or a remote
  client reach files or run code through it is in scope, and so is unsafe behaviour when `--host` is changed. Do not expose the server to a network
  you do not trust; it has no authentication.
* **Files read and written.** The equations folder (`--equations-dir`), `$SLIDERULE_HOME` and datapack folders: path traversal, or a malicious pack
  or equation file that writes outside them.
* **Rendered output.** Cross-site scripting through Markdown, HTML or LaTeX export of user-supplied text.

## What is out of scope

* A calculation that is slow or uses a lot of memory. The time limit (Settings) is a convenience, not a security boundary.
* A wrong numerical result. That is a bug, not a vulnerability: please use the "Wrong result" issue form.
* Problems in dependencies (SymPy, NumPy, SciPy, FastAPI, Pyodide, KaTeX): report those upstream, and tell us if SlideRule needs a version bump.
* A self-hosted static copy of the website (`scripts/build_web.py`) loads Pyodide from a public CDN (`cdn.jsdelivr.net`); the CDN's own security is outside this project.
