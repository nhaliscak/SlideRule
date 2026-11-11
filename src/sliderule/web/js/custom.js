// "My equations": create, edit, import, export and delete user-defined calculations.
// The engine validates everything (units, dimensional consistency, safe expression grammar); this file is the form around it.
import { clear, debounce, h, math } from "./dom.js";
import { flash } from "./steps.js";

const FUNCS = "sqrt, exp, log, ln, log10, log2, sin, cos, tan, asin, acos, atan, atan2, sinh, cosh, tanh, Abs, Min, Max, Piecewise, erf, floor, ceiling, pi";
const CALCULUS = "diff(f, t) or diff(f, t, 2) for derivatives, integrate(f, (x, a, b)) for definite integrals, summation(term, (n, 1, 50)) for a series";

const blankVar = () => ({ key: "", label: "", unit: "", latex: "", role: "input", value: "", example: "", min: "", max: "", signed: false, delta: false, note: "", solve: false, units: null, shape: "" });
const lines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);
/** Rectangles removed from a two-dimensional region, typed as a JSON list; an unreadable list is left out (the server then reports what is missing). */
const cutoutsOf = (text) => { try { const v = JSON.parse(text || "[]"); return Array.isArray(v) && v.length ? { cutouts: v } : {}; } catch (e) { return {}; } };
const num = (s) => (String(s).trim() === "" ? undefined : isFinite(Number(s)) ? Number(s) : String(s).trim());

function docToDraft(doc) {
  const out = new Set(doc.outputs || []);
  return {
    id: doc.id || "", name: doc.name || "", description: doc.description || "", author: doc.author || "",
    disciplines: [...(doc.disciplines || [])], subdisciplines: [...(doc.subdisciplines || [])], tags: [...(doc.tags || [])],
    variables: (doc.variables || []).map((v) => ({
      key: v.key, label: v.label, unit: v.unit === "1" ? "" : v.unit || "", latex: v.latex || "", role: v.constant != null ? "constant" : "input",
      value: v.constant != null ? String(v.constant) : v.default != null ? String(v.default) : "", example: Array.isArray(v.example) ? v.example.join("; ") : v.example || "",
      shape: v.shape ? v.shape.join("x") : "",
      min: v.min != null ? String(v.min) : "", max: v.max != null ? String(v.max) : "", signed: !!v.signed, delta: !!v.delta, note: v.note || "",
      solve: out.has(v.key), units: v.units || null,
    })),
    equations: (doc.equations || []).map((e) => ({ title: e.title || "", text: e.text || "" })),
    functions: (doc.functions || []).map((f) => ({ name: f.name || "", args: (f.args || []).join(", "), body: f.body || "" })),
    tables: (doc.tables || []).map((t) => ({ name: t.name || "", x_unit: t.x_unit === "1" ? "" : t.x_unit || "", y_unit: t.y_unit === "1" ? "" : t.y_unit || "",
      method: t.method || "linear", outside: t.outside || "error", points: (t.x || []).map((x, k) => `${x}, ${(t.y || [])[k]}`).join("\n") })),
    odes: (doc.odes || []).map((o) => ({ title: o.title || "", independent: o.independent || "", start: o.start ?? "0", method: o.method || "auto",
      equations: (o.equations || []).join("\n"), initial: (o.initial || []).join("\n"),
      kind: o.time ? "pde" : o.second ? "steady2d" : (o.boundary && o.boundary.length) ? "boundary" : "initial", second: o.second || "", second_start: o.second_start ?? "0", second_end: o.second_end || "", third: o.third || "", third_start: o.third_start ?? "0", third_end: o.third_end || "", time: o.time || "", nodes: o.nodes ? String(o.nodes) : "", end: o.end || "", boundary: (o.boundary || []).join("\n"), guess: (o.guess || []).join("\n"), unknowns: (o.unknowns || []).join(", "),
      statistics: (o.statistics || []).map((q) => `${q.kind} ${q.of}${q.level ? " : " + q.level : q.p ? " : " + q.p : ""} -> ${q.var}`).join("\n"),
      paths: o.paths ? String(o.paths) : "", steps: o.steps && !o.time ? String(o.steps) : "", seed: o.seed != null ? String(o.seed) : "",
      cutouts: o.cutouts && o.cutouts.length ? JSON.stringify(o.cutouts, null, 1) : "", scheme: o.scheme || "", moving: o.moving ? `${o.moving.front} : ${o.moving.rate}` : "", dry: o.dry ? `${o.dry.depth} : ${(o.dry.zero || []).join(", ")}${o.dry.tol ? " : " + o.dry.tol : ""}` : "", periodic: (o.periodic || []).join(", "), sources: (o.sources || []).map((q) => `${q.field} @ ${q.at}${q.at_second ? ", " + q.at_second : ""}${q.at_third ? ", " + q.at_third : ""} : ${q.rate}`).join("\n"),
      events: (o.events || []).map((e) => ({ title: e.title || "", when: e.when || "", direction: e.direction || "either", terminal: !!e.terminal, time: e.time || "",
        values: Object.entries(e.values || {}).map(([k, v]) => `${k} = ${v}`).join("\n"),
        reset: Object.entries(e.reset || {}).map(([k, v]) => `${k} = ${v}`).join("\n") })), algebraic: (o.algebraic || []).join(", ") })),
    assumptions: (doc.assumptions || []).join("\n"), references: (doc.references || []).join("\n"),
    validity: (doc.validity || []).map((x) => `${x.condition} | ${x.message}`).join("\n"),
  };
}

function draftToDoc(d) {
  const variables = d.variables.map((v) => {
    const o = { key: v.key.trim(), label: v.label.trim(), unit: v.unit.trim() || "1" };
    if (v.latex.trim()) o.latex = v.latex.trim();
    if (v.role === "constant") o.constant = num(v.value) ?? "";
    else {
      const dv = num(v.value);
      if (dv !== undefined) o.default = dv;
      const dims = v.shape.trim() ? v.shape.trim().split(/[x×,\s]+/).map(Number).filter((n) => Number.isInteger(n) && n > 0) : [];
      if (dims.length) o.shape = dims;
      if (v.example.trim()) o.example = dims.length ? v.example.split(";").map((t) => t.trim()) : v.example.trim();
    }
    for (const k of ["min", "max"]) if (num(v[k]) !== undefined) o[k] = num(v[k]);
    if (v.signed) o.signed = true;
    if (v.delta) o.delta = true;
    if (v.note.trim()) o.note = v.note.trim();
    if (v.units) o.units = v.units;
    return o;
  });
  return {
    id: d.id || "custom.draft", name: d.name.trim(), description: d.description.trim(), author: d.author.trim(),
    disciplines: d.disciplines, subdisciplines: d.subdisciplines, tags: d.tags,
    variables,
    equations: d.equations.filter((e) => e.text.trim() || e.title.trim()).map((e) => ({ title: e.title.trim(), text: e.text.trim() })),
    ...(d.functions.some((f) => f.name.trim()) ? { functions: d.functions.filter((f) => f.name.trim()).map((f) => ({ name: f.name.trim(), args: f.args.split(",").map((a) => a.trim()).filter(Boolean), body: f.body.trim() })) } : {}),
    ...(d.tables.some((t) => t.name.trim()) ? { tables: d.tables.filter((t) => t.name.trim()).map((t) => {
      const rows = t.points.split("\n").map((l) => l.split(/[,;\t ]+/).filter((c) => c !== "").map(Number)).filter((r) => r.length >= 2);
      return { name: t.name.trim(), x_unit: t.x_unit.trim() || "1", y_unit: t.y_unit.trim() || "1", method: t.method, outside: t.outside, x: rows.map((r) => r[0]), y: rows.map((r) => r[1]) };
    }) } : {}),
    ...(d.odes.some((o) => o.equations.trim()) ? { odes: d.odes.filter((o) => o.equations.trim()).map((o) => ({
      title: o.title.trim(), independent: o.independent.trim(), start: String(o.start).trim() || "0", method: o.method,
      equations: lines(o.equations),
      ...(o.kind === "boundary" ? { end: String(o.end).trim(), boundary: lines(o.boundary), ...(lines(o.guess).length ? { guess: lines(o.guess) } : {}),
            ...(o.unknowns.trim() ? { unknowns: o.unknowns.split(/[,\s]+/).filter(Boolean) } : {}) }
        : o.kind === "steady2d" ? { end: String(o.end).trim(), second: o.second.trim(), second_start: String(o.second_start).trim() || "0", second_end: String(o.second_end).trim(), boundary: lines(o.boundary),
            ...(o.third && o.third.trim() ? { third: o.third.trim(), third_start: String(o.third_start).trim() || "0", third_end: String(o.third_end).trim() } : {}),
            ...cutoutsOf(o.cutouts),
            ...(lines(o.guess).length ? { guess: lines(o.guess).slice(0, 4) } : {}), ...(String(o.nodes).trim() ? { nodes: Number(o.nodes) } : {}) }
        : o.kind === "pde" ? { end: String(o.end).trim(), time: o.time.trim(), boundary: lines(o.boundary), initial: lines(o.initial), ...(String(o.nodes).trim() ? { nodes: Number(o.nodes) } : {}),
            ...(o.second && o.second.trim() ? { second: o.second.trim(), second_start: String(o.second_start).trim() || "0", second_end: String(o.second_end).trim() } : {}),
            ...(o.second && o.second.trim() && o.third && o.third.trim() ? { third: o.third.trim(), third_start: String(o.third_start).trim() || "0", third_end: String(o.third_end).trim() } : {}),
            ...cutoutsOf(o.cutouts),
            ...(o.moving && o.moving.includes(":") ? { moving: { front: o.moving.split(":")[0].trim(), rate: o.moving.slice(o.moving.indexOf(":") + 1).trim() } } : {}),
            ...(o.scheme === "conservative" ? { scheme: "conservative" } : {}),
            ...(o.scheme === "conservative" && o.dry && o.dry.trim() ? { dry: (([d, z, tol]) => ({ depth: d.trim(), zero: (z || "").split(/[,\s]+/).filter(Boolean), ...(tol && tol.trim() ? { tol: tol.trim() } : {}) }))(o.dry.split(":")) } : {}),
            ...(o.periodic && o.periodic.trim() ? { periodic: o.periodic.split(",").map((x) => x.trim()).filter(Boolean) } : {}),
            ...(lines(o.sources || "").length ? { sources: lines(o.sources).map((l) => { const m = l.match(/^\s*(\w+)\s*@\s*([^:,]+?)\s*(?:,\s*([^:,]+?))?\s*(?:,\s*([^:]+?))?\s*:\s*(.+)$/); return m ? { field: m[1], at: m[2], ...(m[3] ? { at_second: m[3] } : {}), ...(m[4] ? { at_third: m[4] } : {}), rate: m[5].trim() } : { field: "", at: "", rate: l }; }) } : {}) }
        : { initial: lines(o.initial) }),
      ...(o.kind === "initial" && o.events.some((e) => e.when.trim()) ? { events: o.events.filter((e) => e.when.trim()).map((e) => ({
        title: e.title.trim(), when: e.when.trim(), direction: e.direction, terminal: e.terminal, ...(e.time.trim() ? { time: e.time.trim() } : {}),
        ...(lines(e.values).length ? { values: Object.fromEntries(lines(e.values).map((l) => l.split("=").map((x) => x.trim())).filter((p) => p.length === 2)) } : {}),
        ...(lines(e.reset).length ? { reset: Object.fromEntries(lines(e.reset).map((l) => { const k = l.indexOf("="); return [l.slice(0, k).trim(), l.slice(k + 1).trim()]; }).filter((p) => p[0] && p[1])) } : {}) })) } : {}),
      ...(o.algebraic && o.algebraic.trim() ? { algebraic: o.algebraic.split(",").map((x) => x.trim()).filter(Boolean) } : {}),
      ...(lines(o.statistics || "").length ? { statistics: lines(o.statistics).map((l) => { const m = l.match(/^\s*(\w+)\s+(\w+)\s*(?::\s*([^>]+?))?\s*->\s*(\w+)\s*$/); if (!m) return { kind: l, of: "", var: "" };
          return { kind: m[1], of: m[2], var: m[4], ...(m[1] === "quantile" ? (m[3] ? { p: m[3].trim() } : {}) : (m[3] ? { level: m[3].trim() } : {})) }; }) } : {}),
      ...(String(o.paths || "").trim() ? { paths: Number(o.paths) } : {}), ...(o.kind === "initial" && String(o.steps || "").trim() ? { steps: Number(o.steps) } : {}), ...(String(o.seed || "").trim() ? { seed: Number(o.seed) } : {}) })) } : {}),
    outputs: d.variables.filter((v) => v.solve && v.role !== "constant").map((v) => v.key.trim()),
    assumptions: lines(d.assumptions), references: lines(d.references),
    validity: lines(d.validity).map((l) => { const [c, ...m] = l.split("|"); return { condition: c.trim(), message: m.join("|").trim() }; }),
  };
}

function download(name, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2) + "\n"], { type: "application/json" });
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function initCustom(root, ctx) {
  const { call, S } = ctx;
  const fileIn = h("input", { type: "file", accept: "application/json,.json", multiple: true, hidden: true, onchange: onImportFiles });

  async function show(route) {
    if (route.mode === "edit" || route.mode === "new") return showEditor(route);
    return showList();
  }

  // ---------------------------------------------------------------- list
  async function showList(report) {
    const { calculations: items, storage } = await call("custom_list");
    clear(root);
    const where = storage.kind === "folder"
      ? h("p", { class: "hint" }, "Saved as plain JSON files in ", h("code", {}, storage.path), ". Copy them to another computer, or share them, and they will appear here.")
      : h("p", { class: "hint" }, "Saved in this browser only. Use ", h("b", {}, "Export"), " to keep a file you can back up, move to another browser or share; ", h("b", {}, "Import"), " loads such a file.");
    root.append(
      h("div", { class: "panel" },
        h("h2", {}, "My equations"),
        h("p", {}, "Define your own calculations and use them like the built-in ones: solve for any variable, see worked steps with units, and wire them into System Design. Units are checked for dimensional consistency when you save, but the physics is yours — they are labelled ", h("em", {}, "custom"), " everywhere."),
        where,
        h("div", { class: "toolbar" },
          h("a", { class: "btn primary", href: "#/mine/new" }, "New equation"),
          h("button", { type: "button", class: "btn", onclick: () => fileIn.click() }, "Import file…"),
          h("button", { type: "button", class: "btn", disabled: !items.length, onclick: exportAll }, "Export all"),
          fileIn),
        h("p", { class: "hint" }, "Tip: open any built-in calculation and press ", h("b", {}, "Copy to My equations"), " to start from it."),
      ),
      report ? importReport(report) : null,
      h("div", { class: "cust-list" }, items.length ? items.map(card) : h("p", { class: "empty" }, "You have not created any equations yet.")),
    );
  }

  function card(d) {
    return h("div", { class: "panel cust-card", dataset: { id: d.id } },
      h("div", { class: "title-row" }, h("h3", {}, d.name), h("span", { class: "badge custom" }, "custom"), ...d.disciplines.map((x) => h("span", { class: "badge" }, x))),
      h("p", { class: "desc" }, d.description || h("em", {}, "No description")),
      h("div", { class: "eq-line" }, ...d.equations.slice(0, 3).map((e) => h("code", {}, e.text))),
      h("div", { class: "toolbar" },
        h("a", { class: "btn primary", href: `#/calc/${encodeURIComponent(d.id)}` }, "Open"),
        h("a", { class: "btn", href: `#/mine/edit/${encodeURIComponent(d.id)}` }, "Edit"),
        h("a", { class: "btn", href: `#/mine/new?from=${encodeURIComponent(d.id)}` }, "Duplicate"),
        h("button", { type: "button", class: "btn", onclick: () => exportOne(d.id) }, "Export file"),
        h("button", { type: "button", class: "btn danger", onclick: () => remove(d) }, "Delete")));
  }

  async function remove(d) {
    if (!confirm(`Delete “${d.name}”? System Design graphs that use it will no longer open that block.`)) return;
    try { await call("custom_delete", { calc_id: d.id }); } catch (e) { flash(e.message); return; }
    await ctx.changed();
    flash("Deleted");
    showList();
  }
  async function exportOne(id) { const r = await call("custom_export", { ids: [id] }); download(r.filename, r.document); }
  async function exportAll() { const r = await call("custom_export", {}); download(r.filename, r.document); }

  async function onImportFiles(e) {
    const files = [...e.target.files];
    e.target.value = "";
    const results = [];
    for (const f of files) {
      let doc;
      try { doc = JSON.parse(await f.text()); } catch (err) { results.push({ file: f.name, name: f.name, status: "error", errors: [{ field: "file", message: "not valid JSON: " + err.message }] }); continue; }
      try {
        const probe = await call("custom_import", { document: doc, on_conflict: "ask", dry_run: true });
        const conflicts = probe.results.filter((r) => r.status === "conflict");
        let mode = "rename";
        if (conflicts.length) {
          const names = conflicts.map((r) => r.name).join(", ");
          mode = confirm(`${conflicts.length} equation(s) in ${f.name} already exist with different content (${names}).\n\nOK = replace yours with the file's version\nCancel = keep both (the file's copy is renamed)`) ? "replace" : "rename";
        }
        const done = await call("custom_import", { document: doc, on_conflict: mode });
        results.push(...done.results.map((r) => ({ ...r, file: f.name })));
      } catch (err) {
        results.push({ file: f.name, name: f.name, status: "error", errors: err.details || [{ field: "file", message: err.message }] });
      }
    }
    await ctx.changed();
    showList(results);
  }

  function importReport(rows) {
    return h("div", { class: "panel" }, h("h3", {}, "Import result"),
      h("ul", { class: "report" }, rows.map((r) => h("li", { class: r.status === "error" ? "bad" : "" },
        h("b", {}, r.name || r.id), ` (${r.file}): ${r.status}${r.new_id ? ` → ${r.new_id}` : ""}`,
        r.errors ? h("ul", {}, r.errors.map((x) => h("li", {}, `${x.field}: ${x.message}`))) : null))));
  }

  // ---------------------------------------------------------------- editor
  async function showEditor(route) {
    let draft, editingId = null, fromLive = null;
    try {
      if (route.mode === "edit") {
        const { calculations } = await call("custom_list");
        const doc = calculations.find((c) => c.id === route.id);
        if (!doc) throw new Error(`“${route.id}” is not one of your equations`);
        draft = docToDraft(doc);
        editingId = doc.id;
      } else if (route.from) {
        draft = docToDraft((await call("custom_template", { calc_id: route.from })).calculation);
      } else if (route.draft && S.customDraft) {
        fromLive = S.customDraft;      // an equation sent from LiveCalc
        draft = docToDraft(fromLive.calculation);
      } else {
        draft = docToDraft({ variables: [], equations: [{ title: "", text: "" }] });
        draft.variables = [{ ...blankVar(), solve: true }, blankVar(), blankVar()];
      }
    } catch (e) {
      clear(root).append(h("div", { class: "panel" }, h("p", {}, e.message), h("a", { class: "btn", href: "#/mine" }, "Back")));
      return;
    }

    const disciplineBox = h("div", {});
    const subBox = h("div", {});
    const varsBox = h("div", { class: "cust-vars" });
    const eqBox = h("div", { class: "cust-eqs" });
    const odeBox = h("div", { class: "cust-odes" });
    const tableBox = h("div", { class: "cust-odes" });
    const funcBox = h("div", { class: "cust-odes" });
    const varList = h("datalist", { id: "cust-varkeys" });
    const check = h("div", { class: "cust-check" });
    const changedSoon = debounce(validate, 350);
    const touch = () => changedSoon();
    const bind = (obj, key, extra = {}) => (el) => { el.value = obj[key]; el.addEventListener("input", () => { obj[key] = el.value; touch(); }); Object.entries(extra).forEach(([k, v]) => el.setAttribute(k, v)); return el; };
    const text = (obj, key, attrs = {}) => bind(obj, key, attrs)(h("input", { class: "field", type: "text", autocomplete: "off", spellcheck: false }));
    const area = (obj, key, attrs = {}) => bind(obj, key, attrs)(h("textarea", { class: "field", rows: 3 }));
    const labelled = (title, control, hint) => h("label", { class: "cust-f" }, h("span", {}, title), control, hint ? h("small", {}, hint) : null);

    function renderDisciplines() {
      clear(disciplineBox);
      const mk = (d) => h("button", { type: "button", class: "chip", "aria-pressed": String(draft.disciplines.includes(d.id)), onclick: () => {
        const i = draft.disciplines.indexOf(d.id);
        i >= 0 ? draft.disciplines.splice(i, 1) : draft.disciplines.push(d.id);
        renderDisciplines(); touch();
      } }, d.name);
      const core = S.meta.disciplines.filter((d) => d.group === "core");
      const more = S.meta.disciplines.filter((d) => d.group !== "core");
      disciplineBox.append(
        h("div", { class: "chips", role: "group", "aria-label": "Disciplines" }, core.map(mk)),
        h("details", { open: more.some((d) => draft.disciplines.includes(d.id)) }, h("summary", {}, "Emerging and interdisciplinary fields"), h("div", { class: "chips" }, more.map(mk))));
    }
    function renderSubs() {
      clear(subBox);
      const dl = h("datalist", { id: "cust-subs" }, S.meta.subdisciplines.map((s) => h("option", { value: s.name })));
      const input = h("input", { class: "field", type: "text", list: "cust-subs", placeholder: "optional — type a sub-discipline and press Enter", onkeydown: (e) => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        const v = input.value.trim();
        const known = S.meta.subdisciplines.find((s) => s.name.toLowerCase() === v.toLowerCase());
        if (!known) { flash("Pick a sub-discipline from the list"); return; }
        if (!draft.subdisciplines.includes(known.name)) draft.subdisciplines.push(known.name);
        renderSubs(); touch();
      } });
      subBox.append(input, dl, h("div", { class: "chips" }, draft.subdisciplines.map((s) =>
        h("button", { type: "button", class: "chip token", title: "Remove", onclick: () => { draft.subdisciplines.splice(draft.subdisciplines.indexOf(s), 1); renderSubs(); touch(); } }, s, " ×"))));
    }
    function renderVars() {
      clear(varsBox);
      draft.variables.forEach((v, i) => {
        const role = h("select", { class: "field", "aria-label": "Role", onchange: (e) => { v.role = e.target.value; renderVars(); touch(); } },
          h("option", { value: "input", selected: v.role === "input" }, "Variable"), h("option", { value: "constant", selected: v.role === "constant" }, "Constant"));
        const solve = h("label", { class: "cust-solve", title: "Solved for when the equation is first opened" }, h("input", { type: "checkbox", checked: v.solve, disabled: v.role === "constant", onchange: (e) => { v.solve = e.target.checked; touch(); } }), "solve for");
        const adv = h("details", { class: "cust-adv" }, h("summary", {}, "More"),
          h("div", { class: "cust-grid" },
            labelled("LaTeX symbol", text(v, "latex", { placeholder: "e.g. \\\\rho_0" })),
            labelled("Minimum", text(v, "min")), labelled("Maximum", text(v, "max")),
            labelled("Note", text(v, "note")),
            labelled("Vector / matrix size", text(v, "shape", { placeholder: "3 for a vector, 2x2 for a matrix (components F_1, F_2 …); example values separated by ;" })),
            h("label", { class: "cust-check1" }, h("input", { type: "checkbox", checked: v.signed, onchange: (e) => { v.signed = e.target.checked; touch(); } }), "may be negative"),
            h("label", { class: "cust-check1" }, h("input", { type: "checkbox", checked: v.delta, onchange: (e) => { v.delta = e.target.checked; touch(); } }), "temperature difference (ΔT)")));
        varsBox.append(h("div", { class: "cust-var", dataset: { i } },
          h("div", { class: "cust-grid" },
            labelled("Symbol", text(v, "key", { placeholder: "F", "data-field": `variables[${i}].key` })),
            labelled("Name", text(v, "label", { placeholder: "Force", "data-field": `variables[${i}].label` })),
            labelled("Unit", text(v, "unit", { placeholder: "N, kPa, m^3/s … (blank = none)", "data-field": `variables[${i}].unit` })),
            labelled("Kind", role),
            v.role === "constant"
              ? labelled("Constant value", text(v, "value", { placeholder: "9.80665", "data-field": `variables[${i}].constant` }))
              : labelled("Default value", text(v, "value", { placeholder: "optional", "data-field": `variables[${i}].default` })),
            v.role === "constant" ? h("span") : labelled("Example value", text(v, "example", { placeholder: "e.g. 250 kN" })),
            solve,
            h("button", { type: "button", class: "btn small danger", title: "Remove this variable", onclick: () => { draft.variables.splice(i, 1); renderVars(); touch(); } }, "Remove")),
          adv));
      });
      varsBox.append(h("button", { type: "button", class: "btn", onclick: () => { draft.variables.push(blankVar()); renderVars(); } }, "+ Add variable"));
      clear(varList).append(...draft.variables.filter((x) => x.key.trim()).map((x) => h("option", { value: x.key.trim() })));
    }
    function renderEqs() {
      clear(eqBox);
      draft.equations.forEach((e, i) => eqBox.append(h("div", { class: "cust-eq" },
        text(e, "title", { placeholder: "Title (optional)", "aria-label": "Equation title" }),
        text(e, "text", { placeholder: "F = k*x", class: "field mono", "aria-label": "Equation", "data-field": `equations[${i}].text` }),
        h("button", { type: "button", class: "btn small danger", onclick: () => { draft.equations.splice(i, 1); renderEqs(); touch(); } }, "Remove"))));
      eqBox.append(h("button", { type: "button", class: "btn", onclick: () => { draft.equations.push({ title: "", text: "" }); renderEqs(); } }, "+ Add equation"));
    }

    function renderOdes() {
      clear(odeBox);
      draft.odes.forEach((o, i) => odeBox.append(h("div", { class: "cust-var" },
        h("div", { class: "cust-grid" },
          labelled("Title", text(o, "title", { placeholder: "e.g. Newton cooling" })),
          labelled("Independent variable", text(o, "independent", { placeholder: "t", list: "cust-varkeys", "data-field": `odes[${i}].independent` }), "usually time"),
          labelled("Starts at", text(o, "start", { placeholder: "0", "data-field": `odes[${i}].start` }), "a number or a variable"),
          labelled("Solve", h("select", { class: "field", onchange: (e) => { o.method = e.target.value; touch(); } },
            [["auto", "closed form if possible, else numerically"], ["numeric", "numerically only"], ["symbolic", "closed form only"]].map(([v, t]) => h("option", { value: v, selected: o.method === v }, t)))),
          h("button", { type: "button", class: "btn small danger", onclick: () => { draft.odes.splice(i, 1); renderOdes(); touch(); } }, "Remove")),
        labelled("Differential equations — one per line, one for each differentiated quantity", area(o, "equations", { placeholder: "diff(T, t) = -k*(T - Ta)\ndiff(x, t, 2) = -w**2*x", "data-field": `odes[${i}].equations` })),
        labelled("Conditions", h("select", { class: "field", onchange: (e) => { o.kind = e.target.value; renderOdes(); touch(); } },
          [["initial", "initial values at the start (initial-value problem)"], ["boundary", "conditions at positions of an interval (boundary-value problem)"], ["pde", "space and time (partial differential equation)"], ["steady2d", "steady problem on a rectangle (2-D partial differential equation)"]].map(([v, t]) => h("option", { value: v, selected: o.kind === v }, t)))),
        o.kind === "steady2d" ? h("div", {},
          labelled("Second space variable", text(o, "second", { placeholder: "y", list: "cust-varkeys", "data-field": `odes[${i}].second` }), "the independent variable above is the first; the quantity means its value at the point (first, second) you enter"),
          labelled("First interval ends at", text(o, "end", { placeholder: "a", "data-field": `odes[${i}].end` }), "it starts at ‘Starts at’"),
          labelled("Second interval starts at", text(o, "second_start", { placeholder: "0", "data-field": `odes[${i}].second_start` })),
          labelled("Second interval ends at", text(o, "second_end", { placeholder: "b", "data-field": `odes[${i}].second_end` })),
          labelled("Third space variable (optional: a three-dimensional box; sides also front, back)", text(o, "third", { placeholder: "z", list: "cust-varkeys", "data-field": `odes[${i}].third` })),
          labelled("Third interval starts at", text(o, "third_start", { placeholder: "0" })),
          labelled("Third interval ends at", text(o, "third_end", { placeholder: "c", "data-field": `odes[${i}].third_end` })),
          labelled("Boundary conditions — one each for left, right, bottom, top (and front, back in 3-D), for every field", area(o, "boundary", { placeholder: "left: T = T0\nright: diff(T, x) = 0\nbottom: T = T0\ntop: -k*diff(T, y) = h*(T - Tinf)", "data-field": `odes[${i}].boundary` }),
            "left/right are the ends of the first interval; each is a value or a relation with the slope across that side; the value may depend on the coordinate along the side"),
          labelled("Cutouts (optional): rectangles removed from the region — JSON list", area(o, "cutouts", { placeholder: `[{"x0": "a/2", "x1": "a", "y0": "b/2", "y1": "b", "boundary": ["left: diff(T, x) = 0", "bottom: T = Ts"]}]`, "data-field": `odes[${i}].cutouts` }),
            "an L-shape or a plate with a hole; the edges snap to the grid; give a condition for each side of the rectangle that lies inside the region (left/right/bottom/top of the removed rectangle); steady problems with cutouts take several fields (one equation each, conditions for each field)"),
          labelled("Starting guess (optional, nonlinear problems)", area(o, "guess", { placeholder: "T = 300 K", "data-field": `odes[${i}].guess` })),
          labelled("Grid intervals (optional)", text(o, "nodes", { placeholder: "40", "data-field": `odes[${i}].nodes` }), "8 to 100 per direction (6 to 28 in three dimensions)")) : null,
        o.kind === "pde" ? h("div", {},
          labelled("Time variable", text(o, "time", { placeholder: "t", list: "cust-varkeys", "data-field": `odes[${i}].time` }), "the independent variable above is then the space coordinate; time starts at 0"),
          labelled("Interval ends at", text(o, "end", { placeholder: "L", "data-field": `odes[${i}].end` }), "the space interval runs from ‘Starts at’ to here; the quantity then means its value at the position and time you enter"),
          labelled("Boundary conditions — exactly one ‘start:’ and one ‘end:’", area(o, "boundary", { placeholder: "start: T = Ts\nend: -k*diff(T, x) = h*(T - Tinf)", "data-field": `odes[${i}].boundary` }), "a value, or any relation involving the slope"),
          labelled("Initial state at time 0 — one per line", area(o, "initial", { placeholder: "T = Ti + (T1 - Ti)*x/L\ndiff(u, t) = 0", "data-field": `odes[${i}].initial` }), "may depend on the position; second-order (wave) equations also need the initial rate"),
          labelled("Grid intervals (optional)", text(o, "nodes", { placeholder: "100", "data-field": `odes[${i}].nodes` }), "10 to 400 (8 to 120 per direction in two dimensions); more is more accurate and slower"),
          h("details", { class: "cust-adv" }, h("summary", {}, "Coupled fields, a second space direction, periodic and point-source options"),
            h("p", { class: "hint" }, "Several fields: one equation per line above, and a start/end condition for each field, e.g. ", h("code", {}, "start: u = 0"), ". A second space variable makes the problem two-dimensional (sides left/right/bottom/top)."),
            labelled("Second space variable (optional)", text(o, "second", { placeholder: "y", list: "cust-varkeys", "data-field": `odes[${i}].second` })),
            labelled("Second interval starts at", text(o, "second_start", { placeholder: "0" })),
            labelled("Second interval ends at", text(o, "second_end", { placeholder: "b", "data-field": `odes[${i}].second_end` })),
            labelled("Moving end (optional, Stefan problem): front variable : speed of the front", text(o, "moving", { placeholder: "s : -k*diff(T, x)/(rho*Lf)", "data-field": `odes[${i}].moving` }), "the interval ends at ‘Ends at’ initially; the variable receives the front position; diff(T, x) in the speed is the slope at the front"),
            labelled("Third space variable (optional, three dimensions: sides also front/back)", text(o, "third", { placeholder: "z", list: "cust-varkeys", "data-field": `odes[${i}].third` })),
            labelled("Third interval starts at", text(o, "third_start", { placeholder: "0" })),
            labelled("Third interval ends at", text(o, "third_end", { placeholder: "c", "data-field": `odes[${i}].third_end` })),
            labelled("Cutouts (optional, two dimensions): rectangles removed — JSON list", area(o, "cutouts", { placeholder: `[{"x0": "a/2", "x1": "a", "y0": "b/2", "y1": "b", "boundary": ["left: diff(T, x) = 0", "bottom: T = Ts"]}]`, "data-field": `odes[${i}].cutouts` }), "an L-shape or a plate with a hole; conditions for the sides of each removed rectangle that lie inside the region"),
            h("label", { class: "cust-check1" }, h("input", { type: "checkbox", checked: o.scheme === "conservative", onchange: (e) => { o.scheme = e.target.checked ? "conservative" : ""; touch(); } }),
              "conservation form with shocks: write diff(u, t) + diff(flux, x) = 0 (shock-capturing finite volumes; boundary values or ‘diff(u, x) = 0’ for outflow)"),
            o.scheme === "conservative" ? labelled("Dry bed (optional): depth field : momentum fields : tolerance", text(o, "dry", { placeholder: "h : q : 1e-6", "data-field": `odes[${i}].dry` }), "for shallow water over a dry bed: the depth stays non-negative and the momentum vanishes where the depth is below the tolerance") : null,
            labelled("Periodic space variables (optional, comma separated)", text(o, "periodic", { placeholder: "x", "data-field": `odes[${i}].periodic` }), "every field repeats along them: no conditions on those sides"),
            labelled("Point sources (optional) — one per line: field @ position [, second position] : rate", area(o, "sources", { placeholder: "T @ x0 : P/(rho*c*A)", "data-field": `odes[${i}].sources` }), "rate has the field's units times length (times length) per time"))) : null,
        o.kind === "boundary" ? h("div", {},
          labelled("Interval ends at", text(o, "end", { placeholder: "L", "data-field": `odes[${i}].end` }), "a number or a variable; the interval runs from ‘Starts at’ to here. The independent variable is then the position you want the answer at"),
          labelled("Boundary conditions — one per line, ‘where: condition’", area(o, "boundary", { placeholder: "start: T = Tb\nend: -k*diff(T, x) = h*(T - Tinf)", "data-field": `odes[${i}].boundary` }),
            "‘where’ is start, end or a position (an expression). One condition per order of the equations. Robin conditions such as the one above are fine"),
          labelled("Unknown parameters (optional) — variable names, comma separated", text(o, "unknowns", { placeholder: "e.g. P", "data-field": `odes[${i}].unknowns` }),
            "parameters found together with the solution: an eigenvalue (buckling load, frequency, energy) or a constant fitted by extra conditions. Each needs one more boundary condition (an eigenvalue also a normalisation such as ‘L/2: y = a’) and a starting guess below; list them as outputs"),
          labelled("Starting guess (optional) — one per line", area(o, "guess", { placeholder: "T = 300 K\ndiff(T, x) = 0\ny = a*sin(pi*x/L)", "data-field": `odes[${i}].guess` }),
            "a value (‘y = 1’), a slope, a whole starting shape that depends on the independent variable (‘y = a*sin(pi*x/L)’), and a value for each unknown parameter (‘P = 1.3*pi**2*E*I/L**2’): Newton's method finds the solution nearest to it, so for an eigenproblem it picks the mode")) : null,
        o.kind === "initial" ? labelled("Algebraic variables (optional) — constraints without a derivative, fixed at every instant", text(o, "algebraic", { placeholder: "e.g. i", list: "cust-varkeys", "data-field": `odes[${i}].algebraic` }), "write one constraint per name among the equations, e.g. i*R = Vs - Vc") : null,
        o.kind === "initial" ? h("details", { class: "cust-adv" }, h("summary", {}, "Stochastic equation (white noise xi1, xi2, xi3): statistics to report"),
          h("p", { class: "hint" }, "With a noise term such as ", h("code", {}, "sigma*xi1"), " the unknown is random, so you choose what to report. One per line: ", h("code", {}, "mean x -> xm"), ", ", h("code", {}, "std x -> xs"),
            ", ", h("code", {}, "above x : xc -> pexc"), " (probability of exceeding a level), ", h("code", {}, "quantile x : 0.95 -> x95"), "."),
          labelled("Statistics", area(o, "statistics", { placeholder: "mean x -> xm\nstd x -> xs\nabove x : xc -> pexc", "data-field": `odes[${i}].statistics` })),
          labelled("Paths (optional)", text(o, "paths", { placeholder: "20000" })), labelled("Time steps (optional)", text(o, "steps", { placeholder: "400" })), labelled("Random seed (optional)", text(o, "seed", { placeholder: "12345" }))) : null,
        o.kind === "initial" ? labelled("Initial values at the start — one per line", area(o, "initial", { placeholder: "T = T0\ndiff(x, t) = v0", "data-field": `odes[${i}].initial` })) : null,
        o.kind !== "initial" ? null : h("details", { class: "cust-adv", open: o.events.length > 0 }, h("summary", {}, `Events — stop or mark where a condition is met (${o.events.length})`),
          ...o.events.map((e, j) => h("div", { class: "cust-var" },
            h("div", { class: "cust-grid" },
              labelled("Name", text(e, "title", { placeholder: "e.g. ground" })),
              labelled("Condition (crosses zero)", text(e, "when", { placeholder: "h = 0", "data-field": `odes[${i}].events[${j}].when` })),
              labelled("Direction", h("select", { class: "field", onchange: (ev) => { e.direction = ev.target.value; touch(); } },
                [["either", "either way"], ["falling", "falling through zero"], ["rising", "rising through zero"]].map(([v, t]) => h("option", { value: v, selected: e.direction === v }, t)))),
              h("label", { class: "cust-check1" }, h("input", { type: "checkbox", checked: e.terminal, onchange: (ev) => { e.terminal = ev.target.checked; touch(); } }), "stop the integration here"),
              labelled("Variable for the event time", text(e, "time", { placeholder: "e.g. tf", list: "cust-varkeys", "data-field": `odes[${i}].events[${j}].time` })),
              h("button", { type: "button", class: "btn small danger", onclick: () => { o.events.splice(j, 1); renderOdes(); touch(); } }, "Remove")),
            labelled("State at the event — one per line: quantity = variable", area(e, "values", { placeholder: "x = R\nvy = vi", "data-field": `odes[${i}].events[${j}].values` })),
            labelled("Jump at the event (impulsive) — one per line: quantity = new value; the run then continues", area(e, "reset", { placeholder: "diff(h, t) = -e*diff(h, t)\nu = 1", "data-field": `odes[${i}].events[${j}].reset` }), "not with ‘stop the integration here’"))),
          h("button", { type: "button", class: "btn", onclick: () => { o.events.push({ title: "", when: "", direction: "either", terminal: false, time: "", values: "", reset: "" }); renderOdes(); } }, "+ Add an event"),
          h("p", { class: "hint" }, "Events are located precisely between steps and need the numerical solver. The time ", h("code", {}, "t"), " you enter becomes the longest time to simulate; "
            + "with “stop” ticked the quantities are reported at the event if it happens first.")))));
      odeBox.append(h("button", { type: "button", class: "btn", onclick: () => { draft.odes.push({ title: "", independent: "t", start: "0", method: "auto", equations: "", initial: "", kind: "initial", time: "", nodes: "", end: "", boundary: "", guess: "", unknowns: "", events: [], algebraic: "", statistics: "", paths: "", steps: "", seed: "", scheme: "", cutouts: "", moving: "", dry: "", periodic: "", sources: "", second: "", second_start: "0", second_end: "", third: "", third_start: "0", third_end: "" }); renderOdes(); } }, "+ Add a differential equation"));
    }

    function renderFuncs() {
      clear(funcBox);
      draft.functions.forEach((f, i) => funcBox.append(h("div", { class: "cust-var" },
        h("div", { class: "cust-grid" },
          labelled("Function name", text(f, "name", { placeholder: "fsj", "data-field": `functions[${i}].name` })),
          labelled("Arguments (comma separated)", text(f, "args", { placeholder: "Re, rel", "data-field": `functions[${i}].args` })),
          h("button", { type: "button", class: "btn small danger", onclick: () => { draft.functions.splice(i, 1); renderFuncs(); touch(); } }, "Remove")),
        labelled("Body — an expression of the arguments, the variables and the functions above", text(f, "body", { placeholder: "0.25/log10(rel/3.7 + 5.74/Re**0.9)**2", "data-field": `functions[${i}].body` })))));
      funcBox.append(h("button", { type: "button", class: "btn", onclick: () => { draft.functions.push({ name: "", args: "", body: "" }); renderFuncs(); } }, "+ Add a function"));
    }

    function renderTables() {
      clear(tableBox);
      draft.tables.forEach((t, i) => tableBox.append(h("div", { class: "cust-var" },
        h("div", { class: "cust-grid" },
          labelled("Function name", text(t, "name", { placeholder: "pump", "data-field": `tables[${i}].name` }), "used in equations as name(x)"),
          labelled("x unit", text(t, "x_unit", { placeholder: "L/s" })), labelled("y unit", text(t, "y_unit", { placeholder: "m" })),
          labelled("Interpolation", h("select", { class: "field", onchange: (e) => { t.method = e.target.value; touch(); } },
            [["linear", "straight lines"], ["pchip", "smooth, monotone (pchip)"], ["loglog", "straight on log-log axes"]].map(([v, l]) => h("option", { value: v, selected: t.method === v }, l)))),
          labelled("Outside the data", h("select", { class: "field", onchange: (e) => { t.outside = e.target.value; touch(); } },
            [["error", "no answer"], ["clamp", "hold the end value"], ["extrapolate", "continue the end segment"]].map(([v, l]) => h("option", { value: v, selected: t.outside === v }, l)))),
          h("button", { type: "button", class: "btn small danger", onclick: () => { draft.tables.splice(i, 1); renderTables(); touch(); } }, "Remove")),
        labelled("Points — one ‘x, y’ pair per line, x increasing", area(t, "points", { placeholder: "0, 50\n10, 48\n20, 42", "data-field": `tables[${i}]` })))));
      tableBox.append(h("button", { type: "button", class: "btn", onclick: () => { draft.tables.push({ name: "", x_unit: "", y_unit: "", method: "linear", outside: "error", points: "" }); renderTables(); } }, "+ Add a data table"));
    }

    let vseq = 0;
    async function validate() {
      const my = ++vseq;
      let r;
      try { r = await call("custom_validate", { calculation: draftToDoc(draft) }); } catch (e) { return renderCheck({ ok: false, errors: [{ field: "", message: e.message }], warnings: [] }); }
      if (my === vseq) renderCheck(r);
    }
    function renderCheck(r) {
      root.querySelectorAll("[data-field]").forEach((el) => el.classList.remove("bad"));
      for (const e of r.errors || []) root.querySelector(`[data-field="${CSS.escape(e.field)}"]`)?.classList.add("bad");
      clear(check);
      check.append(r.ok
        ? h("p", { class: "ok" }, "✓ Valid: units are consistent in every equation.")
        : h("div", {}, h("p", { class: "bad-msg" }, `✗ ${r.errors.length} problem${r.errors.length === 1 ? "" : "s"} to fix`), h("ul", { class: "report" }, r.errors.map((e) => h("li", { class: "bad" }, e.field ? h("b", {}, e.field + ": ") : null, e.message)))));
      if (r.ok) {
        check.append(
          h("h4", {}, "How it will look"),
          ...r.equations.map((q) => h("div", { class: "eq" }, q.title ? h("div", { class: "t" }, q.title) : null, math(q.latex, true), q.evaluated ? h("div", { class: "evaluated" }, "evaluates to ", math(q.evaluated)) : null)),
          h("p", { class: "hint" }, "Can solve for: ", r.solvable_for.join(", ") || "—"),
          ...(r.odes || []).map((o) => h("div", { class: "eq" }, h("div", { class: "t" }, o.title, " — ", o.kind === "closed" ? "solved in closed form" : `solved numerically (${o.why_numeric || "no closed form"})`),
            ...o.latex.map((q) => math(q, true)), ...o.conditions.map((q) => h("div", { class: "evaluated" }, "with ", math(q))))),
          r.example_result ? h("p", { class: "hint" }, "Example gives: ", r.example_result.outputs.map((o) => `${o.key} = ${o.text}`).join(", ")) : null);
      }
      if (r.warnings?.length) check.append(h("ul", { class: "report warn" }, r.warnings.map((w) => h("li", {}, "! " + w))));
      saveBtn.disabled = openBtn.disabled = !r.ok;
    }

    async function save(thenOpen) {
      const doc = draftToDoc(draft);
      if (editingId) doc.id = editingId; else if (draft.id) doc.id = draft.id; else doc.id = "";
      let res;
      try { res = await call("custom_save", { calculation: doc, replace: !!editingId }); } catch (e) {
        flash(e.message);
        if (e.details) renderCheck({ ok: false, errors: e.details, warnings: [] });
        return;
      }
      await ctx.changed();
      flash("Saved");
      location.hash = thenOpen ? `#/calc/${encodeURIComponent(res.id)}` : "#/mine";
    }
    const saveBtn = h("button", { type: "button", class: "btn", onclick: () => save(false) }, "Save");
    const openBtn = h("button", { type: "button", class: "btn primary", onclick: () => save(true) }, "Save and open");

    renderDisciplines(); renderSubs(); renderVars(); renderEqs(); renderOdes(); renderTables(); renderFuncs();
    clear(root).append(
      h("div", { class: "cust-editor" },
        h("div", { class: "cust-form" },
          fromLive ? h("div", { class: "panel cust-note" },
            h("h3", {}, "Started from LiveCalc"),
            h("p", {}, h("code", {}, fromLive.from)),
            h("p", { class: "hint" }, "Give it a name, pick at least one discipline, and check each variable’s name and unit. Units were taken from the values you had defined in LiveCalc; blank ones are plain numbers unless you choose a unit."),
            fromLive.warnings?.length ? h("ul", { class: "warn-list" }, fromLive.warnings.map((w) => h("li", {}, w))) : null) : null,
          h("div", { class: "panel" },
            h("h2", {}, editingId ? "Edit equation" : "New equation"),
            labelled("Name", text(draft, "name", { placeholder: "e.g. Spring force", "data-field": "name" })),
            labelled("Description", area(draft, "description", { placeholder: "What it calculates and when to use it" })),
            labelled("Author (optional)", text(draft, "author")),
            h("h4", {}, "Disciplines"), disciplineBox,
            h("h4", {}, "Sub-disciplines"), subBox),
          h("div", { class: "panel" },
            h("h3", {}, "Variables"),
            h("p", { class: "hint" }, "Every quantity in your equations, with a unit. Constants have a fixed value. The example column lets the calculator open with a worked result."),
            varsBox),
          h("div", { class: "panel" },
            h("h3", {}, "Equations"),
            h("p", { class: "hint" }, "One ", h("code", {}, "="), " per equation, e.g. ", h("code", {}, "F = k*x"), " or ", h("code", {}, "Re = rho*v*D/mu"), ". Use ", h("code", {}, "*"), " for multiply and ", h("code", {}, "^"), " or ", h("code", {}, "**"), " for powers. Functions: ", FUNCS, ". Calculus: ", CALCULUS, " — the integration variable ", h("code", {}, "x"), " needs no declaration, but the limits must be variables or numbers. Any variable can then be solved for."),
            eqBox),
          h("div", { class: "panel" },
            h("h3", {}, "Your own functions (optional)"),
            h("p", { class: "hint" }, "Define a formula once and call it from several equations: ", h("code", {}, "fsj(Re1, rel1)"), ". The body is written out where it is called, so units are checked and any variable can still be solved for. Products: ",
              h("code", {}, "product(1 - d*i, (i, 1, 6))"), " (up to 50 factors)."), funcBox),
          h("div", { class: "panel" },
            h("h3", {}, "Data tables (optional)"),
            h("p", { class: "hint" }, "Measured or published points that equations can look up, for example a pump curve ", h("code", {}, "H = pump(Q)"), ". Values between points are interpolated; the argument must have the x unit's dimension. "
              + "Whatever sits inside the table (the flow at which the pump meets a system curve) is found numerically."), tableBox),
          h("div", { class: "panel" },
            h("h3", {}, "Differential equations (optional)"),
            h("p", { class: "hint" }, "Initial-value problems such as ", h("code", {}, "diff(T, t) = -k*(T - Ta)"), " with ", h("code", {}, "T = T0"), " at the start. The quantity (", h("code", {}, "T"), ") means its value at the time ",
              h("code", {}, "t"), " you enter. A closed-form solution is used when SymPy finds one, so you can still solve for any variable; otherwise the equation is integrated numerically (other quantities are then found by root-finding) and the solution is plotted. ",
              "Second derivatives: ", h("code", {}, "diff(x, t, 2)"), "; systems: one line per quantity."), odeBox, varList),
          h("details", { class: "panel" }, h("summary", {}, "Assumptions, references and validity checks (optional)"),
            labelled("Assumptions (one per line)", area(draft, "assumptions")),
            labelled("References (one per line)", area(draft, "references")),
            labelled("Validity checks, one per line: condition | warning shown when false", area(draft, "validity", { placeholder: "Re > 4000 | Flow may be laminar" })))),
        h("aside", { class: "cust-side" }, h("div", { class: "panel" }, h("h3", {}, "Live check"), check,
          h("div", { class: "toolbar" }, openBtn, saveBtn, h("a", { class: "btn", href: "#/mine" }, "Cancel"))))));
    validate();
  }

  return { show };
}
