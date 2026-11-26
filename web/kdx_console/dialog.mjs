// KDX Wildcard Studio - small in-app dialogs (replace the browser's window.prompt / window.confirm).
//
// askText(...)    -> Promise<string | null>   (null = cancelled)
// askConfirm(...) -> Promise<boolean>
// Enter confirms (single line), Ctrl+Enter confirms (multi line), Esc or a click outside cancels.
import { ensureTheme } from "./theme.mjs?v=0.7.3";

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
