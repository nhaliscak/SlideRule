// Runtime configuration. The static web build (scripts/build_web.py) overwrites this file.
//   engine: "auto"     use the local Python server if reachable, else run Python in the browser (Pyodide)
//           "http"     always call the local server
//           "pyodide"  always run the engine in the browser
window.SLIDERULE_CONFIG = { engine: "auto" };
