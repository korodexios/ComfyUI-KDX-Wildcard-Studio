// KDX Wildcard Studio - the settings panel (sidebar tab and gear window render the same thing).
//
// Everything shown comes from the server snapshot; every change goes back over REST and
// the server's event repaints all open views. No timers, no polling.
import { action, call, consoleNodes, editConfig, getScope, getSnap, newChannel, previewPrompt, setPick, setScope, subscribe,
  toast } from "./client.mjs?v=0.7.6";
import { askConfirm, askText } from "./dialog.mjs?v=0.7.6";
import { ensureTheme } from "./theme.mjs?v=0.7.6";

const MODES = [["sequential", "Sequential"], ["manual", "Manual"], ["pin", "Pin"]];
const ON_END = [["next", "next category"], ["loop", "loop category"], ["stop", "stop"]];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let profilesCache = null;
async function loadProfiles() {
  if (profilesCache) return profilesCache;
  const d = await call("GET", "/kdx_console/profiles");
  profilesCache = d.ok ? d.profiles : [];
  return profilesCache;
}

/** Same rule as the server's `slug()`: the category key used by overrides. */
function slugKey(text) {
  const s = String(text || "").normalize("NFKD").replace(/[^\x00-\x7f]/g, "").trim().toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "");
  return s || "category";
}

/** Small icon button (move / rename / remove). */
const ico = (act, label, title, extra = "") =>
  `<button class="kdx-go kdx-ico" data-act="${act}" ${extra} title="${esc(title)}">${label}</button>`;

/** Move item `i` of `arr` by `d` (-1 / +1); no-op at the ends. */
function moveItem(arr, i, d) {
  const j = i + d;
  if (!arr || j < 0 || j >= arr.length) return;
  [arr[i], arr[j]] = [arr[j], arr[i]];
}

/** On/off as this workflow sees it: its own value when it has one, else the shared one. */
function eff(scope, key, shared) {
  return scope && key in scope.set ? scope.set[key] : shared;
}

/** Shared vs. this-workflow switch (only when the open workflow has a Studio node). */
function scopeCard(scope) {
  if (!consoleNodes().length) return "";
  const n = scope ? Object.keys(scope.set).length : 0;
  const seg = `<span class="kdx-seg"><button data-act="scope" data-on="0" class="${scope ? "" : "on"}"
      title="On/off and the counter are shared by every workflow">Shared</button><button data-act="scope" data-on="1"
      class="${scope ? "on" : ""}" title="On/off and the counter only for this workflow (saved with the workflow)">This workflow</button></span>`;
  const info = scope
    ? `<span class="kdx-muted">own on/off and counter · ${n ? `${n} different from shared` : "same as shared"}</span>
       ${n ? '<button class="kdx-btn" data-act="scope_clear" title="Use the shared on/off again (keeps this workflow\'s counter)">Same as shared</button>' : ""}`
    : `<span class="kdx-muted">clicks change every workflow</span>`;
  return `<div class="kdx-card"><div class="kdx-row"><span class="kdx-muted">On/off for:</span> ${seg}</div>
    <div class="kdx-row">${info}</div></div>`;
}

function nowCard(s) {
  const st = s.state || {};
  const pv = s.preview || {};
  const next = (pv.upcoming || [])[0];
  const cfg = s.config;
  let head;
  if (st.stopped) head = `<div class="kdx-ok">✅ ${esc(st.message)}</div>`;
  else if (pv.error) head = `<div class="kdx-err">${esc(pv.error)}</div>`;
  else if (next) {
    const pos = next.mode === "sequential" ? `${next.index}/${next.repeat}` : next.mode;
    head = `<div>Next image: <b>${esc(next.category_name)} › ${esc(next.template)}</b> · ${esc(pos)}`
      + ` · seed ${next.seed ?? "?"}</div>`;
  } else head = `<div class="kdx-muted">Nothing planned.</div>`;
  const last = st.last;
  const lastLine = last
    ? `<div class="kdx-muted">Last image: ${esc(last.category_name)} › ${esc(last.template)} #${last.index} · seed ${last.seed}</div>`
    : "";
  const warns = (s.warnings || []).map((w) => `<div class="kdx-warn">⚠ ${esc(w)}</div>`).join("");
  return `<div class="kdx-card kdx-now">${head}${lastLine}
    <div class="kdx-muted">Runs: ${st.runs ?? 0} · mode ${esc(cfg.mode)}${cfg.llm_enabled ? " · LLM on" : ""}</div>${warns}
    <div class="kdx-row" style="margin-top:6px">
      <button class="kdx-btn kdx-primary" data-act="skip" title="Jump to the next template (when stopped: resume)">⏭ Skip</button>
      <button class="kdx-btn" data-act="reset" title="Restart the counter">↺ Reset</button>
      <button class="kdx-btn" data-act="gallery" title="All images made by KDX Wildcard Studio, by category and template, with seed and prompt">🖼️ Gallery</button>
      <button class="kdx-btn" data-act="builder" title="Build a template from bubbles: drag in pools, your own text and groups; live preview and rule checks">🧱 Builder</button>
      <button class="kdx-btn" data-act="packs" title="Share templates with the pools they use as one .zip, or install a pack from someone else">📦 Packs</button>
      <span class="kdx-sp"></span>
      <button class="kdx-btn" data-act="cat_new" title="Create an empty category; add templates to it afterwards">＋ New category</button>
      <button class="kdx-btn" data-act="import" title="Add new templates from templates/ in the wildcard folders (no NSFW)">⇣ Import templates</button>
    </div>${(cfg.ignored || []).length
      ? `<div class="kdx-muted">${cfg.ignored.length} removed template${cfg.ignored.length === 1 ? "" : "s"} skipped by Import.
         <button class="kdx-btn" data-act="restore" title="Forget the removed list and import everything again">Restore all</button></div>` : ""}</div>`;
}

/** "Images per template" for many templates at once: writes `repeat` into each of them. */
function bulkRepeat(templates, scope, label) {
  const vals = new Set(templates.map((t) => t.repeat));
  const same = vals.size === 1 ? [...vals][0] : "";
  return `<div class="kdx-row"><span class="kdx-muted">${label}</span>
    <input class="kdx-rep" type="text" inputmode="numeric" autocomplete="off" spellcheck="false" data-min="1" value="${same}" placeholder="${templates.length ? "–" : ""}"
      data-bulk="${scope}" title="Images per template (– = they differ). Enter or Set applies it to every template here">
    <button class="kdx-btn" data-act="bulk" data-scope="${scope}" title="Set repeat of every template here">Set</button></div>`;
}

function modeCard(s) {
  const cfg = s.config;
  const seg = MODES.map(([m, label]) => `<button data-act="mode" data-mode="${m}" class="${cfg.mode === m ? "on" : ""}">${label}</button>`).join("");
  const sel = cfg.select ? `${cfg.select.category}.${cfg.select.template}` : "—";
  const extra = cfg.mode === "sequential" ? ""
    : `<div class="kdx-row"><span class="kdx-muted">Selected template:</span> <b>${esc(sel)}</b>
       <span class="kdx-muted">(“▶ Use” next to a template selects it)</span></div>`
      + (cfg.mode === "pin"
        ? `<div class="kdx-row"><label class="kdx-muted">Pin seed</label>
           <input class="kdx-rep kdx-num" type="text" inputmode="numeric" autocomplete="off" spellcheck="false" data-min="0" data-act="pin_seed" value="${cfg.pin_seed ?? ""}"></div>`
        : "");
  return `<div class="kdx-card kdx-cat"><div class="kdx-row"><span class="kdx-seg">${seg}</span><span class="kdx-sp"></span>
    <button class="kdx-pill ${cfg.llm_enabled ? "on" : ""}" data-act="llm" title="LLM on/off for KDX-LLM Chat. Templates send the system prompt of their category, your own prompt the one picked on the node">LLM</button>
    <button class="kdx-pill ${cfg.show_nsfw ? "on" : ""}" data-act="nsfw" title="Show NSFW templates (a word of the name starts with nsfw, akt or sheer) in Add template, Import and the Gallery">NSFW</button></div>${extra}
    ${bulkRepeat(cfg.categories.flatMap((c) => c.templates), "all", "Images per template, all:")}</div>`;
}

function catCard(cat, ci, s, profiles, avail, scope) {
  const st = s.state || {};
  const catOn = eff(scope, cat.key, cat.enabled);
  const catOwn = scope && cat.key in scope.set;
  const nCats = s.config.categories.length;
  const next = (s.preview?.upcoming || [])[0];
  const fixed = s.config.mode !== "sequential";
  const tpls = cat.templates.map((t, ti) => {
    const cur = next && next.category === cat.key && next.template === t.name;
    const was = st.last && st.last.category === cat.key && st.last.template === t.name;
    const picked = fixed && s.config.select?.category === cat.key && s.config.select?.template === t.name;
    const go = picked ? "✓ Selected" : fixed ? "▶ Use" : "▶ Start";
    const tKey = `${cat.key}.${t.name}`;
    const tOn = eff(scope, tKey, t.enabled);
    const tOwn = scope && tKey in scope.set;
    const goTitle = fixed ? "Generate only this template (manual / pin)" : "Continue the sequence from this template";
    return `<span class="kdx-tpl">
      <button class="kdx-pill ${tOn ? "on" : ""} ${cur ? "cur" : ""} ${was ? "last" : ""} ${tOwn ? "own" : ""}" data-act="tpl" data-ci="${ci}" data-ti="${ti}"
        title="${(cur ? "Outlined: the NEXT image uses it. " : "") + (was ? "Dot: the last image was made with it. " : "")}${tOn ? "Enabled" : "Disabled"}${tOwn ? " in this workflow only" : ""} – click to toggle">${esc(t.name)}</button>
      <input class="kdx-rep" type="text" inputmode="numeric" autocomplete="off" spellcheck="false" data-min="1" value="${t.repeat}" data-act="repeat" data-ci="${ci}" data-ti="${ti}" title="repeat: images per template">
      <button class="kdx-go ${picked ? "on" : ""}" data-act="select" data-ci="${ci}" data-ti="${ti}" title="${goTitle}">${go}</button>
      ${ti > 0 ? ico("tpl_move", "‹", "Move earlier", `data-ci="${ci}" data-ti="${ti}" data-d="-1"`) : ""}
      ${ti < cat.templates.length - 1 ? ico("tpl_move", "›", "Move later", `data-ci="${ci}" data-ti="${ti}" data-d="1"`) : ""}
      ${ico("tpl_del", "✕", "Remove from this category (the file stays; Import will not bring it back)", `data-ci="${ci}" data-ti="${ti}"`)}
    </span>`;
  }).join("");
  const onEnd = ON_END.map(([v, l]) => `<option value="${v}" ${cat.on_end === v ? "selected" : ""}>${l}</option>`).join("");
  const profs = ["", ...profiles];
  if (cat.system_prompt && !profiles.includes(cat.system_prompt)) profs.push(cat.system_prompt);
  const sp = profs.map((p) => `<option value="${esc(p)}" ${cat.system_prompt === p ? "selected" : ""}>${p ? esc(p) : "— no system prompt —"}</option>`).join("");
  const isCurCat = st.category === cat.key;
  return `<div class="kdx-card kdx-cat ${catOn ? "" : "off"}">
    <div class="kdx-row">
      <button class="kdx-pill ${catOn ? "on" : ""} ${catOwn ? "own" : ""}" data-act="cat" data-ci="${ci}"
        title="Category ${esc(cat.key)}${catOwn ? " – this workflow only" : ""}">${esc(cat.name)}</button>
      <span class="kdx-muted">${esc(cat.key)}${isCurCat ? " · current" : ""}</span><span class="kdx-sp"></span>
      ${ci > 0 ? ico("cat_move", "▲", "Move category up", `data-ci="${ci}" data-d="-1"`) : ""}
      ${ci < nCats - 1 ? ico("cat_move", "▼", "Move category down", `data-ci="${ci}" data-d="1"`) : ""}
      ${ico("cat_rename", "✎", "Rename (the key used by overrides stays the same)", `data-ci="${ci}"`)}
      ${ico("cat_del", "✕", "Remove the category from the list (files stay; Import will not bring its templates back)", `data-ci="${ci}"`)}
      <select class="kdx-sel" data-act="on_end" data-ci="${ci}" title="After the last template">${onEnd}</select>
    </div>
    <div class="kdx-tpls">${tpls || '<span class="kdx-muted">No templates.</span>'}</div>
    ${avail.length ? `<div class="kdx-row"><select class="kdx-sel" data-act="add_tpl" data-ci="${ci}" title="Add a template to this category">
      <option value="">＋ Add template…</option>${avail.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("")}</select></div>` : ""}
    ${cat.templates.length > 1 ? bulkRepeat(cat.templates, String(ci), "Images per template here:") : ""}
    <div class="kdx-row"><span class="kdx-muted">System prompt:</span>
      <select class="kdx-sel" data-act="sp" data-ci="${ci}">${sp}</select></div>
  </div>`;
}

function previewCard(s, view) {
  const items = (s.preview?.upcoming || []).map((u, i) =>
    `<li class="${i === 0 ? "first" : ""}">${esc(u.category_name)} › ${esc(u.template)} `
    + `<span class="kdx-muted">${u.mode === "sequential" ? `${u.index}/${u.repeat}` : u.mode}</span></li>`).join("");
  const promptBox = view.showPrompt
    ? `<div class="kdx-prompt">${view.promptText == null ? "…" : esc(view.promptText)}</div>` : "";
  return `<div class="kdx-card"><div class="kdx-row"><b>Preview</b><span class="kdx-sp"></span>
    <button class="kdx-btn" data-act="prompt">${view.showPrompt ? "Hide prompt" : "Show prompt"}</button></div>
    <ol class="kdx-list">${items || "<li class='kdx-muted'>—</li>"}</ol>${promptBox}</div>`;
}

function wildcardsCard(s) {
  const w = s.wildcards || {};
  if (w.error) return `<div class="kdx-card"><b>Wildcards</b><div class="kdx-err">${esc(w.error)}</div></div>`;
  const src = { config: "set here", env: "from KDX_CONSOLE_WILDCARD_DIRS", auto: "automatic" }[w.source] || "";
  const dirs = (w.dirs || []).map((d) => `<li>${esc(d)}${(w.missing_dirs || []).includes(d)
    ? ' <span class="kdx-warn">(not found)</span>' : ""}</li>`).join("") || "<li class='kdx-muted'>none</li>";
  const missing = (w.last_missing || []).length
    ? `<div class="kdx-warn">⚠ Last run left unknown wildcards: ${esc(w.last_missing.join(", "))}</div>` : "";
  const empty = !w.files ? `<div class="kdx-err">No wildcard files found. Set the folders.</div>` : "";
  const tip = w.user_dir && !(w.dirs || []).includes(w.user_dir)
    ? `<div class="kdx-muted">Tip: keep the files in <code>${esc(w.user_dir)}</code> (used automatically, backed up with the ComfyUI user folder).</div>` : "";
  return `<div class="kdx-card"><div class="kdx-row"><b>Wildcards</b>
    <span class="kdx-muted">${w.files ?? 0} files · ${w.templates ?? 0} templates · ${esc(src)}</span>
    <span class="kdx-sp"></span>
    <button class="kdx-btn" data-act="wc_dirs" title="Folders with wildcard .txt files (templates in templates/)">Folders…</button></div>
    <ul class="kdx-list kdx-muted">${dirs}</ul>${empty}${missing}${tip}</div>`;
}

/** Mount the panel into `el`; returns an unmount function. */
export function mountPanel(el) {
  ensureTheme();
  const root = document.createElement("div");
  root.className = "kdx-root kdx-panel";
  el.appendChild(root);
  const view = { showPrompt: false, promptText: null, profiles: [], dirty: false, bulk: {}, templates: [] };
  let promptSeq = 0;

  /** Templates in the wildcard folders (cached; refreshed after changes). */
  async function loadTemplates() {
    const d = await call("GET", "/kdx_console/templates");
    view.templates = d.ok ? d.templates : [];
    paint(getSnap());
  }
  /** Templates on disk that no category uses (removed ones included). */
  function available(cfg) {
    const used = new Set(cfg.categories.flatMap((c) => c.templates.map((t) => t.name)));
    return view.templates.filter((n) => !used.has(n));
  }

  async function fetchPrompt() {
    if (!view.showPrompt) return;
    const my = ++promptSeq;
    const pv = await previewPrompt(1);
    if (my !== promptSeq) return;
    view.promptText = pv.prompt ?? pv.prompt_error ?? pv.error ?? "";
    paint(getSnap());
  }

  function paint(s) {
    if (!s || !s.config) { root.innerHTML = `<div class="kdx-muted">Loading…</div>`; return; }
    // Do not rebuild under the user's cursor; repaint once the field loses focus.
    if (root.contains(document.activeElement) && document.activeElement.matches("input,select")) { view.dirty = true; return; }
    view.dirty = false;
    const avail = available(s.config);
    const scope = getScope();
    const cats = s.config.categories.map((c, ci) => catCard(c, ci, s, view.profiles, avail, scope)).join("")
      || `<div class="kdx-card kdx-muted">No categories yet. Click “Import templates” or “New category”.</div>`;
    root.innerHTML = `<div class="kdx-h"><span class="kdx-dot"></span>KDX Wildcard Studio</div>
      ${scopeCard(scope)}${nowCard(s)}${modeCard(s)}${cats}${previewCard(s, view)}${wildcardsCard(s)}`;
  }

  root.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-act]");
    if (!b || b.tagName === "SELECT" || b.tagName === "INPUT") return;
    const act = b.dataset.act;
    const ci = Number(b.dataset.ci);
    const ti = Number(b.dataset.ti);
    const cfg = getSnap()?.config;
    if (!cfg) return;
    if (act === "gallery") { import("./gallery.mjs?v=0.7.6").then((m) => m.openGallery()); return; }
    if (act === "builder") { import("./builder.mjs?v=0.7.6").then((m) => m.openBuilder()); return; }
    if (act === "packs") { import("./packs.mjs?v=0.7.6").then((m) => m.openPacks()); return; }
    if (act === "skip") action("/kdx_console/skip");
    else if (act === "reset") action("/kdx_console/reset");
    else if (act === "import") {
      const d = await call("POST", "/kdx_console/import", {});
      if (!d.ok) toast(d.error);
      else toast(`Added: ${d.report.added.length}, missing: ${d.report.missing.length}`, "success");
      loadTemplates();
    } else if (act === "restore") {
      const d = await call("POST", "/kdx_console/import", { restore: true });
      if (!d.ok) toast(d.error);
      else toast(`Restored: ${d.report.added.length}`, "success");
      loadTemplates();
    } else if (act === "cat_new") {
      const name = ((await askText({ title: "New category", text: "Name of the category. Add templates to it afterwards.",
        placeholder: "e.g. Landscapes", okLabel: "Create" })) || "").trim();
      if (!name) return;
      const key = slugKey(name);
      if (cfg.categories.some((c) => c.key === key)) { toast(`A category with the key “${key}” already exists.`); return; }
      editConfig((c) => { c.categories.push({ key, name, enabled: true, system_prompt: "", on_end: "next", templates: [] }); }, 0);
    } else if (act === "cat_move") editConfig((c) => moveItem(c.categories, ci, Number(b.dataset.d)), 0);
    else if (act === "tpl_move") editConfig((c) => moveItem(c.categories[ci].templates, ti, Number(b.dataset.d)), 0);
    else if (act === "cat_rename") {
      const cat = cfg.categories[ci];
      const v = ((await askText({ title: "Rename category", text: `The key “${cat.key}” stays the same, so overrides keep working.`,
        value: cat.name, okLabel: "Rename" })) || "").trim();
      if (v) editConfig((c) => { const x = c.categories.find((k) => k.key === cat.key); if (x) x.name = v; }, 0);
    } else if (act === "cat_del") {
      const cat = cfg.categories[ci];
      if (!(await askConfirm({ title: `Remove “${cat.name}”?`, okLabel: "Remove", danger: true,
        text: `Its ${cat.templates.length} template(s) are only removed from the configuration. The files stay, and “Add template…” or “Restore all” brings them back.` }))) return;
      editConfig((c) => {
        const at = c.categories.findIndex((k) => k.key === cat.key);
        if (at < 0) return;
        const gone = c.categories.splice(at, 1)[0];
        c.ignored = [...new Set([...(c.ignored || []), ...gone.templates.map((t) => t.name)])];
        if (c.select?.category === gone.key) c.select = null;
      }, 0);
    } else if (act === "tpl_del") {
      editConfig((c) => {
        const cat = c.categories[ci];
        const gone = cat.templates.splice(ti, 1)[0];
        c.ignored = [...new Set([...(c.ignored || []), gone.name])];
        if (c.select?.category === cat.key && c.select?.template === gone.name) c.select = null;
      }, 0);
    } else if (act === "wc_dirs") {
      const v = await askText({ title: "Wildcard folders", multiline: true, rows: 5, okLabel: "Save",
        text: "Folders on the server with your wildcard .txt files (templates in templates/). One per line. Empty = automatic.",
        placeholder: "/path/to/wildcards", value: (cfg.wildcard_dirs || []).join("\n") });
      if (v === null) return;
      const dirs = v.split(/[\n;]/).map((d) => d.trim()).filter(Boolean);
      editConfig((c) => { c.wildcard_dirs = dirs; }, 0);
    } else if (act === "mode") editConfig((c) => { c.mode = b.dataset.mode; }, 0);
    else if (act === "llm") editConfig((c) => { c.llm_enabled = !c.llm_enabled; }, 0);
    else if (act === "nsfw") { editConfig((c) => { c.show_nsfw = !c.show_nsfw; }, 0); setTimeout(loadTemplates, 400); }
    else if (act === "scope") {
      const on = b.dataset.on === "1";
      const cur = getScope();
      if (on && !cur) setScope({ channel: newChannel(), set: {} });
      else if (!on && cur) {
        if (Object.keys(cur.set).length && !(await askConfirm({ title: "Use the shared settings?", okLabel: "Use shared",
          text: "This workflow's own on/off is forgotten and it uses the shared counter again." }))) return;
        setScope(null);
      }
    } else if (act === "scope_clear") {
      const cur = getScope();
      if (cur) setScope({ ...cur, set: {} });
    } else if (act === "cat" || act === "tpl") {
      const scope = getScope();
      const cat = cfg.categories[ci];
      if (!scope) {
        if (act === "cat") editConfig((c) => { c.categories[ci].enabled = !c.categories[ci].enabled; });
        else editConfig((c) => { const t = c.categories[ci].templates[ti]; t.enabled = !t.enabled; });
        return;
      }
      // This workflow only: keep just the values that differ from the shared config.
      const key = act === "cat" ? cat.key : `${cat.key}.${cat.templates[ti].name}`;
      const shared = act === "cat" ? cat.enabled : cat.templates[ti].enabled;
      const next = !eff(scope, key, shared);
      const set = { ...scope.set };
      if (next === shared) delete set[key];
      else set[key] = next;
      setScope({ ...scope, set });
      paint(getSnap());
    }
    else if (act === "select") {
      const cat = cfg.categories[ci];
      setPick(cat.key, cat.templates[ti].name); // the next queued prompt keeps this template
      action("/kdx_console/select", { category: cat.key, template: cat.templates[ti].name });
    } else if (act === "prompt") {
      view.showPrompt = !view.showPrompt;
      view.promptText = null;
      paint(getSnap());
      fetchPrompt();
    } else if (act === "bulk") applyBulk(b.dataset.scope);
  });

  // Bulk "images per template": the typed value is kept in `view` (a repaint may replace the input).
  function applyBulk(scope) {
    const raw = view.bulk[scope] ?? root.querySelector(`[data-bulk="${scope}"]`)?.value;
    const v = parseInt(raw, 10);
    if (!Number.isFinite(v) || v < 1) { toast("Enter a number of images (1 or more)."); return; }
    const n = Math.min(100000, v);
    delete view.bulk[scope];
    editConfig((c) => {
      const cats = scope === "all" ? c.categories : [c.categories[Number(scope)]];
      for (const cat of cats) for (const t of cat?.templates || []) t.repeat = n;
    }, 0);
    toast(`${n} image${n === 1 ? "" : "s"} per template ${scope === "all" ? "in all categories" : "in this category"}.`, "success");
  }

  root.addEventListener("input", (e) => {
    const scope = e.target.dataset?.bulk;
    if (scope) view.bulk[scope] = e.target.value;
  });

  root.addEventListener("keydown", (e) => {
    const scope = e.target.dataset?.bulk;
    if (scope && e.key === "Enter") { e.preventDefault(); e.target.blur(); applyBulk(scope); }
  });

  root.addEventListener("change", (e) => {
    const t = e.target;
    const act = t.dataset?.act;
    const ci = Number(t.dataset.ci);
    if (act === "repeat") {
      const v = Math.max(1, Math.min(100000, parseInt(t.value, 10) || 1));
      editConfig((c) => { c.categories[ci].templates[Number(t.dataset.ti)].repeat = v; });
    } else if (act === "add_tpl") {
      const name = t.value;
      if (!name) return;
      t.blur(); // lets the panel repaint (it waits while a select has focus)
      editConfig((c) => {
        c.categories[ci].templates.push({ name, enabled: true, repeat: 1 });
        c.ignored = (c.ignored || []).filter((n) => n !== name);
      }, 0);
    } else if (act === "on_end") editConfig((c) => { c.categories[ci].on_end = t.value; });
    else if (act === "sp") editConfig((c) => { c.categories[ci].system_prompt = t.value; });
    else if (act === "pin_seed") editConfig((c) => { c.pin_seed = t.value === "" ? null : parseInt(t.value, 10); });
  });

  // Number fields: select the content on focus, so typing replaces it (no "2" + "5" = 25).
  // The mouseup that ends the focusing click would collapse the selection again, so it is skipped once.
  root.addEventListener("focusin", (e) => {
    const t = e.target;
    if (!t.matches?.("input.kdx-rep")) return;
    try { t.select(); } catch (_e) { /* not selectable */ }
    t.dataset.justFocused = "1";
  });
  root.addEventListener("mouseup", (e) => {
    const t = e.target;
    if (t.dataset?.justFocused) { e.preventDefault(); delete t.dataset.justFocused; }
  });
  root.addEventListener("keydown", (e) => { if (e.target.dataset?.justFocused) delete e.target.dataset.justFocused; }, true);

  // Number fields are plain text fields: a native number field changes its value on every wheel or touchpad
  // tick while it has focus, and every change was saved at once. Only digits are kept; ↑/↓ step by one
  // (and save at once, like the old spinner); Enter confirms.
  root.addEventListener("input", (e) => {
    const t = e.target;
    if (!t.matches?.("input.kdx-rep")) return;
    const clean = t.value.replace(/\D+/g, "");
    if (clean !== t.value) t.value = clean;
  }, true);
  root.addEventListener("keydown", (e) => {
    const t = e.target;
    if (!t.matches?.("input.kdx-rep")) return;
    if (e.key === "Enter" && !t.dataset.bulk) { e.preventDefault(); t.blur(); return; }
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault();
    const min = Number(t.dataset.min || 0);
    const cur = parseInt(t.value, 10);
    const base = Number.isFinite(cur) ? cur : min;
    t.value = String(Math.min(100000, Math.max(min, base + (e.key === "ArrowUp" ? 1 : -1))));
    t.dispatchEvent(new Event(t.dataset.bulk ? "input" : "change", { bubbles: true }));
  });

  root.addEventListener("focusout", () => {
    setTimeout(() => { if (view.dirty) paint(getSnap()); }, 0);
  });

  loadProfiles().then((p) => { view.profiles = p; paint(getSnap()); });
  loadTemplates();
  const unsub = subscribe((s) => { paint(s); if (view.showPrompt) fetchPrompt(); });
  paint(getSnap());
  return () => { unsub(); root.remove(); };
}
