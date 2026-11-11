// Tiny DOM + math helpers.

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k in el && k !== "list" && k !== "style") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function math(latex, display = false) {
  const el = h("span", { class: display ? "math display" : "math" });
  try {
    if (!window.katex) throw new Error("katex missing");
    window.katex.render(latex, el, { displayMode: display, throwOnError: false, strict: "ignore", trust: false });
  } catch {
    el.textContent = latex;
  }
  return el;
}

export function debounce(fn, ms) {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}

export function store(key, value) {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem("sliderule." + key));
    localStorage.setItem("sliderule." + key, JSON.stringify(value));
  } catch {
    return null;
  }
}
