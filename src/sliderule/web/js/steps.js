// Worked-solution panel and toast, shared by the calculation view and the system-design view.
import { clear, h, math, store } from "./dom.js";

export function flash(msg) {
  const el = h("div", { class: "badge", role: "status", style: "position:fixed;bottom:16px;left:50%;transform:translateX(-50%);z-index:60;padding:.5rem 1rem" }, msg);
  document.body.append(el);
  setTimeout(() => el.remove(), 2200);
}

/** `state.stepMode` is "numeric" | "symbolic" and is remembered across views. */
export function stepsPanel(sol, state, title = "Worked solution") {
  const body = h("div", {});
  const render = () => {
    clear(body);
    const steps = sol.steps[state.stepMode];
    body.append(
      h("p", { class: "step-intro" }, state.stepMode === "symbolic"
        ? "Derivation in symbols: rearrangement, closed-form result and a dimensional check that the units come out right."
        : "Substituted values: every input is converted to coherent SI, units are carried through each operation, and the result is converted to the requested unit."),
      h("div", { class: "steps" }, steps.map((st) =>
        h("section", { class: "step" }, h("h4", {}, st.title),
          st.lines.map((l) => h("div", { class: "line" }, h("div", { class: "m" }, math(l.latex, true)), h("div", { class: "n" }, l.note))))))
    );
  };
  const seg = h("div", { class: "seg", role: "group", "aria-label": "Solution type" },
    ...["numeric", "symbolic"].map((m) => h("button", {
      type: "button", "aria-pressed": String(state.stepMode === m),
      onclick: (e) => {
        state.stepMode = m;
        store("stepMode", m);
        seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === e.currentTarget)));
        render();
      },
    }, m === "numeric" ? "Numeric solution" : "Symbolic solution")));
  const copy = h("button", { type: "button", class: "btn", onclick: async () => {
    const tex = sol.steps[state.stepMode].map((s) => `% ${s.title}\n` + s.lines.map((l) => l.latex).join(" \\\\\n")).join("\n\n");
    try { await navigator.clipboard.writeText(tex); flash("LaTeX copied"); } catch { flash("Clipboard unavailable"); }
  } }, "Copy LaTeX");
  const print = h("button", { type: "button", class: "btn", onclick: () => window.print() }, "Print");
  render();
  return h("div", { class: "panel" }, h("h3", {}, title, h("span", { class: "spacer" }), seg, copy, print), body);
}
