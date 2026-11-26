// KDX Wildcard Studio - Packs: share templates with every pool they need as one .zip, and install packs from others.
// Full window from the panel, three tabs: Installed (uninstall), Import (upload -> checks + preview -> install),
// Export (pick templates -> check -> download). The server checks and writes everything (packs.py); a pack is
// text only and goes into its own namespace packs/<pack>/, so nothing of the user's library is overwritten.
import { api } from "../../../scripts/api.js";
import { ensureTheme } from "./theme.mjs?v=0.7.2";
import { call, getSnap, refresh, toast } from "./client.mjs?v=0.7.2";
import { askConfirm } from "./dialog.mjs?v=0.7.2";

const META_KEY = "kdx_console.packs.meta";
let win = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const kb = (n) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

function loadMeta() {
  try { return JSON.parse(localStorage.getItem(META_KEY) || "{}") || {}; } catch (_e) { return {}; }
}
function saveMeta(m) {
  try { localStorage.setItem(META_KEY, JSON.stringify({ author: m.author, license: m.license })); } catch (_e) { /* fine */ }
}

/** Send raw bytes (the zip) and read the JSON answer. */
async function upload(path, file) {
  try {
    const res = await api.fetchApi(path, { method: "POST", headers: { "Content-Type": "application/zip" }, body: file });
    try { return { status: res.status, ...(await res.json()) }; } catch (_e) { return { ok: false, status: res.status, error: `HTTP ${res.status}` }; }
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

function msgs(list, cls) {
  if (!list?.length) return "";
  return `<ul class="kdx-pk-msgs ${cls}">${list.map((m) => `<li>${m.file ? `<code>${esc(m.file)}</code>: ` : ""}${esc(m.msg)}</li>`).join("")}</ul>`;
}

function checks(r) {
  const e = r.errors || [], w = r.warnings || [];
  if (!e.length && !w.length) return `<p class="kdx-ok">✓ All checks passed.</p>`;
  return `${e.length ? `<p class="kdx-err">✕ ${plural(e.length, "error")}: the pack cannot be ${r._export ? "exported" : "installed"}.</p>${msgs(e, "kdx-err")}` : `<p class="kdx-ok">✓ No errors.</p>`}
    ${w.length ? `<details ${e.length ? "" : "open"}><summary class="kdx-warn">${plural(w.length, "warning")}</summary>${msgs(w, "kdx-warn")}</details>` : ""}`;
}

export function closePacks() { win?.close(); }

/** Open the packs window; `opts.tab` = installed | import | export, `opts.templates` preselects for export. */
export async function openPacks(opts = {}) {
  ensureTheme();
  closePacks();
  const m = loadMeta();
  const v = {
    tab: opts.tab || "installed", list: [], hidden: 0, showNsfw: false, licenses: [], templates: [], limits: {},
    loading: true, error: "", busy: false,
    imp: { file: null, report: null, category: "", newName: "" },
    exp: { sel: new Set(opts.templates || []), filter: "", plan: null,
      meta: { name: "", title: "", author: m.author || "", version: "1.0.0", description: "", license: m.license || "", nsfw: false } },
  };
  const el = document.createElement("div");
  el.className = "kdx-root kdx-gal kdx-pk";
  document.body.appendChild(el);

  // ---------------------------------------------------------------- installed
  function installedHtml() {
    if (v.loading) return `<p class="kdx-muted">Loading…</p>`;
    if (v.error) return `<p class="kdx-err">${esc(v.error)}</p>`;
    const hidden = v.hidden ? `<p class="kdx-muted">${plural(v.hidden, "NSFW pack")} hidden (NSFW switch in the panel).</p>` : "";
    if (!v.list.length) {
      return `<div class="kdx-card kdx-muted">No packs installed yet. Get a pack <b>.zip</b> from someone and open it in <b>Import</b>,
        or share your own templates with <b>Export</b>.</div>${hidden}`;
    }
    return `<div class="kdx-pk-grid">${v.list.map((p) => `<div class="kdx-card kdx-pk-card">
      <h3>${esc(p.title || p.name)} <span class="kdx-muted">${esc(p.version)}</span></h3>
      <div class="kdx-row"><span class="kdx-pk-tag" title="Pack name = folder packs/${esc(p.name)}/">${esc(p.name)}</span>
        <span class="kdx-pk-tag">${esc(p.license || "no license")}</span>${p.nsfw ? `<span class="kdx-pk-tag nsfw">NSFW</span>` : ""}
        <span class="kdx-muted">by ${esc(p.author || "?")}</span></div>
      ${p.description ? `<div>${esc(p.description)}</div>` : ""}
      <div class="kdx-muted">${plural(p.templates.length, "template")}: ${p.templates.map(esc).join(", ")}</div>
      <div class="kdx-muted">${plural(p.pools || 0, "pool")} · installed ${esc((p.installed_at || "").replace("T", " "))}</div>
      <div class="kdx-row"><span class="kdx-sp"></span>
        <button class="kdx-btn" data-p="uninstall" data-name="${esc(p.name)}" title="Remove packs/${esc(p.name)}/ and its templates">Uninstall…</button></div>
    </div>`).join("")}</div>${hidden}`;
  }

  // ---------------------------------------------------------------- import
  function importHtml() {
    const r = v.imp.report;
    const cats = getSnap()?.config?.categories || [];
    const drop = `<div class="kdx-pk-drop" data-drop>Drop a pack <b>.zip</b> here or
      <label class="kdx-btn kdx-primary" style="display:inline-block">Choose file…<input type="file" accept=".zip,application/zip" data-p="file" hidden></label>
      <div class="kdx-muted" style="margin-top:6px">Text only: .txt files and pack.json, at most ${esc(v.limits.zip_mb || 8)} MB. The pack is checked first;
      nothing is written until you click Install, and it never overwrites your own pools or templates.</div></div>`;
    if (!r) return drop + (v.busy ? `<p class="kdx-muted">Checking…</p>` : "");
    if (r.fatal) return `${drop}<div class="kdx-card"><p class="kdx-err">✕ ${esc(r.fatal)}</p></div>`;
    const p = r.pack || {};
    const st = { new: 0, same: 0, differs: 0 };
    for (const x of r.pools || []) st[x.status] = (st[x.status] || 0) + 1;
    const nsfwTag = p.nsfw ? `<span class="kdx-pk-tag nsfw">NSFW</span>` : "";
    return `${drop}<div class="kdx-card kdx-pk-card">
      <h3>${esc(p.title || p.name || "?")} <span class="kdx-muted">${esc(p.version || "")}</span></h3>
      <div class="kdx-row"><span class="kdx-pk-tag">${esc(p.name || "?")}</span><span class="kdx-pk-tag">${esc(p.license || "no license")}</span>${nsfwTag}
        <span class="kdx-muted">by ${esc(p.author || "?")} · ${esc(v.imp.file?.name || "")} · ${kb(r.size || 0)}</span></div>
      ${p.description ? `<div>${esc(p.description)}</div>` : ""}
      ${r.installed ? `<p class="kdx-warn">Version ${esc(r.installed)} of this pack is installed: Install replaces it (its templates keep their names).</p>` : ""}
      ${checks(r)}
      ${(r.templates || []).length ? `<h4 style="margin:6px 0 0">Adds ${plural(r.templates.length, "template")}</h4>
      <table class="kdx-pk-tbl"><tr><th>In the pack</th><th>Installed as</th><th></th></tr>${r.templates.map((t) => `<tr><td>${esc(t.name)}</td>
        <td><code>${esc(t.installed_as)}</code></td><td class="kdx-muted">${t.exists ? `you have a template “${esc(t.name)}” too: it stays as it is` : ""}</td></tr>`).join("")}</table>` : ""}
      ${(r.pools || []).length ? `<details><summary>${plural(r.pools.length, "pool")} into <code>packs/${esc(p.name)}/</code>:
        ${st.new} new${st.same ? `, ${st.same} same as yours` : ""}${st.differs ? `, <span class="kdx-warn">${st.differs} differ from yours</span>` : ""}
        (yours stay unchanged; the pack uses its own copy)</summary>
        <table class="kdx-pk-tbl"><tr><th>Pool</th><th>Values</th><th>Your library</th></tr>${r.pools.map((x) => `<tr><td><code>${esc(x.key)}</code></td>
        <td>${x.values}</td><td class="${x.status === "differs" ? "kdx-warn" : "kdx-muted"}">${{ new: "—", same: "same values", differs: "you have a different pool of this name" }[x.status]}</td></tr>`).join("")}</table></details>` : ""}
      ${(r.samples || []).length ? `<h4 style="margin:6px 0 0">Example prompts</h4>${r.samples.map((s) => `<div class="kdx-pk-sample"><span class="kdx-muted">${esc(s.template)} · seed ${s.seed}</span><br>${esc(s.text)}</div>`).join("")}` : ""}
      <div class="kdx-row" style="margin-top:6px">
        <label class="kdx-row" style="gap:4px">Add templates to <select class="kdx-sel" data-p="category">
          <option value="" ${v.imp.category === "" ? "selected" : ""}>no category</option>
          <option value="__new__" ${v.imp.category === "__new__" ? "selected" : ""}>new category…</option>
          ${cats.map((c) => `<option value="${esc(c.key)}" ${c.key === v.imp.category ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
        ${v.imp.category === "__new__" ? `<input class="kdx-sel" data-p="newName" value="${esc(v.imp.newName)}" placeholder="category name" style="width:180px">` : ""}
        <span class="kdx-sp"></span>
        <button class="kdx-btn" data-p="clear">Cancel</button>
        <button class="kdx-btn kdx-primary" data-p="install" ${r.can_install && !v.busy ? "" : "disabled"}>${v.busy ? "Installing…" : r.installed ? "Replace" : "Install"}</button>
      </div></div>`;
  }

  // ---------------------------------------------------------------- export
  function exportHtml() {
    const e = v.exp, mm = e.meta;
    const q = e.filter.trim().toLowerCase();
    const list = v.templates.filter((t) => !q || t.toLowerCase().includes(q));
    const lic = [...new Set([...(v.licenses || []), mm.license].filter(Boolean))];
    const plan = e.plan;
    return `<div class="kdx-card kdx-pk-card">
      <h3>1. Templates <span class="kdx-muted">${e.sel.size} picked · the pools they use come along by themselves</span></h3>
      <div class="kdx-row"><input class="kdx-sel" type="search" data-p="filter" value="${esc(e.filter)}" placeholder="filter…" style="width:200px">
        <button class="kdx-btn" data-p="all" title="Pick every template the filter shows">All shown</button>
        <button class="kdx-btn" data-p="none">None</button>
        ${v.showNsfw ? "" : `<span class="kdx-muted">NSFW templates hidden (NSFW switch in the panel)</span>`}</div>
      <div class="kdx-pk-list">${list.map((t) => `<label title="${esc(t)}"><input type="checkbox" data-p="pick" data-t="${esc(t)}" ${e.sel.has(t) ? "checked" : ""}>${esc(t)}</label>`).join("") || `<span class="kdx-muted">No templates.</span>`}</div>
    </div>
    <div class="kdx-card kdx-pk-card"><h3>2. About the pack</h3>
      <div class="kdx-pk-form">
        <label>Name *</label><input class="kdx-field" data-m="name" value="${esc(mm.name)}" placeholder="street_portraits (a-z, 0-9, _)" maxlength="32">
        <label>Title</label><input class="kdx-field" data-m="title" value="${esc(mm.title)}" placeholder="Street portraits" maxlength="80">
        <label>Author *</label><input class="kdx-field" data-m="author" value="${esc(mm.author)}" placeholder="your nickname (not your real name, unless you want to)" maxlength="64">
        <label>Version</label><input class="kdx-field" data-m="version" value="${esc(mm.version)}" placeholder="1.0.0" maxlength="16">
        <label>License</label><select class="kdx-field" data-m="license">${lic.map((l) => `<option ${l === (mm.license || v.defaultLicense) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
        <label>Description</label><textarea class="kdx-field" data-m="description" rows="3" maxlength="2000" placeholder="What the templates make; what to connect">${esc(mm.description)}</textarea>
        <label>NSFW</label><label class="kdx-row" style="color:inherit"><input type="checkbox" data-m="nsfw" ${mm.nsfw ? "checked" : ""}>
          marks the pack NSFW (set by itself when a template's name starts with nsfw, akt or sheer)</label>
      </div>
      <div class="kdx-muted">CC0-1.0 (default) = anyone may use it for anything, no credit needed; CC-BY-4.0 = the same, with credit to you. Packs describe adults only.</div>
    </div>
    <div class="kdx-card kdx-pk-card"><h3>3. Check and download</h3>
      <div class="kdx-row"><button class="kdx-btn" data-p="plan" ${e.sel.size && !v.busy ? "" : "disabled"}>Check</button>
        <button class="kdx-btn kdx-primary" data-p="export" ${e.sel.size && !v.busy ? "" : "disabled"}>⇩ Download .zip</button>
        ${v.busy ? `<span class="kdx-muted">Working…</span>` : ""}</div>
      ${plan ? (plan.fatal ? `<p class="kdx-err">✕ ${esc(plan.fatal)}</p>` : `<div>${plural(plan.files.length, "file")} · ${kb(plan.size)} · ${plural(plan.meta.templates.length, "template")}
        ${plan.meta.nsfw ? `<span class="kdx-pk-tag nsfw">NSFW</span>` : ""}</div>${checks({ ...plan, _export: true })}
        <details><summary>Files in the zip</summary><div class="kdx-pk-sample">pack.json\n${plan.files.map(esc).join("\n")}</div></details>`) : ""}
    </div>`;
  }

  function bodyHtml() {
    return { installed: installedHtml, import: importHtml, export: exportHtml }[v.tab]();
  }
  function headHtml() {
    const tab = (k, t, title) => `<button class="${v.tab === k ? "on" : ""}" data-p="tab" data-tab="${k}" title="${title}">${t}</button>`;
    return `<span class="kdx-gal-title">📦 Packs</span>
      <span class="kdx-seg">${tab("installed", `Installed${v.list.length ? ` (${v.list.length})` : ""}`, "Packs in packs/ of your wildcard folder")}${tab("import", "Import", "Check and install a pack .zip")}${tab("export", "Export", "Share templates with the pools they use as one .zip")}</span>
      <span class="kdx-sp"></span>
      <button class="kdx-btn" data-p="reload" title="Load again">⟳</button>
      <button class="kdx-btn" data-p="close" title="Close (Esc)">✕</button>`;
  }
  function render() {
    el.innerHTML = `<div class="kdx-gal-head">${headHtml()}</div><div class="kdx-pk-body">${bodyHtml()}</div>`;
  }
  const paintBody = () => { const b = el.querySelector(".kdx-pk-body"); if (b) b.innerHTML = bodyHtml(); };

  async function load() {
    v.loading = true;
    v.error = "";
    if (v.tab === "installed") paintBody();
    const d = await call("GET", "/kdx_console/packs");
    v.loading = false;
    if (!d.ok) v.error = d.error || "could not load";
    else Object.assign(v, { list: d.packs, hidden: d.hidden, showNsfw: !!d.show_nsfw, licenses: d.licenses, defaultLicense: d.default_license, templates: d.templates, limits: d.limits || {} });
    if (!v.exp.meta.license) v.exp.meta.license = v.defaultLicense || "";
    render();
  }

  // ---------------------------------------------------------------- actions
  async function inspect(file) {
    if (!file) return;
    v.imp = { ...v.imp, file, report: null };
    v.busy = true;
    paintBody();
    const d = await upload("/kdx_console/packs/inspect", file);
    v.busy = false;
    v.imp.report = d.ok ? d : { fatal: d.error || "could not read the file" };
    if (d.ok && v.imp.category === "__new__" && !v.imp.newName) v.imp.newName = d.pack?.title || d.pack?.name || "";
    paintBody();
  }

  async function install(replace = false) {
    const r = v.imp.report;
    if (!r?.can_install || !v.imp.file) return;
    const q = new URLSearchParams();
    if (replace || r.installed) q.set("replace", "1");
    if (v.imp.category === "__new__") {
      const n = v.imp.newName.trim();
      if (!n) { toast("Name the new category first."); return; }
      q.set("new_category", n);
    } else if (v.imp.category) q.set("category", v.imp.category);
    if (r.installed && !replace) {
      const ok = await askConfirm({ title: `Replace ${r.pack.name} ${r.installed}?`, okLabel: "Replace",
        text: `Version ${r.installed} is installed. It is replaced by ${r.pack.version}; templates you edited are kept as .bak.` });
      if (!ok) return;
    }
    v.busy = true;
    paintBody();
    const d = await upload(`/kdx_console/packs/install?${q}`, v.imp.file);
    v.busy = false;
    if (d.status === 409 && d.exists) {
      paintBody();
      const ok = await askConfirm({ title: "Pack installed already", text: `${d.error}\nReplace it with this version?`, okLabel: "Replace" });
      if (ok) install(true);
      return;
    }
    if (!d.ok) { toast(d.error || "install failed"); paintBody(); return; }
    const n = Object.keys(d.installed.templates || {}).length;
    toast(`Installed ${d.installed.name} ${d.installed.version}: ${plural(n, "template")}${d.category ? ` in ${d.category}` : ""}.`, "success");
    v.imp = { file: null, report: null, category: v.imp.category === "__new__" ? "" : v.imp.category, newName: "" };
    v.tab = "installed";
    refresh();
    load();
  }

  async function uninstall(name) {
    const p = v.list.find((x) => x.name === name);
    if (!p) return;
    const ok = await askConfirm({ title: `Uninstall ${p.title || p.name}?`, danger: true, okLabel: "Uninstall",
      text: `Deletes the folder packs/${p.name}/ (${plural(p.pools || 0, "pool")}) and ${plural(p.templates.length, "template")}: ${p.templates.join(", ")}.\n`
        + "They are taken out of your categories. A template you edited after installing is kept. This cannot be undone." });
    if (!ok) return;
    const d = await call("POST", "/kdx_console/packs/uninstall", { name });
    if (!d.ok) { toast(d.error); return; }
    toast(`Removed ${name}${d.kept.length ? `; kept your edited ${d.kept.join(", ")}` : ""}.`, "success");
    refresh();
    load();
  }

  const exportBody = () => ({ templates: [...v.exp.sel], meta: { ...v.exp.meta } });

  async function plan() {
    v.busy = true;
    paintBody();
    const d = await call("POST", "/kdx_console/packs/plan", exportBody());
    v.busy = false;
    v.exp.plan = d.ok ? d : { fatal: d.error };
    paintBody();
  }

  async function download() {
    saveMeta(v.exp.meta);
    v.busy = true;
    paintBody();
    let res;
    try {
      res = await api.fetchApi("/kdx_console/packs/export", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(exportBody()) });
    } catch (e) { res = null; toast(String(e)); }
    v.busy = false;
    if (res && (res.headers.get("Content-Type") || "").includes("application/zip")) {
      const blob = await res.blob();
      const m = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = m ? m[1] : "pack.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 10000);
      toast(`Saved ${a.download} (${kb(blob.size)}).`, "success");
      v.exp.plan = null;
    } else if (res) {
      let d;
      try { d = await res.json(); } catch (_e) { d = { error: `HTTP ${res.status}` }; }
      toast(d.error || "export failed");
      if (d.errors) { await plan(); return; } // show the whole check result
      v.exp.plan = { fatal: d.error || "export failed" };
    }
    paintBody();
  }

  // ---------------------------------------------------------------- events
  el.addEventListener("click", (e) => {
    const b = e.target.closest("[data-p]");
    if (!b || b.disabled || b.tagName === "SELECT" || (b.tagName === "INPUT" && b.type !== "checkbox")) return;
    const p = b.dataset.p;
    if (p === "close") close();
    else if (p === "reload") load();
    else if (p === "tab") { v.tab = b.dataset.tab; render(); }
    else if (p === "uninstall") uninstall(b.dataset.name);
    else if (p === "clear") { v.imp = { ...v.imp, file: null, report: null }; paintBody(); }
    else if (p === "install") install();
    else if (p === "all") {
      const q = v.exp.filter.trim().toLowerCase();
      for (const t of v.templates) if (!q || t.toLowerCase().includes(q)) v.exp.sel.add(t);
      v.exp.plan = null;
      paintBody();
    } else if (p === "none") { v.exp.sel.clear(); v.exp.plan = null; paintBody(); }
    else if (p === "plan") plan();
    else if (p === "export") download();
  });
  el.addEventListener("change", (e) => {
    const t = e.target;
    if (t.dataset.p === "file") inspect(t.files?.[0]);
    else if (t.dataset.p === "pick") {
      if (t.checked) v.exp.sel.add(t.dataset.t); else v.exp.sel.delete(t.dataset.t);
      v.exp.plan = null;
      const h = el.querySelector(".kdx-pk-card h3 .kdx-muted");
      if (h) h.textContent = `${v.exp.sel.size} picked · the pools they use come along by themselves`;
      for (const btn of el.querySelectorAll('[data-p="plan"],[data-p="export"]')) btn.disabled = !v.exp.sel.size || v.busy;
    } else if (t.dataset.p === "category") {
      v.imp.category = t.value;
      if (t.value === "__new__" && !v.imp.newName) v.imp.newName = v.imp.report?.pack?.title || v.imp.report?.pack?.name || "";
      paintBody();
    } else if (t.dataset.m === "nsfw") { v.exp.meta.nsfw = t.checked; v.exp.plan = null; }
    else if (t.dataset.m === "license") { v.exp.meta.license = t.value; v.exp.plan = null; }
  });
  el.addEventListener("input", (e) => {
    const t = e.target;
    if (t.dataset.p === "filter") {
      v.exp.filter = t.value;
      const q = t.value.trim().toLowerCase();
      for (const lab of el.querySelectorAll(".kdx-pk-list label")) lab.hidden = !!q && !lab.title.toLowerCase().includes(q);
    } else if (t.dataset.p === "newName") v.imp.newName = t.value;
    else if (t.dataset.m && t.dataset.m !== "nsfw") { v.exp.meta[t.dataset.m] = t.value; v.exp.plan = null; }
  });
  el.addEventListener("dragover", (e) => {
    const d = e.target.closest?.("[data-drop]");
    if (!d) return;
    e.preventDefault();
    d.classList.add("over");
  });
  el.addEventListener("dragleave", (e) => e.target.closest?.("[data-drop]")?.classList.remove("over"));
  el.addEventListener("drop", (e) => {
    const d = e.target.closest?.("[data-drop]");
    if (!d) return;
    e.preventDefault();
    d.classList.remove("over");
    inspect(e.dataTransfer?.files?.[0]);
  });
  function onKey(e) {
    if (e.key !== "Escape" || document.querySelector(".kdx-modal") || e.target?.matches?.("input,textarea,select")) return;
    e.preventDefault();
    e.stopPropagation();
    close();
  }
  document.addEventListener("keydown", onKey, true);
  function close() {
    document.removeEventListener("keydown", onKey, true);
    el.remove();
    win = null;
  }
  win = { close };
  render();
  load();
}
