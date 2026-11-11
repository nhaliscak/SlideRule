// Small reusable form widgets.
import { clear, h } from "./dom.js";

export const CUSTOM = "__custom__";

export function unitPicker(units, selected, onChange, { custom: allowCustom = true } = {}) {
  const sel = h("select", { class: "unit", "aria-label": "unit" });
  const custom = h("input", { class: "custom", type: "text", placeholder: "unit, e.g. kN*m", hidden: true, "aria-label": "custom unit" });
  const wrap = h("div", { class: "unit-wrap" }, sel, custom);
  const set = (list, current) => {
    clear(sel);
    const all = list.includes(current) || !current ? list : [current, ...list];
    for (const u of all) sel.append(h("option", { value: u }, u));
    if (allowCustom) sel.append(h("option", { value: CUSTOM }, "custom…"));
    sel.value = current && all.includes(current) ? current : all[0];
    custom.hidden = true;
  };
  sel.addEventListener("change", () => {
    custom.hidden = sel.value !== CUSTOM;
    if (!custom.hidden) custom.focus();
    onChange();
  });
  custom.addEventListener("input", onChange);
  set(units, selected);
  return { el: wrap, get: () => (sel.value === CUSTOM ? custom.value.trim() : sel.value), set };
}

