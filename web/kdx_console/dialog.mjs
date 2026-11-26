// KDX Wildcard Studio - small in-app dialogs (replace the browser's window.prompt / window.confirm).
//
// askText(...)    -> Promise<string | null>   (null = cancelled)
// askConfirm(...) -> Promise<boolean>
// askPick(...)    -> Promise<id | null>      (choose a target, see what it holds now)
// Enter confirms (single line), Ctrl+Enter confirms (multi line), Esc or a click outside cancels.
import { ensureTheme } from "./theme.mjs?v=0.7.9";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function open({ title, text = "", field = null, okLabel = "OK", danger = false }) {
  ensureTheme();
  return new Promise((resolve) => {
    const prev = document.activeElement;
    const wrap = document.createElement("div");
    wrap.className = "kdx-root kdx-modal";
    const input = field
      ? (field.multiline
        ? `<textarea class="kdx-field" rows="${field.rows || 4}" spellcheck="false" placeholder="${esc(field.placeholder)}">${esc(field.value)}</textarea>`
        : `<input class="kdx-field" type="text" spellcheck="false" placeholder="${esc(field.placeholder)}" value="${esc(field.value)}">`)
      : "";
    wrap.innerHTML = `<div class="kdx-modal-box" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <div class="kdx-modal-title">${esc(title)}</div>
      ${text ? `<div class="kdx-modal-text">${esc(text)}</div>` : ""}${input}
      <div class="kdx-row kdx-modal-btns"><span class="kdx-sp"></span>
        <button class="kdx-btn" data-no>Cancel</button>
        <button class="kdx-btn ${danger ? "kdx-danger" : "kdx-primary"}" data-ok>${esc(okLabel)}</button></div></div>`;
    document.body.appendChild(wrap);
    const el = wrap.querySelector(".kdx-field");
    let done = false;
    const close = (value) => {
      if (done) return;
      done = true;
      wrap.remove();
      try { prev?.focus?.(); } catch (_e) { /* gone */ }
      resolve(value);
    };
    const ok = () => close(field ? el.value : true);
    const no = () => close(field ? null : false);
    wrap.querySelector("[data-ok]").addEventListener("click", ok);
    wrap.querySelector("[data-no]").addEventListener("click", no);
    wrap.addEventListener("pointerdown", (e) => { if (e.target === wrap) no(); });
    wrap.addEventListener("keydown", (e) => {
      e.stopPropagation(); // ComfyUI shortcuts (Ctrl+Enter = queue!) must not fire behind the dialog
      if (e.key === "Escape") { e.preventDefault(); no(); }
      else if (e.key === "Enter" && (!field?.multiline || e.ctrlKey || e.metaKey)) { e.preventDefault(); ok(); }
    });
    (el || wrap.querySelector("[data-ok]")).focus();
    if (el?.select) el.select();
  });
}

export function askText({ title, text, value = "", placeholder = "", multiline = false, rows = 4, okLabel = "OK" }) {
  return open({ title, text, field: { value, placeholder, multiline, rows }, okLabel });
}

export function askConfirm({ title, text, okLabel = "OK", danger = false }) {
  return open({ title, text, okLabel, danger });
}

/**
 * Choose one of several places and see what is in it before it is replaced.
 * options: [{id, label, note?, current?}]; `current` is shown read-only under the list ("Now in it").
 * okLabel(option) gives the button text for the chosen option. Resolves to the chosen id or null.
 */
export function askPick({ title, text = "", options, value, okLabel = () => "OK" }) {
  ensureTheme();
  return new Promise((resolve) => {
    const prev = document.activeElement;
    let cur = options.find((o) => o.id === value) || options[0];
    const wrap = document.createElement("div");
    wrap.className = "kdx-root kdx-modal";
    wrap.innerHTML = `<div class="kdx-modal-box" role="dialog" aria-modal="true" aria-label="${esc(title)}" style="width:min(560px,100%)">
      <div class="kdx-modal-title">${esc(title)}</div>
      ${text ? `<div class="kdx-modal-text">${esc(text)}</div>` : ""}
      <div style="display:flex;flex-direction:column;gap:6px">${options.map((o) => `<label class="kdx-row" style="align-items:flex-start;gap:6px;cursor:pointer">
        <input type="radio" name="kdx-pick" value="${esc(o.id)}" ${o === cur ? "checked" : ""} style="margin-top:2px">
        <span><b>${esc(o.label)}</b>${o.note ? `<br><span class="kdx-warn">${esc(o.note)}</span>` : ""}</span></label>`).join("")}</div>
      <div data-now></div>
      <div class="kdx-row kdx-modal-btns"><span class="kdx-sp"></span>
        <button class="kdx-btn" data-no>Cancel</button><button class="kdx-btn kdx-primary" data-ok></button></div></div>`;
    document.body.appendChild(wrap);
    const paint = () => {
      const now = String(cur.current ?? "");
      wrap.querySelector("[data-now]").innerHTML = now.trim()
        ? `<div class="kdx-muted">Now in it (will be replaced):</div><textarea class="kdx-field" rows="5" readonly spellcheck="false">${esc(now)}</textarea>`
        : `<div class="kdx-muted">It is empty now.</div>`;
      wrap.querySelector("[data-ok]").textContent = okLabel(cur);
    };
    paint();
    let done = false;
    const close = (val) => {
      if (done) return;
      done = true;
      wrap.remove();
      try { prev?.focus?.(); } catch (_e) { /* gone */ }
      resolve(val);
    };
    wrap.addEventListener("change", (e) => {
      if (e.target.name !== "kdx-pick") return;
      cur = options.find((o) => o.id === e.target.value) || cur;
      paint();
    });
    wrap.querySelector("[data-ok]").addEventListener("click", () => close(cur.id));
    wrap.querySelector("[data-no]").addEventListener("click", () => close(null));
    wrap.addEventListener("pointerdown", (e) => { if (e.target === wrap) close(null); });
    wrap.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Escape") { e.preventDefault(); close(null); }
      else if (e.key === "Enter" && !e.target.matches("textarea")) { e.preventDefault(); close(cur.id); }
    });
    wrap.querySelector("[data-ok]").focus();
  });
}
