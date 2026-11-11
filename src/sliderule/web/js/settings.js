// Settings dialog: the time limit for long calculations (on/off and seconds).
// The engine enforces it; switching it off needs an explicit acknowledgement of the warning the engine supplies.
import { clear, h } from "./dom.js";
import { flash } from "./steps.js";

export function initSettings({ call, S, store }) {
  const badge = document.getElementById("limit-badge");
  const dialog = h("dialog", { class: "settings-dialog", "aria-labelledby": "settings-title" });
  document.body.append(dialog);

  function refreshBadge() {
    const off = S.meta?.settings && !S.meta.settings.timeout_enabled;
    badge.hidden = !off;
  }
  badge.addEventListener("click", open);
  document.getElementById("settings-btn").addEventListener("click", open);

  async function open() {
    const cur = await call("settings_get");
    S.meta.settings = cur;
    let enabled = cur.timeout_enabled;
    const wasEnabled = cur.timeout_enabled;
    let secs = String(cur.timeout_seconds);
    let ack = false;

    const toggle = h("input", { type: "checkbox", checked: enabled, id: "limit-on", onchange: () => { enabled = toggle.checked; update(); } });
    const num = h("input", { class: "field", type: "number", id: "limit-secs", min: cur.min_seconds, max: cur.max_seconds, step: 1, value: secs,
      "aria-label": "Time limit in seconds", oninput: () => { secs = num.value; update(); } });
    const ackBox = h("input", { type: "checkbox", id: "limit-ack", onchange: () => { ack = ackBox.checked; update(); } });
    const warn = h("div", { class: "warn-box", role: "alert", hidden: true },
      h("strong", {}, "⚠ Switching the limit off can freeze the calculator"),
      h("p", {}, cur.disable_warning),
      h("label", { class: "ack" }, ackBox, "I understand and want to switch the time limit off"));
    const err = h("p", { class: "ferr", hidden: true });
    const save = h("button", { type: "button", class: "btn primary", onclick: apply }, "Save");
    const valid = () => { const n = Number(secs); return secs !== "" && n >= cur.min_seconds && n <= cur.max_seconds; };

    function update() {
      num.disabled = !enabled;
      const turningOff = !enabled && wasEnabled;
      warn.hidden = enabled;
      err.hidden = valid();
      err.textContent = valid() ? "" : `Enter a number of seconds from ${cur.min_seconds} to ${cur.max_seconds}.`;
      save.disabled = !valid() || (turningOff && !ack);
    }
    async function apply() {
      try {
        const next = await call("settings_set", { timeout_enabled: enabled, timeout_seconds: Number(secs), acknowledge_risk: ack || !wasEnabled });
        S.meta.settings = next;
        store("settings", { timeout_enabled: next.timeout_enabled, timeout_seconds: next.timeout_seconds });   // the in-browser engine has no disk
        refreshBadge();
        dialog.close();
        flash(next.timeout_enabled ? `Time limit: ${next.timeout_seconds} s` : "Time limit switched off");
      } catch (e) { err.hidden = false; err.textContent = e.message; }
    }

    clear(dialog).append(
      h("h2", { id: "settings-title" }, "Settings"),
      h("fieldset", {},
        h("legend", {}, "Time limit for long calculations"),
        h("div", { class: "limit-row" },
          h("label", { for: "limit-on" }, toggle, " Stop a calculation that runs longer than"), num, h("span", {}, "seconds")),
        h("p", { class: "hint" }, `Applies to solving, checking and saving equations, System Design and exports. Default ${cur.default_seconds} s. `,
          "Heavy symbolic work, such as a hard integral or a large system, may need more. When a calculation is stopped you get a message and nothing else changes."),
        warn, err),
      h("div", { class: "toolbar" }, save,
        h("button", { type: "button", class: "btn", onclick: () => { toggle.checked = enabled = true; num.value = secs = String(cur.default_seconds); update(); } }, "Restore default"),
        h("button", { type: "button", class: "btn", onclick: () => dialog.close() }, "Cancel")));
    update();
    dialog.showModal();
  }

  refreshBadge();
  return { refreshBadge };
}
