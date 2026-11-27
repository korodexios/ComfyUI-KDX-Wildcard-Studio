// KDX lightbox - one image viewer for every KDX pack (the same file lives in each pack; packs stay independent).
//
// Large image(s) on the left, a details panel on the right (what made the image: template, seed, file, prompt …),
// ← → to move, Esc or a click outside the image to close, a click on the image toggles 1:1 zoom, I hides the details.
// The caller describes an item; the lightbox knows nothing about where items come from.
//
//   const lb = openLightbox({
//     prefix: "kdx-",                         // CSS class prefix of the pack (kdx- Console, kdxs- Sweep)
//     accent: "#6f8dff",                      // KDX blue (dark theme)
//     light: "kdx-light",                     // class on <html> that the pack sets for a light theme
//     items, index,
//     title: (it) => "…",                     // header text
//     images: (it) => [{ src, caption }],     // one or two (compare) images
//     details: (it) => [{ label, value, mono, copy, html }],   // rows of the details panel
//     actions: (it) => [{ id, label, title, primary, href }],  // extra header buttons (before ← →)
//     onAction: (id, it, lb) => {},           // a click on an extra button (or on [data-lb-act] inside html rows)
//     onKey: (e, it, lb) => false,            // return true when the key was handled
//     onClose: () => {},
//   });
//   lb.setItems(items, index?) · lb.go(i) · lb.move(d) · lb.refresh() · lb.close() · lb.index · lb.item()

const STORE = "kdx.lightbox.info";
const injected = new Set();

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function css(p, accent, light) {
  return `
.${p}lb{position:fixed;inset:0;z-index:9700;background:rgba(8,9,11,.94);display:flex;flex-direction:column;color:#e9eaec;
 font:12px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;--lb-acc:${accent}}
.${p}lb *{box-sizing:border-box}
.${p}lb-head{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:8px 12px;flex:none}
.${p}lb-title{font-weight:600;font-size:13px;margin-right:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:50vw}
.${p}lb-count{opacity:.7;font-variant-numeric:tabular-nums}
.${p}lb-sp{flex:1}
.${p}lb-btn{appearance:none;border:1px solid #444a52;background:#24272c;color:#e9eaec;border-radius:6px;padding:3px 9px;
 font:inherit;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:4px}
.${p}lb-btn:hover{border-color:var(--lb-acc)}
.${p}lb-btn:focus-visible{outline:2px solid var(--lb-acc);outline-offset:1px}
.${p}lb-btn.on,.${p}lb-btn.primary{background:var(--lb-acc);border-color:var(--lb-acc);color:#060b1f;font-weight:600}
.${p}lb-main{flex:1;display:flex;min-height:0;gap:0}
.${p}lb-imgs{flex:1;display:flex;gap:10px;padding:0 12px 12px;min-width:0;min-height:0}
.${p}lb-imgs figure{flex:1;margin:0;display:flex;flex-direction:column;min-width:0;min-height:0;align-items:center;justify-content:center}
.${p}lb-imgs img{max-width:100%;max-height:100%;min-height:0;object-fit:contain;cursor:zoom-in;border-radius:3px}
.${p}lb-imgs figcaption{padding:4px 0 0;font-size:12px;text-align:center;opacity:.85}
.${p}lb.zoom .${p}lb-imgs{overflow:auto;display:block}
.${p}lb.zoom .${p}lb-imgs figure{display:block}
.${p}lb.zoom .${p}lb-imgs img{max-width:none;max-height:none;cursor:zoom-out}
.${p}lb-info{width:min(380px,36vw);flex:none;border-left:1px solid #33373d;padding:4px 14px 14px;overflow:auto;background:rgba(20,22,25,.9)}
.${p}lb-info dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:6px 10px}
.${p}lb-info dt{opacity:.65;white-space:nowrap}
.${p}lb-info dd{margin:0;word-break:break-word;user-select:text}
.${p}lb-info dd.mono{font-family:ui-monospace,Consolas,monospace;font-size:11px}
.${p}lb-info dd.long{grid-column:1/-1;white-space:pre-wrap;background:#15171a;border:1px solid #33373d;border-radius:6px;padding:6px 8px;
 max-height:50vh;overflow:auto}
.${p}lb-info .${p}lb-copy{margin-left:6px;padding:0 6px;font-size:11px}
.${p}lb-hint{flex:none;padding:0 12px 6px;font-size:11px;opacity:.55}
html.${light} .${p}lb{background:rgba(245,246,247,.97);color:#1d211f}
html.${light} .${p}lb-btn{background:#fff;color:#1d211f;border-color:#c9d0cb}
html.${light} .${p}lb-info{background:#fff;border-color:#c9d0cb}
html.${light} .${p}lb-info dd.long{background:#f6f7f6;border-color:#c9d0cb}
html.${light} .${p}lb-btn.on,html.${light} .${p}lb-btn.primary{color:#fff}
@media (max-width:820px){.${p}lb-main{flex-direction:column}.${p}lb-info{width:auto;max-height:40vh;border-left:0;border-top:1px solid #33373d}}
`;
}

function ensureCss(p, accent, light) {
  if (injected.has(p)) return;
  injected.add(p);
  const st = document.createElement("style");
  st.dataset.kdxLightbox = p;
  st.textContent = css(p, accent, light);
  document.head.appendChild(st);
}

function readInfo() {
  try { return localStorage.getItem(STORE) !== "0"; } catch (_e) { return true; }
}
function writeInfo(on) {
  try { localStorage.setItem(STORE, on ? "1" : "0"); } catch (_e) { /* fine */ }
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (_e) { /* old browser / no permission */ }
  const ta = document.createElement("textarea");
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (_e) { /* ignore */ }
  ta.remove();
  return ok;
}

export function openLightbox(o) {
  const p = o.prefix || "kdx-";
  ensureCss(p, o.accent || "#6f8dff", o.light || "kdx-light");
  const st = { items: o.items || [], index: Math.max(0, o.index || 0), info: readInfo(), zoom: false };
  const el = document.createElement("div");
  el.className = `${p}lb`;
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-modal", "true");
  el.tabIndex = -1;
  document.body.appendChild(el);

  const item = () => st.items[st.index];

  function detailsHtml(it) {
    const rows = (o.details?.(it) || []).filter((r) => r && (r.value !== undefined && r.value !== null && r.value !== "" || r.html));
    return `<dl>${rows.map((r, i) => {
      const val = r.html != null ? r.html : esc(r.value);
      const copy = r.copy ? `<button class="${p}lb-btn ${p}lb-copy" data-lb-copy="${i}" title="Copy">copy</button>` : "";
      if (r.long) return `<dt style="grid-column:1/-1">${esc(r.label)}${copy}</dt><dd class="long ${r.mono ? "mono" : ""}">${val}</dd>`;
      return `<dt>${esc(r.label)}</dt><dd class="${r.mono ? "mono" : ""}">${val}${copy}</dd>`;
    }).join("")}</dl>`;
  }

  function render() {
    const it = item();
    if (!it) { close(); return; }
    const imgs = o.images?.(it) || [];
    const acts = (o.actions?.(it) || []).map((a) => (a.href
      ? `<a class="${p}lb-btn" href="${esc(a.href)}" target="_blank" rel="noopener" title="${esc(a.title || "")}">${esc(a.label)}</a>`
      : `<button class="${p}lb-btn ${a.primary ? "primary" : ""} ${a.on ? "on" : ""}" data-lb-act="${esc(a.id)}" title="${esc(a.title || "")}">${esc(a.label)}</button>`)).join("");
    el.classList.toggle("zoom", st.zoom);
    el.innerHTML = `<div class="${p}lb-head">
        <span class="${p}lb-title" title="${esc(o.title?.(it) || "")}">${esc(o.title?.(it) || "")}</span>
        <span class="${p}lb-count">${st.items.length > 1 ? `${st.index + 1} / ${st.items.length}` : ""}</span>
        <span class="${p}lb-sp"></span>${acts}
        <button class="${p}lb-btn" data-lb="prev" title="Previous (←)" ${st.index <= 0 ? "disabled" : ""}>←</button>
        <button class="${p}lb-btn" data-lb="next" title="Next (→)" ${st.index >= st.items.length - 1 ? "disabled" : ""}>→</button>
        <button class="${p}lb-btn ${st.info ? "on" : ""}" data-lb="info" title="Details (I)">ⓘ</button>
        ${imgs[0]?.src ? `<a class="${p}lb-btn" href="${esc(imgs[imgs.length - 1].src)}" target="_blank" rel="noopener" title="Open the full-size image in a new tab">Full size</a>` : ""}
        <button class="${p}lb-btn" data-lb="close" title="Close (Esc or click outside the image)">✕</button></div>
      <div class="${p}lb-main"><div class="${p}lb-imgs">${imgs.map((im) => `<figure><img src="${esc(im.src)}" alt="${esc(im.caption || "")}">
        ${im.caption ? `<figcaption>${im.caption}</figcaption>` : ""}</figure>`).join("")}</div>
        ${st.info ? `<aside class="${p}lb-info">${detailsHtml(it)}</aside>` : ""}</div>
      <div class="${p}lb-hint">← → move · click the image: 1:1 zoom · I details · Esc or a click beside the image closes${o.hint ? ` · ${esc(o.hint)}` : ""}</div>`;
    preload();
  }

  function preload() {
    for (const d of [1, -1]) {
      const n = st.items[st.index + d];
      if (!n) continue;
      for (const im of o.images?.(n) || []) if (im.src) { const i = new Image(); i.src = im.src; }
    }
  }

  function go(i) {
    if (!st.items.length) return;
    st.index = Math.max(0, Math.min(st.items.length - 1, i));
    st.zoom = false;
    render();
  }
  const move = (d) => go(st.index + d);

  function close() {
    document.removeEventListener("keydown", onKey, true);
    el.remove();
    o.onClose?.();
  }

  el.addEventListener("click", async (e) => {
    const t = e.target;
    const copy = t.closest(`[data-lb-copy]`);
    if (copy) {
      const rows = (o.details?.(item()) || []).filter((r) => r && (r.value !== undefined && r.value !== null && r.value !== "" || r.html));
      const ok = await copyText(String(rows[Number(copy.dataset.lbCopy)]?.copyValue ?? rows[Number(copy.dataset.lbCopy)]?.value ?? ""));
      copy.textContent = ok ? "copied" : "copy failed";
      setTimeout(() => { copy.textContent = "copy"; }, 1200);
      return;
    }
    const act = t.closest("[data-lb-act]");
    if (act) { o.onAction?.(act.dataset.lbAct, item(), api); return; }
    const b = t.closest("[data-lb]");
    if (b) {
      const a = b.dataset.lb;
      if (a === "prev") move(-1);
      else if (a === "next") move(1);
      else if (a === "info") { st.info = !st.info; writeInfo(st.info); render(); }
      else if (a === "close") close();
      return;
    }
    if (t.tagName === "IMG" && t.closest(`.${p}lb-imgs`)) { st.zoom = !st.zoom; render(); return; }
    // a click on nothing in particular (background, beside the image) closes; links, text and the details stay
    if (t.closest(`a,input,select,textarea,.${p}lb-info,.${p}lb-imgs figcaption,.${p}lb-hint`)) return;
    if (t.closest(`.${p}lb-head`) && t !== el.querySelector(`.${p}lb-head`)) return;
    close();
  });

  function onKey(e) {
    if (!el.isConnected) return;
    if (e.target?.matches?.("input,textarea,select")) return;
    if (o.onKey?.(e, item(), api)) { e.preventDefault(); e.stopPropagation(); return; }
    const k = e.key;
    let done = true;
    if (k === "ArrowLeft") move(-1);
    else if (k === "ArrowRight") move(1);
    else if (k === "Home") go(0);
    else if (k === "End") go(st.items.length - 1);
    else if (k === "Escape") { if (st.zoom) { st.zoom = false; render(); } else close(); }
    else if (k === "i" || k === "I") { st.info = !st.info; writeInfo(st.info); render(); }
    else done = false;
    if (done) { e.preventDefault(); e.stopPropagation(); }
  }
  document.addEventListener("keydown", onKey, true);

  const api = {
    el,
    get index() { return st.index; },
    item,
    go,
    move,
    refresh: render,
    close,
    setItems(items, index) {
      st.items = items || [];
      if (index != null) st.index = index;
      if (!st.items.length) { close(); return; }
      st.index = Math.max(0, Math.min(st.items.length - 1, st.index));
      render();
    },
  };
  render();
  el.focus({ preventScroll: true });
  return api;
}
