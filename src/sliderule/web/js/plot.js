// Line plots for differential-equation solutions: one small SVG per quantity (each has its own unit and scale), sharing the time axis.
import { h, math } from "./dom.js";

const NS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}, ...kids) => {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  for (const k of kids.flat()) if (k != null) el.append(k);
  return el;
};

/** "Nice" tick values covering [lo, hi]. */
export function niceTicks(lo, hi, target = 5) {
  if (!(hi > lo)) { const pad = Math.abs(lo) * 0.1 || 1; lo -= pad; hi += pad; }
  const raw = (hi - lo) / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
  const start = Math.ceil(lo / step - 1e-9) * step;
  const out = [];
  for (let v = start; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : Number(v.toPrecision(12)));
  return { ticks: out, step };
}

const fmt = (v, step) => {
  if (v === 0) return "0";
  const digits = Math.max(0, -Math.floor(Math.log10(step)) + (step < 1 ? 0 : 0));
  return Math.abs(v) >= 1e5 || Math.abs(v) < 1e-3 ? v.toExponential(2) : Number(v.toFixed(Math.min(digits, 8))).toString();
};

function onePlot(x, series, indep, events = []) {
  const W = 640, H = 230, m = { l: 62, r: 14, t: 14, b: 40 };
  const ys = series.values;
  const xmin = Math.min(...x), xmax = Math.max(...x);
  let ymin = Math.min(...ys), ymax = Math.max(...ys);
  const xt = niceTicks(xmin, xmax, 6), yt = niceTicks(ymin, ymax, 5);
  const y0 = plot.equal ? ymin : Math.min(ymin, yt.ticks[0] ?? ymin), y1 = plot.equal ? ymax : Math.max(ymax, yt.ticks[yt.ticks.length - 1] ?? ymax);
  const sx = (v) => m.l + ((v - xmin) / (xmax - xmin || 1)) * (W - m.l - m.r);
  const sy = (v) => H - m.b - ((v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
  const g = svg("g");
  for (const t of yt.ticks) {
    g.append(svg("line", { x1: m.l, x2: W - m.r, y1: sy(t), y2: sy(t), class: "grid" }),
      Object.assign(svg("text", { x: m.l - 6, y: sy(t) + 4, "text-anchor": "end", class: "tick" }), { textContent: fmt(t, yt.step) }));
  }
  for (const t of xt.ticks) {
    g.append(svg("line", { x1: sx(t), x2: sx(t), y1: m.t, y2: H - m.b, class: "grid" }),
      Object.assign(svg("text", { x: sx(t), y: H - m.b + 15, "text-anchor": "middle", class: "tick" }), { textContent: fmt(t, xt.step) }));
  }
  g.append(svg("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: "axis" }), svg("line", { x1: m.l, x2: m.l, y1: m.t, y2: H - m.b, class: "axis" }));
  const d = x.map((xv, i) => `${i ? "L" : "M"}${sx(xv).toFixed(1)} ${sy(ys[i]).toFixed(1)}`).join("");
  g.append(svg("path", { d, class: "curve" }));
  g.append(Object.assign(svg("text", { x: (m.l + W - m.r) / 2, y: H - 6, "text-anchor": "middle", class: "label" }), { textContent: `${indep.label} (${indep.unit})` }));
  g.append(Object.assign(svg("text", { x: 14, y: (m.t + H - m.b) / 2, "text-anchor": "middle", class: "label", transform: `rotate(-90 14 ${(m.t + H - m.b) / 2})` }), { textContent: `${series.label} (${series.unit})` }));
  for (const e of events) {      // event markers: a dashed line at the event time and a dot on the curve
    const ev = e.values?.[series.key];
    g.append(svg("line", { x1: sx(e.t), x2: sx(e.t), y1: m.t, y2: H - m.b, class: "event-line" }));
    if (ev != null) g.append(svg("circle", { cx: sx(e.t), cy: sy(ev), r: 5, class: "event-dot" }));
    g.append(Object.assign(svg("text", { x: Math.min(sx(e.t) + 5, W - m.r - 60), y: m.t + 12, class: "event-label" }), { textContent: e.title }));
  }
  const cursor = svg("line", { y1: m.t, y2: H - m.b, class: "cursor", visibility: "hidden" });
  const dot = svg("circle", { r: 4, class: "dot", visibility: "hidden" });
  const catcher = svg("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
  g.append(cursor, dot, catcher);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${series.label} against ${indep.label}`, class: "plot" }, g);
  const readout = h("div", { class: "plot-readout" }, " ");
  catcher.addEventListener("mousemove", (ev) => {
    const r = root.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    const xv = xmin + ((px - m.l) / (W - m.l - m.r)) * (xmax - xmin);
    let best = 0;
    for (let i = 1; i < x.length; i++) if (Math.abs(x[i] - xv) < Math.abs(x[best] - xv)) best = i;
    cursor.setAttribute("x1", sx(x[best])); cursor.setAttribute("x2", sx(x[best])); cursor.setAttribute("visibility", "visible");
    dot.setAttribute("cx", sx(x[best])); dot.setAttribute("cy", sy(ys[best])); dot.setAttribute("visibility", "visible");
    readout.textContent = `${indep.key} = ${Number(x[best].toPrecision(5))} ${indep.unit}   ${series.key} = ${Number(ys[best].toPrecision(5))} ${series.unit}`;
  });
  catcher.addEventListener("mouseleave", () => { cursor.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); readout.textContent = " "; });
  return h("figure", { class: "plot-fig" }, root, readout);
}

/** Several curves of one quantity in one figure (e.g. a profile along a bar at successive times): the oldest is dashed, the latest solid. */
function overlayPlot(x, curves, indep) {
  const W = 640, H = 260, m = { l: 62, r: 14, t: 14, b: 40 };
  const xmin = Math.min(...x), xmax = Math.max(...x);
  const all = curves.flatMap((c) => c.values);
  const ymin = Math.min(...all), ymax = Math.max(...all);
  const xt = niceTicks(xmin, xmax, 6), yt = niceTicks(ymin, ymax, 5);
  const y0 = Math.min(ymin, yt.ticks[0] ?? ymin), y1 = Math.max(ymax, yt.ticks[yt.ticks.length - 1] ?? ymax);
  const sx = (v) => m.l + ((v - xmin) / (xmax - xmin || 1)) * (W - m.l - m.r);
  const sy = (v) => H - m.b - ((v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
  const g = svg("g");
  for (const t of yt.ticks) {
    g.append(svg("line", { x1: m.l, x2: W - m.r, y1: sy(t), y2: sy(t), class: "grid" }),
      Object.assign(svg("text", { x: m.l - 6, y: sy(t) + 4, "text-anchor": "end", class: "tick" }), { textContent: fmt(t, yt.step) }));
  }
  for (const t of xt.ticks) {
    g.append(svg("line", { x1: sx(t), x2: sx(t), y1: m.t, y2: H - m.b, class: "grid" }),
      Object.assign(svg("text", { x: sx(t), y: H - m.b + 15, "text-anchor": "middle", class: "tick" }), { textContent: fmt(t, xt.step) }));
  }
  g.append(svg("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: "axis" }), svg("line", { x1: m.l, x2: m.l, y1: m.t, y2: H - m.b, class: "axis" }));
  const n = curves.length;
  curves.forEach((c, k) => {
    const d = x.map((xv, i) => `${i ? "L" : "M"}${sx(xv).toFixed(1)} ${sy(c.values[i]).toFixed(1)}`).join("");
    g.append(svg("path", { d, class: `curve snap${k === 0 ? " first" : ""}${k === n - 1 ? " last" : ""}`, style: n > 1 ? `opacity:${(0.35 + 0.65 * k / (n - 1)).toFixed(2)}` : "" }));
  });
  g.append(Object.assign(svg("text", { x: (m.l + W - m.r) / 2, y: H - 6, "text-anchor": "middle", class: "label" }), { textContent: `${indep.label} (${indep.unit})` }));
  const q = curves[0];
  g.append(Object.assign(svg("text", { x: 14, y: (m.t + H - m.b) / 2, "text-anchor": "middle", class: "label", transform: `rotate(-90 14 ${(m.t + H - m.b) / 2})` }), { textContent: `${q.key.split("@")[0]} (${q.unit})` }));
  const cursor = svg("line", { y1: m.t, y2: H - m.b, class: "cursor", visibility: "hidden" });
  const catcher = svg("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
  g.append(cursor, catcher);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${q.key.split("@")[0]} against ${indep.label}`, class: "plot" }, g);
  const readout = h("div", { class: "plot-readout" }, " ");
  const legend = h("div", { class: "plot-legend" }, curves.map((c, k) => h("span", {}, h("i", { class: `swatch${k === 0 ? " first" : ""}`, style: n > 1 ? `opacity:${(0.35 + 0.65 * k / (n - 1)).toFixed(2)}` : "" }), c.label)));
  catcher.addEventListener("mousemove", (ev) => {
    const r = root.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    const xv = xmin + ((px - m.l) / (W - m.l - m.r)) * (xmax - xmin);
    let best = 0;
    for (let i = 1; i < x.length; i++) if (Math.abs(x[i] - xv) < Math.abs(x[best] - xv)) best = i;
    cursor.setAttribute("x1", sx(x[best])); cursor.setAttribute("x2", sx(x[best])); cursor.setAttribute("visibility", "visible");
    readout.textContent = `${indep.key} = ${Number(x[best].toPrecision(5))} ${indep.unit}   ` + curves.map((c) => `${c.label}: ${Number(c.values[best].toPrecision(5))}`).join("   ");
  });
  catcher.addEventListener("mouseleave", () => { cursor.setAttribute("visibility", "hidden"); readout.textContent = " "; });
  return h("figure", { class: "plot-fig" }, root, legend, readout);
}

const RAMP = [[253, 241, 214], [240, 190, 110], [184, 111, 15], [90, 48, 8]];
const ramp = (t) => {
  const f = Math.min(Math.max(t, 0), 1) * (RAMP.length - 1), i = Math.min(Math.floor(f), RAMP.length - 2), k = f - i;
  return `rgb(${RAMP[i].map((v, c) => Math.round(v + (RAMP[i + 1][c] - v) * k)).join(",")})`;
};

/** A field over a rectangle as coloured cells with a colour bar, the chosen point marked, and a readout under the pointer. */
function heatmapPlot(hm) {
  const W = 640, H = 480, m = { l: 62, r: 86, t: 14, b: 44 };
  const xs = hm.x, ys = hm.y, nx = xs.length, ny = ys.length;
  const xmin = xs[0], xmax = xs[nx - 1], ymin = ys[0], ymax = ys[ny - 1];
  const sx = (v) => m.l + ((v - xmin) / (xmax - xmin || 1)) * (W - m.l - m.r);
  const sy = (v) => H - m.b - ((v - ymin) / (ymax - ymin || 1)) * (H - m.t - m.b);
  const span = hm.zmax - hm.zmin || 1;
  const g = svg("g");
  for (let j = 0; j < ny; j++) {
    const ylo = j === 0 ? ys[0] : (ys[j - 1] + ys[j]) / 2, yhi = j === ny - 1 ? ys[j] : (ys[j] + ys[j + 1]) / 2;
    for (let i = 0; i < nx; i++) {
      const xlo = i === 0 ? xs[0] : (xs[i - 1] + xs[i]) / 2, xhi = i === nx - 1 ? xs[i] : (xs[i] + xs[i + 1]) / 2;
      if (hm.z[j][i] === null) continue;                       // inside a cutout: not part of the region
      g.append(svg("rect", { x: sx(xlo).toFixed(2), y: sy(yhi).toFixed(2), width: (sx(xhi) - sx(xlo) + 0.6).toFixed(2), height: (sy(ylo) - sy(yhi) + 0.6).toFixed(2), fill: ramp((hm.z[j][i] - hm.zmin) / span), class: "cell" }));
    }
  }
  const xt = niceTicks(xmin, xmax, 6), yt = niceTicks(ymin, ymax, 6);
  g.append(svg("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "none", class: "axis" }));
  for (const t of xt.ticks) g.append(Object.assign(svg("text", { x: sx(t), y: H - m.b + 15, "text-anchor": "middle", class: "tick" }), { textContent: fmt(t, xt.step) }));
  for (const t of yt.ticks) g.append(Object.assign(svg("text", { x: m.l - 6, y: sy(t) + 4, "text-anchor": "end", class: "tick" }), { textContent: fmt(t, yt.step) }));
  g.append(Object.assign(svg("text", { x: (m.l + W - m.r) / 2, y: H - 6, "text-anchor": "middle", class: "label" }), { textContent: `${hm.x_info.label} (${hm.x_info.unit})` }));
  g.append(Object.assign(svg("text", { x: 14, y: (m.t + H - m.b) / 2, "text-anchor": "middle", class: "label", transform: `rotate(-90 14 ${(m.t + H - m.b) / 2})` }), { textContent: `${hm.y_info.label} (${hm.y_info.unit})` }));
  const bx = W - m.r + 18, bh = H - m.t - m.b;
  for (let k = 0; k < 40; k++) g.append(svg("rect", { x: bx, y: m.t + (bh * k) / 40, width: 14, height: bh / 40 + 0.6, fill: ramp(1 - k / 39) }));
  const cb = yt2(hm.zmin, hm.zmax);
  for (const t of cb.ticks) g.append(Object.assign(svg("text", { x: bx + 18, y: m.t + bh * (1 - (t - hm.zmin) / span) + 4, class: "tick" }), { textContent: fmt(t, cb.step) }));
  g.append(Object.assign(svg("text", { x: bx, y: m.t - 3, class: "label" }), { textContent: hm.u.unit }));
  if (hm.point) {
    g.append(svg("circle", { cx: sx(hm.point.x), cy: sy(hm.point.y), r: 6, class: "event-dot", fill: "none", stroke: "var(--ink)", "stroke-width": 2 }));
  }
  const catcher = svg("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
  g.append(catcher);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${hm.u.label} over ${hm.x_info.label} and ${hm.y_info.label}`, class: "plot heat" }, g);
  const readout = h("div", { class: "plot-readout" }, hm.point ? `○ the point you entered: ${hm.x_info.key} = ${Number(hm.point.x.toPrecision(5))} ${hm.x_info.unit}, ${hm.y_info.key} = ${Number(hm.point.y.toPrecision(5))} ${hm.y_info.unit}` : " ");
  catcher.addEventListener("mousemove", (ev) => {
    const r = root.getBoundingClientRect();
    const xv = xmin + ((((ev.clientX - r.left) / r.width) * W - m.l) / (W - m.l - m.r)) * (xmax - xmin);
    const yv = ymin + ((H - m.b - ((ev.clientY - r.top) / r.height) * H) / (H - m.t - m.b)) * (ymax - ymin);
    const near = (a, v) => a.reduce((b, _, i) => (Math.abs(a[i] - v) < Math.abs(a[b] - v) ? i : b), 0);
    const i = near(xs, xv), j = near(ys, yv);
    readout.textContent = `${hm.x_info.key} = ${Number(xs[i].toPrecision(4))} ${hm.x_info.unit}, ${hm.y_info.key} = ${Number(ys[j].toPrecision(4))} ${hm.y_info.unit}: ` + (hm.z[j][i] === null ? "outside the region (cutout)" : `${hm.u.key} = ${Number(hm.z[j][i].toPrecision(5))} ${hm.u.unit}`);
  });
  return h("figure", { class: "plot-fig" }, root, readout);
}
const yt2 = (lo, hi) => niceTicks(lo, hi, 5);

export function csv(sys) {
  if (sys.heatmap) {
    const hm = sys.heatmap;
    return [`${hm.x_info.key} (${hm.x_info.unit}),${hm.y_info.key} (${hm.y_info.unit}),${hm.u.key} (${hm.u.unit})`, ...hm.y.flatMap((yv, j) => hm.x.map((xv, i) => `${xv},${yv},${hm.z[j][i]}`))].join("\n") + "\n";
  }
  const head = [`${sys.independent.key} (${sys.independent.unit})`, ...sys.series.map((s) => `${s.key} (${s.unit})`)].join(",");
  const rows = sys.t.map((t, i) => [t, ...sys.series.map((s) => s.values[i])].join(","));
  return [head, ...rows].join("\n") + "\n";
}

/** A panel with a plot per quantity, the integration method and a CSV download. */
export function solutionPlots(sys) {
  const m = sys.method || {};
  const how = m.method ? `${m.method}${m.steps ? `, ${m.steps} steps, rtol ${m.rtol}` : ""}` : "";
  const dl = h("button", { type: "button", class: "btn small", onclick: () => {
    const blob = new Blob([csv(sys)], { type: "text/csv" });
    const a = h("a", { href: URL.createObjectURL(blob), download: "solution.csv" });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  } }, "Download CSV");
  return h("div", { class: "panel" },
    h("h3", {}, sys.overlay || sys.heatmap ? sys.title : `Solution over time — ${sys.title}`, h("span", { class: "spacer" }), h("span", { class: "badge" }, how), dl),
    ...(m.notes || []).map((n) => h("p", { class: "hint" }, n)),
    sys.stopped_at_event ? h("p", { class: "hint" }, `The integration stopped at the event “${(sys.events.find((e) => e.terminal) || {}).title}”, so the curves end there.`) : null,
    h("div", { class: "plots" }, sys.heatmap ? [heatmapPlot(sys.heatmap)] : sys.overlay ? [overlayPlot(sys.t, sys.series, sys.independent)] : sys.series.map((s) => onePlot(sys.t, s, sys.independent, sys.events || []))));
}

/** Values at the requested times. */
export function valuesTable(rows) {
  if (!rows.length) return null;
  const keys = Object.keys(rows[0].values);
  return h("div", { class: "panel" }, h("h3", {}, "Values at chosen times"),
    h("div", { class: "table-wrap" }, h("table", { class: "vtable" },
      h("thead", {}, h("tr", {}, h("th", {}, `t (${rows[0].t_unit})`), keys.map((k) => h("th", {}, `${k} (${rows[0].units[k]})`)))),
      h("tbody", {}, rows.map((r) => h("tr", { class: r.is_evaluation_time ? "eval" : "", title: r.stopped_at_event ? "the integration stopped here, at an event" : "" }, h("td", {}, r.t + (r.stopped_at_event ? " ⏹" : "")), keys.map((k) => h("td", {}, r.values[k])))))
    )));
}

/** A graph of one or more curves against a common x (LiveCalc's `plot`): hover shows the values at the nearest point; missing points leave gaps. */
/** Decade ticks (1, 10, 100 ...) for a logarithmic axis between two positive values; positions are in log10 units. */
function logTicks(lo, hi) {
  const a = Math.floor(Math.log10(lo) + 1e-9), b = Math.ceil(Math.log10(hi) - 1e-9);
  const out = [];
  for (let k = a; k <= b; k++) out.push(k);
  return out.length > 8 ? out.filter((_, i) => i % Math.ceil(out.length / 8) === 0) : out;
}
const logLabel = (k) => (k >= -3 && k <= 5 ? String(10 ** k) : `1e${k}`);

export function xyPlot(plot) {
  const W = 640, H = 320, m = { l: 66, r: plot.twin ? 66 : 14, t: 14, b: 44 };
  const lx = !!plot.logx, ly = !!plot.logy;
  const tx = (v) => (lx ? Math.log10(v) : v), ty = (v) => (ly && v != null ? (v > 0 ? Math.log10(v) : null) : v);
  const x = plot.x;
  const X = x.map(tx);
  const series = plot.series.map((s) => ({ ...s, Y: s.y.map(ty) }));
  const onRight = (s) => s.axis === "right";
  const finite = series.filter((s) => !onRight(s)).flatMap((s) => s.Y.filter((v) => v != null));
  const finite2 = series.filter(onRight).flatMap((s) => s.Y.filter((v) => v != null));
  let xmin = Math.min(...X), xmax = Math.max(...X);
  let ymin = Math.min(...finite), ymax = Math.max(...finite);
  if (plot.equal) {                                          // one unit of x as long as one unit of y: widen the shorter range around its middle
    const pw = W - m.l - m.r, ph = H - m.t - m.b;
    const k = Math.max((xmax - xmin) / pw || 0, (ymax - ymin) / ph || 0) || 1;
    const cx = (xmin + xmax) / 2, cy = (ymin + ymax) / 2;
    xmin = cx - (k * pw) / 2; xmax = cx + (k * pw) / 2; ymin = cy - (k * ph) / 2; ymax = cy + (k * ph) / 2;
  }
  const xt = lx ? { ticks: logTicks(10 ** xmin, 10 ** xmax).filter((k) => k >= xmin - 1e-9 && k <= xmax + 1e-9), step: 1 } : niceTicks(xmin, xmax, 6);
  const yt = ly ? { ticks: logTicks(10 ** ymin, 10 ** ymax), step: 1 } : niceTicks(ymin, ymax, 6);
  const y0 = Math.min(ymin, yt.ticks[0] ?? ymin), y1 = Math.max(ymax, yt.ticks[yt.ticks.length - 1] ?? ymax);
  const sx = (v) => m.l + ((v - xmin) / (xmax - xmin || 1)) * (W - m.l - m.r);
  const sy = (v) => H - m.b - ((v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
  const yt2 = finite2.length ? (ly ? { ticks: logTicks(10 ** Math.min(...finite2), 10 ** Math.max(...finite2)), step: 1 } : niceTicks(Math.min(...finite2), Math.max(...finite2), 6)) : null;
  const z0 = yt2 ? Math.min(Math.min(...finite2), yt2.ticks[0] ?? Infinity) : 0, z1 = yt2 ? Math.max(Math.max(...finite2), yt2.ticks[yt2.ticks.length - 1] ?? -Infinity) : 1;
  const sy2 = (v) => H - m.b - ((v - z0) / (z1 - z0 || 1)) * (H - m.t - m.b);
  const sY = (s) => (onRight(s) ? sy2 : sy);
  const g = svg("g");
  for (const t of yt.ticks) {
    g.append(svg("line", { x1: m.l, x2: W - m.r, y1: sy(t), y2: sy(t), class: "grid" }),
      Object.assign(svg("text", { x: m.l - 6, y: sy(t) + 4, "text-anchor": "end", class: "tick" }), { textContent: ly ? logLabel(t) : fmt(t, yt.step) }));
  }
  for (const t of xt.ticks) {
    g.append(svg("line", { x1: sx(t), x2: sx(t), y1: m.t, y2: H - m.b, class: "grid" }),
      Object.assign(svg("text", { x: sx(t), y: H - m.b + 15, "text-anchor": "middle", class: "tick" }), { textContent: lx ? logLabel(t) : fmt(t, xt.step) }));
  }
  if (!ly && y0 < 0 && y1 > 0) g.append(svg("line", { x1: m.l, x2: W - m.r, y1: sy(0), y2: sy(0), class: "axis zero" }));
  if (!lx && xmin < 0 && xmax > 0) g.append(svg("line", { x1: sx(0), x2: sx(0), y1: m.t, y2: H - m.b, class: "axis zero" }));
  g.append(svg("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: "axis" }), svg("line", { x1: m.l, x2: m.l, y1: m.t, y2: H - m.b, class: "axis" }));
  series.forEach((s, k) => {
    let d = "", pen = false;
    s.Y.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${sx(X[i]).toFixed(1)} ${sY(s)(v).toFixed(1)}`;
      pen = true;
    });
    if (!plot.points) g.append(svg("path", { d, class: `curve c${k % 6}` }));       // points only: the complex plane
    if (plot.markers) s.Y.forEach((v, i) => { if (v != null) g.append(svg("circle", { cx: sx(X[i]).toFixed(1), cy: sY(s)(v).toFixed(1), r: 3.2, class: `dot c${k % 6}` })); });
  });
  const unit = (u) => (u ? ` (${u})` : "");
  g.append(Object.assign(svg("text", { x: (m.l + W - m.r) / 2, y: H - 6, "text-anchor": "middle", class: "label" }), { textContent: `${plot.var}${unit(plot.x_unit)}${lx ? " — log scale" : ""}` }));
  if (plot.y_unit || ly || plot.y_label) {
    const cy = (m.t + H - m.b) / 2;
    const yl = plot.y_label ? `${plot.y_label}${plot.y_unit ? ` (${plot.y_unit})` : ""}` : plot.y_unit || "";
    g.append(Object.assign(svg("text", { x: 14, y: cy, "text-anchor": "middle", class: "label", transform: `rotate(-90 14 ${cy})` }), { textContent: `${yl}${ly ? `${yl ? " " : ""}log scale` : ""}` }));
  }
  if (yt2) {
    g.append(svg("line", { x1: W - m.r, x2: W - m.r, y1: m.t, y2: H - m.b, class: "axis" }));
    for (const t of yt2.ticks) g.append(Object.assign(svg("text", { x: W - m.r + 6, y: sy2(t) + 4, "text-anchor": "start", class: "tick" }), { textContent: ly ? logLabel(t) : fmt(t, yt2.step) }));
    const cy2 = (m.t + H - m.b) / 2;
    g.append(Object.assign(svg("text", { x: W - 12, y: cy2, "text-anchor": "middle", class: "label", transform: `rotate(90 ${W - 12} ${cy2})` }), { textContent: `${plot.y2_unit || ""}${ly ? " log scale" : ""}` }));
  }
  for (const mk of plot.marks || []) {                                                    // marked points, e.g. the critical point −1 of a Nyquist plot
    if (mk.x < xmin || mk.x > xmax || mk.y < y0 || mk.y > y1) continue;
    const px = sx(tx(mk.x)), py = sy(ty(mk.y)), r = 5;
    g.append(svg("path", { d: `M${px - r} ${py - r}L${px + r} ${py + r}M${px - r} ${py + r}L${px + r} ${py - r}`, class: "axis mark" }),
      Object.assign(svg("text", { x: px + 8, y: py - 6, class: "tick" }), { textContent: mk.label || "" }));
  }
  const cursor = svg("line", { y1: m.t, y2: H - m.b, class: "cursor", visibility: "hidden" });
  const dots = plot.series.map((_, k) => svg("circle", { r: 4, class: `dot c${k % 6}`, visibility: "hidden" }));
  const catcher = svg("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
  g.append(cursor, ...dots, catcher);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Graph of ${plot.series.length} curve${plot.series.length === 1 ? "" : "s"} against ${plot.var}`, class: "plot" }, g);
  const readout = h("div", { class: "plot-readout" }, " ");
  const num = (v) => (v == null ? "—" : Number(v.toPrecision(5)));
  catcher.addEventListener("mousemove", (ev) => {
    const r = root.getBoundingClientRect();
    const xv = xmin + ((((ev.clientX - r.left) / r.width) * W - m.l) / (W - m.l - m.r)) * (xmax - xmin);
    let best = 0;
    for (let i = 1; i < X.length; i++) if (Math.abs(X[i] - xv) < Math.abs(X[best] - xv)) best = i;
    cursor.setAttribute("x1", sx(X[best])); cursor.setAttribute("x2", sx(X[best])); cursor.setAttribute("visibility", "visible");
    series.forEach((s, k) => {
      const v = s.Y[best];
      if (v == null) { dots[k].setAttribute("visibility", "hidden"); return; }
      dots[k].setAttribute("cx", sx(X[best])); dots[k].setAttribute("cy", sY(s)(v)); dots[k].setAttribute("visibility", "visible");
    });
    readout.textContent = `${plot.var} = ${num(x[best])}${plot.x_unit ? " " + plot.x_unit : ""}   ` + plot.series.map((s, k) => { const u = s.axis === "right" ? plot.y2_unit : plot.y_unit; return `y${plot.series.length > 1 ? k + 1 : ""} = ${num(s.y[best])}${u ? " " + u : ""}`; }).join("   ");
  });
  catcher.addEventListener("mouseleave", () => { cursor.setAttribute("visibility", "hidden"); dots.forEach((d) => d.setAttribute("visibility", "hidden")); readout.textContent = " "; });
  const legend = h("div", { class: "plot-legend" }, plot.series.map((s, k) => h("span", {}, h("i", { class: `swatch c${k % 6}` }), math(s.label_latex))));
  return h("figure", { class: "plot-fig" }, root, legend, readout);
}

const SURFACE_COLOURS = ["#b86f0f", "#4a90d9", "#2fa37a", "#d6516b", "#9b6bd0", "#7d8794"];
const hex = (c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));

/** Surfaces z = f(x, y) over a rectangle, drawn in 3D on a canvas (back to front); drag to rotate, wheel to zoom, double-click to reset, arrow keys rotate.
 *  `g`: {x, y, x_var, y_var, x_unit, y_unit, z_unit, zmin, zmax, surfaces: [{name, label_latex, z: [[...]]}]} (z[j][i] is the value at y[j], x[i]; null leaves a hole). */
export function surfacePlot(g) {
  const W = 640, H = 440, dpr = Math.min(2, window.devicePixelRatio || 1);
  const canvas = h("canvas", { class: "surface-canvas", width: W * dpr, height: H * dpr, tabindex: "0", role: "img",
    "aria-label": `3D plot of ${g.surfaces.map((s) => s.name).join(", ")} over ${g.x_var} and ${g.y_var}. Drag or use the arrow keys to rotate.` });
  const ctx = canvas.getContext("2d");
  const view = { yaw: -0.75, pitch: 0.55, zoom: 1 };
  const xs = g.x, ys = g.y;
  const [x0, x1, y0, y1] = [xs[0], xs[xs.length - 1], ys[0], ys[ys.length - 1]];
  const zmin = g.zmin, zmax = g.zmax > g.zmin ? g.zmax : g.zmin + 1;
  const norm = (v, lo, hi) => ((v - lo) / (hi - lo || 1)) * 2 - 1;
  const ZS = 0.85;                                           // height of the box relative to its width

  const project = (u, v, w) => {
    const ca = Math.cos(view.yaw), sa = Math.sin(view.yaw), ce = Math.cos(view.pitch), se = Math.sin(view.pitch);
    const xr = u * ca + v * sa, yr = -u * sa + v * ca;
    const s = 118 * view.zoom;
    return { x: W / 2 + xr * s, y: H / 2 + 8 - (w * ZS * ce + yr * se) * s, d: yr * ce - w * ZS * se };
  };
  const style = (name) => getComputedStyle(canvas).getPropertyValue(name).trim() || "#888";
  const shade = (k, t) => {
    if (g.surfaces.length === 1) return ramp(t);
    const [r, gg, b] = hex(SURFACE_COLOURS[k % SURFACE_COLOURS.length]);
    const f = 0.55 + 0.45 * t;
    return `rgb(${Math.round(r * f + 255 * (1 - f) * 0.15)},${Math.round(gg * f + 255 * (1 - f) * 0.15)},${Math.round(b * f + 255 * (1 - f) * 0.15)})`;
  };

  function draw() {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const ink = style("--ink"), ink2 = style("--ink-2"), line = style("--line");
    // the box: floor outline and the four vertical edges
    const c = (u, v, w) => project(u, v, w);
    const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
    ctx.lineWidth = 1;
    ctx.strokeStyle = line;
    ctx.beginPath();
    corners.forEach(([u, v], i) => { const p = c(u, v, -1); i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); });
    ctx.closePath();
    ctx.stroke();
    // faces, back to front
    const faces = [];
    g.surfaces.forEach((surf, k) => {
      const z = surf.z;
      for (let j = 0; j < ys.length - 1; j++) {
        for (let i = 0; i < xs.length - 1; i++) {
          const zz = [z[j][i], z[j][i + 1], z[j + 1][i + 1], z[j + 1][i]];
          if (zz.some((q) => q == null)) continue;
          const pts = [[xs[i], ys[j]], [xs[i + 1], ys[j]], [xs[i + 1], ys[j + 1]], [xs[i], ys[j + 1]]].map(([a, b], q) => c(norm(a, x0, x1), norm(b, y0, y1), norm(zz[q], zmin, zmax)));
          faces.push({ pts, d: pts.reduce((a, p) => a + p.d, 0) / 4, t: (zz.reduce((a, q) => a + q, 0) / 4 - zmin) / (zmax - zmin || 1), k });
        }
      }
    });
    faces.sort((a, b) => b.d - a.d);
    ctx.lineWidth = 0.5;
    for (const f of faces) {
      ctx.beginPath();
      f.pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
      ctx.closePath();
      ctx.fillStyle = shade(f.k, f.t);
      ctx.fill();
      ctx.strokeStyle = "rgba(0,0,0,.18)";
      ctx.stroke();
    }
    // axes: the two floor edges on the near side, and the z scale on the vertical edge at the left
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillStyle = ink2;
    const fmtn = (v) => (v === 0 ? "0" : Math.abs(v) >= 1e5 || Math.abs(v) < 1e-3 ? v.toExponential(1) : Number(v.toPrecision(4)).toString());
    const unit = (u) => (u ? ` (${u})` : "");
    const label = (text, p, dx, dy, align = "center", colour = ink2) => { ctx.fillStyle = colour; ctx.textAlign = align; ctx.fillText(text, p.x + dx, p.y + dy); };
    const edgeAlong = (a, b, lo, hi, name, u) => {           // label an edge of the floor: end values and the axis name
      const p0 = c(a[0], a[1], -1), p1 = c(b[0], b[1], -1), mid = { x: (p0.x + p1.x) / 2, y: (p0.y + p1.y) / 2 };
      ctx.strokeStyle = ink2; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.moveTo(p0.x, p0.y); ctx.lineTo(p1.x, p1.y); ctx.stroke();
      const out = (p) => { const dx = p.x - W / 2, dy = p.y - (H / 2 + 60); const n = Math.hypot(dx, dy) || 1; return [dx / n * 14, dy / n * 14 + 4]; };
      label(fmtn(lo), p0, ...out(p0));
      label(fmtn(hi), p1, ...out(p1));
      const [ox, oy] = out(mid);
      label(`${name}${unit(u)}`, mid, ox * 1.8, oy * 1.8 + 2, "center", ink);
    };
    // choose, for each horizontal axis, the floor edge that is on the near side
    const nearV = c(0, -1, -1).d < c(0, 1, -1).d ? -1 : 1;
    const nearU = c(-1, 0, -1).d < c(1, 0, -1).d ? -1 : 1;
    edgeAlong([-1, nearV], [1, nearV], x0, x1, g.x_var, g.x_unit);
    edgeAlong([nearU, -1], [nearU, 1], y0, y1, g.y_var, g.y_unit);
    // z scale on the vertical edge at the left of the picture
    const left = corners.map(([u, v]) => ({ u, v, p: c(u, v, -1) })).sort((a, b) => a.p.x - b.p.x)[0];
    const pb = c(left.u, left.v, -1), pt = c(left.u, left.v, 1);
    ctx.strokeStyle = ink2; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.moveTo(pb.x, pb.y); ctx.lineTo(pt.x, pt.y); ctx.stroke();
    label(fmtn(zmin), pb, -8, 4, "right"); label(fmtn(zmax), pt, -8, 4, "right");
    label(`z${unit(g.z_unit)}`, { x: pt.x, y: pt.y }, -8, -10, "right", ink);
  }

  let drag = null;
  canvas.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, yaw: view.yaw, pitch: view.pitch }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    view.yaw = drag.yaw + (e.clientX - drag.x) * 0.01;
    view.pitch = Math.min(1.5, Math.max(0.05, drag.pitch + (e.clientY - drag.y) * 0.01));
    draw();
  });
  const end = (e) => { drag = null; try { canvas.releasePointerCapture(e.pointerId); } catch { /* not captured */ } };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  canvas.addEventListener("wheel", (e) => { e.preventDefault(); view.zoom = Math.min(3, Math.max(0.4, view.zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1))); draw(); }, { passive: false });
  canvas.addEventListener("dblclick", () => { Object.assign(view, { yaw: -0.75, pitch: 0.55, zoom: 1 }); draw(); });
  canvas.addEventListener("keydown", (e) => {
    const step = 0.08;
    if (e.key === "ArrowLeft") view.yaw -= step;
    else if (e.key === "ArrowRight") view.yaw += step;
    else if (e.key === "ArrowUp") view.pitch = Math.min(1.5, view.pitch + step);
    else if (e.key === "ArrowDown") view.pitch = Math.max(0.05, view.pitch - step);
    else return;
    e.preventDefault();
    draw();
  });
  draw();
  const legend = h("div", { class: "plot-legend surface-legend" }, g.surfaces.map((s, k) => h("span", {}, h("i", { class: "swatch", style: `border-top-color:${SURFACE_COLOURS[k % SURFACE_COLOURS.length]}` }), math(s.label_latex))));
  return h("figure", { class: "plot-fig surface-fig" }, canvas, legend, h("div", { class: "plot-readout" }, "Drag to rotate · scroll to zoom · double-click to reset"));
}
