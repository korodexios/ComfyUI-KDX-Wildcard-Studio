// KDX Wildcard Studio - Keep parts: take an image's prompt apart into the picks that made it, keep the parts you like
// (pose, clothing, place, light, style …) and let the rest vary. One window for the Gallery (image details) and the
// Template builder (a preview sample).
//
// The server owns the logic (kdx_console/keep.py): it expands the template again with the image's seed and a record
// of every pick, checks it against the prompt stored in the image, and turns the kept parts into a template line
// (kept parts as fixed text, the choices around them kept, everything else still wildcards). This view only shows
// the parts and sends the ids that are kept. Writes to the node happen on the user's click only.
import { ensureTheme } from "./theme.mjs?v=0.7.12";
import { call, getSnap, refresh, toast } from "./client.mjs?v=0.7.12";
import { askConfirm, askText } from "./dialog.mjs?v=0.7.12";
import { restoreText, useTextOnNode } from "./nodewrite.mjs?v=0.7.12";

let win = null;
let poolCache = null; // the library's pools for Replace / Add (loaded on first use)
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const newSeed = () => Math.floor(Math.random() * 2 ** 31);
const short = (s, n = 70) => { const t = String(s || "").trim(); return t.length > n ? `${t.slice(0, n - 1)}…` : t; };

const CSS = `
.kdx-kp{z-index:9800}
.kdx-kp .kdx-pill:not(.on){text-decoration:none;color:var(--kdx-fg)}
.kdx-kp-body{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1.25fr) minmax(300px,1fr);gap:14px;padding:10px 14px 16px}
.kdx-kp-col{min-height:0;overflow:auto;display:flex;flex-direction:column;gap:10px}
.kdx-kp-col > *{flex:none}
.kdx-kp-top{display:flex;gap:10px;align-items:flex-start}
.kdx-kp-img{width:120px;height:120px;object-fit:cover;border-radius:6px;border:1px solid var(--kdx-border);flex:none}
.kdx-kp-prompt{font-size:13px;line-height:1.75;background:var(--kdx-field);border:1px solid var(--kdx-border);border-radius:8px;padding:10px 12px;
 user-select:none}
.kdx-kp-p{border-radius:4px;cursor:pointer;padding:1px 0;box-decoration-break:clone;-webkit-box-decoration-break:clone;
 border-bottom:1px dotted var(--kdx-muted)}
.kdx-kp-p:hover{background:color-mix(in srgb,var(--kdx-acc) 16%,transparent);outline:1px solid var(--kdx-acc)}
.kdx-kp-p.lock{background:var(--kdx-acc);color:var(--kdx-on-acc);border-bottom-color:transparent}
.kdx-kp-p.lock .kdx-kp-p{border-bottom-color:transparent;color:inherit}
.kdx-kp-p.lock:hover{outline:2px solid var(--kdx-fg)}
.kdx-kp-p.pin{outline:1px dashed var(--kdx-acc);outline-offset:1px}
.kdx-kp-p.foc{box-shadow:0 0 0 2px var(--kdx-warn)}
.kdx-kp-p.miss{color:var(--kdx-err)}
.kdx-kp-t{cursor:pointer;border-radius:3px}
.kdx-kp-t:hover{background:color-mix(in srgb,var(--kdx-fg) 10%,transparent);outline:1px dotted var(--kdx-muted)}
.kdx-kp-t.foc{box-shadow:0 0 0 2px var(--kdx-warn)}
.kdx-kp-off .kdx-kp-t{cursor:default}
.kdx-kp-off .kdx-kp-t:hover{background:none;outline:none}
.kdx-kp-t.mark{background:var(--kdx-acc);color:var(--kdx-on-acc)}
.kdx-kp-gone .kdx-kp-t:not(.mark):not(.swap){opacity:.4;text-decoration:line-through}
.kdx-kp-t.swap,.kdx-kp-p.swap{border:1px dashed var(--kdx-acc);padding:0 4px;font-style:italic;color:var(--kdx-acc-text)}
.kdx-kp-pool{display:flex;flex-direction:column;gap:2px;max-height:50vh;overflow:auto}
.kdx-kp-pool button{appearance:none;text-align:left;border:1px solid transparent;background:none;color:var(--kdx-fg);font:inherit;
 padding:3px 6px;border-radius:5px;cursor:pointer}
.kdx-kp-pool button:hover,.kdx-kp-pool button:focus-visible{border-color:var(--kdx-acc);outline:none}
.kdx-kp-empty{font-size:10px;opacity:.75;padding:0 3px}
.kdx-kp-off .kdx-kp-p{cursor:default;border-bottom-color:transparent}
.kdx-kp-off .kdx-kp-p:hover{background:none;outline:none}
.kdx-kp-chain{display:flex;flex-wrap:wrap;align-items:center;gap:4px}
.kdx-kp-chain .kdx-go{max-width:100%;overflow:hidden;text-overflow:ellipsis}
.kdx-kp-legend{display:flex;flex-wrap:wrap;gap:10px;font-size:11px;color:var(--kdx-muted)}
.kdx-kp-legend i{display:inline-block;width:14px;height:10px;border-radius:3px;vertical-align:-1px;margin-right:3px}
.kdx-kp-banner{border-radius:8px;padding:8px 10px;border:1px solid var(--kdx-warn);color:var(--kdx-fg)}
.kdx-kp-banner.err{border-color:var(--kdx-err)}
.kdx-kp-banner b{color:var(--kdx-warn)}
.kdx-kp-banner.err b{color:var(--kdx-err)}
.kdx-kp-sample mark{background:color-mix(in srgb,var(--kdx-acc) 30%,transparent);color:inherit;border-radius:3px}
@media (max-width:900px){.kdx-kp-body{grid-template-columns:1fr;overflow:auto}.kdx-kp-col{overflow:visible}}
`;
let cssDone = false;
function ensureCss() {
  if (cssDone) return;
  cssDone = true;
  const st = document.createElement("style");
  st.id = "kdx-console-keep-style";
  st.textContent = CSS;
  document.head.appendChild(st);
}

export function closeKeep() { win?.close(); }
export const keepOpen = () => !!win;

/**
 * Open the keep window.
 * opts: {template?: name | text?: string, seed, expected?: stored prompt, llm?: bool, category?: key,
 *        name?: suggested name, image?: url, from?: "gallery" | "builder"}
 */
export async function openKeep(opts = {}) {
  ensureTheme();
  ensureCss();
  closeKeep();
  const el = document.createElement("div");
  el.className = "kdx-root kdx-gal kdx-kp";
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-modal", "true");
  el.innerHTML = `<div class="kdx-gal-head"><span class="kdx-gal-title">🔒 Keep parts</span><span class="kdx-muted">Taking the prompt apart…</span>
    <span class="kdx-sp"></span><button class="kdx-btn" data-k="close" title="Close (Esc)">✕</button></div>`;
  document.body.appendChild(el);
  const input = opts.template ? { template: opts.template } : { text: opts.text || "" };
  const v = {
    data: null, locks: new Set(), swaps: new Map(), marks: new Set(), dropText: false, append: "", focus: null, override: false, built: null,
    sampleSeed: newSeed(), count: 4, category: opts.category || "", undo: null,
  };
  const parts = new Map(); // id -> view node
  const texts = new Map(); // "<part>.<seg>.<piece>" -> {part, core}: pieces of plain text, replaceable
  const parent = new Map(); // id -> parent id

  const close = () => {
    clearTimeout(timer);
    window.removeEventListener("keydown", onKey, true);
    el.remove();
    win = null;
  };
  win = { close };

  // Plain text can be replaced where it is not part of a pick: the prompt itself, the chosen template line, {x}.
  // Inside a pick (an option of a group), a click keeps the pick, as before.
  const plainText = (n) => n.kind === "root" || n.solo || (n.kind === "token" && n.src.startsWith("__templates/"));
  const d = await call("POST", "/kdx_console/keep", { ...input, seed: opts.seed, expected: opts.expected || "" });
  if (!win) return;
  if (!d.ok) {
    el.querySelector(".kdx-muted").innerHTML = `<span class="kdx-err">${esc(d.error || "could not take the prompt apart")}</span>`;
  } else {
    v.data = d;
    (function index(n, p) {
      parts.set(n.id, n);
      if (p != null) parent.set(n.id, p);
      for (const s of n.segs) {
        if (s.kind === "text") { if (plainText(n)) for (const t of s.pieces) if (t.core) texts.set(t.id, { part: n.id, core: t.core }); }
        else index(s, n.id);
      }
    })(d.tree, null);
  }

  // ------------------------------------------------------------------ state helpers
  const transparent = plainText;
  const ancestors = (id) => { const out = []; let p = parent.get(id); while (p != null) { out.push(p); p = parent.get(p); } return out; };
  const lockedBy = (id) => (v.locks.has(id) ? id : ancestors(id).find((a) => v.locks.has(a)) ?? null);
  const canLock = () => v.data && v.data.reliable && (v.data.matches !== false || v.override);
  const lockable = [...parts.values()].filter((n) => !transparent(n));
  const isText = (id) => typeof id === "string";
  const partOf = (id) => (isText(id) ? texts.get(id)?.part : id); // a piece of text belongs to the part that holds it
  const pinned = () => {
    const s = new Set();
    for (const id of v.locks) for (const a of ancestors(id)) s.add(a);
    for (const id of v.swaps.keys()) {
      if (isText(id)) s.add(partOf(id));
      for (const a of ancestors(partOf(id))) s.add(a);
    }
    return s;
  };
  /** Forget locks and replacements on `id`, on what contains it and on its parts (a piece of text: on the part that
   * holds it and what contains that part, since that part has to stay as it is). */
  function free(id) {
    const own = partOf(id);
    const up = isText(id) ? [own, ...ancestors(own)] : ancestors(own);
    for (const set of [v.locks, v.swaps, v.marks]) {
      for (const x of [...set.keys()]) {
        if (x === id || up.includes(x)) set.delete(x);
        else if (!isText(id) && (ancestors(partOf(x)).includes(id) || (isText(x) && partOf(x) === id))) set.delete(x);
      }
    }
  }
  function lock(id) { // keep exactly this part
    free(id);
    v.locks.add(id);
  }
  function swap(id, text) { // put other wildcards (or words) in place of this part
    free(id);
    v.swaps.set(id, text);
    v.focus = id;
    changed();
  }
  function toggle(id) {
    if (v.swaps.has(id)) { v.focus = id; changed(); return; } // a replaced part: its buttons are in the Keep row
    const by = lockedBy(id);
    if (by != null) v.locks.delete(by);
    else lock(id);
    v.focus = id;
    changed();
  }
  function groupOn(g) { return g.ids.length && g.ids.every((id) => lockedBy(id) != null); }
  function toggleGroup(g) {
    if (groupOn(g)) for (const id of g.ids) { const by = lockedBy(id); if (by != null) v.locks.delete(by); }
    else for (const id of g.ids) if (lockedBy(id) == null) lock(id);
    changed();
  }
  function invert() { // keep what varies now, let vary what is kept now
    const was = new Set(v.locks);
    const pins = pinned();
    const next = new Set();
    (function walk(n) {
      if (was.has(n.id) || v.swaps.has(n.id)) return;
      if (!transparent(n) && !pins.has(n.id)) { next.add(n.id); return; }
      for (const s of n.segs) if (s.kind !== "text") walk(s);
    })(v.data.tree);
    v.locks = next;
    changed();
  }

  // ------------------------------------------------------------------ rendering
  function partHtml(n, pins) {
    if (v.swaps.has(n.id)) {
      const t = v.swaps.get(n.id);
      return `<span class="kdx-kp-p swap ${v.focus === n.id ? "foc" : ""}" data-id="${n.id}" title="${esc(`Replaced: ${n.src}\n→ ${t || "(removed)"}`)}">⇄ ${esc(t || "(removed)")}</span>`;
    }
    const inner = n.segs.map((s) => (s.kind === "text" ? textHtml(s, n) : partHtml(s, pins))).join("")
      || (transparent(n) ? "" : `<span class="kdx-kp-empty" aria-label="picked nothing">∅</span>`);
    if (transparent(n)) return inner;
    const cls = [v.locks.has(n.id) ? "lock" : "", pins.has(n.id) ? "pin" : "", v.focus === n.id ? "foc" : "", n.missing ? "miss" : ""].join(" ");
    const tip = `${n.src}${n.text ? `\n→ ${short(n.text, 160)}` : "\n→ (nothing)"}`;
    return `<span class="kdx-kp-p ${cls}" data-id="${n.id}" title="${esc(tip)}">${inner}</span>`;
  }

  function textHtml(s, owner) {
    return s.pieces.map((t) => {
      if (!t.core || !plainText(owner)) return esc(t.lead + t.core + t.trail);
      const mark = v.marks.has(t.id);
      const core = v.swaps.has(t.id)
        ? `<span class="kdx-kp-t swap ${v.focus === t.id ? "foc" : ""}" data-tid="${esc(t.id)}" title="${esc(`Replaced: ${t.core}\n→ ${v.swaps.get(t.id) || "(removed)"}`)}">⇄ ${esc(v.swaps.get(t.id) || "(removed)")}</span>`
        : `<span class="kdx-kp-t ${mark ? "mark" : ""} ${v.focus === t.id ? "foc" : ""}" data-tid="${esc(t.id)}" title="${mark ? "Kept text: click to unmark it" : "Plain text: click to keep it (several can be marked); ⇄ Replace puts wildcards or other words here"}">${esc(t.core)}</span>`;
      return `${esc(t.lead)}${core}${esc(t.trail)}`;
    }).join("");
  }

  function bannerHtml() {
    const d = v.data;
    const out = [];
    if (!d.reliable) {
      out.push(`<div class="kdx-kp-banner err"><b>⛔ Cannot keep parts of this prompt.</b> A wildcard value cuts through another one
        (an unbalanced brace in a pool, for example), so its parts cannot be told apart reliably.</div>`);
    } else if (d.matches === false) {
      out.push(`<div class="kdx-kp-banner"><b>⚠ The image's prompt differs from what the wildcards give today.</b>
        The wildcard files changed since the image was made, so the parts below are today's picks, not the image's.
        ${v.override ? "You chose to work with today's picks." : `<div class="kdx-row" style="margin-top:6px"><button class="kdx-btn" data-k="override"
        title="Keep parts of today's expansion although it is not the image's prompt">Use today's picks anyway</button></div>`}
        <details style="margin-top:6px"><summary class="kdx-muted">Prompt stored in the image</summary><div class="kdx-bb-sample">${esc(opts.expected)}</div></details></div>`);
    } else if (d.matches == null && opts.from === "gallery") {
      out.push(`<div class="kdx-muted">The image stored no prompt text; shown is what its template and seed give today.</div>`);
    }
    if (opts.llm) out.push(`<div class="kdx-muted">LLM was on for this image: these are the parts of the Studio prompt, before the LLM rewrote it.</div>`);
    if (d.missing?.length) out.push(`<div class="kdx-warn">Unknown wildcards: ${esc(d.missing.join(", "))}</div>`);
    return out.join("");
  }

  function chainHtml() {
    if (isText(v.focus) && texts.has(v.focus)) {
      return `<span class="kdx-muted">Text</span><b>“${esc(short(texts.get(v.focus).core, 80))}”</b>
        <span class="kdx-muted">${v.marks.has(v.focus) ? "· kept" : v.swaps.has(v.focus) ? "· replaced" : ""}</span><span class="kdx-sp"></span>
        <button class="kdx-btn" data-k="replace" title="Put wildcards or other words in place of this text (the punctuation around it stays)">⇄ Replace…</button>
        ${v.swaps.has(v.focus) ? `<button class="kdx-btn" data-k="original" title="Back to the original text">↺ Original</button>` : ""}`;
    }
    if (v.focus == null || !parts.has(v.focus)) return `<span class="kdx-muted">Click a part of the prompt to keep it; click it again to let it vary. Dotted underline = a pick. Plain text: a click marks it as kept (several can be marked). ⇄ Replace puts other wildcards or words in place of what you clicked.</span>`;
    const chain = [v.focus, ...ancestors(v.focus)].filter((id) => !transparent(parts.get(id))).reverse();
    return `<span class="kdx-muted">Keep</span>${chain.map((id, i) => {
      const n = parts.get(id);
      const on = v.locks.has(id);
      const covered = !on && lockedBy(id) != null;
      return `${i ? `<span class="kdx-muted">›</span>` : ""}<button class="kdx-go ${on ? "on" : ""}" data-k="level" data-id="${id}"
        title="${esc(`${on ? "Let it vary again" : "Keep exactly this"}: ${n.src}\n→ ${short(n.text, 200)}`)}"${covered ? ' style="opacity:.7"' : ""}>${on ? "🔒 " : ""}${esc(n.label)}${chain.length > 1 && i === 0 ? " (whole)" : ""}</button>`;
    }).join("")}<span class="kdx-sp"></span>
      <button class="kdx-btn" data-k="replace" title="Put another pool, wildcards or your own words in place of ${esc(parts.get(v.focus).label)} (the parts around it stay)">⇄ Replace…</button>
      ${v.swaps.has(v.focus) ? `<button class="kdx-btn" data-k="original" title="Back to the original part">↺ Original</button>` : ""}`;
  }

  function leftHtml() {
    const d = v.data;
    const pins = pinned();
    const off = !canLock();
    const groups = d.groups || [];
    return `${bannerHtml()}
      <div class="kdx-kp-top">${opts.image ? `<img class="kdx-kp-img" src="${esc(opts.image)}" alt="">` : ""}
        <div class="kdx-col" style="display:flex;flex-direction:column;gap:6px;min-width:0">
          <div class="kdx-row"><b>Quick choices</b><span class="kdx-muted">keep a whole group</span></div>
          <div class="kdx-row">${groups.length ? groups.map((g) => `<button class="kdx-pill ${groupOn(g) ? "on" : ""}" data-k="group" data-g="${esc(g.id)}"
            ${off ? "disabled" : ""} title="${esc(`${g.ids.length} part${g.ids.length === 1 ? "" : "s"}: ${g.ids.map((i) => parts.get(i)?.label).join(", ")}`)}">${esc(g.label)}</button>`).join("")
            : `<span class="kdx-muted">no groups in this prompt</span>`}</div>
          <div class="kdx-row"><button class="kdx-btn" data-k="invert" ${off || !lockable.length ? "disabled" : ""} title="Keep what varies now and let vary what is kept now">⇄ Invert</button>
            <button class="kdx-btn" data-k="clear" ${v.locks.size || v.swaps.size || v.marks.size || v.dropText ? "" : "disabled"} title="Let everything vary again, unmark the text and undo the replacements">Clear</button>
            <button class="kdx-pill ${v.dropText ? "on" : ""}" data-k="droptext" ${off || !texts.size ? "disabled" : ""} aria-pressed="${v.dropText}"
              title="Leave out the plain text you did not mark: only the wildcards, the kept parts and the marked text stay. Then add new wildcards with ⇄ Replace or ＋ Add at the end">✂ Remove unmarked text</button>
            <span class="kdx-muted">${v.locks.size + v.marks.size} kept${v.swaps.size ? ` · ${v.swaps.size} replaced` : ""}</span></div>
        </div></div>
      <div class="kdx-kp-chain" data-col="chain">${chainHtml()}</div>
      ${lockable.length || texts.size ? `<div class="kdx-kp-prompt ${off ? "kdx-kp-off" : ""} ${v.dropText ? "kdx-kp-gone" : ""}" data-col="prompt">${partHtml(d.tree, pins)}</div>`
        : `<div class="kdx-kp-prompt">${esc(d.prompt)}</div><p class="kdx-muted">This prompt has no wildcards: nothing varies, so there is nothing to keep.</p>`}
      <div class="kdx-kp-legend"><span><i style="background:var(--kdx-acc)"></i>kept</span>
        <span><i style="outline:1px dashed var(--kdx-acc)"></i>choice kept because a part inside is kept</span>
        <span><i style="border-bottom:1px dotted var(--kdx-muted)"></i>varies</span>
        <span><i style="border:1px dashed var(--kdx-acc)"></i>replaced</span></div>
      <div class="kdx-row"><b title="Text or wildcards added after the prompt, e.g. in the style of __art/style__">＋ Add at the end</b>
        <input class="kdx-sel" data-k="append" type="text" spellcheck="false" style="flex:1;min-width:160px" value="${esc(v.append)}"
          placeholder="text or wildcards, e.g. __art/style__" ${off ? "disabled" : ""}>
        <button class="kdx-btn" data-k="appendpool" ${off ? "disabled" : ""} title="Add a pool from the library">＋ Pool…</button></div>`;
  }

  function markKept(text) {
    const kept = [...[...v.locks].map((id) => parts.get(id)?.text || ""), ...[...v.marks].map((id) => texts.get(id)?.core || "")].filter((t) => t.trim().length >= 3).sort((a, b) => b.length - a.length);
    let html = esc(text);
    for (const t of kept) {
      const e = esc(t);
      const i = html.indexOf(e);
      if (i >= 0 && !html.slice(0, i).endsWith("<mark>")) html = `${html.slice(0, i)}<mark>${e}</mark>${html.slice(i + e.length)}`;
    }
    return html;
  }

  function rightHtml() {
    const b = v.built;
    const cats = getSnap()?.config?.categories || [];
    const acts = `<div class="kdx-row"><b>Result</b><span class="kdx-sp"></span>
        <button class="kdx-btn kdx-primary" data-k="node" ${b?.template ? "" : "disabled"} title="Write the template where the Studio node reads it: user_text (use_user_text on) or the text node connected to user_prompt. Asks before replacing other text">Use on node</button>
        <button class="kdx-btn" data-k="save" ${b?.template ? "" : "disabled"} title="Write it as templates/<name>.txt">Save as template…</button>
        <button class="kdx-btn" data-k="builder" ${b?.template ? "" : "disabled"} title="Open it in the Template builder to edit it further">Open in Builder</button></div>
      ${v.undo ? `<div class="kdx-row"><button class="kdx-btn" data-k="restore" title="Put back the text that ${esc(v.undo.label)} held before Use on node">↶ Restore previous text of ${esc(v.undo.label)}</button></div>` : ""}
      <label class="kdx-row" style="gap:4px" title="Save as template: also add it to this category of the panel">Save into
        <select class="kdx-sel" data-k="category"><option value="">no category</option>
        ${cats.map((c) => `<option value="${esc(c.key)}" ${c.key === v.category ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>`;
    if (!b) return `${acts}<p class="kdx-muted">Composing…</p>`;
    if (b.error) return `${acts}<p class="kdx-err">${esc(b.error)}</p>`;
    const warns = b.warnings || [];
    return `${acts}
      ${warns.map((w) => `<div class="${w.level === "error" ? "kdx-err" : "kdx-warn"}">${w.level === "error" ? "⛔" : "⚠"} ${esc(w.msg)}</div>`).join("")}
      <div class="kdx-row"><b>${b.samples.length} variants</b><span class="kdx-muted">${v.locks.size || v.marks.size ? "kept parts are marked" : "nothing kept yet: everything varies"}</span>
        <span class="kdx-sp"></span><select class="kdx-sel" data-k="count" title="How many variants">${[2, 4, 6, 8].map((n) => `<option ${n === v.count ? "selected" : ""}>${n}</option>`).join("")}</select>
        <button class="kdx-btn" data-k="again" title="New random variants">⟳ Again</button></div>
      ${b.samples.map((s) => `<div class="kdx-bb-sample kdx-kp-sample"><div class="kdx-muted">seed ${s.seed}${s.missing?.length ? ` · <span class="kdx-err">unknown: ${esc(s.missing.join(", "))}</span>` : ""}</div>${markKept(s.text)}</div>`).join("")}
      <details class="kdx-bb-line"><summary>Template line</summary><div class="kdx-row"><span class="kdx-sp"></span><button class="kdx-btn" data-k="copy" title="Copy the line">Copy</button></div>
        <div class="kdx-bb-text">${esc(b.template)}</div></details>`;
  }

  function headHtml() {
    const what = opts.template ? `template ${opts.template}` : opts.from === "builder" ? "builder sample" : "own prompt";
    return `<span class="kdx-gal-title">🔒 Keep parts</span><span class="kdx-muted">${esc(what)} · seed ${esc(opts.seed)}</span>
      <span class="kdx-sp"></span><button class="kdx-btn" data-k="close" title="Close (Esc)">✕</button>`;
  }

  function render() {
    if (!v.data) return;
    el.innerHTML = `<div class="kdx-gal-head">${headHtml()}</div><div class="kdx-kp-body">
      <div class="kdx-kp-col" data-col="left">${leftHtml()}</div><div class="kdx-kp-col" data-col="right">${rightHtml()}</div></div>`;
  }
  const paint = (col, html) => {
    const c = el.querySelector(`[data-col="${col}"]`);
    if (!c) return;
    const top = c.scrollTop;
    const open = c.querySelector(".kdx-bb-line")?.open;
    c.innerHTML = html();
    c.scrollTop = top;
    if (open) c.querySelector(".kdx-bb-line").open = true;
  };

  // ------------------------------------------------------------------ server
  let timer = null;
  let ticket = 0;
  function changed() { paint("left", leftHtml); schedule(); }
  function schedule(delay = 220) { clearTimeout(timer); timer = setTimeout(build, delay); }
  async function build() {
    const my = ++ticket;
    const on = canLock();
    const r = await call("POST", "/kdx_console/keep/build", { ...input, seed: opts.seed, locks: on ? [...v.locks] : [],
      swaps: on ? Object.fromEntries(v.swaps) : {}, append: on ? v.append : "", marks: on ? [...v.marks] : [], drop_text: on && v.dropText,
      fingerprint: v.data.fingerprint, count: v.count, sample_seed: v.sampleSeed });
    if (my !== ticket || !win) return;
    v.built = r.ok ? r : { error: r.error || "could not compose" };
    paint("right", rightHtml);
  }

  // ------------------------------------------------------------------ actions
  async function useOnNode() {
    const undo = await useTextOnNode(v.built?.template);
    if (undo) { v.undo = undo; paint("right", rightHtml); }
  }
  function restore() {
    restoreText(v.undo);
    v.undo = null;
    paint("right", rightHtml);
  }
  /** Choose a pool of the library, or type wildcards / words. Resolves to the text or null. */
  async function pickPool(title, now = "") {
    if (!poolCache) {
      const r = await call("GET", "/kdx_console/builder");
      if (!r.ok) { toast(r.error); return null; }
      poolCache = r.pools.filter((p) => !p.key.startsWith("templates/"));
    }
    return new Promise((resolve) => {
      const wrap = document.createElement("div");
      wrap.className = "kdx-root kdx-modal";
      wrap.innerHTML = `<div class="kdx-modal-box" role="dialog" aria-modal="true" aria-label="${esc(title)}" style="width:min(640px,100%)">
        <div class="kdx-modal-title">${esc(title)}</div>
        ${now ? `<div class="kdx-modal-text">Now: ${esc(now)}</div>` : ""}
        <input class="kdx-field" type="text" spellcheck="false" placeholder="search pools, or type wildcards / words: {oil|ink} painting, __art/style__">
        <div class="kdx-kp-pool"></div>
        <div class="kdx-row kdx-modal-btns"><span class="kdx-muted">A pool picks one value per image.</span><span class="kdx-sp"></span>
          <button class="kdx-btn" data-no>Cancel</button><button class="kdx-btn kdx-primary" data-typed title="Use what is typed, as it is">Use as typed</button></div></div>`;
      document.body.appendChild(wrap);
      const field = wrap.querySelector("input");
      const list = wrap.querySelector(".kdx-kp-pool");
      const paintList = () => {
        const q = field.value.trim().toLowerCase().replace(/^_+|_+$/g, "");
        const rank = (p) => (!q ? 0 : p.key === q ? 0 : p.key.endsWith(`/${q}`) ? 1 : p.key.includes(q) ? 2 : (p.desc || "").toLowerCase().includes(q) ? 3 : 9);
        const hits = poolCache.map((p) => [rank(p), p]).filter(([r]) => r < 9).sort((x, y) => x[0] - y[0] || x[1].key.localeCompare(y[1].key))
          .slice(0, 200).map(([, p]) => p); // name matches first, then description matches
        list.innerHTML = hits.map((p) => `<button data-key="${esc(p.key)}" title="${esc(p.desc || "")}"><b>${esc(p.key)}</b>
          <span class="kdx-muted">${p.count} values${p.desc ? ` · ${esc(short(p.desc, 90))}` : ""}</span></button>`).join("")
          || `<span class="kdx-muted">No pool matches; "Use as typed" puts the text in as it is.</span>`;
      };
      paintList();
      let done = false;
      const close = (val) => { if (done) return; done = true; wrap.remove(); resolve(val); };
      field.addEventListener("input", paintList);
      list.addEventListener("click", (e) => { const b = e.target.closest("[data-key]"); if (b) close(`__${b.dataset.key}__`); });
      wrap.querySelector("[data-no]").addEventListener("click", () => close(null));
      wrap.querySelector("[data-typed]").addEventListener("click", () => close(field.value.trim()));
      wrap.addEventListener("pointerdown", (e) => { if (e.target === wrap) close(null); });
      wrap.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Escape") { e.preventDefault(); close(null); }
        else if (e.key === "Enter" && e.target === field) {
          e.preventDefault();
          const q = field.value.trim().replace(/^_+|_+$/g, "");
          close(poolCache.some((p) => p.key === q) ? `__${q}__` : field.value.trim());
        }
      });
      field.focus();
    });
  }
  function suggestName() {
    const base = String(opts.name || "kept").toLowerCase().replace(/^templates\//, "").replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "") || "kept";
    return `${base.replace(/_kept\d*$/, "")}_kept`.slice(0, 60);
  }
  async function save() {
    const text = v.built?.template;
    if (!text) return;
    if (/[\r\n]/.test(text)) { toast("A template is one line; this prompt has several lines. Use it on the node instead."); return; }
    const name = await askText({ title: "Save as a new template", value: suggestName(),
      text: `File name: templates/<name>.txt (a-z, 0-9, _)${v.category ? ". It is also added to the chosen category." : "."}`, okLabel: "Save" });
    if (name == null) return;
    const clean = name.trim().toLowerCase().replace(/\.txt$/, "");
    const req = { name: clean, text, category: v.category };
    let r = await call("POST", "/kdx_console/builder/save", req);
    if (!r.ok && r.exists) {
      if (!(await askConfirm({ title: `Replace templates/${clean}.txt?`, text: `A template with this name exists. The old version is kept as templates/${clean}.txt.bak.`, okLabel: "Replace", danger: true }))) return;
      r = await call("POST", "/kdx_console/builder/save", { ...req, overwrite: true });
    }
    if (!r.ok) { toast(r.error); return; }
    toast(`Saved templates/${r.name}.txt${r.backup ? " (old file kept as .bak)" : ""}${r.category ? ` and added it to ${r.category}` : ""}.`, "success");
    refresh();
  }
  async function toBuilder() {
    const text = v.built?.template;
    if (!text) return;
    const { openBuilder } = await import("./builder.mjs?v=0.7.12");
    close();
    openBuilder({ text, name: suggestName() });
  }

  // ------------------------------------------------------------------ events
  el.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-k]");
    const k = b?.dataset.k;
    if (k === "close") { close(); return; }
    if (!v.data) return;
    if (b && (b.tagName === "SELECT" || b.disabled)) return;
    if (k === "override") { v.override = true; render(); schedule(0); return; }
    if (k === "group") { const g = v.data.groups.find((x) => x.id === b.dataset.g); if (g && canLock()) toggleGroup(g); return; }
    if (k === "level") { if (!canLock()) return; const id = Number(b.dataset.id); if (v.locks.has(id)) v.locks.delete(id); else lock(id); v.focus = id; changed(); return; }
    if (k === "invert") { if (canLock()) invert(); return; }
    if (k === "clear") { v.locks.clear(); v.swaps.clear(); v.marks.clear(); v.dropText = false; changed(); return; }
    if (k === "droptext") { if (canLock()) { v.dropText = !v.dropText; changed(); } return; }
    if (k === "again") { v.sampleSeed = newSeed(); build(); return; }
    if (k === "copy") { try { await navigator.clipboard.writeText(v.built?.template || ""); toast("Copied.", "success"); } catch (_e) { toast("Copy failed."); } return; }
    if (k === "node") { useOnNode(); return; }
    if (k === "restore") { restore(); return; }
    if (k === "replace") {
      const id = v.focus;
      if (id == null || !canLock()) return;
      const what = isText(id) ? `“${short(texts.get(id).core, 40)}”` : parts.get(id).label;
      const t = await pickPool(`Replace ${what}`, v.swaps.has(id) ? v.swaps.get(id) : isText(id) ? texts.get(id).core : parts.get(id).src);
      if (t != null) swap(id, t);
      return;
    }
    if (k === "original") { v.swaps.delete(v.focus); changed(); return; }
    if (k === "appendpool") {
      const t = await pickPool("Add at the end");
      if (t) { v.append = `${v.append.trim()} ${t}`.trim(); changed(); }
      return;
    }
    if (k === "save") { save(); return; }
    if (k === "builder") { toBuilder(); return; }
    const tp = e.target.closest(".kdx-kp-t");
    if (tp && canLock()) {
      const id = tp.dataset.tid;
      if (!v.swaps.has(id)) { // a click keeps the text (or lets it go again); several can be kept
        if (v.marks.has(id)) v.marks.delete(id);
        else { free(id); v.marks.add(id); }
      }
      v.focus = id;
      changed();
      return;
    }
    const p = e.target.closest(".kdx-kp-p");
    if (p && canLock()) toggle(Number(p.dataset.id));
  });
  el.addEventListener("input", (e) => {
    if (e.target.dataset.k === "append") { v.append = e.target.value; schedule(400); } // never repaint the field being typed in
  });
  el.addEventListener("change", (e) => {
    const k = e.target.dataset.k;
    if (k === "count") { v.count = Number(e.target.value); build(); }
    else if (k === "category") v.category = e.target.value;
  });
  el.addEventListener("keydown", (e) => e.stopPropagation()); // ComfyUI shortcuts must not fire while working here
  // Window capture runs before the lightbox's document listener: Esc and the arrow keys belong to this window.
  function onKey(e) {
    if (!win || document.querySelector(".kdx-modal")) return;
    if (e.target?.matches?.("input,textarea,select")) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); return; }
    if (["ArrowLeft", "ArrowRight", "Home", "End", "i", "I"].includes(e.key)) e.stopPropagation();
  }
  window.addEventListener("keydown", onKey, true);

  if (v.data) { render(); schedule(0); }
}
