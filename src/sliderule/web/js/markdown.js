// A small Markdown renderer for LiveCalc notes. It builds DOM nodes (never innerHTML), so typed text cannot inject markup.
// Blocks: headings, paragraphs, block quotes, bullet and numbered lists, code fences, rules.
// Inline: `code`, **bold**, *italic*, _italic_, ~~strike~~, [text](https://link) and $LaTeX$ (KaTeX).
import { h, math } from "./dom.js";

const SAFE_URL = /^(https?:\/\/|mailto:)/i;

const RULES = [
  { re: /`([^`\n]+)`/, make: (m) => h("code", {}, m[1]) },
  { re: /\$([^$\n]+)\$/, make: (m) => math(m[1]) },
  { re: /\*\*([^*\n]+)\*\*/, make: (m) => h("strong", {}, ...inline(m[1])) },
  { re: /~~([^~\n]+)~~/, make: (m) => h("del", {}, ...inline(m[1])) },
  { re: /\*([^*\s][^*\n]*)\*/, make: (m) => h("em", {}, ...inline(m[1])) },
  { re: /(?<![\w])_([^_\n]+)_(?![\w])/, make: (m) => h("em", {}, ...inline(m[1])) },
  { re: /\[([^\]\n]+)\]\(([^)\s]+)\)/, make: (m) => (SAFE_URL.test(m[2]) ? h("a", { href: m[2], target: "_blank", rel: "noopener noreferrer" }, m[1]) : document.createTextNode(m[0])) },
];

/** Inline markup of one line of text, as an array of nodes. */
export function inline(text) {
  const out = [];
  let rest = text;
  while (rest) {
    let best = null;
    for (const r of RULES) {
      const m = r.re.exec(rest);
      if (m && (!best || m.index < best.m.index)) best = { r, m };
    }
    if (!best) break;
    if (best.m.index) out.push(document.createTextNode(rest.slice(0, best.m.index)));
    out.push(best.r.make(best.m));
    rest = rest.slice(best.m.index + best.m[0].length);
  }
  if (rest) out.push(document.createTextNode(rest));
  return out;
}

const BULLET = /^\s*[-*+]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;

export function renderMarkdown(src) {
  const root = h("div", { class: "md" });
  const lines = String(src).replace(/\r\n/g, "\n").split("\n");
  let para = [];
  const flush = () => {
    if (!para.length) return;
    root.append(h("p", {}, para.flatMap((l, k) => (k ? [h("br"), ...inline(l)] : inline(l)))));
    para = [];
  };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    let m;
    if (/^\s*```/.test(line)) {
      flush();
      const code = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i++]);
      i++;
      root.append(h("pre", {}, h("code", {}, code.join("\n"))));
    } else if (!line.trim()) {
      flush();
      i++;
    } else if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      flush();
      root.append(h(`h${m[1].length}`, {}, ...inline(m[2])));
      i++;
    } else if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      flush();
      root.append(h("hr"));
      i++;
    } else if (/^\s*>/.test(line)) {
      flush();
      const q = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) q.push(lines[i++].replace(/^\s*>\s?/, ""));
      root.append(h("blockquote", {}, renderMarkdown(q.join("\n"))));
    } else if (BULLET.test(line) || NUMBERED.test(line)) {
      flush();
      const re = NUMBERED.test(line) ? NUMBERED : BULLET;
      const items = [];
      while (i < lines.length && re.test(lines[i])) items.push(lines[i++].replace(re, ""));
      root.append(h(re === NUMBERED ? "ol" : "ul", {}, items.map((t) => h("li", {}, ...inline(t)))));
    } else {
      para.push(line.trim());
      i++;
    }
  }
  flush();
  return root;
}
