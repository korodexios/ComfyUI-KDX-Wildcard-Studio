// KDX Wildcard Studio - small node body + floating gear window.
//
// Rules: nothing serialized is written during a Run
// or while a workflow loads. The only writes are the user's own clicks: "Clear pin" clears the
// hidden `pin` widget, the panel's per-workflow settings fill the hidden `scope` widget.
// The body only renders server state.
import { getSnap, onRun, subscribe } from "./client.mjs?v=0.7.2";
import { mountPanel } from "./panel.mjs?v=0.7.2";
import { ensureTheme } from "./theme.mjs?v=0.7.2";

const BODY_H = 74;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ------------------------------------------------------------------ gear window
let floatEl = null;
let floatUnmount = null;

export function openWindow(anchor) {
  ensureTheme();
  if (floatEl) { closeWindow(); return; }
  const w = document.createElement("div");
  w.className = "kdx-root kdx-float";
  const r = anchor?.getBoundingClientRect?.();
  const left = Math.max(16, Math.min((r ? r.right + 8 : 80), window.innerWidth - 446));
  const top = Math.max(16, Math.min((r ? r.top : 80), window.innerHeight - 200));
  Object.assign(w.style, { left: `${left}px`, top: `${top}px` });
  w.innerHTML = `<div class="kdx-float-head"><span>⚙ KDX Wildcard Studio</span><span class="kdx-sp" style="flex:1"></span>
    <button class="kdx-btn" data-close title="Close">✕</button></div><div class="kdx-float-body"></div>`;
  document.body.appendChild(w);
  floatEl = w;
  floatUnmount = mountPanel(w.querySelector(".kdx-float-body"));
  w.querySelector("[data-close]").addEventListener("click", closeWindow);
  const head = w.querySelector(".kdx-float-head");
  head.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button")) return;
    const sx = e.clientX - w.offsetLeft;
    const sy = e.clientY - w.offsetTop;
    const move = (ev) => {
      w.style.left = `${Math.max(0, Math.min(ev.clientX - sx, window.innerWidth - 60))}px`;
      w.style.top = `${Math.max(0, Math.min(ev.clientY - sy, window.innerHeight - 40))}px`;
    };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
}

export function closeWindow() {
  floatUnmount?.();
  floatEl?.remove();
  floatEl = null;
  floatUnmount = null;
}

// ------------------------------------------------------------------ node body
function pinWidget(node) {
  return node.widgets?.find((w) => w.name === "pin");
}

function hideWidget(w) {
  if (!w) return;
  w.hidden = true;
  if (!w.options) w.options = {};
  w.options.hidden = true;
  w.computeSize = () => [0, -4];
}

function pinInfo(node) {
  const v = pinWidget(node)?.value;
  if (!v || !String(v).trim()) return null;
  try { return JSON.parse(v); } catch (_e) { return { template: "?", seed: "?" }; }
}

function renderBody(node, root, s) {
  if (!root.isConnected && root.dataset.mounted) return; // a copy that never reached a canvas
  const pin = pinInfo(node);
  const st = s?.state || {};
  const next = (s?.preview?.upcoming || [])[0];
  let line;
  const userOn = node.widgets?.find((w) => w.name === "use_user_text")?.value === true;
  if (pin?.user) line = `📌 <b>user prompt</b> · seed ${esc(pin.seed)} <span class="kdx-muted">(from image)</span>`;
  else if (pin) line = `📌 <b>${esc(pin.template)}</b> · seed ${esc(pin.seed)} <span class="kdx-muted">(from image)</span>`;
  else if (userOn) line = `✍ <b>user text</b> <span class="kdx-muted">· the template counter waits</span>`;
  else if (!s) line = `<span class="kdx-muted">Loading…</span>`;
  else if (st.stopped) line = `<span class="kdx-ok">✅ finished (on_end = stop)</span> <span class="kdx-muted">· Skip or Reset to go on</span>`;
  else if (s.preview?.error) line = `<span class="kdx-err">${esc(s.preview.error)}</span>`;
  else if (next) {
    const pos = next.mode === "sequential" ? `${next.index}/${next.repeat}` : next.mode;
    line = `▶ <b>${esc(next.category_name)} › ${esc(next.template)}</b> · ${esc(pos)}`;
  } else line = `<span class="kdx-muted">—</span>`;
  const own = s?.channel && s.channel !== "main" ? " · this workflow" : "";
  const last = (st.last ? `${esc(st.last.template)} #${st.last.index} · ${st.runs} runs` : `${st.runs ?? 0} runs`) + own;
  root.innerHTML = `<div class="kdx-line">${line}</div>
    <div class="kdx-row"><span class="kdx-muted kdx-line">${pin ? "Pin: exact reproduction, counter paused" : `Last: ${last}`}</span>
      ${pin ? '<button class="kdx-btn" data-unpin title="Return the node to normal mode">Clear pin</button>' : ""}
      <button class="kdx-btn kdx-gear" data-gear title="KDX Wildcard Studio settings">⚙</button></div>`;
}

export function setupNode(node) {
  ensureTheme();
  hideWidget(pinWidget(node));
  hideWidget(node.widgets?.find((w) => w.name === "scope"));
  const sw = node.widgets?.find((w) => w.name === "use_user_text");
  if (sw) { const cb = sw.callback; sw.callback = function (...a) { const r = cb?.apply(this, a); node._kdxRender?.(); return r; }; }
  const root = document.createElement("div");
  root.className = "kdx-root kdx-node";
  const widget = node.addDOMWidget("kdx_console_ui", "kdx_console", root, {
    serialize: false, // the DOM body owns no state; widgets_values stays [pin, scope, user_text, use_user_text]
    getValue: () => undefined,
    setValue: () => {},
    getMinHeight: () => BODY_H,
    getMaxHeight: () => BODY_H,
    margin: 4,
  });
  // LiteGraph reads `widget.serialize`, not the option: without it the body adds a third value to
  // widgets_values, and the frontend then ignores all of them on load (the `scope` was lost on a tab switch).
  widget.serialize = false;
  root.dataset.mounted = "";
  requestAnimationFrame(() => { if (root.isConnected) root.dataset.mounted = "1"; });

  root.addEventListener("click", (e) => {
    if (e.target.closest("[data-gear]")) openWindow(e.target.closest("[data-gear]"));
    else if (e.target.closest("[data-unpin]")) {
      const w = pinWidget(node);
      if (w) {
        w.value = "";
        w.callback?.("");
        node.setDirtyCanvas?.(true, true);
        node.graph?.change?.();
      }
      renderBody(node, root, getSnap());
    }
  });
  // Stop canvas drag/zoom from stealing clicks inside the body.
  root.addEventListener("pointerdown", (e) => { if (e.target.closest("button")) e.stopPropagation(); });

  const unsub = subscribe((s) => renderBody(node, root, s));
  const unRun = onRun(() => {
    if (!root.isConnected) return;
    root.classList.remove("kdx-flash");
    void root.offsetWidth;
    root.classList.add("kdx-flash");
  });
  node._kdxRender = () => renderBody(node, root, getSnap());
  const prevRemoved = node.onRemoved;
  node.onRemoved = function (...a) {
    unsub();
    unRun();
    return prevRemoved?.apply(this, a);
  };
  renderBody(node, root, getSnap());
  return widget;
}
