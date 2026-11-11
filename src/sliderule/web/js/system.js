// System Design: drag calculations onto a canvas, give each variable a role (input / output / constant) and wire
// outputs to inputs of the same physical type. Evaluation, type rules and structural checks live in the Python engine
// (sliderule.design); this file is the editor.
import { clear, debounce, h, math, store } from "./dom.js";
import { flash, stepsPanel } from "./steps.js";
import { unitPicker } from "./widgets.js";

const GRID = 10;
const NODE_W = 270;
const ROLE_LABEL = { input: "Input", output: "Output", constant: "Const" };
const MATH_OPS = [
  { op: "add", sym: "+", name: "Add", hint: "Adds its inputs. All ports lock to the type of the first wire connected; with no wire the block accepts anything again." },
  { op: "sub", sym: "−", name: "Subtract", hint: "Subtracts the second input from the first. Locks to the type of the first wire connected." },
  { op: "mul", sym: "×", name: "Multiply", hint: "Multiplies its inputs; the units multiply as well (N · m = J) and cancel where they can." },
  { op: "div", sym: "÷", name: "Divide", hint: "Divides the first input by the second; the units divide as well (m / s = velocity, N / N = dimensionless)." },
];
const OPEN_TYPE = { key: "any", kind: "any type", si: "", open: true };

const hueOf = (key) => {
  let x = 7;
  for (const c of key) x = (x * 31 + c.charCodeAt(0)) >>> 0;
  return x % 360;
};
const typeColor = (key) => (key === "any" ? "hsl(0 0% var(--port-grey))" : `hsl(${hueOf(key)} 65% var(--port-l))`);      // lightness set by the theme so every hue keeps 3:1 against the canvas
const splitQty = (t) => {
  const m = String(t ?? "").match(/^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*?)\s*$/);
  return m ? { value: m[1], unit: m[2] } : { value: "", unit: "" };
};

export async function initSystemDesign(root, ctx) {
  const { call, state } = ctx;
  const D = {
    blocks: [], wires: [], details: new Map(), sel: null, results: null, view: { x: 40, y: 30, k: 1 },
    seq: 1, auto: store("designAuto") !== false, examples: [], math: {}, multi: new Set(), clip: null,
  };

  // ------------------------------------------------------------------ skeleton
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "wires");
  const nodesEl = h("div", { class: "nodes" });
  const world = h("div", { class: "world" }, svg, nodesEl);
  const empty = h("div", { class: "canvas-empty" });
  const canvas = h("div", { class: "canvas", tabindex: "0", "aria-label": "System canvas" }, world, empty);

  const exSel = h("select", { "aria-label": "Load an example system", onchange: (e) => { const x = D.examples.find((q) => q.id === e.target.value); e.target.value = ""; if (x) loadGraph(x.graph); } },
    h("option", { value: "" }, "Examples…"));
  const autoBox = h("input", { type: "checkbox", checked: D.auto, onchange: (e) => { D.auto = e.target.checked; store("designAuto", D.auto); if (D.auto) evaluate(); } });
  const fmtSel = h("select", { "aria-label": "Export format" }, h("option", { value: "latex" }, "LaTeX (.tex)"), h("option", { value: "markdown" }, "Markdown (.md)"), h("option", { value: "html" }, "Printable HTML (.html)"), h("option", { value: "python" }, "SymPy script (.py)"), h("option", { value: "matlab" }, "MATLAB / Octave script (.m)"), h("option", { value: "excel" }, "Excel workbook with formulas (.xlsx)"));
  const modeSel = h("select", { "aria-label": "What to export" }, h("option", { value: "both" }, "Symbolic + numeric"), h("option", { value: "symbolic" }, "Symbolic only"), h("option", { value: "numeric" }, "Numeric only"));
  fmtSel.onchange = () => { modeSel.disabled = ["python", "matlab", "excel"].includes(fmtSel.value); };
  const fileIn = h("input", { type: "file", accept: "application/json,.json", hidden: true, onchange: onLoadFile });
  const palette = h("div", { class: "math-palette", role: "group", "aria-label": "Math blocks: drag onto the canvas or click to add" },
    h("span", { class: "plabel" }, "Math"),
    ...MATH_OPS.map((m) => h("button", {
      type: "button", class: "btn mathchip", draggable: "true", title: `${m.name}: ${m.hint}`, "aria-label": `${m.name} block`,
      ondragstart: (e) => { e.dataTransfer.setData("application/x-sliderule-math", m.op); e.dataTransfer.effectAllowed = "copy"; },
      onclick: () => addMathAtCentre(m.op),
    }, m.sym)));
  const toolbar = h("div", { class: "canvas-toolbar" },
    exSel,
    palette,
    h("button", { type: "button", class: "btn primary", onclick: () => evaluate(true) }, "Evaluate system"),
    h("label", { class: "inline" }, autoBox, "auto"),
    h("span", { class: "spacer" }),
    h("span", { class: "export-group", role: "group", "aria-label": "Export the full system of equations" },
      fmtSel, modeSel,
      h("button", { type: "button", class: "btn", title: "Download the equations of the whole system", onclick: () => exportDoc("download") }, "Export"),
      h("button", { type: "button", class: "btn", title: "Copy the document to the clipboard", onclick: () => exportDoc("copy") }, "Copy")),
    h("button", { type: "button", class: "btn", title: "Turn this system into an equation of its own in My equations", onclick: saveAsEquation }, "Save as equation…"),
    h("button", { type: "button", class: "btn", title: "Save the graph itself as JSON", onclick: saveFile }, "Save"),
    h("button", { type: "button", class: "btn", onclick: () => fileIn.click() }, "Load"),
    D.undoBtn = h("button", { type: "button", class: "btn", title: "Undo (Ctrl+Z)", "aria-label": "Undo", disabled: true, onclick: () => undo() }, "↶"),
    D.redoBtn = h("button", { type: "button", class: "btn", title: "Redo (Ctrl+Shift+Z or Ctrl+Y)", "aria-label": "Redo", disabled: true, onclick: () => redo() }, "↷"),
    h("button", { type: "button", class: "btn", title: "Arrange the blocks in columns by what feeds what", onclick: () => tidy() }, "Tidy"),
    h("button", { type: "button", class: "btn", title: "Copy the chosen blocks with the wires between them (Ctrl+C; Shift-click chooses several, Ctrl+A all)", onclick: () => copyChosen() }, "Copy blocks"),
    h("button", { type: "button", class: "btn", title: "Paste the copied blocks (Ctrl+V)", onclick: () => pasteClip() }, "Paste"),
    h("button", { type: "button", class: "btn", onclick: clearAll }, "Clear"),
    h("button", { type: "button", class: "btn", title: "Zoom out", onclick: () => zoomBy(1 / 1.2) }, "−"),
    h("button", { type: "button", class: "btn", title: "Zoom in", onclick: () => zoomBy(1.2) }, "+"),
    h("button", { type: "button", class: "btn", title: "Fit all blocks in view", onclick: fit }, "Fit"),
    fileIn);
  const canvasWrap = h("section", { class: "canvas-wrap" }, toolbar, canvas);
  const inspector = h("aside", { class: "inspector", "aria-label": "Block inspector", "aria-live": "polite" });
  clear(root).append(h("div", { class: "design" }, canvasWrap, inspector));

  // ------------------------------------------------------------------ data helpers
  const blockById = (id) => D.blocks.find((b) => b.id === id);
  const wireById = (id) => D.wires.find((w) => w.id === id);
  const isMath = (b) => b.kind === "math";
  const mathLocks = (b) => b.op === "add" || b.op === "sub";
  const detailOf = (b) => (isMath(b) ? D.math[b.id]?.detail : D.details.get(b.calc)) || { name: "…", variables: [], equations: [], example: {}, default_roles: {}, description: "" };
  /** The variables of a block; a math block's ports take their type from the locked / computed type (open ports stay grey). */
  const varsOf = (b) => {
    const vars = detailOf(b).variables;
    if (!isMath(b)) return vars;
    return vars.map((v) => ({ ...v, type: D.math[b.id]?.types?.[v.key] || OPEN_TYPE }));
  };
  const varOf = (b, key) => varsOf(b).find((v) => v.key === key);
  const rolesOf = (b) => (isMath(b) ? detailOf(b).default_roles : b.roles);
  const wireInto = (bid, key) => D.wires.find((w) => w.to.block === bid && w.to.key === key);
  const wiresAt = (bid, key) => D.wires.filter((w) => (w.from.block === bid && w.from.key === key) || (w.to.block === bid && w.to.key === key));
  const nextId = (p) => { let id; do { id = p + D.seq++; } while (blockById(id) || wireById(id)); return id; };

  async function ensureDetail(calcId) {
    if (!D.details.has(calcId)) D.details.set(calcId, await call("get_calculation", { calc_id: calcId }));
    return D.details.get(calcId);
  }

  function reachable(from, to) {   // is there a wire path from block `from` to block `to`?
    const seen = new Set();
    const stack = [from];
    while (stack.length) {
      const n = stack.pop();
      if (n === to) return true;
      if (seen.has(n)) continue;
      seen.add(n);
      for (const w of D.wires) if (w.from.block === n) stack.push(w.to.block);
    }
    return false;
  }

  /** The type rules, mirrored from sliderule.design (the server re-checks every graph it evaluates). */
  function canConnect(a, b) {
    if (a.role === b.role) return { ok: false, reason: "Wires run from an output to an input." };
    const [src, dst] = a.role === "output" ? [a, b] : [b, a];
    if (src.block === dst.block) return { ok: false, reason: "A block cannot feed itself." };
    const sb = blockById(src.block), db = blockById(dst.block);
    const sv = varOf(sb, src.key), dv = varOf(db, dst.key);
    const freeInput = isMath(db) && !mathLocks(db);          // multiply / divide accept any type; their output follows from the inputs
    if (!freeInput) {
      if (sv.type.open && isMath(sb) && !mathLocks(sb)) return { ok: false, reason: `The ${detailOf(sb).name} block does not know its output type yet: connect (or give units to) all of its inputs first.` };
      if (!sv.type.open && !dv.type.open && sv.type.key !== dv.type.key) {
        return { ok: false, reason: `Type mismatch: ${sv.label} is ${sv.type.kind} [${sv.type.si}] but ${dv.label} expects ${dv.type.kind} [${dv.type.si}].` };
      }
    }
    if (wireInto(dst.block, dst.key)) return { ok: false, reason: `${dv.label} already has a wire — drag it off its input port first.` };
    if (reachable(dst.block, src.block)) return { ok: false, reason: "That wire would create a feedback loop (not supported)." };
    return { ok: true, src, dst };
  }

  // ------------------------------------------------------------------ view (pan / zoom)
  function applyView() {
    const { x, y, k } = D.view;
    world.style.transform = `translate(${x}px, ${y}px) scale(${k})`;
    canvas.style.backgroundPosition = `${x}px ${y}px`;
    canvas.style.backgroundSize = `${GRID * 2 * k}px ${GRID * 2 * k}px`;
  }
  const toWorld = (cx, cy) => { const r = canvas.getBoundingClientRect(); return { x: (cx - r.left - D.view.x) / D.view.k, y: (cy - r.top - D.view.y) / D.view.k }; };
  function zoomAt(factor, cx, cy) {
    const k = Math.min(2, Math.max(0.3, D.view.k * factor));
    const r = canvas.getBoundingClientRect();
    const px = cx - r.left, py = cy - r.top;
    D.view.x = px - (px - D.view.x) * (k / D.view.k);
    D.view.y = py - (py - D.view.y) * (k / D.view.k);
    D.view.k = k;
    applyView();
  }
  function zoomBy(f) { const r = canvas.getBoundingClientRect(); zoomAt(f, r.left + r.width / 2, r.top + r.height / 2); }
  function fit() {
    if (!D.blocks.length) { D.view = { x: 40, y: 30, k: 1 }; applyView(); return; }
    const els = [...nodesEl.children];
    const xs = D.blocks.map((b) => b.x), ys = D.blocks.map((b) => b.y);
    const x1 = Math.max(...D.blocks.map((b, i) => b.x + (els[i]?.offsetWidth || NODE_W)));
    const y1 = Math.max(...D.blocks.map((b, i) => b.y + (els[i]?.offsetHeight || 200)));
    const r = canvas.getBoundingClientRect();
    const w = x1 - Math.min(...xs) + 80, hh = y1 - Math.min(...ys) + 80;
    const k = Math.min(1.2, Math.max(0.3, Math.min(r.width / w, r.height / hh)));
    D.view = { k, x: 40 - (Math.min(...xs) - 0) * k + (r.width - w * k) / 2, y: 40 - Math.min(...ys) * k + (r.height - hh * k) / 2 };
    applyView();
    drawWires();
  }

  // ------------------------------------------------------------------ rendering: nodes
  const portEls = new Map();    // "block|key" -> element

  function blockStatus(b) {
    const diags = (D.results?.diagnostics || []).filter((d) => d.block === b.id);
    if (b.check && !b.check.ok) return "error";
    if (diags.some((d) => d.level === "error")) return "error";
    if (b.check?.warnings?.length || diags.some((d) => d.level === "warning")) return "warning";
    return D.results?.blocks?.[b.id]?.ok ? "ok" : "idle";
  }
  const resultOf = (b, key) => D.results?.blocks?.[b.id]?.outputs?.find((o) => o.key === key);

  function renderNode(b) {
    const detail = detailOf(b);
    const vars = varsOf(b), roles = rolesOf(b);
    const old = nodesEl.querySelector(`[data-block="${b.id}"]`);
    const status = blockStatus(b);
    const rows = [];
    const rowFor = (v, role) => {
      const t = v.type;
      const wired = role === "input" ? wireInto(b.id, v.key) : null;
      let badge;
      if (role === "output") {
        const r = resultOf(b, v.key);
        badge = r ? h("span", { class: "val" }, `${r.value_text} ${r.unit}`) : h("span", { class: "kind" }, t.kind);
      } else if (wired) {
        const up = blockById(wired.from.block);
        const r = up && resultOf(up, wired.from.key);
        badge = h("span", { class: "val wired" }, "⟵ ", r ? `${r.value_text} ${r.unit}` : t.kind);
      } else {
        const q = splitQty(b.values[v.key]);
        badge = q.value !== "" ? h("span", { class: "val set" }, `${q.value} ${q.unit || v.unit}`) : h("span", { class: "val missing" }, "needs value");
      }
      const port = h("span", { class: "port", dataset: { block: b.id, key: v.key, role }, style: `--pc:${typeColor(t.key)}`, title: `${t.kind} [${t.si}] — drag to wire` });
      portEls.set(`${b.id}|${v.key}`, port);
      return h("div", { class: `prow ${role}`, dataset: { block: b.id, key: v.key, role }, title: `${v.label}\n${t.kind} [${t.si}]` },
        port, h("span", { class: "sym" }, math(v.latex)), h("span", { class: "lbl" }, v.label), badge);
    };
    const groups = { input: [], output: [], constant: [] };
    for (const v of vars) groups[roles[v.key]].push(v);
    if (groups.input.length) rows.push(h("div", { class: "grp" }, "inputs"), ...groups.input.map((v) => rowFor(v, "input")));
    if (groups.output.length) rows.push(h("div", { class: "grp" }, "outputs"), ...groups.output.map((v) => rowFor(v, "output")));
    if (groups.constant.length) {
      rows.push(h("div", { class: "grp" }, "constants"));
      for (const v of groups.constant) {
        const text = v.constant != null ? `${v.constant} ${v.unit}` : (splitQty(b.values[v.key]).value !== "" ? `${splitQty(b.values[v.key]).value} ${splitQty(b.values[v.key]).unit || v.unit}` : "needs value");
        rows.push(h("div", { class: "crow", title: v.label }, h("span", { class: "sym" }, math(v.latex)), h("span", { class: "lbl" }, v.label), h("span", { class: "val set" }, text)));
      }
    }
    const el = h("div", {
      class: `node ${status}${D.sel?.type === "block" && D.sel.id === b.id ? " selected" : ""}${D.multi.has(b.id) ? " multi" : ""}`, dataset: { block: b.id }, style: `left:${b.x}px;top:${b.y}px;width:${NODE_W}px`,
    },
      h("div", { class: "nhead", title: detail.name }, h("span", { class: `dot ${status}` }), h("span", { class: "ntitle" }, isMath(b) ? `${D.math[b.id]?.symbol || ""} ${detail.name}` : detail.name),
        isMath(b) ? h("span", { class: `lockbadge${D.math[b.id]?.locked ? " locked" : ""}`, title: D.math[b.id]?.locked ? "Locked to the type of the first wire connected" : mathLocks(b) ? "Open: takes the type of the first wire connected" : "Output type follows from the inputs" },
          mathBadge(b)) : null,
        h("button", { type: "button", class: "nx", "aria-label": `Remove ${detail.name}`, onpointerdown: (e) => e.stopPropagation(), onclick: () => removeBlock(b.id) }, "×")),
      b.comment?.trim() ? h("div", { class: "ncomment", title: b.comment }, h("span", { "aria-hidden": "true" }, "💬 "), b.comment.trim()) : null,
      h("div", { class: "nbody" }, rows));
    for (const k of [...portEls.keys()]) if (k.startsWith(b.id + "|") && !el.contains(portEls.get(k))) portEls.delete(k);
    old ? old.replaceWith(el) : nodesEl.append(el);
    return el;
  }

  function mathBadge(b) {
    const t = D.math[b.id]?.types?.y;
    if (mathLocks(b)) return D.math[b.id]?.locked ? `🔒 ${t.kind}` : "open";
    return t ? `→ ${t.kind}` : "→ ?";
  }

  function renderAll() {
    portEls.clear();
    clear(nodesEl);
    D.blocks.forEach(renderNode);
    empty.hidden = D.blocks.length > 0;
    if (!D.blocks.length) {
      clear(empty).append(h("div", {}, h("h2", {}, "System Design"),
        h("p", {}, "Click or drag calculations from the list onto this canvas. Click a block to choose which variables are inputs, outputs or constants, then drag from an output port to an input port of the same physical type."),
        D.examples.length ? h("p", {}, "Start from an example: ", ...D.examples.map((x) => h("button", { type: "button", class: "btn", onclick: () => loadGraph(x.graph) }, x.name))) : null));
    }
    drawWires();
    renderInspector();
  }

  // ------------------------------------------------------------------ rendering: wires
  const NS = "http://www.w3.org/2000/svg";
  const svgEl = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); return e; };
  function portPos(bid, key) {
    const el = portEls.get(`${bid}|${key}`);
    if (!el || !el.isConnected) return null;
    const r = el.getBoundingClientRect(), c = canvas.getBoundingClientRect();
    return { x: (r.left + r.width / 2 - c.left - D.view.x) / D.view.k, y: (r.top + r.height / 2 - c.top - D.view.y) / D.view.k };
  }
  const curve = (a, b, dir = 1) => {
    const dx = Math.max(50, Math.abs(b.x - a.x) / 2) * dir;
    return `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
  };
  let temp = null;
  function drawWires() {
    clear(svg);
    for (const w of D.wires) {
      const a = portPos(w.from.block, w.from.key), b = portPos(w.to.block, w.to.key);
      if (!a || !b) continue;
      const sv = varOf(blockById(w.from.block), w.from.key);
      const selected = D.sel?.type === "wire" && D.sel.id === w.id;
      const near = D.sel?.type === "block" && (D.sel.id === w.from.block || D.sel.id === w.to.block);
      const d = curve(a, b);
      const g = svgEl("g", { class: `wire${selected ? " selected" : ""}${near ? " near" : ""}`, style: `--pc:${typeColor(sv.type.key)}` });
      const hit = svgEl("path", { d, class: "hit" });
      hit.addEventListener("pointerdown", (e) => { e.stopPropagation(); select({ type: "wire", id: w.id }); });
      g.append(svgEl("path", { d, class: "line" }), hit);
      const up = blockById(w.from.block), r = up && resultOf(up, w.from.key);
      if (r || selected) {
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        const label = svgEl("text", { x: mx, y: my - 6, class: "wlabel", "text-anchor": "middle" });
        label.textContent = r ? `${r.value_text} ${r.unit}` : sv.type.kind;
        g.append(label);
        if (selected) {
          const x = svgEl("g", { class: "wdel", transform: `translate(${mx}, ${my + 12})` });
          x.append(svgEl("circle", { r: 9 }), Object.assign(svgEl("text", { y: 4, "text-anchor": "middle" }), { textContent: "×" }));
          x.addEventListener("pointerdown", (e) => { e.stopPropagation(); removeWire(w.id); });
          g.append(x);
        }
      }
      svg.append(g);
    }
    if (temp) {
      const t = svgEl("path", { d: temp.d, class: `temp ${temp.ok == null ? "" : temp.ok ? "good" : "bad"}` });
      svg.append(t);
    }
  }

  // ------------------------------------------------------------------ selection / inspector
  /** Shift-click adds a block to (or removes it from) a group that moves, is copied and is deleted together. */
  function toggleMulti(id) {
    if (D.sel?.type === "block" && !D.multi.size) D.multi.add(D.sel.id);
    D.multi.has(id) ? D.multi.delete(id) : D.multi.add(id);
    if (D.multi.size <= 1) D.multi.clear();
    D.sel = D.multi.size ? { type: "block", id } : { type: "block", id };
    markSelection();
    renderInspector();
  }
  function markSelection() {
    nodesEl.querySelectorAll(".node").forEach((n) => {
      n.classList.toggle("selected", D.sel?.type === "block" && n.dataset.block === D.sel.id);
      n.classList.toggle("multi", D.multi.has(n.dataset.block));
    });
    drawWires();
  }
  const chosen = () => (D.multi.size > 1 ? [...D.multi].map(blockById).filter(Boolean) : D.sel?.type === "block" ? [blockById(D.sel.id)].filter(Boolean) : []);

  /** Copy the chosen blocks, and the wires between them, inside the page (the clipboard of the system canvas). */
  function copyChosen() {
    const bs = chosen();
    if (!bs.length) return false;
    const ids = new Set(bs.map((b) => b.id));
    const g = JSON.parse(JSON.stringify(toGraph()));
    D.clip = { blocks: g.blocks.filter((b) => ids.has(b.id)), wires: g.wires.filter((w) => ids.has(w.from.block) && ids.has(w.to.block)), pastes: 0 };
    flash(`Copied ${bs.length} block${bs.length > 1 ? "s" : ""}`);
    return true;
  }
  /** Paste the copied blocks a little down and to the right, with their wires, and choose them. */
  async function pasteClip() {
    if (!D.clip?.blocks.length) return;
    D.clip.pastes += 1;
    const shift = 40 * D.clip.pastes, map = new Map();
    for (const b of D.clip.blocks) {
      const id = nextId("b");
      map.set(b.id, id);
      const copy = JSON.parse(JSON.stringify(b));
      D.blocks.push(isMath(b) ? { id, kind: "math", op: b.op, n: b.n ?? 2, x: b.x + shift, y: b.y + shift, roles: {}, values: copy.values || {}, out_units: copy.out_units || {}, comment: b.comment || "" }
        : { id, calc: b.calc, x: b.x + shift, y: b.y + shift, roles: copy.roles, values: copy.values, out_units: copy.out_units || {}, comment: b.comment || "" });
    }
    for (const w of D.clip.wires) D.wires.push({ id: nextId("w"), from: { block: map.get(w.from.block), key: w.from.key }, to: { block: map.get(w.to.block), key: w.to.key } });
    D.multi = new Set(map.size > 1 ? map.values() : []);
    D.sel = { type: "block", id: [...map.values()].at(-1) };
    await rerender();
    markSelection();
    changed();
    D.blocks.filter((b) => [...map.values()].includes(b.id) && !isMath(b)).forEach(recheck);
    flash(`Pasted ${map.size} block${map.size > 1 ? "s" : ""}`);
  }
  async function removeChosen() {
    const bs = chosen();
    if (bs.length < 2) return D.sel.type === "block" ? removeBlock(D.sel.id) : removeWire(D.sel.id);
    const ids = new Set(bs.map((b) => b.id));
    D.blocks = D.blocks.filter((b) => !ids.has(b.id));
    D.wires = D.wires.filter((w) => !ids.has(w.from.block) && !ids.has(w.to.block));
    D.multi.clear(); D.sel = null;
    await rerender();
    changed();
  }

  function select(sel) {
    D.sel = sel;
    D.multi = new Set();
    nodesEl.querySelectorAll(".node").forEach((n) => { n.classList.toggle("selected", sel?.type === "block" && n.dataset.block === sel.id); n.classList.remove("multi"); });
    drawWires();
    renderInspector();
  }

  function renderInspector() {
    const el = clear(inspector);
    if (D.sel?.type === "block" && blockById(D.sel.id)) return isMath(blockById(D.sel.id)) ? inspectMath(el, blockById(D.sel.id)) : inspectBlock(el, blockById(D.sel.id));
    if (D.sel?.type === "wire" && wireById(D.sel.id)) {
      const w = wireById(D.sel.id), a = blockById(w.from.block), b = blockById(w.to.block);
      const sv = varOf(a, w.from.key), dv = varOf(b, w.to.key);
      el.append(h("div", { class: "panel" }, h("h3", {}, "Wire"),
        h("p", {}, detailOf(a).name, " · ", math(sv.latex), " → ", detailOf(b).name, " · ", math(dv.latex)),
        h("p", { class: "desc" }, `Carries ${sv.type.kind} [${sv.type.si}]. Units differ freely between the two ends; values travel in coherent SI and are converted at the input.`),
        h("button", { type: "button", class: "btn", onclick: () => removeWire(w.id) }, "Delete wire")));
      return;
    }
    el.append(h("div", { class: "panel" }, h("h3", {}, "System"),
      h("p", { class: "desc" }, D.blocks.length ? "Click a block to edit its variables, or a wire to inspect it. Delete removes the selection." : "No blocks yet."),
      legend(), messages()));
    const sug = suggestionPanel();
    if (sug) el.append(sug);
  }

  function legend() {
    const types = new Map();
    for (const b of D.blocks) for (const v of varsOf(b)) if (rolesOf(b)[v.key] !== "constant" && !v.type.open) types.set(v.type.key, v.type.kind);
    if (!types.size) return h("div", {});
    return h("div", { class: "legend" }, h("h4", {}, "Port types on the canvas"),
      h("div", { class: "chips" }, [...types].map(([k, kind]) => h("span", { class: "chip" }, h("span", { class: "port static", style: `--pc:${typeColor(k)}` }), kind))),
      h("p", { class: "desc" }, "A wire only connects ports of the same colour."));
  }

  function messages(onlyBlock) {
    const diags = (D.results?.diagnostics || []).filter((d) => !onlyBlock || d.block === onlyBlock);
    if (!diags.length) return h("div", {});
    return h("ul", { class: "diag" }, diags.map((d) => {
      const b = d.block && blockById(d.block);
      return h("li", { class: d.level }, h("code", {}, d.code), b && !onlyBlock ? h("a", { href: "#", class: "link-btn", onclick: (e) => { e.preventDefault(); select({ type: "block", id: b.id }); } }, `${detailOf(b).name}: `) : null, d.message);
    }));
  }

  function inspectBlock(el, b) {
    const detail = detailOf(b);
    const head = h("div", { class: "panel" },
      h("div", { class: "title-row" }, h("h3", { style: "margin:0" }, detail.name),
        h("button", { type: "button", class: "btn", onclick: () => removeBlock(b.id) }, "Remove")),
      h("p", { class: "desc" }, detail.description),
      h("div", { class: "eqs" }, detail.equations.map((q) => h("div", { class: "eq" }, math(q.latex, false)))),
      h("a", { class: "link-btn", href: `#/calc/${detail.id}` }, "Open in Calculations →"));
    const problems = [];
    if (b.check && !b.check.ok) problems.push(h("ul", { class: "diag" }, b.check.errors.map((m) => h("li", { class: "error" }, h("code", {}, "ROLES"), m))));
    if (b.check?.warnings?.length) problems.push(h("ul", { class: "diag" }, b.check.warnings.map((m) => h("li", { class: "warning" }, h("code", {}, "NOTE"), m))));
    problems.push(messages(b.id));

    const table = h("div", { class: "roles" });
    for (const v of detail.variables) {
      const role = b.roles[v.key];
      const locked = v.constant != null;
      const seg = h("div", { class: "seg small", role: "group", "aria-label": `Role of ${v.label}` },
        ...["input", "output", "constant"].map((r) => h("button", {
          type: "button", "aria-pressed": String(role === r), disabled: locked && r !== "constant",
          title: locked ? "Physical constants are fixed" : `Make ${v.label} ${r === "constant" ? "a constant" : "an " + r}`,
          onclick: () => setRole(b, v, r),
        }, ROLE_LABEL[r])));
      let value;
      const wired = role === "input" ? wireInto(b.id, v.key) : null;
      if (locked) value = h("span", { class: "fixed" }, `= ${v.constant} ${v.unit}`);
      else if (role === "output") {
        const r = resultOf(b, v.key);
        const pick = unitPicker(v.units, (b.out_units || {})[v.key] || v.unit, () => { (b.out_units ||= {})[v.key] = pick.get(); changed(); }, { custom: !v.units || v.units.length > 1 });
        value = h("div", { class: "vcell" }, h("span", { class: "res" }, r ? `${r.value_text}` : "—"), pick.el);
      } else if (wired) {
        const up = blockById(wired.from.block);
        value = h("div", { class: "vcell" }, h("span", { class: "fixed" }, `⟵ ${detailOf(up).name} · ${wired.from.key}`),
          h("button", { type: "button", class: "btn small", onclick: () => removeWire(wired.id) }, "Unwire"));
      } else {
        const q = splitQty(b.values[v.key]);
        const input = h("input", { class: "value", type: "text", inputMode: "decimal", value: q.value, "aria-label": `${v.label} value`, placeholder: "value" });
        const pick = unitPicker(v.units, q.unit || v.unit, () => commit(), { custom: !v.units || v.units.length > 1 });
        const commit = () => { b.values[v.key] = input.value.trim() === "" ? "" : `${input.value.trim()} ${pick.get()}`; input.classList.toggle("bad", input.value.trim() !== "" && !isFinite(Number(input.value))); refreshNode(b); changed("edit"); };
        input.addEventListener("input", commit);
        value = h("div", { class: "vcell" }, input, pick.el);
      }
      table.append(h("div", { class: `rrow ${role}` }, h("span", { class: "sym" }, math(v.latex)),
        h("div", { class: "rl" }, h("div", {}, v.label), h("small", {}, `${v.type.kind} [${v.type.si}]`)), seg, value));
    }
    const rolesPanel = h("div", { class: "panel" }, h("h3", {}, "Variables"),
      h("p", { class: "desc" }, "Choose what each variable is. Inputs can take a wire (or a typed value), outputs are computed — the equations are rearranged to find them — and constants stay fixed inside this block."),
      table);
    el.append(head, ...problems.filter((x) => x.childNodes.length), commentPanel(b), suggestionPanel(b.id) || "", rolesPanel);
    const sol = D.results?.blocks?.[b.id];
    if (sol?.ok) el.append(stepsPanel(sol, state, "Worked solution for this block"));
  }

  function refreshNode(b) { renderNode(b); drawWires(); }

  async function recheck(b) {
    if (isMath(b)) { b.check = { ok: true, errors: [], warnings: [] }; return; }
    try { b.check = await call("design_check_block", { calc_id: b.calc, roles: b.roles }); } catch (e) { b.check = { ok: false, errors: [e.message], warnings: [] }; }
    refreshNode(b);
    if (D.sel?.type === "block" && D.sel.id === b.id) renderInspector();
  }

  /** Ask the engine for the type of every math-block port (it owns the "locked to the first wire" rule) and keep the blocks' ports in step. */
  async function refreshMath() {
    const maths = D.blocks.filter(isMath);
    if (!maths.length) { D.math = {}; return; }
    let res;
    try { res = await call("design_math", { graph: toGraph() }); } catch (e) { flash(e.message); return; }
    const before = D.math;
    D.math = res.blocks || {};
    for (const b of maths) {
      const now = D.math[b.id], was = before[b.id];
      if (mathLocks(b) && was && now && (was.types?.y?.key || null) !== (now.types?.y?.key || null) && Object.keys(b.values).length) {
        b.values = {};                       // typed values belong to the old type: a changed or released lock starts the block afresh
        flash(`${detailOf(b).name} block: values cleared because its type changed`);
      }
      if (now) b.roles = { ...now.detail.default_roles };
    }
  }
  async function rerender() { await refreshMath(); renderAll(); }

  /** A free-text note on a block: shown on the block and carried into the saved file and the exports. */
  function commentPanel(b) {
    const area = h("textarea", { class: "comment", rows: "3", maxlength: "2000", placeholder: "Notes on this block: assumptions, sources, what it represents…", "aria-label": "Comment on this block" });
    area.value = b.comment || "";
    area.addEventListener("input", () => { b.comment = area.value; refreshNode(b); persist(); });
    return h("div", { class: "panel" }, h("h3", {}, "Comment"), area);
  }

  function inspectMath(el, b) {
    const info = D.math[b.id];
    if (!info) return;
    const detail = info.detail, spec = MATH_OPS.find((m) => m.op === b.op);
    const t = info.types.y;
    const status = mathLocks(b)
      ? (info.locked ? `Locked to ${t.kind} [${t.si}] by the first wire connected. Disconnect every wire to release it.` : "Open: it takes the type of the first wire you connect, and then accepts only that type.")
      : (t ? `Output type: ${t.kind} [${t.si}] (the units of the inputs ${b.op === "mul" ? "multiplied" : "divided"}).` : "The output type appears once every input is wired or has a value with a unit.");
    const head = h("div", { class: "panel" },
      h("div", { class: "title-row" }, h("h3", { style: "margin:0" }, `${spec.sym} ${detail.name}`),
        h("button", { type: "button", class: "btn", onclick: () => removeBlock(b.id) }, "Remove")),
      h("p", { class: "desc" }, spec.hint),
      h("div", { class: "eqs" }, detail.equations.map((q) => h("div", { class: "eq" }, math(q.latex, false)))),
      h("p", { class: `desc mathstatus${info.locked ? " locked" : ""}` }, status));
    const table = h("div", { class: "roles" });
    const open = !info.locked && mathLocks(b);
    for (const v of varsOf(b)) {
      const role = rolesOf(b)[v.key];
      let value;
      if (role === "output") {
        const r = resultOf(b, v.key);
        const pick = unitPicker(v.units, (b.out_units || {})[v.key] || v.unit, () => { (b.out_units ||= {})[v.key] = pick.get(); changed(); }, { custom: true });
        value = h("div", { class: "vcell" }, h("span", { class: "res" }, r ? `${r.value_text}` : "—"), pick.el);
      } else if (wireInto(b.id, v.key)) {
        const wired = wireInto(b.id, v.key), up = blockById(wired.from.block);
        value = h("div", { class: "vcell" }, h("span", { class: "fixed" }, `⟵ ${detailOf(up).name} · ${wired.from.key}`),
          h("button", { type: "button", class: "btn small", onclick: () => removeWire(wired.id) }, "Unwire"));
      } else {
        const q = splitQty(b.values[v.key]);
        const input = h("input", { class: "value", type: "text", inputMode: "decimal", value: q.value, "aria-label": `${v.label} value`, placeholder: "value" });
        const pick = unitPicker(open || !v.type.si ? ["1"] : v.units, q.unit || (open ? "" : v.unit), () => commit(), { custom: true });
        const commit = async () => {
          b.values[v.key] = input.value.trim() === "" ? "" : `${input.value.trim()} ${pick.get()}`;
          input.classList.toggle("bad", input.value.trim() !== "" && !isFinite(Number(input.value)));
          await refreshMath();
          D.blocks.forEach(renderNode); drawWires();
          changed();
        };
        input.addEventListener("input", commit);
        value = h("div", { class: "vcell" }, input, pick.el);
      }
      table.append(h("div", { class: `rrow ${role}` }, h("span", { class: "sym" }, math(v.latex)),
        h("div", { class: "rl" }, h("div", {}, v.label), h("small", {}, v.type.open ? "any type until wired" : `${v.type.kind} [${v.type.si}]`)), h("span", {}), value));
    }
    const spec2 = detail.variables.filter((v) => rolesOf(b)[v.key] === "input").length;
    const resize = (d) => {
      const last = `x${spec2}`;
      if (d < 0 && wireInto(b.id, last)) { flash(`Unwire input ${spec2} first`); return; }
      b.n = Math.max(2, Math.min(8, spec2 + d));
      delete b.values[last];
      rerender().then(changed);
    };
    const buttons = ["add", "mul"].includes(b.op) ? h("div", { class: "vcell" },
      h("button", { type: "button", class: "btn small", disabled: spec2 >= 8, onclick: () => resize(1) }, "+ input"),
      h("button", { type: "button", class: "btn small", disabled: spec2 <= 2, onclick: () => resize(-1) }, "− input")) : null;
    const rolesPanel = h("div", { class: "panel" }, h("h3", {}, "Ports"),
      h("p", { class: "desc" }, "Wire values in, or type a value for an input that has no wire."), table, buttons);
    el.append(head, messages(b.id), commentPanel(b), rolesPanel);
    const sol = D.results?.blocks?.[b.id];
    if (sol?.ok) el.append(stepsPanel(sol, state, "Worked solution for this block"));
  }

  function setRole(b, v, role) {
    if (b.roles[v.key] === role) return;
    const gone = wiresAt(b.id, v.key);
    D.wires = D.wires.filter((w) => !gone.includes(w));
    b.roles[v.key] = role;
    if (role !== "output" && !b.values[v.key]) {
      const ex = detailOf(b).example[v.key];
      b.values[v.key] = ex ?? (v.default != null ? `${v.default} ${v.unit}` : "");
    }
    if (gone.length) flash(`Removed ${gone.length} wire${gone.length > 1 ? "s" : ""} from ${v.label}`);
    renderAll();
    recheck(b);
    changed();
  }

  // ------------------------------------------------------------------ editing operations
  async function addBlock(calcId, x, y) {
    const d = await ensureDetail(calcId);
    const b = {
      id: nextId("b"), calc: calcId, x: Math.round(x / GRID) * GRID, y: Math.round(y / GRID) * GRID,
      roles: { ...d.default_roles }, values: {}, out_units: {},
    };
    for (const v of d.variables) if (b.roles[v.key] !== "output" && v.constant == null) {
      b.values[v.key] = d.example[v.key] ?? (v.default != null ? `${v.default} ${v.unit}` : "");
    }
    D.blocks.push(b);
    D.sel = { type: "block", id: b.id };
    renderAll();
    recheck(b);
    changed();
  }
  async function addMathBlock(op, x, y) {
    const b = { id: nextId("b"), kind: "math", op, n: 2, x: Math.round(x / GRID) * GRID, y: Math.round(y / GRID) * GRID, roles: {}, values: {}, out_units: {} };
    D.blocks.push(b);
    D.sel = { type: "block", id: b.id };
    await rerender();
    changed();
  }
  async function removeBlock(id) {
    D.blocks = D.blocks.filter((b) => b.id !== id);
    D.wires = D.wires.filter((w) => w.from.block !== id && w.to.block !== id);
    if (D.sel?.id === id) D.sel = null;
    await rerender();
    changed();
  }
  async function removeWire(id) {
    const w = wireById(id);
    D.wires = D.wires.filter((x) => x.id !== id);
    if (D.sel?.id === id) D.sel = null;
    if (w) { const b = blockById(w.to.block); if (b) renderNode(b); }
    await rerender();
    changed();
  }
  async function addWire(src, dst) {
    D.wires.push({ id: nextId("w"), from: { block: src.block, key: src.key }, to: { block: dst.block, key: dst.key } });
    await rerender();
    changed();
  }
  function clearAll() {
    if (D.blocks.length && !confirm("Remove every block and wire from the canvas?")) return;
    D.blocks = []; D.wires = []; D.sel = null; D.results = null; D.math = {};
    renderAll();
    changed();
  }

  // ------------------------------------------------------------------ evaluation + persistence
  const toGraph = () => ({
    version: 1,
    blocks: D.blocks.map((b) => (isMath(b)
      ? { id: b.id, kind: "math", op: b.op, n: b.n, x: b.x, y: b.y, values: b.values, out_units: b.out_units, ...(b.comment ? { comment: b.comment } : {}) }
      : { id: b.id, calc: b.calc, x: b.x, y: b.y, roles: b.roles, values: b.values, out_units: b.out_units, ...(b.comment ? { comment: b.comment } : {}) })),
    wires: D.wires.map((w) => ({ id: w.id, from: w.from, to: w.to })),
  });
  let evalSeq = 0;
  async function evaluate(force) {
    if (!D.blocks.length) { D.results = null; return; }
    const seq = ++evalSeq;
    let res;
    try { res = await call("design_solve", { graph: toGraph(), sig_figs: 5 }); } catch (e) { flash(e.message); return; }
    if (seq !== evalSeq) return;
    D.results = res;
    if (force && res.ok) flash("System evaluated");
    D.blocks.forEach(renderNode);
    drawWires();
    renderInspector();
  }
  const evalSoon = debounce(() => evaluate(false), 400);
  const persist = debounce(() => { try { localStorage.setItem("sliderule.design.graph", JSON.stringify(toGraph())); } catch { /* storage unavailable */ } }, 300);
  function changed(kind) {
    persist();
    record(kind);
    if (D.auto) evalSoon(); else if (D.results) { D.results = null; D.blocks.forEach(renderNode); drawWires(); }
  }

  // ---- undo / redo: the whole graph is small, so each step is a snapshot of it
  const HIST = { stack: [], pos: -1, kind: "", at: 0, restoring: false };
  const snapshot = () => JSON.stringify(toGraph());
  function syncHistoryButtons() {
    D.undoBtn.disabled = HIST.pos <= 0;
    D.redoBtn.disabled = HIST.pos >= HIST.stack.length - 1;
  }
  /** Remember the graph as a step. Typing in a value box is one step per burst (`kind` "edit"), not one per keystroke. */
  function record(kind = "") {
    if (HIST.restoring) return;
    const now = Date.now(), snap = snapshot();
    if (HIST.stack[HIST.pos] === snap) return;
    if (kind === "edit" && HIST.kind === "edit" && HIST.pos === HIST.stack.length - 1 && HIST.pos > 0 && now - HIST.at < 1500) HIST.stack[HIST.pos] = snap;
    else {
      HIST.stack = HIST.stack.slice(0, HIST.pos + 1);
      HIST.stack.push(snap);
      if (HIST.stack.length > 100) HIST.stack.shift();
      HIST.pos = HIST.stack.length - 1;
    }
    HIST.kind = kind; HIST.at = now;
    syncHistoryButtons();
  }
  async function stepHistory(by) {
    const to = HIST.pos + by;
    if (to < 0 || to >= HIST.stack.length) return;
    HIST.pos = to; HIST.kind = "";
    HIST.restoring = true;
    try { await loadGraph(JSON.parse(HIST.stack[to]), { keepView: true }); } finally { HIST.restoring = false; }
    persist();
    syncHistoryButtons();
  }
  const undo = () => stepHistory(-1);
  const redo = () => stepHistory(1);

  /** Arrange the blocks in columns: a block sits one column to the right of the furthest block that feeds it, and rows follow the average height of the feeders. */
  function tidy() {
    if (!D.blocks.length) return;
    const feeders = (b) => [...new Set(D.wires.filter((w) => w.to.block === b.id).map((w) => w.from.block))];
    const depth = new Map();
    const dep = (b, seen = new Set()) => {
      if (depth.has(b.id)) return depth.get(b.id);
      if (seen.has(b.id)) return 0;
      seen.add(b.id);
      const d = feeders(b).reduce((m, id) => Math.max(m, 1 + dep(blockById(id), seen)), 0);
      depth.set(b.id, d);
      return d;
    };
    D.blocks.forEach((b) => dep(b));
    const heightOf = (b) => nodesEl.querySelector(`[data-block="${b.id}"]`)?.offsetHeight || 200;
    const cols = [];
    for (const b of D.blocks) (cols[depth.get(b.id)] ||= []).push(b);
    const GAP_X = 90, GAP_Y = 30;
    cols.forEach((col, ci) => {
      if (!col) return;
      const want = (b) => { const f = feeders(b).map(blockById).filter(Boolean); return f.length ? f.reduce((a, o) => a + o.y, 0) / f.length : b.y; };
      col.sort((a, b) => want(a) - want(b));
      let y = 40;
      for (const b of col) {
        b.x = Math.round((40 + ci * (NODE_W + GAP_X)) / GRID) * GRID;
        b.y = Math.round(Math.max(y, want(b) > y ? Math.min(want(b), y + 120) : y) / GRID) * GRID;
        y = b.y + heightOf(b) + GAP_Y;
      }
    });
    renderAll();
    fit();
    persist();
    record();
    flash("Blocks arranged");
  }

  /** Wires that could be made now: an output to an unwired input of the same physical type, best matches first (the same symbol, then inputs still waiting for a value). */
  function suggestions(only) {
    const out = [];
    for (const sb of D.blocks) for (const db of D.blocks) {
      if (sb === db || (only && sb.id !== only && db.id !== only)) continue;
      const sr = rolesOf(sb), dr = rolesOf(db);
      for (const sv of varsOf(sb)) {
        if (sr[sv.key] !== "output" || sv.type.open) continue;
        for (const dv of varsOf(db)) {
          if (dr[dv.key] !== "input" || dv.type.open || dv.type.key !== sv.type.key || wireInto(db.id, dv.key)) continue;
          const c = canConnect({ block: sb.id, key: sv.key, role: "output" }, { block: db.id, key: dv.key, role: "input" });
          if (!c.ok) continue;
          const waiting = !isMath(db) && splitQty(db.values[dv.key]).value === "";
          out.push({ src: c.src, dst: c.dst, sb, db, sv, dv, score: (sv.key === dv.key ? 2 : 0) + (sv.label === dv.label ? 1 : 0) + (waiting ? 1 : 0) });
        }
      }
    }
    return out.sort((a, b) => b.score - a.score).slice(0, 6);
  }
  function suggestionPanel(only) {
    const list = suggestions(only);
    if (!list.length) return null;
    return h("div", { class: "panel suggest" }, h("h3", {}, "Suggested connections"),
      h("p", { class: "desc" }, "Outputs and inputs of the same physical type that are not wired yet."),
      h("ul", {}, list.map((x) => h("li", {}, h("span", {}, detailOf(x.sb).name, " · ", math(x.sv.latex), " → ", detailOf(x.db).name, " · ", math(x.dv.latex), h("small", {}, ` ${x.sv.type.kind}`)),
        h("button", { type: "button", class: "btn small", onclick: () => addWire(x.src, x.dst) }, "Connect")))));
  }

  async function loadGraph(g, { keepView = false } = {}) {
    const blocks = [];
    for (const b of g.blocks || []) {
      if (b.kind === "math") {
        if (MATH_OPS.some((m) => m.op === b.op)) blocks.push({ id: b.id, kind: "math", op: b.op, n: b.n ?? 2, x: b.x ?? 40, y: b.y ?? 40, roles: {}, values: { ...(b.values || {}) }, out_units: { ...(b.out_units || {}) }, comment: b.comment || "" });
        else flash(`Skipped unknown math block ${b.op}`);
        continue;
      }
      try {
        const d = await ensureDetail(b.calc);
        blocks.push({ id: b.id, calc: b.calc, x: b.x ?? 40, y: b.y ?? 40, roles: { ...d.default_roles, ...(b.roles || {}) }, values: { ...(b.values || {}) }, out_units: { ...(b.out_units || {}) }, comment: b.comment || "" });
      } catch (e) { flash(`Skipped unknown block ${b.calc}`); }
    }
    for (const b of blocks.filter((x) => !isMath(x))) {   // blocks loaded from an example only carry the values they changed: fill the rest from the calculation's example
      const d = D.details.get(b.calc);
      for (const v of d.variables) if (b.roles[v.key] !== "output" && v.constant == null && !b.values[v.key]) b.values[v.key] = d.example[v.key] ?? (v.default != null ? `${v.default} ${v.unit}` : "");
    }
    D.blocks = blocks;
    const ids = new Set(blocks.map((b) => b.id));
    D.wires = (g.wires || []).filter((w) => ids.has(w.from?.block) && ids.has(w.to?.block)).map((w, i) => ({ id: w.id || `w${i + 1}`, from: w.from, to: w.to }));
    D.seq = blocks.length + D.wires.length + 1;
    D.sel = null; D.results = null;
    await rerender();
    await Promise.all(blocks.map(recheck));
    if (!keepView) fit();
    changed();
    evaluate(false);
  }

  async function exportDoc(action) {
    if (!D.blocks.length) { flash("Add some blocks first"); return; }
    let res;
    try { res = await call("design_export", { graph: toGraph(), format: fmtSel.value, mode: modeSel.value, sig_figs: 5, standalone: true }); } catch (e) { flash(e.message); return; }
    if (!res.ok) {
      const d = res.diagnostics?.[0];
      flash(d ? `Cannot export: ${d.message}` : "Cannot export this system");
      if (d?.block && blockById(d.block)) select({ type: "block", id: d.block });
      return;
    }
    if (action === "copy" && res.binary) { flash("The Excel workbook is a file: use Export to download it"); return; }
    if (action === "copy") {
      try { await navigator.clipboard.writeText(res.content); flash(`${{ latex: "LaTeX", markdown: "Markdown", html: "HTML", python: "Python script", matlab: "MATLAB script" }[fmtSel.value]} copied`); } catch { flash("Clipboard unavailable"); }
      return;
    }
    const bytes = res.binary ? Uint8Array.from(atob(res.content_base64), (c) => c.charCodeAt(0)) : null;
    const blob = new Blob([bytes ?? res.content], { type: res.binary ? res.mime : res.mime + ";charset=utf-8" });
    const a = h("a", { href: URL.createObjectURL(blob), download: res.filename });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    flash(`Exported ${res.filename}`);
  }

  // ------------------------------------------------------------------ save the system as an equation of its own
  function showDialog(title, ...content) {
    document.querySelector("dialog.eqdialog")?.remove();
    const dlg = h("dialog", { class: "eqdialog", "aria-label": title }, h("h3", {}, title), ...content);
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
    return dlg;
  }
  async function saveAsEquation() {
    if (!D.blocks.length) { flash("Add some blocks first"); return; }
    let draft;
    try { draft = await call("design_to_equation", { graph: toGraph() }); } catch (e) { flash(e.message); return; }
    if (!draft.ok) {
      const dlg = showDialog("This system cannot be saved as an equation",
        h("ul", { class: "diag" }, draft.errors.map((m) => h("li", { class: "error" }, m))),
        h("div", { class: "actions" }, h("button", { type: "button", class: "btn", onclick: () => dlg.close() }, "Close")));
      return;
    }
    const name = h("input", { type: "text", value: draft.calculation.name, maxlength: "120", "aria-label": "Name of the equation" });
    const desc = h("textarea", { rows: "3", maxlength: "2000", "aria-label": "Description" });
    desc.value = draft.calculation.description;
    const checks = draft.candidates.map((c) => ({ c, box: h("input", { type: "checkbox", checked: draft.selected.includes(c.ref) }) }));
    const msg = h("div", { class: "msg", "aria-live": "polite" });
    const save = h("button", { type: "button", class: "btn primary" }, "Save to My equations");
    const dlg = showDialog("Save this system as an equation",
      h("p", { class: "desc" }, `The ${draft.summary.blocks} block(s) become one calculation of ${draft.summary.equations} equations in ${draft.summary.variables} variables. Wired ports merge into one variable, unwired inputs keep the values typed on the canvas, and every variable can still be solved for.`),
      h("label", { class: "field" }, "Name", name),
      h("label", { class: "field" }, "Description", desc),
      h("fieldset", {}, h("legend", {}, "Computed by default (the rest become inputs)"), ...checks.map(({ c, box }) => h("label", { class: "check" }, box, c.label))),
      draft.warnings?.length ? h("ul", { class: "diag" }, draft.warnings.map((m) => h("li", { class: "warning" }, m))) : null,
      msg,
      h("div", { class: "actions" }, save, h("button", { type: "button", class: "btn", onclick: () => dlg.close() }, "Cancel")));
    save.onclick = async () => {
      save.disabled = true;
      clear(msg);
      try {
        const refs = checks.filter((x) => x.box.checked).map((x) => x.c.ref);
        const d = await call("design_to_equation", { graph: toGraph(), name: name.value, description: desc.value, outputs: refs });
        if (!d.ok) throw new Error(d.errors.join("; "));
        const saved = await call("custom_save", { calculation: d.calculation });
        await ctx.customChanged?.();
        flash(`Saved “${d.calculation.name}” to My equations`);
        clear(msg).append(h("p", {}, `Saved as ${saved.id}. `, h("a", { href: `#/calc/${saved.id}`, onclick: () => dlg.close() }, "Open in Calculations →")));
        save.hidden = true;
      } catch (e) {
        clear(msg).append(h("p", { class: "bad" }, e.message || String(e)));
        save.disabled = false;
      }
    };
  }

  async function saveFile() {
    const graph = toGraph();
    const customIds = [...new Set(D.blocks.map((b) => b.calc).filter((id) => D.details.get(id)?.custom))];
    if (customIds.length) {   // so a recipient who lacks these equations can open the graph
      try { graph.custom_calculations = (await call("custom_export", { ids: customIds })).document.calculations; } catch (e) { flash("Could not embed your equations: " + e.message); }
    }
    const blob = new Blob([JSON.stringify(graph, null, 2)], { type: "application/json" });
    const a = h("a", { href: URL.createObjectURL(blob), download: "sliderule-system.json" });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  /** Equations a shared graph carries are added to My equations unless the user already has one with that id (theirs is kept). */
  async function importEmbedded(calcs) {
    const r = await call("custom_import", { document: { format: "sliderule-calculations", version: 1, calculations: calcs }, on_conflict: "skip" });
    const added = r.results.filter((x) => x.status === "added").length;
    const kept = r.results.filter((x) => x.status === "skipped");
    const bad = r.results.filter((x) => x.status === "error");
    if (added) await ctx.customChanged?.();
    flash([added && `Added ${added} equation(s) from the file to My equations`, kept.length && `kept your own version of ${kept.map((x) => x.name).join(", ")}`, bad.length && `${bad.length} embedded equation(s) were invalid`].filter(Boolean).join("; ") || "Equations in the file are already in My equations");
  }
  async function onLoadFile(e) {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    try {
      const g = JSON.parse(await f.text());
      if (g.custom_calculations?.length) await importEmbedded(g.custom_calculations);
      await loadGraph(g);
    } catch (err) { flash("Could not read that file: " + err.message); }
  }

  // ------------------------------------------------------------------ adding blocks (the calculation list lives in app.js)
  /** Add a calculation near the middle of the visible canvas, staggered so repeated adds do not stack exactly. */
  function addAtCentre(calcId) {
    const r = canvas.getBoundingClientRect();
    const p = toWorld(r.left + r.width / 2, r.top + r.height / 3);
    const n = D.blocks.length % 5;
    return addBlock(calcId, p.x - NODE_W / 2 + n * 24, p.y + n * 24);
  }
  function addMathAtCentre(op) {
    const r = canvas.getBoundingClientRect();
    const p = toWorld(r.left + r.width / 2, r.top + r.height / 3);
    const n = D.blocks.length % 5;
    return addMathBlock(op, p.x - NODE_W / 2 + n * 24, p.y + n * 24);
  }
  canvas.addEventListener("dragover", (e) => { if ([...e.dataTransfer.types].some((t) => t === "application/x-sliderule-calc" || t === "application/x-sliderule-math")) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; } });
  canvas.addEventListener("drop", (e) => {
    const mathOp = e.dataTransfer.getData("application/x-sliderule-math");
    if (mathOp) { e.preventDefault(); const p = toWorld(e.clientX, e.clientY); addMathBlock(mathOp, p.x - NODE_W / 2, p.y - 20); return; }
    const id = e.dataTransfer.getData("application/x-sliderule-calc");
    if (!id) return;
    e.preventDefault();
    const p = toWorld(e.clientX, e.clientY);
    addBlock(id, p.x - NODE_W / 2, p.y - 20);
  });

  // ------------------------------------------------------------------ pointer interactions
  let drag = null;
  const guides = [];
  function clearGuides() { guides.splice(0).forEach((g) => g.remove()); }
  /** While a block is dragged, line its left edge up with another block's, and its top with another's top or bottom (Alt held: no snapping). */
  function snapToNeighbours(b, el, off) {
    clearGuides();
    if (off) return;
    const near = 8 / D.view.k, hh = el.offsetHeight;
    let gx = null, gy = null;
    for (const o of D.blocks) {
      if (o.id === b.id) continue;
      const oel = nodesEl.querySelector(`[data-block="${o.id}"]`), oh = oel?.offsetHeight || 200;
      if (gx === null && Math.abs(b.x - o.x) <= near) gx = o.x;
      for (const y of [o.y, o.y + oh + 30, o.y - hh - 30]) if (gy === null && Math.abs(b.y - y) <= near) gy = y;
    }
    if (gx !== null) { b.x = gx; guides.push(world.appendChild(h("div", { class: "guide v", style: `left:${gx}px` }))); }
    if (gy !== null) { b.y = gy; guides.push(world.appendChild(h("div", { class: "guide h", style: `top:${gy}px` }))); }
  }
  canvas.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    if (e.target.closest(".canvas-empty button, .canvas-empty a")) return;   // the "start from an example" buttons: panning would capture the pointer and swallow their click
    const port = e.target.closest(".port:not(.static)");
    const nodeEl = e.target.closest(".node");
    if (port && port.dataset.block) return startWire(e, port);
    if (nodeEl && e.shiftKey) { toggleMulti(nodeEl.dataset.block); return; }
    if (nodeEl && e.target.closest(".nhead")) {
      const b = blockById(nodeEl.dataset.block);
      const group = D.multi.has(b.id) && D.multi.size > 1;
      if (!group) select({ type: "block", id: b.id });
      const start = toWorld(e.clientX, e.clientY);
      drag = { kind: "node", b, el: nodeEl, ox: start.x - b.x, oy: start.y - b.y, group: group ? [...D.multi].map(blockById).filter(Boolean).map((o) => ({ b: o, dx: o.x - b.x, dy: o.y - b.y })) : null };
      canvas.setPointerCapture(e.pointerId);
      return;
    }
    if (nodeEl) { select({ type: "block", id: nodeEl.dataset.block }); return; }
    if (e.target.closest(".wire")) return;
    select(null);
    drag = { kind: "pan", sx: e.clientX, sy: e.clientY, vx: D.view.x, vy: D.view.y };
    canvas.classList.add("panning");
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (drag?.kind === "node") {
      const p = toWorld(e.clientX, e.clientY);
      drag.b.x = Math.round((p.x - drag.ox) / GRID) * GRID;
      drag.b.y = Math.round((p.y - drag.oy) / GRID) * GRID;
      if (!drag.group) snapToNeighbours(drag.b, drag.el, e.altKey);
      drag.el.style.left = `${drag.b.x}px`;
      drag.el.style.top = `${drag.b.y}px`;
      for (const o of drag.group || []) {                                                 // the rest of a chosen group keeps its place around the one being dragged
        o.b.x = drag.b.x + o.dx; o.b.y = drag.b.y + o.dy;
        const el = nodesEl.querySelector(`[data-block="${o.b.id}"]`);
        if (el) { el.style.left = `${o.b.x}px`; el.style.top = `${o.b.y}px`; }
      }
      drawWires();
    } else if (drag?.kind === "pan") {
      D.view.x = drag.vx + (e.clientX - drag.sx);
      D.view.y = drag.vy + (e.clientY - drag.sy);
      applyView();
    } else if (drag?.kind === "wire") moveWire(e);
  });
  const endDrag = (e) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    canvas.classList.remove("panning");
    if (d.kind === "wire") finishWire(e, d);
    else if (d.kind === "node") { clearGuides(); persist(); record(); }
    try { canvas.releasePointerCapture(e.pointerId); } catch { /* not captured */ }
  };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);
  canvas.addEventListener("wheel", (e) => { e.preventDefault(); zoomAt(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX, e.clientY); }, { passive: false });
  canvas.addEventListener("keydown", (e) => {
    if ((e.key === "Delete" || e.key === "Backspace") && D.sel && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName)) {
      e.preventDefault();
      removeChosen();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (root.hidden || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName)) return;
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
    if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); return; }
    if (mod && e.key.toLowerCase() === "c" && copyChosen()) { e.preventDefault(); return; }
    if (mod && e.key.toLowerCase() === "v" && D.clip) { e.preventDefault(); pasteClip(); return; }
    if (mod && e.key.toLowerCase() === "a" && D.blocks.length) { e.preventDefault(); D.multi = new Set(D.blocks.map((b) => b.id)); D.sel = { type: "block", id: D.blocks.at(-1).id }; markSelection(); renderInspector(); }
  });
  document.addEventListener("keydown", (e) => {
    if (root.hidden || e.target !== document.body) return;
    if ((e.key === "Delete" || e.key === "Backspace") && D.sel) { e.preventDefault(); removeChosen(); }
  });

  // --- wiring
  function portOf(el) { return el && { block: el.dataset.block, key: el.dataset.key, role: el.dataset.role }; }
  async function startWire(e, portEl) {
    e.preventDefault();
    let origin = portOf(portEl);
    if (origin.role === "input") {            // pick up an existing wire by its input end
      const w = wireInto(origin.block, origin.key);
      if (w) { await removeWireQuiet(w.id); origin = { block: w.from.block, key: w.from.key, role: "output" }; }
    }
    const pos = portPos(origin.block, origin.key);
    drag = { kind: "wire", origin, pos };
    canvas.setPointerCapture(e.pointerId);
    canvas.classList.add("wiring");
    // mark every other port as compatible / blocked for this origin
    for (const [k, el] of portEls) {
      const [bid, key] = k.split("|");
      const target = { block: bid, key, role: el.dataset.role };
      if (bid === origin.block && key === origin.key) continue;
      const c = canConnect(origin, target);
      el.classList.toggle("ok", c.ok);
      el.classList.toggle("no", !c.ok);
      el.closest(".prow")?.classList.toggle("ok", c.ok);
      el.closest(".prow")?.classList.toggle("no", !c.ok);
    }
    moveWire(e);
  }
  async function removeWireQuiet(id) { D.wires = D.wires.filter((w) => w.id !== id); await rerender(); changed(); }
  function hoverPort(e) {
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const row = el?.closest?.(".prow[data-key]");
    return row ? { block: row.dataset.block, key: row.dataset.key, role: row.dataset.role } : null;
  }
  const SNAP_PX = 28;
  /** What the wire being dragged would connect to: the port under the pointer, or failing that the nearest port it could connect to within 28 px (so the end need not land exactly). */
  function wireTarget(e, o) {
    const over = hoverPort(e);
    if (over && !(over.block === o.block && over.key === o.key)) {
      const verdict = canConnect(o, over);
      if (verdict.ok) return { target: over, verdict };
    }
    let best = null;
    for (const [k, el] of portEls) {
      const [bid, key] = k.split("|");
      if (bid === o.block && key === o.key) continue;
      const r = el.getBoundingClientRect();
      const d = Math.hypot(r.left + r.width / 2 - e.clientX, r.top + r.height / 2 - e.clientY);
      if (d > SNAP_PX || (best && d >= best.d)) continue;
      const target = { block: bid, key, role: el.dataset.role }, verdict = canConnect(o, target);
      if (verdict.ok) best = { d, target, verdict };
    }
    if (best) return { target: best.target, verdict: best.verdict, snapped: true };
    return over && !(over.block === o.block && over.key === o.key) ? { target: over, verdict: canConnect(o, over) } : { target: null, verdict: null };
  }
  function moveWire(e) {
    const o = drag.origin;
    const { target, verdict, snapped } = wireTarget(e, o);
    const p = snapped ? portPos(target.block, target.key) : toWorld(e.clientX, e.clientY);       // a snapped end sits on the port
    temp = { d: o.role === "output" ? curve(drag.pos, p, 1) : curve(p, drag.pos, 1), ok: verdict ? verdict.ok : null };
    drawWires();
  }
  function finishWire(e, d) {
    const { target, verdict } = wireTarget(e, d.origin);
    temp = null;
    canvas.classList.remove("wiring");
    portEls.forEach((el) => { el.classList.remove("ok", "no"); el.closest(".prow")?.classList.remove("ok", "no"); });
    if (target) {
      if (verdict.ok) return addWire(verdict.src, verdict.dst);
      flash(verdict.reason);
    }
    renderAll();
  }

  // ------------------------------------------------------------------ boot
  applyView();
  try { D.examples = (await call("design_examples")).examples; } catch { D.examples = []; }
  for (const x of D.examples) exSel.append(h("option", { value: x.id }, x.name));
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem("sliderule.design.graph") || "null"); } catch { saved = null; }
  if (saved?.blocks?.length) await loadGraph(saved); else renderAll();
  HIST.stack = [snapshot()]; HIST.pos = 0; syncHistoryButtons();      // what was restored is the starting point: undo never goes before it

  return {
    onShow() { drawWires(); },
    /** Add a calculation (clicked in the shared list) near the middle of the canvas. */
    addCalc: addAtCentre,
    /** My equations changed: re-read the definitions of calculations already on the canvas. */
    async refreshDefinitions() {
      for (const id of new Set(D.blocks.filter((b) => !isMath(b)).map((b) => b.calc))) {
        try { D.details.set(id, await call("get_calculation", { calc_id: id })); } catch { /* deleted: keep the old definition on screen */ }
      }
      D.blocks.forEach(renderNode);
      if (D.blocks.length) evaluate(false);
    },
    _state: D,
  };
}
