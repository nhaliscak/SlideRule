# Contributing

Thanks for helping. Please read the [code of conduct](CODE_OF_CONDUCT.md); report security problems privately as described in [SECURITY.md](SECURITY.md). Bug reports and wrong-result reports are as valuable as code: [open an issue](https://github.com/nhaliscak/SlideRule/issues)
with the calculation, the inputs and what you expected.

## Set up

```bash
python -m venv .venv && . .venv/bin/activate     # Python 3.12 or newer
pip install -e ".[dev]"
ruff check .
pytest                                           # the full suite takes several minutes; `pytest tests/test_x.py` for one file
```

## Ground rules

* **Every formula needs a source and an independent test.** Add the reference in the calculation, a worked example, and a test that
  checks the result against a hand calculation or a published value, not against the code's own output.
* **No copyrighted tables or standards text.** Data must be a physical fact, computed from a published formula, or from a source whose
  licence allows redistribution, with the source recorded (see [DATA_SOURCES.md](DATA_SOURCES.md)). If in doubt, do not add it.
* **No LLMs in the engine**: results come from deterministic code.
* Keep `README.md` and `PROJECT_LOG.md` current (a dated entry for meaningful work, failures included).

Adding a calculation takes about 15 lines: see `src/sliderule/library/` and `docs/ARCHITECTURE.md`. Datapack format and vocabularies:
`docs/DATA_AND_STANDARDS_STRATEGY.md` §10 to §12.
