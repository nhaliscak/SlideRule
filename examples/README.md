# Examples

Small, runnable examples of using SlideRule. Every one was run against the code in this repository, and a test (`tests/test_examples.py`) keeps the Python ones working.
They need SlideRule installed (`pip install ".[server]"` from a clone, Python 3.12 or newer).

| File | What it shows | Run it with |
|---|---|---|
| [`01_command_line.sh`](01_command_line.sh) | Searching, showing and solving calculations, solving for a different unknown, worked steps, unit conversion, property data | `sh examples/01_command_line.sh` |
| [`02_python_api.py`](02_python_api.py) | The same from Python: solving, the worked solution as data, backward solving, a sweep, property data used in a calculation, conversion | `python examples/02_python_api.py` |
| [`03_http_api.py`](03_http_api.py), [`03_http_api.sh`](03_http_api.sh) | Calling a running SlideRule from another program (Python standard library, and curl) | start `sliderule serve --no-browser`, then `python examples/03_http_api.py` |
| [`04_spring_force.json`](04_spring_force.json) | A calculation of your own, as a plain JSON file | `sliderule custom import examples/04_spring_force.json`, then `sliderule solve custom.spring_force k="3 kN/m" x="2 cm" --for F` |
| [`05_livecalc_session.txt`](05_livecalc_session.txt), [`05_livecalc.py`](05_livecalc.py) | A LiveCalc session: paste the lines into the LiveCalc tab, or evaluate the file from Python | `python examples/05_livecalc.py` |

Notes:
* Each `sliderule` command loads the whole catalogue, which takes a few seconds, so the shell script takes a minute or two. The Python examples load it once.
* `sliderule custom import` saves the equation in your SlideRule folder (`~/.sliderule`, or `$SLIDERULE_HOME`); `sliderule custom remove custom.spring_force` takes it out again.
* To try the HTTP example with a token, start `sliderule app --api --api-token mysecret` and run `python examples/03_http_api.py --token mysecret`.
