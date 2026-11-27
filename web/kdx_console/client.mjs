// KDX Wildcard Studio - data layer shared by the sidebar tab, the node body and the gear window.
//
// One snapshot from the server ({config, state, preview, warnings}); the server is the
// only source of truth. Updates arrive as `kdx_console.state` events (send_sync), so
// there is NO polling: one GET when the first view opens and after a reconnect.
import { api } from "../../../scripts/api.js";
import { app } from "../../../scripts/app.js";

const subs = new Set();
const runSubs = new Set();
let snap = null;
let inflight = null;
let again = false;

export const getSnap = () => snap;

// ------------------------------------------------------------------ per-workflow scope
// A workflow may keep its own on/off and counter. They live in the hidden `scope` widget of the
// Studio node(s) of the open workflow, so they are saved with the workflow. Written only by the
// user's clicks in the panel; empty = the shared settings.
const SCOPE_WIDGET = "scope";

export function consoleNodes() {
  const g = app.graph;
  if (!g) return [];
  const nodes = (g._nodes || g.nodes || []).filter((n) => n.type === "KDX_Console");
  return nodes.filter((n) => n.widgets?.some((w) => w.name === SCOPE_WIDGET));
}

/** Scope of the open workflow: {channel, set} or null (shared). */
export function getScope() {
  const w = consoleNodes()[0]?.widgets.find((x) => x.name === SCOPE_WIDGET);
  const v = String(w?.value ?? "").trim();
  if (!v) return null;
  try {
    const o = JSON.parse(v);
    return o && typeof o === "object" ? { channel: String(o.channel || "main"), set: { ...(o.set || {}) } } : null;
  } catch (_e) { return null; }
}

const scopeText = () => {
  const s = getScope();
  return s ? JSON.stringify(s) : "";
};

/** Write the scope into every Studio node of the open workflow (null = shared) and reload. */
export function setScope(scope) {
  const text = scope ? JSON.stringify({ channel: scope.channel, set: scope.set || {} }) : "";
  for (const n of consoleNodes()) {
    const w = n.widgets.find((x) => x.name === SCOPE_WIDGET);
    if (!w || w.value === text) continue;
    w.value = text;
    w.callback?.(text);
    n.setDirtyCanvas?.(true, true);
  }
  app.graph?.change?.();
  try { app.extensionManager?.workflow?.activeWorkflow?.changeTracker?.checkState?.(); } catch (_e) { /* older frontend */ }
  refresh();
}

export const newChannel = () => `w_${Math.random().toString(36).slice(2, 10)}`;

function publish(s) {
  snap = s;
  for (const fn of subs) {
    try { fn(s); } catch (e) { console.error("[KDX Wildcard Studio]", e); }
  }
}

export function subscribe(fn) {
  subs.add(fn);
  if (snap) fn(snap);
  else refresh();
  return () => subs.delete(fn);
}

export function onRun(fn) {
  runSubs.add(fn);
  return () => runSubs.delete(fn);
}

export async function call(method, path, body) {
  let res;
  try {
    res = await api.fetchApi(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    return { ok: false, error: String(e) };
  }
  try { return await res.json(); } catch (_e) { return { ok: false, error: `HTTP ${res.status}` }; }
}

export function refresh() {
  if (inflight) { again = true; return inflight; } // the open request may carry an old scope: ask once more
  const sc = scopeText();
  inflight = call("GET", `/kdx_console/state${sc ? `?scope=${encodeURIComponent(sc)}` : ""}`)
    .then((d) => { if (d.ok) publish(d); else toast(d.error); return d; })
    .finally(() => {
      inflight = null;
      if (again) { again = false; refresh(); }
    });
  return inflight;
}

export function toast(detail, severity = "error") {
  if (!detail) return;
  const t = app.extensionManager?.toast;
  if (t?.add) t.add({ severity, summary: "KDX Wildcard Studio", detail: String(detail), life: severity === "error" ? 6000 : 2500 });
  else console.warn("[KDX Wildcard Studio]", detail);
}

/** POST an action; the snapshot in the reply is shown at once (the event follows anyway). */
export async function action(path, body = {}) {
  const sc = scopeText();
  const d = await call("POST", path, sc ? { ...body, scope: sc } : body);
  if (!d.ok) toast(d.error);
  else if (d.state && d.config) publish(d);
  return d;
}

let saveTimer = null;
let pendingCfg = null;

/** Optimistic config edit: change a copy, show it now, save after a short pause. */
export function editConfig(mutator, delay = 250) {
  if (!snap) return;
  const cfg = structuredClone(pendingCfg || snap.config);
  mutator(cfg);
  pendingCfg = cfg;
  publish({ ...snap, config: cfg });
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    const body = pendingCfg;
    pendingCfg = null;
    const d = await call("POST", "/kdx_console/config", { config: body });
    if (!d.ok) { toast(d.error); refresh(); }
    else if (d.warnings?.length) toast(d.warnings.join("\n"), "warn");
  }, delay);
}

/** Expanded prompt for the next run (on demand only, never on a timer). */
export async function previewPrompt(count = 5) {
  const sc = scopeText();
  const d = await call("GET", `/kdx_console/preview?expand=1&count=${count}${sc ? `&scope=${encodeURIComponent(sc)}` : ""}`);
  return d.ok ? d.preview : { upcoming: [], error: d.error };
}

// ------------------------------------------------------------------ per-prompt template pick
// The selected template lives in one server-side state that a queued prompt reads only when it
// RUNS. Clicking "▶ Use" on A, Run, "▶ Use" on B, Run would therefore render B twice. So the
// "▶" click is attached to the prompt queued by the NEXT Run as `overrides = select=<cat>.<tpl>`:
// every prompt keeps the template that was picked when Run was pressed (one image, counter untouched).
//
// Two hooks, both only reading/editing the API copy of the prompt (never the graph or workflow):
//   * app.queuePrompt  - runs at the moment of the Run press: takes the pending pick (FIFO entry);
//   * api.queuePrompt  - runs later, once per prompt, in the same order: attaches that entry's pick.
// (The frontend builds and sends prompts asynchronously, so the pick cannot be read at send time.)
// Nothing is attached for a wired `overrides`, a pinned image or pin mode.
let pendingPick = null;
const pickQueue = []; // {pick, left, at}: one per app.queuePrompt call, consumed by api.queuePrompt
const PICK_TTL_MS = 120000; // an entry whose prompt never reached the server (graph error) must not linger

export function setPick(category, template) { pendingPick = { category, template }; }

function attachPick(data, pick) {
  if (!pick || !data?.output) return;
  const text = `select=${pick.category}.${pick.template}`;
  if (/[,;\n]/.test(text) || snap?.config?.mode === "pin") return; // not expressible / pin mode keeps its seed
  for (const n of Object.values(data.output)) {
    if (n?.class_type !== "KDX_Console") continue;
    n.inputs = n.inputs || {};
    if (n.inputs.overrides !== undefined) continue; // wired by the user
    if (String(n.inputs.pin || "").trim()) continue; // exact reproduction of an image
    n.inputs.overrides = text;
  }
}

function takeEntryPick() {
  const now = Date.now();
  while (pickQueue.length && now - pickQueue[0].at > PICK_TTL_MS) pickQueue.shift();
  const e = pickQueue[0];
  if (!e) return null;
  const pick = e.left === e.total ? e.pick : null; // a batch: only its first prompt carries the pick
  if (--e.left <= 0) pickQueue.shift();
  return pick;
}

if (!app.__kdxQueueHook && typeof app.queuePrompt === "function" && typeof api.queuePrompt === "function") {
  const origApp = app.queuePrompt;
  app.queuePrompt = function (number, batchCount, ...rest) {
    const total = Number(batchCount) > 0 ? Math.floor(Number(batchCount)) : 1;
    pickQueue.push({ pick: pendingPick, left: total, total, at: Date.now() });
    pendingPick = null; // one click = one Run
    return origApp.call(this, number, batchCount, ...rest);
  };
  const origApi = api.queuePrompt;
  api.queuePrompt = function (number, data, ...rest) {
    try { attachPick(data, takeEntryPick()); } catch (e) { console.error("[KDX Wildcard Studio]", e); }
    return origApi.call(this, number, data, ...rest);
  };
  app.__kdxQueueHook = true;
}

// The event carries the shared counter; a workflow with its own scope asks for its own snapshot.
api.addEventListener("kdx_console.state", (e) => {
  if (pendingCfg) return;
  if (scopeText()) { if (subs.size) refresh(); } else publish({ ok: true, ...e.detail });
});
// Another workflow opened (tab switch, load): show its scope.
if (!app.__kdxLoadHook && typeof app.loadGraphData === "function") {
  const origLoad = app.loadGraphData;
  app.loadGraphData = async function (...a) {
    const r = await origLoad.apply(this, a);
    try { if (subs.size) refresh(); } catch (_e) { /* view gone */ }
    return r;
  };
  app.__kdxLoadHook = true;
}
// The frontend's auto-queue setting (Run / Run (On Change) / Run (Instant)), or null on an older frontend.
function queueSettings() {
  try {
    const pinia = document.getElementById("vue-app")?.__vue_app__?.config?.globalProperties?.$pinia;
    const s = pinia?._s?.get("queueSettingsStore");
    return s && typeof s.mode === "string" ? s : null;
  } catch (_e) { return null; }
}

// A queued run hit a finished category (on_end = stop): nothing was rendered, and that is not an error.
// ComfyUI stops its auto-queue only on an error, and "On Change" re-queues whenever a widget changes
// (a randomized seed changes after every run), so it would loop at full speed: switch auto-queue off.
api.addEventListener("kdx_console.finished", (e) => {
  const msg = e.detail?.message || "KDX Wildcard Studio: finished";
  const qs = queueSettings();
  if (qs && qs.mode !== "disabled") {
    const was = qs.mode === "change" ? "Run (On Change)" : `Run (${qs.mode})`;
    qs.mode = "disabled";
    toast(`${msg} ${was} was switched off.`, "info");
  } else toast(msg, "info");
});
api.addEventListener("kdx_console.run", (e) => {
  for (const fn of runSubs) { try { fn(e.detail); } catch (_e) { /* view gone */ } }
});
api.addEventListener("reconnected", () => { if (subs.size) refresh(); });
