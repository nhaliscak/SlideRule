# Changelog

All notable changes are listed here, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/); the project is pre-1.0 and
versions are not yet released to PyPI. The day-by-day development record, including dead ends, is in [PROJECT_LOG.md](PROJECT_LOG.md).

## [Unreleased]

### Added
* Property data layer: versioned datapacks with sources, basis and uncertainty; temperature curves that refuse to extrapolate; a **from data…** picker on matching inputs;
  `sliderule data` commands and `/api/data` endpoints.
* Four shipped datapacks, all not for design: `fluids-water-air`, `fluids-coolprop` (30 fluids computed with CoolProp), `materials-typical` (sources still "citation needed")
  and `nist-cryo` (23 cryogenic materials, from NIST with its acknowledgement; see [DATA_SOURCES.md](DATA_SOURCES.md)).
* Importers for local-only data: `scripts/import_crc_materials.py` (CRC Handbook extract) and `scripts/build_coolprop_pack.py`, `scripts/import_nist_cryo.py`.
* LiveCalc: worked steps for library calls and user functions, export to Python and notebooks, list arithmetic, hidden-root and near-miss help for inverse solves.
* Community files: code of conduct, security policy, contributing guide, issue and pull-request templates, citation file.

### Added (desktop app)
* `sliderule app --api`: the desktop app also serves the API to other programs on a known port (default 8765) with a loopback-only Host check, refusal of cross-site web requests, an optional bearer token (`--api-token`) and opt-in CORS (`--api-origin`); see the README.

### Changed
* `materials-typical` is re-sourced from open references (NASA CR-123772 and CR-123775, NISTIR 7401, NIST cryogenic fits, a state bridge manual), with strengths for 6061-T6 and Ti-6Al-4V (printed minimums as the low end) and a measured steel Poisson's ratio (0.265, from a 1946 National Bureau of Standards paper); no value reads "citation needed" any more.
* **`sliderule serve` is guarded like the API port**: it answers only to `localhost`, `127.0.0.1` and `[::1]` (against DNS rebinding) and refuses requests that a web page on another site makes (an `Origin` header that is not its own). With `--host 0.0.0.0` the Host rule is dropped, the Origin rule stays, and a warning says it is open to the network.
* `sliderule app` (native window) works: it waits for its private server before opening, uses a free port, allows downloads (Export, Save case and CSV were silently blocked), and explains a missing GUI toolkit instead of crashing; the `desktop` extra installs the Qt backend on Linux.
* **Python 3.12 or newer is required** (the code uses f-string syntax from 3.12; continuous integration had never passed on 3.10).
* Continuous integration: lint and wheel-build jobs, least-privilege permissions, weekly schedule, longer calculation time limit on shared runners.
* Package metadata: SPDX licence, authors, classifiers, project URLs.

### Fixed
* Speed-sensitive tests no longer fail on slow shared runners.
