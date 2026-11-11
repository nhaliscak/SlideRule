// "Property data" picker: fill an input from a datapack (material or fluid), with the source, basis and uncertainty kept next to the value.
// The engine does the work (`data_options`, `data_value`); this file is the dialog and the provenance text.
import { clear, h } from "./dom.js";

const TEMP_UNITS = ["degC", "K", "degF"];
const sig6 = (x) => String(Number(Number(x).toPrecision(6)));

/** The sentence kept beside a value that came from data (also used in copied text and saved cases). */
export function provenanceText(p) {
  const at = p.x != null ? ` at ${sig6(p.x)} ${p.x_unit}` : "";
  const unc = p.rel_uncertainty ? `, within ${sig6(p.rel_uncertainty * 100)} % of the reference` : "";
  return `${p.record_name}, ${p.label.toLowerCase()}${at}: ${sig6(p.value)} ${p.unit} (${p.basis}${unc}; ${p.pack} v${p.pack_version}${p.design_use ? "" : "; not for design"})`;
}

/**
 * Open the picker for one variable. `options` come from `data_options`; `current` is the unit now chosen for the variable.
 * `onApply(result)` receives {value, unit, ...provenance} once the user accepts a value.
 */
export function openDataPicker({ call, variable, options, current, onApply }) {
  const dialog = h("dialog", { class: "eqdialog data-dialog", "aria-labelledby": "data-title" });
  document.body.append(dialog);
  const props = [...new Map(options.map((o) => [o.property, o])).values()];
  const state = { property: props[0].property, record: null, x: "20", xUnit: "degC", filter: "" };
  const recordsFor = (prop) => options.filter((o) => o.property === prop);

  const propSel = h("select", { "aria-label": "property", onchange: () => { state.property = propSel.value; state.record = null; render(); } },
    props.map((o) => h("option", { value: o.property }, o.label + (o.match ? "" : " (other)"))));
  const recSel = h("select", { "aria-label": "material or fluid", onchange: () => { state.record = recSel.value; preview(); renderTemp(); } });
  const filt = h("input", { class: "field", type: "search", placeholder: "type to narrow the list (name, category or pack)", "aria-label": "filter materials and fluids",
    oninput: () => { state.filter = filt.value.trim().toLowerCase(); render(); } });
  const xIn = h("input", { class: "field", type: "text", inputMode: "decimal", value: state.x, "aria-label": "temperature", oninput: () => { state.x = xIn.value; preview(); } });
  const xUnit = h("select", { "aria-label": "temperature unit", onchange: () => { state.xUnit = xUnit.value; preview(); } }, TEMP_UNITS.map((u) => h("option", { value: u }, u)));
  const tempRow = h("label", { class: "field" }, "Temperature", h("div", { class: "temp-row" }, xIn, xUnit), h("small", { class: "hint range" }));
  const out = h("div", { class: "data-preview", role: "status" });
  const useBtn = h("button", { type: "button", class: "btn primary", disabled: true }, "Use this value");
  let last = null, seq = 0;

  const keyOf = (o) => `${o.pack}/${o.record}`;
  function selected() { return recordsFor(state.property).find((o) => keyOf(o) === state.record) || null; }

  function renderTemp() {
    const o = selected();
    tempRow.hidden = !o?.curve;
    if (o?.curve) tempRow.querySelector(".range").textContent = `Valid from ${o.range.min} to ${o.range.max} ${o.range.unit}; there is no answer outside that range.`;
  }

  function render() {
    const all = recordsFor(state.property);
    const words = state.filter.split(/\s+/).filter(Boolean);
    const recs = words.length ? all.filter((o) => words.every((w) => `${o.record_name} ${o.category} ${o.record}`.toLowerCase().includes(w))) : all;
    clear(recSel);
    for (const o of recs) recSel.append(h("option", { value: keyOf(o) }, `${o.record_name} (${o.category})`));
    if (!recs.length) { recSel.append(h("option", { value: "" }, "nothing matches")); state.record = null; preview(); return; }
    if (!state.record || !recs.some((o) => keyOf(o) === state.record)) state.record = keyOf(recs[0]);
    recSel.value = state.record;
    renderTemp();
    preview();
  }

  async function preview() {
    const o = selected();
    const mine = ++seq;
    last = null;
    useBtn.disabled = true;
    if (!o) return;
    const params = { pack: o.pack, record_id: o.record, prop: o.property, unit: current };
    if (o.curve) {
      if (state.x.trim() === "" || !isFinite(Number(state.x))) { out.textContent = "Enter a temperature."; return; }
      params.x = Number(state.x); params.x_unit = state.xUnit;
    }
    let r;
    try { r = await call("data_value", params); } catch (e) {
      if (mine === seq) { out.className = "data-preview bad"; out.textContent = e.message; }
      return;
    }
    if (mine !== seq) return;
    last = { ...r, label: o.label, record_name: o.record_name };
    out.className = "data-preview";
    clear(out).append(...[
      h("div", { class: "big" }, `${sig6(r.value)} ${r.unit}`),
      h("div", {}, h("span", { class: "badge" }, r.basis), r.rel_uncertainty ? h("span", { class: "badge" }, `within ${sig6(r.rel_uncertainty * 100)} % of the reference`) : null,
        r.design_use ? null : h("span", { class: "badge unverified", title: "This datapack is for hand estimates, not design calculations" }, "not for design")),
      h("div", { class: "hint" }, `Source: ${r.source}`),
      r.note ? h("div", { class: "hint" }, r.note) : null,
      r.at?.pressure ? h("div", { class: "hint" }, `At ${r.at.pressure}.`) : null].filter(Boolean));
    useBtn.disabled = false;
  }

  useBtn.addEventListener("click", () => { if (last) { onApply(last); dialog.close(); } });
  dialog.addEventListener("close", () => dialog.remove());
  clear(dialog).append(
    h("h3", { id: "data-title" }, `Fill “${variable.label}” from property data`),
    h("p", { class: "hint" }, `The value is converted to ${current} and stays editable; the source is kept beside it.`),
    h("label", { class: "field" }, "Property", propSel),
    h("label", { class: "field" }, "Material or fluid", filt, recSel),
    tempRow, out,
    h("div", { class: "toolbar" }, useBtn, h("button", { type: "button", class: "btn", onclick: () => dialog.close() }, "Cancel")));
  render();
  dialog.showModal();
}
