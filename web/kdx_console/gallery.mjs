// KDX Wildcard Studio - Gallery: the images KDX Wildcard Studio made, grouped by category and template, any number per
// template. Opens full window from the panel; a click on an image opens the shared KDX lightbox with what made
// it (template, seed, file, prompt). Loads on open and on ⟳ / filter change; no polling.
import { api } from "../../../scripts/api.js";
import { ACCENT, ensureTheme } from "./theme.mjs?v=0.7.3";
import { call, getSnap, toast } from "./client.mjs?v=0.7.3";
import { openLightbox } from "./lightbox.mjs?v=0.7.3";

const VIEW_KEY = "kdx_console.gallery";
const RANGES = [["1h", "last hour", 3600], ["6h", "last 6 hours", 6 * 3600], ["today", "today", 0],
  ["24h", "last 24 hours", 86400], ["7d", "last 7 days", 7 * 86400], ["all", "everything", -1], ["custom", "since …", 0]];
let win = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function loadView() {
  try { return JSON.parse(localStorage.getItem(VIEW_KEY) || "{}") || {}; } catch (_e) { return {}; }
}
function saveView(v) {
  try {
    localStorage.setItem(VIEW_KEY, JSON.stringify({ range: v.range, custom: v.custom, size: v.size, group: v.group, latest: v.latest }));
  } catch (_e) { /* fine */ }
}

export function viewUrl(it) {
  const q = new URLSearchParams({ filename: it.filename, subfolder: it.subfolder || "", type: it.type || "output" });
  return api.apiURL(`/view?${q}`);
}

function sinceOf(v) {
  if (v.range === "all") return 0;
  if (v.range === "today") { const d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime() / 1000; }
  if (v.range === "custom") { const t = Date.parse(v.custom || ""); return Number.isFinite(t) ? t / 1000 : 0; }
  const r = RANGES.find((x) => x[0] === v.range);
  return Date.now() / 1000 - (r ? r[2] : 86400);
}

const fmtTime = (t) => new Date(t * 1000).toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });

export function closeGallery() { win?.close(); }

/** Open the gallery; `opts.template` / `opts.category` start with that filter. */
export async function openGallery(opts = {}) {
  ensureTheme();
  closeGallery();
  const saved = loadView();
  const v = {
    range: saved.range || "24h", custom: saved.custom || "", size: saved.size || 220, group: saved.group || "template",
    latest: saved.latest || 0, category: opts.category || "", template: opts.template || "", text: "",
    items: [], more: false, loading: false, error: "",
  };
  const el = document.createElement("div");
  el.className = "kdx-root kdx-gal";
  document.body.appendChild(el);
  let lb = null;
  let shown = []; // images in the order the grid shows them

  const visible = () => {
    const q = v.text.trim().toLowerCase();
    let out = v.items.filter((it) => (!q || it.template.toLowerCase().includes(q) || (it.prompt || "").toLowerCase().includes(q)));
    if (v.latest > 0) {
      const per = {};
      out = out.filter((it) => (per[it.template] = (per[it.template] || 0) + 1) <= v.latest);
    }
    return out;
  };

  /** Groups in display order: category name, then template; items newest first inside. */
  function groups(list) {
    if (v.group === "time") return [["", [["", list]]]];
    const cats = new Map();
    for (const it of list) {
      const c = it.category_name || it.category || "—";
      if (!cats.has(c)) cats.set(c, new Map());
      const t = cats.get(c);
      if (!t.has(it.template)) t.set(it.template, []);
      t.get(it.template).push(it);
    }
    const order = (getSnap()?.config?.categories || []).map((c) => c.name);
    return [...cats.entries()].sort((a, b) => ((order.indexOf(a[0]) + 1 || 999) - (order.indexOf(b[0]) + 1 || 999)) || a[0].localeCompare(b[0]))
      .map(([c, t]) => [c, [...t.entries()].sort((a, b) => a[0].localeCompare(b[0]))]);
  }

  function thumb(it, i) {
    const s = v.size;
    return `<button class="kdx-gal-cell" data-i="${i}" title="${esc(`${it.template} · seed ${it.seed}\n${it.filename}`)}">
      <img loading="lazy" src="${viewUrl(it)}" style="width:${s}px;height:${s}px" alt="${esc(it.template)}">
      <span class="kdx-gal-cap">${v.group === "time" ? `<b>${esc(it.template)}</b> · ` : ""}seed ${esc(it.seed)} · ${esc(fmtTime(it.time))}</span></button>`;
  }

  function bodyHtml() {
    if (v.loading && !v.items.length) return `<p class="kdx-muted">Loading…</p>`;
    if (v.error) return `<p class="kdx-err">${esc(v.error)}</p>`;
    const list = visible();
    if (!list.length) return `<p class="kdx-muted">No KDX Wildcard Studio images ${v.range === "all" ? "" : "in this time range"}. Images carry their template only when they were saved after a KDX Wildcard Studio run.</p>`;
    const g = groups(list);
    shown = g.flatMap(([, tpls]) => tpls.flatMap(([, its]) => its)); // the viewer steps in this (grid) order
    const index = new Map(shown.map((it, i) => [it, i]));
    return g.map(([cat, tpls]) => `${cat ? `<h2 class="kdx-gal-cat">${esc(cat)}</h2>` : ""}<div class="kdx-gal-tpls">${tpls.map(([tpl, its]) => `
      <section class="kdx-gal-tpl">${tpl ? `<h3>${esc(tpl)} <span class="kdx-muted">${its.length}</span></h3>` : ""}
      <div class="kdx-gal-row">${its.map((it) => thumb(it, index.get(it))).join("")}</div></section>`).join("")}</div>`).join("");
  }

  function headHtml() {
    const cats = [...new Set(v.items.map((it) => it.category_name || it.category))].sort();
    const list = visible();
    return `<span class="kdx-gal-title">🖼️ Gallery</span>
      <span class="kdx-muted">${list.length} image${list.length === 1 ? "" : "s"} · ${new Set(list.map((x) => x.template)).size} templates${v.more ? " · more exist: narrow the time range" : ""}${v.showNsfw ? "" : " · NSFW hidden (NSFW switch in the panel)"}</span>
      <span class="kdx-sp"></span>
      <label class="kdx-row" style="gap:3px">Since <select class="kdx-sel" data-g="range">${RANGES.map(([k, t]) => `<option value="${k}" ${k === v.range ? "selected" : ""}>${t}</option>`).join("")}</select></label>
      ${v.range === "custom" ? `<input class="kdx-sel" type="datetime-local" data-g="custom" value="${esc(v.custom)}" title="Images newer than this">` : ""}
      <label class="kdx-row" style="gap:3px">Category <select class="kdx-sel" data-g="category"><option value="">all</option>
        ${cats.map((c) => `<option value="${esc(c)}" ${c === v.category ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></label>
      <input class="kdx-sel" type="search" data-g="text" placeholder="template or prompt text…" value="${esc(v.text)}" style="width:170px">
      <label class="kdx-row" style="gap:3px" title="Show only the newest N images of every template">Per template
        <select class="kdx-sel" data-g="latest">${[[0, "all"], [1, "newest 1"], [3, "newest 3"], [5, "newest 5"], [10, "newest 10"]]
          .map(([n, t]) => `<option value="${n}" ${n === v.latest ? "selected" : ""}>${t}</option>`).join("")}</select></label>
      <span class="kdx-seg"><button class="${v.group === "template" ? "on" : ""}" data-g="group" data-m="template" title="Grouped by category and template">By template</button><button
        class="${v.group === "time" ? "on" : ""}" data-g="group" data-m="time" title="All images, newest first">Newest first</button></span>
      <input type="range" min="120" max="480" step="20" value="${v.size}" data-g="size" title="Thumbnail size" style="width:90px">
      <button class="kdx-btn" data-g="reload" title="Load again">⟳</button>
      <button class="kdx-btn" data-g="close" title="Close (Esc)">✕</button>`;
  }

  function render() {
    el.innerHTML = `<div class="kdx-gal-head">${headHtml()}</div><div class="kdx-gal-body">${bodyHtml()}</div>`;
  }
  const paintBody = () => { const b = el.querySelector(".kdx-gal-body"); if (b) b.innerHTML = bodyHtml(); };
  const paintHead = () => { const h = el.querySelector(".kdx-gal-head"); if (h && !h.contains(document.activeElement)) h.innerHTML = headHtml(); };

  async function load() {
    v.loading = true;
    v.error = "";
    paintBody();
    const q = new URLSearchParams({ since: String(Math.floor(sinceOf(v))), limit: "2000" });
    const cat = (getSnap()?.config?.categories || []).find((c) => c.name === v.category);
    if (cat) q.set("category", cat.key);
    const d = await call("GET", `/kdx_console/gallery?${q}`);
    v.loading = false;
    if (!d.ok) { v.error = d.error || "could not load"; v.items = []; } else { v.items = d.items; v.more = d.more; v.showNsfw = !!d.show_nsfw; }
    if (v.category && !cat) v.items = v.items.filter((it) => (it.category_name || it.category) === v.category);
    render();
  }

  function openAt(i) {
    lb = openLightbox({
      prefix: "kdx-", accent: ACCENT.dark.acc, items: shown, index: i,
      title: (it) => `${it.category_name || it.category} › ${it.template}`,
      images: (it) => [{ src: viewUrl(it) }],
      details: (it) => [
        { label: "Template", value: it.template, copy: true },
        { label: "Category", value: it.category_name || it.category },
        { label: "Seed", value: it.seed, mono: true, copy: true },
        { label: "Image", value: it.index && it.repeat ? `${it.index} of ${it.repeat}` : "" },
        { label: "Size", value: it.width ? `${it.width} × ${it.height}` : "" },
        { label: "Made", value: new Date(it.time * 1000).toLocaleString() },
        { label: "File", value: `${it.subfolder ? `${it.subfolder}/` : ""}${it.filename}`, mono: true, copy: true },
        { label: "Prompt", value: it.prompt || "(no prompt text in this image)", long: true, copy: !!it.prompt },
      ],
      actions: () => [{ id: "pin", label: "Pin in Studio", title: "Switch the Studio to pin mode with this template and seed (exact repeat). Switch the mode back in the panel afterwards." }],
      onAction: async (id, it) => {
        if (id !== "pin") return;
        const d = await call("POST", "/kdx_console/select", { category: it.category, template: it.template, mode: "pin", pin_seed: it.seed });
        if (!d.ok) toast(d.error); else toast(`Pinned ${it.template} · seed ${it.seed}`, "success");
      },
      onClose: () => { lb = null; },
    });
  }

  el.addEventListener("click", (e) => {
    const cell = e.target.closest(".kdx-gal-cell");
    if (cell) { openAt(Number(cell.dataset.i)); return; }
    const b = e.target.closest("[data-g]");
    if (!b || b.tagName === "SELECT" || b.tagName === "INPUT") return;
    if (b.dataset.g === "close") close();
    else if (b.dataset.g === "reload") load();
    else if (b.dataset.g === "group") { v.group = b.dataset.m; saveView(v); render(); }
  });
  el.addEventListener("change", (e) => {
    const g = e.target.dataset.g;
    if (g === "range") { v.range = e.target.value; saveView(v); if (v.range !== "custom") load(); else render(); }
    else if (g === "custom") { v.custom = e.target.value; saveView(v); load(); }
    else if (g === "category") { v.category = e.target.value; load(); }
    else if (g === "latest") { v.latest = Number(e.target.value); saveView(v); render(); }
  });
  el.addEventListener("input", (e) => {
    const g = e.target.dataset.g;
    if (g === "size") { v.size = Number(e.target.value); saveView(v); paintBody(); }
    else if (g === "text") { v.text = e.target.value; paintBody(); paintHead(); }
  });
  function onKey(e) {
    if (lb || e.key !== "Escape" || e.target?.matches?.("input,textarea,select")) return;
    e.preventDefault();
    e.stopPropagation();
    close();
  }
  document.addEventListener("keydown", onKey, true);
  function close() {
    lb?.close();
    document.removeEventListener("keydown", onKey, true);
    el.remove();
    win = null;
  }
  win = { close };
  render();
  load();
}
