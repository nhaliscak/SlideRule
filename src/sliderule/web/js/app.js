import { createEngine } from "./engine.js";
import { clear, debounce, h, math, store } from "./dom.js";
import { flash, stepsPanel } from "./steps.js";
import { unitPicker } from "./widgets.js";
import { initSystemDesign } from "./system.js";
import { initCustom } from "./custom.js";
import { initLiveCalc } from "./livecalc.js";
import { initSettings } from "./settings.js";
import { openDataPicker, provenanceText } from "./data-picker.js";
import { solutionPlots, valuesTable, xyPlot } from "./plot.js";

const $ = (sel, root = document) => root.querySelector(sel);

const S = {
  prov: {},
  dataOptions: {},
  engine: null,
  meta: null,
  vocab: null,
  filters: savedFilters(),
  results: [],
  calc: null,           // full detail of the open calculation
  unknown: new Set(),   // keys being solved for
  vals: {},             // key -> { value: string, unit: string }
  rows: {},             // key -> row controls
  solution: null,
  stepMode: store("stepMode") || "numeric",
  sig: Number(store("sig")) || 5,
  listSeq: 0,
  listHidden: store("listHidden") === true,
  level: ["basic", "advanced", "custom", "favorites", "recent"].includes(store("calcLevel")) ? store("calcLevel") : "advanced",   // which calculations the list shows
  favorites: Array.isArray(store("calcFavorites")) ? store("calcFavorites").filter((x) => typeof x === "string") : [],    // ids the user starred
  groups: cleanGroups(store("calcGroups")),                                                                              // the user's own groupings: name -> ids
  group: typeof store("calcGroup") === "string" ? store("calcGroup") : "",                                               // the group shown in the Custom level ("" = all of them)
  recent: Array.isArray(store("calcRecent")) ? store("calcRecent").filter((x) => typeof x === "string").slice(0, 30) : [],  // calculations opened lately, newest first
  basicSubs: Array.isArray(store("calcBasicSubs")) ? store("calcBasicSubs").filter((x) => typeof x === "string").slice(0, 300) : null,   // the user's own idea of Basic (null = the default)
  sweep: {},            // the sweep panel: { vary, lo, hi, n, out, log }
  mode: "calc",         // "calc": one calculation in detail; "design": the System Design canvas
  solveSeq: 0,
  odeTimes: "",         // differential equations: extra times to tabulate (text as typed)
  search: {},           // key -> { lo, hi } text: where to look when a value has to be found numerically
};

const call = (method, params = {}) => S.engine.call(method, params);

/** The filters as left in the last session (checked), so a reload keeps the search. */
function savedFilters() {
  const f = { q: "", disc: new Set(), vars: [], solves: [], subs: [], source: "" };
  const raw = store("calcFilters");
  if (raw && typeof raw === "object") {
    const strs = (x) => (Array.isArray(x) ? x.filter((y) => typeof y === "string").slice(0, 50) : []);
    f.q = typeof raw.q === "string" ? raw.q.slice(0, 200) : "";
    f.disc = new Set(strs(raw.disc));
    f.vars = strs(raw.vars); f.solves = strs(raw.solves); f.subs = strs(raw.subs);
    f.source = raw.source === "custom" ? "custom" : "";
  }
  return f;
}
const saveFilters = () => store("calcFilters", { ...S.filters, disc: [...S.filters.disc] });

/** The saved groups, checked: at most 50 groups of at most 1000 ids each, names of up to 40 characters. */
function cleanGroups(raw) {
  const out = {};
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    for (const [name, ids] of Object.entries(raw).slice(0, 50)) {
      if (typeof name === "string" && name.trim() && Array.isArray(ids)) out[name.trim().slice(0, 40)] = [...new Set(ids.filter((x) => typeof x === "string"))].slice(0, 1000);
    }
  }
  return out;
}
const pretty = (s) => s.replace(/_/g, " ");

// ------------------------------------------------------------------ boot

async function boot() {
  setupTheme();
  setupTabs();
  setupKeys();
  const cfg = window.SLIDERULE_CONFIG || {};
  try {
    S.engine = await createEngine(cfg, (m) => ($("#loading-msg").textContent = m));
  } catch (e) {
    $("#loading").replaceChildren(
      h("h2", {}, "SlideRule could not start its calculation engine"),
      h("p", {}, e.message),
      h("p", {}, "If you opened index.html directly from disk, run `sliderule serve` instead, or use the hosted web version."),
    );
    return;
  }
  $("#engine-badge").textContent = S.engine.label;
  if (S.engine.kind === "browser") {   // the in-browser engine has no disk: restore this browser's saved settings and equations
    const savedSettings = store("settings");
    if (savedSettings) {
      try { await call("settings_set", { ...savedSettings, acknowledge_risk: true }); } catch (e) { console.warn("could not restore settings", e); }
    }
    const saved = store("custom");
    if (saved?.calculations?.length) {
      try { await call("custom_import", { document: saved, on_conflict: "replace" }); } catch (e) { console.warn("could not restore saved equations", e); }
    }
  }
  [S.meta, S.vocab] = await Promise.all([call("meta"), call("vocabulary")]);
  await syncLists();
  initSettings({ call, S, store });
  buildSidebar();
  buildConverter();
  buildAbout();
  updateCustomTab();
  await refreshList();
  $("#loading").hidden = true;
  window.addEventListener("hashchange", route);
  route();
}

function setupTheme() {
  $("#theme-toggle").addEventListener("click", () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    store("theme", root.dataset.theme);
  });
}

let design = null;
async function showDesign() {
  setView("calc");
  setMode("design");
  if (!design) {
    design = {};   // guard against re-entry while the editor loads
    design = await initSystemDesign($("#design"), { call, state: S, customChanged });
  }
  design.onShow?.();
}

/** Switch between one calculation in detail and the System Design canvas. The canvas is only hidden, never rebuilt, so
 *  the blocks and wires stay put until the user presses Clear (and it also keeps itself in browser storage). */
function setMode(mode) {
  S.mode = mode;
  const designMode = mode === "design";
  $("#view-calc").classList.toggle("mode-design", designMode);
  $("#detail").hidden = designMode;
  $("#design").hidden = !designMode;
  for (const [k, b] of Object.entries(S.modeBtns || {})) b.setAttribute("aria-pressed", String(k === mode));
  S.listEl?.querySelectorAll(".card").forEach((el) => { el.draggable = designMode; });
}
function goMode(mode) {
  location.hash = mode === "design" ? "#/design" : S.calc ? `#/calc/${S.calc.id}` : "#/";
}

// ---- LiveCalc
let live = null;
function showLive() {
  setView("live");
  live ||= initLiveCalc($("#view-live"), { call, S });
  live.onShow();
}

// ---- user-defined equations ("My equations")
let mine = null;
function updateCustomTab() {
  const n = S.meta.custom_count || 0;
  $('.tabs button[data-view="mine"]').textContent = n ? `My equations (${n})` : "My equations";
}
/** Call after the user library changed (saved, deleted, imported): refresh counts and lists, and keep a copy in browser storage. */
async function customChanged() {
  S.meta = await call("meta");
  updateCustomTab();
  S.vocab = await call("vocabulary");
  if (S.engine.kind === "browser") {
    try { store("custom", (await call("custom_export", {})).document); } catch { /* storage unavailable */ }
  }
  S.calc = null;   // reopen from the engine next time: its definition may have changed
  await refreshList();
  await design?.refreshDefinitions?.();
}
async function showMine(hash) {
  setView("mine");
  mine ||= initCustom($("#view-mine"), { call, S, changed: customChanged });
  const m = hash.match(/^#\/mine\/(new|edit)(?:\/([^?]+))?(?:\?(.*))?$/);
  if (!m) return mine.show({ mode: "list" });
  const q = new URLSearchParams(m[3] || "");
  return mine.show({ mode: m[1], id: m[2] ? decodeURIComponent(m[2]) : null, from: q.get("from"), draft: q.get("draft") });
}

/** "/" jumps to the search box from anywhere that is not a text field; ↓ in the search box moves into the list. */
function setupKeys() {
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target;
    const typing = t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));
    if (e.key === "/" && !typing && !$("#view-calc").hidden) {
      const box = $('[data-role="search"]');
      if (box && box.offsetParent !== null) { e.preventDefault(); box.focus(); box.select(); }
    } else if (e.key === "ArrowDown" && t?.dataset?.role === "search") {
      const first = S.listEl?.querySelector(".card");
      if (first) { e.preventDefault(); first.focus(); }
    }
  });
}

function setupTabs() {
  const tabs = [...document.querySelectorAll(".tabs button")];
  tabs.forEach((b) => {
    b.addEventListener("click", () => {
      const v = b.dataset.view;
      location.hash = v === "calc" ? (S.calc ? `#/calc/${S.calc.id}` : "#/") : `#/${v}`;
    });
    b.addEventListener("keydown", (e) => {                                  // the tab pattern: arrows move between tabs, Home and End jump
      const i = tabs.indexOf(b), to = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : null;
      if (to === null) return;
      e.preventDefault();
      const next = tabs[(to + tabs.length) % tabs.length];
      next.focus();
      next.click();
    });
  });
  $("#skip-link")?.addEventListener("click", (e) => {
    e.preventDefault();
    const target = [...document.querySelectorAll("main")].find((m) => !m.hidden);
    const first = target && (target.querySelector("#detail") || target);
    if (first) { first.tabIndex = -1; first.focus(); }
  });
}

function setView(v) {
  for (const name of ["calc", "live", "mine", "convert", "about"]) {
    $(`#view-${name}`).hidden = name !== v;
  }
  document.querySelectorAll(".tabs button").forEach((b) => { b.setAttribute("aria-selected", String(b.dataset.view === v)); b.tabIndex = b.dataset.view === v ? 0 : -1; });
}

function route() {
  const hash = location.hash;
  const m = hash.match(/^#\/calc\/([^?]+)(?:\?(.*))?$/);
  if (m) {
    setView("calc");
    setMode("calc");
    openCalc(decodeURIComponent(m[1]), new URLSearchParams(m[2] || ""));
  } else if (hash.startsWith("#/design")) showDesign();
  else if (hash.startsWith("#/live")) showLive();
  else if (hash.startsWith("#/mine")) showMine(hash);
  else if (hash.startsWith("#/convert")) setView("convert");
  else if (hash.startsWith("#/about")) setView("about");
  else {
    setView("calc");
    setMode("calc");
    if (!S.calc) showWelcome();
  }
}

// ------------------------------------------------------------------ sidebar: search + filters

function tokenInput(title, placeholder, suggestions, tokens, onChange) {
  const listId = "dl-" + title.replace(/\W+/g, "");
  const chips = h("div", { class: "chips" });
  const input = h("input", { class: "field", type: "text", placeholder, list: listId, "aria-label": title });
  const dl = h("datalist", { id: listId }, suggestions.map((s) => h("option", { value: s })));
  const render = () => {
    clear(chips);
    tokens.forEach((t, i) =>
      chips.append(
        h("span", { class: "chip token" }, t, h("button", { type: "button", "aria-label": `remove ${t}`, onclick: () => { tokens.splice(i, 1); render(); onChange(); } }, "×")),
      ),
    );
  };
  const commit = () => {
    const v = input.value.replace(/,/g, "").trim();
    if (v && !tokens.includes(v)) {
      tokens.push(v);
      render();
      onChange();
    }
    input.value = "";
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !input.value && tokens.length) {
      tokens.pop();
      render();
      onChange();
    }
  });
  input.addEventListener("change", commit);
  render();
  const quick = h("div", { class: "chips quick", "aria-label": `Common choices for ${title}` });
  const box = h("div", { class: "token-input" }, h("h3", {}, title), input, dl, chips, quick);
  box.setSuggestions = (list) => {                                                                       // what the other filters leave
    dl.replaceChildren(...list.map((x) => h("option", { value: x })));
    clear(quick);
    for (const k of list.filter((x) => box.kinds?.has(x) && x !== "dimensionless" && !tokens.includes(x)).slice(0, 8))            // the commonest quantities, one click each
      quick.append(h("button", { type: "button", class: "chip", title: `Add ${k}`, onclick: () => { tokens.push(k); render(); onChange(); } }, `+ ${k}`));
  };
  return box;
}

function buildSidebar() {
  const side = clear($("#sidebar"));
  const search = h("input", {
    class: "field", type: "search", value: S.filters.q, placeholder: "Search by name or topic, e.g. “beam deflection”", "aria-label": "Search calculations", dataset: { role: "search" },
    oninput: debounce((e) => { S.filters.q = e.target.value; refreshList(); }, 140),
  });
  S.chipEls = {};
  const chipFor = (d) => {
    const el = h("button", {
      type: "button", class: "chip", "aria-pressed": String(S.filters.disc.has(d.id)),
      onclick: () => {
        S.filters.disc.has(d.id) ? S.filters.disc.delete(d.id) : S.filters.disc.add(d.id);
        el.setAttribute("aria-pressed", String(S.filters.disc.has(d.id)));
        refreshList();
      },
    }, d.name, h("small", {}, String(d.count)));
    S.chipEls[d.id] = el;
    return el;
  };
  const core = S.meta.disciplines.filter((d) => d.group === "core");
  const emerging = S.meta.disciplines.filter((d) => d.group === "emerging");
  const chips = h("div", {},
    h("div", { class: "chips", role: "group", "aria-label": "Disciplines" }, core.map(chipFor)),
    h("details", { class: "emerging", open: emerging.some((d) => S.filters.disc.has(d.id)) },
      h("summary", {}, "Emerging and interdisciplinary fields"),
      h("div", { class: "chips", role: "group", "aria-label": "Emerging disciplines" }, emerging.map(chipFor))));
  const suggestions = [...S.vocab.kinds, ...S.vocab.symbols.map((s) => s.key)];
  S.tokenEls = {
    subs: tokenInput("Sub-discipline", "e.g. hydraulic, wind, tribology", S.meta.subdisciplines.map((x) => x.name), S.filters.subs, refreshList),
    vars: tokenInput("I have", "a symbol, word or quantity, e.g. force — Enter to add", suggestions, S.filters.vars, refreshList),
    solves: tokenInput("I need to find", "e.g. deflection, Re, temperature", suggestions, S.filters.solves, refreshList),
  };
  for (const t of Object.values(S.tokenEls)) t.kinds = new Set(S.vocab.kinds);
  S.countEl = h("span", { role: "status", "aria-live": "polite" });
  S.listEl = h("div", { class: "list", role: "list" });
  S.hintEl = h("p", { class: "list-hint" }, "Click a calculation, or drag it onto the canvas, to add it to the system. Keys: / search, ↑ ↓ move, Enter open, f favorite.");
  clear($("#listpane")).append(S.hintEl, S.listEl);
  S.listToggle = h("button", { type: "button", class: "link-btn", onclick: () => setListHidden(!S.listHidden) });
  setListHidden(S.listHidden);
  S.modeBtns = {
    calc: h("button", { type: "button", class: "seg", title: "Open one calculation and solve it", onclick: () => goMode("calc") }, "Single calculation"),
    design: h("button", { type: "button", class: "seg", title: "Wire several calculations into one system on a canvas", onclick: () => goMode("design") }, "System"),
  };
  S.levelEl = h("div", { class: "level-box" });
  renderLevel();
  side.append(
    h("div", { class: "mode-switch", role: "group", "aria-label": "Mode" }, S.modeBtns.calc, S.modeBtns.design),
    h("div", { class: "list-toggle-row" }, S.listToggle),
    S.levelEl,
    h("div", {}, h("h3", {}, "Search"), search),
    h("div", {}, h("h3", {}, "Discipline"), chips),
    S.tokenEls.subs, S.tokenEls.vars, S.tokenEls.solves,
    h("label", { class: "only-mine" }, h("input", { type: "checkbox", checked: S.filters.source === "custom", onchange: (e) => { S.filters.source = e.target.checked ? "custom" : ""; refreshList(); } }), "Only my equations"),
    h("div", { class: "result-meta" }, S.countEl,
      h("button", { type: "button", class: "link-btn", onclick: () => { S.filters = { q: "", disc: new Set(), vars: [], solves: [], subs: [], source: "" }; buildSidebar(); refreshList(); } }, "Reset filters")),
  );
  setMode(S.mode);
}

function setListHidden(hidden) {
  S.listHidden = hidden;
  store("listHidden", hidden);
  $("#view-calc").classList.toggle("list-hidden", hidden);
  $("#listpane").hidden = hidden;
  S.listToggle.textContent = hidden ? "Show calculation list" : "Hide calculation list";
  S.listToggle.setAttribute("aria-expanded", String(!hidden));
}

/** The ids the Custom (a group, or every group) and Favorites levels are limited to; null when the level is Basic or Advanced. */
function levelIds() {
  if (S.level === "favorites") return S.favorites;
  if (S.level === "recent") return S.recent;
  if (S.level === "custom") return S.group && S.groups[S.group] ? S.groups[S.group] : [...new Set(Object.values(S.groups).flat())];
  return null;
}

async function refreshList() {
  const seq = ++S.listSeq;
  const ids = levelIds();
  let r;
  if (ids && !ids.length) r = { count: 0, results: [], facets: { disciplines: [], subdisciplines: [], variables: [], solves: [] } };      // nothing starred, or an empty group: no need to ask the engine
  else {
    r = await call("list_calculations", {
      q: S.filters.q, disciplines: [...S.filters.disc], variables: S.filters.vars, solves_for: S.filters.solves, subdisciplines: S.filters.subs, source: S.filters.source,
      level: S.level === "basic" ? "basic" : "", ...(ids ? { ids } : {}), ...(S.level === "basic" && S.basicSubs ? { basic: S.basicSubs } : {}),
    });
  }
  if (seq !== S.listSeq) return;
  saveFilters();
  S.results = orderResults(r.results);
  S.countEl.textContent = `${r.count} calculation${r.count === 1 ? "" : "s"}`;
  for (const d of S.meta.disciplines) {
    const el = S.chipEls[d.id];
    if (!el) continue;
    const n = (r.facets.disciplines.find((x) => x.id === d.id) || {}).count || 0;
    el.querySelector("small").textContent = String(n);
    el.style.display = n || S.filters.disc.has(d.id) ? "" : "none";      // a discipline with nothing in the chosen Show set is not offered
  }
  const f = r.facets;
  S.tokenEls.subs.setSuggestions(f.subdisciplines.filter((x) => x.count).map((x) => x.name));
  S.tokenEls.vars.setSuggestions(f.variables);
  S.tokenEls.solves.setSuggestions(f.solves);
  const emerging = document.querySelector("details.emerging");
  if (emerging) emerging.style.display = [...emerging.querySelectorAll(".chip")].some((el) => el.style.display !== "none") ? "" : "none";
  renderList();
}

/** Recent is newest first and a single group keeps the order the user gave it, unless a search is ranking the list. */
function orderResults(results) {
  const order = S.level === "recent" ? S.recent : S.level === "custom" && S.group && !S.filters.q.trim() ? S.groups[S.group] : null;
  if (!order) return results;
  const at = new Map(order.map((id, i) => [id, i]));
  return [...results].sort((a, b) => (at.get(a.id) ?? 1e9) - (at.get(b.id) ?? 1e9));
}
const groupOrdered = () => S.level === "custom" && !!S.group && !S.filters.q.trim();

function noteRecent(id) {
  if (S.recent[0] === id) return;
  S.recent = [id, ...S.recent.filter((x) => x !== id)].slice(0, 30);
  saveLevelState();
  renderLevel();
  if (S.level === "recent") refreshList();
}

/** Move a calculation one place up or down inside the group being shown. */
function moveInGroup(id, by) {
  const ids = S.groups[S.group];
  const i = ids.indexOf(id), j = i + by;
  if (i < 0 || j < 0 || j >= ids.length) return;
  [ids[i], ids[j]] = [ids[j], ids[i]];
  saveLevelState();
  S.results = orderResults(S.results);
  renderList();
  S.listEl.querySelector(`.item[data-id="${CSS.escape(id)}"] .move.${by < 0 ? "up" : "down"}`)?.focus();
}

/** Favorites, groups, recent calculations and the choice of what Basic means, as a file (they are otherwise kept only in this browser). */
function exportLists() {
  const doc = { sliderule_lists: 1, favorites: S.favorites, groups: S.groups, recent: S.recent, ...(S.basicSubs ? { basic: S.basicSubs } : {}) };
  const url = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" }));
  const a = h("a", { href: url, download: "sliderule-lists.json" });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** Merge a lists file into what is here: favorites and group members are added, nothing is removed. */
async function importLists(file) {
  let doc;
  try { doc = JSON.parse(await file.text()); } catch { flash("That file is not valid JSON"); return; }
  if (!doc || doc.sliderule_lists !== 1) { flash("That is not a SlideRule lists file"); return; }
  const before = { fav: S.favorites.length, groups: Object.keys(S.groups).length };
  S.favorites = [...new Set([...S.favorites, ...(Array.isArray(doc.favorites) ? doc.favorites.filter((x) => typeof x === "string") : [])])].slice(-1000);
  const incoming = cleanGroups(doc.groups);
  for (const [name, ids] of Object.entries(incoming)) {
    if (!(name in S.groups) && Object.keys(S.groups).length >= 50) continue;
    S.groups[name] = [...new Set([...(S.groups[name] || []), ...ids])].slice(0, 1000);
  }
  if (!S.basicSubs && Array.isArray(doc.basic)) S.basicSubs = doc.basic.filter((x) => typeof x === "string").slice(0, 300);
  saveLevelState();
  renderLevel();
  refreshList();
  flash(`Imported: ${S.favorites.length - before.fav} new favorites, ${Object.keys(S.groups).length - before.groups} new groups`);
}

// ------------------------------------------------------------------ levels, favourites and the user's groups
const LEVELS = [
  ["basic", "Basic", "Classical mechanics and college-level chemistry"],
  ["advanced", "Advanced", "Every calculation"],
  ["custom", "Custom", "Your own groupings of calculations"],
  ["favorites", "Favorites", "The calculations you starred"],
  ["recent", "Recent", "The calculations you opened lately, newest first"],
];

function saveLevelState() {
  store("calcLevel", S.level);
  store("calcFavorites", S.favorites);
  store("calcGroups", S.groups);
  store("calcGroup", S.group);
  store("calcRecent", S.recent);
  store("calcBasicSubs", S.basicSubs);
  store("calcListsUpdated", Date.now());
  pushLists();
}

// ---- the lists on disk (installed app): every browser that opens the same app sees the same favorites and groups
const listsDoc = () => ({ favorites: S.favorites, groups: S.groups, recent: S.recent, ...(S.basicSubs ? { basic: S.basicSubs } : {}), updated: Number(store("calcListsUpdated")) || 0 });
const pushLists = debounce(async () => {
  if (!S.listsStored) return;
  try { await call("lists_set", { lists: listsDoc() }); } catch (e) { console.warn("could not save the lists", e); }
}, 700);

/** At start: the newer of the saved copy (on disk) and this browser's copy wins, as a whole. */
async function syncLists() {
  let r;
  try { r = await call("lists_get"); } catch { return; }
  S.listsStored = !!r.stored;
  if (!r.stored) return;
  const mine = Number(store("calcListsUpdated")) || 0, saved = r.lists;
  const hasLocal = S.favorites.length || Object.keys(S.groups).length || S.recent.length || S.basicSubs;
  if (saved && saved.updated > mine) {
    S.favorites = saved.favorites; S.groups = cleanGroups(saved.groups); S.recent = saved.recent.slice(0, 30); S.basicSubs = Array.isArray(saved.basic) ? saved.basic : null;
    if (S.group && !(S.group in S.groups)) S.group = "";
    store("calcFavorites", S.favorites); store("calcGroups", S.groups); store("calcGroup", S.group); store("calcRecent", S.recent); store("calcBasicSubs", S.basicSubs); store("calcListsUpdated", saved.updated);
  } else if (hasLocal && (!saved || mine > saved.updated)) {
    if (!mine) store("calcListsUpdated", Date.now());
    try { await call("lists_set", { lists: listsDoc() }); } catch (e) { console.warn("could not save the lists", e); }
  }
}

function setLevel(level) {
  S.level = level;
  saveLevelState();
  renderLevel();
  refreshList();
}

const isFavorite = (id) => S.favorites.includes(id);

function toggleFavorite(id) {
  S.favorites = isFavorite(id) ? S.favorites.filter((x) => x !== id) : [...S.favorites, id].slice(-1000);
  saveLevelState();
  renderLevel();
  if (S.level === "favorites") refreshList(); else renderList();
  if (S.calc?.id === id) renderDetail();
}

function newGroup(name) {
  name = (name || "").trim().slice(0, 40);
  if (!name) return null;
  if (Object.keys(S.groups).length >= 50 && !(name in S.groups)) { flash("At most 50 groups"); return null; }
  S.groups[name] ||= [];
  return name;
}

function toggleInGroup(id, name) {
  const ids = S.groups[name] || [];
  S.groups[name] = ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id].slice(-1000);
  saveLevelState();
  renderLevel();
  if (S.level === "custom") refreshList();
}

/** The Basic / Advanced / Custom / Favorites switch, and under it what belongs to the level chosen. */
function renderLevel() {
  if (!S.levelEl) return;
  const box = clear(S.levelEl);
  const basic = S.meta.levels?.basic?.count;
  box.append(h("h3", {}, "Show"),
    h("div", { class: "level-switch", role: "group", "aria-label": "Which calculations to list" }, LEVELS.map(([id, name, tip]) =>
      h("button", { type: "button", class: "seg", "aria-pressed": String(S.level === id), title: tip, "aria-label": `${name}: ${tip}`, dataset: { level: id }, onclick: () => setLevel(id) },
        name, id === "favorites" ? h("small", {}, String(S.favorites.length)) : id === "recent" && S.recent.length ? h("small", {}, String(S.recent.length)) : id === "basic" && basic ? h("small", {}, S.basicSubs ? "✎" : String(basic)) : null))));
  if (S.level === "basic") {
    const defaults = S.meta.levels?.basic?.subdisciplines || [];
    const tokens = [...(S.basicSubs || defaults)];
    const field = tokenInput("Basic includes", "add a sub-discipline", S.meta.subdisciplines.map((x) => x.name), tokens, () => {
      S.basicSubs = tokens.length === defaults.length && tokens.every((t) => defaults.includes(t)) ? null : [...tokens];
      saveLevelState();
      refreshList();
    });
    box.append(h("p", { class: "level-note" }, S.basicSubs ? "Your own choice of sub-disciplines (below)." : "Classical mechanics (kinematics, forces, energy, momentum, rotation, oscillations, collisions, statics) and college chemistry (general, analytical, kinetics, thermodynamics, electrochemistry, atomic structure, organic)."),
      h("details", { class: "basic-edit" }, h("summary", {}, "Change what Basic includes"), field,
        h("button", { type: "button", class: "link-btn", disabled: !S.basicSubs, onclick: () => { S.basicSubs = null; saveLevelState(); renderLevel(); refreshList(); } }, "Back to the default")));
  }
  if (S.level === "recent") box.append(h("p", { class: "level-note" }, S.recent.length ? "The calculations you opened lately, newest first." : "Nothing opened yet: calculations you open appear here."));
  if (S.level === "favorites") box.append(h("p", { class: "level-note" }, S.favorites.length ? "The calculations you starred (★ on a card or beside a calculation's title)." : "Nothing starred yet. Press ☆ on a calculation, or beside its title, to put it here."));
  if (S.level === "custom") {
    const names = Object.keys(S.groups);
    if (S.group && !(S.group in S.groups)) S.group = "";
    const pick = h("select", { "aria-label": "Group", onchange: (e) => { S.group = e.target.value; saveLevelState(); renderLevel(); refreshList(); } },
      h("option", { value: "" }, names.length ? "All my groups" : "No groups yet"), names.map((n) => h("option", { value: n, selected: n === S.group }, `${n} (${S.groups[n].length})`)));
    box.append(h("div", { class: "group-bar" }, pick,
      h("button", { type: "button", class: "btn small", title: "Make a new, empty group", onclick: () => { const n = newGroup(prompt("Name of the new group:", "")); if (n) { S.group = n; saveLevelState(); renderLevel(); refreshList(); } } }, "New"),
      h("button", { type: "button", class: "btn small", disabled: !S.group, title: "Rename the group", onclick: () => {
        const n = (prompt("New name for the group:", S.group) || "").trim().slice(0, 40);
        if (!n || n === S.group) return;
        if (n in S.groups && !confirm(`A group called “${n}” exists. Merge this group into it?`)) return;
        S.groups[n] = [...new Set([...(S.groups[n] || []), ...S.groups[S.group]])];
        delete S.groups[S.group];
        S.group = n; saveLevelState(); renderLevel(); refreshList();
      } }, "Rename"),
      h("button", { type: "button", class: "btn small", disabled: !S.group, title: "Delete the group (the calculations stay)", onclick: () => {
        if (!confirm(`Delete the group “${S.group}”? The calculations in it are not deleted.`)) return;
        delete S.groups[S.group]; S.group = ""; saveLevelState(); renderLevel(); refreshList();
      } }, "Delete")));
    box.append(h("p", { class: "level-note" }, names.length ? "Add a calculation to a group from the Groups menu beside its title. With one group chosen, ▲ ▼ on a card set its order." : "Make a group with New, then add calculations to it from the Groups menu beside a calculation's title."));
  }
  if (S.level === "favorites" || S.level === "custom") {
    const pickFile = h("input", { type: "file", accept: ".json,application/json", hidden: true, onchange: (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) importLists(f); } });
    box.append(h("div", { class: "group-bar" },
      h("button", { type: "button", class: "btn small", title: "Save favorites, groups and recent calculations to a file", onclick: exportLists }, "Export"),
      h("button", { type: "button", class: "btn small", title: "Add the favorites and groups of a saved file to these", onclick: () => pickFile.click() }, "Import"), pickFile));
  }
}


function renderList() {
  clear(S.listEl);
  if (!S.results.length) {
    const ids = levelIds();
    S.listEl.append(h("p", { class: "empty" }, ids && !ids.length
      ? (S.level === "favorites" ? "No favorites yet: press ☆ on a calculation to add it." : S.group ? "This group is empty: add calculations to it from the Groups menu beside a calculation's title." : "No groups yet: make one with New, then add calculations to it.")
      : S.level === "basic" ? "No basic calculation matches. Try fewer filters, or choose Advanced to search everything." : "No calculations match. Try fewer filters or a broader word."));
    return;
  }
  for (const c of S.results) {
    const open = () => (S.mode === "design" ? design?.addCalc?.(c.id) : (location.hash = `#/calc/${c.id}`));
    const card = h("div", {
      class: "card", role: "button", tabindex: "0", draggable: S.mode === "design", "aria-current": String(S.calc?.id === c.id), dataset: { id: c.id }, title: c.description,
      onclick: open,
      onkeydown: (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
        else if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); const cards = [...S.listEl.querySelectorAll(".card")]; cards[cards.indexOf(card) + (e.key === "ArrowDown" ? 1 : -1)]?.focus(); }
        else if (e.key === "f" && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); toggleFavorite(c.id); S.listEl.querySelector(`.card[data-id="${CSS.escape(c.id)}"]`)?.focus(); }
        else if (e.key === "Home" || e.key === "End") { e.preventDefault(); const cards = S.listEl.querySelectorAll(".card"); cards[e.key === "Home" ? 0 : cards.length - 1]?.focus(); }
      },
      ondragstart: (e) => { e.dataTransfer.setData("application/x-sliderule-calc", c.id); e.dataTransfer.setData("text/plain", c.name); e.dataTransfer.effectAllowed = "copy"; },
    }, h("span", { class: "name" }, c.name, c.custom ? h("span", { class: "badge custom" }, "custom") : null), h("span", { class: "disc" }, c.disciplines.join(" · ")), h("span", { class: "add", "aria-hidden": "true" }, "+"));
    const star = h("button", { type: "button", class: "star", "aria-pressed": String(isFavorite(c.id)), title: isFavorite(c.id) ? "Remove from favorites" : "Add to favorites", "aria-label": `${isFavorite(c.id) ? "Remove" : "Add"} ${c.name} ${isFavorite(c.id) ? "from" : "to"} favorites`,
      onclick: () => toggleFavorite(c.id) }, isFavorite(c.id) ? "★" : "☆");
    const moves = groupOrdered() ? h("span", { class: "moves" }, ...[["up", -1, "▲", "Move up"], ["down", 1, "▼", "Move down"]].map(([cls, by, glyph, tip]) =>
      h("button", { type: "button", class: `move ${cls}`, title: `${tip} in this group`, "aria-label": `${tip}: ${c.name}`, onclick: () => moveInGroup(c.id, by) }, glyph))) : null;
    S.listEl.append(h("div", { class: "item", role: "listitem", dataset: { id: c.id } }, card, star, moves));      // the star and the arrows sit beside the card, not inside it: a button must not contain buttons
  }
}

function markActive() {
  S.listEl?.querySelectorAll(".card").forEach((el) => el.setAttribute("aria-current", String(el.dataset.id === S.calc?.id)));
}

// ------------------------------------------------------------------ calculation detail + form

function showWelcome() {
  clear($("#detail")).append(
    h("div", { class: "panel hint-empty" },
      h("h2", {}, `${S.meta.calculation_count} engineering calculations`),
      h("p", {}, "Pick one on the left. Every result comes with a symbolic derivation and a numeric solution that show the units and conversions at each step."),
      h("p", {}, "No AI is involved: every number comes from deterministic code you can read."),
    ),
  );
}

async function openCalc(id, params) {
  if (S.calc?.id !== id) {
    try {
      S.calc = await call("get_calculation", { calc_id: id });
    } catch (e) {
      S.calc = null;
      clear($("#detail")).append(h("div", { class: "panel" }, h("p", {}, `Could not open "${id}": ${e.message}`)));
      return;
    }
    noteRecent(id);
    S.sweep = {};
    S.solution = null;
    S.odeTimes = "";
    S.search = {};
    S.prov = {};
    S.dataOptions = {};
    try {
      S.dataOptions = (await call("data_options", { variables: S.calc.variables.filter((v) => v.constant == null).map((v) => ({ key: v.key, unit: v.unit, label: v.label })) })).options || {};
    } catch { /* an engine without property data: no picker */ }
    S.unknown = new Set(S.calc.outputs);
    S.vals = {};
    for (const v of S.calc.variables) {
      if (v.constant == null) S.vals[v.key] = { value: v.default != null ? String(v.default) : "", unit: v.unit };
    }
    if (![...params.keys()].length) { applyExample(); await applyUnitPrefs(); } // start from the worked example so steps are visible at once
  }
  const find = params.get("find");
  if (find) S.unknown = new Set(find.split(",").filter((k) => S.vals[k]));
  for (const [k, raw] of params) {
    if (k === "find" || !S.vals[k]) continue;
    const q = splitQuantity(raw);
    if (q) S.vals[k] = { value: q.value, unit: q.unit || S.vals[k].unit };
  }
  renderDetail();
  markActive();
  scheduleSolve(0);
}

function splitQuantity(text) {
  const m = String(text).match(/^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*?)\s*$/);
  return m ? { value: m[1], unit: m[2] } : null;
}

document.addEventListener("click", (e) => document.querySelectorAll(".group-menu[open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; }));

/** The "Groups" menu of a calculation: tick the groups it belongs to, or start a new one. */
function groupMenu(id) {
  const names = Object.keys(S.groups);
  const inCount = names.filter((n) => S.groups[n].includes(id)).length;
  const menu = h("details", { class: "group-menu" }, h("summary", { class: "btn small", title: "Put this calculation in your own groups" }, inCount ? `Groups (${inCount})` : "Groups"),
    h("div", { class: "group-menu-body" },
      names.length ? names.map((n) => h("label", {}, h("input", { type: "checkbox", checked: S.groups[n].includes(id), onchange: () => { toggleInGroup(id, n); renderDetail(); } }), ` ${n}`)) : h("p", { class: "level-note" }, "No groups yet."),
      h("button", { type: "button", class: "link-btn", onclick: () => { const n = newGroup(prompt("Name of the new group:", "")); if (n) { toggleInGroup(id, n); renderDetail(); } } }, "New group with this calculation…")));
  return menu;
}

function renderDetail() {
  const c = S.calc;
  const root = clear($("#detail"));
  S.rows = {};

  const head = h("div", { class: "panel" },
    h("div", { class: "title-row" }, h("h2", {}, c.name), c.custom ? h("span", { class: "badge custom" }, "custom") : null, ...c.disciplines.map((d) => h("span", { class: "badge" }, d)),
      h("button", { type: "button", class: "star big", "aria-pressed": String(isFavorite(c.id)), title: isFavorite(c.id) ? "Remove from favorites" : "Add to favorites", onclick: () => toggleFavorite(c.id) }, isFavorite(c.id) ? "★ Favorite" : "☆ Favorite"),
      groupMenu(c.id),
      h("span", { class: "spacer" }),
      c.custom ? h("a", { class: "btn small", href: `#/mine/edit/${encodeURIComponent(c.id)}` }, "Edit") : null,
      h("a", { class: "btn small", href: `#/mine/new?from=${encodeURIComponent(c.id)}`, title: "Start a new equation of your own from this one" }, "Copy to My equations")),
    c.custom ? h("p", { class: "notice" }, "User-defined equation", c.author ? ` by ${c.author}` : "", ". Its units are checked for consistency, but it has not been reviewed like the built-in library.") : null,
    c.subdisciplines.length ? h("div", { class: "chips subs", "aria-label": "Sub-disciplines" }, c.subdisciplines.map((sd) =>
      h("button", { type: "button", class: "chip token", title: "Show all calculations in this sub-discipline", onclick: () => { S.filters.subs.length = 0; S.filters.subs.push(sd); buildSidebar(); refreshList(); } }, sd))) : null,
    c.unverified_references?.length ? h("p", { class: "notice" }, "⚠ ", `${c.unverified_references.length === 1 ? "A reference" : "References"} for this calculation ${c.unverified_references.length === 1 ? "has" : "have"} not been checked against a source; see “References” below.`) : null,
    h("p", { class: "desc" }, c.description),
    ...(c.odes || []).map((o) => h("div", { class: "ode", style: "margin-top:10px" },
      h("div", { class: "t" }, o.title, " ", h("span", { class: "badge" }, o.kind === "closed" ? "solved in closed form" : "solved numerically"),
        o.kind === "numeric" && o.why_numeric ? h("span", { class: "hint" }, ` (${o.why_numeric})`) : null),
      ...o.latex.map((q) => math(q, true)), ...o.conditions.map((q) => h("div", { class: "cond" }, o.bvp ? null : "with ", math(q))),
      ...(o.events || []).map((e) => h("div", { class: "cond" }, `${e.terminal ? "stops at" : "marks"} “${e.title}”: `, math(e.latex), ` (${e.direction === "either" ? "any crossing" : e.direction})`)))),
    h("div", { style: "margin-top:10px" }, ...c.equations.map((e) => h("div", { class: "eq" }, e.title && c.equations.length > 1 ? h("div", { class: "t" }, e.title) : null, math(e.latex, true), e.evaluated ? h("div", { class: "evaluated" }, "evaluates to ", math(e.evaluated)) : null))),
  );

  const form = h("div", { class: "form" });
  for (const v of c.variables) {
    if (v.constant != null) continue;
    const isUnknown = S.unknown.has(v.key);
    const state = S.vals[v.key];
    const value = h("input", {
      class: "value", type: "text", inputMode: "decimal", autocomplete: "off", spellcheck: false, value: isUnknown ? "" : state.value,
      placeholder: isUnknown ? "result" : "value", "aria-label": `${v.label} value`,
      oninput: (e) => { state.value = e.target.value; e.target.classList.toggle("bad", e.target.value.trim() !== "" && !isFinite(Number(e.target.value))); editedByHand(v.key); scheduleSolve(); },
    });
    const picker = unitPicker(v.units, state.unit, () => { state.unit = picker.get(); rememberUnit(v, state.unit); editedByHand(v.key); scheduleSolve(0); });
    const find = h("input", { type: "checkbox", checked: isUnknown, "aria-label": `solve for ${v.label}`, onchange: (e) => toggleUnknown(v.key, e.target.checked, e.target) });
    const opts = S.dataOptions?.[v.key] || [];
    const dataBtn = opts.length ? h("button", { type: "button", class: "link data-btn", title: "Fill this input from property data (materials, fluids) and keep the source",
      onclick: () => openDataPicker({ call, variable: v, options: opts, current: picker.get() || v.unit, onApply: (r) => applyDataValue(v.key, r) }) }, "from data…") : null;
    const prov = h("div", { class: "data-prov", hidden: true });
    const row = h("div", { class: "row" + (isUnknown ? " unknown" : ""), dataset: { key: v.key } },
      h("label", { class: "find", title: "Tick to solve for this quantity" }, find, "find"),
      h("span", { class: "sym" }, math(v.latex)),
      h("div", { class: "label" }, v.label, h("small", {}, pretty(v.kind) + (v.delta ? " (difference)" : "") + (v.signed ? "" : "")), dataBtn),
      value, picker.el, prov,
    );
    if (v.min != null || v.max != null || v.note) {
      const bits = [];
      if (v.min != null) bits.push(`≥ ${v.min} ${v.unit}`);
      if (v.max != null) bits.push(`≤ ${v.max} ${v.unit}`);
      if (v.note) bits.push(v.note);
      row.append(h("div", { class: "note" }, bits.join(" · ")));
    }
    const range = h("details", { class: "search-range", hidden: !isUnknown },
      h("summary", {}, "search range"),
      h("span", { class: "hint" }, "Only used when this value cannot be isolated and has to be found numerically (for example from a numerically solved differential equation). Give an interval that contains the answer, in the unit chosen above."),
      h("input", { class: "field", type: "text", placeholder: "from", "aria-label": `${v.label} search from`, value: S.search[v.key]?.lo || "", oninput: (e) => { (S.search[v.key] ||= {}).lo = e.target.value; scheduleSolve(); } }),
      h("input", { class: "field", type: "text", placeholder: "to", "aria-label": `${v.label} search to`, value: S.search[v.key]?.hi || "", oninput: (e) => { (S.search[v.key] ||= {}).hi = e.target.value; scheduleSolve(); } }));
    row.append(range);
    S.rows[v.key] = { row, value, picker, find, range, prov };
    paintProv(v.key);
    form.append(row);
  }

  const consts = c.variables.filter((v) => v.constant != null);
  const constBox = consts.length
    ? h("details", { class: "constants" }, h("summary", {}, `${consts.length} fixed constant${consts.length > 1 ? "s" : ""} used`),
        h("ul", {}, consts.map((v) => h("li", {}, math(v.latex), ` — ${v.label} = ${v.constant} ${v.unit}`, v.note ? ` (${v.note})` : ""))))
    : null;

  const sigSel = h("select", { "aria-label": "significant figures", onchange: (e) => { S.sig = Number(e.target.value); store("sig", S.sig); scheduleSolve(0); } },
    [3, 4, 5, 6, 8, 10].map((n) => h("option", { value: n, selected: n === S.sig }, String(n))));
  const caseFile = h("input", { type: "file", accept: ".json,application/json", hidden: true, onchange: (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) openCase(f); } });
  const toolbar = h("div", { class: "toolbar" },
    h("button", { type: "button", class: "btn primary", onclick: () => solveNow() }, "Calculate"),
    h("button", { type: "button", class: "btn", onclick: loadExample }, "Load example"),
    h("button", { type: "button", class: "btn", onclick: clearInputs }, "Clear"),
    h("button", { type: "button", class: "btn", onclick: copyLink }, "Copy link"),
    h("button", { type: "button", class: "btn", title: "Copy the inputs and results as plain text", onclick: copyText }, "Copy as text"),
    h("button", { type: "button", class: "btn", title: "Save this case (inputs, unknowns, results) as a file", onclick: saveCase }, "Save case"),
    h("button", { type: "button", class: "btn", title: "Open a case saved earlier", onclick: () => caseFile.click() }, "Open case"), caseFile,
    h("label", {}, "Significant figures", sigSel),
    c.odes?.length ? h("label", { title: "Extra times (in the unit of the time input) to list in a table, e.g. 5, 10, 20" }, "Tabulate at times",
      h("input", { class: "field times", type: "text", placeholder: "e.g. 5, 10, 20", value: S.odeTimes, "aria-label": "Times to tabulate", oninput: (e) => { S.odeTimes = e.target.value; scheduleSolve(); } })) : null,
  );
  const formPanel = h("div", { class: "panel" }, h("h3", {}, "Inputs", h("span", { class: "spacer" }),
    h("span", { class: "badge" }, "tick “find” for unknowns · pick any unit")), form, constBox, toolbar);

  S.solutionEl = h("div", { id: "solution" });
  const sweepPanel = sweepBox();
  const meta = h("div", { class: "panel" }, h("h3", {}, "Assumptions and references"),
    c.assumptions.length ? h("details", { class: "meta", open: true }, h("summary", {}, "Assumptions"), h("ul", {}, c.assumptions.map((a) => h("li", {}, a)))) : null,
    c.references.length ? h("details", { class: "meta", open: !!c.unverified_references?.length }, h("summary", {}, "References", c.unverified_references?.length ? h("span", { class: "badge unverified", title: "Some of these references were not checked against a source" }, ` ${c.unverified_references.length} not verified`) : null),
      h("ul", {}, c.references.map((a) => { const u = (c.unverified_references || []).find((x) => x.reference === a); return h("li", {}, a, u ? h("div", { class: "unverified-ref" }, "⚠ Not verified: ", u.note) : null); }))) : null,
    h("p", { class: "desc", style: "margin-top:8px" }, `ID: ${c.id}`));
  root.append(head, formPanel, sweepPanel, S.solutionEl, meta);
}

/** The line under an input that came from property data: what it is, where it is from, and whether it was edited since. */
function paintProv(key) {
  const r = S.rows[key], p = S.prov[key];
  if (!r?.prov) return;
  r.prov.hidden = !p;
  if (!p) return;
  clear(r.prov).append(...[h("span", { class: "badge" }, "data"), ` ${provenanceText(p)}`, p.edited ? h("strong", {}, " — edited by hand since") : null,
    h("button", { type: "button", class: "link", title: "Forget where this value came from", "aria-label": "forget the data source", onclick: () => { delete S.prov[key]; paintProv(key); } }, "×")].filter(Boolean));
}

function editedByHand(key) {
  const p = S.prov[key];
  if (p && !p.edited) { p.edited = true; paintProv(key); }
}

function applyDataValue(key, r) {
  const v = S.calc.variables.find((x) => x.key === key), row = S.rows[key];
  if (!v || !row) return;
  const text = String(Number(Number(r.value).toPrecision(6)));
  S.vals[key] = { value: text, unit: row.picker.get() || v.unit };
  row.value.value = text;
  row.value.classList.remove("bad");
  S.prov[key] = { pack: r.pack, pack_version: r.pack_version, record: r.record, record_name: r.record_name, property: r.property, label: r.label,
    value: Number(text), unit: r.unit, x: r.x ?? null, x_unit: r.x_unit ?? null, basis: r.basis, rel_uncertainty: r.rel_uncertainty ?? null, source: r.source, design_use: r.design_use };
  paintProv(key);
  scheduleSolve(0);
}

function toggleUnknown(key, on, box) {
  if (on) S.unknown.add(key);
  else if (S.unknown.size > 1) S.unknown.delete(key);
  else {
    box.checked = true; // at least one unknown is required
    return;
  }
  const r = S.rows[key];
  const isUnknown = S.unknown.has(key);
  if (isUnknown) { delete S.prov[key]; paintProv(key); }          // a result is not data any more
  r.row.classList.toggle("unknown", isUnknown);
  r.value.value = isUnknown ? "" : S.vals[key].value;
  r.value.placeholder = isUnknown ? "result" : "value";
  r.range.hidden = !isUnknown;
  scheduleSolve(0);
}

function applyExample() {
  const c = S.calc;
  S.unknown = new Set(c.outputs);
  for (const v of c.variables) {
    if (v.constant != null) continue;
    const q = c.example[v.key] != null ? splitQuantity(c.example[v.key]) : null;
    S.vals[v.key] = q ? { value: q.value, unit: q.unit || v.unit } : { value: v.default != null ? String(v.default) : "", unit: v.unit };
  }
}

/** The unit last chosen for each kind of quantity (inches once, inches everywhere it makes sense); kept in this browser. */
const unitPrefs = () => (store("unitPrefs") && typeof store("unitPrefs") === "object" ? store("unitPrefs") : {});
function rememberUnit(v, unit) {
  if (!v.units?.includes(unit) || !v.kind) return;
  const prefs = unitPrefs();
  prefs[v.kind] = unit;
  store("unitPrefs", prefs);
}

/** Show the example in the units the user prefers: values are converted (not just relabelled) by the engine. */
async function applyUnitPrefs() {
  const prefs = unitPrefs();
  await Promise.all(S.calc.variables.map(async (v) => {
    const want = prefs[v.kind], st = S.vals[v.key];
    if (v.constant != null || !st || !want || want === st.unit || !v.units?.includes(want)) return;
    if (S.unknown.has(v.key) || st.value.trim() === "") { st.unit = want; return; }       // a result, or nothing typed yet: just choose the unit
    try {
      const r = await call("convert", { value: Number(st.value), from_unit: st.unit, to_unit: want, sig_figs: 8 });
      if (r.ok) S.vals[v.key] = { value: String(r.value_text), unit: want };
    } catch { /* keep the example's own unit */ }
  }));
}

async function loadExample() {
  applyExample();
  await applyUnitPrefs();
  renderDetail();
  scheduleSolve(0);
}

function clearInputs() {
  for (const v of S.calc.variables) if (v.constant == null) S.vals[v.key] = { value: v.default != null ? String(v.default) : "", unit: v.unit };
  S.solution = null;
  S.prov = {};
  renderDetail();
}

function shareHash() {
  const p = new URLSearchParams();
  p.set("find", [...S.unknown].join(","));
  for (const [k, v] of Object.entries(S.vals)) if (!S.unknown.has(k) && v.value.trim() !== "") p.set(k, `${v.value} ${v.unit}`.trim());
  return `#/calc/${S.calc.id}?${p}`;
}

async function copyLink() {
  history.replaceState(null, "", shareHash());
  try {
    await navigator.clipboard.writeText(location.href);
    flash("Link copied");
  } catch {
    flash("Copy the address bar to share this calculation");
  }
}

/** The case on screen as plain text: what was given, what was found, in the units shown. */
function caseText() {
  const c = S.calc, lines = [c.name, `(${c.id})`, ""];
  const unitOf = (k) => S.rows[k]?.picker.get() ?? "";
  for (const v of c.variables) {
    if (v.constant != null) continue;
    const val = S.unknown.has(v.key) ? S.rows[v.key]?.value.value : S.vals[v.key].value;
    lines.push(`${S.unknown.has(v.key) ? "→" : " "} ${v.label} = ${val || "?"} ${unitOf(v.key)}`.trimEnd());
  }
  const data = Object.entries(S.prov).map(([k, p]) => `  ${c.variables.find((v) => v.key === k)?.label || k}: ${provenanceText(p)}${p.edited ? " (edited by hand since)" : ""}`);
  return lines.join("\n") + "\n\n→ marks what was solved for." + (data.length ? `\n\nValues from property data (not for design unless stated):\n${data.join("\n")}` : "");
}

async function copyText() {
  try { await navigator.clipboard.writeText(caseText()); flash("Copied as text"); } catch { flash("Clipboard unavailable"); }
}

function saveCase() {
  const c = S.calc;
  const doc = { sliderule_case: 1, calc_id: c.id, name: c.name, solve_for: [...S.unknown], inputs: {}, results: {}, data_sources: JSON.parse(JSON.stringify(S.prov)) };
  for (const v of c.variables) {
    if (v.constant != null) continue;
    if (S.unknown.has(v.key)) doc.results[v.key] = { value: S.rows[v.key]?.value.value || "", unit: S.rows[v.key]?.picker.get() ?? "" };
    else doc.inputs[v.key] = { value: S.vals[v.key].value, unit: S.rows[v.key]?.picker.get() ?? S.vals[v.key].unit };
  }
  const url = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" }));
  const a = h("a", { href: url, download: `${c.id.replace(/[^\w.-]+/g, "_")}.case.json` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** Open a saved case: go to its calculation with those inputs (the same address a shared link uses). */
async function openCase(file) {
  let doc;
  try { doc = JSON.parse(await file.text()); } catch { flash("That file is not valid JSON"); return; }
  if (!doc || doc.sliderule_case !== 1 || typeof doc.calc_id !== "string" || typeof doc.inputs !== "object") { flash("That is not a SlideRule case file"); return; }
  const p = new URLSearchParams();
  if (Array.isArray(doc.solve_for) && doc.solve_for.length) p.set("find", doc.solve_for.filter((x) => typeof x === "string").join(","));
  for (const [k, v] of Object.entries(doc.inputs || {})) if (v && typeof v.value === "string" && v.value.trim() !== "" && isFinite(Number(v.value))) p.set(k, `${v.value} ${typeof v.unit === "string" ? v.unit : ""}`.trim());
  S.calc = null;                      // reopen from the engine so the file's values replace what is on screen
  location.hash = `#/calc/${doc.calc_id}?${p}`;
  flash("Case opened");
}

// ------------------------------------------------------------------ sweeping one input

/** "Sweep one input": solve over a range of one input and graph a result against it. */
function sweepBox() {
  const c = S.calc;
  const inputs = c.variables.filter((v) => v.constant == null && !S.unknown.has(v.key));
  const outputs = c.variables.filter((v) => S.unknown.has(v.key));
  const box = h("details", { class: "panel sweep", open: !!S.sweep.open, ontoggle: (e) => { S.sweep.open = e.target.open; } },
    h("summary", {}, h("strong", {}, "Sweep one input"), h("span", { class: "hint" }, " — graph a result as one input varies")));
  if (!inputs.length || !outputs.length || c.odes?.length) {
    box.append(h("p", { class: "hint" }, c.odes?.length ? "Differential-equation calculations already plot against time; change an input and calculate again to compare." : "Tick “find” on a result and leave at least one input to sweep."));
    return box;
  }
  const sw = S.sweep;
  sw.vary = inputs.some((v) => v.key === sw.vary) ? sw.vary : inputs[0].key;
  sw.out = outputs.some((v) => v.key === sw.out) ? sw.out : outputs[0].key;
  const num = (x) => String(Number(x.toPrecision(6)));
  const fillRange = () => {
    const x = Number(S.vals[sw.vary]?.value);
    if (isFinite(x) && x !== 0) { sw.lo = num(x > 0 ? x / 2 : x * 2); sw.hi = num(x > 0 ? x * 2 : x / 2); } else { sw.lo = "0"; sw.hi = "1"; }
    lo.value = sw.lo; hi.value = sw.hi;
  };
  const sel = (items, current, on) => h("select", { class: "field", onchange: (e) => on(e.target.value) }, items.map((v) => h("option", { value: v.key, selected: v.key === current }, `${v.label} (${v.key})`)));
  const lo = h("input", { class: "field", type: "text", inputMode: "decimal", value: sw.lo ?? "", "aria-label": "from", oninput: (e) => { sw.lo = e.target.value; } });
  const hi = h("input", { class: "field", type: "text", inputMode: "decimal", value: sw.hi ?? "", "aria-label": "to", oninput: (e) => { sw.hi = e.target.value; } });
  const n = h("input", { class: "field", type: "number", min: "2", max: "200", value: sw.n ?? 25, "aria-label": "points", oninput: (e) => { sw.n = e.target.value; } });
  const log = h("input", { type: "checkbox", checked: !!sw.log, onchange: (e) => { sw.log = e.target.checked; } });
  const second = h("select", { class: "field", "aria-label": "second input", onchange: (e) => { sw.second = e.target.value; } },
    h("option", { value: "" }, "none"), inputs.map((v) => h("option", { value: v.key, selected: v.key === sw.second }, `${v.label} (${v.key})`)));
  const secondVals = h("input", { class: "field", type: "text", placeholder: "e.g. 2, 4, 8", value: sw.secondVals ?? "", "aria-label": "values of the second input", oninput: (e) => { sw.secondVals = e.target.value; } });
  const out = h("div", { class: "sweep-out", "aria-live": "polite" });
  if (sw.lo == null) fillRange();
  const run = async () => {
    clear(out);
    const a = Number(sw.lo), b = Number(sw.hi), count = Math.round(Number(sw.n ?? 25));
    if (!isFinite(a) || !isFinite(b) || a === b) { out.append(h("p", { class: "hint" }, "Give two different numbers for from and to.")); return; }
    if (!(count >= 2 && count <= 200)) { out.append(h("p", { class: "hint" }, "Use between 2 and 200 points.")); return; }
    if (sw.log && (a <= 0 || b <= 0)) { out.append(h("p", { class: "hint" }, "Logarithmic spacing needs positive limits.")); return; }
    const given = {};
    for (const v of inputs) {
      const raw = S.vals[v.key].value.trim();
      if (raw === "" || !isFinite(Number(raw))) { out.append(h("p", { class: "hint" }, `Enter a value for ${v.label} first (it stays fixed while the other one is swept).`)); return; }
      given[v.key] = { value: Number(raw), unit: S.rows[v.key].picker.get() };
    }
    const values = Array.from({ length: count }, (_, i) => (sw.log ? a * (b / a) ** (i / (count - 1)) : a + ((b - a) * i) / (count - 1)));
    const outUnits = {};
    for (const v of outputs) outUnits[v.key] = S.rows[v.key].picker.get();
    const sec = sw.second && sw.second !== sw.vary ? inputs.find((v) => v.key === sw.second) : null;
    let steps = [null];
    if (sec) {                                                                  // a second input: one curve for each of its values
      steps = String(sw.secondVals || "").split(/[,;\s]+/).filter(Boolean).map(Number);
      if (!steps.length || steps.some((x) => !isFinite(x)) || steps.length > 6) { out.append(h("p", { class: "hint" }, `Give 1 to 6 numbers for ${sec.label}, separated by commas.`)); return; }
    }
    out.append(h("p", { class: "hint" }, "Calculating…"));
    const runs = [];
    for (const v2 of steps) {
      const g2 = v2 === null ? given : { ...given, [sec.key]: { ...given[sec.key], value: v2 } };
      try { runs.push(await call("sweep", { calc_id: c.id, inputs: g2, vary: sw.vary, values, solve_for: outputs.map((v) => v.key), output_units: outUnits, sig_figs: S.sig })); } catch (e) { clear(out).append(h("p", { class: "hint" }, e.message)); return; }
    }
    clear(out);
    const r = runs[0];
    const sers = runs.map((rr) => rr.series.find((x) => x.key === sw.out));
    if (sers.every((x) => !x || x.y.every((y) => y == null))) { out.append(h("p", { class: "hint" }, "The calculation has no answer anywhere in this range.")); return; }
    const ser = sers.find(Boolean);
    const vlabel = inputs.find((v) => v.key === sw.vary).label;
    const curves = sers.map((x, i) => ({ label_latex: sec ? `${sec.latex} = ${steps[i]}\\ \\text{${given[sec.key].unit}}` : ser.latex, y: x ? x.y : r.x.map(() => null) }));
    out.append(xyPlot({ var: vlabel, x: r.x, x_unit: r.x_unit, y_unit: ser.unit, markers: r.x.length <= 40 && curves.length === 1, logx: !!sw.log, series: curves }));
    const failed = runs.reduce((a, rr) => a + rr.failed, 0);
    if (failed) out.append(h("p", { class: "hint" }, `${failed} of ${runs.length * r.points} points have no answer (shown as gaps).`));
    out.append(h("button", { type: "button", class: "btn small", onclick: () => {
      const rows = [`${vlabel} (${r.x_unit}),${sers.map((x, i) => `${ser.label} (${ser.unit})${sec ? ` at ${sec.key} = ${steps[i]}` : ""}`).join(",")}`, ...r.x.map((x, i) => `${x},${sers.map((q) => q?.y[i] ?? "").join(",")}`)];
      const url = URL.createObjectURL(new Blob([rows.join("\n")], { type: "text/csv" }));
      const a2 = h("a", { href: url, download: "sweep.csv" }); document.body.append(a2); a2.click(); a2.remove(); setTimeout(() => URL.revokeObjectURL(url), 1500);
    } }, "Download CSV"));
  };
  box.append(h("div", { class: "sweep-form" },
    h("label", {}, "Vary", sel(inputs, sw.vary, (k) => { sw.vary = k; fillRange(); })),
    h("label", {}, "From", lo), h("label", {}, "To", hi), h("label", {}, "Points", n),
    h("label", { class: "chk" }, log, " log spacing"),
    h("label", {}, "Graph", sel(outputs, sw.out, (k) => { sw.out = k; })),
    h("label", {}, "Also vary", second), h("label", {}, "at the values", secondVals),
    h("button", { type: "button", class: "btn primary", onclick: run }, "Sweep")),
    h("p", { class: "hint" }, "From and to are in the unit chosen for that input above; every other input keeps its value."), out);
  return box;
}

// ------------------------------------------------------------------ solving

const scheduleSolve = (() => {
  const deb = debounce(() => solveNow(), 350);
  return (ms) => (ms === 0 ? solveNow() : deb());
})();

const parseTimes = (text) => String(text || "").split(/[,;\n]/).map((s) => s.trim()).filter(Boolean).map((s) => (isFinite(Number(s)) ? Number(s) : s));

async function solveNow() {
  if (!S.calc) return;
  const c = S.calc;
  const inputs = {};
  const missing = [];
  let bad = false;
  for (const v of c.variables) {
    if (v.constant != null || S.unknown.has(v.key)) continue;
    const st = S.vals[v.key];
    const raw = st.value.trim();
    if (raw === "") missing.push(v.label);
    else if (!isFinite(Number(raw))) bad = true;
    else inputs[v.key] = { value: Number(raw), unit: S.rows[v.key].picker.get() };
  }
  if (bad || missing.length) {
    S.solution = null;
    for (const k of S.unknown) S.rows[k].value.value = "";
    renderSolution(null, bad ? "Some values are not valid numbers." : `Enter ${missing.length === 1 ? "a value" : "values"} for: ${missing.join(", ")}.`);
    return;
  }
  const output_units = {};
  const search = {};
  for (const k of S.unknown) {
    output_units[k] = S.rows[k].picker.get();
    const r = S.search[k];
    if (r && r.lo?.trim() && r.hi?.trim()) search[k] = [`${r.lo.trim()} ${output_units[k]}`, `${r.hi.trim()} ${output_units[k]}`];
  }
  const seq = ++S.solveSeq;
  let sol;
  try {
    sol = await call("solve", { calc_id: c.id, inputs, solve_for: [...S.unknown], output_units, sig_figs: S.sig, ode_times: c.odes?.length ? parseTimes(S.odeTimes) : undefined, search: Object.keys(search).length ? search : undefined });
  } catch (e) {
    renderSolution(null, e.message);
    return;
  }
  if (seq !== S.solveSeq) return;
  S.solution = sol;
  history.replaceState(null, "", shareHash());
  renderSolution(sol);
}

function renderSolution(sol, hint) {
  const root = clear(S.solutionEl);
  if (!sol) {
    root.append(h("div", { class: "panel" }, h("p", { class: "desc" }, hint || "")));
    return;
  }
  const panels = [];
  if (sol.diagnostics.length) {
    const order = { error: 0, warning: 1, info: 2 };
    const list = [...sol.diagnostics].sort((a, b) => order[a.level] - order[b.level]);
    panels.push(h("ul", { class: "diag", role: "list" }, list.map((d) => h("li", { class: d.level }, h("code", {}, d.code), d.message))));
  }
  if (!sol.ok) {
    for (const k of S.unknown) S.rows[k].value.value = "";
    root.append(h("div", { class: "panel" }, h("h3", {}, "Cannot calculate"), ...panels));
    return;
  }
  for (const o of sol.outputs) {
    const r = S.rows[o.key];
    if (r) r.value.value = o.value_text;
  }
  const results = h("div", { class: "results" }, sol.outputs.map((o) => h("div", { class: "result" }, h("div", { class: "lbl" }, o.label), math(o.result_latex, true))));
  const inter = sol.intermediates.length
    ? h("details", { class: "intermediates" }, h("summary", {}, `${sol.intermediates.length} intermediate value${sol.intermediates.length > 1 ? "s" : ""}`),
        sol.intermediates.map((o) => h("div", {}, math(o.result_latex), ` — ${o.label}`)))
    : null;
  root.append(
    h("div", { class: "panel" }, h("h3", {}, "Results"), ...panels, results, inter),
    ...(sol.series || []).map(solutionPlots),
    ...[valuesTable(sol.table || [])].filter(Boolean),
    stepsPanel(sol, S),
  );
}

// ------------------------------------------------------------------ unit converter

async function buildConverter() {
  const root = clear($("#view-convert"));
  const { kinds } = await call("kinds");
  const kindSel = h("select", { class: "field", "aria-label": "Quantity" }, kinds.map((k) => h("option", { value: k.kind }, k.kind)));
  const value = h("input", { class: "field", type: "text", inputMode: "decimal", value: "1", "aria-label": "value" });
  const out = h("div", { class: "conv-out", "aria-live": "polite" });
  const steps = h("div", { class: "steps", style: "margin-top:10px" });
  const info = h("div", { class: "desc" });
  const run = debounce(async () => {
    const n = Number(value.value);
    clear(steps); clear(out); clear(info);
    if (value.value.trim() === "" || !isFinite(n)) return;
    let r;
    try { r = await call("convert", { value: n, from_unit: from.get(), to_unit: to.get(), sig_figs: S.sig + 1 }); } catch (e) { out.textContent = e.message; return; }
    if (!r.ok) { out.append(h("div", { class: "diag" }, h("li", { class: "error" }, r.error))); return; }
    out.append(math(r.result_latex, true));
    steps.append(h("section", { class: "step" }, h("h4", {}, "Working"), r.steps.map((l) => h("div", { class: "line" }, h("div", { class: "m" }, math(l, true)), h("div", { class: "n" })))));
    if (r.notes.length) info.append(h("ul", { class: "diag" }, r.notes.map((n2) => h("li", { class: "info" }, n2))));
  }, 120);
  const from = unitPicker([], "", run);
  const to = unitPicker([], "", run);
  const fill = () => {
    const k = kinds.find((x) => x.kind === kindSel.value);
    from.set(k.units, k.units[0]);
    to.set(k.units, k.units[1] || k.units[0]);
    run();
  };
  kindSel.addEventListener("change", fill);
  value.addEventListener("input", run);
  const swap = h("button", { type: "button", class: "btn", onclick: () => { const a = from.get(), b = to.get(); const k = kinds.find((x) => x.kind === kindSel.value); from.set(k.units, b); to.set(k.units, a); run(); } }, "⇄ Swap");
  root.append(h("div", { class: "panel" },
    h("h3", {}, "Unit converter"),
    h("p", { class: "desc" }, "Pick a quantity or type any unit expression such as ", h("code", {}, "Btu/(h*ft^2*degF)"), " via “custom…”. Dimensions are checked, so you cannot convert pressure to force."),
    h("div", { class: "conv-grid", style: "margin-top:10px" },
      h("label", {}, "Quantity", kindSel), h("label", {}, "Value", value),
      h("label", {}, "From", from.el), h("label", {}, "To", to.el)),
    h("div", { class: "toolbar" }, swap), out, info, steps));
  kindSel.value = "pressure";
  fill();
}

// ------------------------------------------------------------------ about

function buildAbout() {
  $("#view-about").innerHTML = `
    <div class="panel">
      <h2>About SlideRule</h2>
      <p>SlideRule is a collection of engineering calculations that <strong>shows its work</strong>. Each calculation is a small, readable
      definition — variables with units and governing equations — and everything else (unit conversion, rearrangement, evaluation and the written
      steps) is generated by deterministic code. No language model is used anywhere.</p>
      <h2>How units are handled</h2>
      <ul>
        <li>Every variable has a physical dimension. Entering <code>psi</code> where a force is expected is an error, not a silent mistake.</li>
        <li>All inputs are converted to coherent SI before calculating; the conversion factor is shown. Results are converted back to the unit you pick.</li>
        <li>Mixing unit systems (e.g. <code>lbf</code> with <code>mm²</code>) still gives a correct result but raises a warning, because it is a common data-entry slip.</li>
        <li>Every governing equation is checked for dimensional homogeneity when it is loaded; an inconsistent equation cannot be registered.</li>
        <li>Temperature scales (°C, °F) are offset units. For temperature <em>differences</em> the app uses difference units (Δ°C, Δ°F, K) with no offset.</li>
        <li>Ambiguous names are rejected: use <code>lbm</code> or <code>lbf</code> (never <code>lb</code>); gauge pressure is an offset unit like °C (<code>psig</code>, <code>barg</code>, <code>kPag</code> = absolute minus 1 atm).</li>
        <li><code>Hz</code> is 1/s and angles are dimensionless (rad = 1). Remember ω = 2πf. <code>rpm</code> is an angular speed (1 rpm = 0.1047 rad/s).</li>
        <li>Oilfield prefixes <code>Mbbl</code> (thousand) and <code>MMbbl</code> (million) are defined explicitly and flagged, since SI “M” means million.</li>
      </ul>
      <h2>How far to trust a result</h2>
      <ul>
        <li><strong>Checked by the program:</strong> every equation is checked for dimensional consistency when it is loaded, inputs are converted exactly, and every calculation ships with a worked example that is solved in the test suite.</li>
        <li><strong>Checked by independent code, not by independent people:</strong> many library formulas are also tested against a second implementation (numerical integration, root finding, a library routine, or a hand calculation). The author wrote both, so this catches coding and unit slips, not a formula remembered wrongly.</li>
        <li><strong>References:</strong> journal articles and books were looked up in public catalogues; a few were not and show a “not verified” note on the calculation. Check a reference yourself before relying on a formula for something that matters.</li>
        <li><strong>Your own equations</strong> are marked <em>custom</em>: their units are checked, but nobody has reviewed them.</li>
      </ul>
      <h2>LiveCalc</h2>
      <p>A scratchpad calculator with units. Each line is evaluated as you type (a preview shows it as Markdown with maths) and Enter adds it to the history, which keeps the
      last 30 entries; variables carry from one entry to the next. Examples: <code>5 m + 30 cm</code>, <code>120 km/h to m/s</code>, <code>m = 5 kg</code> then <code>F = m*a</code>,
      <code>f(x) = 3*x^2 - 2</code>, <code>plot sin(x), cos(x) from 0 to 2*pi</code>. “Show steps” adds the working to every calculation. Mismatched units are refused. Select an equation
      (in the input box or in the history) and press “Send selection to My equations” to start a new equation with the units taken from your variables. Anything that is not a
      calculation is Markdown.</p>
      <h2>System Design</h2>
      <p>Switch the Calculations tab from “Single calculation” to “System” to build a multi-step model on a canvas: click or drag calculations from the list into it, click a block to decide which variables are inputs, outputs or constants, and drag from an output
      port to an input port. Ports are coloured by physical type and a wire is refused when the types differ (pressure cannot feed a force input), when it would create a loop,
      or when the input already has a wire. The system is evaluated in dependency order and values are converted between units on every wire. “Export” downloads (or “Copy” copies) the full system of equations as LaTeX, Markdown, printable HTML or a SymPy script, symbolic, numeric or both.</p>
      <h2>My equations</h2>
      <p>Define your own calculations in the “My equations” tab: name, variables with units, and one or more equations such as <code>F = k*x</code>. They are checked for dimensional
      consistency, can be solved for any variable like the built-in ones, appear in search and in System Design, and are marked <em>custom</em>. Equations are stored as plain JSON
      files (in <code>~/.sliderule/calculations</code> for the installed app, or in this browser's storage for the web version); “Export” and “Import” share them as files, and a saved
      System Design carries the custom equations it uses. Equation text is checked against a small whitelist of maths before anything is evaluated, so a file from someone else cannot run code.</p>
      <h2>Derivatives and integrals</h2>
      <p>Equations may use <code>diff(f, t)</code> (or <code>diff(f, t, 2)</code>) and definite integrals <code>integrate(f, (x, a, b))</code>. They are dimension-checked as written (an integral gains the
      units of its variable, a derivative divides by them), evaluated symbolically, and the worked steps show the equation as written and then evaluated. Any quantity, including an integration limit, can still
      be solved for. Integrals without a closed form are integrated numerically; differential equations are described below.
      A series is written <code>summation(term, (n, 1, 50))</code> (whole-number limits, up to 500 terms) and added term by term, which is how the textbook Fourier-series solutions of the heat, wave and Laplace equations are built.</p>
      <h2>Differential equations</h2>
      <p>Calculations can contain initial-value problems such as <code>diff(T, t) = -k*(T - Ta)</code>. When SymPy finds a closed-form solution you can still solve for any quantity (the time to reach a temperature, the rate
      constant…); otherwise the equation is integrated numerically (adaptive RK45, switching to an implicit method when stiff), which is evaluated forward directly and inverted by root-finding when you solve for something else. Results come with a plot of the solution, a CSV download and a table at
      times you choose. Add your own under My equations → Differential equations. Integrals that have no closed form are integrated numerically too.</p>
      <p>Boundary-value problems (conditions at the two ends of an interval, as for beams, fins and pipe profiles) are solved in closed form when SymPy can, otherwise numerically by multiple shooting. The independent variable is then
      the position you want the answer at, and the plot covers the whole interval. A boundary-value problem can also contain unknown parameters: an eigenvalue (buckling load, natural frequency, energy level; you supply a
      normalisation and a starting guess that selects the mode) or a constant fitted by extra conditions (the tension that gives a cable a stated length).</p>
      <p>Time-dependent partial differential equations in one space dimension (heat, waves, advection–diffusion) are solved numerically by the method of lines. You enter the position and the time; the result comes with an estimate of
      the discretisation error, a profile along the space axis at several times and the history at your position. Steady problems on a rectangle (Laplace, Poisson, conduction with sources, nonlinear variants) are solved
      on a grid with Newton's method and shown as a colour map with profiles through your point.</p>
      <h2>Time limit</h2>
      <p>Calculations that run too long are stopped after a time limit (10 seconds by default). Change it, or switch it off, under ⚙ Settings. With the limit off, a calculation that never finishes keeps the engine busy
      until it ends: the page may look frozen until you reload it, and the installed app keeps using a processor core until you quit it. The limit only decides when to give up; it never changes a result.</p>
      <h2>Solving</h2>
      <p>Tick “find” on any quantity and the equations are rearranged symbolically (SymPy) and evaluated. When a calculation has several
      equations they are ordered automatically so that each one has exactly one unknown. Equations that share several unknowns (solving the Colebrook and
      Darcy equations together for velocity, node voltages, a pipe junction) are solved simultaneously: exactly when they are linear, by Newton's method otherwise, with a note when there is more than one solution.</p>
      <h2>Limits</h2>
      <p>Results are only as good as the stated assumptions, which are listed under each calculation. This tool is an aid for learning and
      for checking work — it is not a substitute for applicable codes, standards, or professional engineering judgement.</p>
    </div>`;
}

boot();
