// Two interchangeable back ends behind one interface: `await engine.call(method, params)`.
//   HttpEngine    -> the local FastAPI server (pip-installed app)
//   PyodideEngine -> the same Python package compiled to WebAssembly, in a Web Worker (static site)
// Both speak the {ok, result|error} envelope produced by `sliderule.api.handle`.

export class EngineError extends Error {
  constructor(message, code = "ERROR", status = 0, details = null) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function unwrap(envelope) {
  if (envelope.ok) return envelope.result;
  const e = envelope.error || {};
  throw new EngineError(e.message || "Unknown error", e.code, e.status, e.details);
}

export class HttpEngine {
  constructor(base = "") {
    this.base = base;
    this.kind = "server";
    this.label = "Local Python engine";
  }
  async init() {
    await this.call("meta", {});
  }
  async call(method, params = {}) {
    let res;
    try {
      res = await fetch(`${this.base}api/rpc`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method, params }),
      });
    } catch (e) {
      throw new EngineError("Cannot reach the SlideRule server: " + e.message, "NETWORK");
    }
    if (!res.ok) throw new EngineError(`Server returned HTTP ${res.status}`, "HTTP", res.status);
    return unwrap(await res.json());
  }
}

export class PyodideEngine {
  constructor(cfg = {}) {
    this.cfg = cfg;
    this.kind = "browser";
    this.label = "In-browser Python (Pyodide)";
    this.pending = new Map();
    this.nextId = 1;
    this.onProgress = () => {};
  }
  init() {
    if (this.ready) return this.ready;
    this.worker = new Worker(new URL("./pyodide-worker.js", import.meta.url));
    this.worker.onmessage = (ev) => {
      const m = ev.data;
      if (m.type === "progress") return this.onProgress(m.message);
      const p = this.pending.get(m.id);
      if (!p) return;
      this.pending.delete(m.id);
      m.error ? p.reject(new EngineError(m.error, "WORKER")) : p.resolve(m.result);
    };
    this.worker.onerror = (ev) => {
      const err = new EngineError("Python worker failed: " + (ev.message || "unknown error"), "WORKER");
      for (const p of this.pending.values()) p.reject(err);
      this.pending.clear();
    };
    this.ready = this._send({ type: "init", cfg: this.cfg });
    return this.ready;
  }
  _send(msg) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ ...msg, id });
    });
  }
  async call(method, params = {}) {
    await this.init();
    const text = await this._send({ type: "call", method, params: JSON.stringify(params) });
    return unwrap(JSON.parse(text));
  }
}

export async function createEngine(cfg = {}, onProgress = () => {}) {
  const mode = cfg.engine || "auto";
  if (mode !== "pyodide") {
    try {
      const http = new HttpEngine(cfg.apiBase || "");
      await http.init();
      return http;
    } catch (e) {
      if (mode === "http") throw e;
    }
  }
  const py = new PyodideEngine(cfg.pyodide || {});
  py.onProgress = onProgress;
  await py.init();
  return py;
}
