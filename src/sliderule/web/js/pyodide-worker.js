// Classic-script worker that boots Pyodide, unpacks the sliderule Python package and serves API calls.
let py = null;
let handle = null;

function progress(message) {
  postMessage({ type: "progress", message });
}

async function boot(cfg) {
  const version = cfg.version || "0.29.3";
  const indexURL = cfg.indexURL || `https://cdn.jsdelivr.net/pyodide/v${version}/full/`;
  progress("Downloading Python runtime…");
  importScripts(indexURL + "pyodide.js");
  py = await loadPyodide({ indexURL });
  progress("Loading SymPy (symbolic algebra)…");
  await py.loadPackage(cfg.packages || ["sympy", "numpy", "scipy"]);
  progress("Loading SlideRule engine…");
  const bundle = cfg.bundle || "sliderule_pkg.zip";
  const res = await fetch(new URL(bundle, self.location.href.replace(/js\/[^/]*$/, "")));
  if (!res.ok) throw new Error(`could not fetch ${bundle}: HTTP ${res.status}`);
  py.unpackArchive(await res.arrayBuffer(), "zip", { extractDir: "/sliderule_pkgs" });
  py.runPython(`
import sys
sys.path.insert(0, "/sliderule_pkgs")
import sliderule.api as _api
`);
  progress("Warming up the calculation library…");
  handle = py.runPython("_api.handle_json");
  handle("meta", "{}");
}

onmessage = async (ev) => {
  const { id, type } = ev.data;
  try {
    if (type === "init") {
      await boot(ev.data.cfg || {});
      postMessage({ id, result: true });
    } else if (type === "call") {
      postMessage({ id, result: handle(ev.data.method, ev.data.params) });
    }
  } catch (e) {
    postMessage({ id, error: String((e && e.message) || e) });
  }
};
