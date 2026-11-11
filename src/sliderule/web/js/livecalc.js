// LiveCalc: a unit-aware scratchpad. What you type is evaluated by the Python engine (`livecalc_eval`) on every keystroke and
// shown as Markdown with maths; Enter adds it to the history (the last 200 entries are kept; sessions can be saved, exported and imported). Variables carry from one entry
// to the next. A typed equation can be sent to the "My equations" editor.
import { clear, debounce, h, math, store } from "./dom.js";
import { flash } from "./steps.js";
import { renderMarkdown } from "./markdown.js";
import { surfacePlot, xyPlot } from "./plot.js";

export const MAX_ENTRIES = 200;

const EXAMPLES = [
  ["Units", "5 m + 30 cm"],
  ["Convert", "120 km/h to m/s"],
  ["Variables", "m = 80 kg\na = 9.81 m/s^2\nF = m*a"],
  ["Function", "f(x) = 3*x^2 - 2\nf(4)"],
  ["Graph", "plot sin(x), cos(x) from 0 to 2*pi"],
  ["Equation", "v^2 = u^2 + 2*a*s"],
  ["Note", "# Beam check\nSpan **6 m**, load $w$ in kN/m"],
];

const MAX_PINNED = 4;
function loadPinned() {
  const raw = store("livePinned");
  return (Array.isArray(raw) ? raw : []).filter((x) => x && typeof x.key === "string" && typeof x.src === "string" && x.plot && Array.isArray(x.plot.x) && Array.isArray(x.plot.series)).slice(0, MAX_PINNED);
}

export function initLiveCalc(root, ctx) {
  const { call, S } = ctx;
  const L = {
    entries: (Array.isArray(store("liveEntries")) ? store("liveEntries") : []).filter((e) => typeof e === "string").slice(-MAX_ENTRIES),
    showSteps: store("liveSteps") === true,
    res: null,
    seq: 0,
    histDirty: true,
    stick: true,
    plotted: (Array.isArray(store("livePlotted")) ? store("livePlotted") : []).filter((n) => typeof n === "string").slice(0, 6),
    range: { x: ["-10", "10"], y: ["-10", "10"], ...(store("livePlotRange") || {}) },
    catalog: null,
    angle: store("liveAngle") === "deg" ? "deg" : "rad",      // how a bare number is read by sin, cos, tan (and what asin, acos, atan answer in)
    pinned: loadPinned(),                          // graphs kept in view above the history, as snapshots: [{ key, src, plot }]
    side: store("livePlotSide") === true,          // plots in a column on the right instead of inside the history
    sessions: (Array.isArray(store("liveSessions")) ? store("liveSessions") : []).filter((x) => x && typeof x.name === "string" && Array.isArray(x.entries)).slice(0, 50),
  };

  // ------------------------------------------------------------------ rendering one result line
  const stepsView = (steps) =>
    h("ol", { class: "live-steps" }, steps.map((s) =>
      h("li", {}, h("span", { class: "live-step-label" }, s.label),
        ...[].concat(s.latex).map((t) => h("div", { class: "live-step-math" }, math(t, true))))));

  /** The box that adds a function of one value (a curve) or two (a surface) to the combined plot. */
  function plotBox(r) {
    const dims = r.params.length;
    const box = h("input", { type: "checkbox", checked: L.plotted.includes(r.name), dataset: { fn: r.name },
      "aria-label": `Add ${r.name} to the ${dims === 1 ? "2D" : "3D"} plot`,
      onchange: (e) => togglePlotted(r.name, e.target.checked) });
    return h("label", { class: "live-plotbox", title: dims === 1 ? `Add ${r.name} as a curve to the plot` : `Add ${r.name} as a surface to the 3D plot` }, box, dims === 1 ? "2D plot" : "3D plot");
  }

  // ---- pinned graphs: a copy of a graph that stays above the history while you keep working
  const pinKey = (r) => `${r.text.trim()}|${r.plot.x.length}|${r.plot.series[0]?.y?.[0] ?? ""}`;
  const isPinned = (r) => L.pinned.some((x) => x.key === pinKey(r));
  function pinButton(r) {
    const on = isPinned(r);
    return h("button", { type: "button", class: "btn small live-pin", "aria-pressed": String(on), title: on ? "Unpin this graph" : "Keep a copy of this graph in view above the history", onclick: () => togglePin(r) }, on ? "📌 Pinned" : "📌 Pin");
  }
  function togglePin(r) {
    const key = pinKey(r);
    if (isPinned(r)) L.pinned = L.pinned.filter((x) => x.key !== key);
    else {
      if (L.pinned.length >= MAX_PINNED) { flash(`At most ${MAX_PINNED} pinned graphs: unpin one first`); return; }
      L.pinned = [...L.pinned, { key, src: r.text.trim().slice(0, 120), plot: r.plot }];
    }
    store("livePinned", L.pinned);
    L.histDirty = true;
    L.stick = false;
    renderPinned();
    renderHistory();
    renderGraphs();
  }

  function lineView(r, inHistory = true) {
    const el = h("div", { class: `live-line k-${r.kind}`, dataset: { src: r.text } });
    if (r.kind === "error") {
      el.append(h("div", { class: "live-error" }, h("code", {}, r.text.trim()), h("span", {}, r.error.message)));
      return el;
    }
    if (r.kind === "plot" && L.side) {
      el.append(h("div", { class: "live-math" }, math(r.display_latex, false)), h("div", { class: "live-note" }, "Graph shown in the plot column on the right"));
    } else if (r.kind === "plot") {
      el.append(xyPlot(r.plot), pinButton(r));
    } else {
      el.append(h("div", { class: "live-math" }, math(r.display_latex, false)));
    }
    if (r.kind === "function" && inHistory && [1, 2].includes(r.params?.length)) el.append(plotBox(r));
    if (r.formula && r.text.includes("=")) {
      el.append(h("button", { type: "button", class: "link-btn live-send", title: "Send this equation to My equations", onclick: () => sendToMine(r.text) }, "→ My equations"));
    }
    for (const n of r.notes || []) el.append(h("div", { class: "live-note" }, n));
    if (L.showSteps && r.steps?.length) el.append(stepsView(r.steps));
    return el;
  }

  /** Consecutive text lines become one Markdown block; every calculation line is its own row. */
  function blocksOf(lines, inHistory = true) {
    const out = [];
    let buf = [];
    const flush = () => {
      if (buf.some((l) => l.trim())) out.push(renderMarkdown(buf.join("\n")));
      buf = [];
    };
    for (const r of lines) {
      if (r.kind === "text" || r.kind === "blank") buf.push(r.kind === "blank" ? "" : r.text);
      else { flush(); out.push(lineView(r, inHistory)); }
    }
    flush();
    return out;
  }

  // ------------------------------------------------------------------ the window
  const historyEl = h("div", { class: "live-window", role: "log", "aria-live": "polite", "aria-label": "Calculation history", tabindex: "0" });
  const previewEl = h("div", { class: "live-preview", "aria-label": "Preview of what you are typing" });
  const varsEl = h("details", { class: "live-vars" });
  const countEl = h("span", { class: "live-count" });
  const input = h("textarea", {
    class: "field live-input", rows: 1, spellcheck: false, autocomplete: "off", "aria-label": "Type a calculation, an equation, a graph or a note",
    placeholder: "Type a calculation, equation, graph or note — Enter adds it to the history",
    oninput: () => { autosize(); refreshSoon(); },
    onkeydown: (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); commit(); }
      else if (e.key === "Escape") { input.value = ""; autosize(); refresh(); }
      else if (e.key === "ArrowUp" && !input.value && L.entries.length) { e.preventDefault(); recall(L.entries.length - 1, false); }
    },
  });

  function autosize() {
    input.rows = Math.min(8, Math.max(1, input.value.split("\n").length));
  }

  function renderHistory() {
    clear(historyEl);
    countEl.textContent = `${L.entries.length} of ${MAX_ENTRIES} entries kept`;
    if (!L.entries.length) {
      historyEl.append(h("p", { class: "live-empty" }, "Your calculations appear here, newest at the bottom. The last ", String(MAX_ENTRIES), " are kept in this browser."));
      return;
    }
    const entries = L.res?.entries || [];
    L.entries.forEach((text, i) => {
      const e = entries[i];
      historyEl.append(h("article", { class: "live-entry" },
        h("div", { class: "live-entry-body" }, ...(e ? blocksOf(e.lines) : [h("code", {}, text)])),
        h("div", { class: "live-entry-actions" },
          h("button", { type: "button", class: "icon-btn small", title: "Put this entry back in the input box to edit it", "aria-label": "Edit this entry", onclick: () => recall(i, false) }, "↺"),
          h("button", { type: "button", class: "icon-btn small", title: "Remove this entry (later entries are re-evaluated without it)", "aria-label": "Remove this entry", onclick: () => remove(i) }, "×"))));
    });
    L.histDirty = false;
    if (L.stick) historyEl.scrollTop = historyEl.scrollHeight;
    L.stick = false;
  }

  function renderPreview(error) {
    clear(previewEl);
    previewEl.classList.toggle("empty", !input.value.trim());
    if (error) { previewEl.append(h("div", { class: "live-error" }, h("span", {}, error))); return; }
    if (!input.value.trim()) {
      previewEl.append(h("div", { class: "live-hint" },
        h("span", {}, "Try: "),
        ...EXAMPLES.map(([name, text]) => h("button", { type: "button", class: "chip", title: text, onclick: () => { input.value = text; autosize(); input.focus(); refresh(); } }, name))));
      return;
    }
    previewEl.append(h("div", { class: "live-preview-label" }, "Preview — Enter adds it to the history"), ...blocksOf(L.res?.draft.lines || [], false));
  }

  function renderVars() {
    const vars = (L.res?.variables || []).filter((v) => v.name !== "ans");
    clear(varsEl);
    varsEl.hidden = !vars.length;
    if (!vars.length) return;
    varsEl.append(h("summary", {}, `Variables and functions (${vars.length})`),
      h("div", { class: "chips" }, vars.map((v) =>
        h("button", { type: "button", class: "chip live-var", title: `Insert ${v.name}`, onclick: () => { insert(v.function ? v.name.split("(")[0] : v.name); } },
          math(v.function ? `${v.latex}` : `${v.latex} = ${v.result_latex}`)))));
  }

  function insert(text) {
    const a = input.selectionStart ?? input.value.length, b = input.selectionEnd ?? a;
    input.setRangeText(text, a, b, "end");
    autosize();
    input.focus();
    refreshSoon();
  }

  // ------------------------------------------------------------------ evaluation
  async function refresh() {
    const seq = ++L.seq;
    let res;
    try {
      res = await call("livecalc_eval", { entries: L.entries, draft: input.value, angle: L.angle });
    } catch (e) {
      if (seq === L.seq) renderPreview(e.message);
      return;
    }
    if (seq !== L.seq) return;
    L.res = res;
    if (L.histDirty) renderHistory();
    renderPreview();
    renderVars();
    renderGraphs();
    if (L.plotted.length && plotKey() !== L.plotKey) { renderPlotFrame(); refreshPlotSoon(); }
    if (!funcPanel.hidden) renderFuncs();
  }
  const refreshSoon = debounce(refresh, 140);

  function commit() {
    const text = input.value.replace(/\s+$/, "").replace(/^\n+/, "");
    if (!text.trim()) return;
    L.entries.push(text);
    if (L.entries.length > MAX_ENTRIES) L.entries.splice(0, L.entries.length - MAX_ENTRIES);
    store("liveEntries", L.entries);
    input.value = "";
    autosize();
    L.histDirty = true;
    L.stick = true;
    refresh();
  }

  function recall(i, removeIt) {
    input.value = L.entries[i];
    if (removeIt) remove(i);
    autosize();
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
    refresh();
  }

  function remove(i) {
    L.entries.splice(i, 1);
    store("liveEntries", L.entries);
    L.histDirty = true;
    refresh();
  }

  function clearHistory() {
    if (L.entries.length && !confirm(`Remove all ${L.entries.length} entries from the history? Variables defined in them are forgotten.`)) return;
    L.entries = [];
    store("liveEntries", L.entries);
    L.histDirty = true;
    refresh();
  }

  // ------------------------------------------------------------------ saved sessions, export and import
  const saveSessions = () => store("liveSessions", L.sessions);

  function saveSession() {
    if (!L.entries.length) { flash("There is nothing to save yet"); return; }
    const name = (prompt("Name for this session:", L.sessionName || `Session ${L.sessions.length + 1}`) || "").trim().slice(0, 60);
    if (!name) return;
    const at = L.sessions.findIndex((x) => x.name === name);
    if (at >= 0 && !confirm(`A session called “${name}” exists. Replace it?`)) return;
    const rec = { name, entries: [...L.entries], angle: L.angle, saved: new Date().toISOString() };
    if (at >= 0) L.sessions[at] = rec; else L.sessions.unshift(rec);
    L.sessions = L.sessions.slice(0, 50);
    L.sessionName = name;
    saveSessions();
    renderSessions();
    flash(`Saved “${name}” (${rec.entries.length} entries)`);
  }

  function loadSession(name) {
    const rec = L.sessions.find((x) => x.name === name);
    if (!rec) return;
    const saved = L.sessions.some((x) => JSON.stringify(x.entries) === JSON.stringify(L.entries));
    if (L.entries.length && !saved && !confirm("The current history is not saved as a session and will be replaced. Continue?")) return;
    L.entries = rec.entries.filter((e) => typeof e === "string").slice(-MAX_ENTRIES);
    L.sessionName = rec.name;
    if (rec.angle) setAngle(rec.angle, false);
    store("liveEntries", L.entries);
    L.histDirty = true;
    L.stick = true;
    L.plotted = [];
    store("livePlotted", L.plotted);
    renderPlotFrame();
    refresh();
  }

  function deleteSession(name) {
    if (!confirm(`Delete the saved session “${name}”?`)) return;
    L.sessions = L.sessions.filter((x) => x.name !== name);
    if (L.sessionName === name) L.sessionName = "";
    saveSessions();
    renderSessions();
  }

  function saveFile(name, text, type) {
    const a = h("a", { href: URL.createObjectURL(new Blob([text], { type })), download: name });
    document.body.append(a);
    a.click();
    a.remove();
  }

  async function exportHistory(fmt) {
    if (!L.entries.length) { flash("There is nothing to export yet"); return; }
    try {
      if (fmt === "json") {
        saveFile("livecalc-session.json", JSON.stringify({ livecalc: 1, name: L.sessionName || "", angle: L.angle, entries: L.entries }, null, 2) + "\n", "application/json");
        return;
      }
      const r = await call("livecalc_export", { entries: L.entries, fmt, title: L.sessionName || "LiveCalc session", angle: L.angle, steps: !!L.showSteps && fmt === "markdown" });
      saveFile(r.filename, r.content, fmt === "markdown" ? "text/markdown" : fmt === "notebook" ? "application/x-ipynb+json" : fmt === "python" ? "text/x-python" : "text/plain");
    } catch (e) { flash(e.message); }
  }

  async function copyHistory() {
    if (!L.entries.length) { flash("There is nothing to copy yet"); return; }
    try {
      const r = await call("livecalc_export", { entries: L.entries, fmt: "markdown", title: L.sessionName || "LiveCalc session", angle: L.angle, steps: !!L.showSteps });
      await navigator.clipboard.writeText(r.content);
      flash("Copied the history as Markdown");
    } catch (e) { flash(e.message); }
  }

  /** A .json file written by Export, or a plain text file (entries separated by blank lines). */
  async function importFile(file) {
    if (!file) return;
    if (file.size > 500000) { flash("That file is too large for LiveCalc (500 kB at most)"); return; }
    const text = await file.text();
    let entries;
    try {
      const doc = JSON.parse(text);
      entries = Array.isArray(doc) ? doc : doc.entries;
      if (!Array.isArray(doc) && (doc.angle === "deg" || doc.angle === "rad") && !L.entries.length) setAngle(doc.angle, false);
    } catch { entries = text.replace(/\r\n/g, "\n").split(/\n\s*\n/).map((x) => x.trim()).filter(Boolean); }
    entries = (entries || []).filter((e) => typeof e === "string" && e.trim()).map((e) => e.slice(0, 20000));
    if (!entries.length) { flash("No entries found in that file"); return; }
    if (L.entries.length && !confirm(`Add ${entries.length} imported entries after the ${L.entries.length} already in the history?`)) return;
    L.entries = [...L.entries, ...entries].slice(-MAX_ENTRIES);
    store("liveEntries", L.entries);
    L.histDirty = true;
    L.stick = true;
    refresh();
    flash(`Imported ${entries.length} entries`);
  }

  const sessionsEl = h("details", { class: "live-sessions" });
  document.addEventListener("click", (e) => { if (sessionsEl.open && !sessionsEl.contains(e.target)) sessionsEl.open = false; });
  sessionsEl.addEventListener("keydown", (e) => { if (e.key === "Escape") { sessionsEl.open = false; sessionsEl.querySelector("summary").focus(); } });
  function renderSessions() {
    clear(sessionsEl);
    sessionsEl.append(h("summary", {}, L.sessions.length ? `Sessions (${L.sessions.length})` : "Sessions"),
      h("div", { class: "live-sessions-body" },
        h("div", { class: "live-sessions-actions" },
          h("button", { type: "button", class: "btn small", title: "Keep the current history under a name, to open again later", onclick: saveSession }, "Save…"),
          h("button", { type: "button", class: "btn small", title: "Download the history with its results as a Markdown document (with the worked steps when Show steps is on)", onclick: () => exportHistory("markdown") }, "Markdown"),
          h("button", { type: "button", class: "btn small", title: "Download the entries exactly as typed; LiveCalc can import this file", onclick: () => exportHistory("text") }, "Text"),
          h("button", { type: "button", class: "btn small", title: "Download the history as a JSON file", onclick: () => exportHistory("json") }, "JSON"),
          h("button", { type: "button", class: "btn small", title: "Download a Python script that re-runs this session with SlideRule's evaluator", onclick: () => exportHistory("python") }, "Python"),
          h("button", { type: "button", class: "btn small", title: "Download a Jupyter notebook that re-runs this session, with the results saved in it", onclick: () => exportHistory("notebook") }, "Notebook"),
          h("button", { type: "button", class: "btn small", title: "Copy the history with its results as Markdown", onclick: copyHistory }, "Copy"),
          h("label", { class: "btn small", title: "Add the entries of a .json or .txt file to the history" }, "Import…", h("input", { type: "file", accept: ".json,.txt,.md,text/plain,application/json", hidden: true, onchange: (e) => { importFile(e.target.files[0]); e.target.value = ""; } }))),
        L.sessions.length ? h("ul", { class: "live-session-list" }, L.sessions.map((x) => h("li", {},
          h("button", { type: "button", class: "link-btn", title: "Open this session (replaces the current history)", onclick: () => loadSession(x.name) }, x.name),
          h("span", { class: "live-session-meta" }, ` ${x.entries.length} entries · ${(x.saved || "").slice(0, 10)}`),
          h("button", { type: "button", class: "icon-btn small", title: "Delete this saved session", "aria-label": `Delete session ${x.name}`, onclick: () => deleteSession(x.name) }, "×")))) : h("p", { class: "live-empty" }, "No saved sessions yet. The history itself is always kept in this browser; a session is a named copy you can come back to.")));
  }

  // ------------------------------------------------------------------ send an equation to My equations
  /** The text the user has selected: in the input box, or in the history/preview (the typed source of the lines it touches). */
  function selectedText() {
    const sel = window.getSelection();
    if (sel && sel.rangeCount && !sel.isCollapsed) {
      const range = sel.getRangeAt(0);
      const lines = [...root.querySelectorAll(".live-line[data-src]")].filter((el) => range.intersectsNode(el)).map((el) => el.dataset.src);
      if (lines.length) return lines.join("\n");
    }
    if (input.selectionStart !== input.selectionEnd) return input.value.slice(input.selectionStart, input.selectionEnd);
    return "";
  }

  function caretLine() {
    const pos = input.selectionStart ?? 0;
    const before = input.value.slice(0, pos).split("\n").length - 1;
    return input.value.split("\n")[before] || "";
  }

  async function sendSelection() {
    let text = selectedText();
    let candidates = text.split("\n").filter((l) => l.includes("="));
    if (!candidates.length) candidates = caretLine().includes("=") ? [caretLine()] : [];
    if (!candidates.length) { flash("Select an equation first (for example F = m*a), or put the cursor on its line"); return; }
    if (candidates.length > 1) { flash("Select just one equation"); return; }
    await sendToMine(candidates[0]);
  }

  async function sendToMine(text) {
    try {
      const res = await call("livecalc_to_equation", { text: text.trim(), entries: [...L.entries, input.value], angle: L.angle });
      S.customDraft = { calculation: res.calculation, warnings: res.warnings, from: text.trim() };
      location.hash = "#/mine/new?draft=1";
    } catch (e) {
      flash(e.message);
    }
  }

  // ------------------------------------------------------------------ the combined plot of the checked functions
  const graphsEl = h("section", { class: "panel live-graphs", hidden: true, "aria-label": "Graphs from plot commands" });
  const plotEl = h("section", { class: "panel live-plot", hidden: true, "aria-label": "Plot of the functions ticked in the history" });
  let plotSeq = 0;
  const plotKey = () => JSON.stringify([L.entries, L.plotted, L.range, L.angle]);

  function togglePlotted(name, on) {
    L.plotted = L.plotted.filter((n) => n !== name);
    if (on) {
      if (L.plotted.length >= 6) { flash("A plot can show at most 6 functions"); }
      else L.plotted.push(name);
    }
    store("livePlotted", L.plotted);
    for (const box of root.querySelectorAll(".live-plotbox input")) box.checked = L.plotted.includes(box.dataset.fn);
    renderPlotFrame();
    refreshPlot();
  }

  const rangeInput = (axis, i) => {
    const el = h("input", { type: "text", class: "range", value: L.range[axis][i], "aria-label": `${axis} range ${i ? "end" : "start"}`, placeholder: i ? "10" : "-10", size: 8 });
    el.addEventListener("input", () => { L.range[axis][i] = el.value; store("livePlotRange", L.range); refreshPlotSoon(); });
    return el;
  };
  const paramsOf = (name) => (L.res?.variables || []).find((v) => v.function && v.name.split("(")[0] === name)?.name.replace(/^[^(]*\(|\)$/g, "").split(",").map((x) => x.trim()) || [];

  /** The header of the plot panel (chips, ranges); the figures are filled in by refreshPlot. */
  function renderPlotFrame() {
    const names = L.plotted;
    plotEl.hidden = !names.length;
    if (!names.length) { clear(plotEl); plotEl.dataset.frame = ""; return; }
    const has3 = names.some((n) => paramsOf(n).length === 2), has2 = names.some((n) => paramsOf(n).length === 1);
    const frame = JSON.stringify([names, names.map((n) => paramsOf(n).length)]);
    if (plotEl.dataset.frame === frame) return;                  // unchanged: keep the range boxes (and their focus) and the figures
    plotEl.dataset.frame = frame;
    const prev = plotEl.querySelector(".live-plot-figs");
    clear(plotEl);
    plotEl.append(
      h("div", { class: "live-plot-head" },
        h("h3", {}, "Plot"),
        h("div", { class: "chips" }, names.map((n) => h("span", { class: "chip live-plotted" }, `${n}(${paramsOf(n).join(", ")})`,
          h("button", { type: "button", class: "icon-btn small", "aria-label": `Remove ${n} from the plot`, title: "Remove from the plot", onclick: () => togglePlotted(n, false) }, "×"))))),
      h("div", { class: "live-ranges" },
        h("label", {}, h("span", {}, has3 && !has2 ? "x (first value)" : has3 ? "x (first value) from" : "x from"), rangeInput("x", 0), h("span", {}, "to"), rangeInput("x", 1)),
        has3 ? h("label", {}, h("span", {}, "y (second value) from"), rangeInput("y", 0), h("span", {}, "to"), rangeInput("y", 1)) : null,
        h("span", { class: "live-hint-text" }, "Give a range a unit if the function needs one, e.g. 0 s")),
      prev || h("div", { class: "live-plot-figs" }));
  }

  async function refreshPlot() {
    if (!L.plotted.length) return;
    const seq = ++plotSeq;
    L.plotKey = plotKey();
    let res;
    try { res = await call("livecalc_plot", { entries: L.entries, functions: L.plotted, x: L.range.x, y: L.range.y, angle: L.angle }); } catch (e) { res = { curves: [], surfaces: [], errors: [{ name: "", message: e.message }] }; }
    if (seq !== plotSeq) return;
    renderPlotFrame();
    const figs = plotEl.querySelector(".live-plot-figs");
    clear(figs);
    for (const c of res.curves) figs.append(xyPlot(c));
    for (const g of res.surfaces) figs.append(surfacePlot(g));
    for (const e of res.errors) figs.append(h("div", { class: "live-error" }, e.name ? h("code", {}, e.name) : null, h("span", {}, e.message)));
  }
  const refreshPlotSoon = debounce(refreshPlot, 250);

  /** With the plots on the right: the graphs of every `plot` command in the history (newest first) and of the line being typed. */
  function renderGraphs() {
    clear(graphsEl);
    const figsOf = (lines, label, preview) => lines.filter((r) => r.kind === "plot").map((r) => h("div", { class: `live-graph${preview ? " preview" : ""}` },
      h("div", { class: "live-graph-src" }, preview ? "Preview, not in the history yet" : `Entry ${label}`, h("code", {}, r.text.trim().slice(0, 80)), preview ? null : pinButton(r)), xyPlot(r.plot)));
    const done = (L.res?.entries || []).flatMap((e, i) => figsOf(e.lines, i + 1, false)).reverse();
    const figs = [...figsOf(L.res?.draft?.lines || [], 0, true), ...done];
    graphsEl.hidden = !L.side || !figs.length;
    if (!graphsEl.hidden) graphsEl.append(h("h3", {}, "Graphs"), ...figs);
  }

  // ------------------------------------------------------------------ search for functions
  const funcInput = h("input", { type: "search", class: "field live-func-search", placeholder: "Search functions, constants, commands and library calculations — sqrt, angle, wind…", "aria-label": "Search the functions LiveCalc offers",
    oninput: () => { if (funcInput.value.trim()) renderFuncs(true); else { funcPanel.hidden = true; browseBtn.setAttribute("aria-expanded", "false"); } }, onfocus: () => { if (funcInput.value.trim()) renderFuncs(true); },
    onkeydown: (e) => { if (e.key === "Escape") { funcInput.value = ""; funcPanel.hidden = true; } } });
  const funcPanel = h("div", { class: "live-funcs", hidden: true, role: "region", "aria-label": "Functions and examples" });
  const browseBtn = h("button", { type: "button", class: "btn", "aria-expanded": "false", onclick: () => { if (funcPanel.hidden) { funcInput.value = ""; renderFuncs(true); } else { funcPanel.hidden = true; } browseBtn.setAttribute("aria-expanded", String(!funcPanel.hidden)); } }, "Browse all");

  /** Use an example: it replaces an empty input box, otherwise it goes on a new line below what is typed. */
  function useExample(text) {
    input.value = input.value.trim() ? `${input.value.replace(/\s+$/, "")}\n${text}` : text;
    autosize();
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
    refresh();
  }

  /** Insert a command with nothing filled in; the cursor lands at `caret` (an offset in the inserted text) ready to type the values. */
  function useTemplate(text, caret = text.length) {
    const had = input.value.trim();
    const start = had ? input.value.replace(/\s+$/, "").length + 1 : 0;
    input.value = had ? `${input.value.replace(/\s+$/, "")}\n${text}` : text;
    autosize();
    input.focus();
    input.setSelectionRange(start + caret, start + caret);
    refresh();
  }

  /** The small button of a catalogue row: put the command in the input box with nothing filled in. */
  const insertButton = (text, caret, title) => h("button", { type: "button", class: "btn small live-insert", title, onclick: () => useTemplate(text, caret) }, "Insert");

  /** One catalogue row: only the signature (and badge) show; More opens the description and examples. */
  function foldEntry(sig, badge, insert, body) {
    const bodyEl = h("div", { class: "live-func-body", hidden: true }, ...body);
    const more = h("button", { type: "button", class: "btn small live-more", "aria-expanded": "false", title: "Show what it does and examples", onclick: () => {
      const open = bodyEl.hidden;
      bodyEl.hidden = !open;
      more.setAttribute("aria-expanded", String(open));
      more.textContent = open ? "Less" : "More";
    } }, "More");
    return h("article", { class: "live-func" }, h("div", { class: "live-func-head" }, sig, badge, h("span", { class: "live-func-spacer" }), insert, more), bodyEl);
  }

  function userFunctionItems() {
    return (L.res?.variables || []).filter((v) => v.function).map((v) => {
      const name = v.name.split("(")[0], params = v.name.replace(/^[^(]*\(|\)$/g, "").split(",").map((x) => x.trim());
      const call_ = `${name}(${params.map((_, i) => i + 1).join(", ")})`;
      return { name, kind: "yours", category: "Your functions", signature: v.name, summary: "", math: `${v.latex} = ${v.result_latex}`, keywords: "defined history custom yours",
        examples: [{ text: call_, ok: true, result_text: "" }], plot: params.length };
    });
  }

  async function renderFuncs(open) {
    if (open) funcPanel.hidden = false;
    if (funcPanel.hidden) return;
    browseBtn.setAttribute("aria-expanded", "true");
    if (!L.catalog) {
      clear(funcPanel).append(h("p", { class: "live-empty" }, "Loading…"));
      try { L.catalog = await call("livecalc_functions", {}); } catch (e) { clear(funcPanel).append(h("p", { class: "live-error" }, e.message)); return; }
    }
    const q = funcInput.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const items = [...userFunctionItems(), ...L.catalog.items].filter((it) => {
      const hay = `${it.name} ${it.signature} ${it.summary} ${it.keywords} ${it.category} ${it.kind}`.toLowerCase();
      return q.every((w) => hay.includes(w));
    });
    clear(funcPanel);
    const libSlot = h("div", { class: "live-library" });
    if (!items.length) funcPanel.append(h("p", { class: "live-empty" }, `No function matches “${funcInput.value}”. Try a word like angle, root, log or convert.`));
    if (items.length) funcPanel.append(h("p", { class: "live-func-count" }, `${items.length} match${items.length === 1 ? "" : "es"} — Insert puts the command in the input box, More shows what it does and examples`));
    let last = "";
    for (const it of items) {
      if (it.category !== last) { funcPanel.append(h("h4", {}, it.category)); last = it.category; }
      const insertText = it.kind === "function" || it.kind === "yours" ? `${it.name}()` : it.kind === "constant" ? it.name : "";
      funcPanel.append(foldEntry(
        h("code", { class: "sig" }, it.signature), h("span", { class: `badge ${it.kind}` }, it.kind === "yours" ? "yours" : it.kind),
        insertText ? insertButton(insertText, it.kind === "constant" ? insertText.length : it.name.length + 1, it.kind === "constant" ? `Put ${it.name} in the input box` : `Insert ${it.name}() with the brackets empty, ready for your values`) : null,
        [it.math ? h("div", { class: "live-func-math" }, math(it.math, false)) : h("p", { class: "desc" }, it.summary),
          it.plot ? h("p", { class: "desc" }, it.plot === 1 ? "Tick ‘2D plot’ beside its definition in the history to draw it." : it.plot === 2 ? "Tick ‘3D plot’ beside its definition in the history to draw it as a surface." : "") :
            h("div", { class: "live-func-examples" }, it.examples.map((e) => h("button", {
              type: "button", class: `live-example${e.ok ? "" : " bad"}`, title: "Put this example in the input box", onclick: () => useExample(e.text),
            }, h("code", {}, e.text.replace(/\n/g, "  ⏎  ")), e.result_text ? h("span", { class: "res" }, ` → ${e.result_text}`) : null)))]));
    }
    funcPanel.append(libSlot);
    loadLibrary(libSlot, funcInput.value.trim());
  }

  /** calc("id", "out", a = , b = ): every input named, no value given; the cursor goes after the first ‘= ’. */
  function libraryInsert(it) {
    const head = `calc("${it.id}", "${it.outputs[0]?.key || ""}", `;
    const names = it.inputs.map((v) => `${v.key} = `);
    return insertButton(`${head}${names.join(", ")})`, head.length + (names[0] || "").length, "Insert the call with every input named and no value given; the cursor lands at the first value");
  }

  /** Library calculations matching the search words, each with a ready-to-run calc(...) line (the example has been run by the engine). */
  let libSeq = 0;
  async function loadLibrary(slot, query) {
    if (query.length < 2) return;
    const seq = ++libSeq;
    slot.append(h("p", { class: "live-func-count" }, "Searching the library…"));
    let res;
    try { res = await call("livecalc_library", { query, limit: 8 }); } catch (e) { if (seq === libSeq) { clear(slot).append(h("p", { class: "live-error" }, e.message)); } return; }
    if (seq !== libSeq) return;
    clear(slot);
    if (!res.items.length) { slot.append(h("p", { class: "live-empty" }, `No library calculation matches “${query}”.`)); return; }
    slot.append(h("h4", {}, "Library calculations"), h("p", { class: "live-func-count" }, `${res.total} match${res.total === 1 ? "" : "es"}${res.total > res.items.length ? `, the best ${res.items.length} shown` : ""} — use calc("id", "output", name = value, …); a list for an input gives a list of results`));
    for (const it of res.items) {
      slot.append(foldEntry(
        h("code", { class: "sig" }, it.name), h("span", { class: "badge function" }, it.id), libraryInsert(it),
        [h("p", { class: "desc" }, it.description),
          h("p", { class: "desc" }, h("b", {}, "Inputs: "), it.inputs.map((v) => `${v.key} (${v.label}, ${v.unit})`).join("; "), h("br"), h("b", {}, "Outputs: "), it.outputs.map((v) => `${v.key} (${v.label}, ${v.unit})`).join("; ")),
          h("div", { class: "live-func-examples" }, h("button", { type: "button", class: `live-example${it.ok ? "" : " bad"}`, title: "Put this example in the input box", onclick: () => useExample(it.example) },
            h("code", {}, it.example), it.ok ? h("span", { class: "res" }, ` → ${it.result_text}`) : h("span", { class: "res" }, ` — ${it.error}`)))]));
    }
  }

  const pinnedEl = h("section", { class: "panel live-pinned", hidden: true, "aria-label": "Pinned graphs" });
  function renderPinned() {
    clear(pinnedEl);
    pinnedEl.hidden = !L.pinned.length;
    if (!L.pinned.length) return;
    pinnedEl.append(h("div", { class: "live-pinned-head" }, h("h3", {}, "Pinned graphs"), h("span", { class: "live-note" }, "snapshots, kept while you work below"),
      h("button", { type: "button", class: "link-btn", onclick: () => { L.pinned = []; store("livePinned", L.pinned); L.histDirty = true; L.stick = false; renderPinned(); renderHistory(); renderGraphs(); } }, "Unpin all")),
      h("details", { class: "live-pinned-fold", open: L.pinnedOpen !== false, ontoggle: (e) => { L.pinnedOpen = e.target.open; } }, h("summary", {}, L.pinned.length === 1 ? "Show the graph" : `Show the ${L.pinned.length} graphs`),
      h("div", { class: "live-pinned-figs" }, L.pinned.map((x) => h("div", { class: "live-pinned-fig" },
        h("div", { class: "live-graph-src" }, h("code", {}, x.src),
          h("button", { type: "button", class: "icon-btn small", "aria-label": `Unpin ${x.src}`, title: "Unpin", onclick: () => { L.pinned = L.pinned.filter((y) => y.key !== x.key); store("livePinned", L.pinned); L.histDirty = true; L.stick = false; renderPinned(); renderHistory(); renderGraphs(); } }, "×")),
        xyPlot(x.plot))))));
  }

  // ------------------------------------------------------------------ layout: plots inside the history, or in a column on the right
  const leftEl = h("div", { class: "live-left" });
  const rightEl = h("div", { class: "live-right" }, graphsEl);
  const bodyEl = h("div", { class: "live-body" }, leftEl, rightEl);
  const layoutBtns = [["inline", "In the history"], ["side", "On the right"]].map(([mode, text]) => h("button", {
    type: "button", "aria-pressed": String((mode === "side") === L.side), title: mode === "side" ? "Keep the history on the left and show every plot in a column on the right" : "Show graphs inside the history, as they were typed",
    onclick: () => setSide(mode === "side"),
  }, text));

  /** Radians or degrees: how a bare number is read by sin, cos and tan, and the unit asin, acos, atan, atan2 and arg answer in. */
  const angleBtns = [["rad", "Radians"], ["deg", "Degrees"]].map(([mode, text]) => h("button", {
    type: "button", "aria-pressed": String(mode === L.angle), dataset: { angle: mode },
    title: mode === "deg" ? "sin(30) is the sine of 30 degrees, and asin(0.5) answers 30 deg" : "sin(pi/6) is the sine of 0.5236 radians, and asin(0.5) answers 0.5236",
    onclick: () => setAngle(mode, true),
  }, text));
  function setAngle(mode, doRefresh) {
    if (mode === L.angle) return;
    L.angle = mode;
    store("liveAngle", mode);
    angleBtns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.angle === mode)));
    L.histDirty = true;
    L.stick = false;
    if (doRefresh) { refresh(); if (L.plotted.length) refreshPlot(); }
  }

  function applyLayout() {
    root.classList.toggle("side", L.side);
    layoutBtns.forEach((b, i) => b.setAttribute("aria-pressed", String((i === 1) === L.side)));
    if (L.side) { rightEl.prepend(plotEl); rightEl.prepend(pinnedEl); }
    else { leftEl.insertBefore(plotEl, historyEl); leftEl.insertBefore(pinnedEl, plotEl); }
  }
  function setSide(on) {
    if (on === L.side) return;
    L.side = on;
    store("livePlotSide", on);
    applyLayout();
    L.histDirty = true;
    L.stick = false;
    renderHistory();
    renderPreview();
    renderGraphs();
  }

  // ------------------------------------------------------------------ page
  const stepsBox = h("input", { type: "checkbox", checked: L.showSteps, onchange: (e) => { L.showSteps = e.target.checked; store("liveSteps", L.showSteps); L.histDirty = true; L.stick = false; renderHistory(); renderPreview(); } });
  root.append(
    h("div", { class: "live" },
      h("div", { class: "panel live-head" },
        h("h2", {}, "LiveCalc"),
        h("div", { class: "live-tools" },
          sessionsEl,
          h("label", { class: "inline", title: "Show the working for every calculation: the expression, the values substituted, what is converted to SI and the result" }, stepsBox, "Show steps"),
          h("button", { type: "button", class: "btn small", title: "Select an equation (in the input box or in the history) and send it to the My equations editor", onmousedown: (e) => e.preventDefault(), onclick: sendSelection }, "Send to My equations"),
          h("button", { type: "button", class: "btn small", onclick: clearHistory }, "Clear history"),
          h("span", { class: "live-layout" }, h("span", { class: "live-layout-label" }, "Angles"), h("span", { class: "seg", role: "group", "aria-label": "How angles are read and shown" }, ...angleBtns)),
          h("span", { class: "live-layout" }, h("span", { class: "live-layout-label" }, "Plots"), h("span", { class: "seg", role: "group", "aria-label": "Where plots are shown" }, ...layoutBtns)),
          countEl)),
      bodyEl));
  const helpEl = h("details", { class: "live-help" }, h("summary", {}, "What can I type?"),
          h("ul", {},
            h("li", {}, h("b", {}, "Calculations with units: "), h("code", {}, "5 m + 30 cm"), ", ", h("code", {}, "3 kN * 2 m"), ", ", h("code", {}, "9.81 m/s^2 * 5 kg"), ". Mismatched units are refused. Convert with ", h("code", {}, "to"), " or ", h("code", {}, "in"), ": ", h("code", {}, "120 km/h to m/s"), "."),
            h("li", {}, h("b", {}, "Variables and functions: "), h("code", {}, "m = 5 kg"), ", then ", h("code", {}, "F = m*a"), "; ", h("code", {}, "f(x) = 3*x^2 - 2"), ", then ", h("code", {}, "f(4)"), ". ", h("code", {}, "ans"), " is the last result. A name right after a number is a unit (", h("code", {}, "5 m"), ") even if you defined a variable ", h("code", {}, "m"), "; multiply with ", h("code", {}, "5*m"), "."),
            h("li", {}, h("b", {}, "Equations: "), "a line such as ", h("code", {}, "F = m*a"), " whose names have no value yet is kept as an equation. Select it and press “Send selection to My equations”; units are taken from the variables you have defined."),
            h("li", {}, h("b", {}, "Graphs: "), h("code", {}, "plot sin(x) from 0 to 2*pi"), ", ", h("code", {}, "plot x^2, x^3"), ", ", h("code", {}, "plot 0.5*m*v^2 for v from 0 m/s to 20 m/s"), " (give the unit of the range to get a labelled axis; name the variable with ", h("code", {}, "for"), " when it could be a unit, like ", h("code", {}, "t"), ")."),
            h("li", {}, h("b", {}, "Text: "), "anything that is not a calculation is Markdown: ", h("code", {}, "# heading"), ", ", h("code", {}, "**bold**"), ", ", h("code", {}, "- list"), ", ", h("code", {}, "> quote"), ", ", h("code", {}, "$\\alpha$"), " maths."),
            h("li", {}, h("b", {}, "Functions: "), h("code", {}, "sqrt cbrt exp ln log log10 log2 sin cos tan asin acos atan atan2 sinh cosh tanh abs min max floor ceil round factorial sum mean median stdev hypot sign mod; lists, matrices, measured data and complex numbers (search ‘list’, ‘matrix’, ‘data’, ‘complex’)"), ", calculus on functions you define ", h("code", {}, "integrate derivative findroot sumover"), ", constants ", h("code", {}, "pi e c0 g0 hP kBoltz NA Rgas qe ..."), " (search for ‘constant’ to see all). Angles: write ", h("code", {}, "30 deg"), "; a plain number is radians. ", h("code", {}, "log"), " is the natural logarithm, as in My equations.")));
  leftEl.append(varsEl, historyEl, previewEl, input, h("div", { class: "live-search" }, h("div", { class: "live-searchrow" }, funcInput, browseBtn), funcPanel, helpEl));
  renderSessions();
  applyLayout();
  renderPinned();
  autosize();

  return {
    onShow() {
      L.stick = true;
      L.histDirty = true;
      refresh();
      input.focus();
    },
  };
}
