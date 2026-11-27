// KDX Wildcard Studio - Template builder: a template as a row of bubbles you drag, drop and click together.
//
// The canvas shows the template line as it reads, left to right: text bubbles (type anything), pool bubbles
// (__folder/file__) and group boxes (one of {a|b}, sometimes {a|}, pick several {1-2$$ $$a|b}) whose option lanes
// take bubbles too. The palette on the left offers pools, ready sentences and shapes; drag them in or click ＋.
// The server owns the syntax: it turns a line into bubbles, writes bubbles back as a line, checks and expands it.
// No external libraries; no polling (the preview is asked for after a change, debounced).
import { ensureTheme } from "./theme.mjs?v=0.7.14";
import { call, getSnap, refresh, toast } from "./client.mjs?v=0.7.14";
import { askConfirm, askText } from "./dialog.mjs?v=0.7.14";
import { restoreText, useTextOnNode } from "./nodewrite.mjs?v=0.7.14";

let win = null;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const newSeed = () => Math.floor(Math.random() * 2 ** 31);
const dirOf = (k) => (k.includes("/") ? k.slice(0, k.lastIndexOf("/")) : "(top)");
const baseOf = (k) => k.slice(k.lastIndexOf("/") + 1);
const clone = (x) => JSON.parse(JSON.stringify(x));
const SHAPES = [
  ["text", "✎ Text", "Your own words, written straight into the template", () => ({ t: "text", v: "text" })],
  ["one", "⑂ One of", "Each image picks one option: {a|b}", () => ({ t: "choice", count: null, sep: null, opts: [{ w: null, items: [{ t: "text", v: "a" }] }, { w: null, items: [{ t: "text", v: "b" }] }] })],
  ["some", "◐ Sometimes", "In about half the images: {a|}", () => ({ t: "choice", count: null, sep: null, opts: [{ w: null, items: [{ t: "text", v: "text" }] }, { w: null, items: [] }] })],
  ["multi", "⁂ Pick several", "Each image picks 1-2 different options, joined by a space: {1-2$$ $$a|b|c}", () => ({ t: "choice", count: "1-2", sep: " ", opts: [{ w: null, items: [{ t: "text", v: "a." }] }, { w: null, items: [{ t: "text", v: "b." }] }, { w: null, items: [{ t: "text", v: "c." }] }] })],
];

// ------------------------------------------------------------------ tree helpers
// A path is an array: [node, option, node, option, …]. Even length = a lane (root = []), odd = a node.
const key = (p) => p.join(".");
const unkey = (s) => (s === "" || s == null ? [] : String(s).split(".").map(Number));
function laneAt(root, lp) {
  let lane = root;
  for (let i = 0; i < lp.length; i += 2) lane = lane[lp[i]].opts[lp[i + 1]].items;
  return lane;
}
const nodeAt = (root, p) => laneAt(root, p.slice(0, -1))[p[p.length - 1]];
function walk(lane, fn) {
  for (let i = 0; i < lane.length; i++) {
    if (fn(lane, i) === false) return false;
    const n = lane[i];
    if (n.t === "choice") for (const o of n.opts) if (walk(o.items, fn) === false) return false;
  }
  return true;
}
/** Drop groups with one empty option ({}): what is left when their only bubble was moved or removed. */
function prune(lane) {
  for (let i = lane.length - 1; i >= 0; i--) {
    const n = lane[i];
    if (n.t !== "choice") continue;
    n.opts.forEach((o) => prune(o.items));
    if (n.opts.length === 1 && !n.opts[0].items.length) lane.splice(i, 1);
  }
}
function removeRef(root, ref) { walk(root, (lane, i) => { if (lane[i] === ref) { lane.splice(i, 1); return false; } return true; }); }
function replaceRef(root, ref, items) { walk(root, (lane, i) => { if (lane[i] === ref) { lane.splice(i, 1, ...items); return false; } return true; }); }
function pathOf(root, ref) {
  let found = null;
  const rec = (lane, base) => lane.some((n, i) => {
    if (n === ref) { found = [...base, i]; return true; }
    return n.t === "choice" && n.opts.some((o, oi) => rec(o.items, [...base, i, oi]));
  });
  rec(root, []);
  return found;
}
const kindOf = (n) => (n.count != null ? "multi" : n.opts.length === 1 && !n.opts[0].w ? "solo" : n.opts.length === 2 && n.opts.some((o) => !o.items.length) ? "some" : "one");
function summary(items, max = 60) {
  const s = items.map((n) => (n.t === "text" || n.t === "raw" ? n.v : n.t === "pool" ? `‹${baseOf(n.name)}›` : `{${n.opts.map((o) => summary(o.items, 20)).join("|")}}`)).join("");
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export function closeBuilder() { win?.close(); }

/** Open the builder; `opts.text` (a template line) starts it with that line, `opts.name` with that name. An open
 * builder takes the line over (asking first when it has unsaved changes). */
export async function openBuilder(opts = {}) {
  ensureTheme();
  if (opts.text != null && win?.loadText) { win.loadText(opts.text, opts.name || ""); return; }
  closeBuilder();
  const el = document.createElement("div");
  el.className = "kdx-root kdx-gal kdx-bb";
  el.innerHTML = `<div class="kdx-gal-head"><span class="kdx-gal-title">🧱 Template builder</span><span class="kdx-muted">Loading…</span>
    <span class="kdx-sp"></span><button class="kdx-btn" data-b="close" title="Close (Esc)">✕</button></div>`;
  document.body.appendChild(el);
  const cat = await call("GET", "/kdx_console/builder");
  if (!cat.ok) el.querySelector(".kdx-muted").textContent = cat.error || "could not load";
  const v = {
    name: "", nodes: cat.ok ? clone(cat.starters.woman) : [], loaded: "", dirty: false, category: "", sel: null,
    pool: null, tab: "pools", sex: "woman", filter: "", openDirs: new Set(), seed: newSeed(), preview: null,
    textView: false, past: [], future: [], note: "",
  };
  let drag = null; // {src: "palette", el} | {src: "canvas", ref, el}
  let editSnap = false;

  // ------------------------------------------------------------------ history
  function snap() {
    v.past.push(JSON.stringify(v.nodes));
    if (v.past.length > 100) v.past.shift();
    v.future = [];
    v.dirty = true;
  }
  function undo(redo = false) {
    const from = redo ? v.future : v.past;
    const to = redo ? v.past : v.future;
    if (!from.length) return;
    to.push(JSON.stringify(v.nodes));
    v.nodes = JSON.parse(from.pop());
    v.sel = null;
    v.dirty = true;
    paintCanvas(); paintSide(); schedule();
  }

  // ------------------------------------------------------------------ rendering
  function headHtml() {
    const cats = getSnap()?.config?.categories || [];
    return `<span class="kdx-gal-title">🧱 Template builder</span>
      <label class="kdx-row" style="gap:3px">Name <input class="kdx-sel" data-b="name" type="text" spellcheck="false" autocomplete="off"
        placeholder="portrait_woman" value="${esc(v.name)}" style="width:160px" title="File name: templates/<name>.txt (a-z, 0-9, _)"></label>
      <select class="kdx-sel" data-b="open" title="Open an existing template as bubbles">
        <option value="">Open…</option>${cat.templates.map((n) => `<option value="${esc(n)}" ${n === v.loaded ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>
      <select class="kdx-sel" data-b="new" title="Start a new template"><option value="">New…</option>
        <option value="woman">woman (all sentences)</option><option value="man">man (all sentences)</option>
        <option value="none">no person (all sentences)</option><option value="empty">empty</option></select>
      <span class="kdx-sp"></span>
      <label class="kdx-row" style="gap:3px" title="After saving, add the template to this category of the panel">Add to
        <select class="kdx-sel" data-b="category"><option value="">no category</option>
        ${cats.map((c) => `<option value="${esc(c.key)}" ${c.key === v.category ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
      ${saveButtons()}
      <button class="kdx-btn" data-b="close" title="Close (Esc)">✕</button>`;
  }

  // palette ----------------------------------------------------------
  function paletteHtml() {
    const tabs = [["pools", "Pools"], ["sentences", "Sentences"], ["shapes", "Text & groups"]];
    let head = "";
    let list = "";
    if (v.tab === "pools") {
      const q = v.filter.trim().toLowerCase();
      const dirs = new Map();
      for (const p of cat.pools.filter((p) => !q || p.key.includes(q) || (p.desc || "").toLowerCase().includes(q))) {
        const d = dirOf(p.key);
        if (!dirs.has(d)) dirs.set(d, []);
        dirs.get(d).push(p);
      }
      const tree = [...dirs.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([d, ps]) => `<details ${q || v.openDirs.has(d) ? "open" : ""} data-dir="${esc(d)}">
        <summary>${esc(d)} <span class="kdx-muted">${ps.length}</span>${d.startsWith("packs/") || d === "(top)" ? "" : ` <button class="kdx-go kdx-ico kdx-bb-dirnew" data-b="pnew" data-dir="${esc(d)}" title="New pool in ${esc(d)}/">＋</button>`}</summary>${ps.map((p) => `<div class="kdx-bb-pal kdx-bb-palpool ${v.pool?.key === p.key ? "sel" : ""}"
          draggable="true" data-pal="pool" data-key="${esc(p.key)}" title="${esc(`${p.key} · ${p.count} values${p.desc ? `\n${p.desc}` : ""}\nDrag into the template, or click to see its values`)}">
          <span>${esc(baseOf(p.key))}</span><span class="kdx-muted">${p.count}${p.templates.length ? ` · ${p.templates.length} tpl` : ""}</span>
          ${p.key.startsWith("packs/") ? "" : `<button class="kdx-go kdx-ico" data-b="pedit" data-key="${esc(p.key)}" title="Edit this pool: values, weights, order, retire">✎</button>`}
          <button class="kdx-go kdx-ico" data-b="append" data-pal="pool" data-key="${esc(p.key)}" title="Add after the selected bubble (or at the end)">＋</button></div>`).join("")}</details>`).join("");
      head = `<input class="kdx-sel" type="search" data-b="filter" placeholder="search pools…" value="${esc(v.filter)}">
        <div class="kdx-row"><span class="kdx-muted">values · tpl = templates using it</span><span class="kdx-sp"></span>
          <button class="kdx-btn" data-b="pnew" title="Create a new pool in a folder of your library">＋ New pool</button></div>`;
      list = `<div class="kdx-bb-tree">${tree || `<p class="kdx-muted">No pool matches.</p>`}</div>`;
    } else if (v.tab === "sentences") {
      head = `<span class="kdx-seg">${[["woman", "Woman"], ["man", "Man"], ["none", "No person"]].map(([k, t]) => `<button class="${v.sex === k ? "on" : ""}" data-b="sex" data-m="${k}">${t}</button>`).join("")}</span>
        <div class="kdx-muted">Whole sentences with the library's default pools, written by its rules (expression and mood together, scene bundles with their place and shot).</div>`;
      list = `
        ${cat.snippets[v.sex].map((s, i) => `<div class="kdx-bb-pal kdx-bb-palsn" draggable="true" data-pal="snippet" data-i="${i}" title="Drag into the template, or ＋ to add">
          <div class="kdx-row"><b>${esc(s.label)}</b><span class="kdx-sp"></span><button class="kdx-go kdx-ico" data-b="append" data-pal="snippet" data-i="${i}" title="Add after the selected bubble (or at the end)">＋</button></div>
          <div class="kdx-muted kdx-bb-sum">${esc(summary(s.nodes, 140))}</div></div>`).join("")}`;
    } else {
      head = `<div class="kdx-muted">Drag into the template or into a group's option, or ＋ to add.</div>`;
      list = `
        ${SHAPES.map(([k, label, title]) => `<div class="kdx-bb-pal kdx-bb-palshape" draggable="true" data-pal="shape" data-k="${k}" title="${esc(title)}">
          <b>${esc(label)}</b><span class="kdx-muted">${esc(title)}</span><button class="kdx-go kdx-ico" data-b="append" data-pal="shape" data-k="${k}" title="Add">＋</button></div>`).join("")}`;
    }
    // The tabs and the head stay put; only the list below scrolls (a long list used to squeeze the tabs to nothing).
    return `<div class="kdx-bb-palhead"><span class="kdx-seg kdx-bb-tabs">${tabs.map(([k, t]) => `<button class="${v.tab === k ? "on" : ""}" data-b="tab" data-m="${k}">${t}</button>`).join("")}</span>${head}</div>
      <div class="kdx-bb-pallist">${list}</div>`;
  }

  // canvas -------------------------------------------------------------
  function nodeHtml(n, p) {
    const k = key(p);
    const sel = v.sel === k ? " sel" : "";
    const x = `<button class="kdx-bb-x" data-b="del" data-path="${k}" title="Remove" tabindex="-1">✕</button>`;
    if (n.t === "text" || n.t === "raw") {
      return `<span class="kdx-bb-n kdx-bb-${n.t}${sel}" data-path="${k}" title="${n.t === "raw" ? "Kept exactly as written (an unbalanced brace)" : "Text: click to type"}"><span class="kdx-bb-grip" draggable="true" title="Drag to move">⠿</span><span
        class="kdx-bb-tv" contenteditable="plaintext-only" spellcheck="false" data-edit="${k}">${esc(n.v)}</span>${x}</span>`;
    }
    if (n.t === "pool") {
      const info = cat.pools.find((q) => q.key === n.name);
      const title = info ? `${n.name} · ${info.count} values${info.desc ? `\n${info.desc}` : ""}` : `${n.name}: not a pool of the library`;
      return `<span class="kdx-bb-n kdx-bb-pool${sel}${info ? "" : " bad"}" draggable="true" data-path="${k}" tabindex="0" title="${esc(title)}"><span class="kdx-bb-dir">${esc(n.name.includes("/") ? `${dirOf(n.name)}/` : "")}</span><b>${esc(baseOf(n.name))}</b>${x}</span>`;
    }
    const kind = kindOf(n);
    if (kind === "solo") { // {x}: braces around one option, as the library writes every slot; shown light
      return `<span class="kdx-bb-n kdx-bb-solo${sel}" draggable="true" data-path="${k}" tabindex="0" title="A group with one option: add options in the panel on the right">${laneHtml(n.opts[0].items, [...p, 0], "empty")}</span>`;
    }
    const label = kind === "multi" ? `⁂ pick ${esc(n.count || "1")}` : kind === "some" ? "◐ sometimes" : "⑂ one of";
    if (n._c) {
      return `<span class="kdx-bb-n kdx-bb-choice kdx-bb-${kind}${sel}" draggable="true" data-path="${k}" tabindex="0"><span class="kdx-bb-ch">
        <button class="kdx-bb-fold" data-b="fold" data-path="${k}" title="Open the group">▸</button>${label} <span class="kdx-muted">${n.opts.length} options · ${esc(summary([n], 50))}</span>${x}</span></span>`;
    }
    const opts = n.opts.map((o, oi) => `<div class="kdx-bb-opt"><input class="kdx-bb-w" type="text" inputmode="decimal" data-b="w" data-path="${k}" data-o="${oi}"
        value="${esc(o.w ?? "")}" placeholder="1" title="Weight: how often this option is picked, relative to the others">
        ${laneHtml(o.items, [...p, oi], o.items.length ? "" : (kind === "some" ? "nothing" : "empty"))}
        <button class="kdx-bb-ox" data-b="optdel" data-path="${k}" data-o="${oi}" title="Remove this option" ${n.opts.length < 2 ? "disabled" : ""}>✕</button></div>`).join("");
    return `<span class="kdx-bb-n kdx-bb-choice kdx-bb-${kind}${sel}" draggable="true" data-path="${k}" tabindex="0"><span class="kdx-bb-ch">
      <button class="kdx-bb-fold" data-b="fold" data-path="${k}" title="Fold the group">▾</button>${label}${n.sep != null && kind === "multi" ? ` <span class="kdx-muted">joined by “${esc(n.sep)}”</span>` : ""}<span class="kdx-sp"></span>${x}</span>
      ${opts}<button class="kdx-bb-add" data-b="optadd" data-path="${k}" title="Add an option">＋ option</button></span>`;
  }
  function laneHtml(items, lp, empty = "") {
    return `<div class="kdx-bb-lane" data-lane="${key(lp)}">${items.map((n, i) => nodeHtml(n, [...lp, i])).join("")}${!items.length && empty ? `<span class="kdx-bb-empty">${empty}</span>` : ""}</div>`;
  }
  function canvasHtml() {
    const tools = `<div class="kdx-row kdx-bb-tools"><b>Template</b><span class="kdx-muted">drag bubbles to move them · click text to type · Del removes the selected bubble</span><span class="kdx-sp"></span>
      <button class="kdx-btn" data-b="undo" title="Undo (Ctrl+Z)" ${v.past.length ? "" : "disabled"}>↶</button>
      <button class="kdx-btn" data-b="redo" title="Redo (Ctrl+Y)" ${v.future.length ? "" : "disabled"}>↷</button>
      <button class="kdx-btn ${v.textView ? "kdx-primary" : ""}" data-b="textview" title="Show the line as text: edit or paste it, then Apply">Text</button></div>`;
    if (v.textView) {
      return `${tools}<textarea class="kdx-field kdx-bb-ta" data-b="text" spellcheck="false" rows="12">${esc(v.preview?.text ?? "")}</textarea>
        <div class="kdx-row"><span class="kdx-sp"></span><button class="kdx-btn" data-b="textview">Cancel</button><button class="kdx-btn kdx-primary" data-b="apply" title="Turn the text into bubbles">Apply</button></div>`;
    }
    return `${tools}${v.note ? `<div class="kdx-warn">${esc(v.note)}</div>` : ""}<div class="kdx-bb-canvas">${laneHtml(v.nodes, [], "Drag pools, sentences or text here")}</div>`;
  }

  // side: inspector + preview --------------------------------------------
  function inspectorHtml() {
    const p = v.sel != null ? unkey(v.sel) : null;
    const n = p ? nodeAt(v.nodes, p) : null;
    const acts = n ? `<div class="kdx-row" style="flex-wrap:wrap;gap:4px">
        <button class="kdx-btn" data-b="move" data-d="-1" title="Move left (Alt+←)">←</button><button class="kdx-btn" data-b="move" data-d="1" title="Move right (Alt+→)">→</button>
        <button class="kdx-btn" data-b="wrap" data-m="some" title="Put it in a “sometimes” group {…|}">◐ Sometimes</button>
        <button class="kdx-btn" data-b="wrap" data-m="one" title="Put it in a “one of” group as the first option">⑂ One of</button>
        <button class="kdx-btn" data-b="dup" title="Duplicate">⧉</button><button class="kdx-btn" data-b="delsel" title="Remove (Del)">✕</button></div>` : "";
    let body = "";
    if (n?.t === "choice") {
      const kind = kindOf(n);
      body = `<div class="kdx-row"><span class="kdx-seg"><button class="${kind !== "multi" ? "on" : ""}" data-b="kind" data-m="one" title="Each image picks one option">One of</button><button
        class="${kind === "multi" ? "on" : ""}" data-b="kind" data-m="multi" title="Each image picks several different options">Pick several</button></span></div>
        ${kind === "multi" ? `<div class="kdx-row"><label class="kdx-row" style="gap:3px" title="How many: 2, or a range 1-3">how many <input class="kdx-rep" data-b="count" value="${esc(n.count)}" style="width:46px"></label>
          <label class="kdx-row" style="gap:3px" title="Text between the picked options (empty = the default “, ”)">joined by <input class="kdx-rep" data-b="sep" value="${esc(n.sep ?? "")}" placeholder=", " style="width:46px"></label></div>` : ""}
        <div class="kdx-row"><button class="kdx-btn" data-b="optadd" data-path="${v.sel}" title="Add an option: each image then picks one of them">＋ option</button></div>
        <div class="kdx-muted">An option with nothing in it makes the group “sometimes”. Weights: an option with 3 comes three times as often as one with 1.</div>`;
    } else if (n?.t === "pool" && v.pool?.key !== n.name) {
      body = `<p class="kdx-muted">Loading ${esc(n.name)}…</p>`;
    } else if (n?.t === "text") body = `<div class="kdx-muted">Text goes into the template as you type it. Mind the spaces at the ends: they are part of the text.</div>`;
    else if (n?.t === "raw") body = `<div class="kdx-warn">This piece is kept exactly as written: it has a brace without its partner.</div>`;
    const pool = v.pool && (!n || (n.t === "pool" && n.name === v.pool.key)) ? poolHtml(v.pool) : "";
    if (!n && !pool) return `<div class="kdx-card kdx-muted">Click a bubble to see it here; click a pool in the palette to see its values.</div>`;
    return `<div class="kdx-card kdx-bb-insp">${n ? `<div class="kdx-row"><b>${n.t === "choice" ? "Group" : n.t === "pool" ? "Pool" : "Text"}</b></div>${acts}${body}` : ""}${pool}</div>`;
  }
  function poolHtml(p) {
    return `<div class="kdx-row"><b>${esc(p.key)}</b><span class="kdx-muted">${p.count} values</span></div>
      ${p.head.length ? `<div class="kdx-muted kdx-bb-head">${p.head.map(esc).join("<br>")}</div>` : ""}
      <div class="kdx-muted">Used by ${p.templates.length ? p.templates.map(esc).join(", ") : "no template"}${p.hidden_templates ? ` (+${p.hidden_templates} NSFW hidden)` : ""}${p.pools.length ? `; inside ${p.pools.map(esc).join(", ")}` : ""}</div>
      <ol class="kdx-bb-vals">${p.values.slice(0, 400).map((x) => `<li>${x.w !== 1 ? `<span class="kdx-muted">${x.w}::</span>` : ""}${esc(x.value)}</li>`).join("")}</ol>`;
  }
  function previewHtml() {
    const pv = v.preview;
    if (!pv) return `<p class="kdx-muted">Composing…</p>`;
    if (pv.error) return `<p class="kdx-err">${esc(pv.error)}</p>`;
    const warns = pv.warnings || [];
    return `<div class="kdx-row"><b>Checks</b>${warns.length ? "" : ` <span class="kdx-ok">✅ all rules met</span>`}</div>
      ${warns.map((w) => `<div class="${w.level === "error" ? "kdx-err" : "kdx-warn"}">${w.level === "error" ? "⛔" : "⚠"} ${esc(w.msg)}</div>`).join("")}
      ${v.undo ? `<div class="kdx-row"><button class="kdx-btn" data-b="restore" title="Put back the text that ${esc(v.undo.label)} held before Use on node">↶ Restore previous text of ${esc(v.undo.label)}</button></div>` : ""}
      <div class="kdx-row"><b>3 random images</b><span class="kdx-sp"></span><button class="kdx-btn" data-b="again" title="Expand again with new random seeds">⟳ Again</button></div>
      ${(pv.samples || []).map((s, i) => `<div class="kdx-bb-sample"><div class="kdx-row kdx-muted">seed ${s.seed}${s.missing?.length ? ` · <span class="kdx-err">unknown: ${esc(s.missing.join(", "))}</span>` : ""}
        <span class="kdx-sp"></span><button class="kdx-btn" data-b="keep" data-i="${i}" title="Keep parts of this sample (pose, clothing, place …) and let the rest vary">🔒 Keep parts</button></div>${esc(s.text)}</div>`).join("")}
      <details class="kdx-bb-line"><summary>Template line</summary><div class="kdx-row"><span class="kdx-sp"></span><button class="kdx-btn" data-b="copy" title="Copy the line">Copy</button></div>
        <div class="kdx-bb-text">${esc(pv.text)}</div></details>`;
  }

  function render() {
    if (!cat.ok) return;
    el.innerHTML = `<div class="kdx-gal-head">${headHtml()}</div><div class="kdx-bb-body">
      <div class="kdx-bb-col kdx-bb-palette" data-col="palette">${paletteHtml()}</div>
      <div class="kdx-bb-col" data-col="canvas">${canvasHtml()}</div>
      <div class="kdx-bb-col" data-col="side"><div data-col="insp">${inspectorHtml()}</div><div data-col="preview">${previewHtml()}</div></div></div>`;
  }
  const paint = (col, html) => {
    const c = el.querySelector(`[data-col="${col}"]`);
    if (!c) return;
    const sc = c.closest(".kdx-bb-col") || c;
    const top = sc.scrollTop;
    c.innerHTML = html();
    sc.scrollTop = top;
  };
  const paintCanvas = () => paint("canvas", canvasHtml);
  const paintSide = () => paint("insp", inspectorHtml);
  const paintPreview = () => {
    const open = el.querySelector(".kdx-bb-line")?.open;
    paint("preview", previewHtml);
    if (open) el.querySelector(".kdx-bb-line").open = true;
  };
  function paintPalette() {
    const c = el.querySelector('[data-col="palette"]');
    const f = c?.querySelector('[data-b="filter"]');
    if (f && document.activeElement === f) { // keep the search field and its caret while typing
      const tmp = document.createElement("div");
      tmp.innerHTML = paletteHtml();
      c.querySelector(".kdx-bb-tree").replaceWith(tmp.querySelector(".kdx-bb-tree"));
      return;
    }
    const top = c?.querySelector(".kdx-bb-pallist")?.scrollTop || 0;
    const tab = c?.dataset.tab;
    c.innerHTML = paletteHtml();
    c.dataset.tab = v.tab;
    if (tab === v.tab) c.querySelector(".kdx-bb-pallist").scrollTop = top; // another tab starts at the top
  }
  const paintHead = () => { const h = el.querySelector(".kdx-gal-head"); if (h && !h.contains(document.activeElement)) h.innerHTML = headHtml(); };

  // ------------------------------------------------------------------ server calls
  let timer = null;
  let ticket = 0;
  function schedule(delay = 300) { clearTimeout(timer); timer = setTimeout(runPreview, delay); }
  async function runPreview() {
    const my = ++ticket;
    const r = await call("POST", "/kdx_console/builder/preview", { nodes: v.nodes, name: v.name, count: 3, seed: v.seed });
    if (my !== ticket || !win) return;
    v.preview = r.ok ? r : { error: r.error || "could not compose" };
    paintPreview();
  }
  async function showPool(name) {
    if (v.pool?.key === name) return;
    const r = await call("GET", `/kdx_console/builder/pool?key=${encodeURIComponent(name)}`);
    if (!r.ok) { v.pool = null; paintSide(); return; }
    v.pool = r.pool;
    paintSide();
  }
  const changed = () => { paintCanvas(); paintSide(); schedule(); };

  // ------------------------------------------------------------------ editing
  function paletteNodes(t) {
    if (t.dataset.pal === "pool") return [{ t: "pool", name: t.dataset.key }];
    if (t.dataset.pal === "snippet") return clone(cat.snippets[v.sex][Number(t.dataset.i)].nodes);
    return [SHAPES.find((s) => s[0] === t.dataset.k)[3]()];
  }
  /** Insert into lane `lp` at `index`; a sentence added after text that ends without a space gets one. */
  function insert(lp, index, items, sentence = false) {
    const lane = laneAt(v.nodes, lp);
    const prev = lane[index - 1];
    if (sentence && prev && !(prev.t === "text" && /\s$/.test(prev.v))) items = [{ t: "text", v: " " }, ...items];
    lane.splice(index, 0, ...items);
    return items;
  }
  function appendHere(items, sentence) {
    snap();
    const p = selected(true)?.p || null;
    const lp = p ? p.slice(0, -1) : [];
    const idx = p ? p[p.length - 1] + 1 : v.nodes.length;
    const added = insert(lp, idx, items, sentence);
    v.sel = key(pathOf(v.nodes, added[added.length - 1]));
    changed();
  }
  /** The selection, lifted out of plain braces {x} that hold only it: wrapping or moving x means the braces. */
  function selected(lift = false) {
    let p = v.sel != null ? unkey(v.sel) : null;
    if (!p) return null;
    while (lift && p.length >= 3) {
      const g = nodeAt(v.nodes, p.slice(0, -2));
      if (kindOf(g) !== "solo" || g.opts[0].items.length !== 1) break;
      p = p.slice(0, -2);
    }
    return { p, n: nodeAt(v.nodes, p) };
  }
  function select(k) {
    v.sel = k;
    const n = k != null ? nodeAt(v.nodes, unkey(k)) : null;
    el.querySelectorAll(".kdx-bb-n.sel").forEach((x) => x.classList.remove("sel"));
    if (k != null) el.querySelector(`.kdx-bb-n[data-path="${k}"]`)?.classList.add("sel");
    if (n?.t === "pool") showPool(n.name);
    paintSide();
  }
  function removeSel() {
    const s = selected();
    if (!s) return;
    snap();
    laneAt(v.nodes, s.p.slice(0, -1)).splice(s.p[s.p.length - 1], 1);
    prune(v.nodes);
    v.sel = null;
    changed();
  }
  function moveSel(d) {
    const s = selected(true);
    if (!s) return;
    const lane = laneAt(v.nodes, s.p.slice(0, -1));
    const i = s.p[s.p.length - 1];
    const j = i + d;
    if (j < 0 || j >= lane.length) return;
    snap();
    [lane[i], lane[j]] = [lane[j], lane[i]];
    v.sel = key([...s.p.slice(0, -1), j]);
    changed();
  }

  // ------------------------------------------------------------------ drag and drop
  let caret = null;
  function dropTarget(e) {
    const laneEl = e.target.closest?.("[data-lane]") || el.querySelector('.kdx-bb-canvas > [data-lane=""]');
    if (!laneEl) return null;
    const kids = [...laneEl.children].filter((c) => c.classList.contains("kdx-bb-n"));
    let index = kids.length;
    for (let i = 0; i < kids.length; i++) {
      const r = kids[i].getBoundingClientRect();
      if (e.clientY < r.top || (e.clientY <= r.bottom && e.clientX < r.left + r.width / 2)) { index = i; break; }
    }
    return { laneEl, lp: unkey(laneEl.dataset.lane), index, kids };
  }
  function showCaret(t) {
    if (!caret) { caret = document.createElement("span"); caret.className = "kdx-bb-caret"; }
    const ref = t.kids[t.index] || null;
    if (caret.parentNode !== t.laneEl || caret.nextSibling !== ref) t.laneEl.insertBefore(caret, ref);
  }
  const hideCaret = () => { caret?.remove(); };

  el.addEventListener("dragstart", (e) => {
    const pal = e.target.closest?.("[data-pal]");
    const n = e.target.closest?.(".kdx-bb-n");
    if (e.target.closest?.("[contenteditable]") && !e.target.classList?.contains("kdx-bb-n")) { e.preventDefault(); return; }
    if (pal) drag = { src: "palette", el: pal };
    else if (n) drag = { src: "canvas", ref: nodeAt(v.nodes, unkey(n.dataset.path)), el: n };
    else return;
    e.dataTransfer.effectAllowed = drag.src === "palette" ? "copy" : "move";
    e.dataTransfer.setData("text/plain", "kdx-bubble");
    e.stopPropagation();
    requestAnimationFrame(() => drag?.el?.classList.add("dragging"));
  });
  el.addEventListener("dragend", () => { drag?.el?.classList.remove("dragging"); drag = null; hideCaret(); });
  el.addEventListener("dragover", (e) => {
    if (!drag || !e.target.closest?.('[data-col="canvas"]')) { hideCaret(); return; }
    const t = dropTarget(e);
    if (!t) return;
    if (drag.src === "canvas" && t.laneEl.closest(".kdx-bb-n") && drag.el.contains(t.laneEl)) { hideCaret(); return; } // not into itself
    e.preventDefault();
    e.dataTransfer.dropEffect = drag.src === "palette" ? "copy" : "move";
    showCaret(t);
  });
  el.addEventListener("drop", (e) => {
    if (!drag) return;
    const t = dropTarget(e);
    hideCaret();
    if (!t || (drag.src === "canvas" && drag.el.contains(t.laneEl))) return;
    e.preventDefault();
    snap();
    if (drag.src === "palette") {
      const added = insert(t.lp, t.index, paletteNodes(drag.el), drag.el.dataset.pal === "snippet");
      v.sel = key(pathOf(v.nodes, added[added.length - 1]));
    } else { // insert a placeholder first (paths are still valid), then move the bubble there by reference
      const ph = { t: "text", v: "" };
      laneAt(v.nodes, t.lp).splice(t.index, 0, ph);
      removeRef(v.nodes, drag.ref);
      prune(v.nodes);
      replaceRef(v.nodes, ph, [drag.ref]);
      v.sel = key(pathOf(v.nodes, drag.ref));
    }
    drag.el?.classList.remove("dragging");
    drag = null;
    changed();
  });

  // ------------------------------------------------------------------ pool editor (phase 2)
  async function editPool(key, dir = "") {
    const m = await import("./pooledit.mjs?v=0.7.14");
    const folders = [...new Set(cat.pools.map((p) => dirOf(p.key)))].filter((d) => !d.startsWith("packs/") && d !== "(top)").sort();
    const folder = dir || (v.pool && !key ? dirOf(v.pool.key) : ""); // the folder it was opened from, else none
    m.openPoolEditor({ key, folder, folders, onSaved: (saved) => reloadPalette(saved) });
  }
  /** After a pool was saved or retired: fresh pool list, values and preview. */
  async function reloadPalette(key) {
    const fresh = await call("GET", "/kdx_console/builder");
    if (fresh.ok) Object.assign(cat, { pools: fresh.pools, templates: fresh.templates });
    if (key) { v.openDirs.add(dirOf(key)); v.pool = null; await showPool(key); }
    else if (v.pool && !cat.pools.some((p) => p.key === v.pool.key)) v.pool = null;
    paintPalette(); paintCanvas(); paintSide(); schedule(0);
  }

  // ------------------------------------------------------------------ open, new, save
  async function discardOk() {
    return !v.dirty || askConfirm({ title: "Discard changes?", text: "The current template has unsaved changes.", okLabel: "Discard", danger: true });
  }
  function load(nodes, name = "", note = "") {
    Object.assign(v, { nodes, name, loaded: name, note, dirty: false, sel: null, past: [], future: [], textView: false, seed: newSeed() });
    render();
    schedule(0);
  }
  async function openTemplate(name) {
    if (!(await discardOk())) { paintHead(); return; }
    const r = await call("GET", `/kdx_console/builder/template?name=${encodeURIComponent(name)}`);
    if (!r.ok) { toast(r.error); paintHead(); return; }
    v.category = (r.categories || [])[0] || ""; // Save as keeps the copy in the original's category
    load(r.nodes, r.name, r.note);
  }
  async function startNew(kind) {
    if (!(await discardOk())) { paintHead(); return; }
    if (kind !== "empty") v.sex = kind;
    load(kind === "empty" ? [] : clone(cat.starters[kind]));
  }
  /** Save over the open file, or (new / renamed) as a new one. Save as… is the safe choice once a file is open. */
  function saveButtons() {
    const replace = !!v.loaded && v.name.trim() === v.loaded;
    return `<button class="kdx-btn ${replace ? "" : "kdx-primary"}" data-b="save" title="${replace
      ? `Write over templates/${esc(v.loaded)}.txt (asks first; the old file is kept as .bak)`
      : "Write templates/<name>.txt (asks before replacing a file; the old one is kept as .bak)"}">${replace ? "Save (replace)" : "Save"}</button>
      <button class="kdx-btn ${replace ? "kdx-primary" : ""}" data-b="saveas" title="Save under a new name; the open template stays as it is">Save as…</button>
      <button class="kdx-btn" data-b="node" title="Send this line to the KDX Wildcard Studio node as your own prompt, without saving a template (asks before replacing text there)">Use on node</button>`;
  }
  const paintSaveButtons = () => {
    const h = el.querySelector(".kdx-gal-head");
    h?.querySelectorAll('[data-b="save"],[data-b="saveas"],[data-b="node"]').forEach((b, i) => { if (i === 0) b.outerHTML = saveButtons(); else b.remove(); });
  };
  /** A free name for a copy: portrait_woman -> portrait_copy_woman, portrait_copy2_woman, …; the sex stays last. */
  function copyName(name) {
    const m = /^(.*?)(_woman|_man)?$/.exec(name || "template");
    const base = m[1].replace(/_copy\d*$/, "");
    const taken = new Set(cat.templates);
    for (let i = 1; i < 1000; i++) {
      const cand = `${base}_copy${i > 1 ? i : ""}${m[2] || ""}`;
      if (!taken.has(cand)) return cand;
    }
    return `${base}_copy${m[2] || ""}`;
  }
  async function saveAs() {
    const name = await askText({ title: "Save as a new template", value: copyName(v.name.trim() || v.loaded),
      text: `${v.loaded ? `templates/${v.loaded}.txt stays as it is. ` : ""}Name of the new file (a-z, 0-9, _)${v.category ? `; it goes into the same category` : ""}.`,
      okLabel: "Save copy" });
    if (name == null) return;
    const clean = name.trim().toLowerCase().replace(/\.txt$/, "");
    if (!/^[a-z0-9][a-z0-9_]{0,63}$/.test(clean)) { toast("Template names are lower case letters, digits and _ (e.g. lounge_copy_woman)."); return; }
    const before = v.name;
    v.name = clean;
    if (!(await save(true))) { v.name = before; paintHead(); }
  }
  async function save(asNew = false) {
    const name = v.name.trim();
    if (!name) { toast("Give the template a name first."); el.querySelector('[data-b="name"]')?.focus(); return; }
    clearTimeout(timer);
    await runPreview();
    const pv = v.preview;
    if (pv?.error) { toast(pv.error); return; }
    const warns = pv?.warnings || [];
    if (warns.length && !(await askConfirm({ title: `Save with ${warns.length} warning${warns.length === 1 ? "" : "s"}?`,
      text: warns.map((w) => `• ${w.msg}`).join("\n"), okLabel: "Save anyway" }))) return;
    const req = { name, category: v.category, nodes: v.nodes };
    let r = await call("POST", "/kdx_console/builder/save", req);
    if (!r.ok && r.exists) {
      const what = asNew ? "A template with this name exists already." : "The file exists.";
      if (!(await askConfirm({ title: `Replace templates/${name}.txt?`, text: `${what} The old version is kept as templates/${name}.txt.bak.`, okLabel: "Replace", danger: true }))) { paintHead(); return; }
      r = await call("POST", "/kdx_console/builder/save", { ...req, overwrite: true });
    }
    if (!r.ok) { toast(r.error); return; }
    v.dirty = false;
    v.loaded = r.name;
    if (!cat.templates.includes(r.name)) { cat.templates.push(r.name); cat.templates.sort(); }
    toast(`Saved templates/${r.name}.txt${r.backup ? " (old file kept as .bak)" : ""}${r.category ? ` and added it to ${r.category}` : ""}.`, "success");
    refresh();
    paintHead();
    return true;
  }

  // ------------------------------------------------------------------ events
  el.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-b]");
    const act = b?.dataset.b;
    if (act === "close") { close(); return; }
    if (!cat.ok) return;
    if (b && (b.tagName === "SELECT" || (b.tagName === "INPUT"))) return;
    if (act === "save") { save(); return; }
    if (act === "saveas") { saveAs(); return; }
    if (act === "node") {
      clearTimeout(timer);
      await runPreview();
      if (v.preview?.error || !v.preview?.text?.trim()) { toast(v.preview?.error || "The template is empty."); return; }
      const undo = await useTextOnNode(v.preview.text);
      if (undo) { v.undo = undo; paintPreview(); }
      return;
    }
    if (act === "restore") { restoreText(v.undo); v.undo = null; paintPreview(); return; }
    if (act === "tab") { v.tab = b.dataset.m; paintPalette(); return; }
    if (act === "pedit" || act === "pnew") { e.preventDefault(); editPool(act === "pedit" ? b.dataset.key : null, b.dataset.dir || ""); return; } // preventDefault: a ＋ in a folder title must not fold it
    if (act === "sex") { v.sex = b.dataset.m; paintPalette(); return; }
    if (act === "append") { const pal = b.closest("[data-pal]") || b; appendHere(paletteNodes(pal), pal.dataset.pal === "snippet"); return; }
    if (act === "undo" || act === "redo") { undo(act === "redo"); return; }
    if (act === "textview") { v.textView = !v.textView; paintCanvas(); el.querySelector(".kdx-bb-ta")?.focus(); return; }
    if (act === "apply") {
      const text = el.querySelector(".kdx-bb-ta")?.value || "";
      const r = await call("POST", "/kdx_console/builder/parse", { text });
      if (!r.ok) { toast(r.error); return; }
      snap();
      v.nodes = r.nodes; v.textView = false; v.sel = null;
      changed();
      return;
    }
    if (act === "again") { v.seed = newSeed(); runPreview(); return; }
    if (act === "keep") {
      const s = v.preview?.samples?.[Number(b.dataset.i)];
      if (!s || !v.preview?.text) return;
      const { openKeep } = await import("./keep.mjs?v=0.7.14");
      openKeep({ text: v.preview.text, seed: s.seed, expected: s.text, from: "builder", name: v.name || v.loaded, category: v.category });
      return;
    }
    if (act === "copy") { try { await navigator.clipboard.writeText(v.preview?.text || ""); toast("Copied.", "success"); } catch (_e) { toast("Copy failed."); } return; }
    if (act === "del") { select(b.dataset.path); removeSel(); return; }
    if (act === "delsel") { removeSel(); return; }
    if (act === "move") { moveSel(Number(b.dataset.d)); return; }
    if (act === "fold") { const n = nodeAt(v.nodes, unkey(b.dataset.path)); n._c = !n._c; paintCanvas(); return; }
    if (act === "optadd") { snap(); nodeAt(v.nodes, unkey(b.dataset.path)).opts.push({ w: null, items: [] }); changed(); return; }
    if (act === "optdel") { snap(); nodeAt(v.nodes, unkey(b.dataset.path)).opts.splice(Number(b.dataset.o), 1); v.sel = null; changed(); return; }
    if (act === "dup") { const s = selected(true); if (s) { snap(); const c = clone(s.n); laneAt(v.nodes, s.p.slice(0, -1)).splice(s.p[s.p.length - 1] + 1, 0, c); v.sel = key(pathOf(v.nodes, c)); changed(); } return; }
    if (act === "wrap") {
      const s = selected(true);
      if (!s) return;
      snap();
      const other = b.dataset.m === "some" ? [] : [{ t: "text", v: "or this" }];
      const inner = s.n.t === "choice" && kindOf(s.n) === "solo" ? s.n.opts[0].items : [s.n]; // {x} becomes {x|}, not {{x}|}
      const g = { t: "choice", count: null, sep: null, opts: [{ w: null, items: inner }, { w: null, items: other }] };
      laneAt(v.nodes, s.p.slice(0, -1))[s.p[s.p.length - 1]] = g;
      v.sel = key(s.p);
      changed();
      return;
    }
    if (act === "kind") {
      const s = selected();
      if (!s || s.n.t !== "choice") return;
      snap();
      if (b.dataset.m === "multi") { s.n.count = s.n.count ?? "1-2"; s.n.sep = s.n.sep ?? " "; } else { s.n.count = null; s.n.sep = null; }
      changed();
      return;
    }
    const pal = e.target.closest("[data-pal]");
    if (pal?.dataset.pal === "pool") { v.pool = null; await showPool(pal.dataset.key); paintPalette(); return; }
    const n = e.target.closest(".kdx-bb-n");
    if (n) { select(n.dataset.path); return; }
    if (e.target.closest(".kdx-bb-canvas")) select(null);
  });
  el.addEventListener("toggle", (e) => {
    const d = e.target.closest?.("details[data-dir]");
    if (d) { if (d.open) v.openDirs.add(d.dataset.dir); else v.openDirs.delete(d.dataset.dir); }
  }, true);
  el.addEventListener("focusin", (e) => {
    const ed = e.target.closest?.("[data-edit]");
    if (ed && v.sel !== ed.dataset.edit) select(ed.dataset.edit);
    if (ed) editSnap = true; // one undo step per editing session, taken at the first key
  });
  el.addEventListener("focusout", (e) => {
    const ed = e.target.closest?.("[data-edit]");
    if (!ed) return;
    const n = nodeAt(v.nodes, unkey(ed.dataset.edit));
    if (n && !n.v) { removeRef(v.nodes, n); v.sel = null; changed(); }
  });
  el.addEventListener("change", (e) => {
    const t = e.target;
    const act = t.dataset.b;
    if (act === "open" && t.value) openTemplate(t.value);
    else if (act === "new" && t.value) startNew(t.value);
    else if (act === "category") v.category = t.value;
    else if (act === "w") {
      const w = t.value.trim();
      if (w && !/^(\d+(\.\d+)?|\.\d+)$/.test(w)) { toast("A weight is a number like 3 or 0.5."); t.value = ""; return; }
      snap();
      nodeAt(v.nodes, unkey(t.dataset.path)).opts[Number(t.dataset.o)].w = w && w !== "1" ? w : null;
      schedule();
    } else if (act === "count" || act === "sep") {
      const s = selected();
      if (!s) return;
      const val = t.value;
      if (act === "count" && !/^\d{0,2}(-\d{0,2})?$/.test(val.trim())) { toast("Write a number (2) or a range (1-3)."); t.value = s.n.count; return; }
      if (act === "sep" && /[{}|$]/.test(val)) { toast("The separator cannot contain { } | $."); t.value = s.n.sep ?? ""; return; }
      snap();
      if (act === "count") s.n.count = val.trim(); else s.n.sep = val === "" ? null : val;
      changed();
    }
  });
  el.addEventListener("input", (e) => {
    const t = e.target;
    const ed = t.closest?.("[data-edit]");
    if (ed) { // typing in a text bubble: change the data, never repaint the bubble being typed in
      if (editSnap) { snap(); editSnap = false; }
      const n = nodeAt(v.nodes, unkey(ed.dataset.edit));
      n.v = ed.textContent.replace(/[\r\n]+/g, " ");
      v.dirty = true;
      schedule(500);
      return;
    }
    if (t.dataset.b === "name") { v.name = t.value.trim().toLowerCase(); v.dirty = true; paintSaveButtons(); schedule(500); }
    else if (t.dataset.b === "filter") { v.filter = t.value; paintPalette(); }
  });
  el.addEventListener("keydown", (e) => {
    e.stopPropagation(); // ComfyUI shortcuts must not fire while working here
    const typing = e.target.matches?.("input,textarea,select,[contenteditable]");
    if (e.target.closest?.("[data-edit]") && e.key === "Enter") { e.preventDefault(); e.target.blur(); return; }
    if (e.key === "Enter" && e.target.matches?.("input.kdx-bb-w,input.kdx-rep")) { e.target.blur(); return; }
    if (typing) return;
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); undo(e.shiftKey); }
    else if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); undo(true); }
    else if ((e.key === "Delete" || e.key === "Backspace") && v.sel != null) { e.preventDefault(); removeSel(); }
    else if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) { e.preventDefault(); moveSel(e.key === "ArrowLeft" ? -1 : 1); }
  });
  function onKey(e) {
    if (e.key !== "Escape" || document.querySelector(".kdx-modal") || !win) return;
    if (e.target?.matches?.("input,textarea,select,[contenteditable]")) { e.target.blur(); return; }
    e.preventDefault();
    e.stopPropagation();
    close();
  }
  document.addEventListener("keydown", onKey, true);
  async function close() {
    if (v.dirty && !(await askConfirm({ title: "Close the builder?", text: "The template has unsaved changes.", okLabel: "Close", danger: true }))) return;
    clearTimeout(timer);
    document.removeEventListener("keydown", onKey, true);
    el.remove();
    win = null;
  }
  /** A line from Keep parts: parse it into bubbles and load it as a new, unsaved template. */
  async function loadText(text, name = "") {
    if (!cat.ok) return;
    el.style.zIndex = "9750"; // above the Gallery and its viewer it came from, below Keep parts and dialogs
    document.body.appendChild(el);
    if (!(await discardOk())) return;
    const r = await call("POST", "/kdx_console/builder/parse", { text });
    if (!r.ok) { toast(r.error); return; }
    load(r.nodes, "", "From Keep parts: kept parts are plain text, the rest are still pools and groups.");
    v.name = name;
    v.dirty = true;
    paintHead();
  }
  win = { close, loadText };
  if (cat.ok) {
    if (opts.text != null) await loadText(opts.text, opts.name || "");
    else { render(); schedule(0); }
  }
}
